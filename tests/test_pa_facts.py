"""UX-GAME-RECAP1：打席事實流 [plate appearance fact stream] 的紅燈與回歸測試。

本檔釘住 spike（`docs/research/INIT-GAME-RECAP/spike-report.md`）取得的四類語意保證——
每一類都是「canonical 打席路徑比 naive livelog 掃描正確」的具體證據，且都是實作最容易
退化回去的地方：

1. **錨點出局數**（spike §2.1 陷阱）：ΔRE24 的 RE(before) 必須用「終結事件**之前**」的
   出局數，且該值由 ``content`` 推導、不讀會落後的 ``out_cnt``。誤用 ``post_state.outs``
   會讓每個打席系統性偏移一個出局的 RE 差。
2. **突破僵局非打席**（spike §2.3，全季 49 筆）：``state='non_pa'`` 的佈局列不得產生
   ΔRE24，也不得被拿來當下一個打席的 after 錨點。
3. **記錄規則 9.15(b)**：代打接替後三振記給最初擊球員。
4. **打席中途代打不切界**：兩段碎片必須合成一個打席。

以及 fail-closed 的骨幹：任何打席要嘛有 ΔRE24、要嘛有封閉集合內的原因，不存在第三種
狀態（``test_no_unclassified_facts`` 以真實全季資料窮舉）。
"""

from __future__ import annotations

import psycopg
import pytest
from psycopg_pool import PoolClosed, PoolTimeout

from cpbl.models.pa_facts import (
    GARBAGE_TIME_MARGIN,
    UNAVAILABLE_REASONS,
    bases_key,
    build_game_facts,
    cache_directive,
    conclusion,
    delta_re24,
    game_shape,
    key_plays,
    mini_reconcile,
    pa_rows_from_snapshot,
    player_names,
    scoring_chain,
    snapshot_events,
)

# 真實 RE 矩陣值（2018-2025 / A；migration 既有，抄進測試以免測試依賴 DB）
RE = {
    ("___", 0): 0.5269, ("1__", 0): 0.8781, ("_2_", 0): 1.1625, ("__3", 0): 1.4601,
    ("12_", 0): 1.5899, ("1_3", 0): 1.8460, ("_23", 0): 2.1805, ("123", 0): 2.4814,
    ("___", 1): 0.2794, ("1__", 1): 0.5510, ("_2_", 1): 0.7270, ("__3", 1): 0.9678,
    ("12_", 1): 1.0124, ("1_3", 1): 1.2062, ("_23", 1): 1.4759, ("123", 1): 1.6457,
    ("___", 2): 0.1073, ("1__", 2): 0.2412, ("_2_", 2): 0.3508, ("__3", 2): 0.3835,
    ("12_", 2): 0.5003, ("1_3", 2): 0.5580, ("_23", 2): 0.6347, ("123", 2): 0.8372,
}


def ev(no: int, hitter: str | None, *, inning: int = 1, half: str = "1",
       pitcher: str = "P1", pitch_cnt: int | None = 1, action: str = "",
       content: str = "", change: bool = False, is_strike: bool = False,
       is_ball: bool = False, out: int = 0, order: int = 1, balls: int = 0,
       strikes: int = 0, away: int = 0, home: int = 0, hitter_name: str | None = None,
       pitcher_name: str = "投手甲", b1: str | None = None, b2: str | None = None,
       b3: str | None = None) -> dict:
    """合成 livelog 事件列（欄位語意對齊 cpbl.game_livelog）。"""
    return {
        "main_event_no": f"{no:010d}", "inning_seq": inning, "visiting_home_type": half,
        "batting_order": order, "out_cnt": out, "ball_cnt": balls, "strike_cnt": strikes,
        "pitch_cnt": pitch_cnt, "content": content, "action_name": action,
        "batting_action_name": "", "hitter_acnt": hitter,
        "hitter_name": hitter_name or (f"打者{hitter}" if hitter else None),
        "pitcher_acnt": pitcher, "pitcher_name": pitcher_name,
        "first_base": b1, "second_base": b2, "third_base": b3,
        "is_strike": is_strike, "is_ball": is_ball, "is_score": False,
        "is_change_player": change, "is_special_event": False,
        "visiting_score": away, "home_score": home,
    }


