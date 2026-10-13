"""#268 契約 SQL 語意：只在**自行擁有的隔離 Postgres**（``CPBL_ISOLATED_TEST_DSN``）執行。

比照 ``test_daily_chain_completion.py`` 的隔離慣例：未設 DSN 即 skip（CI 與一般本機）；
該庫已有 ``cpbl.games`` 即拒跑——⛔ 絕不在共用本機庫或正式庫建表寫列。結束時 DROP 自建 schema。

驗證兩件只有真 SQL 才看得出來的事：

1. 契約 ``completed_keys`` 與 ``/api/v1/postseason-summary`` 的完賽判準（``standings._DONE``）
   在同一份資料上**逐場相同**（同源判準，不是兩份手寫）。
2. 契約的官方狀態選列（``OFFICIAL_SCHEDULE_ORDER_BY``）與 ``official_final_sql`` 一致。

場次為合成形狀（E 賽中部分比分、E 官方 final、E 0:0 有證據、C 公告後入庫未開打），不是正式資料。
"""

from __future__ import annotations

import os
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from cpbl import postseason_contract as contract

# #268 D1：訊號表用**真實 migration 檔**建（跑兩次證明冪等），不是手寫 DDL。
_SIGNALS_MIGRATION = (Path(__file__).resolve().parents[1] / "migrations"
                      / "075_official_change_signals.sql")

_DDL = """
CREATE SCHEMA cpbl;
CREATE TABLE cpbl.games (
    year smallint, kind_code text, game_sno int, game_date date, venue text,
    away_team_code text, home_team_code text, away_score int, home_score int);
CREATE TABLE cpbl.game_completion_evidence (year smallint, kind_code text, game_sno int);
CREATE TABLE cpbl.game_schedule_status_revisions (
    id bigint GENERATED ALWAYS AS IDENTITY, year smallint, kind_code text, game_sno int,
    raw_present_status int, raw_game_result text, raw_game_date date,
    payload_hash text NOT NULL, fetched_at timestamptz NOT NULL, last_seen_at timestamptz NOT NULL);
CREATE TABLE cpbl.refresh_log (refreshed_at timestamptz, ok boolean, scope text);
"""

_T0 = datetime(2026, 10, 12, 14, 0, tzinfo=UTC)
_D = date
# (kind, sno, date, away, home, away_score, home_score, [(present, result, seen_min)], evidence)
_GAMES = [
    ("E", 1, _D(2026, 10, 9), "ADD011", "ACN011", 0, 3, [(1, "", 0), (1, "0", 30)], False),
    ("E", 2, _D(2026, 10, 10), "ACN011", "ADD011", 0, 0, [], True),
    ("E", 3, _D(2026, 10, 11), "ADD011", "ACN011", 1, 5, [(1, "0", 0)], False),
    # 賽中部分比分、官方仍非 final：不得算完成。
    ("E", 4, _D(2026, 10, 12), "ADD011", "ACN011", 2, 6, [(1, "", 0)], False),
    ("C", 1, _D(2026, 10, 17), "ACN011", "AAA011", 0, 0, [(1, "", 0)], False),
]


@pytest.fixture(scope="module")
def isolated():
    dsn = os.environ.get("CPBL_ISOLATED_TEST_DSN")
    if not dsn:
        pytest.skip("未設 CPBL_ISOLATED_TEST_DSN（自行擁有的隔離 Postgres）")
    import psycopg

    with psycopg.connect(dsn, autocommit=True) as c:
        if c.execute("SELECT to_regclass('cpbl.games')").fetchone()[0] is not None:
            pytest.fail("隔離庫已有 cpbl.games：拒絕在疑似真實資料庫上建表寫列")
        c.execute(_DDL)
        try:
            for _ in range(2):
                c.execute(_SIGNALS_MIGRATION.read_text(encoding="utf-8"))
            for i, (k, s, d, away, home, a, h, sched, ev) in enumerate(_GAMES):
                c.execute("INSERT INTO cpbl.games VALUES (2026,%s,%s,%s,'測試場',%s,%s,%s,%s)",
                          (k, s, d, away, home, a, h))
                if ev:
                    c.execute("INSERT INTO cpbl.game_completion_evidence VALUES (2026,%s,%s)", (k, s))
                for j, (present, result, minutes) in enumerate(sched):
                    seen = _T0 + timedelta(minutes=minutes)
                    c.execute(
                        "INSERT INTO cpbl.game_schedule_status_revisions (year, kind_code, game_sno, "
                        "raw_present_status, raw_game_result, raw_game_date, payload_hash, "
                        "fetched_at, last_seen_at) VALUES (2026,%s,%s,%s,%s,%s,%s,%s,%s)",
                        (k, s, present, result, d, f"h{i}-{j}", seen, seen))
            c.execute("INSERT INTO cpbl.refresh_log VALUES (%s, true, 'recent-games')", (_T0,))
            yield c
        finally:
            c.execute("DROP SCHEMA cpbl CASCADE")


