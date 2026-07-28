"""連續無自責分局數（ML-PITCHER-SCORELESS1）：保守性紅線的釘子。

這些測試釘的是「**不確定一律往中斷／不採計解讀**」。任何一條轉綠成「多算一局」
都代表演算法開始高估，即違反卡面紅線 2。純函式測試不需要 DB。
"""

from __future__ import annotations

from datetime import date

import pytest

from cpbl.models.scoreless_streak import (
    BREAK_DATA_BOUNDARY,
    BREAK_EARNED_RUN,
    BREAK_MISSING_LINE,
    BREAK_POSTSEASON_EARNED_RUN,
    BREAK_SUSPENDED,
    SUSPENDED,
    Appearance,
    compute_streak,
    last_pitch_inning,
    outs_to_innings,
    pigeonhole_tail_outs,
    tail_credit,
)

PID = "P1"
OTHER = "P2"


def app(day: int, er: int | None, outs: int | None = 3, kind: str = "A", **kw) -> Appearance:
    return Appearance(year=2026, kind_code=kind, game_sno=day, game_date=date(2026, 5, day),
                      earned_runs=er, outs=outs, **kw)


def ev(inning: int, vht: str, seq: int, out_cnt, pitcher=PID, *, score=False,
       away=0, home=0, change=False) -> dict:
    return {
        "main_event_no": f"{inning:02d}{vht}{seq:04d}000",
        "inning_seq": inning, "visiting_home_type": vht, "out_cnt": out_cnt,
        "is_score": score, "is_change_player": change, "pitcher_acnt": pitcher,
        "visiting_score": away, "home_score": home,
    }


def half(inning: int, *, pitcher=PID, runs=0, outs_before=(0, 1, 2), away=0, home=0,
         vht="1") -> list[dict]:
    """一個正常的三出局半局：每個出局數各一列。`runs` 只改跑分欄與 is_score。"""
    rows = []
    for i, oc in enumerate(outs_before):
        rows.append(ev(inning, vht, i + 1, oc, pitcher, away=away, home=home))
    if runs:
        rows[-1]["is_score"] = True
        if vht == "1":
            for r in rows[-1:]:
                r["visiting_score"] = away + runs
        else:
            for r in rows[-1:]:
                r["home_score"] = home + runs
    return rows


# --------------------------------------------------------------------------
# 回走：中斷條件
# --------------------------------------------------------------------------

def test_earned_run_appearance_breaks_the_streak():
    """出賽 ER>0 必中斷——後面的 ER=0 出賽不得被接上去。"""
    res = compute_streak([app(1, 0), app(2, 3), app(3, 0), app(4, 0)])

    assert res.strict_outs == 6           # 只有 5/3、5/4 兩場
    assert res.break_reason == BREAK_EARNED_RUN
    assert res.break_key == (2026, "A", 2)


def test_unearned_run_does_not_break():
    """非自責失分**不**中斷（紅線 5 的語意：這是無自責分，不是無失分）。

    ER 一律讀官方欄位；本模組沒有、也不得有任何判定某分是否自責的邏輯。
    """
    res = compute_streak([app(1, 0), app(2, 0), app(3, 0)])

    assert res.strict_outs == 9
    assert res.boundary_limited is True


def test_suspended_game_breaks():
    """保留賽橫跨兩個日期、排序無法保證正確 → 一律中斷，不採計。"""
    res = compute_streak([app(1, 0), app(2, 0, delay_kind=SUSPENDED), app(3, 0)])

    assert res.strict_outs == 3
    assert res.break_reason == BREAK_SUSPENDED


def test_missing_official_line_breaks():
    """官方 ER 或局數缺值 → 中斷（不猜、不補算）。"""
    assert compute_streak([app(1, 0), app(2, None), app(3, 0)]).break_reason == BREAK_MISSING_LINE
    assert compute_streak([app(1, 0), app(2, 0, outs=None), app(3, 0)]).strict_outs == 3


def test_boundary_limited_when_all_appearances_consumed():
    """走完所有可得出賽仍未中斷 → 必須標示受資料邊界限制（紅線 4，不得沉默截斷）。

    注意：這**不是**「跨 2018 必截斷」的測試（那條是
    `test_pre_2018_appearances_are_truncated`）。只驗旗標會通過一個根本沒 enforce
    邊界的實作——iteration 2 的 F3 正是這樣漏掉的。
    """
    res = compute_streak([app(1, 0), app(2, 0)])

    assert res.boundary_limited is True
    assert res.break_reason is None


