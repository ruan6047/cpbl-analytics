"""ML-PITCHER-ER-REBUILD1：從 `cpbl.game_livelog` 逐事件重建每位投手每場的
自責分（earned runs）、失分（runs）與出局數（outs），並與官方 `cpbl.pitching_gamelog`
**三維對帳**。

本卡是**可行性評估**：唯一要回答的問題是「逐場對帳通過率是多少」。
對帳維度於 iteration 2 由兩維（ER＋outs）擴為三維（＋runs）：實測有 15 場
逐投手失分與官方不符、卻因 ER 與 outs 剛好都吻合而通過兩維對帳。
故本檔只讀 DB、只寫 JSON 到本目錄，不改任何既有模組、不寫任何表。

證明策略（與 ML-PITCHER-SCORELESS1 前七輪不同）
------------------------------------------------
前七輪都在「結構性地證明 livelog 完整」，全部被反例打穿。本檔**不證明完整性**：
重建 → 與官方逐場值對帳 → 不一致的場次 fail-closed 排除並分類成因。
對得上的場次，就是 livelog 對該場**足夠**的證明。

規則依據一律標出處，見同目錄 RESULTS.md §1（9.16 逐條核對）。
PA 切界／半局出局數／outcome 分類**沿用 canonical `cpbl.ingest.pa_build`**，
不另寫一套（避免語意漂移；GLOSSARY「island」「PA 的 outs」）。

`--check` 的語意：**分辨「我算錯了」與「母體長大了」**，不是凍結數字
--------------------------------------------------------------------
母體每天長大（官網爬蟲排程 10:10 補前一日），這是**正常狀態不是缺陷**——
canonical `templates/statistical-redline.md` 第 9 條：「母體隨資料新增而變動是正常
狀態，不是缺陷：處置為**標注 as-of**，**不設法凍結數字**，也不得把漂移讀成錯誤。」

iteration 1–6 的 `--check` 只做全文字比對，不符即 `MISMATCH` 退出 1。它因此把
**兩件性質完全不同的事**壓成同一個紅燈：

* **母體漂移**（input drift）：新比賽入庫，數字跟著變。**這是正常的**，報告數字
  本來就該隨母體走。R1 跨家族查核的紅燈就是這一類（4,259→4,264→4,261）。
* **重建邏輯改變**：來源指紋一模一樣，數字卻不同 ⇒ 真的算錯了或被改壞了。

現在 `--check` 先比 `data_asof` 的來源指紋，再判定屬於哪一類，並**列出漂移量**：

    exit 0  REPRODUCED   指紋與數字都相同
    exit 2  INPUT_DRIFT  來源指紋已變（列出各來源與各主要數字的變動量）
    exit 1  LOGIC_MISMATCH  來源指紋相同、數字卻不同 ⇒ 真正的退步，必須查

`--as-of` 是**驗證工具，不是報告數字的凍結**：它把母體限定在 `game_date <= as_of`，
讓兩次不同時間的執行可以在同一母體上對照，用來回答「數字變動是不是純粹來自新增
比賽」。**產生 artifact 的預設路徑不帶界線**——報告數字照實隨母體走並標注 as-of。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from cpbl.ingest.pa_build import (  # noqa: E402
    build_islands,
    classify_island,
    derive_half_inning_outs,
    event_sort_key,
    load_taxonomy,
)

DSN = os.environ.get("DATABASE_URL", "postgresql://cpbl:cpbl@localhost:5433/cpbl")

EVENT_COLS = (
    "year, kind_code, game_sno, main_event_no, inning_seq, visiting_home_type, "
    "batting_order, out_cnt, ball_cnt, strike_cnt, pitch_cnt, content, action_name, "
    "batting_action_name, hitter_acnt, hitter_name, pitcher_acnt, pitcher_name, "
    "first_base, second_base, third_base, is_strike, is_ball, is_score, "
    "is_change_player, is_special_event, visiting_score, home_score"
)

# ---------------------------------------------------------------------------
# 規則常數（出處見 RESULTS.md §1）
# ---------------------------------------------------------------------------

# 9.16(a)：自責分之因素 — 安打、犧牲觸擊、犧牲飛球、盜壘、刺殺、野手選擇、
# 四壞球、觸身球、投手犯規、暴投。故 hit/walk/hbp/sacrifice/fielders_choice 皆
# earned-eligible。
EARNED_ELIGIBLE_FAMILIES = frozenset(
    {"hit", "walk", "hbp", "sacrifice", "fielders_choice"}
)
# 9.16(b)(1)(2)(3) 與 9.16(a)【註 2】②：守備失誤、捕手／野手妨礙、妨礙跑壘、
# 捕逸、漏接界外飛球之失誤 — 均非自責分之因素。
UNEARNED_FAMILIES = frozenset({"reach_on_error", "interference"})
# 7.01(b)(2)(C)：延長賽每半局開始位於二壘的跑壘員「視為守備失誤上壘」。
TIEBREAK_FAMILY = "tiebreak_runner"

# 不死三振（uncaught_third_strike）依成因分流：
#   暴投 → 9.16(a) 明列暴投為自責分之因素（含「第 3 好球時暴投使擊球員佔於一壘」）
#   捕逸／捕手傳球失誤／趁傳 → 9.16(a)【註 2】② 非自責分之因素
U3K_EARNED_ACTIONS = frozenset({"不死三振 暴投"})

# 9.16(a)【註 2】② 的非自責分因素在 livelog 文字上的標記（暴投**不在其中**：
# 9.16(a) 明列暴投為自責分之因素）。用於 9.16(d)「藉失誤／捕逸／妨礙進壘」的偵測。
ERROR_MARKERS = ("失誤", "捕逸", "妨礙", "漏接")

# 得分敘述的完整樣態（實測全庫）：`N壘跑者<姓名>[ <進壘原因>]回本壘得分`。
# 原因欄實例：投手暴投 775／因野手失誤進壘 310／雙盜壘 114／捕手捕逸 88／投手犯規 72／
# 趁傳進壘 66／因<守位>失誤 …。**姓名與原因之間有空白**，早期版本的
# `[^\s，。,]+?` 會整條匹配失敗而把該分誤記到打者身上（2026/A/72 六局上實例）。
SCORE_RE = re.compile(r"([一二三])壘跑者\s*([^\s。，,]+)([^。]{0,30}?)回本壘得分")
# 打者自身踏本壘＝全壘打（含場內全壘打），由 island 的 taxonomy 分類判定
# （`"全壘打" in action`），**不用文字比對**——文字會被「全壘打牆前接殺」之類的
# 敘述誤命中。跑者的分一律由 SCORE_RE 涵蓋，打者靠其後打席回本壘的情形也會在
# 該打席以「N壘跑者…回本壘得分」出現。
# 進壘敘述（含得分）：用來逐跑者判定「這一次進壘是不是靠失誤」。**必須逐跑者**——
# 同一 play 上常有人靠安打推進、有人靠失誤多跑一個壘，整個 island 一起判會過度
# 保守（實測 er-1 從 11 漲到 23）。
ADVANCE_RE = re.compile(
    r"([一二三])壘跑者\s*([^\s。，,]+)([^。]{0,30}?)(?:回本壘得分|上[一二三]壘)"
)
PINCH_RUN_RE = re.compile(r"更換代跑[:：]\s*([^\s=]+?)\s*=>\s*([^\s。]+?)。")
BASE_CH = {"一": 1, "二": 2, "三": 3}
GAME_OVER_MARKERS = ("比賽結束",)

# 變異模式：用來證明「對帳通過」不是巧合，以及量測需求方逐字邏輯能走多遠。
#   full         ：本檔完整實作（9.16 全條 + 無失誤重建）
#   spec_literal ：需求方 2026-08-07 逐字邏輯的操作化（只看上壘手段 + 失誤致第三
#                  出局未成立），**不做 9.16(d) 的無失誤重建**
#   no_shadow    ：full 拿掉無失誤重建
#   no_inherit   ：full 拿掉 9.16(g) 的遺留跑者責任轉移
#   zero_er      ：**虛無對照**——自責分一律回 0。若 ER=0 出賽的通過率在此模式下
#                  仍然很高，代表該分層量到的其實只是出局數維度，不是自責分能力。
#   no_hr_fix    ：拿掉全壘打修正（消融，證明該修正的貢獻）
# 以下三個是**已被實測否證**的假設，保留以便重現否證證據，預設不啟用：
#   team_opps      ：出局機會改團隊制（＝不給後援投手 9.16(i) 的重設）
#   out_before_run ：5.08(a) 第三出局先於得分成立
#   maxtaint       ：失誤半局內所有壘上跑者一律非自責
#   no_tb_owner  ：拿掉突破僵局跑者的歸屬修正（消融）
#   no_scoreboard_signal：拿掉記分板 error_cnt 的獨立失誤訊號（消融）
#   no_unnarrated_check ：拿掉得分完整性檢查的**兩道**閘門（歷史消融，iteration 6
#                         為 +77、iteration 7 修正後為 +0，是「修正 vs 放寬」的基準案例）
# 逐閘門消融（iteration 8 補齊；每道 fail-closed 閘門一個，Δ 才歸得了因）：
#   no_unnarrated_run        ：只拿掉 deferred<0 的 `unnarrated_run`
#   no_narrated_run_not_scored：只拿掉 deferred>0 的 `narrated_run_not_scored`
#   no_scorer_unresolved     ：只拿掉「得分敘述指名的跑者對不到帳本」的閘門
#   wide_official_error_gate ：還原 `official_error_unlocated` **窄化前**的行為
#                              （不看該半局是否得分，一律整場排除）。窄化本身
#                              也要能被消融，否則「修正」與「放寬」分不開。
#   double_as_earned    ：把二壘安打當成「必然把污染跑者送回本壘」（反事實假設，
#                         條文無明文；用來量這個灰帶往哪個方向偏）
# 以下是**尚未採用的候選**（需求方 2026-08-07 裁定暫緩，僅供量測）：
#   walkoff_fix  ：再見判定改「末半局為下半且主隊獲勝」
MUTATIONS = (
    "full", "spec_literal", "no_shadow", "no_inherit", "zero_er", "no_hr_fix",
    "no_tb_owner", "no_scoreboard_signal", "no_unnarrated_check",
    "no_unnarrated_run", "no_narrated_run_not_scored", "no_scorer_unresolved",
    "wide_official_error_gate",
    "double_as_earned",
    "team_opps", "out_before_run",
    "maxtaint", "walkoff_fix",
)

# 逐閘門消融的對照表：`fail_reasons` 的閘門名 → 對應 mutation。
# 沒有對應 mutation 的閘門在 `gate_ablation.py` 以「為何不需要消融」逐道交代。
GATE_ABLATIONS: dict[str, str] = {
    "unnarrated_run": "no_unnarrated_run",
    "narrated_run_not_scored": "no_narrated_run_not_scored",
    "official_error_unlocated": "no_scoreboard_signal",
    "scorer_unresolved": "no_scorer_unresolved",
}


@dataclass
class Runner:
    """壘上跑者。`slot` ＝ livelog 壘包欄位的棒次槽（1-9），代跑接替同一槽 →
    9.16(a)「包含代跑者」的歸屬繼承自動成立。"""

    slot: str
    name: str
    owner: str  # 責任投手 acnt（9.16(g)）
    earned_ok: bool  # 上壘手段是否為自責分之因素


@dataclass
class GameResult:
    year: int
    kind_code: str
    game_sno: int
    ok: bool
    reason: str | None = None
    outs: dict[str, int] = field(default_factory=dict)
    runs: dict[str, int] = field(default_factory=dict)
    er: dict[str, int] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    detail: str | None = None
    # 閘門的結構化附註（供 `gate_ablation.py` 逐案分析用；不進 artifact JSON）
    gate_info: dict[str, Any] = field(default_factory=dict)


def _s(v: Any) -> str:
    return "" if v is None else str(v).strip()


def _slots(ev: dict[str, Any]) -> dict[int, str]:
    out: dict[int, str] = {}
    for base, col in ((1, "first_base"), (2, "second_base"), (3, "third_base")):
        v = _s(ev.get(col))
        if v:
            out[base] = v
    return out


def _forced_targets(shadow: dict[str, int], batter_reaches: bool) -> dict[str, int]:
    """重建世界的被迫進壘目標：打者上一壘時，一壘跑者被迫上二壘，依序推。"""
    if not batter_reaches:
        return {}
    occupied = {b: s for s, b in shadow.items()}
    targets: dict[str, int] = {}
    b = 1
    while b in occupied:
        targets[occupied[b]] = b + 1
        b += 1
    return targets


def _natural_batter_base(action: str, double_as_earned: bool = False) -> int:
    """打者在「無失誤重建世界」裡應到達的壘（不含失誤造成的額外進壘）。

    9.16(d)：藉失誤進壘者，若判斷無該失誤即無法得分，其得分不記自責分。實例
    `2026/A/4` 七局上：戴培峰**內野安打**上一壘、再「因游擊手傳一壘手失誤上二壘」，
    下一棒一壘安打送他回本壘 —— 官方判非自責分（無失誤時他只在一壘，一支一壘打
    回不了本壘）。若沿用觀測落點（二壘）就會誤判為自責分。
    """
    if "全壘打" in action:
        return 4
    if "三壘安打" in action:
        return 3
    if "二壘安打" in action:
        # 條文對二壘安打**沒有明文**：9.16(d)【註 1】①③ 的門檻是「三壘安打以上」、
        # ② 是「二壘以上」，兩者不同是因為**跑者在重建世界的壘位不同**，不是規則
        # 有兩套門檻（見 RESULTS.md §3.7 的逐例走查）。回 2＝「打者推進 2 個壘」，
        # 不等於「污染跑者必然得分」——壘位由跑者自己的 shadow base 決定。
        return 4 if double_as_earned else 2
    return 1


def _batting_score(ev: dict[str, Any], half: str) -> int | None:
    v = ev.get("visiting_score") if half == "1" else ev.get("home_score")
    return None if v is None else int(v)


# ---------------------------------------------------------------------------
# 單場重建
# ---------------------------------------------------------------------------


def rebuild_game(
    year: int, kind: str, sno: int, events: list[dict[str, Any]], taxonomy: Any,
    trace: bool = False, mutation: str = "full",
    official_errors: dict[tuple[int, str], int] | None = None,
    official_half_runs: dict[tuple[int, str], int] | None = None,
) -> GameResult:
    """`official_errors`：`{(inning_seq, livelog 半局別): 該半局守方失誤數}`。
    `official_half_runs`：`{(inning_seq, livelog 半局別): 該半局攻方得分}`（官方記分板）。

    來源 `cpbl.game_scoreboard.error_cnt`＝**該隊在該局所犯**的失誤數。
    半局對應要**翻轉** `visiting_home_type`：記分板的客隊（`'1'`）守的是**下半局**
    （livelog `'2'`）。此方向已用鑑別性檢定驗過——E>0 的半局裡，翻轉後有
    99.0% 的半局在逐球敘述找得到失誤性字樣，不翻轉只有 9.2%。
    """
    res = GameResult(year=year, kind_code=kind, game_sno=sno, ok=False)
    if not events:
        res.reason = "no_livelog"
        return res

    islands = build_islands(events)
    outs_by_event = derive_half_inning_outs(events)

    # --- 物化 island 摘要 ---------------------------------------------------
    summaries: list[dict[str, Any]] = []
    for isl in islands:
        ordered = sorted(isl, key=event_sort_key)
        non_change = [e for e in ordered if not e.get("is_change_player")]
        if not non_change:
            continue
        first, last = non_change[0], non_change[-1]
        cls = classify_island(ordered, taxonomy)
        half = _s(first.get("visiting_home_type"))
        inning = first.get("inning_seq")
        pre = outs_by_event.get(_s(first.get("main_event_no")), (None, None))[0]
        post = outs_by_event.get(_s(last.get("main_event_no")), (None, None))[1]
        pitchers = [_s(e.get("pitcher_acnt")) for e in non_change if _s(e.get("pitcher_acnt"))]
        summaries.append(
            {
                "half_key": (inning, half),
                "half": half,
                "inning": inning,
                "pre_outs": pre,
                "post_outs": post,
                "pre_slots": _slots(first),
                "pitchers": pitchers,
                "action": cls.result_action,
                "family": cls.outcome_family,
                "island_class": cls.island_class,
                "state": cls.state,
                "hitter_name": _s(last.get("hitter_name")) or _s(first.get("hitter_name")),
                "text": "\n".join(_s(e.get("content")) for e in ordered),
                # 得分欄取 island 內**所有**列的最大值（含公告列）：實測得分事件列
                # 本身有時尚未反映該分，要到下一列才更新。比分單調，取 max 安全。
                #
                # ⚠️ 取 max **只涵蓋 island 內部的延後**。延後會跨 island（見下方
                # 「延後比分的跨 island 對齊」），此處不可能靠 max 解決——指標案例
                # `2026/A/81` 三局下的犧牲飛球 island 只有**一列**，island 內無下一列。
                "score": max(
                    (
                        v
                        for v in (_batting_score(e, half) for e in ordered)
                        if v is not None
                    ),
                    default=None,
                ),
                # 該 island 實際被歸屬的得分數，由下方「得分歸屬與完整性」填入
                "runs": 0,
                "game_over": any(
                    m in _s(e.get("content")) for e in ordered for m in GAME_OVER_MARKERS
                ),
                "ball": last.get("ball_cnt"),
                "strike": last.get("strike_cnt"),
            }
        )

    if not summaries:
        res.reason = "no_usable_island"
        return res

    # --- 得分歸屬與完整性：敘述定「哪一個 play」、比分欄定「共幾分」（R1-001）---
    # livelog 的比分欄**落後於敘述**：得分敘述已寫在某一列，比分欄要到其後某一列
    # 才更新，而**延後會跨 island**。iteration 1–6 直接用 `本 island 比分 −
    # 前一 island 比分` 當作該 island 的得分數，等於假設「更新落在同一個 island」。
    # 指標案例 `2026/A/81` 三局下打穿該假設：
    #
    #   0320019000（劉基鴻，**單列 island**）犧牲飛球，content 已寫
    #                「三壘跑者郭天信回本壘得分」，home_score 仍為 2
    #   0320021000（朱育賢，下一個 island 的首列）無任何得分敘述，home_score 變 3
    #
    # 後果是雙重的：完整性檢查在朱育賢那個 island 看到「分數 +1、敘述 0」判
    # `unnarrated_run` 整場排除；就算放行，主迴圈在劉基鴻那個 island 也會得到
    # `island_runs=0` 卻有 1 位具名跑者，落入 `run_count_mismatch`。
    #
    # 修法是**改分工**，不是改門檻：
    #   * **哪一個 play 得分** → 由敘述決定（具名跑者 ＋ 打者自己踏本壘＝全壘打）。
    #     全壘打以 island 的 taxonomy 分類判定，不用文字比對——文字比對會被
    #     「全壘打牆前接殺」之類的敘述誤命中。
    #   * **總共幾分** → 仍由比分欄決定，但改成**逐側累計對帳**而非逐 island 相減。
    #
    # 比分欄只會落後不會超前，故不變量是：任一時點「比分已累計的分」不得超過
    # 「敘述已交代的分」。`deferred` ＝ 敘述已交代但比分尚未反映的分：
    #   deferred < 0 ⇒ 有一分進了比分卻沒人描述 ⇒ `unnarrated_run`（原閘門，
    #                  指標案例 `2021/A/208` 九局下仍照樣被擋）
    #   終局 deferred > 0 ⇒ 敘述交代的分比分數欄多 ⇒ `narrated_run_not_scored`
    # 兩者都 fail-closed。**不得猜那個 play 是什麼**（捕逸？失誤？妨礙？）。
    def _narrated(isl: dict[str, Any]) -> int:
        return len(SCORE_RE.findall(isl["text"])) + (
            1 if "全壘打" in (isl["action"] or "") else 0
        )

    by_side: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for isl in summaries:
        by_side[isl["half"]].append(isl)
    final_score: dict[str, int] = {"1": 0, "2": 0}
    for side, side_islands in by_side.items():
        prev_sc = 0
        deferred = 0
        for isl in side_islands:
            sc = isl["score"]
            if sc is None:
                res.reason = "null_score"
                res.detail = (
                    f"i{isl['inning']}/{isl['half']} {isl['action']} "
                    f"pre={isl['pre_slots']}"
                )
                return res
            gained = sc - prev_sc
            prev_sc = sc
            if gained < 0:
                res.reason = "score_decreased"
                res.detail = (
                    f"i{isl['inning']}/{isl['half']} {isl['action']} "
                    f"pre={isl['pre_slots']}"
                )
                return res
            narrated = _narrated(isl)
            isl["runs"] = narrated
            deferred += narrated - gained
            if deferred < 0 and mutation not in (
                "no_unnarrated_check", "no_unnarrated_run"
            ):
                res.reason = "unnarrated_run"
                res.detail = (
                    f"i{isl['inning']}/{isl['half']} 分數 +{gained}、"
                    f"敘述可解釋 {narrated}（{isl['action']}）"
                )
                return res
        final_score[side] = prev_sc
        if deferred > 0 and mutation not in (
            "no_unnarrated_check", "no_narrated_run_not_scored"
        ):
            res.reason = "narrated_run_not_scored"
            res.detail = f"half={side} 敘述比比分欄多 {deferred} 分"
            return res

    # --- 記分板 error_cnt：獨立於逐球敘述的失誤訊號 ---------------------------
    # 逐球敘述是本檔偵測失誤的唯一來源，而它會漏。官方逐局 E 提供第二個訊號：
    # 「這個半局有 N 次失誤」。但**它給不出是哪一球**——所以不得用來猜歸屬，
    # 只能用來否證「這半局沒有失誤」。官方說有、敘述看不到 ⇒ 我對這半局的
    # 自責分判定沒有依據 ⇒ 整場 fail-closed。
    #
    # 這是把「默默算錯」換成「明講不知道」，通過率會下降，那是正確方向。
    if official_errors and mutation != "no_scoreboard_signal":
        seen_halves = {(isl["inning"], isl["half"]) for isl in summaries}
        narrated = {
            (isl["inning"], isl["half"])
            for isl in summaries
            if any(m in isl["text"] for m in ERROR_MARKERS)
        }
        # **窄化（iteration 8）**：9.16 的失誤效果全部侷限在**同一個半局內** ——
        # (b) 失誤所致得分非自責、(d) 以無失誤重建該半局、漏接第三出局後該半局的
        # 續打得分非自責。本檔的帳本（`bases`／`shadow`／`out_opps`）也是逐半局重置。
        # 故官方說有失誤的那個半局若**攻方一分未得**，這個看不見的失誤對三個對帳
        # 維度都不可能有影響：ER 沒有分可以被判、runs 不因失誤改變、outs 取自逐球
        # 實際發生的出局。此時整場 fail-closed 是**排太多**，不是保守。
        #
        # 得分數取自官方記分板 `score_cnt`（獨立於逐球敘述的第二來源；半局別對照
        # 由 `gate_ablation.py` 的 `half_inning_mapping_check` 全母體驗過）。
        # 取不到該半局得分時**不窄化**（fail-closed 方向不變）。
        # 窄化本身可消融：`--mutation wide_official_error_gate` 還原窄化前的行為。
        unlocated: list[dict[str, Any]] = []
        er_irrelevant: list[dict[str, Any]] = []
        for (inning, half), n_err in sorted(official_errors.items()):
            if not n_err:
                continue
            if (inning, half) not in seen_halves or (inning, half) not in narrated:
                rec = {
                    "inning": inning,
                    "half": half,
                    "n_err": n_err,
                    "missing_livelog": (inning, half) not in seen_halves,
                }
                half_runs = (
                    None if official_half_runs is None
                    else official_half_runs.get((inning, half))
                )
                if half_runs == 0 and mutation != "wide_official_error_gate":
                    er_irrelevant.append(rec)
                    continue
                rec["half_runs"] = half_runs
                unlocated.append(rec)
        if er_irrelevant:
            res.gate_info["er_irrelevant_unlocated"] = er_irrelevant
        if unlocated:
            first = unlocated[0]
            res.reason = "official_error_unlocated"
            res.detail = (
                f"i{first['inning']}{first['half']} 官方 E={first['n_err']}，"
                f"{'該半局無 livelog' if first['missing_livelog'] else '逐球敘述無失誤性字樣'}"
            )
            res.gate_info["unlocated"] = unlocated
            return res

    # --- 逐半局走訪 ---------------------------------------------------------
    outs: dict[str, int] = defaultdict(int)
    runs: dict[str, int] = defaultdict(int)
    er: dict[str, int] = defaultdict(int)

    idx = 0
    n = len(summaries)
    last_pitcher_of_game: str | None = None
    last_post_outs = 0
    last_half = "1"
    last_island_runs = 0

    while idx < n:
        half_key = summaries[idx]["half_key"]
        group = []
        while idx < n and summaries[idx]["half_key"] == half_key:
            group.append(summaries[idx])
            idx += 1

        half = group[0]["half"]
        bases: dict[int, Runner] = {}
        # 9.16(a)／9.16(d)：以「無失誤重建的半局」判定自責分。shadow 是重建世界裡
        # 仍在壘上的跑者（slot → 壘號）；在重建世界裡踏上本壘者，其得分才是自責分。
        shadow: dict[str, int] = {}
        team_opps = 0
        # 9.16(i)：後援投手不得享有出場前的出局機會 → 每位投手自己的重建出局計數
        out_opps: dict[str, int] = {}

        for gi, isl in enumerate(group):
            pitchers = isl["pitchers"]
            cur_pitcher = pitchers[-1] if pitchers else None
            if cur_pitcher is None:
                res.reason = "island_without_pitcher"
                return res
            for p in pitchers:
                out_opps.setdefault(p, team_opps if mutation == "team_opps" else 0)

            # 得分數來自上方的逐側累計對帳（敘述定 play、比分欄定總數），
            # 不再用「本 island 比分 − 前一 island 比分」——那個相減假設比分欄的
            # 更新不會跨 island，`2026/A/81` 三局下證明它會（見上方 R1-001）。
            # `null_score`／`score_decreased` 已在該處先行 fail-closed。
            island_runs = isl["runs"]

            pre_outs, post_outs = isl["pre_outs"], isl["post_outs"]
            if pre_outs is None or post_outs is None:
                res.reason = "null_outs"
                res.detail = f"i{isl['inning']}/{isl['half']} {isl['action']} pre={isl['pre_slots']}"
                return res
            island_outs = post_outs - pre_outs
            if island_outs < 0:
                res.reason = "outs_decreased"
                res.detail = f"i{isl['inning']}/{isl['half']} {isl['action']} pre={isl['pre_slots']}"
                return res

            # 突破僵局跑者：「視為守備失誤上壘」→ 非自責（7.01(b)(2)(C)）。
            # 該列本身的壘況欄是空的，跑者的棒次槽要向**下一個 island** 取。
            #
            # === 責任歸屬（失分要記給誰）=========================================
            # 結論：記給**實際投該半局**的投手，不是置人列上的 `pitcher_acnt`。
            # 完整查證過程見 RESULTS.md §3.5。以下是摘要——**刻意記錄兩次失敗的
            # 推導**，因為「規則文本查不到」正是這裡最重要的事實。
            #
            # 一、規則文本查證（皆核對原文）
            #   1. 7.01(b)(2)(C) 原文限縮於「為符合規則 9.16 **自責分**的計算」，
            #      未提失分歸屬。
            #   2. 9.16 標題含「失分 Runs Allowed」，但**全條無失分歸屬通則**。
            #      條內「失分」12 處：1 標題／2 處 9.16(a)原註例示／1 處 9.16(g)
            #      本文／8 處 9.16(g) 原註例示。唯一規範性語句是 9.16(g) 本文
            #      「該失分（無論自責分或非自責分）皆不為後援投手之責任」——但它
            #      是**換投遺留跑壘員**的專款，突破僵局跑者不是任何投手讓他上壘的。
            #   3. 聯盟規章第 37 條、裁判執法手冊補述 1.01 僅規定賽制與跑者位置，
            #      無歸屬條款。
            #
            # 二、兩次推導嘗試皆不貼合
            #   * 從一般歸屬原則外推 → 9.16 無通則可外推。
            #   * 引 5.10(g) 的最少面對打席要求 → **實例證明套不上**：2025/D/30
            #     官方 box 王奕凱 inning_pitched_cnt=1（＝3 個出局），他不是「未
            #     面對任何打者」，而是**未在該半局投球**（他投的是九局下）。
            #
            # 三、官方行為的準確敘述（本實作依據的事實）
            #   置人列是「首位打者之前」的偽事件，其 pitcher_acnt 沿用前一個同側
            #   半局的投手。窮舉：259 個突破僵局半局，30 個置人列投手 ≠ 面對首打者
            #   的投手，而這 30 個**全部**等於前一同側半局的投手（30/30 零例外）。
            #
            # 四、實證：三維對帳 +12 場一致、0 場相反（`--mutation no_tb_owner`）。
            #
            # ⚠️ 官方記錄員手冊不在本倉三份文件內。若日後取得，應回頭補依據。
            # ===================================================================
            #
            # **不得假設跑者在二壘。** 7.01(b)(2)(C) 只規定二壘，但**二軍曾試行
            # 一二壘版本**（需求方 2026-08-07 確認；實例 `2020/D/224` 十局上有兩個
            # 突破僵局 island，首位跑者置於**一壘**）。故改為從實際壘況欄推導：
            # 下一個 island 壘上出現、而目前帳本沒有的棒次槽，就是被放上去的跑者。
            if isl["family"] == TIEBREAK_FAMILY:
                nxt = group[gi + 1]["pre_slots"] if gi + 1 < len(group) else {}
                if not nxt:
                    # 靜默丟棄是隱患：取不到壘況就不可能正確歸屬這位跑者的得分
                    res.reason = "tiebreak_runner_unresolved"
                    res.detail = f"i{isl['inning']}/{isl['half']} next_pre_slots={nxt}"
                    return res
                # 突破僵局跑者的**責任投手**＝實際面對該半局第一位打者的投手，
                # 不是置人列上的 `pitcher_acnt`。推導與證據見下方 §「責任歸屬」。
                tb_owner = cur_pitcher
                if mutation != "no_tb_owner":
                    for later in group[gi + 1:]:
                        if later["family"] == TIEBREAK_FAMILY:
                            continue  # 一二壘變體會有連續兩個置人 island
                        if later["pitchers"]:
                            tb_owner = later["pitchers"][0]
                            break
                rebuilt: dict[int, Runner] = {}
                for b, s in nxt.items():
                    prev = next((r for r in bases.values() if r.slot == s), None)
                    rebuilt[b] = prev or Runner(
                        slot=s,
                        name=_s(isl.get("hitter_name")),
                        owner=tb_owner,
                        earned_ok=False,
                    )
                bases = rebuilt
                continue

            # 半局最後一個 island 沒有「下一個 island 的壘況」可讀 —— 此時壘上未
            # 得分的跑者是**殘壘**（LOB），不是出局。不得以空壘況推論他們消失，
            # 否則殘壘會被當成出局，重建出局數暴增（clean 場次實測會因此誤判）。
            is_last_in_half = gi + 1 >= len(group)
            next_slots = {} if is_last_in_half else group[gi + 1]["pre_slots"]
            pre_slots = isl["pre_slots"]

            # 壘上狀態與帳本一致性檢查（fail-closed）
            if set(pre_slots.values()) != {r.slot for r in bases.values()} or any(
                bases.get(b) is None or bases[b].slot != s for b, s in pre_slots.items()
            ):
                # 帳本重同步：以 livelog 觀測為準，但標記為不可證
                res.reason = "ledger_desync"
                res.detail = f"i{isl['inning']}/{isl['half']} {isl['action']} pre={isl['pre_slots']}"
                return res

            new_slots = set(next_slots.values()) - set(pre_slots.values())
            if len(new_slots) > 1:
                res.reason = "multiple_new_runners"
                res.detail = f"i{isl['inning']}/{isl['half']} {isl['action']} pre={isl['pre_slots']}"
                return res
            batter_slot = next(iter(new_slots)) if new_slots else None
            vanished = {b: r for b, r in bases.items() if r.slot not in set(next_slots.values())}

            # --- 誰得分 -------------------------------------------------------
            named = SCORE_RE.findall(isl["text"])
            named_runners: list[Runner] = []
            tainted_scorers: set[str] = set()
            unresolved = 0
            for base_ch, nm, why in named:
                hit_r = None
                for b, r in vanished.items():
                    if r.name and r.name == nm:
                        hit_r = b
                        break
                if hit_r is None:
                    b = BASE_CH[base_ch]
                    if b in vanished:
                        hit_r = b
                if hit_r is None:
                    unresolved += 1
                    continue
                r = vanished.pop(hit_r)
                named_runners.append(r)
                # 9.16(d)：藉失誤／捕逸／妨礙進壘而得分 → 該分不記自責分
                if any(m in why for m in ERROR_MARKERS):
                    tainted_scorers.add(r.slot)
            if unresolved and mutation != "no_scorer_unresolved":
                res.reason = "scorer_unresolved"
                res.detail = f"i{isl['inning']}/{isl['half']} {isl['action']} pre={isl['pre_slots']}"
                # 消融時這一分會落到「打者」那條路徑（見 RESULTS.md §5.3）：
                # 記給**當下投手**、用**打者的上壘手段**判自責。該半局若只有一位
                # 投手，逐投手 runs 對這個代換完全不敏感——那正是「通過不等於判對」。
                res.gate_info["unresolved_scorer"] = {
                    "inning": isl["inning"], "half": isl["half"],
                    "unresolved": unresolved,
                    "pitchers_in_half": len(
                        {p for g in group for p in g["pitchers"]}
                    ),
                    "batter_reached_base": batter_slot is not None,
                }
                return res

            # （iteration 4 移除）舊版在「比賽結束」列以「離本壘最近者先得分」指派
            # 無敘述的再見得分。那是**猜測歸屬**，正是修正 3 要禁止的路徑——現在
            # 這類場次一律由上方的得分敘述完整性檢查 fail-closed。

            batter_runs = island_runs - len(named_runners)
            if batter_runs not in (0, 1):
                res.reason = "run_count_mismatch"
                res.detail = f"i{isl['inning']}/{isl['half']} {isl['action']} pre={isl['pre_slots']}"
                return res
            # 打者若已站上壘包就不可能同時得分 → 代表有一分沒被敘述涵蓋，fail-closed
            if batter_runs and batter_slot is not None:
                res.reason = "unnamed_runner_score"
                res.detail = f"i{isl['inning']}/{isl['half']} {isl['action']} pre={isl['pre_slots']}"
                return res

            # --- 打者的上壘手段與責任歸屬 ---------------------------------------
            fam = isl["family"]
            action = isl["action"] or ""
            if fam == "uncaught_third_strike":
                batter_earned_ok = action in U3K_EARNED_ACTIONS
            elif fam in UNEARNED_FAMILIES:
                batter_earned_ok = False
            elif (
                mutation != "spec_literal"
                and fam == "fielders_choice"
                and any(m in isl["text"] for m in ERROR_MARKERS)
            ):
                # 9.16(a)【註 1】①：因守備失誤而倖免出局者，其「出局機會」仍計 1 次。
                # 實例 `2026/A/30` 七局上：內野滾地球三壘手失誤，打者以「趁傳上壘」
                # 記錄 —— 無失誤時該 play 本應成立一個出局。
                batter_earned_ok = False
            elif fam in EARNED_ELIGIBLE_FAMILIES:
                batter_earned_ok = True
            else:
                batter_earned_ok = True  # out / sacrifice：打者不上壘，值不被使用

            # 9.16(g)：被封殺／野手選擇替換掉的遺留跑者，其責任轉移給替代的擊球跑者
            inherit: Runner | None = None
            if vanished and batter_slot is not None and not is_last_in_half:
                inherit = vanished[min(vanished)]

            batter_owner = cur_pitcher
            # 9.16(h)：投手替換時後援面對留有 2-0/2-1/3-0/3-1/3-2 的打者，
            # 若獲四壞球則記前任投手責任。本檔以 island 內投手序判定。
            if fam == "walk" and len(set(pitchers)) > 1:
                batter_owner = pitchers[0]
            if inherit is not None and mutation == "no_inherit":
                inherit = None
            if inherit is not None:
                batter_owner = inherit.owner
                batter_earned_ok = batter_earned_ok and inherit.earned_ok

            # --- 無失誤重建（9.16(a) 後段「3 出局機會」＋ 9.16(d)）---------------
            # 逐跑者的「本次進壘是否藉失誤」：以進壘敘述裡的原因欄判定。
            tainted_names = {
                nm
                for _b, nm, why in ADVANCE_RE.findall(isl["text"])
                if any(m in why for m in ERROR_MARKERS)
            }
            # island 層級的失誤旗標**只用於 trace 顯示**：判定一律走逐跑者的
            # `tainted_names`（island 層級會過度保守，見 module docstring 上方註解）
            tainted = bool(tainted_names)
            batter_lands: int | None = None
            if batter_slot is not None:
                for b, s in next_slots.items():
                    if s == batter_slot:
                        batter_lands = b
            elif batter_runs:
                batter_lands = 4
            batter_in_shadow = batter_lands is not None and batter_earned_ok
            batter_shadow_base = batter_lands
            batter_name = _s(isl.get("hitter_name"))
            if batter_lands is not None and batter_name in tainted_names:
                batter_shadow_base = min(
                    batter_lands,
                    _natural_batter_base(action, mutation == "double_as_earned"),
                )

            # 重建世界裡本 island 造成的出局：實際被刺殺的跑者 + 打者（實際出局，
            # 或實際藉失誤／妨礙上壘＝重建世界應出局）
            if mutation == "spec_literal":
                # 需求方逐字：「因失誤造成第三出局數沒有成立」→ 只算實際出局
                # 加上打者因失誤上壘（本應出局）的那一次
                sh_outs = island_outs + (1 if fam == "reach_on_error" else 0)
            elif is_last_in_half:
                # 殘壘不可判為出局：改採官方推導的實際出局數
                sh_outs = island_outs
            else:
                sh_outs = len(vanished)
                if batter_lands is None or not batter_earned_ok:
                    sh_outs += 1

            # 得分判定必須用「本 island 之前」的重建出局數（同一 play 上先得分後
            # 成立第 3 出局仍算），故先結算再累加。
            scored_shadow: set[str] = set()
            moves: list[tuple[str, int, int]] = []  # (slot, 實際起點, 實際終點/4)
            for r in named_runners:
                pb = next((b for b, rr in pre_slots.items() if rr == r.slot), None)
                if pb is not None:
                    moves.append((r.slot, pb, 4))
            for b, s in next_slots.items():
                if s == batter_slot:
                    continue
                pb = next((bb for bb, ss in pre_slots.items() if ss == s), None)
                if pb is not None:
                    moves.append((s, pb, b))

            forced = _forced_targets(shadow, batter_in_shadow)
            # 失誤污染的 play：重建世界裡跑者只走「被迫進壘」與「打者自身推進數」
            # 之較大者，且不超過實際觀測（9.16(d)【註 1】：若不藉失誤仍可進壘得分
            # 者仍記自責分）。純淨 play 直接沿用實際推進數。
            natural = (
                batter_shadow_base
                if (batter_in_shadow and batter_shadow_base and batter_shadow_base < 4)
                else 0
            )
            if mutation != "no_hr_fix" and batter_in_shadow and batter_shadow_base == 4:
                # 打者自己踏上本壘（全壘打）→ 他前方的每一位跑者必然得分，與失誤
                # 無關。9.16(d)【註 1】① 明文：「但不是一壘安打，若以三壘安打以上之
                # 長打得分時為自責分」。
                #
                # 舊版此處退回 0（條件寫 `batter_shadow_base < 4`），使失誤／捕逸
                # 污染把前方跑者壓在原壘 → 全壘打送回來的分被誤判非自責。
                # 實例 `2018/A/1` 二局上：王峻杰二壘安打、捕逸上三壘、王勝偉全壘打，
                # 官方記自責分而舊版不記。修正後 5 場翻正、0 場退步。
                natural = 4
            slot_names = {r.slot: r.name for r in bases.values()}
            for slot, pb, nb in moves:
                if slot not in shadow:
                    continue
                forced_delta = max(forced.get(slot, shadow[slot]) - shadow[slot], 0)
                delta = nb - pb
                if slot_names.get(slot) in tainted_names:
                    delta = min(delta, max(forced_delta, natural))
                delta = max(delta, forced_delta)
                new = shadow[slot] + delta
                if new >= 4:
                    scored_shadow.add(slot)
                    shadow.pop(slot, None)
                else:
                    shadow[slot] = new
            if not is_last_in_half:
                for r in vanished.values():
                    shadow.pop(r.slot, None)

            if mutation == "maxtaint" and any(m in isl["text"] for m in ERROR_MARKERS):
                for _r in list(bases.values()):
                    shadow.pop(_r.slot, None)
                scored_shadow -= {r.slot for r in bases.values()}
            scored_shadow -= tainted_scorers
            batter_key = batter_slot or "__BATTER__"
            if batter_in_shadow and batter_shadow_base == 4:
                scored_shadow.add(batter_key)

            # --- 記分（自責分＝在重建世界得分，且該投手尚未用完 3 個出局機會）----
            def charge(owner: str, slot: str | None, fallback_ok: bool) -> None:
                runs[owner] += 1
                if mutation in ("spec_literal", "no_shadow"):
                    earned = fallback_ok
                else:
                    earned = slot is not None and slot in scored_shadow
                limit = out_opps.get(owner, 0)
                if mutation == "out_before_run" and (
                    batter_lands is None or not batter_earned_ok
                ):
                    limit += 1
                if earned and limit < 3:
                    er[owner] += 1

            for r in named_runners:
                charge(r.owner, r.slot, r.earned_ok)
            if batter_runs:
                charge(
                    batter_owner,
                    batter_key if batter_in_shadow else None,
                    batter_earned_ok,
                )

            # 打者進入重建世界的壘上
            if batter_in_shadow and batter_slot is not None and (batter_shadow_base or 4) < 4:
                shadow[batter_slot] = batter_shadow_base or 1

            # --- 出局數歸屬 -----------------------------------------------------
            if island_outs:
                outs[cur_pitcher] += island_outs

            if trace:
                print(
                    f"  i{isl['inning']}/{half} pre{pre_slots} nxt{next_slots} "
                    f"fam={fam}/{action} outs{pre_outs}->{post_outs} R+{island_runs} "
                    f"tainted={tainted} sh_outs={sh_outs} opp={dict(out_opps)} "
                    f"shadow={shadow} scored_sh={scored_shadow} "
                    f"batter={batter_slot}->{batter_lands} in_sh={batter_in_shadow} "
                    f"named={[r.slot for r in named_runners]} van={[r.slot for r in vanished.values()]}"
                )

            # --- 累加重建出局機會（9.16(a)【註 1】、9.16(i)）--------------------
            team_opps += sh_outs
            if sh_outs:
                for p in list(out_opps):
                    out_opps[p] += sh_outs

            # --- 更新壘包帳本 ---------------------------------------------------
            new_bases: dict[int, Runner] = {}
            by_slot = {r.slot: r for r in bases.values()}
            for b, s in next_slots.items():
                if s in by_slot:
                    new_bases[b] = by_slot[s]
                elif batter_slot is not None and s == batter_slot:
                    new_bases[b] = Runner(
                        slot=s,
                        name=_s(isl.get("hitter_name")),
                        owner=batter_owner,
                        earned_ok=batter_earned_ok,
                    )
                else:
                    res.reason = "unknown_runner_appeared"
                    return res
            bases = new_bases

            # --- 代跑替換（9.16(a)「包含代跑者」）-------------------------------
            for old, new in PINCH_RUN_RE.findall(isl["text"]):
                for r in bases.values():
                    if r.name == old:
                        r.name = new

            last_pitcher_of_game = cur_pitcher
            last_post_outs = post_outs
            last_half = half
            last_island_runs = island_runs

    # --- 比賽最後一個出局：livelog 的「比賽結束」列不帶「N人出局」敘述 ---------
    # （實測：全庫 4,100 個半局達 2 出局卻無 3 出局敘述，末列皆為「比賽結束」）
    if mutation == "walkoff_fix":
        walk_off = last_half == "2" and final_score["2"] > final_score["1"]
    else:
        walk_off = last_half == "2" and last_island_runs > 0
    if not walk_off and last_post_outs < 3 and last_pitcher_of_game:
        outs[last_pitcher_of_game] += 3 - last_post_outs

    res.ok = True
    res.outs = dict(outs)
    res.runs = dict(runs)
    res.er = {} if mutation == "zero_er" else dict(er)
    res.notes = sorted(
        {
            m
            for isl in summaries
            for m in ERROR_MARKERS
            if m in isl["text"]
        }
        | {isl["family"] for isl in summaries if isl["family"] in UNEARNED_FAMILIES}
    )
    return res


# ---------------------------------------------------------------------------
# 對帳
# ---------------------------------------------------------------------------


def _classify(res: GameResult, official: dict[str, dict[str, Any]]) -> str:
    """不一致成因分類（守恆律）。

    繼承跑者的責任轉移（9.16(g)）必然在**同一 game 的同一側內淨差為 0** —— 分只是
    從一位投手轉到另一位。故：

    * 某一側的 `runs` 或 `outs` **淨差不為 0** ⇒ 不是歸屬轉移，是**來源資料缺漏**
      （分或出局憑空多出／消失）。實例：`2026/D/180` 的 livelog 末筆比分 1:2，
      而 header final 是 2:3（#103 查核，兩側各 +1）。
    * 淨差為 0 但逐投手不同 ⇒ **歸屬邊界**（9.16(g)/(h) 的判定差異）。
    * 失分與出局全對、只有自責分不同 ⇒ **自責分規則邊界**（9.16(a)(c)(d) 的
      記錄員判斷）。
    """
    side_runs: dict[str, int] = defaultdict(int)
    side_outs: dict[str, int] = defaultdict(int)
    per_pitcher_runs = False
    per_pitcher_outs = False
    er_diff = False
    for acnt, row in official.items():
        side = _s(row.get("visiting_home_type")) or "?"
        off_outs = (
            int(row["inning_pitched_cnt"]) * 3 + int(row["inning_pitched_div3"])
            if row["inning_pitched_cnt"] is not None
            and row["inning_pitched_div3"] is not None
            else None
        )
        d_out = res.outs.get(acnt, 0) - (off_outs if off_outs is not None else 0)
        d_run = res.runs.get(acnt, 0) - int(row["runs"] or 0)
        side_outs[side] += d_out
        side_runs[side] += d_run
        per_pitcher_outs = per_pitcher_outs or d_out != 0
        per_pitcher_runs = per_pitcher_runs or d_run != 0
        er_diff = er_diff or res.er.get(acnt, 0) != int(row["earned_runs"] or 0)

    if any(v != 0 for v in side_runs.values()) or any(v != 0 for v in side_outs.values()):
        return "source_gap"
    if per_pitcher_runs or per_pitcher_outs:
        return "attribution_boundary"
    if er_diff:
        return "earned_rule_boundary"
    return "unknown"


def _assert_bindable(conn: Any, years: list[int], kinds: list[str]) -> None:
    """`--as-of` 專用的 fail-closed 前置檢查。

    以 `games.game_date` 為界時，**任何無法定日期的 livelog 場次都會被靜默排除** ——
    那會讓「界線只釘一半」變成看不見的母體縮水。故先證明界線覆蓋全母體再繼續
    （實測目前兩者皆為 0）。不給 `--as-of` 時不做界線，也就不需要這道檢查。
    """
    cur = conn.cursor()
    cur.execute(
        "SELECT count(*) FILTER (WHERE g.game_sno IS NULL) AS orphan, "
        "       count(*) FILTER (WHERE g.game_sno IS NOT NULL "
        "                        AND g.game_date IS NULL) AS undated "
        "FROM (SELECT DISTINCT year, kind_code, game_sno FROM cpbl.game_livelog "
        "      WHERE year = ANY(%s) AND kind_code = ANY(%s)) l "
        "LEFT JOIN cpbl.games g USING (year, kind_code, game_sno)",
        (years, kinds),
    )
    row = cur.fetchone() or {}
    if row.get("orphan") or row.get("undated"):
        raise SystemExit(
            f"as_of 界線無法覆蓋全母體：{row.get('orphan')} 場 livelog 無 games 列、"
            f"{row.get('undated')} 場 game_date 為 NULL。"
            "這些場次會被日期界線靜默排除，等同界線只釘一半 —— 先修資料再重跑。"
        )


def reconcile(
    years: list[int], kinds: list[str], limit: int | None, mutation: str = "full",
    as_of: str | None = None, per_game: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """`as_of=None`（預設）＝**不設界線**，母體就是當下 DB 的全部 scope。

    報告數字照實隨母體走。`as_of` 只在需要「兩次執行對照同一母體」時給
    （驗證工具，見 module docstring）。

    `per_game`：給定時逐場填入 `{gid: {"status": ..., "gate_info": ...}}`。
    `status` ＝ `pass`／閘門名／`mismatch:<cause>`／`no_official`。**只供
    `gate_ablation.py` 做逐閘門 Δ 與去向分析**，不影響回傳的 artifact 內容。
    """
    taxonomy = load_taxonomy()
    stats: dict[tuple[int, str], dict[str, int]] = defaultdict(
        lambda: defaultdict(int)
    )
    reasons: dict[str, int] = defaultdict(int)
    examples: dict[str, list[str]] = defaultdict(list)
    diff_hist: dict[str, int] = defaultdict(int)

    with psycopg.connect(DSN, row_factory=dict_row) as conn:
        cur = conn.cursor()
        if as_of is None:
            cur.execute(
                """
                SELECT DISTINCT l.year, l.kind_code, l.game_sno
                FROM cpbl.game_livelog l
                WHERE l.year = ANY(%s) AND l.kind_code = ANY(%s)
                ORDER BY 1, 2, 3
                """,
                (years, kinds),
            )
        else:
            # 給了界線才 join `games`。**一條界線同時釘住所有下游來源**：livelog／
            # pitching_gamelog／game_scoreboard 都是以界內場次逐場取值，界外場次
            # 連查都不會查到，故不存在「只釘一半」的漏洞。
            _assert_bindable(conn, years, kinds)
            cur.execute(
                """
                SELECT DISTINCT l.year, l.kind_code, l.game_sno
                FROM cpbl.game_livelog l
                JOIN cpbl.games g
                  ON g.year = l.year AND g.kind_code = l.kind_code
                 AND g.game_sno = l.game_sno
                WHERE l.year = ANY(%s) AND l.kind_code = ANY(%s)
                  AND g.game_date <= %s::date
                ORDER BY 1, 2, 3
                """,
                (years, kinds, as_of),
            )
        games = [(r["year"], r["kind_code"], r["game_sno"]) for r in cur.fetchall()]
        if limit:
            games = games[:limit]

        for year, kind, sno in games:
            key = (year, kind)
            stats[key]["games"] += 1
            cur.execute(
                f"SELECT {EVENT_COLS} FROM cpbl.game_livelog "  # noqa: S608
                "WHERE year=%s AND kind_code=%s AND game_sno=%s",
                (year, kind, sno),
            )
            events = [dict(r) for r in cur.fetchall()]
            cur.execute(
                "SELECT pitcher_acnt, visiting_home_type, inning_pitched_cnt, "
                "inning_pitched_div3, runs, earned_runs FROM cpbl.pitching_gamelog "
                "WHERE year=%s AND kind_code=%s AND game_sno=%s",
                (year, kind, sno),
            )
            official = {
                r["pitcher_acnt"]: r for r in cur.fetchall()
            }
            # 記分板逐局失誤：翻轉 visiting_home_type（守方 ↔ 半局），見 rebuild_game
            cur.execute(
                "SELECT inning_seq, visiting_home_type, error_cnt, score_cnt "
                "FROM cpbl.game_scoreboard "
                "WHERE year=%s AND kind_code=%s AND game_sno=%s",
                (year, kind, sno),
            )
            official_errors: dict[tuple[int, str], int] = {}
            official_half_runs: dict[tuple[int, str], int] = {}
            for r in cur.fetchall():
                if r["inning_seq"] is None:
                    continue
                # 變數名不得用 `key`——外層 `key = (year, kind)` 是 stats 的分組鍵，
                # 覆寫它會讓其後所有 stats 寫入落到 (inning, half) 桶裡（實際踩過）
                if r["error_cnt"] is not None:
                    # 失誤是**守方**犯的 → 半局別要翻轉
                    err_key = (int(r["inning_seq"]), "2"
                               if _s(r["visiting_home_type"]) == "1" else "1")
                    official_errors[err_key] = (
                        official_errors.get(err_key, 0) + int(r["error_cnt"])
                    )
                if r["score_cnt"] is not None:
                    # 得分是**攻方**的 → 半局別**不翻**（客隊 vht='1' 打上半局）
                    run_key = (int(r["inning_seq"]), "1"
                               if _s(r["visiting_home_type"]) == "1" else "2")
                    official_half_runs[run_key] = (
                        official_half_runs.get(run_key, 0) + int(r["score_cnt"])
                    )
            if not official:
                stats[key]["no_official"] += 1
                reasons["no_official"] += 1
                if per_game is not None:
                    per_game[f"{year}/{kind}/{sno}"] = {"status": "no_official"}
                continue

            try:
                res = rebuild_game(
                    year, kind, sno, events, taxonomy, mutation=mutation,
                    official_errors=official_errors,
                    official_half_runs=official_half_runs,
                )
            except Exception as exc:  # noqa: BLE001 - 研究腳本：任何例外皆 fail-closed
                res = GameResult(year, kind, sno, ok=False, reason=f"exception:{type(exc).__name__}")

            gid = f"{year}/{kind}/{sno}"
            # 窄化揭露：這些場次有「官方說有失誤、敘述看不到」的半局，但該半局
            # 一分未得，故不再整場排除。數字進 artifact 讓 `--check` 看得到。
            if res.gate_info.get("er_irrelevant_unlocated"):
                stats[key]["oeu_narrowed_games"] += 1
            stats[key]["appearances"] += len(official)
            stats[key]["appearances_er0"] += sum(
                1 for r in official.values() if (r["earned_runs"] or 0) == 0
            )
            if not res.ok:
                stats[key]["rebuild_failed"] += 1
                reasons[res.reason or "unknown"] += 1
                if len(examples[res.reason or "unknown"]) < 5:
                    examples[res.reason or "unknown"].append(gid)
                if per_game is not None:
                    per_game[gid] = {
                        "status": res.reason or "unknown",
                        "gate_info": res.gate_info,
                    }
                continue

            ok_outs = True
            ok_er = True
            ok_runs = True
            for acnt, row in official.items():
                off_outs = None
                if row["inning_pitched_cnt"] is not None and row["inning_pitched_div3"] is not None:
                    off_outs = int(row["inning_pitched_cnt"]) * 3 + int(row["inning_pitched_div3"])
                got_outs = res.outs.get(acnt, 0)
                if off_outs is None or got_outs != off_outs:
                    ok_outs = False
                    if off_outs is not None:
                        diff_hist[f"outs{got_outs - off_outs:+d}"] += 1
                off_er = row["earned_runs"]
                got_er = res.er.get(acnt, 0)
                er_ok_here = off_er is not None and got_er == int(off_er)
                if not er_ok_here:
                    ok_er = False
                    if off_er is not None:
                        diff_hist[f"er{got_er - int(off_er):+d}"] += 1
                # 第三維：失分。兩維（ER＋outs）擋不住失分歸屬錯誤——實測有 15 場
                # 逐投手 runs 與官方不符、但 ER 與 outs 剛好都吻合而通過兩維對帳
                # （ML-PITCHER-ER-REBUILD1 iteration 2 發現）。runs 是官方既有欄位，
                # 加入零成本且嚴格更強。
                off_runs = row["runs"]
                got_runs = res.runs.get(acnt, 0)
                runs_ok_here = off_runs is not None and got_runs == int(off_runs)
                if not runs_ok_here:
                    ok_runs = False
                    if off_runs is not None:
                        diff_hist[f"runs{got_runs - int(off_runs):+d}"] += 1
                # 逐出賽（pitcher×game）通過率：下游消費的粒度就是出賽
                if er_ok_here and runs_ok_here and off_outs is not None and got_outs == off_outs:
                    stats[key]["appearance_pass"] += 1
                    if int(off_er) == 0:
                        stats[key]["appearance_pass_er0"] += 1
            # 重建出現官方沒有的投手 → 不一致
            for acnt in res.outs:
                if acnt not in official and res.outs[acnt]:
                    ok_outs = False

            if sum(official_errors.values()) == 0 and any(
                int(r["runs"] or 0) > int(r["earned_runs"] or 0) for r in official.values()
            ):
                stats[key]["zero_error_unearned_games"] += 1
                if ok_outs and ok_er and ok_runs:
                    stats[key]["zero_error_unearned_pass"] += 1
            stratum = "clean" if not res.notes else "error_tainted"
            stats[key][f"{stratum}_games"] += 1
            if ok_outs:
                stats[key]["outs_pass"] += 1
            if ok_er:
                stats[key]["er_pass"] += 1
                stats[key][f"{stratum}_er_pass"] += 1
            if ok_runs:
                stats[key]["runs_pass"] += 1
            # 舊的兩維基準保留為稽核值，供「第三維買到／揭穿了什麼」的對照
            if ok_outs and ok_er:
                stats[key]["two_dim_pass"] += 1
            if ok_outs and ok_er and ok_runs:
                stats[key]["all_pass"] += 1
                # 分層的**三維**通過數。舊版只輸出分層的自責分維通過數，害 §4.3
                # 得靠報告外的一次性計算補值 —— 那種數字無法被 `--check` 驗。
                stats[key][f"{stratum}_all_pass"] += 1
                if per_game is not None:
                    per_game[gid] = {"status": "pass"}
            else:
                cause = _classify(res, official)
                stats[key][f"cause_{cause}"] += 1
                # 分層 × 成因：clean 分層剩下的落差究竟是自責分判斷還是來源缺漏，
                # 是 §4.3 唯一的論據，必須由 artifact 自己產生。
                stats[key][f"{stratum}_cause_{cause}"] += 1
                reasons[f"mismatch:{cause}"] += 1
                if len(examples[f"mismatch:{cause}"]) < 8:
                    examples[f"mismatch:{cause}"].append(gid)
                if per_game is not None:
                    per_game[gid] = {"status": f"mismatch:{cause}"}

    # as-of 用**資料本身**表述，不用 wall-clock（wall-clock 會讓每次重跑都髒
    # worktree，使「worktree 髒了」失去訊號功能——RESEARCH-VERDICT-AUDIT1 R1 教訓）。
    #
    # 這一區塊是**來源指紋**：`--check` 用它分辨「母體漂移」與「重建邏輯改變」。
    # 三個被消費的來源都要記——只記 livelog 的話，官方 box 或記分板被補寫時
    # 指紋不動，漂移就會被誤判成邏輯退步。
    bound = "" if as_of is None else " AND g.game_date <= %(as_of)s::date"
    params = {"years": years, "kinds": kinds, "as_of": as_of}
    with psycopg.connect(DSN, row_factory=dict_row) as conn:
        c2 = conn.cursor()

        def rows_of(table: str) -> int:
            c2.execute(  # noqa: S608 - table 為本函式內的字面值白名單、bound 為字面值
                f"SELECT count(*) n FROM cpbl.{table} t "
                "JOIN cpbl.games g ON g.year = t.year AND g.kind_code = t.kind_code "
                "AND g.game_sno = t.game_sno "
                "WHERE t.year = ANY(%(years)s) AND t.kind_code = ANY(%(kinds)s)" + bound,
                params,
            )
            return int((c2.fetchone() or {}).get("n") or 0)

        c2.execute(  # noqa: S608 - bound 為字面值
            "SELECT max(g.game_date)::text d, count(*) n FROM cpbl.games g "
            "WHERE g.year = ANY(%(years)s) AND g.kind_code = ANY(%(kinds)s)" + bound,
            params,
        )
        gmeta = c2.fetchone() or {}
        c2.execute(  # noqa: S608 - bound 為字面值
            "SELECT max(g.game_date)::text d FROM cpbl.games g "
            "WHERE g.year = ANY(%(years)s) AND g.kind_code = ANY(%(kinds)s)"
            " AND EXISTS (SELECT 1 FROM cpbl.game_livelog l WHERE l.year = g.year"
            " AND l.kind_code = g.kind_code AND l.game_sno = g.game_sno)" + bound,
            params,
        )
        pmeta = c2.fetchone() or {}
        # --- 資料涵蓋日（coverage as-of）：把保留賽的改期日排除在外 -------------
        # `max_population_game_date` 是**污染值**：保留賽 [suspended game] 的
        # `game_date` 是**續賽的改期日**（未來），而它已經有 orig_date 當天那段的
        # livelog 與比分（實測 `2026/D/165` 排 09-15、7/17 打了 1:3）。拿它當
        # 「資料涵蓋到哪一天」會讀成「資料到九月」。
        #
        # 處置與 #106 同型：**算 coverage as-of 時排除保留賽**，但
        #   (1) 原始污染值仍以 `max_population_game_date` 揭露，不沉默捨棄；
        #   (2) 保留賽的場數與其原定日另立欄位揭露；
        #   (3) **母體與來源指紋一列都不動**（population_games / *_rows 仍涵蓋保留賽）——
        #       排除只影響 as-of 的顯示值。
        # 延賽 [postponed]（`delay_kind='延賽'`）不排除：它在改期日**整場重打**，
        # game_date 就是資料實際發生的日子；排除它反而會低估涵蓋日。
        c2.execute(  # noqa: S608 - bound 為字面值
            "SELECT (max(g.game_date) FILTER "
            "         (WHERE g.delay_kind IS DISTINCT FROM '保留'))::text AS cov, "
            "       count(*) FILTER (WHERE g.delay_kind = '保留') AS held, "
            "       count(*) FILTER (WHERE g.delay_kind = '保留' "
            "                        AND g.orig_date IS NULL) AS held_no_orig, "
            "       (max(g.game_date) FILTER (WHERE g.delay_kind = '保留'))::text "
            "         AS held_max_game_date, "
            "       (max(g.orig_date) FILTER (WHERE g.delay_kind = '保留'))::text "
            "         AS held_max_orig_date "
            "FROM cpbl.games g "
            "WHERE g.year = ANY(%(years)s) AND g.kind_code = ANY(%(kinds)s)"
            " AND EXISTS (SELECT 1 FROM cpbl.game_livelog l WHERE l.year = g.year"
            " AND l.kind_code = g.kind_code AND l.game_sno = g.game_sno)" + bound,
            params,
        )
        cmeta = c2.fetchone() or {}
        counts = {t: rows_of(t) for t in
                  ("game_livelog", "pitching_gamelog", "game_scoreboard")}

    out: dict[str, Any] = {
        "data_asof": {
            # 母體界線。**None＝未設界線**（預設；報告數字隨母體走，不凍結）。
            "as_of": as_of,
            # scope 內最大比賽日。**這不是母體界線**——實測它是球季賽程末日
            # （2026-10-03，比執行日晚兩個月），只描述 `games` 排到哪一天。
            "max_game_date": gmeta.get("d"),
            # 母體（有 livelog 的場次）裡的最大比賽日。**這是污染值、不是涵蓋日**：
            # 保留賽改期後帶未來日期卻已有部分 livelog（實測 `2026/D/165` 排 09-15）。
            # 保留在此**只作為漂移指紋與原始值揭露**；要引用「資料涵蓋到哪一天」
            # 一律用下面的 `coverage_asof`。
            "max_population_game_date": pmeta.get("d"),
            # **報告要標的 as-of**：母體裡最大比賽日，排除保留賽（其 game_date 是
            # 改期日）。母體本身不受影響，見上方查詢註解。
            "coverage_asof": cmeta.get("cov"),
            "coverage_asof_basis": (
                "max(games.game_date) over 母體，排除 delay_kind='保留'"
                "（保留賽的 game_date 是續賽改期日、非資料涵蓋日）；"
                "延賽不排除（改期日整場重打）。母體與來源指紋不受此排除影響。"
            ),
            # 被排除者的原始值揭露（不沉默捨棄）
            "held_population_games": cmeta.get("held"),
            "held_population_max_game_date": cmeta.get("held_max_game_date"),
            "held_population_max_orig_date": cmeta.get("held_max_orig_date"),
            "held_population_without_orig_date": cmeta.get("held_no_orig"),
            # 實際被對帳的場次數（＝有 livelog 的場次，**含保留賽**）。
            # 母體漂移最直接的訊號。
            "population_games": len(games),
            "games_rows": gmeta.get("n"),
            "livelog_rows": counts["game_livelog"],
            "pitching_gamelog_rows": counts["pitching_gamelog"],
            "scoreboard_rows": counts["game_scoreboard"],
        },
        "scope": {"years": years, "kinds": kinds, "limit": limit, "mutation": mutation},
        "by_year_kind": {
            f"{y}/{k}": dict(v) for (y, k), v in sorted(stats.items())
        },
        "totals": {},
        "fail_reasons": dict(sorted(reasons.items(), key=lambda kv: -kv[1])),
        "fail_examples": {k: v for k, v in examples.items()},
        "diff_histogram": dict(sorted(diff_hist.items(), key=lambda kv: -kv[1])[:30]),
    }
    tot: dict[str, int] = defaultdict(int)
    for v in stats.values():
        for kk, vv in v.items():
            tot[kk] += vv
    out["totals"] = dict(tot)
    if tot["games"]:
        out["totals"]["all_pass_rate"] = round(tot["all_pass"] / tot["games"], 4)
        out["totals"]["outs_pass_rate"] = round(tot["outs_pass"] / tot["games"], 4)
        out["totals"]["runs_pass_rate"] = round(tot["runs_pass"] / tot["games"], 4)
        out["totals"]["er_pass_rate"] = round(tot["er_pass"] / tot["games"], 4)
        # 稽核值：舊的兩維基準（ER＋outs）。**不是本卡的通過率**，只用來顯示
        # 第三維揭穿了多少「其實歸屬錯了卻被判通過」的場次。
        out["totals"]["two_dim_pass_rate_AUDIT_ONLY"] = round(
            tot["two_dim_pass"] / tot["games"], 4
        )
    if tot["appearances"]:
        out["totals"]["appearance_pass_rate"] = round(
            tot["appearance_pass"] / tot["appearances"], 4
        )
    if tot["appearances_er0"]:
        out["totals"]["appearance_pass_rate_er0"] = round(
            tot["appearance_pass_er0"] / tot["appearances_er0"], 4
        )
    return out


# `--check` 報告漂移量時要看的主要數字（來源指紋以外的部分）
HEADLINE_KEYS = (
    "games", "all_pass", "all_pass_rate", "appearances", "appearance_pass",
    "appearance_pass_rate", "er_pass_rate", "runs_pass_rate", "outs_pass_rate",
)


def _diff_line(name: str, old: Any, new: Any) -> str:
    if isinstance(old, (int, float)) and isinstance(new, (int, float)):
        return f"  {name}: {old} → {new}（{new - old:+g}）"
    return f"  {name}: {old!r} → {new!r}"


def run_check(path: Path, result: dict[str, Any], text: str) -> int:
    """比對重跑結果與既有 artifact，並**分辨兩種不符**。

    退出碼：0＝REPRODUCED／2＝INPUT_DRIFT／1＝LOGIC_MISMATCH。

    母體隨新比賽入庫而變動是正常狀態（canonical `statistical-redline.md` 第 9 條），
    不得讀成錯誤 —— 故漂移走 exit 2 並列出漂移量，與真正的邏輯退步（exit 1）分開。
    """
    if not path.exists():
        print(f"LOGIC_MISMATCH: 找不到 artifact {path}", file=sys.stderr)
        return 1
    prev_text = path.read_text(encoding="utf-8")
    if prev_text == text:
        print("REPRODUCED: 來源指紋與所有數字皆與 artifact 相同")
        return 0

    try:
        prev = json.loads(prev_text)
    except json.JSONDecodeError:
        print("LOGIC_MISMATCH: 既有 artifact 不是合法 JSON", file=sys.stderr)
        return 1

    old_asof, new_asof = prev.get("data_asof", {}), result["data_asof"]
    drift = {
        k: (old_asof.get(k), new_asof.get(k))
        for k in sorted(set(old_asof) | set(new_asof))
        if old_asof.get(k) != new_asof.get(k)
    }
    old_tot, new_tot = prev.get("totals", {}), result["totals"]
    moved = [
        _diff_line(k, old_tot.get(k), new_tot.get(k))
        for k in HEADLINE_KEYS
        if old_tot.get(k) != new_tot.get(k)
    ]

    if drift:
        print("INPUT_DRIFT: 來源資料已變動，artifact 的數字對應的是較舊的母體。")
        print("這是正常狀態不是缺陷（母體隨新比賽入庫而長大）；重生 artifact 即可。")
        print("來源指紋變動：")
        for k, (o, n) in drift.items():
            print(_diff_line(k, o, n))
        print("主要數字變動：" if moved else "主要數字未變動。")
        for line in moved:
            print(line)
        print(
            "若要排除漂移做對照，**兩次執行都加同一個** --as-of YYYY-MM-DD（驗證工具）。"
            "注意保留賽改期後帶未來日期，日期界線不等於當時的母體，只能近似。"
        )
        return 2

    print(
        "LOGIC_MISMATCH: 來源指紋完全相同、數字卻不同 ⇒ 重建邏輯已改變，必須查。",
        file=sys.stderr,
    )
    for line in moved:
        print(line, file=sys.stderr)
    return 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", default="2018-2026")
    ap.add_argument("--kinds", default="A,D")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--out", default=str(Path(__file__).with_name("reconciliation.json")))
    ap.add_argument("--check", action="store_true", help="只比對既有輸出，不覆寫")
    ap.add_argument(
        "--as-of", dest="as_of", default=None, metavar="YYYY-MM-DD",
        help="**驗證工具**：把母體限定在 game_date <= 此日，讓兩次不同時間的執行"
             "可在同一母體上對照。預設不設界線，報告數字照實隨母體走。",
    )
    ap.add_argument("--mutation", default="full", choices=MUTATIONS)
    args = ap.parse_args()

    lo, _, hi = args.years.partition("-")
    years = list(range(int(lo), int(hi or lo) + 1))
    kinds = args.kinds.split(",")

    result = reconcile(years, kinds, args.limit, args.mutation, as_of=args.as_of)
    text = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    path = Path(args.out)
    if args.check:
        return run_check(path, result, text)
    path.write_text(text, encoding="utf-8")
    print(json.dumps(result["totals"], ensure_ascii=False, indent=2))
    print(json.dumps(result["fail_reasons"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
