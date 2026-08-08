"""連續無自責分局數（ML-PITCHER-SCORELESS1）：保守性紅線的釘子。

這些測試釘的是「**不確定一律往中斷／不採計解讀**」。任何一條轉綠成「多算一局」
都代表演算法開始高估，即違反卡面紅線 2。純函式測試不需要 DB。
"""

from __future__ import annotations

from datetime import date
from itertools import product

import pytest

from cpbl.models.scoreless_streak import (
    BREAK_DATA_BOUNDARY,
    BREAK_EARNED_RUN,
    BREAK_MISSING_LINE,
    BREAK_POSTSEASON_EARNED_RUN,
    BREAK_POSTSEASON_RUN,
    BREAK_RUN,
    BREAK_SUSPENDED,
    EARNED_RUN_BASIS,
    RUN_BASIS,
    SUSPENDED,
    Appearance,
    compute_streak,
    outs_to_innings,
    pigeonhole_tail_outs,
    tail_credit,
)

PID = "P1"
OTHER = "P2"


def app(day: int, er: int | None, outs: int | None = 3, kind: str = "A", **kw) -> Appearance:
    """預設 `runs` 跟著 `er` 走（自責分口徑的既有測試不受影響）；要測兩者不同時明給 runs。"""
    kw.setdefault("runs", er)
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
    """非自責失分**不**中斷自責分口徑（紅線 5 的語意：這是無自責分，不是無失分）。

    ER 一律讀官方欄位；本模組沒有、也不得有任何判定某分是否自責的邏輯。

    **這一條必須真的構造出非自責失分**（`runs=1, earned_runs=0`）才有鑑別力——原版
    三場全 0 的寫法在任何口徑下都不中斷，通過與否跟「非自責失分是否中斷」無關。
    """
    res = compute_streak([app(1, 0), app(2, 0, runs=1), app(3, 0)])

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

    outs, suffix_from = pigeonhole_tail_outs(opp, 21, 3)

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

    outs, suffix_from = pigeonhole_tail_outs(opp_runs, kanan_outs, 3)

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

    assert pigeonhole_tail_outs(incomplete, 6, 1) == (0, None)
    assert tail_credit((2026, "A", 1), incomplete, 6, 1).reason == "scoreboard_incomplete"
    # 同一組逐局比分，若官方終場確實是 0 分，則完整、可採計
    assert pigeonhole_tail_outs(incomplete, 6, 0) == (6, 1)


def test_pigeonhole_is_zero_when_opponent_scores_late():
    """對手在後段得分 → 後綴太短、下界 ≤ 0 → 採計 0（fail-closed）。

    這是刻意的保守失敗模式：即使該投手早早退場、後面的分是別人掉的，官方逐局比分
    無法區分，於是不採計。**寧可少報一局。**
    """
    opp = dict(enumerate([1, 0, 0, 0, 0, 0, 2, 0, 0], start=1))

    assert pigeonhole_tail_outs(opp, 18, 3) == (0, None)


def test_pigeonhole_never_exceeds_official_outs():
    opp = dict(enumerate([0, 0, 0], start=1))

    outs, _ = pigeonhole_tail_outs(opp, 6, 0)

    assert outs == 6


def test_pigeonhole_needs_both_official_facts():
    assert pigeonhole_tail_outs({}, 21, 0) == (0, None)
    assert pigeonhole_tail_outs({1: 0}, None, 0) == (0, None)
    assert pigeonhole_tail_outs({1: 0}, 21, None) == (0, None)


def test_pigeonhole_uses_runs_not_earned_runs():
    """後綴以**得分**界定：零得分必然零自責分，反之不然，故以 R 判定只會低估。

    第 3 局有 1 分（不論自責與否）就切斷後綴——即使那分是失誤造成的非自責分。
    """
    opp = dict(enumerate([0, 0, 1, 0, 0], start=1))

    outs, suffix_from = pigeonhole_tail_outs(opp, 15, 1)

    assert suffix_from == 4 and outs == 15 - 9


def test_pigeonhole_handles_extra_innings():
    opp = dict(enumerate([0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0], start=1))

    outs, suffix_from = pigeonhole_tail_outs(opp, 30, 1)

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
# ML-PITCHER-SCORELESS2：零投球自責分反例——為什麼視窗不得提早收掉
# --------------------------------------------------------------------------