def facts_of(events: list[dict], *, season: int = 2026, kind: str = "A",
             sno: int = 1) -> list[dict]:
    """合成事件 → canonical 打席 → 事實流（走與生產完全相同的兩支純函式）。"""
    rows, _ = pa_rows_from_snapshot(season, kind, sno, events)
    return delta_re24(rows, events, RE)


# ===========================================================================
# 1. 錨點出局數：content 推導 vs out_cnt 落後
# ===========================================================================
def test_delta_re24_uses_outs_before_terminal_event():
    """飛球接殺（0 出、空壘 → 1 出、空壘）的 ΔRE24 必須是 RE(___,1) − RE(___,0)。

    錯誤實作（用終結事件**之後**的出局數當 RE(before)）會得到 0.0——這正是 spike 第一版
    踩到的坑，全場每個打席偏移 +0.2475。
    """
    events = [
        ev(1, "H1", action="飛球接殺", content="擊出高飛球，飛球接殺出局。 1人出局。",
           is_strike=True),
        ev(2, "H2", action="一壘安打", content="擊出一壘安打。", out=1, order=2,
           is_strike=True),
    ]
    facts = facts_of(events)
    assert facts[0]["result_action"] == "飛球接殺"
    # RE(after)=下一打席打席前(空壘,1出)=0.2794；RE(before)=(空壘,0出)=0.5269
    assert facts[0]["delta_re24"] == pytest.approx(0.2794 - 0.5269, abs=1e-4)
    assert facts[0]["delta_re24"] < 0


def test_outs_come_from_content_not_stale_out_cnt():
    """``out_cnt`` 落後時（實測全庫 0.653% 事件），錨點仍須由 ``content`` 推導。

    本例第二個打席的 ``out_cnt`` 仍寫 0（落後），但前一列 content 已宣告 1 人出局。
    """
    stale = [
        ev(1, "H1", action="刺殺", content="打者-三壘手 傳一壘手刺殺出局。 1人出局。",
           is_strike=True),
        ev(2, "H2", action="飛球接殺", content="飛球接殺出局。 2人出局。", out=0,  # 落後
           order=2, is_strike=True),
        ev(3, "H3", action="一壘安打", content="擊出一壘安打。", out=2, order=3, is_strike=True),
    ]
    facts = facts_of(stale)
    # 第二個打席：RE(before) 必須是 (空壘,1出)=0.2794，不是被 out_cnt 誤導的 (空壘,0出)
    assert facts[1]["delta_re24"] == pytest.approx(0.1073 - 0.2794, abs=1e-4)


def test_half_inning_last_pa_anchors_to_zero():
    """半局最後一個打席的 RE(after)=0（再見局依慣例歸零、得分照記）。"""
    events = [
        ev(1, "H1", action="刺殺", content="1人出局。", is_strike=True),
        ev(2, "H2", action="刺殺", content="2人出局。", out=1, order=2, is_strike=True),
        ev(3, "H3", action="刺殺", content="3人出局。", out=2, order=3, is_strike=True),
        ev(4, "V1", inning=1, half="2", action="一壘安打", content="擊出一壘安打。",
           order=1, is_strike=True),
    ]
    facts = facts_of(events)
    assert facts[2]["delta_re24"] == pytest.approx(0.0 - 0.1073, abs=1e-4)


# ===========================================================================
# 2. 突破僵局：非打席，不得產生 ΔRE24，也不得當 after 錨點
# ===========================================================================
def test_tiebreak_runner_is_not_a_plate_appearance():
    """``突破僵局上壘`` 是 ``non_pa``：naive 路徑會記給該跑者 +0.6356，canonical 必須排除。

    ΔRE24(naive 誤算) = RE(_2_,0) − RE(___,0) = 1.1625 − 0.5269 = 0.6356
    （2026/A 全季 49 筆，是 `batter_re24` 現存偏差的來源；見 #94）。
    """
    events = [
        ev(1, "R1", inning=10, action="突破僵局上壘", content="突破僵局上二壘。",
           pitch_cnt=None, order=2),
        ev(2, "H9", inning=10, action="一壘安打", content="擊出一壘安打。1分打點。",
           order=3, b2="R1", is_strike=True, away=1),
    ]
    facts = facts_of(events)
    tiebreak = [f for f in facts if f["result_action"] == "突破僵局上壘"]
    assert len(tiebreak) == 1
    assert tiebreak[0]["state"] == "non_pa"
    assert tiebreak[0]["delta_re24"] is None
    assert tiebreak[0]["unavailable_reason"] == "pa_state_non_pa"
    assert not any(abs(f["delta_re24"] or 0) == pytest.approx(0.6356, abs=1e-3) for f in facts)


