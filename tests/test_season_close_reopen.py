"""#392 WP1：``cpbl.season_close`` 套用開季切回紀錄（判定端；工具本體見 ``tests/test_season_reopen.py``）。

收官值一律取自 #391 的真實樣本（``tests/test_season_close.py`` 的 2026 C／F 真實列推導），⛔ 不自造：
- 一軍 2026：台灣大賽 G6 決勝、G7＝not_needed；二軍 2026：F G3 先達 3 勝（官網原始回應）。

本檔全部不連 DB（假 cursor／假 connect）；真 PostgreSQL 的讀寫契約在 ``tests/test_season_reopen_db.py``（預設 skip）。
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, date, datetime

from cpbl import season_close as sc
from tests import test_season_close as real391

NOW = datetime(2026, 11, 10, 4, 0, tzinfo=UTC)
REAL_MAJOR_2026 = real391.major(real391.major_games())
REAL_FARM_2026 = sc.tally_farm_series(2026, real391.farm_2026_from_raw())


def test_real_2026_samples_are_closed_as_391_derived():
    """前提自證：下面的切回測試都建立在「2026 兩軍真實推導＝已收官」上。"""
    assert (REAL_MAJOR_2026.closed, REAL_MAJOR_2026.status) == (True, "decided")
    assert REAL_MAJOR_2026.not_needed_keys == frozenset({(2026, "C", 7)})
    assert (REAL_FARM_2026.closed, REAL_FARM_2026.status) == (True, "decided")


# =========================================================================== 假 DB


class _Cur:
    def __init__(self, *, table: bool, rows: list[tuple[str, int]]):
        self.table, self.rows, self.sql = table, rows, []
        self._one = None
        self._all: list = []

    def execute(self, sql, params=None):
        self.sql.append((sql, params))
        if "to_regclass" in sql:
            self._one = (self.table,)
        elif "cpbl.season_reopen" in sql:
            assert self.table, "表不存在時不得查切回紀錄（to_regclass 守衛）"
            self._all = list(self.rows)

    def fetchone(self):
        return self._one

    def fetchall(self):
        return self._all


class _Conn:
    def __init__(self, cur):
        self.cur = cur

    @contextmanager
    def transaction(self):
        yield

    def cursor(self):
        return self.cur


def _closure(monkeypatch, *, rows=(), table=True, latest=None, by_year=None, season=None, env=None, reopen=True):
    """以真實 2026 推導結果跑 ``league_closure``（推導函式換成回傳真實樣本，只驗切回的套用）。"""
    latest = latest or {"A": 2026, "D": 2026}
    by_year = by_year or {}
    cur = _Cur(table=table, rows=list(rows))

    def read_major(_cur, year, *, as_of):
        return by_year.get(("major", year)) or replace(REAL_MAJOR_2026, season=year)

    def read_farm(_cur, year, *, as_of):
        return by_year.get(("farm", year)) or replace(REAL_FARM_2026, season=year)

    monkeypatch.setattr(sc, "read_major", read_major)
    monkeypatch.setattr(sc, "read_farm", read_farm)
    monkeypatch.setattr(sc, "_latest_season", lambda _cur, kind, as_of: latest[kind])

    @contextmanager
    def connect():
        yield _Conn(cur)

    out = sc.league_closure(season, now=NOW, connect=connect, env=env or {}, reopen=reopen)
    return out, cur


REOPENED_2026 = [("major", 2026), ("farm", 2026)]


# =========================================================================== 驗收 2：切回後判為未收官


def test_reopen_records_turn_both_leagues_open_and_keep_status_and_not_needed(monkeypatch):
    out, _ = _closure(monkeypatch, rows=REOPENED_2026)
    for league in ("major", "farm"):
        got = out[league]
        assert (got.closed, got.status, got.override) == (False, "decided", sc.OVERRIDE_REOPENED)
    assert out["major"].champion_team_code == REAL_MAJOR_2026.champion_team_code
    assert out["major"].not_needed_keys == frozenset({(2026, "C", 7)}), "切回後 2026/C/7 仍不當待打"
    assert sc.closed_leagues(out) == frozenset()


def test_reopen_only_one_league_leaves_the_other_closed(monkeypatch):
    out, _ = _closure(monkeypatch, rows=[("major", 2026)])
    assert (out["major"].closed, out["farm"].closed) == (False, True)
    assert sc.closed_leagues(out) == frozenset({"farm"})


def test_reopened_closure_reaches_cli_closed_leagues_as_empty_line(monkeypatch, capsys):
    """週跑兩支以 ``python -m cpbl.season_close closed-leagues`` 判斷；切回後印空行 ⇒ A、D 都照跑。"""
    out, _ = _closure(monkeypatch, rows=REOPENED_2026)
    monkeypatch.setattr(sc, "league_closure", lambda *_a, **_k: out)
    assert sc.main(["closed-leagues"]) == 0
    assert capsys.readouterr().out == "\n"


def test_reopened_closure_makes_daily_chain_crawl_both_leagues(monkeypatch):
    from cpbl.ingest import daily_gate as dg

    out, _ = _closure(monkeypatch, rows=REOPENED_2026)
    closed = sc.closed_leagues(out)
    day = date(2026, 10, 28)
    decision = dg.classify(dg.DayInputs(day, {date(2026, 10, 27): {"C": 1}}, True, "fixture", False, "fixture",
                                        False, closed), lambda: dg.ProbeResult("clean"))
    assert decision.day_type == dg.FULL and decision.closed_leagues == frozenset()
    assert not any("收官" in r for r in decision.reasons)
    assert dg.open_kinds(closed) == dg.DAYTYPE_KINDS and set(dg.DAYTYPE_KINDS) == {"A", "C", "D", "E", "F"}
    assert "DAILY_CLOSED_LEAGUES" not in dg.render_plan(decision)


def test_reopened_closure_keeps_evening_chain_kinds(monkeypatch):
    from cpbl import db
    from cpbl.ingest import postseason_evening as pe

    out, _ = _closure(monkeypatch, rows=REOPENED_2026)
    asked = []

    class _C:
        def execute(self, _sql, params):
            asked.append(params[1])
            return self

        def fetchall(self):
            return [(k,) for k in asked[-1]]

    @contextmanager
    def fake_conn():
        yield _C()

    monkeypatch.setattr(pe, "read_closure", lambda now=None: out)
    monkeypatch.setattr(db, "conn", fake_conn)
    got = pe.local_scheduled_kinds(date(2027, 3, 1), ["A", "C", "E", "F"])
    assert got == {"A", "C", "E", "F"} and asked == [["A", "C", "E", "F"]]


def test_reopened_closure_makes_home_summary_in_season(monkeypatch):
    """首頁 API：``season_close.major.closed=false``、``override=reopened``；G7 照舊不是待更新。"""
    from tests import test_daily_summary as tds

    out, _ = _closure(monkeypatch, rows=REOPENED_2026)
    g7_day = tds._TODAY - tds.timedelta(days=2)
    script = tds._script(latest=tds._TODAY - tds.timedelta(days=3), next_day=None, scoped=7,
                         games=[tds._game(6, tds._TODAY - tds.timedelta(days=3), home=6, away=0, kind="C",
                                          official_final=True)],
                         unresolved=[tds._g7(g7_day)], revisions=[tds._revision(7, 1, "", g7_day, kind="C")])
    script = [step for step in script if step[0] is not tds._REVISION_COLS]
    body, _ = tds._run(monkeypatch, script, closure=out)
    assert body["season_close"]["major"]["closed"] is False
    assert body["season_close"]["major"]["override"] == "reopened"
    assert body["season_close"]["farm"]["closed"] is False
    assert body["freshness"]["unresolved_games"] == []


# =========================================================================== 驗收 3：未切回時 #391 行為不變


def test_without_records_closure_is_pure_derivation(monkeypatch):
    out, cur = _closure(monkeypatch, rows=[])
    assert sc.closed_leagues(out) == frozenset({"major", "farm"})
    assert all(c.override is None for c in out.values())


def test_missing_table_reads_as_no_records_and_never_queries_it(monkeypatch):
    """部署先於 migration：表不存在 ⇒ 無紀錄（不 500、不改 #391 行為）。"""
    out, cur = _closure(monkeypatch, rows=REOPENED_2026, table=False)
    assert sc.closed_leagues(out) == frozenset({"major", "farm"})
    assert not any("cpbl.season_reopen" in sql and "to_regclass" not in sql for sql, _ in cur.sql)


