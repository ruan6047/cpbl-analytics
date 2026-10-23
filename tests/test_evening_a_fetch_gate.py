"""#365 S3（驗收 h）：P-A-FETCH-GATE＋晚間 A 完賽判定（需求方裁定 #343 6361673244 第 1 項＝甲）。

樣本：2026-09-07 的 A304／A306（``tests/fixtures/evening_schedule_2026_real.json`` 的 ``a_partial_2026_09_07``）。
19:50:53（台北）www 在賽中回了兩場的部分比分（``GameResult=''``、PresentStatus=1；A304 主 3：客 2）——
這是真實觀測。⚠️ 該晚兩場在同一時刻都還在賽中；「A306 已終局、A304 仍在賽中」的時序是**情境構造**：
A306 用它的真實 final 列、A304 用它的真實賽中列，stats 狀態分別給 ``FINISHED``／``START``。

①–⑤ 不連網、不碰 DB。⑥ 跑在**自行擁有的隔離 Postgres**（``CPBL_ISOLATED_TEST_DSN``，未設即 skip；該庫已有
``cpbl.games`` 即拒跑，沿 tests/test_daily_chain_completion.py 的 ``isolated``）——⛔ 絕不在共用本機或正式庫建表寫列。
CI 沒有 DB，⑥ 在 CI 必定 skip；本機實跑的指令與輸出見 #365 執行交付報告。
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from cpbl.completion import completed_games_sql_with_evidence, daily_chain_completed_games_sql
from cpbl.ingest import postseason_evening as pe

TPE = ZoneInfo("Asia/Taipei")
FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "evening_schedule_2026_real.json")
                     .read_text(encoding="utf-8"))["a_partial_2026_09_07"]
NOW = datetime(2026, 9, 7, 21, 0, tzinfo=TPE)


def stats(sno: int, status: str, starts: str = "2026-09-07T18:35:00", kind: str = "A") -> pe.StatsGame:
    g = FIXTURE["games"][f"2026-{kind}-{sno}"]
    return pe.StatsGame(2026, kind, sno, status, starts, starts[:10], g["away_team_code"], g["home_team_code"],
                        g["venue"])


def local(sno: int, completed: bool, kind: str = "A") -> pe.LocalGame:
    g = FIXTURE["games"][f"2026-{kind}-{sno}"]
    return pe.LocalGame(2026, kind, sno, g["game_date"], g["away_team_code"], g["home_team_code"], g["venue"],
                        completed)


A306_FINAL_A304_LIVE = [stats(306, "FINISHED"), stats(304, "START")]
# 本機：A306 尚未入庫終場（產生 final_not_ingested）；A304 的部分比分在晚間判準下不是完賽（⑤⑥ 證明）。
LOCAL_NEITHER_DONE = {"2026-A-304": local(304, False), "2026-A-306": local(306, False)}


def wake(state, now, games, local_games, *, enabled=False):
    return pe.plan(state, now, probe=lambda: games, load_local=lambda: local_games, starter_enabled=enabled)


# =========================================================== ① 另一場 A 仍在賽中 → 不對 A 發 www

def test_a_www_waits_while_another_a_game_is_in_progress():
    state = pe.empty_state()
    assert wake(state, NOW, A306_FINAL_A304_LIVE, LOCAL_NEITHER_DONE) == ("idle", "a_fetch_gate")
    assert "A" not in state["scrape_kinds"]
    (ev,) = pe.open_events(state).values()
    assert ev["key"] == "2026-A-306" and ev["attempts"] == [], "擋下不耗每事件 3 次額度"
    assert state["www_requests"] == {}, "擋下不寫賽別冷卻帳本"
    assert state["a_fetch_gate"]["reason"] == "a_in_progress_or_pending:2026-A-304:START"
    # 套用點 (3)：同一狀態下 A 場 box 缺 → boxpa 明細不抓、不計 detail_attempts。
    rec = {"key": "2026-A-306", "game_date": "2026-09-07", "state": "open", "detail_attempts": [],
           "sends": [], "sources": {"box": {"reason": "local_box_incomplete:game_livelog"}}}
    state["boxpa"] = {"2026-A-306": rec}
    assert pe.boxpa_plan(state, NOW, {"2026-A-306": rec}) == ("idle", [], [])
    assert rec["detail_attempts"] == []


def test_starter_checkpoints_for_a_wait_on_the_gate():
    """套用點 (2)：#292 先發時點旗標開啟時，A 的時點同樣受擋（記 a_fetch_gate、不計次）。
    情境：2026-09-27 真實開賽時刻 A355 15:05（進行中）／A357 17:05——16:05 是 A357 的 S-60。"""
    # 開賽時刻＝本機 game_schedule_status_revisions 的 PreExeDate 真實值（fixture _provenance.sql_schedule）。
    games = [pe.StatsGame(2026, "A", 355, "START", "2026-09-27T15:05:00", "2026-09-27", "ADD011", "AKP011", "大巨蛋"),
             pe.StatsGame(2026, "A", 357, "SCHEDULED", "2026-09-27T17:05:00", "2026-09-27", "ACN011", "AEO011",
                          "新莊")]
    local_games = {g.key: pe.LocalGame(2026, "A", g.game_sno, "2026-09-27", g.away_code, g.home_code, g.venue,
                                       False) for g in games}
    state = pe.empty_state()
    t0 = datetime(2026, 9, 27, 14, 0, tzinfo=TPE)
    wake(state, t0, games, local_games, enabled=True)
    action, reason = wake(state, datetime(2026, 9, 27, 16, 5, tzinfo=TPE), games, local_games, enabled=True)
    assert action == "idle"
    s60 = [r for r in state["starter_checkpoints"].values() if r["key"] == "2026-A-357" and r["point"] == "S-60"]
    assert len(s60) == 1 and s60[0]["wait_reason"] == "a_fetch_gate" and s60[0]["attempts"] == []
    # 對照（負控）：同一情境換掉閘門（無閘門行為）→ 同一時點照常抓 A，證明擋下的是閘門而不是別的條件。
    import pytest as _pytest

    with _pytest.MonkeyPatch.context() as mp:
        mp.setattr(pe, "a_fetch_blocked", lambda state, now: (False, ""))
        state = pe.empty_state()
        wake(state, t0, games, local_games, enabled=True)
        assert wake(state, datetime(2026, 9, 27, 16, 5, tzinfo=TPE), games, local_games, enabled=True) == (
            "scrape", "starter_checkpoint")
        assert state["scrape_kinds"] == ["A"]


# =========================================================== ② 全部終局後才抓

def test_all_a_final_then_scrape():
    state = pe.empty_state()
    wake(state, NOW, A306_FINAL_A304_LIVE, LOCAL_NEITHER_DONE)
    later = datetime(2026, 9, 7, 21, 30, tzinfo=TPE)
    both_final = [stats(306, "FINISHED"), stats(304, "FINISHED")]
    assert wake(state, later, both_final, LOCAL_NEITHER_DONE) == ("scrape", "event")
    assert state["scrape_kinds"] == ["A"]
    assert all(e["attempts"] == [] for e in pe.open_events(state).values()), "前一步沒有耗用額度"
    assert state["a_fetch_gate"] is None


# =========================================================== ③ stats 不可用 → 只擋 A

def test_stats_unavailable_blocks_a_only(monkeypatch):
    """stats 讀取失敗：A 判不出狀態 → 擋（PLAN-r4 §6.3，交隔日 J1）。E 照現行規則——結果鏈本來就在
    讀不到 stats 時不連 www（與無閘門時逐字相同）；box／PA 明細只擋 A、E 照抓。
    ⚠️ E4（真實日期 10-12）與 A306 放在同一晚是情境構造，只為同時觀察兩個賽別。"""
    games = [stats(306, "FINISHED"), stats(4, "FINISHED", kind="E")]
    local_games = {**LOCAL_NEITHER_DONE, "2026-E-4": local(4, False, kind="E")}
    state = pe.empty_state()
    wake(state, NOW, games, local_games)
    assert set(state["scrape_kinds"]) == {"A", "E"}, "前提：兩個賽別都有可抓的事件，A 沒有在賽中的場"

    def broken():
        raise pe.ProbeUnavailable("stats timeout")

    t = datetime(2026, 9, 7, 21, 30, tzinfo=TPE)
    gated = json.loads(json.dumps(state))
    assert pe.plan(gated, t, probe=broken, load_local=lambda: {}) == ("idle", "probe_unavailable")
    assert pe.a_fetch_blocked(gated, t) == (True, "probe_unavailable")
    ungated = json.loads(json.dumps(state))
    monkeypatch.setattr(pe, "a_fetch_blocked", lambda state, now: (False, ""))
    assert pe.plan(ungated, t, probe=broken, load_local=lambda: {}) == ("idle", "probe_unavailable")
    monkeypatch.undo()
    gated.pop("a_fetch_gate"), ungated.pop("a_fetch_gate", None)
    assert gated == ungated, "E 的結果鏈行為與無閘門時相同"
    box_missing = {"box": {"reason": "local_box_incomplete:game_livelog"}}
    recs = {k: {"key": k, "game_date": d, "state": "open", "detail_attempts": [], "sends": [],
                "sources": box_missing} for k, d in (("2026-A-306", "2026-09-07"), ("2026-E-4", "2026-09-07"))}
    gated["boxpa"] = recs
    assert pe.boxpa_plan(gated, t, recs) == ("detail", ["2026-E-4"], [])


# =========================================================== ④ 放行集合是白名單 {FINISHED, POSTPONED}（規劃 4 §12 第 1 項）

def _night_state(*games: pe.StatsGame) -> dict:
    state = pe.empty_state()
    state["schedule"] = [pe.asdict(g) for g in games]
    return state


@pytest.mark.parametrize("status", ["SUSPENDED", "", "DELAYED"])
def test_unknown_stats_status_is_not_terminal(status):
    """④ 同晚另一場 FINISHED，本場狀態是未知字或缺值 → 擋（a_status_unknown）；plan 不回 scrape、也不因 A 回 sync。"""
    games = [stats(306, "FINISHED"), stats(304, status)]
    assert pe.a_fetch_blocked(_night_state(*games), NOW) == (True, f"a_status_unknown:2026-A-304:{status or '?'}")
    state = pe.empty_state()
    assert wake(state, NOW, games, LOCAL_NEITHER_DONE) == ("idle", "a_fetch_gate")
    assert state["scrape_kinds"] == [] and state["pending_sync"] is False


A1001 = FIXTURE["games"]


def stats_1001(sno: int, status: str) -> pe.StatsGame:
    g = A1001[f"2026-A-{sno}"]
    return pe.StatsGame(2026, "A", sno, status, "2026-10-01T18:35:00", "2026-10-01", g["away_team_code"],
                        g["home_team_code"], g["venue"])


def local_1001(sno: int, completed: bool) -> pe.LocalGame:
    g = A1001[f"2026-A-{sno}"]
    return pe.LocalGame(2026, "A", sno, "2026-10-01", g["away_team_code"], g["home_team_code"], g["venue"], completed)


AT_1001 = datetime(2026, 10, 1, 22, 0, tzinfo=TPE)


def test_reserved_night_holds_all_a_until_next_day():
    """④b 2026-10-01：A277 FINISHED、A326 RESERVED（09-19 真實保留列；本機灌非零比分是構造，⑥ 證明晚間判準判它未完成）。
    A277 未入庫（產生 final_not_ingested）→ 不抓 A、boxpa 不抓 A 明細、plan 回 idle（不是 scrape／sync），
    reason＝a_reserved。保留賽可能帶非零比分：放行就會把它整表送上正式站（#343 審核 F1）。
    ⚠️ 前提：狀態檔沒有待同步資料／訊號（pending_sync、signals_unsynced 皆否）。有待同步訊號時既有的僅訊號同步
    仍會走 RESULTS_ONLY（#365 審核 N1；見 test_reserved_night_still_syncs_pending_signals_documented_residual）。"""
    games = [stats_1001(277, "FINISHED"), stats_1001(326, "RESERVED")]
    local_games = {"2026-A-277": local_1001(277, False), "2026-A-326": local_1001(326, False)}
    state = pe.empty_state()
    assert wake(state, AT_1001, games, local_games) == ("idle", "a_fetch_gate")
    assert state["a_fetch_gate"]["reason"] == "a_reserved:2026-A-326:RESERVED"
    assert state["scrape_kinds"] == [] and state["pending_sync"] is False and state["www_requests"] == {}
    rec = {"key": "2026-A-277", "game_date": "2026-10-01", "state": "open", "detail_attempts": [], "sends": [],
           "sources": {"box": {"reason": "local_box_incomplete:game_livelog"}}}
    assert pe.boxpa_plan(state, AT_1001, {"2026-A-277": rec}) == ("idle", [], [])