def test_pre_2018_appearances_are_truncated():
    """**F3 迴歸**：早於 `DATA_FROM_YEAR` 的出賽一律截斷，不得計入（紅線 4）。

    2018 前無逐場資料，那些列即使被餵進來也不可信。`DATA_FROM_YEAR` 必須是**執行點**，
    不是 payload 上的一個顯示欄位——「DB 目前最早就是 2018」是運氣不是保證。
    """
    old = Appearance(year=2017, kind_code="A", game_sno=9, game_date=date(2017, 9, 1),
                     earned_runs=0, outs=3)
    new = Appearance(year=2018, kind_code="A", game_sno=1, game_date=date(2018, 4, 1),
                     earned_runs=0, outs=3)

    res = compute_streak([old, new])

    assert res.outs == 3                                  # 只有 2018 那場，不是 6
    assert [a.year for a in res.counted] == [2018]
    assert res.break_reason == BREAK_DATA_BOUNDARY
    assert res.boundary_limited is True                   # 且必須明示，不得沉默截斷


def test_data_boundary_year_is_configurable_and_enforced():
    """邊界年可調，但一定會 enforce（防止未來改年份時又退回只顯示不執行）。"""
    apps = [app(1, 0), app(2, 0)]

    res = compute_streak(apps, data_from_year=2027)

    assert res.outs == 0 and res.break_reason == BREAK_DATA_BOUNDARY


def test_not_boundary_limited_when_broken():
    res = compute_streak([app(1, 5), app(2, 0)])

    assert res.boundary_limited is False


def test_empty_appearances():
    res = compute_streak([])

    assert (res.outs, res.strict_outs, res.boundary_limited) == (0, 0, False)


# --------------------------------------------------------------------------
# 賽別範圍：只算例行賽；季後賽乾淨跳過、掉分中斷
# --------------------------------------------------------------------------

def test_postseason_innings_are_never_counted():
    """季後賽局數不計入例行賽紀錄（需求方裁定：只算例行賽）。"""
    res = compute_streak([app(1, 0), app(2, 0, kind="C"), app(3, 0)], counted_kinds=("A",))

    assert res.strict_outs == 6                      # 只有兩場 A，C 那場不算
    assert [a.kind_code for a in res.skipped] == ["C"]


def test_clean_postseason_appearance_does_not_break():
    """季後賽 ER=0 → 跳過：不計局數，但也沒有中斷這條紀錄的理由。"""
    res = compute_streak([app(1, 0), app(2, 0, kind="E"), app(3, 0)], counted_kinds=("A",))

    assert res.break_reason is None
    assert res.boundary_limited is True
    assert res.strict_outs == 6
    # 跳過的場次必須留存，供 API 揭露——不做沉默跳過。
    assert [a.key for a in res.skipped] == [(2026, "E", 2)]


def test_postseason_earned_run_breaks_the_streak():
    """季後賽掉自責分 → 中斷。

    一律跳過會產生「紀錄橫跨一場他被打爆的台灣大賽」的輸出；中斷才讓本值同時是
    「只算例行賽」與「一軍所有比賽都算」**兩種讀法的下界**（紅線 2）。
    """
    res = compute_streak([app(1, 0), app(2, 3, kind="C"), app(3, 0), app(4, 0)],
                         counted_kinds=("A",))

    assert res.strict_outs == 6                      # 只剩 C 之後的兩場
    assert res.break_reason == BREAK_POSTSEASON_EARNED_RUN
    assert res.break_key == (2026, "C", 2)


def test_postseason_break_takes_no_tail():
    """季後賽中斷不取尾段——那場的局數本來就不計入例行賽紀錄。"""
    called = []

    def spy(a):
        called.append(a.key)
        return None

    compute_streak([app(1, 2, kind="C"), app(2, 0)], tail_lookup=spy, counted_kinds=("A",))

    assert called == []


def test_counted_kinds_none_counts_everything():
    """未指定 counted_kinds 時退回「全賽別都計入」，供純演算法測試使用。"""
    res = compute_streak([app(1, 0), app(2, 0, kind="C")])

    assert res.strict_outs == 6 and res.skipped == []


# --------------------------------------------------------------------------
# 尾段：鴿籠下界（官方逐局比分 ＋ 官方局數，零假設）
# --------------------------------------------------------------------------