def test_zero_pitch_earned_run_forbids_ending_the_window_early():
    """規則反例：投手可以在**一球都不投**的情況下被記自責分。

    ML-PITCHER-SCORELESS2 iteration 1 曾以「官方投球數耗盡的局」把零得分視窗提早收掉，
    其前提是「讓跑者上壘一定要投球」。該前提被 `docs/reference/棒球規則.txt` 原文推翻：

    - 用語定義 BASE ON BALLS（5.05(b)(1)）：四壞球「包括⋯⋯裁判員獲得來自守方總教練之
      手勢，意圖故意四壞球讓擊球員上壘」；9.14(d)「對於守方總教練通知裁判員意圖讓擊
      球員上一壘時，記錄員應記錄為故意四壞球」。**零投球即可送出保送。**
    - 6.02(a) 罰則／5.06(c)(3)：「投手犯規—各跑壘員應進 1 個壘」。**零投球即可推進得分。**
    - 9.16：「為決定自責分，無論任何情況，故意四壞球皆認定為四壞球」；9.16(a)【註 2】①
      明列自責分因素含「四壞球（含故意四壞球）⋯⋯投手犯規」。

    於是：投完第 8 局（累計 91 球、24 outs）→ 第 9 局仍是責任投手 → 以**手勢**故意四壞
    三次（投球數仍是 91）→ 投手犯規使三壘跑者得分。**全程零新增投球，該分記為自責分。**

    因此只要視窗右端之後還有任何得分局，那分就**可能**是他的，採計必須是 0。
    這是確定性的規則路徑，不是低機率事件——紅線 2 明令不得以機率論證代替證明。
    """
    opp = dict(enumerate([0] * 8 + [1], start=1))

    # 第 1~8 局零得分、24 outs；若容許把視窗收到「第 8 局」會採計到 24 outs（8.0 局），
    # 而真值可能是 0（他的自責分發生在第 9 局）。全場式正確地回 0。
    assert pigeonhole_tail_outs(opp, 24, 1) == (0, None)


def test_credit_never_exceeds_the_full_game_pigeonhole():
    """紅線：採計視窗**必須開到比賽末端**——窮舉釘死。

    只有「全場最後得分局之後全零得分」這個視窗排除得掉零投球自責分：那些局根本沒有
    分可以記給任何人。任何把視窗提早收掉的做法，都會把「他之後那幾局」留在視窗外，
    而那正是零投球自責分（手勢故意四壞＋投手犯規）可以發生的地方。

    等價陳述：採計值不得超過 `官方出局數 − 3 × 全場最後得分局`。
    """
    for innings in range(1, 10):
        for runs in product(range(2), repeat=innings):
            opp = dict(enumerate(runs, start=1))
            scored = [i for i, r in opp.items() if r]
            n_prefix = max(scored) if scored else 0
            for official_outs in range(1, 3 * innings + 1):
                credited, _ = pigeonhole_tail_outs(opp, official_outs, sum(runs))
                assert credited <= max(official_outs - 3 * n_prefix, 0), (
                    f"runs={runs} outs={official_outs} 採計 {credited} "
                    f"超過全場鴿籠上限")


def _withdrawn_last_pitch_bound(runs, official_outs, last_pitch):
    """ML-PITCHER-SCORELESS2 iteration 1 撤回的第二式，僅供本測試對照，**不得回到產品碼**。"""
    scored = [i for i, r in enumerate(runs, 1) if r]
    n_prefix = max(scored) if scored else 0
    baseline = official_outs - 3 * n_prefix
    if not 1 <= last_pitch <= len(runs):
        return baseline
    before = [i for i in scored if i <= last_pitch]
    m = max(before) if before else 0
    return max(baseline, official_outs - 3 * m - 3 * (len(runs) - last_pitch))


