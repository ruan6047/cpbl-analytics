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
    GameEvidence,
    compute_streak,
    half_innings_of,
    half_out_allocation,
    out_allocation,
    outs_to_innings,
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
# 尾段：livelog 定位
# --------------------------------------------------------------------------

def _sb(rows: list[dict], extra: dict | None = None) -> dict:
    """由事件列推出「與 livelog 相符的」記分板。

    覆蓋缺陷的測試用 `extra` 疊上獨立來源才知道的事實（例：livelog 缺了某個半局，
    但記分板證明它存在且有得分）。
    """
    board = {h.key: h.runs for h in half_innings_of(rows, PID)}
    if extra:
        board.update(extra)
    return board


def _box(rows: list[dict], override: dict | None = None) -> dict:
    """由事件列推出「與 livelog 相符的」官方 box；`override` 疊上官方才知道的事實。"""
    b = {p: lo for p, (lo, _hi) in out_allocation(rows).items()}
    if override:
        b.update(override)
    return b


def _number_pitches(rows: list[dict]) -> list[dict]:
    """依序給每位投手編逐球序號（模擬 livelog 的 pitch_cnt）。"""
    n: dict[str, int] = {}
    for r in rows:
        if r["is_change_player"]:
            continue
        p = r["pitcher_acnt"]
        n[p] = n.get(p, 0) + 1
        r["pitch_cnt"] = n[p]
    return rows


def _pitches(rows: list[dict], override: dict | None = None) -> dict:
    """與事件列相符的官方投球數；`override` 模擬「官方說他投更多、livelog 卻少了」。"""
    n: dict[str, int] = {}
    for r in rows:
        if r["is_change_player"] or r.get("pitch_cnt") is None:
            continue
        n[r["pitcher_acnt"]] = max(n.get(r["pitcher_acnt"], 0), int(r["pitch_cnt"]))
    if override:
        n.update(override)
    return n


def _tail_of(rows: list[dict], official_outs: int | None = None, pitcher: str = PID,
             scoreboard: dict | None = None, box: dict | None = None,
             pitches: dict | None = None):
    rows = _number_pitches(rows)
    board = _sb(rows) if scoreboard is None else scoreboard
    b = _box(rows) if box is None else box
    if official_outs is not None:
        b = {**b, pitcher: official_outs}
    ev = GameEvidence(scoreboard=board, official_outs=b,
                      official_pitches=_pitches(rows) if pitches is None else pitches)
    return tail_credit((2026, "A", 1), rows, pitcher, ev)


def test_missing_livelog_gives_no_tail():
    """ER>0 那場沒有 livelog → 尾段 0 出局數（缺資料一律不採計）。"""
    res = compute_streak([app(1, 2), app(2, 0)], tail_lookup=lambda a: None)

    assert res.outs == 3 and res.strict_outs == 3


def test_tail_counts_run_free_half_innings_after_the_run():
    """得分半局之後的乾淨半局才算：第 1 局有分、2~3 局乾淨 → 尾段 6 出局數。"""
    rows = half(1, runs=1) + half(2, away=1) + half(3, away=1) + half(4, pitcher=OTHER, away=1)
    tail = _tail_of(rows)

    assert tail.outs == 6
    assert tail.credited == ((3, "1"), (2, "1"))


def test_tail_stops_at_a_half_inning_with_runs():
    """一遇到有得分的半局就停——更早的乾淨半局也不採計（連續紀錄已在該處重新起算）。"""
    rows = half(1) + half(2, runs=2) + half(3, away=2) + half(4, pitcher=OTHER, away=2)
    tail = _tail_of(rows)

    assert tail.outs == 3
    assert tail.credited == ((3, "1"),)


def test_tail_ignores_half_inning_the_pitcher_did_not_finish():
    """中途接手的半局無法證明他記下幾個出局 → 採計 0，但零得分故不中斷、繼續往前。"""
    mid = [ev(3, "1", 1, 1), ev(3, "1", 2, 2)]          # 從 1 出局接手
    rows = half(1, runs=1) + half(2, away=1) + [ev(3, "1", 0, 0, OTHER, away=1)] + mid
    tail = _tail_of(rows)

    assert tail.credited == ((2, "1"),)                  # 第 3 局沒被採計出局數
    assert tail.passed == ((3, "1"),)                    # 但也沒中斷
    assert tail.outs == 3


def test_last_half_inning_of_game_only_credits_proven_outs():
    """全場最後一個半局可能未達三出局（再見／保護傘）→ 只採計最後一列的打席前出局數。"""
    rows = half(1, runs=1) + [ev(2, "1", 1, 0, away=1), ev(2, "1", 2, 1, away=1)]
    tail = _tail_of(rows)

    assert tail.outs == 1            # 不是 3


