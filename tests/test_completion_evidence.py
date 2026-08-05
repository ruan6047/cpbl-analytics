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
    """空別名會讓相關子查詢退化成恆真（母體暴增，見下方變體測試），必須直接拒絕。"""
    with pytest.raises(ValueError):
        completed_games_sql_with_evidence("")


# ────────────────────────────────── 判準 SQL：以**母體差集**證明，不比對字串
#
# 這裡刻意不檢查 SQL 字面（`"g.year" in sql`、`startswith("(")` 之類）：字串比對
# 正是本卡一再強調擋不住運算子優先序／作用域錯誤的手法，拿它來驗判準等於自打嘴巴
# （跨家族查核 R1 的 RMDY1-R1-1）。改以唯讀 DB 跑真判準與**刻意構造的壞變體**，
# 比對它們選出的場次集合差在哪裡——錯誤只要存在就一定反映在母體上。
#
# 斷言一律針對**集合恆等式**而非絕對筆數：本庫是活的（每日爬蟲進新場、當日賽事
# 比分陸續寫入），任何硬編數字都會過期。查核者與我實測的絕對值本就不同
# （漏括號變體兩邊都是 13014，但總數 12955/13009、13263/13322 各有差異），
# 集合恆等式則兩邊完全一致。

_TAIPEI_TODAY = "(now() AT TIME ZONE 'Asia/Taipei')::date"
_EVIDENCE_EXISTS = (
    "EXISTS (SELECT 1 FROM cpbl.game_completion_evidence e "
    "WHERE e.year = games.year AND e.kind_code = games.kind_code "
    "AND e.game_sno = games.game_sno)")

# 壞變體 1：日期界線寫成尾隨 AND。SQL 的 AND 優先於 OR，實際解析為
# `score > 0 OR (evidence AND date)`——正比分場次完全繞過日期界線。
_VARIANT_MISSING_PARENS = (
    f"games.home_score + games.away_score > 0 OR {_EVIDENCE_EXISTS} "
    f"AND games.game_date <= {_TAIPEI_TODAY}")

# 壞變體 2：子查詢未關聯外層。未限定的 `year` 會解析到**內層**表，
# 變成 `gce_.year = gce_.year` 恆真，EXISTS 退化成「證據表有沒有任何一列」。
_VARIANT_UNCORRELATED = (
    f"games.game_date <= {_TAIPEI_TODAY} AND ("
    "games.home_score + games.away_score > 0 OR "
    "EXISTS (SELECT 1 FROM cpbl.game_completion_evidence gce_ "
    "WHERE gce_.year = year AND gce_.kind_code = kind_code "
    "AND gce_.game_sno = game_sno))")


def _game_set(cond: str) -> set[tuple]:
    """跑條件取場次集合（唯讀）。無 DB 時 skip。"""
    try:
        from cpbl.db import conn

        with conn() as c, c.cursor() as cur:
            cur.execute(
                f"SELECT year, kind_code, game_sno FROM cpbl.games games WHERE {cond}")
            return {tuple(r) for r in cur.fetchall()}
    except Exception as exc:  # noqa: BLE001 — 無 DB 時跳過（CI 無 Postgres）
        pytest.skip(f"需本機 DB：{exc}")


def test_criterion_adds_exactly_the_evidenced_ties_over_the_legacy_one() -> None:
    """真判準相對舊判準，**只**多收那 5 場有證據的 0:0，且不漏掉任何舊有場次。"""
    from cpbl.completion import completed_games_sql

    correct = _game_set(completed_games_sql_with_evidence("games"))
    legacy = _game_set(completed_games_sql())

    assert correct - legacy == set(CONFIRMED_TIES), "多收的不是那 5 場和局"
    assert legacy - correct == set(), "新判準漏掉了舊判準已收的場次"


def test_missing_parentheses_variant_leaks_future_dated_games() -> None:
    """壞變體 1 的母體**必須**與真判準不同，差集恰為「未來日期且已有比分」。

    這正是保留賽的形態（掛未來續賽日卻帶著中止比分）。差集非空才證明括號有意義。
    """
    correct = _game_set(completed_games_sql_with_evidence("games"))
    leaked = _game_set(_VARIANT_MISSING_PARENS) - correct
    future_scored = _game_set(
        f"games.game_date > {_TAIPEI_TODAY} AND games.home_score + games.away_score > 0")

    if not future_scored:
        pytest.skip("目前無未來日期保留賽，此變體無可觀察差異")
    assert leaked == future_scored, "漏括號洩漏的不是未來日期保留賽"
    assert leaked, "漏括號變體與真判準母體相同 → 括號守衛失效"


