"""DATA-TIE-REMEDY1：證據感知完成判準的四重回歸（**語意斷言，非字串比對**）。

為什麼堅持語意斷言：舊測試 `test_completion.py` 以字串比對釘住判準，
運算子優先序這類錯誤能同時通過字串比對與計數檢查而不被發現
（DATA-RULES-AUDIT1 §3.1）。本檔全部以「餵入樣本→檢查判定」或
「對真實 DB 跑判準→檢查母體」的方式驗證。

四重回歸（缺一不可）：

1. 5 場已證實 0:0 和局皆判為完成場。
2. 官方 standings 和局數對帳完全解釋（2018–2024 無殘留）。
3. 0:0 偽陽集不被整批誤納（僅該 5 場進入）。
4. 未來日期的保留賽（帶比分）仍被排除。
"""

from __future__ import annotations

from datetime import date

import pytest

from cpbl.completion import (
    completed_games_sql_with_evidence,
    is_completed_game,
)

# 5 場已證實 0:0 和局（官方 box 直接取證：game_detail=final、滿規章 §38 五局門檻）
CONFIRMED_TIES = [(2018, "A", 124), (2021, "A", 256), (2023, "A", 119),
                  (2023, "A", 175), (2025, "A", 233)]

_TODAY = date(2026, 7, 19)


# ────────────────────────────────── 純函式：判準語意（不需 DB）


@pytest.mark.parametrize(
    ("home", "away", "game_day", "has_evidence", "expected", "why"),
    [
        (5, 4, date(2026, 7, 16), False, True, "一般完賽：比分自證"),
        (3, 2, _TODAY, False, True, "日期邊界：當日已有比分"),
        (None, None, _TODAY, False, False, "當日未開打"),
        # 0:0 的兩種世界——證據是唯一的區分依據
        (0, 0, date(2026, 7, 18), False, False, "0:0 無證據 → 隔離為待判讀，不得納入"),
        (0, 0, date(2026, 7, 18), True, True, "0:0 有證據 → 真實和局，必須納入"),
        # ⚠️ 括號守衛：日期界線在最外層，帶比分也不得繞過
        (5, 4, date(2026, 8, 8), False, False, "未來日期保留賽（帶中止比分）必須排除"),
        (5, 4, date(2026, 8, 8), True, False, "未來日期即使有證據也必須排除"),
        (7, 4, date(2026, 8, 8), False, False, "同上；續賽日仍在未來"),
    ],
)
def test_is_completed_game_semantics(
    home: int | None, away: int | None, game_day: date,
    has_evidence: bool, expected: bool, why: str,
) -> None:
    assert is_completed_game(home, away, game_day, _TODAY, has_evidence) is expected, why


def test_sql_builder_refuses_empty_alias() -> None:
    """空別名會讓相關子查詢退化成恆真（實測誤納 318 場），必須直接拒絕。"""
    with pytest.raises(ValueError):
        completed_games_sql_with_evidence("")


def test_sql_correlates_subquery_to_outer_games_row() -> None:
    """證據子查詢必須關聯到**外層**該場，而非只問「證據表有沒有資料」。

    相關子查詢內的未限定欄名會優先解析到內層表：``gce_.year = year`` 會被
    PostgreSQL 解析成 ``gce_.year = gce_.year``（恆真）。故外層欄位必須帶限定詞。
    """
    sql = completed_games_sql_with_evidence("g")

    assert "g.year" in sql and "g.kind_code" in sql and "g.game_sno" in sql
    # 子查詢的比對右側不得是未限定的裸欄名
    for col in ("year", "kind_code", "game_sno"):
        assert f"= {col}" not in sql, f"{col} 未加限定詞 → 相關子查詢會恆真"


def test_sql_wraps_date_boundary_outside_the_or() -> None:
    """日期界線必須在最外層、OR 子句必須加括號（AND 優先於 OR 的陷阱）。"""
    sql = completed_games_sql_with_evidence("g")

    assert sql.startswith("(") and sql.endswith(")")
    # 日期條件出現在第一個 OR 之前，且 OR 被括號包住
    assert sql.index("game_date <=") < sql.index(" OR ")
    assert "> 0 OR EXISTS" in sql


# ────────────────────────────────── 真實 DB：四重回歸


def _rows(sql: str, params: tuple = ()):
    try:
        from cpbl.db import conn

        with conn() as c, c.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()
    except Exception as exc:  # noqa: BLE001 — 無 DB 時跳過（CI 無 Postgres）
        pytest.skip(f"需本機 DB：{exc}")


