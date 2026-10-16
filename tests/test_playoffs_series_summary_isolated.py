"""#288 S07 WP-G2 系列累計榜讀取層 SQL 語意：只在**自行擁有的隔離 Postgres**（``CPBL_ISOLATED_TEST_DSN``）執行。

比照 ``test_playoffs_overview_isolated.py``：未設 DSN 即 skip；該庫已有 ``cpbl.games`` 即拒跑；結束時 DROP 自建
schema。⛔ 絕不在共用本機庫或正式庫建表寫列。

驗只有真 SQL 才看得出來的事：

1. 累計榜的 PA／livelog／換投四壞／RE 查詢與 S02、姓名在**同一個 REPEATABLE READ READ ONLY 交易**（同 snapshot）。
2. 查詢數固定（各 1 支、``unnest`` 批次），不隨場數成長；姓名仍只查一次（MVP＋榜上合併）。
3. 真實 E1–E4（``tests/fixtures/series_summary_2026E.json``，本機唯讀抽取）跑完整 ``pa_facts.delta_re24``
   的結果＝執行階段對帳 artifact（逐人 PA/BF 對官方 gamelog 0 差）的前 3／前 2。
4. PA 表讀取失敗只降級該欄（SAVEPOINT 隔離）：比分、MVP、姓名照常，交易不 aborted。
"""

from __future__ import annotations

import json
import os
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path

import pytest
from postseason_context_inputs import YEARS
from test_playoffs_overview_isolated import _DDL, _NOW, _T0, MVP, NAMES

from cpbl import postseason_contract as pc
from cpbl.playoffs import overview as ov
from cpbl.playoffs import series_summary as ss

FIXTURE = json.loads((Path(__file__).resolve().parent / "fixtures" / "series_summary_2026E.json").read_text("utf-8"))

_INT = {"inning_seq", "batting_order", "out_cnt", "ball_cnt", "strike_cnt", "pitch_cnt", "visiting_score", "home_score"}


def _summary_ddl() -> str:
    cols = ", ".join(f"{c} {'boolean' if c.startswith('is_') else 'integer' if c in _INT else 'text'}"
                     for c in FIXTURE["livelog_cols"])
    return f"""
CREATE TABLE cpbl.game_recap_builds (build_id uuid PRIMARY KEY, year smallint, kind_code text, game_sno int,
    state text, built_at timestamptz);
CREATE TABLE cpbl.game_plate_appearances (pa_row_id bigint PRIMARY KEY, pa_id uuid, build_id uuid, year smallint,
    kind_code text, game_sno int, pa_index int, start_event_no text, end_event_no text, hitter_acnt text,
    end_hitter_acnt text, start_pitcher_acnt text, end_pitcher_acnt text, pre_state jsonb, post_state jsonb,
    result_action text, outcome_family text, state text);
CREATE TABLE cpbl.game_pa_events (pa_row_id bigint, year smallint, kind_code text, game_sno int, event_no text,
    event_position int);
CREATE TABLE cpbl.run_expectancy (span text, kind_code text, bases text, outs int, re double precision);
CREATE TABLE cpbl.game_livelog (year smallint, kind_code text, game_sno int, {cols});
"""