def test_scheduled_later_game_blocks():
    """④c 同晚一場 FINISHED、一場 SCHEDULED 且尚未開賽 → 仍擋（規劃 4 拿掉規劃 3 的 starts_at ≤ now 條件）。"""
    later = pe.StatsGame(**{**pe.asdict(stats(304, "SCHEDULED")), "starts_at": "2026-09-07T21:35:00"})
    assert pe.a_fetch_blocked(_night_state(stats(306, "FINISHED"), later), NOW) == (
        True, "a_in_progress_or_pending:2026-A-304:SCHEDULED")


def test_postponed_before_start_releases():
    """④d 一場 FINISHED、一場 POSTPONED → 放行（兩者都在放行集合）。"""
    games = [stats_1001(277, "FINISHED"), stats_1001(326, "POSTPONED")]
    assert pe.a_fetch_blocked(_night_state(*games), AT_1001) == (False, "")
    state = pe.empty_state()
    assert wake(state, AT_1001, games, {"2026-A-277": local_1001(277, False),
                                        "2026-A-326": local_1001(326, False)}) == ("scrape", "event")
    assert state["scrape_kinds"] == ["A"]


def test_same_game_rows_use_latest_start_and_ties_fail_closed():
    """規劃 4 §12 第 2 項：同場多筆 stats 列取最新 PreExeDate 那筆；開賽時刻相同分不出新舊 → 任一筆非放行即擋。"""
    old = pe.asdict(stats(304, "SCHEDULED", "2026-09-02T18:35:00"))
    old["game_date"] = "2026-09-07"            # 舊開賽時刻的列（改期前），刻意留在同晚
    new = pe.asdict(stats(304, "FINISHED"))
    state = pe.empty_state()
    state["schedule"] = [old, new, pe.asdict(stats(306, "FINISHED"))]
    assert pe.a_fetch_blocked(state, NOW) == (False, ""), "取最新那筆（FINISHED）"
    state["schedule"] = [pe.asdict(stats(304, "FINISHED")), pe.asdict(stats(304, "RESERVED"))]
    assert pe.a_fetch_blocked(state, NOW)[0] is True, "同一開賽時刻、狀態不一致 → 擋"


