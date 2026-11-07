"""#394：截至某場的戰績與打擊率，以及 `/live` 決定「這一場算不算」的四條路徑。

SQL 的截止語意在 SQLite 記憶體庫以 synthetic 列實際求值，只改寫方言：`%s`→`?`、
`= ANY(%s)`→`IN`，並把完賽判準換成 `g.done = 1`（判準本身的求值由
`tests/test_completion.py` 負責）。真實場次對帳需共享庫，不在此，見 #394 的 E2 探針。
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

import pytest

from cpbl.api.routers import games
from cpbl.models import as_of

_ROOT = Path(__file__).resolve().parents[1]

_DDL = """
CREATE TABLE cpbl.games (year INT, kind_code TEXT, game_sno INT, game_date TEXT,
    home_team_code TEXT, away_team_code TEXT, home_score INT, away_score INT, done INT);
CREATE TABLE cpbl.batting_gamelog (year INT, kind_code TEXT, game_sno INT, hitter_acnt TEXT,
    at_bats INT, hits INT);
"""

# 場號與日期刻意逆序：補賽的低場號排在後面的日期，這正是不能只比 game_sno 的原因。
_GAMES = [
    (2026, "A", 10, "2026-04-01", "H", "V", 3, 1, 1),   # H 勝
    (2026, "A", 11, "2026-04-02", "V", "H", 2, 2, 1),   # 和局
    (2026, "A", 30, "2026-04-03", "H", "V", 0, 5, 1),   # 本場（H 敗）
    (2026, "A", 31, "2026-04-03", "H", "V", 7, 0, 1),   # 同日較晚場
    (2026, "A", 5, "2026-04-20", "H", "V", 9, 0, 1),    # 低場號補賽，日期在本場之後
    (2026, "A", 40, "2026-04-02", "H", "V", 1, 0, 0),   # 未完成，不得計入
    (2026, "D", 12, "2026-04-02", "H", "V", 8, 0, 1),   # 其他賽別
    (2025, "A", 12, "2025-04-02", "H", "V", 8, 0, 1),   # 其他年份
]
_LINES = [
    (2026, "A", 10, "b1", 4, 2), (2026, "A", 11, "b1", 3, 0), (2026, "A", 30, "b1", 3, 1),
    (2026, "A", 31, "b1", 5, 5), (2026, "A", 5, "b1", 5, 5), (2026, "A", 40, "b1", 5, 5),
    (2026, "D", 12, "b1", 5, 5), (2025, "A", 12, "b1", 5, 5),
    (2026, "A", 10, "walks", 0, 0), (2026, "A", 10, "other", 4, 4),
]


class _SqliteCursor:
    def __init__(self, db: sqlite3.Connection):
        self._cur = db.cursor()

    def execute(self, sql: str, params=()):
        params = list(params)
        for i, value in enumerate(params):
            if isinstance(value, list):
                sql = sql.replace("= ANY(%s)", f"IN ({','.join('?' * len(value))})", 1)
                params[i:i + 1] = value
                break
        assert as_of._DONE in sql
        self._cur.execute(sql.replace(as_of._DONE, "g.done = 1").replace("%s", "?"), params)
        return self

    def fetchall(self):
        return self._cur.fetchall()


@pytest.fixture
def cur():
    db = sqlite3.connect(":memory:")
    db.execute("ATTACH ':memory:' AS cpbl")
    db.executescript(_DDL)
    db.executemany("INSERT INTO cpbl.games VALUES (?,?,?,?,?,?,?,?,?)", _GAMES)
    db.executemany("INSERT INTO cpbl.batting_gamelog VALUES (?,?,?,?,?,?)", _LINES)
    yield _SqliteCursor(db)
    db.close()


_AT = (2026, "A", "2026-04-03", 30)


def test_records_include_this_game_and_ignore_later_low_sno_makeup(cur) -> None:
    out = as_of.team_records_as_of(cur, *_AT, ["H", "V"])
    assert out == {"H": {"w": 1, "l": 1, "form": "1-1-1"}, "V": {"w": 1, "l": 1, "form": "1-1-1"}}


def test_records_can_exclude_this_game(cur) -> None:
    out = as_of.team_records_as_of(cur, *_AT, ["H"], include_game=False)
    assert out == {"H": {"w": 1, "l": 0, "form": "1-1-0"}}


def test_extra_result_is_appended_as_the_latest_game(cur) -> None:
    extra = {"home_team_code": "H", "away_team_code": "V", "home_score": 0, "away_score": 5}
    out = as_of.team_records_as_of(cur, *_AT, ["H", "V"], include_game=False, extra_result=extra)
    assert out == as_of.team_records_as_of(cur, *_AT, ["H", "V"])


def test_team_without_completed_games_is_left_out(cur) -> None:
    assert as_of.team_records_as_of(cur, 2026, "A", "2026-03-01", 1, ["H", "V"]) == {}


def test_batter_avg_stops_at_this_game(cur) -> None:
    assert as_of.batter_avg_as_of(cur, *_AT, ["b1"]) == {"b1": 0.3}     # (2+0+1)/(4+3+3)


def test_batter_avg_can_exclude_this_game(cur) -> None:
    assert as_of.batter_avg_as_of(cur, *_AT, ["b1"], include_game=False) == {"b1": 0.286}  # 2/7


def test_extra_lines_are_added_on_top_of_the_db(cur) -> None:
    lines = [{"hitter_acnt": "b1", "at_bats": 3, "hits": 1},
             {"hitter_acnt": "new", "at_bats": 2, "hits": 1},
             {"hitter_acnt": "not-asked", "at_bats": 2, "hits": 1}]
    out = as_of.batter_avg_as_of(cur, *_AT, ["b1", "new"], include_game=False, extra_lines=lines)
    assert out == {"b1": 0.3, "new": 0.5}


def test_zero_at_bats_is_left_out(cur) -> None:
    assert as_of.batter_avg_as_of(cur, *_AT, ["walks", "nobody"]) == {}


def test_rate_rounds_half_up_like_the_official_figure() -> None:
    assert as_of._rate3(5, 16) == 0.313               # 0000007282 季末官方 .313；round() 會給 .312
    assert as_of._rate3(1, 3) == 0.333 and as_of._rate3(2, 3) == 0.667 and as_of._rate3(0, 4) == 0.0


def test_no_hitters_runs_no_query() -> None:
    assert as_of.batter_avg_as_of(None, *_AT, []) == {}


@pytest.mark.parametrize(("results", "label"), [
    ("WWLWL", "3-2"),                # 季初不足 10 場
    ("WWLLTLLLLL", "2-1-7"),         # 含和局顯示三段（2026/A/180 樂天）
    ("TWWWWWWWWWW", "10-0"),         # 第 11 場之前的和局已滑出視窗
])
def test_form_counts_the_last_ten_games_including_ties(results: str, label: str) -> None:
    assert as_of.form_label(list(results)) == label


def test_accumulate_keeps_only_requested_teams_and_ties_do_not_count_in_w_l() -> None:
    rows = [("H", "V", 3, 1), ("H", "X", 2, 2), ("V", "X", 0, 4)]
    assert as_of.accumulate_records(rows, ["H"]) == {"H": {"w": 1, "l": 0, "form": "1-1-0"}}


# ---- `/live` 的本場判定（PLAN §4.2）----

_GAME = {"year": 2026, "kind_code": "A", "game_sno": 30, "game_date": "2026-04-03",
         "away_team_code": "V", "home_team_code": "H", "completed": True}
_DB_LINE = [{"hitter_acnt": "b1"}]


def _final(away: int = 5, home: int = 0) -> dict:
    return {"phase": "final",
            "away": {"score": away, "hitters": [{"HitterAcnt": "b1", "HitCnt": 3, "HittingCnt": 1}]},
            "home": {"score": home, "hitters": [{"HitterAcnt": "b2", "HitCnt": 4, "HittingCnt": 0}]}}


def test_without_a_snapshot_the_db_decides() -> None:
    assert games._as_of_options(None, _GAME, _DB_LINE) == ({}, {})


@pytest.mark.parametrize("phase", ["live", "scheduled", "reserved", "postponed", "unknown"])
def test_non_final_snapshot_shows_pregame_values_even_if_db_says_completed(phase: str) -> None:
    excluded = {"include_game": False}
    assert games._as_of_options({"phase": phase}, _GAME, _DB_LINE) == (excluded, excluded)


def test_final_already_in_db_is_not_counted_twice() -> None:
    assert games._as_of_options(_final(), _GAME, _DB_LINE) == ({}, {})


def test_final_not_in_db_counts_the_game_from_the_snapshot() -> None:
    team, bat = games._as_of_options(_final(), {**_GAME, "completed": False}, [])
    assert team == {"include_game": False, "extra_result": {
        "home_team_code": "H", "away_team_code": "V", "home_score": 0, "away_score": 5}}
    assert bat == {"include_game": False, "extra_lines": [
        {"hitter_acnt": "b1", "at_bats": 3, "hits": 1},
        {"hitter_acnt": "b2", "at_bats": 4, "hits": 0}]}


def test_result_synced_before_box_splits_the_two_decisions() -> None:
    team, bat = games._as_of_options(_final(), _GAME, [])
    assert team == {}
    assert bat["include_game"] is False and len(bat["extra_lines"]) == 2


def test_final_nil_nil_not_in_db_fails_closed_to_pregame_record() -> None:
    team, _ = games._as_of_options(_final(0, 0), {**_GAME, "completed": False}, [])
    assert team == {"include_game": False, "extra_result": None}


def test_snapshot_line_without_counts_is_dropped() -> None:
    snap = _final()
    snap["away"]["hitters"] = [{"HitterAcnt": "b1", "HitCnt": None, "HittingCnt": 1}]
    snap["home"]["hitters"] = [{"HitCnt": 3, "HittingCnt": 1}]
    assert games._as_of_options(snap, _GAME, [])[1]["extra_lines"] == []


def test_real_a_final_box_carries_the_counts_the_snapshot_path_reads() -> None:
    """2026-A-234 官方 stats 原始檔：A 賽別 hitters 確實有 `HitCnt`／`HittingCnt`。"""
    raw = json.loads((_ROOT / "tests/fixtures/stats_game_2026-A-234.json").read_text("utf-8"))
    snap = {"phase": "final",
            "away": {"score": raw["Visiting"]["Score"], "hitters": raw["Visiting"]["Hitters"]},
            "home": {"score": raw["Home"]["Score"], "hitters": raw["Home"]["Hitters"]}}
    lines = games._as_of_options(snap, {**_GAME, "completed": False}, [])[1]["extra_lines"]
    assert len(lines) == len(raw["Visiting"]["Hitters"]) + len(raw["Home"]["Hitters"])
    assert sum(line["hits"] for line in lines) == raw["Visiting"]["HittingCnt"] + raw["Home"]["HittingCnt"]


def test_hitter_ids_union_db_box_and_snapshot() -> None:
    snap = {**_final(), "livelog": [{"HitterAcnt": "b3"}, {"HitterAcnt": ""}, {}]}
    ids = games._as_of_hitter_ids([{"hitter_acnt": "live"}, {"hitter_acnt": None}],
                                  [{"hitter_acnt": "boxonly"}], snap)
    assert ids == ["b1", "b2", "b3", "boxonly", "live"]


class _ScriptedCursor:
    """依序回 game_live 的固定查詢；as_of 兩支由 monkeypatch 取代，故不會走到這裡。"""

    def __init__(self, script: list[tuple[list[str], list[tuple]]]):
        self._script = list(script)
        self.description: list = []
        self._rows: list[tuple] = []

    def execute(self, sql, params=None):
        cols, rows = self._script.pop(0) if self._script else ([], [])
        self.description = [(c,) for c in cols]
        self._rows = rows
        return self

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._rows[0] if self._rows else None


def _live(monkeypatch, *, kind: str, snapshot: dict | None, batting: list[tuple]):
    empty: tuple[list[str], list[tuple]] = (["x"], [])
    cur = _ScriptedCursor([
        (["year", "kind_code", "game_sno", "game_date", "away_team_code", "home_team_code",
          "completed"], [(2026, kind, 30, "2026-04-03", "V", "H", False)]),
        empty, empty, empty,                 # scoreboard／livelog／livelog_extra
        (["hitter_acnt"], batting), empty,   # batting／pitching
        empty, (["exists"], [(False,)]),     # tracking／has_raw_tracking
        empty,                               # game_detail
    ])

    @contextmanager
    def factory():
        class _C:
            def cursor(self):
                return cur
        yield _C()

    calls: dict[str, tuple] = {}

    def records(_cur, *args, **kwargs):
        calls["records"] = (args, kwargs)
        return {"H": {"w": 1, "l": 0, "form": "1-0"}}

    def averages(_cur, *args, **kwargs):
        calls["avg"] = (args, kwargs)
        return {"b1": 0.25}

    def legacy(*_):
        calls["team_stats"] = ()
        return {}

    monkeypatch.setattr(games, "conn", factory)
    monkeypatch.setattr(games.pitcher_decisions, "game_decisions", lambda *_: {})
    monkeypatch.setattr(games, "_decision_counts", lambda *_: None)
    monkeypatch.setattr(games.matchup, "team_stats", legacy)
    monkeypatch.setattr(games.as_of, "team_records_as_of", records)
    monkeypatch.setattr(games.as_of, "batter_avg_as_of", averages)
    monkeypatch.setattr(games, "get_public_live_snapshot", lambda *_: snapshot)
    monkeypatch.setattr(games.pitch_type_live, "annotate", lambda snap, _season: snap)
    return games.game_live(30, season=2026, kind_code=kind), calls


def test_live_a_uses_the_as_of_path_and_keeps_the_response_keys(monkeypatch) -> None:
    body, calls = _live(monkeypatch, kind="A", snapshot=_final(), batting=[("boxonly",)])

    assert body["records"] == {"H": {"w": 1, "l": 0, "form": "1-0"}}
    assert body["batter_avg"] == {"b1": 0.25}
    assert "team_stats" not in calls
    assert calls["records"][0] == (2026, "A", "2026-04-03", 30, ["V", "H"])
    assert calls["records"][1]["extra_result"]["away_score"] == 5
    assert calls["avg"][0][-1] == ["b1", "b2", "boxonly"]
    assert calls["avg"][1] == {"include_game": False, "extra_lines": [
        {"hitter_acnt": "b1", "at_bats": 3, "hits": 1},
        {"hitter_acnt": "b2", "at_bats": 4, "hits": 0}]}
    assert set(body) == {"game", "scoreboard", "livelog", "batting", "pitching", "people",
                         "records", "batter_avg", "detail", "decisions", "decision_counts",
                         "has_tracking", "tracking", "spray", "live_snapshot"}


@pytest.mark.parametrize("kind", ["C", "E", "D"])
def test_live_other_kinds_stay_on_the_old_path(monkeypatch, kind: str) -> None:
    _, calls = _live(monkeypatch, kind=kind, snapshot=None, batting=[])
    assert "team_stats" in calls and "records" not in calls and "avg" not in calls
