"""TEAM-STYLE2 純函式單元測試：主教練判定封閉解、二分歸屬、Pearson r、bootstrap 性質。

規則出處：docs/research/TEAM-STYLE2_RESULTS.md §0（預註冊凍結）。
"""

from __future__ import annotations

import math

from scripts.team_style2_manager_pairs import (
    AXES,
    bootstrap_deltas,
    classify_pair,
    clean_name,
    main_manager,
    pearson,
    season_manager_games,
)

# ---------------------------------------------------------------------------
# 逐季主教練判定（封閉解；表格式取自維基快照實際格式）
# ---------------------------------------------------------------------------

# 富邦式 header（逐年戰績表含「總教練」欄）
HDR_B = ["年度", "職棒紀年", "總教練", "年排名", "出賽", "勝場", "敗場", "和局", "勝率", "備註"]
# 中信式 header（「按總教練分」專表，逐季列）
HDR_A = ["時期", "任次", "姓名", "球季", "出賽", "勝", "敗", "和", "勝率", "季後賽", "總冠軍"]
# 統一式 header（總教練欄＋球季欄含半季/日期區間）
HDR_S = ["任次", "總教練", "隊長", "球季", "出賽", "勝", "敗", "和", "勝率", "季後賽", "總冠軍"]


def test_midseason_change_year_majority_wins():
    """季中換帥年（富邦 2018 型）：三任各帶場數 → 場數最多者為主教練。"""
    rows = [
        ["2018", "職棒29年", "葉君璋", "3", "73", "31", "42", "0", ".425", "季中請辭"],
        ["2018", "職棒29年", "陳連宏", "3", "44", "22", "22", "0", ".500", "季後賽外卡"],
        ["2018", "職棒29年", "劉榮華", "3", "3", "1", "2", "0", ".333", "代理三場"],
        ["2019", "職棒30年", "陳連宏", "1", "119", "63", "54", "2", ".538", ""],
    ]
    games, used = season_manager_games(HDR_B, rows, 2018)
    assert games == {"葉君璋": 73, "陳連宏": 44, "劉榮華": 3}
    assert len(used) == 3
    mm, detail = main_manager(games)
    assert mm == "葉君璋"
    assert "73場" in detail


def test_acting_manager_with_few_games_does_not_win():
    """中信 2018 型：代理僅 1/17 場，正任 102 場 → 正任為主教練（按場數，非頭銜）。"""
    rows = [
        ["中信兄弟", "3", "史耐德", "2018", "102", "42", "59", "1", ".416", "0", "0"],
        ["中信兄弟", "代", "丘昌榮", "2018", "1", "0", "1", "0", ".000", "0", "0"],
        ["中信兄弟", "代", "伯納", "2018", "17", "6", "11", "0", ".353", "0", "0"],
    ]
    games, _ = season_manager_games(HDR_A, rows, 2018)
    mm, _ = main_manager(games)
    assert mm == "史耐德"


def test_tie_is_undecidable():
    """統一 2019 型：黃甘霖 60（上半季）／劉育辰 60（下半季代理）平手 → 不可判定。"""
    rows = [
        ["11", "黃甘霖", "陳傑憲", "2019上半季", "60", "25", "34", "1", ".424", "0", "0"],
        ["(代理)", "劉育辰", "陳傑憲", "2019下半季", "60", "23", "36", "1", ".390", "0", "0"],
    ]
    games, _ = season_manager_games(HDR_S, rows, 2019)
    assert games == {"黃甘霖": 60, "劉育辰": 60}
    mm, reason = main_manager(games)
    assert mm is None
    assert "平手" in reason


def test_year_cell_variants_parse_first_4digit():
    """年份欄「2019上半季」「2022/05/17-5/24」→ 取第一個四位數字。"""
    rows = [
        ["(代理)", "高志綱", "", "2022/05/17-5/24", "6", "4", "2", "0", ".667", "0", "0"],
        ["12", "林岳平", "林岱安", "2022", "114", "44", "67", "3", ".396", "0", "0"],
    ]
    games, _ = season_manager_games(HDR_S, rows, 2022)
    assert games == {"高志綱": 6, "林岳平": 114}
    assert main_manager(games)[0] == "林岳平"


def test_same_name_multiple_stints_sum():
    """同季同名多列（多任次）場數加總。"""
    rows = [
        ["2020", "職棒31年", "某教練", "4", "50", "25", "25", "0", ".500", ""],
        ["2020", "職棒31年", "另一人", "4", "30", "15", "15", "0", ".500", ""],
        ["2020", "職棒31年", "某教練", "4", "40", "20", "20", "0", ".500", "回任"],
    ]
    games, _ = season_manager_games(HDR_B, rows, 2020)
    assert games == {"某教練": 90, "另一人": 30}