def test_gate_ignores_e_c_and_other_nights():
    """閘門只看該晚的 A：E／C 進行中不擋 A，也不擋 E／C；前一晚未結的 A 列不影響今晚。"""
    state = pe.empty_state()
    state["schedule"] = [pe.asdict(stats(4, "START", kind="E")),
                         {**pe.asdict(stats(304, "START")), "game_date": "2026-09-06"}]
    assert pe.a_fetch_blocked(state, NOW) == (False, "")


# =========================================================== ⑤ 晚間 A 判定用每日鏈判準（SQL 文字）

def _captured_sql(monkeypatch) -> str:
    seen = []

    class Conn:
        def execute(self, sql, params=None):
            seen.append((sql, params))
            return self

        def fetchall(self):
            return []

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    import cpbl.db

    monkeypatch.setattr(cpbl.db, "conn", lambda: Conn())
    pe.load_local_games(2026, NOW)
    ((sql, _),) = seen
    return sql


def test_evening_a_completion_uses_daily_chain_criterion(monkeypatch):
    sql = _captured_sql(monkeypatch)
    daily = daily_chain_completed_games_sql("g", "%(as_of)s")
    evidence = completed_games_sql_with_evidence("g", "%(as_of)s")
    assert f"CASE WHEN g.kind_code = 'A' THEN {daily} ELSE {evidence} END" in sql