def test_r1_five_confirmed_ties_are_completed() -> None:
    """回歸 1：5 場已證實 0:0 和局皆判為完成場。"""
    cond = completed_games_sql_with_evidence("g")
    for year, kind, sno in CONFIRMED_TIES:
        rows = _rows(
            f"SELECT ({cond}) FROM cpbl.games g "
            "WHERE g.year=%s AND g.kind_code=%s AND g.game_sno=%s",
            (year, kind, sno))
        assert rows, f"{year}/{kind}/{sno} 不在 games 表"
        assert rows[0][0] is True, f"{year}/{kind}/{sno} 未被判為完成場"


def test_r2_official_tie_reconciliation_has_no_remainder() -> None:
    """回歸 2：官方 standings 和局數對帳完全解釋（2018–2024 殘留為 0）。

    恆等式：官方和局場數 ＝ 我方推導的非零和局 ＋ 有證據的 0:0 和局。
    """
    rows = _rows("""
        SELECT s.year,
               sum(s.tie) / 2.0 AS official_tie_games,
               (SELECT count(*) FROM cpbl.games g
                 WHERE g.year=s.year AND g.kind_code='A'
                   AND g.home_score=g.away_score AND g.home_score>0) AS derived_nonzero,
               (SELECT count(*) FROM cpbl.games g
                 WHERE g.year=s.year AND g.kind_code='A'
                   AND g.home_score=0 AND g.away_score=0
                   AND EXISTS (SELECT 1 FROM cpbl.game_completion_evidence e
                               WHERE e.year=g.year AND e.kind_code=g.kind_code
                                 AND e.game_sno=g.game_sno)) AS evidenced_scoreless
        FROM cpbl.standings s WHERE s.year BETWEEN 2018 AND 2024
        GROUP BY s.year ORDER BY s.year
    """)
    assert rows, "standings 無 2018–2024 資料"
    for year, official, nonzero, evidenced in rows:
        assert float(official) == nonzero + evidenced, (
            f"{year} 和局對帳有殘留：官方 {official} ≠ 非零 {nonzero} + 有證據 0:0 {evidenced}")


def test_r3_scoreless_false_positive_set_is_not_admitted_wholesale() -> None:
    """回歸 3：0:0 偽陽集不被整批誤納——母體中僅該 5 場進入完成場。

    偽陽母體＝0:0 且日期已過且 ``present_status=1``（AUDIT1 實測 288 場，
    其中僅 5 場為真；``present_status`` 對完賽毫無鑑別力）。
    """
    cond = completed_games_sql_with_evidence("g")
    total = _rows("""
        SELECT count(*) FROM cpbl.games g
        WHERE g.home_score + g.away_score = 0 AND g.game_date <= CURRENT_DATE
          AND g.present_status = 1
    """)[0][0]
    assert total > 100, f"偽陽母體只有 {total} 場，樣本過小則本測試失去意義"

    admitted = _rows(f"""
        SELECT g.year, g.kind_code, g.game_sno FROM cpbl.games g
        WHERE g.home_score + g.away_score = 0 AND g.game_date <= CURRENT_DATE
          AND g.present_status = 1 AND ({cond})
        ORDER BY g.year, g.game_sno
    """)
    assert [tuple(r) for r in admitted] == CONFIRMED_TIES, (
        f"0:0 母體 {total} 場中被納入的不是恰好那 5 場，而是 {admitted}")


def test_r4_future_dated_games_are_never_completed() -> None:
    """回歸 4：未來日期的場次一律排除，**即使已有比分**（保留賽的中止比分）。"""
    cond = completed_games_sql_with_evidence("g")
    scored_future = _rows("""
        SELECT count(*) FROM cpbl.games g
        WHERE g.game_date > (now() AT TIME ZONE 'Asia/Taipei')::date
          AND g.home_score + g.away_score > 0
    """)[0][0]
    if not scored_future:
        pytest.skip("目前無「未來日期且帶比分」的保留賽，本回歸無樣本可驗")

    leaked = _rows(f"""
        SELECT g.year, g.kind_code, g.game_sno, g.game_date FROM cpbl.games g
        WHERE g.game_date > (now() AT TIME ZONE 'Asia/Taipei')::date AND ({cond})
    """)
    assert leaked == [], f"未來日期場次被判為完成：{leaked}"