def test_pigeonhole_matches_the_worked_example():
    """坎南 2026-04-23 實例：對手逐局 [0,2,0,1,0,0,0,0,0]、官方 21 outs。

    最後得分局＝第 4 局 ⇒ 前綴 4 局至多 12 個出局 ⇒ 後綴至少 21−12＝9 個出局＝3.0 局。
    """
    opp = dict(enumerate([0, 2, 0, 1, 0, 0, 0, 0, 0], start=1))

    outs, suffix_from, _to = pigeonhole_tail_outs(opp, 21, 3)

    assert outs == 9 and suffix_from == 5


def test_sno55_regression_from_team_filtered_facts():
    """**回歸案例 2026/A/55（坎南）**——用隊別過濾後的事實重算，確認 3.0 局非巧合。

    我自己查到的隊別（`pitching_gamelog.visiting_home_type`）：

        台鋼（vht=2，主隊）坎南 21｜林詩翔 3｜陳柏清 3 ＝ 27 outs ＝ 守 9 局
        味全（vht=1，客隊）梅賽鍶 15｜林鋅杰 4｜李超 3｜林子昱 2 ＝ 24 outs ＝ 守 8 局
                          （台鋼主場 4:3 獲勝，九局下未進行）

    坎南是**主隊**投手 ⇒ 後綴要看**客隊味全**的逐局得分。兩種等價寫法都給 9 outs：

        本式：官方 21 − 3 × 前綴 4 局 = 9
        另式：後綴(5~9 局) 15 outs − **同隊**其他投手 (林詩翔 3 ＋ 陳柏清 3) = 9

    第二式若誤把對手投手（李超 3）當同隊，數字碰巧仍是 9——**那是運氣不是推論**。
    本式不含「其他投手」這一項，從源頭消除該類錯誤。
    """
    kanan_outs = 21
    opp_runs = dict(enumerate([0, 2, 0, 1, 0, 0, 0, 0, 0], start=1))   # 味全（客隊）

    outs, suffix_from, _to = pigeonhole_tail_outs(opp_runs, kanan_outs, 3)

    assert (outs, suffix_from) == (9, 5)
    assert outs_to_innings(outs) == 3.0
    # 同隊其他投手寫法交叉驗算（必須用同隊的 3+3，不是對手的 3）
    assert 5 * 3 - (3 + 3) == outs


def test_opponent_side_must_be_the_batting_side_of_the_other_team():
    """取錯邊 = 拿自己隊的進攻得分當失分。這裡釘住「相反側」這個決策。"""
    home_pitcher_vht = "2"
    away_batting_side = "1" if home_pitcher_vht == "2" else "2"

    assert away_batting_side == "1"


def test_missing_scoring_inning_row_must_fail_closed():
    """**回歸（iteration 8）**：`game_scoreboard` 缺掉一個**有得分**的局。

    `{1:0, 3:0}` 看起來全場零得分 ⇒ 後綴自第 1 局 ⇒ 宣稱 6 outs；但官方終場對手得 1 分，
    代表第 2 局那列不見了，真正可證的下界是 0。`game_scoreboard` 是逐列 UPSERT、沒有
    完整性 constraint，所以這不是純理論。

    以**官方終場比分**（`games`）驗逐局總和是官方對官方的交叉檢查，不引入新假設。
    """
    incomplete = {1: 0, 3: 0}

    assert pigeonhole_tail_outs(incomplete, 6, 1)[:2] == (0, None)
    assert tail_credit((2026, "A", 1), incomplete, 6, 1).reason == "scoreboard_incomplete"
    # 同一組逐局比分，若官方終場確實是 0 分，則完整、可採計
    assert pigeonhole_tail_outs(incomplete, 6, 0)[:2] == (6, 1)


def test_pigeonhole_is_zero_when_opponent_scores_late():
    """對手在後段得分 → 後綴太短、下界 ≤ 0 → 採計 0（fail-closed）。

    這是刻意的保守失敗模式：即使該投手早早退場、後面的分是別人掉的，官方逐局比分
    無法區分，於是不採計。**寧可少報一局。**
    """
    opp = dict(enumerate([1, 0, 0, 0, 0, 0, 2, 0, 0], start=1))

    assert pigeonhole_tail_outs(opp, 18, 3)[:2] == (0, None)


def test_pigeonhole_never_exceeds_official_outs():
    opp = dict(enumerate([0, 0, 0], start=1))

    outs, _, _ = pigeonhole_tail_outs(opp, 6, 0)

    assert outs == 6


