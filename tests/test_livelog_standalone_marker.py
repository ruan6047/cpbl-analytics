"""#357 C1 回看：結束標記自佔事件號（85 場）——判定、寫入端記錄、檢查 (i) 豁免。

黃金值＝WP1 報告 §2.2 的 85 場封閉清單（`~/.wf-evidence/cpbl-analytics/357/exec-wp1/REPORT.md`）。
全量黃金值測試讀 WP1 原文目錄（3,905 場，不進 repo）；目錄不在時 skip，以 repo 內 5 份真實
原文 fixture 的測試代替。fixture 逐檔 sha256 與 WP1 `SHA256SUMS` 相同。
"""

from __future__ import annotations

import gzip
import json
import os
from pathlib import Path

import pytest

from cpbl.ingest import livelog_checks
from cpbl.ingest.cpbl_gamelog import (
    _LL_COLS,
    _is_end_marker,
    _livelog_rows,
    standalone_end_marker_no,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "livelog_357_www"
WP1_RAW = Path(os.environ.get("CPBL_357_WP1_RAW",
                              Path.home() / ".wf-evidence/cpbl-analytics/357/exec-wp1/www-raw"))

# WP1 REPORT §2.2 逐字清單（85 場）。
GOLDEN_85 = frozenset("""
2018-A-9 2018-A-14 2018-A-17 2018-A-38 2018-A-40 2018-A-44 2018-A-52 2018-A-80 2018-A-121
2018-A-132 2018-A-158 2018-A-162 2018-A-175 2018-D-3 2018-D-10 2018-D-29 2018-D-40 2018-D-58
2018-D-92 2018-D-95 2018-D-111 2018-D-123 2018-D-137 2018-D-141 2018-D-142 2018-D-143 2019-A-5
2019-A-26 2019-A-40 2019-A-60 2019-A-64 2019-A-77 2019-A-92 2019-A-110 2019-A-116 2019-A-117
2019-A-118 2019-A-129 2019-A-140 2019-A-162 2019-A-191 2019-A-217 2019-A-220 2019-A-236 2019-C-1
2019-D-18 2019-D-100 2019-D-127 2019-D-151 2020-A-21 2020-A-97 2020-A-117 2020-A-121 2020-A-126
2020-A-131 2020-A-132 2020-A-134 2020-A-140 2020-A-162 2020-A-176 2020-A-181 2020-A-183 2020-A-187
2020-A-196 2020-A-224 2020-A-225 2020-D-4 2020-D-23 2020-D-78 2020-D-102 2020-D-123 2020-D-124
2020-D-132 2020-D-143 2020-D-144 2020-D-159 2020-D-167 2020-D-176 2020-D-187 2020-D-189 2020-D-208
2020-D-214 2020-D-217 2020-D-224 2021-A-20
""".split())


def _raw(path: Path) -> list[dict]:
    return json.loads(json.loads(gzip.decompress(path.read_bytes()))["LiveLogJson"])


def test_golden_list_is_85_games():
    assert len(GOLDEN_85) == 85


# ── 純函式：repo 內真實原文 ─────────────────────────────────────────────────────────
@pytest.mark.parametrize(("name", "want"), [
    ("2019-A-118", "0920001000"),   # 9 局上結束、標記放在 9 局下第 1 號
    ("2018-A-175", "0720014000"),   # 主審裁定比賽結束、IsSpecialEvent='4'、IsChangePlayer='1'
])
def test_standalone_marker_detected(name, want):
    assert standalone_end_marker_no(_raw(FIXTURES / f"{name}.json.gz")) == want


@pytest.mark.parametrize("name", ["2026-C-4", "2026-D-118", "2018-D-110", "2019-A-39", "2020-D-84"])
def test_shared_number_group_is_not_standalone(name):
    """負控：實際事件＋標記同號兩列的場次不得被判成自佔。"""
    assert standalone_end_marker_no(_raw(FIXTURES / f"{name}.json.gz")) is None


def test_mutations_break_standalone():
    """負控（變異）：自佔場加一列同號非標記列／把標記改成非標記 → 都不是自佔。"""
    raw = _raw(FIXTURES / "2019-A-118.json.gz")
    last = raw[-1]
    assert standalone_end_marker_no([*raw[:-1], {**last, "Content": "擊出界外球。"}, last]) is None
    assert standalone_end_marker_no([*raw[:-1], {**last, "Content": "擊出界外球。"}]) is None
    assert standalone_end_marker_no([]) is None


# ── 全量黃金值：WP1 原文 3,905 場 ────────────────────────────────────────────────────
@pytest.mark.skipif(not WP1_RAW.is_dir(), reason="WP1 原文目錄不在（不進 repo）")
def test_golden_wp1_raw_yields_exactly_the_85_games():
    from cpbl.ingest.livelog_replay import load_raw_games

    games, rejected = load_raw_games(WP1_RAW, sums_path=WP1_RAW.parent / "SHA256SUMS")
    assert rejected == {} and len(games) == 3905
    hits = {f"{y}-{k}-{s}" for (y, k, s), g in games.items() if standalone_end_marker_no(g.livelog)}
    assert hits == GOLDEN_85
    # 其餘 3,820 場：每場恰一組同號，在最大事件號，前非標記後標記（負控母體）。
    for (y, k, s), g in games.items():
        if f"{y}-{k}-{s}" in GOLDEN_85:
            continue
        no = max(r["MainEventNo"] for r in g.livelog)
        grp = [r for r in g.livelog if r["MainEventNo"] == no]
        assert len(grp) == 2 and not _is_end_marker(grp[0]["Content"]) and _is_end_marker(grp[1]["Content"])


# ── 檢查 (i) 豁免：DB（隔離庫哨兵 year=1900）──────────────────────────────────────────
YEAR = 1900
KEY = (YEAR, "A", 118)


def _seed_main(c, raw: list[dict]) -> None:
    rows = [(*KEY, *r[3:]) for r in _livelog_rows(2019, "A", 118, raw)]
    c.cursor().executemany(f"INSERT INTO cpbl.game_livelog ({_LL_COLS}) VALUES ({','.join(['%s'] * 31)})",
                           rows)


def _seed_revision(c, detail: dict) -> None:
    from cpbl.ingest.game_source_revisions import record_source_revision

    del c
    record_source_revision(year=KEY[0], kind_code=KEY[1], game_sno=KEY[2], source="livelog",
                           outcome="available", row_count=1, payload=[{"x": json.dumps(detail)}],
                           detail=detail)


def _wipe(c) -> None:
    for t in ("game_livelog", "game_livelog_extra", "game_source_revisions"):
        c.execute(f"DELETE FROM cpbl.{t} WHERE year=%s", (YEAR,))


@pytest.fixture
def db():
    from cpbl.db import conn

    try:
        with conn() as c:
            _wipe(c)
            c.execute("SELECT 1 FROM cpbl.game_livelog_extra LIMIT 0")
    except Exception as exc:  # noqa: BLE001 — 無 DB／無 079 的環境
        pytest.skip(f"DB 不可用：{type(exc).__name__}")
    with conn() as c:
        _seed_main(c, _raw(FIXTURES / "2019-A-118.json.gz"))
    yield conn
    with conn() as c:
        _wipe(c)


def _last(**kw):
    return livelog_checks.run_checks(year=YEAR, **kw)["last_event"]


def test_no_raw_evidence_is_a_violation(db):
    res = _last()
    assert (res["violations"], res["exempt"]) == (1, 0)
    assert res["violation_games"][0]["evidence"] == "none"


def test_raw_dir_evidence_exempts(db):
    res = _last(standalone={KEY: "0920001000"})
    assert (res["violations"], res["exempt"]) == (0, 1)
    assert res["exempt_games"] == [{"game": "1900-A-118", "main_event_no": "0920001000",
                                    "reason": "exempt_standalone_marker", "evidence": "raw"}]
    assert res["by_scope"] == {"1900/A": {"games": 1, "violations": 0, "exempt": 1}}


def test_raw_says_shared_group_is_a_violation(db):
    """原文說末組不是自佔（同號未回補）→ 照樣違反。"""
    assert _last(standalone={KEY: None})["violations"] == 1


def test_raw_marker_on_other_event_no_is_a_violation(db):
    assert _last(standalone={KEY: "0910001000"})["violations"] == 1


def test_revision_detail_evidence_exempts(db):
    with db() as c:
        _seed_revision(c, {"phase": "getlive", "event_rows": 1, "standalone_end_marker": "0920001000"})
    res = _last()
    assert (res["violations"], res["exempt"]) == (0, 1)
    assert res["exempt_games"][0]["evidence"] == "revision"


def test_revision_without_key_or_null_is_a_violation(db):
    with db() as c:
        _seed_revision(c, {"phase": "getlive", "event_rows": 1})
    assert _last()["violations"] == 1
    with db() as c:
        _seed_revision(c, {"phase": "getlive", "event_rows": 1, "standalone_end_marker": None})
    assert _last()["violations"] == 1