def test_uncorrelated_subquery_variant_swallows_unevidenced_scoreless_games() -> None:
    """壞變體 2 的母體**必須**與真判準不同，差集恰為「過去 0:0 且無證據」。

    未關聯的 EXISTS 恆真，於是每一場過去日期的 0:0 都被當成完成場。
    """
    correct = _game_set(completed_games_sql_with_evidence("games"))
    swallowed = _game_set(_VARIANT_UNCORRELATED) - correct
    unevidenced_scoreless = _game_set(
        f"games.game_date <= {_TAIPEI_TODAY} "
        f"AND games.home_score + games.away_score = 0 AND NOT {_EVIDENCE_EXISTS}")

    assert swallowed == unevidenced_scoreless, "恆真變體吞下的不是無證據的 0:0"
    assert len(swallowed) > 100, (
        f"差集只有 {len(swallowed)} 場，樣本過小則本測試失去鑑別力")


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


# ────────────────────────────────── 連段語意：和局中斷（官方，二次裁定定案）
#
# 語意經過一次翻案：首裁曾定「和局跳過不計」，PM 外部查證後**推翻**——官方語意是
# **和局中斷連段**，即原實作正確（需求方二次裁定，Issue #90）。
#
# 決定性反證（skip 語意會憑空製造官方榜上不存在的紀錄）：
#   * 2003 兄弟官方最長連勝 9，skip 會算成 12
#   * 1997 統一官方 7，skip 會算成 13（且會擠進歷史前三，官方榜查無此筆）
#   * 2022 富邦 6/22–7/16 為純 11 連敗，7/17 和局、7/18 再敗；媒體記載
#     「13 連不勝、一度 11 連敗追平隊史」——break 精確重現 11，skip 會算成 12
#
# 以下把官方值直接釘成黃金樣本：它們是**外部可查證**的，比任何內部一致性檢查都強。


def test_streak_semantics_tie_breaks_the_run() -> None:
    """純語意單元：和局**中斷**連段（官方語意）。"""
    from scripts.data_tie_remedy1 import _streaks_for

    # A 隊：勝、勝、和、勝 → 官方語意為 2 連勝（和局把連段切斷），不是 3
    games = [("A", "B", 5, 1), ("A", "B", 4, 2), ("A", "B", 3, 3), ("A", "B", 6, 0)]
    assert _streaks_for(games, tie_breaks=True)["A"][0] == 2
    assert _streaks_for(games, tie_breaks=False)["A"][0] == 3   # skip 語意對照（已否決）


@pytest.mark.parametrize(
    ("year", "team_code", "metric", "official", "skip_would_give", "note"),
    [
        (2003, "ACC011", "max_win_streak", 9, 12, "兄弟：官方連勝榜 9"),
        (1997, "ADD011", "max_win_streak", 7, 13, "統一：skip 會虛構出 13 並擠進歷史前三"),
        (2022, "AEO011", "max_lose_streak", 11, 12, "富邦：7/17 和局中斷，官方 11 追平隊史"),
    ],
)
def test_streaks_match_official_leaderboard(
    year: int, team_code: str, metric: str, official: int,
    skip_would_give: int, note: str,
) -> None:
    """回歸：連段須重現**官方榜**的值，且不得等於 skip 語意的值。"""
    import cpbl.models.special_records as sr

    try:
        out: dict = {}
        sr._add_streaks(year, "A", out)
    except Exception as exc:  # noqa: BLE001 — 無 DB 時跳過
        pytest.skip(f"需本機 DB：{exc}")
    if not out:
        pytest.skip(f"需本機 DB：{year} 無資料")

    got = out[team_code][metric]
    assert got == official, f"{note}：得 {got}，官方 {official}"
    assert got != skip_would_give, f"{note}：命中已否決的 skip 語意值 {skip_would_give}"


def test_r5_newly_visible_ties_do_break_2023_streaks() -> None:
    """回歸 5：和局可見（新判準）後，2023 的連敗**應該**被和局中斷。

    Phase 1 首次觀測到的統一 5→4、富邦 8→7 **是正確行為**（新資料讓官方語意生效），
    不是缺陷——首裁一度誤判為錯並要求改成 skip，二次裁定翻案後這裡改為守衛：
    若哪天有人把語意改回 skip，這兩個值會漲回 5／8 而被此測試擋下。
    """
    import cpbl.models.special_records as sr

    try:
        out: dict = {}
        sr._add_streaks(2023, "A", out)
    except Exception as exc:  # noqa: BLE001 — 無 DB 時跳過
        pytest.skip(f"需本機 DB：{exc}")
    if not out:
        pytest.skip("需本機 DB：2023 無資料")

    # ADD011 = 統一7-ELEVEn獅（2023/A/175）、AEO011 = 富邦悍將（2023/A/119）
    assert out["ADD011"]["max_lose_streak"] == 4
    assert out["AEO011"]["max_lose_streak"] == 7


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
