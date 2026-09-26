"""#213：每日鏈只憑官方 final／完賽證據選 2026+ 完成場（0:0 完賽 2026/D/234 應入、未完賽不得入）。

SQL 語意測試跑在**自行擁有的隔離 Postgres**：只在設了 ``CPBL_ISOLATED_TEST_DSN`` 時執行
（CI 與未設者 skip），且該庫已有 ``cpbl.games`` 即拒跑——⛔ 絕不在共用本機或正式庫建表寫列。
場次以 #203／#213 研究的官方事實為樣本形狀（D/234＝五局 0:0 官方 final、A/326＝0:0 保留賽）。
"""

from __future__ import annotations

import os
import re
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from cpbl.api.helpers import official_status
from cpbl.completion import (
    completed_games_sql_with_evidence,
    daily_chain_completed_games_sql,
    is_completed_game,
)

AS_OF = date(2026, 9, 26)
AS_OF_SQL = f"DATE '{AS_OF.isoformat()}'"
_T0 = datetime(2026, 9, 26, 10, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("home", "away", "official_final", "has_evidence", "expected", "why"),
    [
        (0, 0, True, False, True, "D/234：0:0 且官方 final → 完成場"),
        (0, 0, False, False, False, "0:0 無 final、無證據 → 仍排除"),
        (None, None, True, False, False, "無比分即使 final 也不走 0:0 分支（與 SQL 同為 NULL）"),
        (3, 2, False, False, True, "帶比分場判定不變"),
    ],
)
def test_is_completed_game_official_final_branch(
    home, away, official_final, has_evidence, expected, why,
) -> None:
    got = is_completed_game(home, away, date(2026, 9, 5), AS_OF, has_evidence,
                            official_final=official_final)
    assert got is expected, why


def test_official_final_rule_copy_matches_api_rule() -> None:
    """completion 內抄的官方選列規則與 raw 組合，必須與 api 端唯一來源逐字一致。"""
    from cpbl import completion
    from cpbl.api import helpers

    assert completion._OFFICIAL_SCHEDULE_ORDER_BY == helpers.OFFICIAL_SCHEDULE_ORDER_BY
    assert helpers._OFFICIAL_STATUS_BY_RAW[(1, "0")] == "final"
    assert [k for k, v in helpers._OFFICIAL_STATUS_BY_RAW.items() if v == "final"] == [(1, "0")]
    sql = completion.official_final_sql("g")
    assert "raw_present_status = 1" in sql and "raw_game_result = '0'" in sql


def test_daily_chain_uses_only_the_daily_helper() -> None:
    """每日鏈的選場點全走 ``daily_chain_completed_games_sql``，不再殘留舊判準呼叫。"""
    src = Path(__file__).resolve().parents[1] / "src/cpbl/ingest/run_refresh_recent.py"
    code = src.read_text(encoding="utf-8")
    assert re.findall(r"(?<!daily_chain_)completed_games_sql\(", code) == []
    assert code.count("daily_chain_completed_games_sql(") == 7


# ────────────────────────────────── 隔離 Postgres：SQL 語意

_DDL = """
CREATE SCHEMA cpbl;
CREATE TABLE cpbl.games (
    year smallint, kind_code text, game_sno int, game_date date,
    home_score int, away_score int);
CREATE TABLE cpbl.game_completion_evidence (year smallint, kind_code text, game_sno int);
CREATE TABLE cpbl.game_schedule_status_revisions (
    id bigint GENERATED ALWAYS AS IDENTITY, year smallint, kind_code text, game_sno int,
    raw_present_status int, raw_game_result text, raw_game_date date, raw_pre_exe_date date,
    payload_hash text NOT NULL, fetched_at timestamptz NOT NULL, last_seen_at timestamptz NOT NULL);
"""

# (year, kind, sno, game_date, home, away, [(present, result, raw_date, seen_offset_min)], evidence)
_D = date
_GAMES = [
    (2026, "D", 234, _D(2026, 9, 5), 0, 0, [(1, "0", _D(2026, 9, 5), 0)], False),
    (2026, "A", 326, _D(2026, 9, 20), 0, 0, [(1, "2", _D(2026, 9, 20), 0)], False),
    (2026, "D", 901, _D(2026, 9, 21), 4, 3, [(1, "2", _D(2026, 9, 21), 0)], False),
    (2026, "A", 902, AS_OF, 2, 1, [(1, "", AS_OF, 0)], False),
    (2026, "A", 903, AS_OF, 0, 0, [(1, "", AS_OF, 0)], False),
    (2026, "A", 904, _D(2026, 9, 25), 1, 0, [(1, "", _D(2026, 9, 25), 0)], False),
    (2026, "A", 905, _D(2026, 9, 24), 5, 3, [(1, "0", _D(2026, 9, 24), 0)], False),
    (2026, "D", 906, _D(2026, 9, 23), 6, 2,
     [(0, "1", _D(2026, 9, 1), 5), (1, "0", _D(2026, 9, 23), 0)], False),
    (2026, "D", 907, _D(2026, 9, 22), 0, 0,
     [(1, "0", _D(2026, 9, 10), 5), (1, "", _D(2026, 9, 22), 0)], False),
    (2026, "D", 908, _D(2026, 9, 22), 3, 1,
     [(1, "2", _D(2026, 9, 22), 0), (1, "0", _D(2026, 9, 22), 30)], False),
    # 現行列（present=1）優先於日期較新的舊列：選錯列就會把 final 讀成非 final
    (2026, "A", 912, _D(2026, 9, 20), 2, 1,
     [(1, "0", _D(2026, 9, 20), 0), (0, "", _D(2026, 9, 25), 5)], False),
    (2026, "A", 909, _D(2026, 9, 1), 0, 0, [], False),
    (2026, "A", 910, _D(2026, 9, 2), 0, 0, [], True),
    (2026, "A", 911, _D(2026, 9, 30), 3, 3, [(1, "0", _D(2026, 9, 30), 0)], False),
    (2025, "A", 233, _D(2025, 9, 1), 0, 0, [], True),
    (2025, "A", 100, _D(2025, 6, 1), 4, 1, [], False),
]