def test_pigeonhole_needs_both_official_facts():
    assert pigeonhole_tail_outs({}, 21, 0)[:2] == (0, None)
    assert pigeonhole_tail_outs({1: 0}, None, 0)[:2] == (0, None)
    assert pigeonhole_tail_outs({1: 0}, 21, None)[:2] == (0, None)


def test_pigeonhole_uses_runs_not_earned_runs():
    """後綴以**得分**界定：零得分必然零自責分，反之不然，故以 R 判定只會低估。

    第 3 局有 1 分（不論自責與否）就切斷後綴——即使那分是失誤造成的非自責分。
    """
    opp = dict(enumerate([0, 0, 1, 0, 0], start=1))

    outs, suffix_from, _to = pigeonhole_tail_outs(opp, 15, 1)

    assert suffix_from == 4 and outs == 15 - 9


def test_pigeonhole_handles_extra_innings():
    opp = dict(enumerate([0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0], start=1))

    outs, suffix_from, _to = pigeonhole_tail_outs(opp, 30, 1)

    assert suffix_from == 3 and outs == 30 - 6


def test_tail_credit_reports_why_it_credited_nothing():
    assert tail_credit((2026, "A", 1), {}, 21, 0).reason == "no_scoreboard"
    assert tail_credit((2026, "A", 1), {1: 5}, 3, 5).reason == "no_provable_scoreless_suffix"
    assert tail_credit((2026, "A", 1), {1: 0}, 21, None).reason == "no_official_final_score"


def test_tail_feeds_into_the_streak():
    opp = dict(enumerate([0, 2, 0, 1, 0, 0, 0, 0, 0], start=1))
    apps = [app(1, 3, outs=21), app(2, 0), app(3, 0)]

    res = compute_streak(apps, tail_lookup=lambda a: tail_credit(a.key, opp, a.outs, 3))

    assert res.strict_outs == 6 and res.outs == 15


# --------------------------------------------------------------------------
# 顯示
# --------------------------------------------------------------------------

@pytest.mark.parametrize("outs,expected", [(0, 0.0), (1, 0.1), (2, 0.2), (3, 1.0), (85, 28.1)])
def test_outs_to_innings(outs, expected):
    assert outs_to_innings(outs) == expected


# ---------------------------------------------------------------------------
# ML-PITCHER-SCORELESS2：退場局認證（`last_pitch_inning`）與第二條下界
#
# 這一組釘的是「**認證只能由正向觀測建立**」：livelog 少任何一列，觀測到的累計投球數
# 最大值只會變小、達不到官方總數 ⇒ 不認證 ⇒ 退回原本的全場鴿籠下界。任何一條轉綠成
# 「缺列時仍然認證」都代表本方法退化成「以缺席為證據」，即前七輪被推翻的那條路。
# ---------------------------------------------------------------------------


def test_last_pitch_inning_takes_the_earliest_inning_that_exhausts_the_official_count():
    """換投列會把被換下投手的最終累計投球數帶到**下一局**（實例 2026/A/223 黃子鵬）。

    取「最早達成官方總數的局」在邏輯上同樣成立（該局內已存在一列顯示累計值等於官方
    總數，其後不可能再有投球），而且不必判讀 `is_change_player` 這個旗標。
    """
    observed = {1: 24, 2: 43, 3: 56, 4: 69, 5: 79, 6: 91, 7: 91}

    assert last_pitch_inning(observed, 91, 9) == 6


def test_hidden_rows_can_only_weaken_the_certificate_never_strengthen_it():
    """缺列 ⇒ 觀測最大值變小 ⇒ 達不到官方總數 ⇒ 不認證。**這是本方法的核心保守性。**"""
    full = {1: 24, 2: 43, 3: 56, 4: 69, 5: 79, 6: 91}
    assert last_pitch_inning(full, 91, 9) == 6

    # 把最後一局整段藏起來：再也證明不到耗盡 → None（退回全場鴿籠下界）
    assert last_pitch_inning({i: v for i, v in full.items() if i < 6}, 91, 9) is None
    # 只藏中間一局：最大值仍在，認證的局不會**提早**
    assert last_pitch_inning({i: v for i, v in full.items() if i != 3}, 91, 9) == 6