@pytest.fixture(scope="module")
def dsn():
    value = os.environ.get("CPBL_ISOLATED_TEST_DSN")
    if not value:
        pytest.skip("未設 CPBL_ISOLATED_TEST_DSN（自行擁有的隔離 Postgres）")
    import psycopg
    from psycopg.types.json import Jsonb

    with psycopg.connect(value, autocommit=True) as c:
        if c.execute("SELECT to_regclass('cpbl.games')").fetchone()[0] is not None:
            pytest.fail("隔離庫已有 cpbl.games：拒絕在疑似真實資料庫上建表寫列")
        c.execute(_DDL)
        try:
            c.execute(_summary_ddl())
            # S02 場次列與官方狀態（同 overview isolated 測試）
            for kind, sno, seg, day, away, home, a, h, done in YEARS["2026"]["games"]:
                if kind == "C" and sno > 2:
                    continue
                c.execute("INSERT INTO cpbl.games VALUES (2026,%s,%s,%s,%s,'測試',%s,%s,%s,%s,%s)",
                          (kind, seg, sno, day, MVP.get(sno) if kind == "E" else None, away, home, a, h))
                seen = _T0 + timedelta(days=sno - 4)
                c.execute(
                    "INSERT INTO cpbl.game_schedule_status_revisions (year, kind_code, game_sno, "
                    "raw_present_status, raw_game_result, raw_game_date, raw_payload, payload_hash, "
                    "fetched_at, last_seen_at) VALUES (2026,%s,%s,1,%s,%s,'{\"IsPlayBall\":\"N\"}',%s,%s,%s)",
                    (kind, sno, "0" if done else "", day, f"h{kind}{sno}", seen, seen))
            for st, tc, w, l, t in YEARS["2026"]["official"]:  # noqa: E741
                c.execute("INSERT INTO cpbl.team_standings VALUES (2026,'A',%s,%s,0,%s,%s,%s)", (st, tc, w, l, t))
            for pid, name in NAMES.items():   # players 只有 4 位 MVP：其餘姓名走 livelog 後備
                c.execute("INSERT INTO cpbl.players VALUES (%s, %s)", (pid, name))
            # 累計榜原料：真實 E1–E4
            with c.cursor() as cur:
                cur.executemany("INSERT INTO cpbl.game_recap_builds VALUES (%s,%s,%s,%s,%s,%s)", FIXTURE["builds"])
                cur.executemany("INSERT INTO cpbl.game_plate_appearances VALUES "
                                "(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                                [[*r[:13], Jsonb(r[13]), Jsonb(r[14]), *r[15:]] for r in FIXTURE["pas"]])
                n = 3 + len(FIXTURE["livelog_cols"])
                cur.executemany(f"INSERT INTO cpbl.game_livelog VALUES ({','.join(['%s'] * n)})", FIXTURE["livelog"])
                cur.executemany("INSERT INTO cpbl.run_expectancy VALUES (%s,%s,%s,%s,%s)", FIXTURE["run_expectancy"])
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


_WATCH = ("cpbl.players", "cpbl.game_plate_appearances", "cpbl.game_livelog", "cpbl.game_pa_events",
          "cpbl.run_expectancy")


class _Spy:
    """轉發 cursor；記錄每次累計榜／姓名查詢當下的交易身分。"""

    def __init__(self, cur, seen):
        self._cur, self._seen = cur, seen

    def __getattr__(self, name):
        return getattr(self._cur, name)

    def execute(self, sql, params=None):
        if any(t in sql for t in _WATCH):
            self._cur.execute("SELECT now(), current_setting('transaction_isolation'), "
                              "current_setting('transaction_read_only'), pg_current_snapshot()::text")
            self._seen.setdefault("q", []).append((sql, self._cur.fetchone()))
        return self._cur.execute(sql, params)


def _run(dsn, monkeypatch):
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
    return ov.playoffs_overview(2026, now=_NOW, connect=lambda: _connect(dsn)), seen


def test_same_transaction_fixed_query_count_and_real_e_board(dsn, monkeypatch):
    o, seen = _run(dsn, monkeypatch)
    assert seen["s02"][1:3] == ("repeatable read", "on")
    qs = seen["q"]
    assert all(ident == seen["s02"] for _, ident in qs)          # 同一交易：同 now()、同 snapshot
    count = {s: sum(1 for sql, _ in qs if s == sql) for s in (ss.PA_SQL, ss.LIVELOG_SQL, ss.MID_WALK_SQL)}
    assert count == {ss.PA_SQL: 1, ss.LIVELOG_SQL: 1, ss.MID_WALK_SQL: 1}   # 4 場仍各 1 支
    assert sum(1 for sql, _ in qs if "cpbl.run_expectancy" in sql) == 1
    assert sum(1 for sql, _ in qs if "cpbl.players" in sql) == 1           # 姓名只批次查一次

    e = o["series_summary"]["previous"]
    assert (e["kind_code"], e["status"], e["games_covered"], e["games_total"]) == ("E", "ok", 4, 4)
    # 期望值＝執行階段真實對帳 artifact（RECON-E1-E4.json）的前 3／前 2
    assert [(b["player_id"], b["re24_raw"], b["pa"]) for b in e["batters"]] == [
        ("0000002297", 2.4087, 5), ("0000004636", 1.6517, 17), ("0000003609", 1.1984, 6)]
    assert [(p["player_id"], p["value_raw"], p["bf"]) for p in e["pitchers"]] == [
        ("0000007778", 3.4458, 24), ("0000007597", 3.028, 18)]
    assert e["pitcher_unattributed"] == 0 and e["excluded_games"] == []
    # 姓名：players 有的用 players，沒有的走 livelog 後備
    assert e["pitchers"][0]["name"] == "喬登" and e["batters"][0]["name"] == "詹子賢"
    assert [(m["name"], m["count"]) for m in e["mvp_counts"]] == [("勝騎士", 1), ("喬登", 1), ("獅帝芬", 1), ("鄭浩均", 1)]
    # C1–C2 未完賽 ⇒ 整塊 no_completed_games；context_version 與 S02 原值相同
    assert o["series_summary"]["current"]["status"] == "no_completed_games"
    src = {m["source"]: m for m in o["source_manifest"]}
    assert src["pa_published"]["scope"] == "series:E:4/4" and src["pa_published"]["status"] == "ok"
    assert o["source_manifest"][-1]["source"] == "players"


def test_pa_table_failure_only_degrades_summary(dsn, monkeypatch):
    monkeypatch.setattr(ss, "PA_SQL", ss.PA_SQL.replace("cpbl.game_plate_appearances", "cpbl.pa_missing"))
    o = ov.playoffs_overview(2026, now=_NOW, connect=lambda: _connect(dsn))
    e = o["series_summary"]["previous"]
    assert e["status"] == "unavailable" and e["batters"] == [] and len(e["mvp_counts"]) == 4
    assert {m["source"]: m["status"] for m in o["source_manifest"]}["pa_published"] == "unavailable"
    prev = o["series_section"]["previous"]["games"]
    assert [c["mvp"]["name"] for c in prev] == ["勝騎士", "喬登", "獅帝芬", "鄭浩均"]   # 姓名照常
    assert prev[0]["away_score"] == 1                                                # 比分照常