def test_tiebreak_row_is_not_used_as_after_anchor():
    """佈局列的快照在跑者上壘**前**（壘位恆空），拿來當 after 錨點會低估延長局開局。"""
    events = [
        ev(1, "H1", inning=9, action="刺殺", content="3人出局。", out=2, is_strike=True),
        ev(2, "R1", inning=10, action="突破僵局上壘", content="突破僵局上二壘。",
           pitch_cnt=None, order=2),
        ev(3, "H2", inning=10, action="刺殺", content="1人出局。", order=3, b2="R1",
           is_strike=True),
    ]
    facts = facts_of(events)
    tenth = [f for f in facts if f["inning"] == 10 and f["state"] == "ready"]
    assert tenth[0]["bases_before"] == ["2"]  # 錨點吃到真正的二壘有人狀態


# ===========================================================================
# 3./4. 記錄規則 9.15(b) 與打席中途代打合併
# ===========================================================================
def test_pinch_hitter_strikeout_charged_to_original_batter():
    """9.15(b)：擊球員 2 好球後退出、替代者以三振完成 → 記為**最初擊球員**的三振。"""
    events = [
        ev(1, "H1", is_strike=True, strikes=1, pitch_cnt=1, action="三振"),
        ev(2, "H1", is_strike=True, strikes=2, pitch_cnt=2, action="三振"),
        ev(3, None, change=True, content="更換代打：H1=>H2。", pitch_cnt=None, action=""),
        ev(4, "H2", is_strike=True, strikes=3, pitch_cnt=3, action="三振",
           content="揮棒落空。 打者出局-三振出局。 1人出局。", balls=0),
    ]
    facts = facts_of(events)
    assert len(facts) == 1, "打席中途換代打不得切成兩個打席"
    assert facts[0]["hitter"]["player_id"] == "H1"      # 記錄歸屬
    assert facts[0]["end_hitter"]["player_id"] == "H2"  # 實際完成者


def test_mid_pa_pinch_hit_is_one_plate_appearance():
    """打者變化 ≠ 打席變化：同 ``batting_order`` 且球數未回退 → 合併為一個打席。"""
    events = [
        ev(1, "H1", is_strike=True, strikes=1, pitch_cnt=1, action="一壘安打"),
        ev(2, "H1", is_ball=True, balls=1, strikes=1, pitch_cnt=2, action="一壘安打"),
        ev(3, "H2", is_strike=True, balls=1, strikes=2, pitch_cnt=3, action="一壘安打",
           content="擊出一壘安打。"),
    ]
    facts = facts_of(events)
    assert len(facts) == 1
    assert facts[0]["delta_re24"] is not None


# ===========================================================================
# fail closed：封閉原因集合，不存在第三種狀態
# ===========================================================================
def test_every_fact_is_either_scored_or_has_a_known_reason():
    events = [
        ev(1, "H1", action="飛球接殺", content="1人出局。", is_strike=True),
        ev(2, "R1", inning=10, action="突破僵局上壘", content="突破僵局上二壘。",
           pitch_cnt=None, order=2),
        ev(3, "H2", inning=10, action="", content="牽制。", pitch_cnt=None, order=3),
    ]
    for fact in facts_of(events):
        assert (fact["delta_re24"] is None) != (fact["unavailable_reason"] is None)
        if fact["unavailable_reason"] is not None:
            assert fact["unavailable_reason"] in UNAVAILABLE_REASONS