def test_official_outs_disagreeing_with_livelog_fails_closed():
    """官方出局數與 livelog 可見區間不符 → 覆蓋閘門攔下（比夾擠更強）。

    `TailCredit.clamped` 的夾擠仍留在程式裡當第二層防線，但覆蓋閘門會先攔截，
    所以實務上不會走到夾擠——這裡釘的是「先攔截」這個更強的行為。
    """
    rows = half(1, runs=1) + half(2, away=1) + half(3, away=1) + half(4, pitcher=OTHER, away=1)

    tail = _tail_of(rows, official_outs=4)

    assert tail.outs == 0
    assert tail.coverage_reason == "official_outs_outside_visible_range"


def test_tail_feeds_into_the_streak():
    rows = half(1, runs=1) + half(2, away=1) + half(3, pitcher=OTHER, away=1)
    res = compute_streak([app(1, 1, outs=6), app(2, 0), app(3, 0)],
                         tail_lookup=lambda a: _tail_of(rows, 6))

    assert res.strict_outs == 6 and res.outs == 9


# --------------------------------------------------------------------------
# 覆蓋完整性（F1）：漏掉的半局會被「跨過」而非被看見 → 必須 fail-closed
# --------------------------------------------------------------------------

def test_missing_scoring_half_inning_must_not_credit_earlier_halves():
    """**F1 迴歸**：整場有 livelog，但失自責分的那個半局整段缺失。

    投手第 1 局乾淨、第 2 局失分，而 2 局上整段不在 livelog 裡。反向走「看得見的」
    半局會直接跨過第 2 局而採計第 1 局＝**高估**。安全尾段必須是 0。

    只驗「已選入的半局零得分」抓不到這條路徑——那證明的是選中的都乾淨，不是沒有
    漏掉的。量詞方向不同，所以要有獨立的覆蓋完整性證明。
    """
    rows = half(1) + half(1, vht="2", pitcher=OTHER) + half(2, vht="2", pitcher=OTHER)
    board = _sb(rows, extra={(2, "1"): 1})       # 獨立來源證明 2 局上存在且有得分

    tail = _tail_of(rows, official_outs=6, scoreboard=board)

    assert tail.outs == 0
    assert tail.credited == ()
    assert tail.coverage_reason == "scoreboard_half_missing_from_livelog"


def test_pitcher_outs_below_official_fails_closed():
    """觀測到的出局數少於官方局數 ⇒ livelog 缺了他投的內容 → 尾段歸零。"""
    rows = half(1, runs=1) + half(2, away=1) + half(3, pitcher=OTHER, away=1)

    assert _tail_of(rows, official_outs=6).outs == 3          # 觀測 6 ≥ 官方 6，正常採計
    tail = _tail_of(rows, official_outs=12)                   # 官方說他投更多 → 有缺漏
    assert tail.outs == 0 and tail.coverage_reason == "pitcher_outs_below_official"


def test_pitcher_half_innings_must_be_contiguous():
    """投手局序不連續（中間整局消失）→ 尾段歸零。"""
    rows = half(1, runs=1) + half(3, away=1) + half(4, pitcher=OTHER, away=1)
    board = _sb(rows, extra={(2, "1"): 0})

    tail = _tail_of(rows, official_outs=6, scoreboard=board)

    assert tail.outs == 0
    assert tail.coverage_reason in {
        "scoreboard_half_missing_from_livelog", "pitcher_half_innings_not_contiguous"}


def test_missing_scoreboard_fails_closed():
    """沒有獨立來源可交叉驗證 → 不採計（不賭 livelog 自己說的話）。"""
    rows = half(1, runs=1) + half(2, away=1) + half(3, pitcher=OTHER, away=1)

    tail = _tail_of(rows, official_outs=6, scoreboard={})

    assert tail.outs == 0 and tail.coverage_reason == "no_scoreboard"


def test_scoreboard_disagreeing_on_a_credited_half_stops_crediting():
    """livelog 說乾淨、記分板說有得分 → 以中斷方向解讀（兩來源取聯集）。"""
    rows = half(1, runs=1) + half(2, away=1) + half(3, away=1) + half(4, pitcher=OTHER, away=1)
    board = _sb(rows, extra={(3, "1"): 1})       # 記分板說第 3 局上有分

    tail = _tail_of(rows, official_outs=9, scoreboard=board)

    assert tail.outs == 0 and tail.credited == ()


