"""連續無自責分局數（ML-PITCHER-SCORELESS1）：保守性紅線的釘子。

這些測試釘的是「**不確定一律往中斷／不採計解讀**」。任何一條轉綠成「多算一局」
都代表演算法開始高估，即違反卡面紅線 2。純函式測試不需要 DB。
"""

from __future__ import annotations

from datetime import date

import pytest

from cpbl.models.scoreless_streak import (
    BREAK_EARNED_RUN,
    BREAK_MISSING_LINE,
    BREAK_POSTSEASON_EARNED_RUN,
    BREAK_SUSPENDED,
    SUSPENDED,
    Appearance,
    compute_streak,
    half_innings_of,
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
    """走完所有可得出賽仍未中斷 → 必須標示受資料邊界限制（紅線 4，不得沉默截斷）。"""
    res = compute_streak([app(1, 0), app(2, 0)])

    assert res.boundary_limited is True
    assert res.break_reason is None


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

def _tail_of(rows: list[dict], official_outs: int = 99, pitcher: str = PID):
    halves = half_innings_of(rows, pitcher)
    mine = {(r["inning_seq"], r["visiting_home_type"]) for r in rows
            if not r["is_change_player"] and r["pitcher_acnt"] == pitcher}
    return tail_credit((2026, "A", 1), halves, mine, official_outs)


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


def test_tail_clamped_by_official_outs():
    """livelog 若異常給出比官方更多的出局數，以官方為上限夾擠。"""
    rows = half(1, runs=1) + half(2, away=1) + half(3, away=1) + half(4, pitcher=OTHER, away=1)
    tail = _tail_of(rows, official_outs=4)

    assert tail.outs == 4 and tail.clamped is True


def test_tail_feeds_into_the_streak():
    rows = half(1, runs=1) + half(2, away=1) + half(3, pitcher=OTHER, away=1)
    res = compute_streak([app(1, 1, outs=6), app(2, 0), app(3, 0)],
                         tail_lookup=lambda a: _tail_of(rows, 6))

    assert res.strict_outs == 6 and res.outs == 9


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