# ===========================================================================
# 關鍵打席：|ΔRE24| 排序 → 時間序呈現；垃圾時間降飽和不剔除
# ===========================================================================
def _fact(index: int, delta: float | None, *, inning: int = 1, garbage: bool = False) -> dict:
    return {"pa_index": index, "delta_re24": delta, "state": "ready", "inning": inning,
            "half": "1", "garbage_time": garbage, "runs_on_play": 0,
            "hitter": {"player_id": "H", "name": "打者"}, "result_action": "一壘安打",
            "outs_before": 0, "bases_before": [], "pa_id": None,
            "start_event_no": None, "end_event_no": None}


def test_key_plays_ranked_by_abs_delta_but_returned_in_time_order():
    facts = [_fact(0, 0.4), _fact(1, -1.9), _fact(2, 0.05), _fact(3, 1.2), _fact(4, None)]
    picked = key_plays(facts, limit=3)
    assert [f["pa_index"] for f in picked] == [0, 1, 3]  # 取 |Δ| 前三後回到時間序


def test_key_plays_keep_garbage_time_plays():
    """分差 ≥7 的打席**降飽和呈現、不剔除、不加權**（v1.3 排序契約紅線）。"""
    facts = [_fact(0, 0.4), _fact(1, 1.8, garbage=True)]
    picked = key_plays(facts, limit=5)
    assert [f["pa_index"] for f in picked] == [0, 1]
    assert picked[1]["garbage_time"] is True


def test_garbage_time_flag_uses_pre_pa_margin():
    """分差看的是**打席前**的比分：前一個打席把分數拉開，下一個打席才進垃圾時間。"""
    events = [
        ev(1, "H0", inning=1, half="2", action="全壘打", content="擊出全壘打。",
           is_strike=True, home=GARBAGE_TIME_MARGIN),
        ev(2, "H1", inning=2, action="一壘安打", content="擊出一壘安打。", is_strike=True,
           away=0, home=GARBAGE_TIME_MARGIN),
    ]
    facts = facts_of(events)
    assert facts[0]["garbage_time"] is False   # 造成分差的那一打席本身還不是垃圾時間
    assert facts[1]["garbage_time"] is True


def test_scores_come_from_event_stream_not_pre_state():
    """單一事件就結束的得分打席：`pre_state` 存的比分已是得分**後**的值，不可當打席前比分。"""
    events = [ev(1, "H1", action="全壘打", content="擊出全壘打。1分打點。",
                 is_strike=True, away=1)]
    fact = facts_of(events)[0]
    assert (fact["away_score_before"], fact["home_score_before"]) == (0, 0)
    assert (fact["away_score_after"], fact["home_score_after"]) == (1, 0)


# ===========================================================================
# 事實句：分支門檻（需求方裁決 Q1）與再見場的負 ΔRE24
# ===========================================================================
def test_game_shape_thresholds():
    facts = [_fact(0, 0.5)]
    assert game_shape(facts, 5, 0) == "blowout"      # 分差 5
    assert game_shape(facts, 4, 0) == "regular"      # 分差 3–4 走中性句
    assert game_shape(facts, 2, 0) == "close"        # 分差 ≤2
    assert game_shape(facts, 3, 3) == "tie"


def test_walkoff_conclusion_uses_last_pa_not_max_delta():
    """再見打席的 ΔRE24 是**負值**（半局結束使 RE(after)=0），永遠上不了 |ΔRE24| 排行。

    故結論行必須以「賽果事實」取最後一個打席，不能沿用 key_plays 的首位——
    這是 brief 把①結論行與②關鍵打席分開的理由（spike §6.1 發現 1）。
    """
    big = _fact(0, 1.87, inning=4)
    walkoff = _fact(1, -0.16, inning=9)
    walkoff["half"] = "2"
    walkoff["result_action"] = "一壘安打"
    walkoff["hitter"] = {"player_id": "W", "name": "再見打者"}
    out = conclusion([big, walkoff], home_score=7, away_score=6,
                     home_name="主隊", away_name="客隊")
    assert out["shape"] == "walkoff"
    assert "再見打者" in out["sentence"]
    assert "再見致勝" in out["sentence"]