def test_no_games_rows_undecidable():
    """無含場數列（味全 2019「重返中華職棒」型）→ 不可判定。"""
    rows = [["2019", "職棒30年", "葉君璋", "--", "重返中華職棒"]]
    games, used = season_manager_games(HDR_B, rows, 2019)
    assert games == {} and used == []
    mm, reason = main_manager(games)
    assert mm is None
    assert "不可判定" in reason


def test_multi_name_cell_undecidable():
    """防禦性：姓名欄含多名（頓號）→ 不可判定。"""
    mm, reason = main_manager({"甲、乙": 120})
    assert mm is None
    assert "多名" in reason


def test_clean_name_strips_annotations():
    assert clean_name("竹之內雅史（日语：たけのうち）") == "竹之內雅史"
    assert clean_name("古久保健二") == "古久保健二"


# ---------------------------------------------------------------------------
# 二分歸屬
# ---------------------------------------------------------------------------

def test_classify_pair():
    assert classify_pair("葉君璋", "葉君璋") == "same"
    assert classify_pair("林威助", "彭政閔") == "changed"
    assert classify_pair(None, "林岳平") == "excluded"
    assert classify_pair("黃甘霖", None) == "excluded"


# ---------------------------------------------------------------------------
# Pearson r
# ---------------------------------------------------------------------------

def test_pearson_closed_form():
    assert abs(pearson([1, 2, 3], [2, 4, 6]) - 1.0) < 1e-12
    assert abs(pearson([1, 2, 3], [3, 2, 1]) + 1.0) < 1e-12
    # 封閉解：x=[0,1,2], y=[0,1,4] → sxy=4, sxx=2, syy=78/9 → r = 4/sqrt(2*78/9) ≈ 0.960769
    r = pearson([0, 1, 2], [0, 1, 4])
    assert abs(r - 4 / math.sqrt(2 * 78 / 9)) < 1e-9


def test_pearson_degenerate_none():
    assert pearson([1, 1, 1], [1, 2, 3]) is None
    assert pearson([1.0], [2.0]) is None


# ---------------------------------------------------------------------------
# bootstrap：決定性、CI 排序、退化保護
# ---------------------------------------------------------------------------

def _mk_pair(seedval: float, noise: float) -> dict:
    z_t = {ax: seedval + i * 0.1 for i, ax in enumerate(AXES)}
    z_t1 = {ax: z_t[ax] + noise * ((-1) ** i) for i, ax in enumerate(AXES)}
    return {"z_t": z_t, "z_t1": z_t1}


def _synthetic_groups() -> tuple[list[dict], list[dict]]:
    # 同教練組：t+1 幾乎複製 t（高延續）；換教練組：t+1 與 t 去相關（低延續）。
    # 數值刻意逐對相異避免 std=0 退化。
    same = [_mk_pair(0.3 * k - 1.5, 0.05) for k in range(10)]
    changed = []
    for i in range(8):
        z_t = {ax: 0.37 * i - 1.2 + j * 0.11 for j, ax in enumerate(AXES)}
        z_t1 = {ax: ((i * 5 + j * 3) % 13 - 6) / 4 for j, ax in enumerate(AXES)}
        changed.append({"z_t": z_t, "z_t1": z_t1})
    return same, changed


def test_bootstrap_deterministic_and_ci_ordered():
    same, changed = _synthetic_groups()
    b1 = bootstrap_deltas(same, changed, b=300, seed=42)
    b2 = bootstrap_deltas(same, changed, b=300, seed=42)
    assert b1 == b2  # 同 seed 逐位一致
    assert b1["replicates_used"] + b1["replicates_dropped_degenerate"] == 300
    lo, hi = b1["mean_delta_ci"]
    assert lo <= hi
    for ax in AXES:
        alo, ahi = b1["per_axis_ci"][ax]
        assert alo <= ahi


def test_bootstrap_seed_changes_stream():
    same, changed = _synthetic_groups()
    b1 = bootstrap_deltas(same, changed, b=300, seed=1)
    b2 = bootstrap_deltas(same, changed, b=300, seed=2)
    assert b1 != b2


def test_bootstrap_detects_synthetic_gap():
    """同教練組近乎完美延續、換教練組去相關 → Δ̄ CI 下界應 > 0（合成資料 sanity）。"""
    same, changed = _synthetic_groups()
    b = bootstrap_deltas(same, changed, b=500, seed=7)
    lo, _hi = b["mean_delta_ci"]
    assert lo > 0


def test_bootstrap_degenerate_axis_dropped():
    """某軸整組常數 → 該組 r 未定義 → replicate 剔除計數；CI 回 None。"""
    same, changed = _synthetic_groups()
    for p in same:
        p["z_t"] = dict(p["z_t"], speed=0.0)  # speed 軸常數 → std=0
    b = bootstrap_deltas(same, changed, b=50, seed=3)
    assert b["replicates_dropped_degenerate"] == 50
    assert b["replicates_used"] == 0
    assert b["mean_delta_ci"] is None
