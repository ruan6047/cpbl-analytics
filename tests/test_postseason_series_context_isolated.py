"""#283 S02 v2 讀取層 SQL 語意：只在**自行擁有的隔離 Postgres**（``CPBL_ISOLATED_TEST_DSN``）執行。

比照 ``test_postseason_contract_isolated.py``：未設 DSN 即 skip；該庫已有 ``cpbl.games`` 即拒跑；
結束時 DROP 自建 schema。⛔ 絕不在共用本機庫或正式庫建表寫列。

驗只有真 SQL 才看得出來的事：

1. ``postseason_series_context`` 在**單一 REPEATABLE READ READ ONLY 交易**內讀完全部來源。
2. v2 完賽集合與 ``/api/v1/postseason-summary`` 的 ``standings._DONE`` 逐場相同（同源判準）。
3. 無官方 team_standings 的年份走 games 即時算（半季以 game_season_code 切）。
4. 074 先發公告表（真實 migration 建）與 recap builds 缺表時只降級、不讓交易 aborted。

場次列取自 2026 真實 E1–E4、C1–C2（本機 DB 唯讀抽取，見 tests/fixtures/postseason_real_years.json）；
2026 官方戰績取同一 fixture。⛔ 不作年度規則實證（那在 test_postseason_series_context.py）。
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from postseason_context_inputs import YEARS

from cpbl import postseason_contract as pc

_MIG = Path(__file__).resolve().parents[1] / "migrations"

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
CREATE TABLE cpbl.refresh_log (refreshed_at timestamptz, ok boolean, scope text);
CREATE TABLE cpbl.team_standings (year int, kind_code text, season_code int, team_code text,
    rank int, w int, l int, t int);
"""

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
            for _ in range(2):   # 真實 migration 建表，跑兩次證明冪等
                c.execute((_MIG / "074_game_lineup_announcement_revisions.sql").read_text(encoding="utf-8"))
                c.execute((_MIG / "075_official_change_signals.sql").read_text(encoding="utf-8"))
            for kind, sno, seg, day, away, home, a, h, done in YEARS["2026"]["games"]:
                if kind == "C" and sno > 2:
                    continue
                c.execute("INSERT INTO cpbl.games VALUES (2026,%s,%s,%s,%s,'測試',NULL,%s,%s,%s,%s)",
                          (kind, seg, sno, day, away, home, a, h))
                result = "0" if done else ""
                for j, minutes in enumerate((0, 30) if done else (0,)):
                    seen = _T0 + timedelta(days=sno - 4, minutes=minutes)
                    c.execute(
                        "INSERT INTO cpbl.game_schedule_status_revisions (year, kind_code, game_sno, "
                        "raw_present_status, raw_game_result, raw_game_date, raw_payload, payload_hash, "
                        "fetched_at, last_seen_at) VALUES (2026,%s,%s,1,%s,%s,'{\"IsPlayBall\":\"N\"}',%s,%s,%s)",
                        (kind, sno, result if j else "", day, f"h{kind}{sno}{j}", seen, seen))
            for s, tc, w, l, t in YEARS["2026"]["official"]:  # noqa: E741
                c.execute("INSERT INTO cpbl.team_standings VALUES (2026,'A',%s,%s,0,%s,%s,%s)", (s, tc, w, l, t))
            # 2024 無官方戰績：三場例行賽（真實隊碼，只驗 SQL 加總，不作規則實證）
            for sno, seg, away, home, a, h in ((1, "1", "ADD011", "AJL011", 3, 1), (2, "1", "AJL011", "ADD011", 2, 2),
                                               (3, "2", "ACN011", "ADD011", 0, 5)):
                c.execute("INSERT INTO cpbl.games VALUES (2024,'A',%s,%s,%s,'測試',NULL,%s,%s,%s,%s)",
                          (seg, sno, date(2024, 5, sno), away, home, a, h))
            c.execute("INSERT INTO cpbl.game_completion_evidence VALUES (2024,'A',2)")
            c.execute("INSERT INTO cpbl.refresh_log VALUES (%s, true, 'recent-games')", (_T0,))
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


def test_single_repeatable_read_read_only_transaction(dsn, monkeypatch):
    seen = {}
    real = pc.read_series_inputs

    def spy(cur, year, **kw):
        cur.execute("SELECT current_setting('transaction_read_only'), current_setting('transaction_isolation'), "
                    "txid_current_if_assigned()")
        seen["txn"] = cur.fetchone()
        return real(cur, year, **kw)

    monkeypatch.setattr(pc, "read_series_inputs", spy)
    ctx = pc.postseason_series_context(2026, now=_NOW, connect=lambda: _connect(dsn))
    assert seen["txn"] == ("on", "repeatable read", None)
    assert ctx["series"]["E"]["winner"] == "ACN011"
    assert ctx["series"]["C"]["series_status"] == "pending"
    assert {m["source"]: m["status"] for m in ctx["source_manifest"]}["lineup_announcements"] == "ok"
    # recap builds 表不存在：只降級，後續來源（074）照常讀到——交易沒有進入 aborted
    assert "recap_builds_unavailable" in ctx["missing_reason"]


def test_v2_completed_set_matches_postseason_summary_predicate(dsn):
    import psycopg

    from cpbl.api.routers.standings import _DONE

    with psycopg.connect(dsn) as c:
        c.execute("SET TIME ZONE 'Asia/Taipei'")
        inputs = pc.read_series_inputs(c.cursor(), 2026, now=datetime.now(UTC))
        summary = {tuple(r) for r in c.execute(
            f"SELECT year, kind_code, game_sno FROM cpbl.games WHERE year=2026 "
            f"AND kind_code = ANY(%s) AND {_DONE}", (["E", "C"],)).fetchall()}
    assert {g.key for g in inputs.games if g.completed} == summary == {(2026, "E", n) for n in (1, 2, 3, 4)}
    e4 = next(g for g in inputs.games if g.key == (2026, "E", 4))
    assert e4.first_observed_final_at == _T0 + timedelta(minutes=30)   # 最早觀測到 final 的那一列
    assert inputs.standings.source == "official"


def test_computed_standings_without_official_rows(dsn):
    import psycopg

    with psycopg.connect(dsn) as c:
        c.execute("SET TIME ZONE 'Asia/Taipei'")
        inputs = pc.read_series_inputs(c.cursor(), 2024, now=_NOW)
    st = inputs.standings
    assert st.source == "computed"
    first = {r.team_code: (r.w, r.l, r.t) for r in st.first}
    assert first == {"ADD011": (1, 0, 1), "AJL011": (0, 1, 1)}   # 2:2 有完賽證據 ⇒ 和局
    full = {r.team_code: (r.w, r.l, r.t) for r in st.full}
    assert full["ADD011"] == (2, 0, 1) and full["ACN011"] == (0, 1, 0)