def test_unplayed_bottom_of_final_inning_is_benign():
    """主隊未進行的最終局下半：記分板有列、livelog 沒有——良性，不該擋掉尾段。

    實測 2018+ 有 1,814 個半局屬於此樣態，若一律視為缺漏會把尾段全數歸零。
    """
    rows = half(1, runs=1) + half(1, vht="2", pitcher=OTHER) + half(2, away=1)
    board = _sb(rows, extra={(2, "2"): 0})       # 最終局下半未進行

    tail = _tail_of(rows, official_outs=6, scoreboard=board)

    assert tail.coverage_reason is None          # 重點：覆蓋檢查沒有誤擋
    # 仍只採計 2 出局——(2,'1') 是 livelog 最後一個半局，無法證明有第三個出局
    # （末半局規則）。覆蓋檢查用寬鬆上界、採計用嚴格下界，兩個方向各司其職。
    assert tail.outs == 2 and tail.credited == ((2, "1"),)


def test_missing_events_inside_a_clean_half_inning_must_not_credit_it():
    """**F1-b 迴歸（iteration 3）**：半局**內部**事件缺漏。

    官方 4 outs：第 1 局失分半局 3 outs、第 2 局零得分半局他只記 1 out 就換投，而
    **換投後的所有事件都不在 livelog**。現存列仍全屬他、首列 out_cnt=0，於是
    `pitched_whole` 為真、半局集合比對通過、投手半局連號——**前面每一道閘門都放行**。

    這是「檢查看得見的量」循環的第三層：`pitched_whole` 由現存列一致推導，而現存列
    一致證明不了列是齊全的。要跳出循環，證據必須來自 livelog 之外——官方 box 知道
    後任投手記了幾個出局，那些出局在 livelog 裡沒有位置可以安放，對帳就不平。
    """
    rows = (
        half(1, runs=1)                                    # 第 1 局：失分，3 outs
        + [ev(2, "1", 1, 0)]                               # 第 2 局：他只留下 1 個打席
        + half(3, pitcher=OTHER, away=1)                   # 之後由別人投
    )
    # 官方 box：他 4 outs；後任投手 OTHER 記了第 2 局剩下的 2 outs ＋ 第 3 局 3 outs。
    box = {PID: 4, OTHER: 5}

    tail = _tail_of(rows, box=box)

    assert tail.outs == 0, "半局內事件缺漏時不得採計"
    assert tail.credited == ()
    assert tail.coverage_reason == "official_outs_outside_visible_range"


def test_third_out_must_be_observable_to_credit_a_full_half():
    """採計整個半局需要看到「他投到第三個出局的那個打席」（末列 `out_cnt == 2`）。

    只靠「現存列都是他」會把「1 出局後換投、後續事件缺漏」誤判成投完整局。
    """
    partial = [ev(2, "1", 1, 0), ev(2, "1", 2, 1)]          # 只到 1 出局
    rows = half(1, runs=1) + partial + half(3, pitcher=OTHER, away=1)

    tail = _tail_of(rows, box={PID: 5, OTHER: 5})

    assert tail.outs == 0


def test_box_pitcher_absent_from_livelog_fails_closed():
    """官方 box 有這位投手、livelog 完全看不到他 → 缺漏，尾段歸零。"""
    rows = half(1, runs=1) + half(2, away=1) + half(3, pitcher=OTHER, away=1)

    tail = _tail_of(rows, box={PID: 6, OTHER: 3, "GHOST": 3})

    assert tail.outs == 0 and tail.coverage_reason == "box_pitcher_missing_from_livelog"


def test_missing_official_box_fails_closed():
    rows = half(1, runs=1) + half(2, away=1) + half(3, pitcher=OTHER, away=1)

    tail = _tail_of(rows, box={})

    assert tail.outs == 0 and tail.coverage_reason == "no_official_box"


def test_cross_half_offsetting_misallocation_is_caught():
    """**F1-c 迴歸（iteration 4）**：跨半局的相反誤配會在整場總和裡互相抵銷。

    查核者的反例：可見配置 P=(4,4)、O=(5,5)、Q=(8,9)，官方 box 完全吻合，於是
    「官方總數落在可見區間內」通過；但 P 在採計半局實際只有 2 outs，高估 1 out。
    第 2 局上末列仍是 `out_cnt == 2`，局部條件也擋不住。

    **總和證明不了歸屬。** 攔截點必須是逐事件的：官方投球數說 O 投了 3 球，livelog
    只看得到 1 球，逐球序號就閉合不起來。
    """
    rows = (
        half(1, runs=1)                                   # 第 1 局：失分
        + [ev(2, "1", 1, 0), ev(2, "1", 2, 1), ev(2, "1", 3, 2)]   # 第 2 局：看似他投完
        + half(3, pitcher=OTHER, away=1)
    )
    rows = _number_pitches(rows)
    # 官方說 OTHER 在這場投了比 livelog 看得到的更多球（他在第 2 局的事件缺漏）
    pitches = _pitches(rows, override={OTHER: _pitches(rows)[OTHER] + 2})

    tail = _tail_of(rows, pitches=pitches)

    assert tail.outs == 0
    assert tail.coverage_reason == "pitch_sequence_not_closed"