# =========================================================== ⑥ 真實 SQL（隔離 Postgres）

_DDL = """
CREATE SCHEMA cpbl;
CREATE TABLE cpbl.games (year smallint, kind_code text, game_sno int, game_date date,
  away_team_code text, home_team_code text, venue text, home_score int, away_score int,
  PRIMARY KEY (year, kind_code, game_sno));
CREATE TABLE cpbl.game_completion_evidence (year smallint, kind_code text, game_sno int);
CREATE TABLE cpbl.game_schedule_status_revisions (id bigint GENERATED ALWAYS AS IDENTITY,
  year smallint, kind_code text, game_season_code text NOT NULL DEFAULT '', game_sno int,
  raw_present_status int, raw_game_result text, raw_game_date date, raw_pre_exe_date date,
  payload_hash text NOT NULL, raw_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  fetched_at timestamptz NOT NULL, last_seen_at timestamptz NOT NULL, seen_count int NOT NULL DEFAULT 1);
"""


@pytest.fixture
def isolated(monkeypatch):
    dsn = os.environ.get("CPBL_ISOLATED_TEST_DSN")
    if not dsn:
        pytest.skip("未設 CPBL_ISOLATED_TEST_DSN（自行擁有的隔離 Postgres）")
    import psycopg

    import cpbl.db

    with psycopg.connect(dsn, autocommit=True) as c:
        if c.execute("SELECT to_regclass('cpbl.games')").fetchone()[0] is not None:
            pytest.fail("隔離庫已有 cpbl.games：拒絕在疑似真實資料庫上建表寫列")
        c.execute(_DDL)
        monkeypatch.setattr(cpbl.db, "conn", lambda: psycopg.connect(dsn))
        try:
            yield c
        finally:
            c.execute("DROP SCHEMA cpbl CASCADE")


