"""#285 S04 overview 讀取層 SQL 語意：只在**自行擁有的隔離 Postgres**（``CPBL_ISOLATED_TEST_DSN``）執行。

比照 ``test_postseason_series_context_isolated.py``：未設 DSN 即 skip；該庫已有 ``cpbl.games`` 即拒跑；
結束時 DROP 自建 schema。⛔ 絕不在共用本機庫或正式庫建表寫列。

驗只有真 SQL 才看得出來的事（A12 (a)）：

1. ``playoffs_overview`` 在**單一 REPEATABLE READ READ ONLY 交易**內讀完 S02 inputs 與 MVP 姓名。
2. 姓名只查一次（``ANY`` 批次），且與 S02 inputs 同一交易（同一 ``now()``、同一 snapshot）。
3. players 讀取失敗只降級（SAVEPOINT 隔離），不讓交易 aborted、不讓整個 overview 失敗。

場次列取自 2026 真實 E1–E4、C1–C2（同 S02 isolated 測試的 fixture）；MVP id／姓名為本機 DB 唯讀查得的真實值。
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

import pytest
from postseason_context_inputs import YEARS

from cpbl import postseason_contract as pc
from cpbl.playoffs import overview as ov

_DDL = """
CREATE SCHEMA cpbl;
CREATE TABLE cpbl.games (
    year int, kind_code text, game_season_code text, game_sno int, game_date date, venue text, mvp_id text,
    away_team_code text, home_team_code text, away_score int, home_score int);
CREATE TABLE cpbl.game_completion_evidence (year smallint, kind_code text, game_sno int);
CREATE TABLE cpbl.game_schedule_status_revisions (
    id bigint GENERATED ALWAYS AS IDENTITY, year smallint, kind_code text, game_sno int,
    raw_present_status int, raw_game_result text, raw_game_date date, raw_payload jsonb,
    payload_hash text NOT NULL, fetched_at timestamptz NOT NULL, last_seen_at timestamptz NOT NULL);
CREATE TABLE cpbl.team_standings (year int, kind_code text, season_code int, team_code text,
    rank int, w int, l int, t int);
CREATE TABLE cpbl.players (id text PRIMARY KEY, name text);
"""

MVP = {1: "0000005604", 2: "0000007778", 3: "0000007597", 4: "0000002345"}
NAMES = {"0000005604": "勝騎士", "0000007778": "喬登", "0000007597": "獅帝芬", "0000002345": "鄭浩均"}
_T0 = datetime(2026, 10, 12, 14, 0, tzinfo=UTC)
_NOW = datetime(2026, 10, 14, 17, 0, tzinfo=UTC)   # 台北 10/15 01:00


@pytest.fixture(scope="module")
def dsn():
    value = os.environ.get("CPBL_ISOLATED_TEST_DSN")
    if not value:
        pytest.skip("未設 CPBL_ISOLATED_TEST_DSN（自行擁有的隔離 Postgres）")
    import psycopg

    with psycopg.connect(value, autocommit=True) as c:
        if c.execute("SELECT to_regclass('cpbl.games')").fetchone()[0] is not None:
            pytest.fail("隔離庫已有 cpbl.games：拒絕在疑似真實資料庫上建表寫列")
        c.execute(_DDL)
        try:
            for kind, sno, seg, day, away, home, a, h, done in YEARS["2026"]["games"]:
                if kind == "C" and sno > 2:
                    continue
                c.execute("INSERT INTO cpbl.games VALUES (2026,%s,%s,%s,%s,'測試',%s,%s,%s,%s,%s)",
                          (kind, seg, sno, day, MVP.get(sno) if kind == "E" else None, away, home, a, h))
                # 官方狀態列（同 S02 isolated 測試）：完賽場最後一筆為 final，2026 E／C 才算完賽
                seen = _T0 + timedelta(days=sno - 4)
                c.execute(
                    "INSERT INTO cpbl.game_schedule_status_revisions (year, kind_code, game_sno, "
                    "raw_present_status, raw_game_result, raw_game_date, raw_payload, payload_hash, "
                    "fetched_at, last_seen_at) VALUES (2026,%s,%s,1,%s,%s,'{\"IsPlayBall\":\"N\"}',%s,%s,%s)",
                    (kind, sno, "0" if done else "", day, f"h{kind}{sno}", seen, seen))
            for st, tc, w, l, t in YEARS["2026"]["official"]:  # noqa: E741 — 讓勝推導所需的官方戰績
                c.execute("INSERT INTO cpbl.team_standings VALUES (2026,'A',%s,%s,0,%s,%s,%s)", (st, tc, w, l, t))
            for pid, name in NAMES.items():
                c.execute("INSERT INTO cpbl.players VALUES (%s, %s)", (pid, name))
            yield value
        finally:
            c.execute("DROP SCHEMA cpbl CASCADE")


@contextmanager
def _connect(dsn):
    import psycopg

    with psycopg.connect(dsn) as c:
        c.execute("SET TIME ZONE 'Asia/Taipei'")
        c.commit()
        yield c


class _Spy:
    """轉發 cursor；記錄每次 players 查詢當下的交易身分。"""

    def __init__(self, cur, seen):
        self._cur, self._seen = cur, seen

    def __getattr__(self, name):
        return getattr(self._cur, name)

    def execute(self, sql, params=None):
        if "cpbl.players" in sql:
            self._cur.execute("SELECT now(), current_setting('transaction_isolation'), "
                              "current_setting('transaction_read_only'), pg_current_snapshot()::text")
            self._seen.setdefault("players", []).append(self._cur.fetchone())
        return self._cur.execute(sql, params)


def test_single_repeatable_read_read_only_transaction_with_one_name_batch(dsn, monkeypatch):
    seen: dict = {}
    real_inputs = pc.read_series_inputs
    real_read = ov.read_overview_inputs

    def spy_inputs(cur, year, **kw):
        cur.execute("SELECT now(), current_setting('transaction_isolation'), "
                    "current_setting('transaction_read_only'), pg_current_snapshot()::text")
        seen["s02"] = cur.fetchone()
        return real_inputs(cur, year, **kw)

    monkeypatch.setattr(pc, "read_series_inputs", spy_inputs)
    monkeypatch.setattr(ov, "read_overview_inputs", lambda cur, year, **kw: real_read(_Spy(cur, seen), year, **kw))
    o = ov.playoffs_overview(2026, now=_NOW, connect=lambda: _connect(dsn))

    assert seen["s02"][1:3] == ("repeatable read", "on")
    assert len(seen["players"]) == 1                       # 姓名只批次查一次
    assert seen["players"][0] == seen["s02"]                # 同一交易：同 now()、同 snapshot
    prev = o["series_section"]["previous"]["games"]
    assert [c["mvp"]["name"] for c in prev] == ["勝騎士", "喬登", "獅帝芬", "鄭浩均"]
    assert o["series_section"]["next_game"]["official_game_sno"] == 1
    assert {m["source"]: m["status"] for m in o["source_manifest"]}["players"] == "ok"


def test_players_failure_only_degrades_names(dsn, monkeypatch):
    monkeypatch.setattr(ov, "PLAYERS_SQL", "SELECT id, name FROM cpbl.players_missing WHERE id = ANY(%(ids)s)")
    o = ov.playoffs_overview(2026, now=_NOW, connect=lambda: _connect(dsn))
    assert "player_names_unavailable" in o["series_section"]["missing_reason"]
    assert all(c["mvp_missing_reason"] == "player_name_unavailable" for c in o["series_section"]["previous"]["games"])
    assert o["series_section"]["previous"]["games"][0]["away_score"] == 1   # 其餘照常