def test_credited_outs_never_exceed_the_cell_lower_bound():
    """採計值不得超過「投手 × 半局」那一格的**下界**——只採計被逼出來的部分。"""
    rows = _number_pitches(half(1, runs=1) + half(2, away=1))
    cells = half_out_allocation(rows)

    # 第 2 局是全場最後一個半局 → 該格是區間 (2,3)：至少 2 個出局是確定的
    assert cells[(PID, (2, "1"))] == (2, 3)
    assert _tail_of(rows).outs == 2      # 採下界，不是上界


def test_pitch_sequence_closure_detects_missing_middle_event():
    rows = _number_pitches(half(1, runs=1) + half(2, away=1)
                           + half(3, pitcher=OTHER, away=1))
    official = _pitches(rows)
    rows = [r for r in rows if r.get("pitch_cnt") != 2 or r["pitcher_acnt"] != PID]

    tail = _tail_of(rows, pitches=official)

    assert tail.outs == 0 and tail.coverage_reason == "pitch_sequence_not_closed"


def test_missing_official_pitch_counts_fails_closed():
    rows = half(1, runs=1) + half(2, away=1) + half(3, pitcher=OTHER, away=1)

    tail = _tail_of(rows, pitches={})

    assert tail.outs == 0 and tail.coverage_reason == "no_official_pitch_counts"


def test_out_allocation_splits_at_pitcher_change_boundaries():
    """`out_allocation` 以半局內的投手更迭邊界切段——這是對帳的粒度基礎。"""
    rows = [ev(1, "1", 1, 0), ev(1, "1", 2, 1, OTHER), ev(1, "1", 3, 2, OTHER)]
    rows += half(2, pitcher=OTHER)

    alloc = out_allocation(rows)

    assert alloc[PID] == (1, 1)        # 0 → 1
    # OTHER：第 1 局 1→3 共 2 個出局，＋ 第 2 局。第 2 局是全場最後一個半局、可能未達
    # 三出局，故下界取觀測值 2、上界取 3 → (4, 5)。這個上下界差就是末半局的不確定性。
    assert alloc[OTHER] == (4, 5)


def test_duplicate_half_innings_fail_closed():
    rows = half(1) + half(2, pitcher=OTHER) + half(1)
    tail = _tail_of(rows, official_outs=3)

    assert tail.outs == 0 and tail.coverage_reason == "duplicate_half_innings"


# --------------------------------------------------------------------------
# half_innings_of：livelog 讀法的陷阱
# --------------------------------------------------------------------------

def test_change_player_rows_are_excluded():
    """換人公告列的 out_cnt 是上一個半局的殘值、pitcher_acnt 是**換下**的投手。

    實測例：第 7 局上開頭的換投列帶 out_cnt=2。若不排除，該半局會被誤判成
    「不是從 0 出局開始」而漏採計（保守方向），或投手歸屬被寫成前一位（危險方向）。
    """
    rows = [ev(1, "1", 0, 2, OTHER, change=True), *half(1)]
    halves = half_innings_of(rows, PID)

    assert len(halves) == 1
    assert halves[0].pitched_whole is True


def test_score_columns_read_as_prefix_max():
    """跑分欄以前綴最大值讀，換人列殘值不會讓得分被漏偵測。"""
    rows = half(1, runs=1) + [ev(2, "1", 0, 2, PID, change=True, away=0), *half(2, away=1)]
    halves = half_innings_of(rows, PID)

    assert halves[0].run_free is False
    assert halves[1].run_free is True


def test_half_inning_with_score_flag_but_no_delta_is_not_run_free():
    """只要有 is_score 事件就不算乾淨（兩個訊號取聯集，往中斷方向）。"""
    rows = [ev(1, "1", 1, 0), ev(1, "1", 2, 1, score=True), ev(1, "1", 3, 2)]
    halves = half_innings_of(rows, PID)

    assert halves[0].run_free is False


# --------------------------------------------------------------------------
# 顯示
# --------------------------------------------------------------------------

@pytest.mark.parametrize("outs,expected", [(0, 0.0), (1, 0.1), (2, 0.2), (3, 1.0), (85, 28.1)])
def test_outs_to_innings(outs, expected):
    assert outs_to_innings(outs) == expected