def _load(c, key: str, scores: tuple[int, int], revision: str) -> None:
    g = FIXTURE["games"][key]
    r = FIXTURE["revisions"][key][revision]
    c.execute("DELETE FROM cpbl.games WHERE year=%s AND kind_code=%s AND game_sno=%s",
              (g["year"], g["kind_code"], g["game_sno"]))
    c.execute("DELETE FROM cpbl.game_schedule_status_revisions WHERE year=%s AND kind_code=%s AND game_sno=%s",
              (g["year"], g["kind_code"], g["game_sno"]))
    c.execute("INSERT INTO cpbl.games VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
              (g["year"], g["kind_code"], g["game_sno"], g["game_date"], g["away_team_code"],
               g["home_team_code"], g["venue"], scores[0], scores[1]))
    c.execute("INSERT INTO cpbl.game_schedule_status_revisions (year, kind_code, game_season_code, game_sno, "
              "raw_present_status, raw_game_result, raw_game_date, raw_pre_exe_date, payload_hash, "
              "fetched_at, last_seen_at, seen_count) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
              (r["year"], r["kind_code"], r["game_season_code"], r["game_sno"], r["raw_present_status"],
               r["raw_game_result"], r["raw_game_date"], r["raw_pre_exe_date"], r["payload_hash"],
               r["fetched_at"], r["last_seen_at"], r["seen_count"]))


def _reference(c, key: str, as_of: str) -> bool:
    """現行判準（讀端／E／C 晚間判準）在同一列上的結果。``as_of`` 只來自本檔常數。"""
    y, k, s = key.split("-")
    as_of_sql = f"DATE '{datetime.fromisoformat(as_of).date().isoformat()}'"
    return c.execute(
        f"SELECT COALESCE({completed_games_sql_with_evidence('g', as_of_sql)}, FALSE) FROM cpbl.games g "
        "WHERE g.year=%s AND g.kind_code=%s AND g.game_sno=%s", (int(y), k, int(s))).fetchone()[0]


def test_evening_a_completion_on_real_partial_and_reserved_rows(isolated):
    """A304 賽中（19:50 真實修訂列＋games 3：2）→ 晚間判定 false（讀端判準為 true，即 §3.3.1 的錯誤）；
    改灌 09-08 官方 final 列（4：6）→ true。E4 真實列（賽前列＋8：2、final 列）→ 與現行判準相同。"""
    c = isolated
    partial = FIXTURE["revisions"]["2026-A-304"]["in_progress_1950"]
    _load(c, "2026-A-304", (partial["home_score"], partial["visiting_score"]), "in_progress_1950")
    _load(c, "2026-A-306", (0, 2), "in_progress_1950")
    got = pe.load_local_games(2026, NOW)
    assert got["2026-A-304"].completed is False, "賽中部分比分 3：2 不得判完賽"
    assert got["2026-A-306"].completed is False
    assert _reference(c, "2026-A-304", "2026-09-07") is True, "前提：讀端判準對 A 用比分自證（會判成完賽）"

    _load(c, "2026-A-304", (4, 6), "final_0908")
    after = datetime(2026, 9, 8, 0, 30, tzinfo=TPE)
    assert pe.load_local_games(2026, after)["2026-A-304"].completed is True

    # 規劃 4：A326 的 09-19 真實保留列（GameResult='2'）＋構造的非零比分 2：1 → 晚間判定 false；讀端判準為 true。
    _load(c, "2026-A-326", (2, 1), "reserved_0919")
    at_1001 = datetime(2026, 10, 1, 22, 0, tzinfo=TPE)
    assert pe.load_local_games(2026, at_1001)["2026-A-326"].completed is False, "保留賽帶比分不得判完賽"
    assert _reference(c, "2026-A-326", "2026-10-01") is True, "前提：讀端判準對 A 用比分自證"

    for revision, scores, as_of, when in (
            ("pregame_1010", (8, 2), "2026-10-12", datetime(2026, 10, 12, 21, 0, tzinfo=TPE)),
            ("final_1013", (8, 2), "2026-10-13", datetime(2026, 10, 13, 0, 30, tzinfo=TPE))):
        _load(c, "2026-E-4", scores, revision)
        evening = pe.load_local_games(2026, when)["2026-E-4"].completed
        # as_of 以 load_local_games 的台北日期為準（10-13 00:30 → 2026-10-13）
        assert evening is _reference(c, "2026-E-4", as_of), revision