# 每日鏈（2026+ 只認 final／證據；2025 走舊判準）
_EXPECTED_DAILY = {
    (2026, "D", 234), (2026, "A", 905), (2026, "D", 906), (2026, "D", 908),
    (2026, "A", 910), (2026, "A", 912), (2025, "A", 100),
}
# API／同步閘門：舊的 score>0 或證據，再多收 0:0 且官方 final（只多 D/234）
_EXPECTED_WITH_EVIDENCE = {
    (2026, "D", 234), (2026, "D", 901), (2026, "A", 902),
    (2026, "A", 904), (2026, "A", 905), (2026, "D", 906), (2026, "D", 908), (2026, "A", 910),
    (2026, "A", 912), (2025, "A", 233), (2025, "A", 100),
}


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
        for i, (y, k, s, d, h, a, sched, ev) in enumerate(_GAMES):
            c.execute("INSERT INTO cpbl.games VALUES (%s,%s,%s,%s,%s,%s)", (y, k, s, d, h, a))
            if ev:
                c.execute("INSERT INTO cpbl.game_completion_evidence VALUES (%s,%s,%s)", (y, k, s))
            for j, (present, result, raw_date, minutes) in enumerate(sched):
                seen = _T0 + timedelta(minutes=minutes)
                c.execute(
                    "INSERT INTO cpbl.game_schedule_status_revisions (year, kind_code, game_sno, "
                    "raw_present_status, raw_game_result, raw_game_date, payload_hash, "
                    "fetched_at, last_seen_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (y, k, s, present, result, raw_date, f"h{i}-{j}", seen, seen))
        yield c
        c.execute("DROP SCHEMA cpbl CASCADE")


def _selected(c, cond: str) -> set[tuple]:
    return {tuple(r) for r in c.execute(
        f"SELECT g.year, g.kind_code, g.game_sno FROM cpbl.games g WHERE {cond}").fetchall()}


def test_daily_chain_admits_d234_and_rejects_unfinished(isolated) -> None:
    got = _selected(isolated, daily_chain_completed_games_sql("g", AS_OF_SQL))
    assert got == _EXPECTED_DAILY
    assert (2026, "A", 326) not in got, "0:0 保留賽不得入帳"
    assert (2026, "A", 902) not in got, "當日已得分賽中場不得入帳"
    assert (2026, "D", 901) not in got, "帶比分保留賽不得入帳"
    assert (2026, "A", 904) not in got, "官方未定案的昨日場不得入帳"


def test_daily_chain_unaliased_form_matches(isolated) -> None:
    rows = isolated.execute(
        "SELECT year, kind_code, game_sno FROM cpbl.games "
        f"WHERE {daily_chain_completed_games_sql(as_of_sql=AS_OF_SQL)}").fetchall()
    assert {tuple(r) for r in rows} == _EXPECTED_DAILY


def test_with_evidence_only_adds_official_final_scoreless(isolated) -> None:
    got = _selected(isolated, completed_games_sql_with_evidence("g", AS_OF_SQL))
    assert got == _EXPECTED_WITH_EVIDENCE


def test_official_final_sql_agrees_with_official_status(isolated) -> None:
    """SQL 端選列與 ``official_status``（Python）逐場一致，含改期舊列與同日續賽兩列。"""
    from cpbl.completion import official_final_sql

    cols = ("raw_present_status", "raw_game_result", "raw_game_date", "raw_pre_exe_date",
            "payload_hash", "fetched_at", "last_seen_at")
    sql_final = _selected(isolated, official_final_sql("g"))
    for y, k, s, *_ in _GAMES:
        rows = isolated.execute(
            f"SELECT {', '.join(cols)} FROM cpbl.game_schedule_status_revisions "
            "WHERE year=%s AND kind_code=%s AND game_sno=%s", (y, k, s)).fetchall()
        phase = official_status([dict(zip(cols, r, strict=True)) for r in rows])[0]
        assert ((y, k, s) in sql_final) is (phase == "final"), (y, k, s, phase)