def test_completed_keys_match_postseason_summary_predicate(isolated) -> None:
    from cpbl.api.routers.standings import _DONE

    now = datetime.now(UTC)
    state = contract.series_state_from_cursor(isolated.cursor(), 2026, now=now)
    summary = {tuple(r) for r in isolated.execute(
        f"SELECT year, kind_code, game_sno FROM cpbl.games WHERE year=2026 "
        f"AND kind_code = ANY(%s) AND {_DONE}", (["E", "C"],)).fetchall()}

    assert {tuple(k) for k in state["completed_keys"]} == summary
    assert {(k[1], k[2]) for k in state["completed_keys"]} == {("E", 1), ("E", 2), ("E", 3)}
    e4 = next(g for g in state["games"] if (g["kind_code"], g["game_sno"]) == ("E", 4))
    assert e4["completed"] is False and e4["home_score"] is None


def test_official_status_selection_agrees_with_official_final_sql(isolated) -> None:
    from cpbl.completion import official_final_sql

    state = contract.series_state_from_cursor(isolated.cursor(), 2026, now=datetime.now(UTC))
    sql_final = {(r[0], r[1]) for r in isolated.execute(
        f"SELECT g.kind_code, g.game_sno FROM cpbl.games g WHERE {official_final_sql('g')}").fetchall()}
    for g in state["games"]:
        assert ((g["kind_code"], g["game_sno"]) in sql_final) is (g["official_status"] == "final"), g


def test_coverage_crosses_midnight_without_cutoff(isolated) -> None:
    """台北 10/13 00:40 與 02:10：E4 仍未完成 → pending_update；無任何鐘點截止。"""
    for now in (datetime(2026, 10, 12, 16, 40, tzinfo=UTC), datetime(2026, 10, 12, 18, 10, tzinfo=UTC)):
        state = contract.series_state_from_cursor(isolated.cursor(), 2026, now=now)
        assert state["as_of"]["taipei_date"] == "2026-10-13"
        assert state["as_of"]["coverage"] == "pending_update"
        assert [(g["kind_code"], g["game_sno"]) for g in state["as_of"]["pending_games"]] == [("E", 4)]
        assert state["as_of"]["last_refresh_ok"] is True


def test_change_signals_write_resolve_reopen_and_contract_read(isolated) -> None:
    """D1 寫讀一輪：upsert 冪等（保留首次偵測）、不在集合者解決、解決後再偵測＝重新開啟；
    契約把未解決訊號併入 coverage，⛔ 不因此新增 games 列。"""
    from cpbl.change_signals import write_signals

    count_open = "SELECT count(*) FROM cpbl.official_change_signals WHERE resolved_at IS NULL"
    t1 = datetime(2026, 10, 13, 12, 0, tzinfo=UTC)
    rows = [{"kind_code": "C", "game_sno": 2, "field": "game", "official_value": "2026-10-18T17:05:00"},
            {"kind_code": "C", "game_sno": 1, "field": "venue", "official_value": "洲際"}]
    cur = isolated.cursor()
    try:
        # 回傳值＝實際變動列數（B1：晚間鏈據此決定要不要「僅訊號變動」同步）；重寫同一集合必為 0。
        assert write_signals(cur, 2026, rows, t1) == 2
        assert write_signals(cur, 2026, rows, t1 + timedelta(minutes=5)) == 0
        assert isolated.execute(
            "SELECT kind_code, game_sno, field, detected_at, resolved_at "
            "FROM cpbl.official_change_signals ORDER BY 1, 2, 3").fetchall() == [
            ("C", 1, "venue", t1, None), ("C", 2, "game", t1, None)]

        state = contract.series_state_from_cursor(
            isolated.cursor(), 2026, now=datetime(2026, 10, 13, 12, 10, tzinfo=UTC))
        pending = {(g["kind_code"], g["game_sno"]): (g["game_date"], g["reason"])
                   for g in state["as_of"]["pending_games"]}
        assert pending[("C", 2)] == ("2026-10-18", "official_change_not_ingested")
        assert pending[("C", 1)] == ("2026-10-17", "official_change_not_ingested"), "無新日期 → 本站日期"
        assert pending[("E", 4)][1] == "past_game_without_result"
        assert ("C", 2) not in {(g["kind_code"], g["game_sno"]) for g in state["games"]}

        t2 = t1 + timedelta(hours=1)
        assert write_signals(cur, 2026, rows[:1], t2) == 1, "只有解決那一列算變動"
        assert isolated.execute(
            "SELECT resolved_at FROM cpbl.official_change_signals WHERE game_sno = 1").fetchone() == (t2,)
        t3 = t2 + timedelta(hours=1)
        assert write_signals(cur, 2026, rows, t3) == 1, "重新開啟那一列"
        assert isolated.execute(
            "SELECT detected_at, resolved_at FROM cpbl.official_change_signals "
            "WHERE game_sno = 1").fetchone() == (t3, None)
        assert write_signals(cur, 2026, [], t3 + timedelta(minutes=1)) == 2
        assert isolated.execute(count_open).fetchone() == (0,)
    finally:
        isolated.execute("DELETE FROM cpbl.official_change_signals")