def test_a_last_pitch_narrowing_gains_only_where_the_counterexample_applies():
    """為什麼這條下界**救不回來**：它的增益區**包含於**反例適用區。

    窮舉小型組態證明：撤回的第二式嚴格大於全場式，**只有當** `last_pitch` 之後
    存在得分局時才會發生（反之不成立——`last_pitch` 之後有得分局不保證有增益，
    見 `docs/research/ML-PITCHER-SCORELESS2_RESULTS.md` §2 的反向反例統計）。
    而「`last_pitch` 之後有得分局」正是零投球自責分可能發生的情形
    （見 `test_zero_pitch_earned_run_forbids_ending_the_window_early`）。

    推論：**沒有任何一塊增益落在安全區**。若加守衛把不安全的情形排除掉，剩下的增益
    恰好是 0 ——也就是退回全場式本身。這條路不存在「部分可救」的中間地帶。
    """
    gains = 0
    for innings in range(1, 10):
        for runs in product(range(2), repeat=innings):
            scored = [i for i, r in enumerate(runs, 1) if r]
            n_prefix = max(scored) if scored else 0
            for official_outs in range(1, 3 * innings + 1):
                baseline = official_outs - 3 * n_prefix
                for last_pitch in range(1, innings + 1):
                    widened = _withdrawn_last_pitch_bound(runs, official_outs, last_pitch)
                    if widened > baseline:
                        gains += 1
                        assert [i for i in scored if i > last_pitch], (
                            f"runs={runs} outs={official_outs} last_pitch={last_pitch}："
                            "有增益卻無反例適用條件，本卡的撤回理由需重新檢視")
    assert gains, "測試參數必須涵蓋到有增益的組態，否則此測試沒有鑑別力"


# --------------------------------------------------------------------------
# ML-PITCHER-RUNLESS1：失分口徑（`RUN_BASIS`）
# --------------------------------------------------------------------------

def test_run_basis_breaks_on_an_unearned_run_and_earned_run_basis_does_not():
    """**兩個口徑是兩個紀錄**，同一組出賽必須給出不同答案，否則新端點沒有存在理由。

    2026-06-11 呂彥青那場正是這個形態：`runs=1, earned_runs=0`（失誤造成的非自責失分）。
    自責分口徑不中斷（與 ERA 語意一致）、失分口徑中斷（與媒體「無失分」一致）。
    """
    apps = [app(1, 0), app(2, 0, runs=1), app(3, 0)]

    er = compute_streak(apps, basis=EARNED_RUN_BASIS)
    run = compute_streak(apps, basis=RUN_BASIS)

    assert (er.strict_outs, er.break_reason) == (9, None)
    assert (run.strict_outs, run.break_reason) == (3, BREAK_RUN)
    assert run.break_key == (2026, "A", 2)


def test_run_basis_missing_runs_fails_closed_instead_of_folding_to_zero():
    """`runs=None` ＝「這場掉幾分不知道」，**不是 0 分** → `BREAK_MISSING_LINE`。

    `Appearance.runs` 的預設值就是 `None`，所以「忘了餵 runs」與「DB 是 NULL」走同一條
    fail-closed 路徑；若哪天有人把它折成 0，這條會轉綠成「多算一段」＝ 高估。
    """
    missing = Appearance(year=2026, kind_code="A", game_sno=2, game_date=date(2026, 5, 2),
                         earned_runs=0, outs=3, runs=None)
    apps = [app(1, 0), missing, app(3, 0)]

    res = compute_streak(apps, basis=RUN_BASIS)

    assert res.strict_outs == 3
    assert res.break_reason == BREAK_MISSING_LINE
    # 同一組資料在自責分口徑下不中斷——證明 fail-closed 是 basis 選出來的欄位在管，
    # 不是碰巧兩個口徑都缺值。
    assert compute_streak(apps, basis=EARNED_RUN_BASIS).strict_outs == 9


def test_each_basis_has_its_own_break_reason_codes():
    """中斷原因碼不得共用：前端要能分辨「掉自責分」與「掉失分」。"""
    er_post = compute_streak([app(1, 0), app(2, 1, kind="C"), app(3, 0)],
                             counted_kinds=("A",), basis=EARNED_RUN_BASIS)
    run_post = compute_streak([app(1, 0), app(2, 1, kind="C"), app(3, 0)],
                              counted_kinds=("A",), basis=RUN_BASIS)

    assert er_post.break_reason == BREAK_POSTSEASON_EARNED_RUN
    assert run_post.break_reason == BREAK_POSTSEASON_RUN
    assert BREAK_RUN != BREAK_EARNED_RUN


def test_run_basis_skips_a_clean_postseason_appearance_by_its_own_criterion():
    """季後賽 `runs=0` 才跳過；`runs>0, ER=0` 在失分口徑要中斷，不得沿用 ER 的判準。"""
    apps = [app(1, 0), app(2, 0, kind="E", runs=1), app(3, 0)]

    er = compute_streak(apps, counted_kinds=("A",), basis=EARNED_RUN_BASIS)
    run = compute_streak(apps, counted_kinds=("A",), basis=RUN_BASIS)

    assert [a.key for a in er.skipped] == [(2026, "E", 2)] and er.strict_outs == 6
    assert run.skipped == [] and run.strict_outs == 3
    assert run.break_reason == BREAK_POSTSEASON_RUN


