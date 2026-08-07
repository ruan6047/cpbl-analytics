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
# 以下是**尚未採用的候選**（需求方 2026-08-07 裁定暫緩，僅供量測）：
#   walkoff_fix  ：再見判定改「末半局為下半且主隊獲勝」
MUTATIONS = (
    "full", "spec_literal", "no_shadow", "no_inherit", "zero_er", "no_hr_fix",
    "no_tb_owner", "team_opps", "out_before_run", "maxtaint", "walkoff_fix",
)


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


def _natural_batter_base(action: str) -> int:
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
        return 2
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
) -> GameResult:
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
                # 本身有時尚未反映該分，要到同 island 的下一列才更新
                # （`2026/A/81` 三局下犧牲飛球）。比分單調，取 max 安全。
                "score": max(
                    (
                        v
                        for v in (_batting_score(e, half) for e in ordered)
                        if v is not None
                    ),
                    default=None,
                ),
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

    # --- 逐半局走訪 ---------------------------------------------------------
    outs: dict[str, int] = defaultdict(int)
    runs: dict[str, int] = defaultdict(int)
    er: dict[str, int] = defaultdict(int)

    prev_score: dict[str, int] = {"1": 0, "2": 0}
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

            score = isl["score"]
            if score is None:
                res.reason = "null_score"
                res.detail = f"i{isl['inning']}{isl['half']} {isl['action']} pre={isl['pre_slots']}"
                return res
            island_runs = score - prev_score[half]
            prev_score[half] = score
            if island_runs < 0:
                res.reason = "score_decreased"
                res.detail = f"i{isl['inning']}{isl['half']} {isl['action']} pre={isl['pre_slots']}"
                return res

            pre_outs, post_outs = isl["pre_outs"], isl["post_outs"]
            if pre_outs is None or post_outs is None:
                res.reason = "null_outs"
                res.detail = f"i{isl['inning']}{isl['half']} {isl['action']} pre={isl['pre_slots']}"
                return res
            island_outs = post_outs - pre_outs
            if island_outs < 0:
                res.reason = "outs_decreased"
                res.detail = f"i{isl['inning']}{isl['half']} {isl['action']} pre={isl['pre_slots']}"
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
                    res.detail = f"i{isl['inning']}{isl['half']} next_pre_slots={nxt}"
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
                res.detail = f"i{isl['inning']}{isl['half']} {isl['action']} pre={isl['pre_slots']}"
                return res

            new_slots = set(next_slots.values()) - set(pre_slots.values())
            if len(new_slots) > 1:
                res.reason = "multiple_new_runners"
                res.detail = f"i{isl['inning']}{isl['half']} {isl['action']} pre={isl['pre_slots']}"
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
            if unresolved:
                res.reason = "scorer_unresolved"
                res.detail = f"i{isl['inning']}{isl['half']} {isl['action']} pre={isl['pre_slots']}"
                return res

            # 再見安打：livelog 以「比賽結束」取代該打席的敘述，得分跑者無文字可解析。
            # 此時剩餘得分依「離本壘最近者先得分」指派給壘上跑者（棒球規則跑者不得
            # 超越前位跑者，5.09(b)(9)），是唯一可行的指派。
            if isl["game_over"] and island_runs > len(named_runners) and vanished:
                for b in sorted(vanished, reverse=True):
                    if len(named_runners) >= island_runs:
                        break
                    named_runners.append(vanished.pop(b))

            batter_runs = island_runs - len(named_runners)
            if batter_runs not in (0, 1):
                res.reason = "run_count_mismatch"
                res.detail = f"i{isl['inning']}{isl['half']} {isl['action']} pre={isl['pre_slots']}"
                return res
            # 打者若已站上壘包就不可能同時得分 → 代表有一分沒被敘述涵蓋，fail-closed
            if batter_runs and batter_slot is not None:
                res.reason = "unnamed_runner_score"
                res.detail = f"i{isl['inning']}{isl['half']} {isl['action']} pre={isl['pre_slots']}"
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
                batter_shadow_base = min(batter_lands, _natural_batter_base(action))

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
                    f"  i{isl['inning']}{half} pre{pre_slots} nxt{next_slots} "
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
        walk_off = last_half == "2" and prev_score["2"] > prev_score["1"]
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