def test_conclusion_falls_back_to_score_only_without_facts():
    out = conclusion([], home_score=3, away_score=1, home_name="主隊", away_name="客隊")
    assert out["shape"] == "score_only"
    assert out["sentence"] == "主隊 3：1 客隊。"


def test_blowout_without_inning_runs_degrades_to_regular():
    """講不出「最大單局」時退中性句，**不編一個出來**。"""
    out = conclusion([_fact(0, 1.5)], home_score=9, away_score=0,
                     home_name="主隊", away_name="客隊", inning_runs={})
    assert out["shape"] in ("blowout", "regular")
    assert "{" not in out["sentence"]


def test_sentences_contain_no_fan_nicknames():
    """recap 正式文案禁球迷暱稱（brief 非目標）。"""
    from cpbl.models.pa_facts import SENTENCE_TEMPLATES
    banned = ("龍龍", "爪爪", "喵喵", "邦邦", "吱吱", "啾啾", "魯閣", "煮粥", "劇場", "問天")
    for template in SENTENCE_TEMPLATES.values():
        assert not any(word in template for word in banned)


# ===========================================================================
# 得分半局鏈
# ===========================================================================
def test_scoring_chain_only_lists_halves_with_runs():
    events = [
        ev(1, "H1", action="刺殺", content="1人出局。", is_strike=True),
        ev(2, "H2", action="全壘打", content="擊出全壘打。1分打點。", out=1, order=2,
           is_strike=True, away=1),
        ev(3, "V1", inning=1, half="2", action="刺殺", content="1人出局。", is_strike=True),
    ]
    chain = scoring_chain(facts_of(events))
    assert [(c["inning"], c["half"], c["runs"]) for c in chain] == [(1, "1", 1)]
    assert chain[0]["plays"][0]["result_action"] == "全壘打"


def test_scoring_chain_plays_carry_pre_play_score():
    """得分標示元件要算「得分後變成幾比幾」，故每筆得分打席須帶打席前比分與半局。

    三處逐列呈現（逐打席頁籤／關鍵打席／得分過程）共用同一個元件，缺這幾欄會讓得分過程
    只能顯示分數而顯示不出比分，形式就不一致了。
    """
    events = [
        ev(1, "H1", action="全壘打", content="擊出全壘打。1分打點。", is_strike=True, away=1),
    ]
    play = scoring_chain(facts_of(events))[0]["plays"][0]
    assert play["half"] == "1"
    assert play["runs"] == 1
    # 得分後比分直接取終結事件的事件後快照——首球全壘打的起始列即終結列，
    # 用「打席前比分 + 進帳分數」推算會多加一次。
    assert play["away_score_after"] == 1
    assert play["home_score_after"] == 0


# ===========================================================================
# snapshot 正規化與 mini 對帳閘門
# ===========================================================================
def snap_row(event: dict) -> dict:
    """把合成的 DB 事件轉成 snapshot 的官方 payload 形狀（旗標為字串 "0"/"1"）。"""
    return {
        "MainEventNo": event["main_event_no"], "InningSeq": event["inning_seq"],
        "VisitingHomeType": event["visiting_home_type"], "BattingOrder": event["batting_order"],
        "OutCnt": event["out_cnt"], "BallCnt": event["ball_cnt"],
        "StrikeCnt": event["strike_cnt"], "PitchCnt": event["pitch_cnt"],
        "Content": event["content"], "ActionName": event["action_name"],
        "BattingActionName": "", "HitterAcnt": event["hitter_acnt"],
        "HitterName": event["hitter_name"], "PitcherAcnt": event["pitcher_acnt"],
        "PitcherName": event["pitcher_name"],
        "FirstBase": event["first_base"] or "", "SecondBase": event["second_base"] or "",
        "ThirdBase": event["third_base"] or "",
        "IsStrike": "1" if event["is_strike"] else "0",
        "IsBall": "1" if event["is_ball"] else "0",
        "IsChangePlayer": "1" if event["is_change_player"] else "0",
        "IsSpecialEvent": "0",
        "VisitingScore": event["visiting_score"], "HomeScore": event["home_score"],
    }