def test_basis_charged_reads_the_field_it_names():
    a = app(1, 0, runs=2)

    assert EARNED_RUN_BASIS.charged(a) == 0
    assert RUN_BASIS.charged(a) == 2
    assert (EARNED_RUN_BASIS.field, RUN_BASIS.field) == ("earned_runs", "runs")


def test_run_basis_never_exceeds_earned_run_basis():
    """**窮舉小型組態**釘住模組 docstring 那句「失分口徑恆 ≤ 自責分口徑」。

    證明前提是 `runs = 0 ⇒ earned_runs = 0`（自責分是失分的子集），所以合法組態只有
    `(R,ER) ∈ {(0,0), (1,0), (1,1), (2,1)}`——`(0,1)` 這種「零失分卻有自責分」在規則上
    不存在，全母體實測也是 0 筆（對帳腳本 X1 的 `失分=0 卻 自責分>0` 欄）。

    這裡窮舉的是**回走邏輯**（含季後賽跳過／中斷），不含尾段；尾段的部分由 X3 在真實
    資料上逐人驗（尾段可能落在不同場次，純靠型別推不出來）。
    """
    combos = [(0, 0), (1, 0), (1, 1), (2, 1)]
    checked = 0
    for n in range(1, 5):
        for seq in product(combos, repeat=n):
            for kinds in product(("A", "C"), repeat=n):
                apps = [app(i + 1, er, kind=k, runs=r)
                        for i, ((r, er), k) in enumerate(zip(seq, kinds, strict=True))]
                er_res = compute_streak(apps, counted_kinds=("A",), basis=EARNED_RUN_BASIS)
                run_res = compute_streak(apps, counted_kinds=("A",), basis=RUN_BASIS)
                assert run_res.strict_outs <= er_res.strict_outs, (
                    f"seq={seq} kinds={kinds}：失分口徑 {run_res.strict_outs} "
                    f"> 自責分口徑 {er_res.strict_outs}")
                checked += 1
    assert checked > 1000, "組態數太少，此測試沒有鑑別力"


def test_the_ordering_flips_when_earned_runs_is_unknown_but_runs_is_not():
    """大小關係**唯一**的翻轉路徑：`earned_runs` 缺值而 `runs` 有值。

    這不是缺陷，是「未知一律中斷」的正確結果——但它是模組 docstring 那句「恆 ≤」的
    前提條件，必須有一條測試把它釘出來，否則那句話會被讀成無條件成立。
    對帳腳本的 X2 就是在量這種列在真實資料裡有幾筆（不假設它是 0）。
    """
    weird = Appearance(year=2026, kind_code="A", game_sno=2, game_date=date(2026, 5, 2),
                       earned_runs=None, outs=3, runs=0)
    apps = [app(1, 0), weird, app(3, 0)]

    er = compute_streak(apps, basis=EARNED_RUN_BASIS)
    run = compute_streak(apps, basis=RUN_BASIS)

    assert er.strict_outs == 3 and er.break_reason == BREAK_MISSING_LINE
    assert run.strict_outs == 9 > er.strict_outs


def test_tail_is_shared_verbatim_by_both_bases():
    """尾段是**同一個函式、同一組官方事實**，兩口徑一字不差——這正是「口徑一致」的來源。

    自責分口徑下尾段證的是「零得分 ⇒ 零自責分」（跨口徑的蘊含）；失分口徑下證的是
    「零得分 ⇒ 零失分」（同一個量的另一個粒度）。數值相同，敘述層數不同。
    """
    opp = dict(enumerate([0, 2, 0, 1, 0, 0, 0, 0, 0], start=1))
    apps = [app(1, 3, outs=21, runs=3), app(2, 0), app(3, 0)]
    def lookup(a):
        return tail_credit(a.key, opp, a.outs, 3)

    er = compute_streak(apps, tail_lookup=lookup, basis=EARNED_RUN_BASIS)
    run = compute_streak(apps, tail_lookup=lookup, basis=RUN_BASIS)

    assert er.tail is not None and run.tail is not None
    assert er.tail.outs == run.tail.outs == 9
    assert er.outs == run.outs == 15


# --------------------------------------------------------------------------
# 顯示
# --------------------------------------------------------------------------

@pytest.mark.parametrize("outs,expected", [(0, 0.0), (1, 0.1), (2, 0.2), (3, 1.0), (85, 28.1)])
def test_outs_to_innings(outs, expected):
    assert outs_to_innings(outs) == expected