# =========================================================== A 路徑：晚間 scrape 對 A 直呼既有 scrape_games

def test_evening_scrape_uses_scrape_games_for_a_and_the_postseason_step_for_e_c(monkeypatch):
    """A 走既有 ``scrape_games(year, year, "A")``（``_postseason_games_step`` 對 A 會 raise）；E／C 照舊。
    單一賽別失敗只記 ``{"kind", "error"}``、不連坐（與 ``_postseason_games_step`` 同形）。"""
    import sys
    import types

    calls = []
    fake = types.ModuleType("cpbl.ingest.run_refresh_recent")
    fake._postseason_games_step = lambda year, kinds: calls.append(("step", year, kinds)) or {
        "games": {k: 1 for k in kinds}, "errors": []}

    def scrape_games(start, end, kind="A"):
        calls.append(("scrape_games", start, end, kind))
        raise RuntimeError("HiNet 挑戰 428")

    fake.scrape_games = scrape_games
    monkeypatch.setitem(sys.modules, "cpbl.ingest.run_refresh_recent", fake)
    out = pe.evening_games_step(2026, ("A", "C"))
    assert calls == [("step", 2026, ("C",)), ("scrape_games", 2026, 2026, "A")]
    assert out["games"] == {"C": 1} and out["errors"] == [{"kind": "A", "error": "HiNet 挑戰 428"}]
    assert pe.scrape_failures(out["errors"], ("A", "C")) == ({"A"}, {"A"})
    calls.clear()
    pe.evening_games_step(2026, ("E",))
    assert calls == [("step", 2026, ("E",))], "沒有 A 就不碰 scrape_games"


# =========================================================== 審核 F1／F2：走真實 stats_probe → plan 路徑

def _raw(sno: int, status: str, starts: str | None, kind: str = "A") -> dict:
    g = FIXTURE["games"].get(f"2026-{kind}-{sno}") or {"away_team_code": "ADD011", "home_team_code": "AAA011",
                                                       "venue": "洲際"}
    row = {"GameId": f"2026-{kind}-{sno}", "KindCode": kind, "GameSno": sno, "GameStatus": status,
           "Visiting": {"Team": {"Code": g["away_team_code"]}}, "Home": {"Team": {"Code": g["home_team_code"]}},
           "Field": {"Abbe": g["venue"]}}
    if starts is not None:
        row["PreExeDate"] = starts
    return row


_ROWS = object()


def _fetch(rows_by_kind: dict[str, list[dict]] | None = None, body=_ROWS):
    def fetch(path, params):
        if body is not _ROWS:
            return body
        return {"Data": {"Games": (rows_by_kind or {}).get(params["kindCode"], [])}}
    return fetch


def _plan_via_probe(state, at, fetch, local_games):
    return pe.plan(state, at, probe=lambda: pe.stats_probe(2026, [9], kinds=("A",), fetch=fetch),
                   load_local=lambda: local_games)


T1835 = "2026-09-07T18:35:00"


@pytest.mark.parametrize("other", ["RESERVED", "CANCELLED"])
@pytest.mark.parametrize("order", ["other_first", "finished_first"])
def test_same_time_conflict_from_real_probe_blocks_in_either_order(order, other):
    """F1：同場同時刻回「非放行狀態」與 FINISHED（兩種回傳順序）→ 不得只剩一筆而放行。A306 FINISHED 產生事件。
    CANCELLED（未觀測過的假設字，字母序排在 FINISHED 之前）確保閘門讀的是原始列、不是去重後剛好留下的那筆。"""
    pair = [_raw(304, other, T1835), _raw(304, "FINISHED", T1835)]
    if order == "finished_first":
        pair.reverse()
    state = pe.empty_state()
    action = _plan_via_probe(state, NOW, _fetch({"A": [*pair, _raw(306, "FINISHED", T1835)]}), LOCAL_NEITHER_DONE)
    assert action == ("idle", "a_fetch_gate"), state["a_fetch_gate"]
    why = "a_reserved" if other == "RESERVED" else "a_status_unknown"
    assert state["a_fetch_gate"]["reason"] == f"{why}:2026-A-304:{other}"
    assert "A" not in state["scrape_kinds"] and len(state["a_stats_rows"]) == 3


