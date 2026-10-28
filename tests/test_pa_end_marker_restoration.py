"""#357 WP2-d：PA「結束標記還原」受控接受（PLAN-v2 §2.3③）。

舊 published build 是在最後事件 content＝「比賽結束／主審裁定比賽結束」時建的；寫入端修正
＋回補後，同一場重建只有最後一個 PA 的最後成員指紋變動。此型態自動接受、留痕；其他任何
差異仍走原 fail closed。三個必過負控：同場另一處內容變動、不變式違反、非標記內容變動。

事件取自 #357 研究 2 的 www 原文（fixture 見 `test_livelog_primary_row.py`），經現行寫入端
轉換——與 builder 實際讀到的 `game_livelog` 同形。紅綠紀錄見 `~/.wf-evidence/cpbl-analytics/357/exec-wp2/`。
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import pytest

from cpbl.ingest import pa_build
from cpbl.ingest.cpbl_gamelog import _LL_COLS, _livelog_rows
from cpbl.ingest.pa_build import (
    ACCEPT_SHAPE_END_MARKER,
    end_marker_restoration,
    event_sort_key,
    half_inning_out_violations,
    load_taxonomy,
    plate_appearances,
    reconcile,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "livelog_357_www"
TAX = load_taxonomy()
# (檔名, 原文標記 content)
CASES = [
    ("2026-C-4.json.gz", "比賽結束"),
    ("2026-D-118.json.gz", "主審裁定比賽結束"),
    ("2026-D-163.json.gz", "主審裁定比賽結束"),
]


def _ident(name: str) -> tuple[int, str, int]:
    year, kind, sno = name.removesuffix(".json.gz").split("-")
    return int(year), kind, int(sno)


def _events(name: str) -> list[dict]:
    raw = json.loads(json.loads(gzip.decompress((FIXTURES / name).read_bytes()))["LiveLogJson"])
    cols = _LL_COLS.split(",")
    return [dict(zip(cols, r, strict=True)) for r in _livelog_rows(*_ident(name), raw)]


def _with_marker(events: list[dict], marker: str) -> list[dict]:
    """舊 DB 前態：最後事件 content 被標記覆蓋、is_special_event 帶標記列的 True。"""
    last = max(events, key=event_sort_key)
    return [{**e, "content": marker, "is_special_event": True} if e is last else e for e in events]


def _published(events: list[dict], name: str) -> dict[str, str]:
    return {str(pa.pa_id): pa.pa_fingerprint() for pa in plate_appearances(*_ident(name), events, TAX)}


def _decide(name: str, old: list[dict], new: list[dict]):
    pas = plate_appearances(*_ident(name), new, TAX)
    published = _published(old, name)
    rec = reconcile(pas, published)
    return rec, end_marker_restoration(pas, published, new, rec,
                                       invariant_violations=half_inning_out_violations(pas))


@pytest.mark.parametrize(("name", "marker"), CASES)
def test_restored_last_content_is_accepted(name, marker):
    new = _events(name)
    rec, shape = _decide(name, _with_marker(new, marker), new)
    assert rec.action == "reconcile" and len(rec.changed_pa_ids) == 1  # 前提：原路徑會擋
    assert shape is not None and shape["shape"] == ACCEPT_SHAPE_END_MARKER
    assert shape["old_content"] == marker and shape["old_is_special_event"] is True
    assert shape["event_no"] == max(new, key=event_sort_key)["main_event_no"]


def test_accepts_when_361_already_fixed_content_but_special_flag_differs():
    """#361 方案乙前態：content 舊值是標記、is_special_event 舊值 False 也在型態內。"""
    name, marker = CASES[0]
    new = _events(name)
    last = max(new, key=event_sort_key)
    old = [{**e, "content": marker, "is_special_event": False} if e is last else e for e in new]
    _rec, shape = _decide(name, old, new)
    assert shape is not None and shape["old_is_special_event"] is False