def make_snapshot(events: list[dict], *, phase: str = "final", away: int = 1,
                  home: int = 0, duplicate_last: bool = False) -> dict:
    rows = [snap_row(e) for e in events]
    if duplicate_last and rows:
        rows.append(dict(rows[-1]))
    return {"phase": phase, "livelog": rows,
            "away": {"score": away, "inning_score": []},
            "home": {"score": home, "inning_score": []}}


SCORED = [
    ev(1, "H1", action="全壘打", content="擊出全壘打。1分打點。", is_strike=True, away=1),
    ev(2, "H2", action="刺殺", content="1人出局。", order=2, is_strike=True, away=1),
]


def test_snapshot_string_flags_are_coerced():
    """官方旗標是字串 ``"0"``（truthy）；不轉型會讓每一列都被當換人列、PA 數歸零。"""
    events = snapshot_events(make_snapshot(SCORED))
    assert all(e["is_change_player"] is False for e in events)
    rows, _ = pa_rows_from_snapshot(2026, "A", 1, events)
    assert len(rows) == 2


def test_snapshot_deduplicates_repeated_last_event():
    """官方 LiveLog 末列可能重複（實測 2026/A/241）。"""
    events = snapshot_events(make_snapshot(SCORED, duplicate_last=True))
    assert len(events) == len(SCORED)


def test_mini_reconcile_passes_on_consistent_snapshot():
    snapshot = make_snapshot(SCORED, away=1, home=0)
    events = snapshot_events(snapshot)
    _, pas = pa_rows_from_snapshot(2026, "A", 1, events)
    assert mini_reconcile(snapshot, events, pas) == (True, None)


def test_mini_reconcile_rejects_non_final_phase():
    snapshot = make_snapshot(SCORED, phase="live", away=1)
    events = snapshot_events(snapshot)
    _, pas = pa_rows_from_snapshot(2026, "A", 1, events)
    assert mini_reconcile(snapshot, events, pas) == (False, "phase_not_final")


def test_mini_reconcile_rejects_score_mismatch():
    snapshot = make_snapshot(SCORED, away=9, home=0)
    events = snapshot_events(snapshot)
    _, pas = pa_rows_from_snapshot(2026, "A", 1, events)
    ok, reason = mini_reconcile(snapshot, events, pas)
    assert (ok, reason) == (False, "score_mismatch")


def test_mini_reconcile_rejects_missing_ball_strike_flags():
    """缺 IsBall/IsStrike 時 ``pinch_hit_slot`` 佐證會退化成無條件合併 → fail closed。"""
    snapshot = make_snapshot(SCORED, away=1)
    for row in snapshot["livelog"]:
        row.pop("IsBall")
        row.pop("IsStrike")
    events = snapshot_events(snapshot)
    _, pas = pa_rows_from_snapshot(2026, "A", 1, events)
    assert mini_reconcile(snapshot, events, pas) == (False, "missing_ball_strike_flags")


def test_mini_reconcile_rejects_half_inning_out_violation():
    """任一半局的打者出局 PA > 3 → 整場不可信（pa_build 既有不變式）。"""
    events = [ev(i, f"H{i}", action="刺殺", content=f"{min(i,3)}人出局。", order=i,
                 out=min(i - 1, 2), is_strike=True) for i in range(1, 6)]
    snapshot = make_snapshot(events, away=0, home=0)
    parsed = snapshot_events(snapshot)
    _, pas = pa_rows_from_snapshot(2026, "A", 1, parsed)
    ok, reason = mini_reconcile(snapshot, parsed, pas)
    assert (ok, reason) == (False, "half_inning_out_violation")


def test_snapshot_and_db_paths_agree_on_synthetic_game():
    """同一份事件走「snapshot 正規化」與「直接 DB 欄位」兩條路，事實流必須逐值相同。

    這是 spike §5.2「當晚與隔日零分歧」在單元層的替身。
    """
    snapshot = make_snapshot(SCORED, away=1)
    from_snapshot = facts_of(snapshot_events(snapshot))
    from_db_shape = facts_of(SCORED)
    keys = ("pa_index", "state", "hitter", "result_action", "delta_re24", "runs_on_play")
    assert [{k: f[k] for k in keys} for f in from_snapshot] == \
           [{k: f[k] for k in keys} for f in from_db_shape]