@pytest.mark.parametrize("order", ["start_first", "postponed_first"])
def test_tonight_start_beats_an_older_postponed_row(order):
    """F1：當晚 START 與較早日期的 POSTPONED 歷史列（延賽改期都會留列）→ 依最新 PreExeDate 取 START → 擋。"""
    pair = [_raw(304, "START", T1835), _raw(304, "POSTPONED", "2026-09-02T18:35:00")]
    if order == "postponed_first":
        pair.reverse()
    state = pe.empty_state()
    assert _plan_via_probe(state, NOW, _fetch({"A": [*pair, _raw(306, "FINISHED", T1835)]}),
                           LOCAL_NEITHER_DONE) == ("idle", "a_fetch_gate")
    assert state["a_fetch_gate"]["reason"] == "a_in_progress_or_pending:2026-A-304:START"
    (row,) = [g for g in state["schedule"] if g["game_sno"] == 304]
    assert row["status"] == "START", "去重後的 schedule 也取最新 PreExeDate，不看回傳順序"


@pytest.mark.parametrize("order", ["final_first", "postponed_first"])
def test_negative_control_final_tonight_with_older_postponed_row_releases(order):
    """負控：當晚 FINISHED＋較早 POSTPONED 歷史列 → 放行（證明上兩條不是一律擋）。"""
    pair = [_raw(304, "FINISHED", T1835), _raw(304, "POSTPONED", "2026-09-02T18:35:00")]
    if order == "postponed_first":
        pair.reverse()
    state = pe.empty_state()
    assert _plan_via_probe(state, NOW, _fetch({"A": [*pair, _raw(306, "FINISHED", T1835)]}),
                           LOCAL_NEITHER_DONE) == ("scrape", "event")
    assert state["scrape_kinds"] == ["A"]


@pytest.mark.parametrize("bad", ["not-a-date", "2026-99-99T18:35:00", "2026-09-07T25:61:00", "2026-02-30T18:35:00"])
def test_a_row_with_invalid_pre_exe_date_blocks(bad):
    """review-2 F2-R（Codex 重現情境）：2026-09-07 21:00，A304 RESERVED 的 PreExeDate 無效、A306 FINISHED。
    走真實 stats_probe → plan：無效值非空卻判不出日期，⛔ 不得因 game_date ≠ night 被濾掉而放行 A。"""
    state = pe.empty_state()
    rows = [_raw(304, "RESERVED", bad), _raw(306, "FINISHED", T1835)]
    assert _plan_via_probe(state, NOW, _fetch({"A": rows}), LOCAL_NEITHER_DONE) == ("idle", "a_fetch_gate")
    assert state["a_fetch_gate"]["reason"] == "a_date_unknown:2026-A-304:RESERVED"
    assert "A" not in state["scrape_kinds"]


def test_a_row_without_pre_exe_date_blocks():
    """F2 事實一：A304 RESERVED 缺 PreExeDate（判不出屬於哪一晚）＋A306 FINISHED → 擋（a_date_unknown）。"""
    state = pe.empty_state()
    rows = [_raw(304, "RESERVED", None), _raw(306, "FINISHED", T1835)]
    assert _plan_via_probe(state, NOW, _fetch({"A": rows}), LOCAL_NEITHER_DONE) == ("idle", "a_fetch_gate")
    assert state["a_fetch_gate"]["reason"] == "a_date_unknown:2026-A-304:RESERVED"


@pytest.mark.parametrize("body", [{}, {"Data": {}}, {"Data": None}, {"Data": {"Games": None}},
                                  {"Data": {"Games": {}}}, [], None])
def test_structurally_missing_response_is_unavailable_not_an_empty_month(body):
    """F2 事實二：結構缺失不是空清單 → ProbeUnavailable；合法的 {"Data": {"Games": []}} 才是空月份。"""
    with pytest.raises(pe.ProbeUnavailable):
        pe.stats_probe(2026, [9], kinds=("A",), fetch=_fetch(body=body))
    assert pe.stats_probe(2026, [9], kinds=("A",), fetch=_fetch(body={"Data": {"Games": []}})) == []