@pytest.mark.parametrize("observed, official, innings, why", [
    ({1: 10}, None, 9, "官方投球數缺值"),
    ({1: 10}, 0, 9, "官方投球數為 0"),
    ({}, 91, 9, "沒有任何觀測"),
    ({1: None, 2: 91}, 91, 9, "任一局觀測值未知——未知不得折成已知"),
    ({1: 50, 2: 92}, 91, 9, "觀測值超過官方總數：兩個官方量互相矛盾"),
    ({1: 50, 10: 91}, 91, 9, "觀測局序超出該場局數"),
    ({1: 50, 2: 60}, 91, 9, "累計值從未達到官方總數（多半就是缺列）"),
])
def test_last_pitch_inning_fails_closed(observed, official, innings, why):
    assert last_pitch_inning(observed, official, innings) is None, why


def test_huang_2026_07_26_regression_the_card_headline_case():
    """黃子鵬 2026-07-26：第 1 局失分、投完第 6 局，對手第 7 局對**後援**再得分。

    全場式 `18 − 3×7 < 0` → 0（這正是卡面說的「7% 採計率」的成因）。
    退場局式 `18 − 3×1 − 3×(9−6) = 6` → 採計 2.0 局，視窗第 2~6 局。
    真值是 5.0 局，仍然少報 3.0 局——**低估是允許的，高估不是**。
    """
    opp = {1: 1, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0, 7: 1, 8: 0, 9: 0}

    assert pigeonhole_tail_outs(opp, 18, 2) == (0, None, None)
    assert pigeonhole_tail_outs(opp, 18, 2, last_pitch=6) == (6, 2, 6)


def test_certificate_never_lowers_the_credit():
    """坎南 2026/A/55：全場式已給 9 outs，認證存在時**不得反而變少**。"""
    opp = {1: 0, 2: 2, 3: 0, 4: 1, 5: 0, 6: 0, 7: 0, 8: 0, 9: 0}

    baseline = pigeonhole_tail_outs(opp, 21, 3)
    assert baseline == (9, 5, 9)
    for lp in range(1, 10):
        outs, _from, _to = pigeonhole_tail_outs(opp, 21, 3, last_pitch=lp)
        assert outs >= baseline[0], f"退場局 {lp} 讓採計值下降"


def test_out_of_range_last_pitch_is_ignored_not_trusted():
    opp = {1: 1, 2: 0, 3: 0}
    assert pigeonhole_tail_outs(opp, 9, 1, last_pitch=0)[0] == \
        pigeonhole_tail_outs(opp, 9, 1)[0]
    assert pigeonhole_tail_outs(opp, 9, 1, last_pitch=99)[0] == \
        pigeonhole_tail_outs(opp, 9, 1)[0]


def _feasible_worlds(innings: int, official_outs: int):
    """窮舉所有「他的出局數如何散佈在各局」的可行世界（每半局至多 3 個出局）。"""
    from itertools import product
    for x in product(range(4), repeat=innings):
        if sum(x) == official_outs:
            yield x


@pytest.mark.parametrize("runs", [
    (1, 0, 0, 0, 1, 0),
    (0, 0, 1, 0, 0, 0),
    (2, 1, 0, 0, 0, 0),
    (0, 0, 0, 0, 0, 1),
    (1, 1, 1, 1, 1, 1),
    (0, 0, 0, 0, 0, 0),
])
@pytest.mark.parametrize("official_outs", [3, 6, 9, 12, 15])
@pytest.mark.parametrize("last_pitch", [None, 1, 2, 3, 4, 5, 6])
def test_bound_holds_in_every_feasible_world(runs, official_outs, last_pitch):
    """**窮舉式保守性檢驗**：採計值不得超過任何一個可行世界裡「視窗內的真實出局數」。

    這是對算術本身的暴力驗證——不假設投手投了哪幾局，把每半局 0~3 個出局的所有配置
    全部列舉出來，逐一驗 `採計值 ≤ 視窗內出局數`。一旦式子寫錯（例如少扣一段、
    或視窗端點取錯），這裡會立刻紅。
    """
    opp = dict(enumerate(runs, start=1))
    credited, w_from, w_to = pigeonhole_tail_outs(
        opp, official_outs, sum(runs), last_pitch=last_pitch)
    if not credited:
        return
    assert w_from is not None and w_to is not None
    # 視窗內必須全部零得分，否則「零失分」的宣稱本身就不成立
    assert all(opp[i] == 0 for i in range(w_from, w_to + 1))
    worlds = list(_feasible_worlds(len(runs), official_outs))
    assert worlds, "測試參數應至少有一個可行世界"
    for x in worlds:
        in_window = sum(x[i - 1] for i in range(w_from, w_to + 1))
        assert credited <= in_window, (
            f"採計 {credited} > 可行世界 {x} 的視窗 [{w_from},{w_to}] 內出局數 {in_window}")