def test_negative_another_content_change_in_same_game_is_rejected():
    """負控 1：同場另有一處（非最後 PA）內容變動 → 不是本型態，仍 reconcile。"""
    name, marker = CASES[0]
    new = _events(name)
    old = _with_marker(new, marker)
    first = min(old, key=event_sort_key)
    old = [{**e, "content": "（官方事後改過的敘述）"} if e is first else e for e in old]
    rec, shape = _decide(name, old, new)
    assert rec.action == "reconcile" and len(rec.changed_pa_ids) == 2
    assert shape is None


def test_negative_invariant_violation_wins():
    """負控 2：不變式違反時，型態完全吻合也不接受。"""
    name, marker = CASES[0]
    new = _events(name)
    pas = plate_appearances(*_ident(name), new, TAX)
    published = _published(_with_marker(new, marker), name)
    rec = reconcile(pas, published)
    assert end_marker_restoration(pas, published, new, rec, invariant_violations=[]) is not None
    # 真實樣本形狀（2019/A/173 的 validation_summary.invariant_violations）
    real = [{"half": "1", "inning": 1, "out_pa": 4}]
    assert end_marker_restoration(pas, published, new, rec, invariant_violations=real) is None


def test_negative_non_marker_old_content_is_rejected():
    """負控 3：最後成員舊 content 不是結束標記（真的來源漂移）→ 不接受。"""
    name, _marker = CASES[0]
    new = _events(name)
    last = max(new, key=event_sort_key)
    old = [{**e, "content": "擊出右外野高飛球，二壘安打。"} if e is last else e for e in new]
    rec, shape = _decide(name, old, new)
    assert rec.action == "reconcile" and shape is None


def test_negative_other_field_changed_alongside_content_is_rejected():
    """只允許 content、is_special_event 兩欄不同：舊值另有一欄不同（比分）即不接受。"""
    name, marker = CASES[0]
    new = _events(name)
    last = max(new, key=event_sort_key)
    old = [{**e, "content": marker, "is_special_event": True, "home_score": (e["home_score"] or 0) + 1}
           if e is last else e for e in new]
    _rec, shape = _decide(name, old, new)
    assert shape is None


def test_negative_new_content_still_marker_is_rejected():
    """新值仍是標記（例如另一種標記字面互換）不屬「還原」。"""
    name, _marker = CASES[1]
    new = _events(name)
    old = _with_marker(new, "主審裁定比賽結束")
    newer = _with_marker(new, "比賽結束")
    _rec, shape = _decide(name, old, newer)
    assert shape is None


def test_identical_source_is_plain_publish_not_shape():
    name, _marker = CASES[0]
    new = _events(name)
    rec, shape = _decide(name, new, new)
    assert rec.action == "publish" and shape is None


def test_builder_version_bumped_for_reconcile_decision_change():
    """版本紀律（pa_build.py 檔頭）：預設路徑的 reconcile 決策改變必須進位。"""
    assert pa_build.BUILDER_VERSION == "pa-build-1.7.0"  # 1.5.0／1.6.0：#357 第 5 項逐場黃金值


# ── DB：真的走 build_game（隔離庫；DB 不可達時 skip）────────────────────────────────
_KEY = (1900, "A", 357)


def _db_events(name: str, marker: bool) -> list[tuple]:
    rows = _livelog_rows(*_ident(name), json.loads(json.loads(
        gzip.decompress((FIXTURES / name).read_bytes()))["LiveLogJson"]))
    cols = _LL_COLS.split(",")
    i_c, i_s = cols.index("content"), cols.index("is_special_event")
    last = max(range(len(rows)), key=lambda k: event_sort_key({"main_event_no": rows[k][3]}))
    out = []
    for k, r in enumerate(rows):
        r = list((*_KEY, *r[3:]))
        if marker and k == last:
            r[i_c], r[i_s] = "比賽結束", True
        out.append(tuple(r))
    return out