def test_record_of_an_older_season_does_not_reopen(monkeypatch):
    out, _ = _closure(monkeypatch, rows=[("major", 2025), ("farm", 2025)])
    assert sc.closed_leagues(out) == frozenset({"major", "farm"})


def test_2026_record_expires_once_2027_regular_season_has_a_completed_game(monkeypatch):
    """新球季首場完賽 ⇒ 最新球季＝2027 ⇒ 2026 紀錄失效；2027 收官照常觸發（⛔ 不會永久關掉收官）。"""
    latest = {"A": 2027, "D": 2027}
    open27 = {("major", 2027): replace(REAL_MAJOR_2026, season=2027, closed=False, status="undecided"),
              ("farm", 2027): replace(REAL_FARM_2026, season=2027, closed=False, status="undecided")}
    out, _ = _closure(monkeypatch, rows=REOPENED_2026, latest=latest, by_year=open27)
    assert sc.closed_leagues(out) == frozenset() and all(c.override is None for c in out.values())
    closed27 = {("major", 2027): replace(REAL_MAJOR_2026, season=2027),
                ("farm", 2027): replace(REAL_FARM_2026, season=2027)}
    out, _ = _closure(monkeypatch, rows=REOPENED_2026, latest=latest, by_year=closed27)
    assert sc.closed_leagues(out) == frozenset({"major", "farm"})