def test_empty_object_response_keeps_the_gate_closed_across_wakes():
    """F2 事實二（入口到決策）：先因 A304 START 擋住、留下 A306 未結事件；之後 stats 回 {} → 不得清空賽程、
    下一輪也不得放行。負控：stats 恢復且兩場都 FINISHED 才回 scrape。"""
    state = pe.empty_state()
    live = _fetch({"A": [_raw(304, "START", T1835), _raw(306, "FINISHED", T1835)]})
    assert _plan_via_probe(state, NOW, live, LOCAL_NEITHER_DONE) == ("idle", "a_fetch_gate")
    schedule_before = list(state["schedule"])
    for minutes in (5, 10, 15):
        at = datetime(2026, 9, 7, 21, minutes, tzinfo=TPE)
        action = _plan_via_probe(state, at, _fetch(body={}), LOCAL_NEITHER_DONE)
        assert action == ("idle", "probe_unavailable") and state["schedule"] == schedule_before
        assert pe.a_fetch_blocked(state, at)[0] is True
    final = _fetch({"A": [_raw(304, "FINISHED", T1835), _raw(306, "FINISHED", T1835)]})
    assert _plan_via_probe(state, datetime(2026, 9, 7, 21, 30, tzinfo=TPE), final,
                           LOCAL_NEITHER_DONE) == ("scrape", "event")


def test_reserved_night_still_syncs_pending_signals_documented_residual():
    """審核 N1：④b 的「不觸發 RESULTS_ONLY」只在**沒有待同步資料／訊號**的前提下成立。本機異動訊號表待同步
    （signals_unsynced）時，既有的僅訊號同步仍會走 RESULTS_ONLY（它整表帶 games；上游已接受的殘餘風險，
    ⛔ 本卡不擴張或收窄同步範圍）。A 閘門照樣不抓 A。"""
    games = [stats_1001(277, "FINISHED"), stats_1001(326, "RESERVED")]
    local_games = {"2026-A-277": local_1001(277, False), "2026-A-326": local_1001(326, False)}
    state = pe.empty_state()
    state["signals_unsynced"] = True
    assert wake(state, AT_1001, games, local_games) == ("sync", "signals_only")
    assert state["scrape_kinds"] == [] and state["a_fetch_gate"]["reason"].startswith("a_reserved")


def test_a_pregame_starter_checkpoints_are_always_held_by_the_gate():
    """review-2 Claude N2（Runbook §10 依此改寫）：SCHEDULED 不在放行集合 ⇒ 即使該晚沒有任何 A 在賽中，
    A 的 S−60／S−30 也一律被擋（a_fetch_gate、不計次），過最遲時刻記 missed。樣本：2026-09-27 A357 17:05。"""
    a357 = pe.StatsGame(2026, "A", 357, "SCHEDULED", "2026-09-27T17:05:00", "2026-09-27", "ACN011", "AEO011", "新莊")
    local_games = {a357.key: pe.LocalGame(2026, "A", 357, "2026-09-27", "ACN011", "AEO011", "新莊", False)}
    state = pe.empty_state()
    wake(state, datetime(2026, 9, 27, 14, 0, tzinfo=TPE), [a357], local_games, enabled=True)
    for hh, mm in ((16, 5), (16, 35)):
        assert wake(state, datetime(2026, 9, 27, hh, mm, tzinfo=TPE), [a357], local_games, enabled=True)[0] == "idle"
    recs = {r["point"]: r for r in state["starter_checkpoints"].values() if r["key"] == "2026-A-357"}
    assert {p: (r["wait_reason"], r["attempts"]) for p, r in recs.items()} == {
        "S-60": ("a_fetch_gate", []), "S-30": ("a_fetch_gate", [])}
    wake(state, datetime(2026, 9, 27, 17, 10, tzinfo=TPE), [a357], local_games, enabled=True)
    assert {r["outcome"] for r in state["starter_checkpoints"].values() if r["key"] == "2026-A-357"} == {"missed"}


def test_stored_a_row_with_invalid_game_date_blocks():
    """F2-R 的另一半：閘門用 game_date 比對該晚。經 stats_probe 時 game_date 取自 PreExeDate（starts_at 能解析即有效），
    但狀態檔裡的列也可能來自舊版或手動修補——game_date 不是有效日期時同樣擋，不因比對不到該晚而放行。"""
    state = pe.empty_state()
    bad = {**pe.asdict(stats(304, "RESERVED")), "game_date": "2026-99-99"}
    state["a_stats_rows"] = [bad, pe.asdict(stats(306, "FINISHED"))]
    assert pe.a_fetch_blocked(state, NOW) == (True, "a_date_unknown:2026-A-304:RESERVED")