def _wipe(c) -> None:
    c.execute("DELETE FROM cpbl.game_pa_pitch_mappings WHERE year=%s AND kind_code=%s AND game_sno=%s", _KEY)
    c.execute("DELETE FROM cpbl.game_pa_events e USING cpbl.game_plate_appearances pa "
              "WHERE e.pa_row_id=pa.pa_row_id AND pa.year=%s AND pa.kind_code=%s AND pa.game_sno=%s", _KEY)
    for t in ("game_plate_appearances", "game_recap_builds", "game_recap_source_revisions",
              "game_livelog"):
        c.execute(f"DELETE FROM cpbl.{t} WHERE year=%s AND kind_code=%s AND game_sno=%s", _KEY)


def _load_db(c, rows: list[tuple]) -> None:
    c.execute("DELETE FROM cpbl.game_livelog WHERE year=%s AND kind_code=%s AND game_sno=%s", _KEY)
    c.cursor().executemany(
        f"INSERT INTO cpbl.game_livelog ({_LL_COLS}) VALUES ({','.join(['%s'] * 31)})", rows)


def test_build_game_shape_publishes_and_records_shape():
    from psycopg.rows import dict_row

    from cpbl.db import conn

    try:
        with conn() as c:
            _wipe(c)
            _load_db(c, _db_events("2026-C-4.json.gz", marker=True))
            first = pa_build.build_game(c.cursor(row_factory=dict_row), *_KEY)
    except Exception as exc:  # noqa: BLE001 — 無 DB 的環境
        pytest.skip(f"DB 不可用：{type(exc).__name__}")
    try:
        assert first.action == "publish"
        with conn() as c:
            _load_db(c, _db_events("2026-C-4.json.gz", marker=False))
            second = pa_build.build_game(c.cursor(row_factory=dict_row), *_KEY)
        assert second.action == "shape_publish" and second.build_state == "published"
        shape = second.summary["reconcile"]["accepted_shape"]
        assert shape["shape"] == ACCEPT_SHAPE_END_MARKER and shape["old_content"] == "比賽結束"
        assert second.summary["reconcile"]["accepted_reconciliation"] is False
        with conn() as c:
            states = dict(c.execute(
                "SELECT build_id::text, state FROM cpbl.game_recap_builds "
                "WHERE year=%s AND kind_code=%s AND game_sno=%s", _KEY).fetchall())
        assert states == {first.build_id: "superseded", second.build_id: "published"}
    finally:
        with conn() as c:
            _wipe(c)


def test_build_game_other_drift_still_reconciles():
    """DB 層負控：最後一列還原之外另有一處內容變動 → reconciliation_required、舊 published 保留。"""
    from psycopg.rows import dict_row

    from cpbl.db import conn

    try:
        with conn() as c:
            _wipe(c)
            _load_db(c, _db_events("2026-C-4.json.gz", marker=True))
            first = pa_build.build_game(c.cursor(row_factory=dict_row), *_KEY)
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"DB 不可用：{type(exc).__name__}")
    try:
        rows = _db_events("2026-C-4.json.gz", marker=False)
        i_c = _LL_COLS.split(",").index("content")
        rows[0] = (*rows[0][:i_c], "（官方事後改過的敘述）", *rows[0][i_c + 1:])
        with conn() as c:
            _load_db(c, rows)
            second = pa_build.build_game(c.cursor(row_factory=dict_row), *_KEY)
        assert second.action == "reconcile" and second.build_state == "reconciliation_required"
        assert second.summary["reconcile"]["accepted_shape"] is None
        with conn() as c:
            pub = c.execute("SELECT build_id::text FROM cpbl.game_recap_builds WHERE year=%s AND "
                            "kind_code=%s AND game_sno=%s AND state='published'", _KEY).fetchone()[0]
        assert pub == first.build_id
    finally:
        with conn() as c:
            _wipe(c)