def test_explicit_older_season_query_stays_historically_closed(monkeypatch):
    """月曆／``?season=2026``：2027 開打後查 2026 仍是已收官；切回期間查 2025 也仍是已收官。"""
    out, _ = _closure(monkeypatch, rows=REOPENED_2026, latest={"A": 2027, "D": 2027}, season=2026)
    assert sc.closed_leagues(out) == frozenset({"major", "farm"})
    out, _ = _closure(monkeypatch, rows=REOPENED_2026, season=2025)
    assert sc.closed_leagues(out) == frozenset({"major", "farm"})
    out, _ = _closure(monkeypatch, rows=REOPENED_2026, season=2026)
    assert sc.closed_leagues(out) == frozenset()


def test_reopen_false_returns_pure_derivation_and_skips_the_table(monkeypatch):
    out, cur = _closure(monkeypatch, rows=REOPENED_2026, reopen=False)
    assert sc.closed_leagues(out) == frozenset({"major", "farm"})
    assert not any("cpbl.season_reopen" in sql for sql, _ in cur.sql)


def test_env_override_still_applies_after_reopen(monkeypatch):
    out, _ = _closure(monkeypatch, rows=[], env={sc.OVERRIDE_ENV: "open"})
    assert all((c.closed, c.override) == (False, "open") for c in out.values())


def test_reopen_never_closes_an_open_league():
    undecided = replace(REAL_MAJOR_2026, closed=False, status="undecided")
    got = sc.apply_reopen(undecided, 2026, frozenset(REOPENED_2026))
    assert got is undecided


def test_reading_side_stays_select_only_and_derivation_untouched():
    """驗收 4：讀取端只有 SELECT；切回紀錄表名只出現在唯讀查詢。"""
    assert sc.REOPENED_SQL.lstrip().upper().startswith("SELECT")
    assert "revoked_at IS NULL" in sc.REOPENED_SQL


