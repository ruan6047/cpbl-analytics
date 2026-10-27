"""#357 WP2 第 5 項：20 場「主審裁定比賽結束」標記列 IsChangePlayer=1 的 PA 受控接受（逐場黃金值）。

需求方裁定 issuecomment-6437358761：清單封閉 20 場，每場依黃金值鎖定預期差異（A 型末事件三欄、
B 型末 PA end_event_no、C 型舊末 PA 縮減＋新末打席）；實際差異與黃金值不完全相同一律擋下。
黃金值 `src/cpbl/resources/pa_end_marker_change_player.v1.json` 由 WP1 原文機械產生（產生器與
紀錄見 `~/.wf-evidence/cpbl-analytics/357/exec-wp2/gen/`）。

舊前態＝修正前寫入端（後到者勝）：每個事件號取原文**最後一列**整列轉換——標記列的
is_change_player=True 正是這 20 場的差異來源。
"""

from __future__ import annotations

import gzip
import json
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest

from cpbl.ingest import pa_build
from cpbl.ingest.cpbl_gamelog import _LL_COLS, _livelog_rows
from cpbl.ingest.pa_build import (
    ACCEPT_SHAPE_CHANGE_PLAYER,
    end_marker_change_player_restoration,
    end_marker_restoration,
    half_inning_out_violations,
    load_taxonomy,
    plate_appearances,
    reconcile,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "livelog_357_www"
TAX = load_taxonomy()
COLS = _LL_COLS.split(",")
EVIDENCE = Path(os.environ.get("CPBL_357_EVIDENCE", Path.home() / ".wf-evidence/cpbl-analytics/357"))

LIST_20 = frozenset((
    "2018-D-110 2018-D-118 2018-D-119 2018-D-136 2018-D-63 2018-D-73 2018-D-93 2019-A-39 "
    "2019-D-110 2019-D-114 2019-D-140 2019-D-22 2019-D-44 2019-D-69 2020-D-121 2020-D-149 "
    "2020-D-154 2020-D-191 2020-D-74 2020-D-84").split())
FIXTURE_SHAPES = {"2018-D-73": "A", "2018-D-110": "B", "2019-D-22": "C"}


def _key(name: str) -> tuple[int, str, int]:
    y, k, s = name.split("-")
    return int(y), k, int(s)


def _raw(path: Path) -> list[dict]:
    return json.loads(json.loads(gzip.decompress(path.read_bytes()))["LiveLogJson"])


def _new_old(raw: list[dict], key) -> tuple[list[dict], list[dict]]:
    new = [dict(zip(COLS, r, strict=True)) for r in _livelog_rows(*key, raw)]
    last: dict[str, dict] = {}
    for r in raw:
        last[r["MainEventNo"]] = r
    old = [dict(zip(COLS, _livelog_rows(*key, [r])[0], strict=True)) for r in last.values()]
    return new, old


def _decide(new: list[dict], old: list[dict], key, *, old_key=None):
    pas = plate_appearances(*key, new, TAX)
    published = {str(p.pa_id): p.pa_fingerprint() for p in plate_appearances(*(old_key or key), old, TAX)}
    rec = reconcile(pas, published)
    return rec, end_marker_change_player_restoration(
        pas, published, new, rec, invariant_violations=half_inning_out_violations(pas))


def _fixture(name: str):
    key = _key(name)
    return (*_new_old(_raw(FIXTURES / f"{name}.json.gz"), key), key)


# ── 黃金值檔本身 ─────────────────────────────────────────────────────────────────────
def test_golden_file_is_the_closed_20_game_list():
    games = pa_build.change_player_golden()
    assert set(games) == LIST_20
    assert Counter(g["shape"] for g in games.values()) == {"A": 3, "B": 15, "C": 2}


# ── 正控：repo 內真實原文（A／B／C 各一）────────────────────────────────────────────────
@pytest.mark.parametrize(("name", "shape"), FIXTURE_SHAPES.items())
def test_fixture_game_is_accepted_with_its_golden_shape(name, shape):
    new, old, key = _fixture(name)
    rec, got = _decide(new, old, key)
    assert rec.action == "reconcile"  # 前提：原路徑會擋
    assert end_marker_restoration(plate_appearances(*key, new, TAX),
                                  {str(p.pa_id): p.pa_fingerprint() for p in plate_appearances(*key, old, TAX)},
                                  new, rec) is None  # 前提：原謂詞接不住
    assert got is not None and got["shape"] == ACCEPT_SHAPE_CHANGE_PLAYER and got["golden_shape"] == shape
    assert got["game"] == name


# ── 負控：清單外出現同型差異 → 擋 ─────────────────────────────────────────────────────
@pytest.mark.parametrize("name", FIXTURE_SHAPES)
def test_negative_same_shape_outside_the_list_is_rejected(name):
    new, old, _key_ = _fixture(name)
    other = (2018, "D", 111)  # 不在清單（WP1：2018-D-111 是自佔標記場，不是 IsChangePlayer 場）
    _rec, got = _decide(new, old, other)
    assert got is None


# ── 負控：清單內出現非預期差異 → 擋 ─────────────────────────────────────────────────────
def _final_no(events: list[dict]) -> str:
    return max(events, key=pa_build.event_sort_key)["main_event_no"]


@pytest.mark.parametrize("name", FIXTURE_SHAPES)
def test_negative_extra_content_change_elsewhere_is_rejected(name):
    new, old, key = _fixture(name)
    new = [{**e, "content": "（官方事後改過的敘述）"} if i == 0 else e for i, e in enumerate(new)]
    assert _decide(new, old, key)[1] is None


@pytest.mark.parametrize("name", FIXTURE_SHAPES)
def test_negative_old_marker_content_differs_from_golden(name):
    new, old, key = _fixture(name)
    fin = _final_no(old)
    old = [{**e, "content": "比賽結束"} if e["main_event_no"] == fin else e for e in old]
    assert _decide(new, old, key)[1] is None


@pytest.mark.parametrize("name", FIXTURE_SHAPES)
def test_negative_old_marker_without_change_player_flag(name):
    new, old, key = _fixture(name)
    fin = _final_no(old)
    old = [{**e, "is_change_player": False} if e["main_event_no"] == fin else e for e in old]
    assert _decide(new, old, key)[1] is None


@pytest.mark.parametrize(("name", "field", "value"), [
    ("2018-D-110", "changed_pa_old_fields", {"end_event_no": "0720007000"}),   # B 型 end_event_no 不符
    ("2018-D-110", "changed_pa_old_fields", {}),                               # B 型當 A 型
    ("2018-D-73", "changed_pa_old_fields", {"end_event_no": "0820005000"}),    # A 型當 B 型
    ("2019-D-22", "added_pas", []),                                            # C 型少了新末打席
    ("2018-D-110", "final_event_no", "0720008000"),
])
def test_negative_golden_mismatch_is_rejected(monkeypatch, name, field, value):
    golden = {k: dict(v) for k, v in pa_build.change_player_golden().items()}
    golden[name][field] = value
    monkeypatch.setattr(pa_build, "change_player_golden", lambda: golden)
    new, old, key = _fixture(name)
    assert _decide(new, old, key)[1] is None


def test_negative_c_shape_added_pa_field_mismatch(monkeypatch):
    golden = {k: dict(v) for k, v in pa_build.change_player_golden().items()}
    golden["2019-D-22"]["added_pas"] = [{**golden["2019-D-22"]["added_pas"][0], "result_action": "三振"}]
    monkeypatch.setattr(pa_build, "change_player_golden", lambda: golden)
    assert _decide(*_fixture("2019-D-22")[:2], _key("2019-D-22"))[1] is None


def test_negative_invariant_violation_wins():
    new, old, key = _fixture("2018-D-110")
    pas = plate_appearances(*key, new, TAX)
    published = {str(p.pa_id): p.pa_fingerprint() for p in plate_appearances(*key, old, TAX)}
    rec = reconcile(pas, published)
    assert end_marker_change_player_restoration(pas, published, new, rec,
                                                invariant_violations=[{"x": 1}]) is None


def test_builder_version_bumped():
    assert pa_build.BUILDER_VERSION == "pa-build-1.5.0"


# ── 全量：WP1 原文 20 場＋黃金值可重生（證據目錄不在時 skip）────────────────────────────
RAW = EVIDENCE / "exec-wp1" / "www-raw"


@pytest.mark.skipif(not RAW.is_dir(), reason="WP1 原文目錄不在（不進 repo）")
def test_all_20_wp1_games_are_accepted():
    from cpbl.ingest.livelog_replay import load_raw_games

    games, rej = load_raw_games(RAW, only={_key(n) for n in LIST_20}, sums_path=RAW.parent / "SHA256SUMS")
    assert not rej and len(games) == 20
    shapes = {}
    for key, g in games.items():
        new, old = _new_old(g.livelog, key)
        got = _decide(new, old, key)[1]
        assert got is not None, key
        shapes[got["game"]] = got["golden_shape"]
    assert Counter(shapes.values()) == {"A": 3, "B": 15, "C": 2}


GEN = EVIDENCE / "exec-wp2" / "gen" / "gen_pa_change_player_golden.py"


@pytest.mark.skipif(not (RAW.is_dir() and GEN.is_file()), reason="WP1 原文或產生器不在")
def test_packaged_golden_equals_regenerated(tmp_path):
    out = tmp_path / "golden.json"
    subprocess.run([sys.executable, str(GEN), str(RAW), str(RAW.parent / "SHA256SUMS"), str(out)],
                   check=True, capture_output=True)
    assert json.loads(out.read_text()) == json.loads(pa_build._CHANGE_PLAYER_GOLDEN_PATH.read_text())


SHAPE_JSON = EVIDENCE / "exec-wp2" / "logs" / "pa20-shape.json"


@pytest.mark.skipif(not SHAPE_JSON.is_file(), reason="pa20-shape.json 不在")
def test_golden_agrees_with_the_ruled_shape_report():
    """裁定依據 pa20-shape.json（sha256 b766bafb…7e49）：每場型別與 C 型拆分一致。"""
    import hashlib

    assert hashlib.sha256(SHAPE_JSON.read_bytes()).hexdigest().startswith("b766bafb")
    golden = pa_build.change_player_golden()
    for g in json.loads(SHAPE_JSON.read_text()):
        c = g["changed"][0]
        added = [a["members"] for a in g["added"]]
        if added:
            want = "C"
        else:
            want = "B" if c["old"]["end"] != c["new"]["end"] else "A"
        assert golden[g["game"]]["shape"] == want, g["game"]
        assert [a["members"] for a in golden[g["game"]]["added_pas"]] == added


# ── DB：build_game 實跑（隔離庫；用真實場次鍵，結束時清掉）─────────────────────────────
_DB_KEY = (2018, "D", 110)


def _wipe(c) -> None:
    c.execute("DELETE FROM cpbl.game_pa_pitch_mappings WHERE year=%s AND kind_code=%s AND game_sno=%s", _DB_KEY)
    c.execute("DELETE FROM cpbl.game_pa_events e USING cpbl.game_plate_appearances pa "
              "WHERE e.pa_row_id=pa.pa_row_id AND pa.year=%s AND pa.kind_code=%s AND pa.game_sno=%s", _DB_KEY)
    for t in ("game_plate_appearances", "game_recap_builds", "game_recap_source_revisions", "game_livelog"):
        c.execute(f"DELETE FROM cpbl.{t} WHERE year=%s AND kind_code=%s AND game_sno=%s", _DB_KEY)


def _load(c, events: list[dict]) -> None:
    c.execute("DELETE FROM cpbl.game_livelog WHERE year=%s AND kind_code=%s AND game_sno=%s", _DB_KEY)
    c.cursor().executemany(f"INSERT INTO cpbl.game_livelog ({_LL_COLS}) VALUES ({','.join(['%s'] * 31)})",
                           [tuple(e[col] for col in COLS) for e in events])


def test_build_game_change_player_shape_publishes():
    from psycopg.rows import dict_row

    from cpbl.db import conn

    new, old, _k = _fixture("2018-D-110")
    try:
        with conn() as c:
            if c.execute("SELECT current_database()").fetchone()[0] == "cpbl":
                pytest.skip("⛔ 不在共享 cpbl 庫寫真實場次鍵")
            _wipe(c)
            _load(c, old)
            first = pa_build.build_game(c.cursor(row_factory=dict_row), *_DB_KEY)
    except pytest.skip.Exception:
        raise
    except Exception as exc:  # noqa: BLE001 — 無 DB 的環境
        pytest.skip(f"DB 不可用：{type(exc).__name__}")
    try:
        assert first.action == "publish"
        with conn() as c:
            _load(c, new)
            second = pa_build.build_game(c.cursor(row_factory=dict_row), *_DB_KEY)
        assert second.action == "shape_publish" and second.build_state == "published"
        shape = second.summary["reconcile"]["accepted_shape"]
        assert shape["shape"] == ACCEPT_SHAPE_CHANGE_PLAYER and shape["golden_shape"] == "B"
    finally:
        with conn() as c:
            _wipe(c)
