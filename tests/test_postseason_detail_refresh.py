"""#237：季後 E／C 明細自動補抓的離線測試（無 DB、無網路）。

只測新增的 `_postseason_detail_step`／`_missing_postseason_detail_snos`／`_postseason_detail_gaps`。
CI 無真實 Postgres，故一律 monkeypatch `conn`／被呼叫函式（比照既有 refresh 測試）。
⚠️ scheduled／final 判準本身在既有 SQL（`daily_chain_completed_games_sql`）；這裡只釘
「候選只來自完成判準查詢＋缺明細查詢」。stub 回傳值不是正式資料驗收。
main() 內呼叫順序不在此測（見執行者自檢的靜態控制流說明）。
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import date
from types import SimpleNamespace

import pytest

from cpbl.ingest import run_refresh_recent as rr

YEAR = 2026
DAYS = [date(2026, 10, 9), date(2026, 10, 10)]
SAME_GAME = "x.year = g.year AND x.kind_code = g.kind_code AND x.game_sno = g.game_sno"


class _FakeCursor:
    def __init__(self, rows: list[tuple]) -> None:
        self._rows = rows

    def fetchall(self) -> list[tuple]:
        return self._rows


class _FakeConn:
    def __init__(self, rows: list[tuple], calls: list) -> None:
        self._rows = rows
        self._calls = calls

    def execute(self, sql: str, params=None) -> _FakeCursor:
        self._calls.append((sql, params))
        return _FakeCursor(self._rows)


def _fake_conn(rows: list[tuple], calls: list):
    @contextmanager
    def _conn():
        yield _FakeConn(rows, calls)

    return _conn


def _forbid(name: str):
    def _boom(*args, **kwargs):
        raise AssertionError(f"不應呼叫 {name}")

    return _boom


def _gamelog_result(kind: str, snos: list[int], failed: tuple[int, ...] = ()) -> dict:
    """形狀比照 scrape_gamelogs 的對帳欄位（target／games／failed／failures）。

    ＋四個來源計數（scoreboard／livelog／batting_box／pitching_box），預設每個成功場各 1。"""
    games = len(snos) - len(failed)
    return {"kind_code": kind, "target": len(snos), "games": games,
            "failed": list(failed),
            "failures": [{"game_sno": s, "error": "stub"} for s in failed],
            "scoreboard": games, "livelog": games, "batting_box": games, "pitching_box": games}


@pytest.fixture
def wired(monkeypatch):
    """來源與查詢換成記錄器；completed／missing／after 模擬 DB 查詢結果。"""
    state: dict = {"completed": {}, "missing": {}, "after": {}, "calls": [], "gamelog": None,
                   "details_rows": None, "pitches_out": None, "day_pitchers": []}
    gaps: list[dict] = []
    monkeypatch.setattr(rr, "_GAMELOG_GAPS", gaps)
    monkeypatch.setattr(rr, "reconcile_line", lambda result: "stub")
    monkeypatch.setattr(rr, "requires_official_completion", lambda kind, year: True)
    monkeypatch.setattr(rr, "settings", SimpleNamespace(pitch_ingest="game"))
    monkeypatch.setattr(rr, "_pitchers_of_games", _forbid("_pitchers_of_games"))
    state["frozen"] = set()
    monkeypatch.setattr(rr, "is_frozen", lambda year, kind_code, sno: sno in state["frozen"])

    def completed(year, days, kind_code="A"):
        state["calls"].append(("completed", kind_code))
        return list(state["completed"].get(kind_code, []))

    def missing(year, kind_code, tables=rr._POSTSEASON_CORE_DETAIL_TABLES):
        state["calls"].append(("missing", kind_code, tables))
        return list(state["missing"].get(kind_code, []))

    def gamelogs(year, snos, kind_code="A", allow_partial=False):
        state["calls"].append(("gamelog", kind_code, list(snos), allow_partial))
        if state["gamelog"] is not None:
            return state["gamelog"](kind_code, list(snos))
        return _gamelog_result(kind_code, list(snos))

    def details(year, snos, kind_code="A"):
        state["calls"].append(("details", kind_code, list(snos)))
        return len(snos) if state["details_rows"] is None else state["details_rows"]

    def pitches(year, kind_code, day_snos, day_pitchers, delay):
        state["calls"].append(("pitches", kind_code, list(day_snos)))
        state["day_pitchers"].append(list(day_pitchers))
        if state["pitches_out"] is not None:
            return dict(state["pitches_out"])
        sent = [s for s in day_snos if s not in state["frozen"]]
        return {"games": len(sent), "pitches": 0, "skipped_frozen": len(day_snos) - len(sent),
                "pitcher_flags": len(sent), "mode": "game", "lagging_games": 0}

    def after(year, kind_code, snos, tables):
        state["calls"].append(("after", kind_code, list(snos), tables))
        return {s: t for s, t in state["after"].get(kind_code, {}).items() if s in snos}

    monkeypatch.setattr(rr, "_completed_snos", completed)
    monkeypatch.setattr(rr, "_missing_postseason_detail_snos", missing)
    monkeypatch.setattr(rr, "scrape_gamelogs", gamelogs)
    monkeypatch.setattr(rr, "scrape_game_details", details)
    monkeypatch.setattr(rr, "_refresh_pitches", pitches)
    monkeypatch.setattr(rr, "_postseason_detail_gaps", after)
    state["gaps"] = gaps
    return state


def _source_calls(state: dict) -> list[tuple]:
    return [c for c in state["calls"] if c[0] in ("gamelog", "details", "pitches")]


def test_empty_kinds_queries_and_scrapes_nothing(monkeypatch):
    for name in ("conn", "_completed_snos", "_missing_postseason_detail_snos",
                 "_postseason_detail_gaps", "scrape_gamelogs", "scrape_game_details",
                 "_refresh_pitches"):
        monkeypatch.setattr(rr, name, _forbid(name))
    assert rr._postseason_detail_step(YEAR, (), DAYS) == {"games": {}, "errors": []}


@pytest.mark.parametrize("kind", ["A", "D"])
def test_regular_kinds_rejected_by_postseason_paths(monkeypatch, kind):
    monkeypatch.setattr(rr, "conn", _forbid("conn"))
    with pytest.raises(ValueError):
        rr._postseason_detail_step(YEAR, (kind,), DAYS)
    with pytest.raises(ValueError):
        rr._missing_postseason_detail_snos(YEAR, kind)
    with pytest.raises(ValueError):
        rr._postseason_detail_gaps(YEAR, kind, [1], rr._POSTSEASON_CORE_DETAIL_TABLES)


def test_core_tables_are_exactly_the_six_verified_tables():
    assert rr._POSTSEASON_CORE_DETAIL_TABLES == (
        "batting_gamelog", "pitching_gamelog", "game_livelog", "game_scoreboard",
        "game_detail", "pitching_game_flags",
    )
    assert "pitch_tracking" not in rr._POSTSEASON_CORE_DETAIL_TABLES
    assert rr._POSTSEASON_FAST_DETAIL_TABLES == tuple(
        t for t in rr._POSTSEASON_CORE_DETAIL_TABLES if t != "pitching_game_flags"
    )


def test_ad_missing_helper_still_batting_only(monkeypatch):
    calls: list = []
    monkeypatch.setattr(rr, "conn", _fake_conn([(7,)], calls))
    assert rr._missing_gamelog_snos(YEAR, "A") == [7]
    [(sql, params)] = calls
    assert params == (YEAR, "A")
    assert "cpbl.batting_gamelog" in sql
    for table in rr._POSTSEASON_CORE_DETAIL_TABLES:
        if table != "batting_gamelog":
            assert f"cpbl.{table}" not in sql


def test_missing_helper_checks_each_core_table_on_exact_game_key(monkeypatch):
    calls: list = []
    monkeypatch.setattr(rr, "conn", _fake_conn([(1,), (4,)], calls))
    assert rr._missing_postseason_detail_snos(YEAR, "E") == [1, 4]
    [(sql, params)] = calls
    assert params == (YEAR, "E")
    assert rr.daily_chain_completed_games_sql("g") in sql
    for table in rr._POSTSEASON_CORE_DETAIL_TABLES:
        assert f"FROM cpbl.{table} x WHERE {SAME_GAME}" in sql
    assert sql.count(SAME_GAME) == len(rr._POSTSEASON_CORE_DETAIL_TABLES)


def test_missing_helper_fast_scope_omits_pitch_step_table(monkeypatch):
    calls: list = []
    monkeypatch.setattr(rr, "conn", _fake_conn([], calls))
    rr._missing_postseason_detail_snos(YEAR, "C", rr._POSTSEASON_FAST_DETAIL_TABLES)
    [(sql, params)] = calls
    assert params == (YEAR, "C")
    assert "pitching_game_flags" not in sql
    assert sql.count(SAME_GAME) == len(rr._POSTSEASON_CORE_DETAIL_TABLES) - 1


def test_gaps_helper_maps_missing_tables_per_game(monkeypatch):
    tables = rr._POSTSEASON_CORE_DETAIL_TABLES
    calls: list = []
    rows = [(1,) + (False,) * len(tables),
            (2,) + tuple(t in ("game_livelog", "game_scoreboard") for t in tables)]
    monkeypatch.setattr(rr, "conn", _fake_conn(rows, calls))
    assert rr._postseason_detail_gaps(YEAR, "E", [1, 2], tables) == {
        2: ["game_livelog", "game_scoreboard"],
    }
    [(sql, params)] = calls
    assert params == (YEAR, "E", [1, 2])
    for table in tables:
        assert f"FROM cpbl.{table} x WHERE {SAME_GAME}" in sql


def test_gaps_helper_empty_snos_does_not_query(monkeypatch):
    monkeypatch.setattr(rr, "conn", _forbid("conn"))
    assert rr._postseason_detail_gaps(YEAR, "E", [], rr._POSTSEASON_CORE_DETAIL_TABLES) == {}


def test_scheduled_e2_not_fetched_until_final(wired):
    # E2 仍 scheduled：完成判準與缺明細查詢都不回它 → 不碰任何來源
    out = rr._postseason_detail_step(YEAR, ("E",), DAYS)
    assert _source_calls(wired) == []
    assert out == {"games": {"E": {"completed_games": 0}}, "errors": []}
    # 官方 final 後完成判準回 E2 → 抓 gamelog／details／pitches，對帳無缺 → 無 errors
    wired["completed"] = {"E": [2]}
    out = rr._postseason_detail_step(YEAR, ("E",), DAYS)
    assert _source_calls(wired) == [
        ("gamelog", "E", [2], True), ("details", "E", [2]), ("pitches", "E", [2]),
    ]
    assert out["games"]["E"]["missing"] == []
    assert out["errors"] == []


def test_e_and_c_snos_isolated(wired):
    wired["completed"] = {"E": [1, 2], "C": [1]}
    rr._postseason_detail_step(YEAR, ("E", "C"), DAYS)
    assert _source_calls(wired) == [
        ("gamelog", "E", [1, 2], True), ("details", "E", [1, 2]), ("pitches", "E", [1, 2]),
        ("gamelog", "C", [1], True), ("details", "C", [1]), ("pitches", "C", [1]),
    ]
    assert [c[:3] for c in wired["calls"] if c[0] == "after"] == [
        ("after", "E", [1, 2]), ("after", "C", [1]),
    ]


def test_window_and_missing_deduped_single_send(wired):
    wired["completed"] = {"E": [2, 3]}
    wired["missing"] = {"E": [1, 2]}
    out = rr._postseason_detail_step(YEAR, ("E",), DAYS)
    assert _source_calls(wired) == [
        ("gamelog", "E", [1, 2, 3], True), ("details", "E", [1, 2, 3]),
        ("pitches", "E", [1, 2, 3]),
    ]
    assert out["games"]["E"]["window"] == 2
    assert out["games"]["E"]["completed_games"] == 3


def test_partial_gamelog_ledgered_and_reselected_next_run(wired):
    wired["completed"] = {"E": [1, 2]}
    wired["gamelog"] = lambda kind, snos: _gamelog_result(kind, snos, failed=(2,))
    wired["after"] = {"E": {2: ["batting_gamelog", "pitching_gamelog",
                                "game_livelog", "game_scoreboard"]}}
    out = rr._postseason_detail_step(YEAR, ("E",), DAYS)
    (gap,) = wired["gaps"]
    assert gap["kind_code"] == "E" and gap["failed"] == [2]
    assert "季後明細" in gap["why"]
    assert [e["stage"] for e in out["errors"]] == ["detail_missing"]
    assert out["games"]["E"]["missing"][0]["game_sno"] == 2
    assert ("details", "E", [1, 2]) in wired["calls"]  # 部分失敗不中止同賽別其餘明細
    # 下一次排程：窗已過、DB 仍缺 → 缺明細查詢選出 2，只重抓 2
    wired["calls"].clear()
    wired["completed"], wired["missing"], wired["after"] = {}, {"E": [2]}, {}
    wired["gamelog"] = None
    out = rr._postseason_detail_step(YEAR, ("E",), DAYS)
    assert _source_calls(wired)[0] == ("gamelog", "E", [2], True)
    assert out["errors"] == []


def test_zero_row_sources_are_recorded_as_missing_not_complete(wired):
    # HTML 明細回 0、官方 stats 回 games=0／flags=0 都不拋錯；只有寫入後對帳看得出缺漏
    wired["completed"] = {"E": [1]}
    wired["details_rows"] = 0
    wired["pitches_out"] = {"games": 0, "flags": 0, "pitches": 0}
    wired["after"] = {"E": {1: ["game_detail", "pitching_game_flags"]}}
    out = rr._postseason_detail_step(YEAR, ("E",), DAYS)
    assert wired["gaps"] == []  # gamelog 本身沒失敗，不得冒充 gamelog 落差
    by_stage = {e["stage"]: e for e in out["errors"]}
    assert set(by_stage) == {"detail_missing", "detail_source"}
    err = by_stage["detail_missing"]
    assert err["kind"] == "E"
    assert "game_detail" in err["error"] and "pitching_game_flags" in err["error"]
    assert "game_details=0/1" in by_stage["detail_source"]["error"]
    assert out["games"]["E"]["missing"] == [
        {"game_sno": 1, "tables": ["game_detail", "pitching_game_flags"]},
    ]
    json.dumps(out)  # 進 refresh_log detail 前須可序列化


def test_empty_gamelog_arrays_with_games_counted_still_missing(wired):
    # gamelog 四陣列皆空但 games>0：回傳計數不足以判齊，仍以對帳缺 livelog／scoreboard 記錯
    wired["completed"] = {"C": [1]}
    wired["after"] = {"C": {1: ["game_livelog", "game_scoreboard"]}}
    out = rr._postseason_detail_step(YEAR, ("C",), DAYS)
    assert wired["gaps"] == []
    assert [(e["kind"], e["stage"]) for e in out["errors"]] == [("C", "detail_missing")]


def test_empty_c_does_not_hit_sources(wired):
    wired["completed"] = {"E": [1]}
    out = rr._postseason_detail_step(YEAR, ("E", "C"), DAYS)
    assert [c for c in _source_calls(wired) if c[1] == "C"] == []
    assert not [c for c in wired["calls"] if c[0] == "after" and c[1] == "C"]
    assert out["games"]["C"] == {"completed_games": 0}
    assert out["errors"] == []


def test_fast_mode_only_fills_missing_without_window_or_pitches(wired):
    wired["completed"] = {"E": [4]}
    wired["missing"] = {"E": [3]}
    out = rr._postseason_detail_step(YEAR, ("E",), DAYS, full=False)
    assert ("completed", "E") not in wired["calls"]
    assert _source_calls(wired) == [("gamelog", "E", [3], True), ("details", "E", [3])]
    fast = rr._POSTSEASON_FAST_DETAIL_TABLES
    assert ("missing", "E", fast) in wired["calls"]
    assert [c[3] for c in wired["calls"] if c[0] == "after"] == [fast]
    assert out["games"]["E"]["unchecked_tables"] == ["pitching_game_flags"]


def test_pitcher_fallback_receives_local_pitchers_of_candidate_games(wired, monkeypatch):
    monkeypatch.setattr(rr, "settings", SimpleNamespace(pitch_ingest="pitcher"))
    seen: list = []

    def pitchers_of_games(year, kind_code, snos):
        seen.append((kind_code, list(snos)))
        return {"p2", "p1"}

    monkeypatch.setattr(rr, "_pitchers_of_games", pitchers_of_games)
    wired["completed"] = {"E": [1, 2]}
    out = rr._postseason_detail_step(YEAR, ("E",), DAYS)
    assert seen == [("E", [1, 2])]
    assert wired["day_pitchers"] == [["p1", "p2"]]
    assert out["errors"] == []


def test_game_mode_does_not_query_pitchers(wired):
    wired["completed"] = {"E": [1]}
    out = rr._postseason_detail_step(YEAR, ("E",), DAYS)  # fixture 令 _pitchers_of_games 一呼即炸
    assert out["errors"] == []
    assert wired["day_pitchers"] == [[]]


def test_one_kind_failure_does_not_block_other(wired):
    wired["completed"] = {"E": [1], "C": [1]}

    def flaky(kind, snos):
        if kind == "E":
            raise RuntimeError("boom")
        return _gamelog_result(kind, snos)

    wired["gamelog"] = flaky
    out = rr._postseason_detail_step(YEAR, ("E", "C"), DAYS)
    assert [(e["kind"], e["stage"]) for e in out["errors"]] == [("E", "detail")]
    assert ("gamelog", "C", [1], True) in wired["calls"]


@pytest.mark.parametrize("override", [
    {"details_rows": 0},
    {"pitches_out": {"games": 0, "pitches": 0, "skipped_frozen": 0, "pitcher_flags": 1,
                     "mode": "game", "lagging_games": 0}},
    {"pitches_out": {"games": 1, "pitches": 0, "skipped_frozen": 0, "pitcher_flags": 0,
                     "mode": "game", "lagging_games": 0}},
    {"gamelog": lambda kind, snos: {**_gamelog_result(kind, snos), "livelog": 0}},
])
def test_source_shortfall_is_error_even_when_db_rows_exist(wired, override):
    # DB 對帳無缺（舊列如 getlive 的 weather／舊 flags 已在），但本次來源回 0 → 仍須記錯
    wired["completed"] = {"E": [1]}
    wired.update(override)
    out = rr._postseason_detail_step(YEAR, ("E",), DAYS)
    assert out["games"]["E"]["missing"] == []
    assert [(e["kind"], e["stage"]) for e in out["errors"]] == [("E", "detail_source")]


def test_frozen_games_not_expected_and_zero_trackman_pitches_accepted(wired):
    wired["completed"] = {"E": [1, 2]}
    wired["frozen"] = {2}
    out = rr._postseason_detail_step(YEAR, ("E",), DAYS)
    assert out["games"]["E"]["pitches"]["pitches"] == 0
    assert out["errors"] == []