# ===========================================================================
# 姓名解析：逐場來源優先，不依賴 cpbl.players
# ===========================================================================
def test_player_names_come_from_game_source():
    names = player_names(SCORED)
    assert names["H1"] == "打者H1"
    assert names["P1"] == "投手甲"


def test_bases_key_normalises_occupancy():
    assert bases_key(["1", "3"]) == "1_3"
    assert bases_key([]) == "___"
    assert bases_key(None) == "___"


# ===========================================================================
# 快取指令（設計稿 §8）
# ===========================================================================
def test_cache_directive_is_short_for_provisional():
    directive = cache_directive({"source": "provisional", "season": 2026})
    assert "s-maxage=60" in directive


def test_cache_directive_is_long_for_historical_authoritative():
    from datetime import date
    directive = cache_directive(
        {"source": "authoritative", "season": 2024, "game_date": date(2024, 5, 1)},
        today=date(2026, 8, 6))
    assert "immutable" in directive


def test_cache_directive_is_medium_for_current_season():
    from datetime import date
    directive = cache_directive(
        {"source": "authoritative", "season": 2026, "game_date": date(2026, 8, 5)},
        today=date(2026, 8, 6))
    assert "s-maxage=3600" in directive


# ===========================================================================
# 真實資料回歸：未歸類 = 0（需要 DB；無 DB 時 skip）
# ===========================================================================
def _season_games() -> list[tuple[int, str, int]]:
    from cpbl.db import conn
    with conn() as connection:
        cur = connection.cursor()
        cur.execute(
            "SELECT DISTINCT pa.year, pa.kind_code, pa.game_sno "
            "FROM cpbl.game_plate_appearances pa "
            "JOIN cpbl.game_recap_builds b USING (build_id) "
            "WHERE b.state='published' AND pa.year=%s AND pa.kind_code='A' "
            "ORDER BY 3 DESC LIMIT 40", (2026,))
        return [(r[0], r[1], r[2]) for r in cur.fetchall()]


@pytest.fixture(scope="module")
def db_games() -> list[tuple[int, str, int]]:
    try:
        games = _season_games()
    except (psycopg.Error, PoolClosed, PoolTimeout, OSError) as exc:
        pytest.skip(f"無 DB：{type(exc).__name__}")
    if not games:
        pytest.skip("DB 無 published PA build")
    return games


def test_no_unclassified_facts(db_games):
    """真實場次窮舉：每個打席要嘛有 ΔRE24、要嘛有封閉集合內的原因，沒有第三種狀態。

    這是 spike「2026/A 全季逐打席窮舉歸類，未歸類 = 0」帶進生產碼的回歸形式。
    """
    unclassified: list[tuple] = []
    for season, kind, sno in db_games:
        payload = build_game_facts(season, kind, sno)
        assert payload["render_state"] == "authoritative", (season, kind, sno)
        for fact in payload["plate_appearances"]:
            scored = fact["delta_re24"] is not None
            reason = fact["unavailable_reason"]
            if scored == (reason is not None):
                unclassified.append((sno, fact["pa_index"], "both_or_neither"))
            elif reason is not None and reason not in UNAVAILABLE_REASONS:
                unclassified.append((sno, fact["pa_index"], reason))
    assert not unclassified, f"未歸類打席：{unclassified[:10]}"


def test_tiebreak_rows_never_scored_on_real_games(db_games):
    """真實資料上再確認一次：``non_pa`` 一筆都不得帶 ΔRE24（`batter_re24` 的病灶）。"""
    for season, kind, sno in db_games:
        for fact in build_game_facts(season, kind, sno)["plate_appearances"]:
            if fact["state"] == "non_pa":
                assert fact["delta_re24"] is None, (sno, fact["pa_index"])


def test_key_plays_are_subset_of_facts_and_time_ordered(db_games):
    for season, kind, sno in db_games:
        payload = build_game_facts(season, kind, sno)
        indexes = [f["pa_index"] for f in payload["key_plays"]]
        assert indexes == sorted(indexes)
        assert len(indexes) <= 5
        known = {f["pa_index"] for f in payload["plate_appearances"]}
        assert set(indexes) <= known