def reconcile(
    years: list[int], kinds: list[str], limit: int | None, mutation: str = "full"
) -> dict[str, Any]:
    taxonomy = load_taxonomy()
    stats: dict[tuple[int, str], dict[str, int]] = defaultdict(
        lambda: defaultdict(int)
    )
    reasons: dict[str, int] = defaultdict(int)
    examples: dict[str, list[str]] = defaultdict(list)
    diff_hist: dict[str, int] = defaultdict(int)

    with psycopg.connect(DSN, row_factory=dict_row) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT DISTINCT l.year, l.kind_code, l.game_sno
            FROM cpbl.game_livelog l
            WHERE l.year = ANY(%s) AND l.kind_code = ANY(%s)
            ORDER BY 1, 2, 3
            """,
            (years, kinds),
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
            if not official:
                stats[key]["no_official"] += 1
                reasons["no_official"] += 1
                continue

            try:
                res = rebuild_game(year, kind, sno, events, taxonomy, mutation=mutation)
            except Exception as exc:  # noqa: BLE001 - 研究腳本：任何例外皆 fail-closed
                res = GameResult(year, kind, sno, ok=False, reason=f"exception:{type(exc).__name__}")

            gid = f"{year}/{kind}/{sno}"
            stats[key]["appearances"] += len(official)
            stats[key]["appearances_er0"] += sum(
                1 for r in official.values() if (r["earned_runs"] or 0) == 0
            )
            if not res.ok:
                stats[key]["rebuild_failed"] += 1
                reasons[res.reason or "unknown"] += 1
                if len(examples[res.reason or "unknown"]) < 5:
                    examples[res.reason or "unknown"].append(gid)
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
            else:
                cause = _classify(res, official)
                stats[key][f"cause_{cause}"] += 1
                reasons[f"mismatch:{cause}"] += 1
                if len(examples[f"mismatch:{cause}"]) < 8:
                    examples[f"mismatch:{cause}"].append(gid)

    # as-of 用**資料本身**表述，不用 wall-clock（wall-clock 會讓每次重跑都髒
    # worktree，使「worktree 髒了」失去訊號功能——RESEARCH-VERDICT-AUDIT1 R1 教訓）
    with psycopg.connect(DSN, row_factory=dict_row) as conn:
        c2 = conn.cursor()
        c2.execute(
            "SELECT max(g.game_date)::text d, count(*) n FROM cpbl.games g "
            "WHERE g.year = ANY(%s) AND g.kind_code = ANY(%s)",
            (years, kinds),
        )
        gmeta = c2.fetchone() or {}
        c2.execute(
            "SELECT count(*) n FROM cpbl.game_livelog WHERE year = ANY(%s) "
            "AND kind_code = ANY(%s)",
            (years, kinds),
        )
        lmeta = c2.fetchone() or {}

    out: dict[str, Any] = {
        "data_asof": {
            "max_game_date": gmeta.get("d"),
            "games_rows": gmeta.get("n"),
            "livelog_rows": lmeta.get("n"),
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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", default="2018-2026")
    ap.add_argument("--kinds", default="A,D")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--out", default=str(Path(__file__).with_name("reconciliation.json")))
    ap.add_argument("--check", action="store_true", help="只比對既有輸出，不覆寫")
    ap.add_argument("--mutation", default="full", choices=MUTATIONS)
    args = ap.parse_args()

    lo, _, hi = args.years.partition("-")
    years = list(range(int(lo), int(hi or lo) + 1))
    kinds = args.kinds.split(",")

    result = reconcile(years, kinds, args.limit, args.mutation)
    text = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    path = Path(args.out)
    if args.check:
        prev = path.read_text(encoding="utf-8") if path.exists() else ""
        if prev != text:
            print("MISMATCH: 重跑結果與既有 artifact 不同", file=sys.stderr)
            return 1
        print("OK: artifact 可重現")
        return 0
    path.write_text(text, encoding="utf-8")
    print(json.dumps(result["totals"], ensure_ascii=False, indent=2))
    print(json.dumps(result["fail_reasons"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
