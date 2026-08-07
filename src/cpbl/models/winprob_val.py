"""GAME-RECAP-WP-VAL1：場中 WP 時間外驗證 harness（唯讀；統計 Go/No-Go）。

沿用 models/winprob.py 的 run_dist + WE 動態規劃方法，但驗證打席改消費
GAME-RECAP-PA1 canonical 打席（cpbl.game_plate_appearances，published build、
state='ready'），以 walk-forward（訓練 2018..Y-1 → 驗證季 Y）檢驗 WP 校準與
規則邊界，產出各 scope（A 一軍例行／C 一軍總冠軍賽／D 二軍例行／E 一軍季後
挑戰賽）的 supported / proxy_with_warning / unsupported / insufficient_evidence
（v3 新增，「測不了」，見 :func:`verdict_for`）結論。F（二軍總冠軍賽）
**未納入驗證範圍**。scope 語意以 DB 實證為準（見 docs/reference/GLOSSARY.md
「kind_code」條目；FIX1 修正原「E 二軍季後」誤標與 {"E": "D"} proxy）。

不變量（紅線）：
1. 全程唯讀：訓練分布在記憶體重建，不寫 cpbl.run_dist / cpbl.win_expectancy。
2. 訓練與驗證期間完全分離：walk-forward 模型 span 恆 ≤ Y-1；in-sample 對照
   （全期 2018-2026 模型與生產 artifact 2018-2025）只用來量化同母體樂觀偏差，
   不作為支援證據。
3. 規則邊界依 (kind, year) 配置（聯盟規章第 37/38 條 + 逐場實證）：
   - A ≤2023：9 局制、最多延長至 12 局和局、延長空壘開局；
     A ≥2024：第 10 局起每半局二壘突破僵局跑者（113 年總教練會議修定）。
   - C：無和局、無突破僵局（全期 non_pa_tiebreak=0、最深 14 局實證）。
   - D：2018 與 2021–2024 9 局和局；2019–2020 10 局和局；
     2025+ 第 10 局突破僵局、10 局和局（實證：2025 起 9 局和局歸零）。
   - E（一軍季後挑戰賽）：無和局、無突破僵局（全史僅 2025 #4 達 10 局，
     該局空壘開局實證）；樣本極小（每季 3–5 場），僅 pooled 描述。
4. fail closed：state != 'ready' 的打席不評分且逐季回報排除數；完成場無
   published build 列入 coverage 缺口；縮短賽／宵禁和局／保留賽另做敏感度。
5. **局面分差只能取打席前比分**（ML-WP-VAL-RESAMPLE1，2026-08-07）：原實作直接讀
   canonical `pre_state.away_score`／`home_score`，但那是**起始事件列的比分欄原值**，
   而 livelog 的比分欄是事件**後**快照——單一事件即結束的得分打席（首球全壘打等）
   起始列＝終結列，存到的已是得分**後**的比分（DATA-RECAP-WP-PRESTATE1／#96）。
   改由 `recap.pre_scores_from_events()`（同一支純函式，不另刻）以 `start_event_no`
   對回 `pa_facts.annotate_scores()` 的事件流取「事件之前」的 running 比分；解不出
   來的 ready 打席 fail closed 排除並計入 `ready_pre_score_unresolved`。
   `--pre-score-source pre_state` 保留舊讀法**僅供 A/B 對照**，產出不得作為對外數字。
6. **判定必須可重現，且能表達「測不了」**（ML-WP-VERDICT-ROBUST1，2026-08-07）：
   v2 的硬性判定吃**單一 bootstrap seed** 的 99% CI 含不含 0，邊界分箱因此擲硬幣
   （實測 A 十分位 7 為 5/12 seed 顯著、D 十分位 2 為 7–8/12）。v3 把「抽樣不確定度」
   （不可約，正是 CI 要量的東西）與「Monte Carlo 誤差」（純實作雜訊，可用更多重抽壓下去）
   分開：決策統計量改用**跨註冊 seed 集池化**的 bootstrap 尾機率，並以該機率自身的
   MC 誤差判斷決策是否解析得出來——解析不出來就回 `undetermined`，**不得**當硬性證據。
   判定詞彙同步從二值擴為三態，見 :func:`verdict_for`。**門檻數值一律未動**
   （`THRESHOLDS` 與基準 `876ce9f` 逐字元相同），改的只有「怎麼判斷是否達標」。

執行（host 即可，無 LightGBM 相依）：
    uv run python -m cpbl.models.winprob_val            # 全部 scope
    uv run python -m cpbl.models.winprob_val --kinds A  # 單一 scope
產出：docs/research/game_recap_wp_val1_metrics.json（機器 artifact）+ stdout 表。
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import random
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from functools import cache
from pathlib import Path

import numpy as np

from cpbl.db import conn

# 打席前比分的 running 比分標註器。models 內部依賴，無循環：
# pa_facts 只在模組層 import ingest/db/completion（winprob_scorer 是它的函式內延後 import）。
from cpbl.models.pa_facts import annotate_scores

log = logging.getLogger("cpbl.winprob_val")

K_CAP = 6
DIFF_CLIP = 15
REGULATION = 9          # 一二軍皆 9 局制；勝負門檻自第 9 局起
MIN_STATE_N = 30        # 與 winprob.build_run_dist 相同的狀態樣本門檻
FIRST_YEAR = 2018       # livelog / canonical PA 起始年

# Go/No-Go 門檻。v1（首輪預註冊）以逐季點估計 ECE/maxdev 判定；首輪結果顯示
# 該設計忽略「同場打席共享賽果」的叢集相關——單季有效樣本≈場數（~150–360），
# 十分位偏差的抽樣雜訊底線即 ~3pt，ECE 0.025 門檻低於單季雜訊底線，校準完美的
# 模型也會經常超標。v2 改以 game-cluster bootstrap 顯著性 + 池化 walk-forward
# （全部時間外季合併，~10 倍檢定力）判定；v1 逐季點估計仍完整回報供稽核。
THRESHOLDS = {
    "ece_weighted_max": 0.025,   # v1 參考門檻（逐季點估計；雜訊未調整，僅回報）
    "decile_max_dev": 0.06,      # v1 參考門檻（同上）
    "min_season_pa": 5000,       # supported 所需最低單季樣本
    "min_coverage": 0.98,        # 完成場有 published build 的最低比例
    "pooled_bin_dev_max": 0.03,  # v2：池化 walk-forward 十分位（n>=1000）偏差上限
    "proxy_pooled_ece_max": 0.05,  # v2：proxy scope 至少池化 ECE 不嚴重失準才可掛警示
    "boot_reps": 500,            # game-cluster bootstrap 重抽次數
    "boot_ci": 0.99,             # 分箱偏差 CI 水準（60+ 分箱多重比較下取 99%）
}

# ───────────────── v3 判定機制常數（ML-WP-VERDICT-ROBUST1）─────────────────
# **刻意不放進 THRESHOLDS**：本卡只換判定機制、不動任何門檻數值。THRESHOLDS 區塊
# 與基準 876ce9f 逐字元相同（`git diff` 可直接驗證），新機制的旋鈕全部另立常數，
# 讓「有沒有偷改門檻」是一個機械可驗的問題。
#
# BOOT_SEEDS：註冊 seed 集。沿用 ML-WP-VAL-RESAMPLE1 §5 `bin_stability.py` 的同一組
#   （首位即 v2 的唯一 seed），使本卡的判定與那份已交付診斷直接可比。
BOOT_SEEDS: tuple[int, ...] = (20260725, 1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144)
LEGACY_BOOT_SEED = BOOT_SEEDS[0]     # v2 的唯一 seed；仍逐分箱回報供 A/B 對照
# BOOT_MAX_REPS：重抽總數上限。**這是本機制唯一還會左右結果的任意數字**，因此不能
#   讓「註冊了幾個 seed」決定判定——決策若在目前預算下解析不出來就**自動加碼重抽**
#   （seed 集倍增），直到解析得出來或撞到上限。撞到上限才回 undetermined，此時
#   「測不了」講的是資料本身的知識界線，不是「我沒抽夠」。
#   上限取 boot_reps 的 192 倍（96,000 次）：A 池化 1,856 場約 30 秒，是可接受的代價；
#   若日後有統計量常態撞頂，那本身就是該 scope 的訊號，應調高上限而非改判定。
BOOT_MAX_REPS = 192 * THRESHOLDS["boot_reps"]
BOOT_LADDER_SEED = 20260807          # 加碼 seed 的確定性來源（可重現）
# MC_TOLERANCE_Z：**計算容忍度**，不是統計顯著水準。用途是替尾機率 p̂ 的
#   Monte Carlo 誤差配一個 Wilson 區間（z=3 ≈ 99.7%），據以回答「再多抽幾次會不會
#   改變決策」。它管的是實作雜訊，不參與任何科學推論；調大只會讓更多分箱落入
#   undetermined（保守方向），敏感度見 docs/research/ML-WP-VERDICT-ROBUST1/。
MC_TOLERANCE_Z = 3.0
# 完美校準零假設下的 ECE 雜訊底線（RESEARCH-VERDICT-AUDIT1 §2 的同一把尺）。
HALF_NORMAL_MEAN = math.sqrt(2.0 / math.pi)   # E|X|，X ~ N(0, 1)
NULL_ECE_MC_REPS = 20000
NULL_ECE_MC_SEED = 20260807

SIG_SIGNIFICANT = "significant"
SIG_NOT_SIGNIFICANT = "not_significant"
SIG_UNDETERMINED = "undetermined"

# 判定詞彙（v3）。v2 只有前三個，把「測了，不準」與「測不了」壓成同一個 unsupported。
VERDICT_SUPPORTED = "supported"
VERDICT_PROXY_WITH_WARNING = "proxy_with_warning"
VERDICT_UNSUPPORTED = "unsupported"
VERDICT_INSUFFICIENT = "insufficient_evidence"


# ───────────────────────── 規則邊界 ─────────────────────────
@dataclass(frozen=True)
class RuleSet:
    max_inning: int             # 和局上限；tie_allowed=False 時為 DP 安全深度
    tiebreak_from: int | None   # 該局起每半局開局二壘有跑者（None=無）
    tie_allowed: bool

    @property
    def tag(self) -> str:
        tb = f",tb{self.tiebreak_from}" if self.tiebreak_from else ""
        tie = "tie" if self.tie_allowed else "no-tie"
        return f"cap{self.max_inning}{tb},{tie}"


def ruleset_for(kind: str, year: int) -> RuleSet:
    if kind == "A":
        return RuleSet(12, 10 if year >= 2024 else None, True)
    if kind == "C":                       # 季後賽：打到分出勝負（觀測最深 14）
        return RuleSet(20, None, False)
    if kind == "D":
        if year >= 2025:
            return RuleSet(10, 10, True)
        if year in (2019, 2020):
            return RuleSet(10, None, True)
        return RuleSet(9, None, True)
    if kind == "E":
        # 一軍季後挑戰賽（FIX1 修正：原誤標二軍季後並借二軍 2025 突破僵局規則）。
        # 實證：全史 E 僅 2025 #4 超過 9 局（10 局），該局上半**空壘開局**（livelog
        # first/second_base 皆空）→ 無突破僵局；無和局（同 C，一軍季後語意）。
        return RuleSet(20, None, False)
    raise ValueError(f"未知 kind_code: {kind}")


# 各 scope 的訓練 proxy：季後（C/E）樣本過小不足以自建分布，借同軍例行賽。
# FIX1：E＝一軍季後挑戰賽（DB 實證：1998 起 40 場、僅半季冠軍歧異年份、主隊碼
# *011）→ proxy 修正為 A；原 {"E": "D"} 係 E 誤標二軍季後所致。F（二軍總冠軍賽）
# 未納入驗證範圍。
TRAIN_PROXY = {"A": "A", "C": "A", "D": "D", "E": "A"}


# ───────────────────────── 訓練：半局剩餘得分紀錄（記憶體版快照機器） ─────────────────────────
def iter_half_pa_records(events: list[dict]) -> list[tuple[str, str, int, int]]:
    """單場事件 → [(side, bases, outs, rest), ...]。

    與 winprob.build_run_dist 逐行同語意（獨立第二實作，等價性以生產
    cpbl.run_dist 2018-2025/A 逐列對帳證明）：非更換列打席首事件、事件前比分
    =前列事件後比分、排除每場末半局、rest<0 略過、outs 夾 0..2。
    """
    pv, ph = 0, 0
    for e in events:
        e["_pre_vs"], e["_pre_hs"] = pv, ph
        pv = e["visiting_score"] if e.get("visiting_score") is not None else pv
        ph = e["home_score"] if e.get("home_score") is not None else ph
        e["_post_vs"], e["_post_hs"] = pv, ph
    halves: dict[tuple, list[dict]] = defaultdict(list)
    order: list[tuple] = []
    for e in events:
        k = (e["inning_seq"], str(e["visiting_home_type"]))
        if k not in halves:
            order.append(k)
        halves[k].append(e)
    out: list[tuple[str, str, int, int]] = []
    for hk in order[:-1]:                  # 排除末半局（再見截斷母體）
        vht = hk[1]
        pre_k = "_pre_vs" if vht == "1" else "_pre_hs"
        post_k = "_post_vs" if vht == "1" else "_post_hs"
        evs = [e for e in halves[hk] if not e.get("is_change_player")
               and e.get("hitter_acnt")]
        if not evs:
            continue
        end_score = max(e[post_k] for e in halves[hk])
        seen: set = set()
        for e in evs:
            pa_key = (e.get("batting_order"), e.get("hitter_acnt"))
            if pa_key in seen:
                continue
            seen.add(pa_key)
            bases = (("1" if e.get("first_base") else "_")
                     + ("2" if e.get("second_base") else "_")
                     + ("3" if e.get("third_base") else "_"))
            outs = min(int(e.get("out_cnt") or 0), 2)
            rest = end_score - e[pre_k]
            if rest < 0:
                continue
            out.append((vht, bases, outs, min(rest, K_CAP)))
    return out


def collect_training_counts(cur, kind: str, from_year: int, to_year: int
                            ) -> dict[int, Counter]:
    """逐年收集 (side,bases,outs,k) 計數；之後任意年窗聚合零成本。"""
    per_year: dict[int, Counter] = {}
    for year in range(from_year, to_year + 1):
        cur.execute(
            "SELECT game_sno, main_event_no, inning_seq, visiting_home_type, "
            "batting_order, out_cnt, is_change_player, hitter_acnt, "
            "first_base, second_base, third_base, visiting_score, home_score "
            "FROM cpbl.game_livelog WHERE year=%s AND kind_code=%s", (year, kind))
        cols = [d[0] for d in cur.description]
        by_game: dict[int, list[dict]] = defaultdict(list)
        for row in cur.fetchall():
            e = dict(zip(cols, row, strict=True))
            by_game[e["game_sno"]].append(e)
        cnt: Counter = Counter()
        for events in by_game.values():
            events.sort(key=lambda r: int(r["main_event_no"]))
            for side, bases, outs, k in iter_half_pa_records(events):
                cnt[(side, bases, outs, k)] += 1
        per_year[year] = cnt
        log.info("training %s %d：%d 場，%d 紀錄", kind, year, len(by_game),
                 sum(cnt.values()))
    return per_year


def dist_from_counts(per_year: dict[int, Counter], y0: int, y1: int
                     ) -> dict[tuple[str, str, int], list[float]]:
    """年窗聚合 → run_dist（同 build_run_dist 的 n>=30 門檻與 5 位捨入）。"""
    agg: dict[tuple[str, str, int], list[int]] = defaultdict(lambda: [0] * (K_CAP + 1))
    for y in range(y0, y1 + 1):
        for (side, bases, outs, k), v in per_year.get(y, {}).items():
            agg[(side, bases, outs)][k] += v
    dist: dict[tuple[str, str, int], list[float]] = {}
    for state, ks in agg.items():
        n = sum(ks)
        if n < MIN_STATE_N:
            continue
        dist[state] = [round(v / n, 5) for v in ks]
    return dist


def load_production_dist(cur, span: str, kind: str
                         ) -> dict[tuple[str, str, int], list[float]] | None:
    """讀取生產 artifact（cpbl.run_dist）作對照模型；不存在回 None。"""
    cur.execute("SELECT side, bases, outs, k, p FROM cpbl.run_dist "
                "WHERE span=%s AND kind_code=%s", (span, kind))
    rows = cur.fetchall()
    if not rows:
        return None
    out: dict[tuple[str, str, int], list[float]] = defaultdict(lambda: [0.0] * (K_CAP + 1))
    for s, b, o, k, p in rows:
        out[(s, b, o)][k] = float(p)
    return dict(out)


# ───────────────────────── WE 邊界 DP（規則參數化） ─────────────────────────
def we_solver_rules(dist: dict, rules: RuleSet):
    """winprob._we_solver 的規則參數化推廣；legacy 規則（12 局和局、無突破僵局）
    下與生產解算器逐值相等（tests/test_winprob_val.py 驗證）。"""
    d0_top = dist[("1", "___", 0)]
    d0_bot = dist[("2", "___", 0)]
    # 突破僵局：延長半局開局二壘有跑者；訓練窗若無 (_2_,0) 樣本則退回空壘（記警告）
    tb_top = dist.get(("1", "_2_", 0), d0_top)
    tb_bot = dist.get(("2", "_2_", 0), d0_bot)
    clip = lambda d: max(-DIFF_CLIP, min(DIFF_CLIP, d))  # noqa: E731

    def start_dist(side: str, inning: int) -> list[float]:
        if rules.tiebreak_from and inning >= rules.tiebreak_from:
            return tb_top if side == "1" else tb_bot
        return d0_top if side == "1" else d0_bot

    @cache
    def we_bot(i: int, d: int) -> tuple[float, float]:
        w = t = 0.0
        for k, p in enumerate(start_dist("2", i)):
            if not p:
                continue
            nd = d + k
            if i >= REGULATION:
                if nd > 0:
                    w += p
                elif i >= rules.max_inning:
                    t += p if nd == 0 else 0.0
                elif nd == 0:
                    nw, nt = we_top(i + 1, 0)
                    w += p * nw
                    t += p * nt
            else:
                nw, nt = we_top(i + 1, clip(nd))
                w += p * nw
                t += p * nt
        return (w, t)

    @cache
    def we_top(i: int, d: int) -> tuple[float, float]:
        w = t = 0.0
        for k, p in enumerate(start_dist("1", i)):
            if not p:
                continue
            nd = clip(d - k)
            if i >= REGULATION and nd > 0:
                w += p
            else:
                nw, nt = we_bot(i, nd)
                w += p * nw
                t += p * nt
        return (w, t)

    return we_top, we_bot


def wp_state_rules(dist: dict, we_top, we_bot, rules: RuleSet, inning: int,
                   vht: str, diff: int, bases: str, outs: int) -> float:
    """半局進行中任意狀態的主隊 WP（勝 + 0.5×和）；winprob.wp_state 的規則參數化。"""
    dk = dist.get((vht, bases, min(outs, 2))) or dist[(vht, "___", 0)]
    w = t = 0.0
    clip = lambda d: max(-DIFF_CLIP, min(DIFF_CLIP, d))  # noqa: E731
    inning = min(inning, rules.max_inning)
    for k, p in enumerate(dk):
        if not p:
            continue
        if vht == "1":
            nd = clip(diff - k)
            if inning >= REGULATION and nd > 0:
                w += p
            else:
                nw, nt = we_bot(inning, nd)
                w += p * nw
                t += p * nt
        else:
            nd = diff + k
            if inning >= REGULATION:
                if nd > 0:
                    w += p
                elif nd == 0:
                    if inning >= rules.max_inning:
                        t += p
                    else:
                        nw, nt = we_top(inning + 1, 0)
                        w += p * nw
                        t += p * nt
            else:
                nw, nt = we_top(inning + 1, clip(nd))
                w += p * nw
                t += p * nt
    return w + 0.5 * t


# ───────────────────────── 打席前比分（跨消費者共用的唯一實作）─────────────────────────
def pre_scores_from_events(pa_rows: list[dict], events: list[dict]) -> dict[int, tuple[int, int]]:
    """``pa_index`` → 該打席**開始之前**的 ``(away, home)``（純函式）。

    唯一正確的打席前比分來源：以 ``start_event_no`` 對回事件流，取
    :func:`cpbl.models.pa_facts.annotate_scores` 標上的「事件**之前**」running 比分。
    **不可讀 ``pre_state.away_score``／``home_score``**——那是起始事件列的比分欄原值，
    而 livelog 的比分欄是事件**後**快照（DATA-RECAP-WP-PRESTATE1／#96）。

    對不回事件流的打席**不進 map**（fail closed，由呼叫端標 ``pre_score_unresolved``），
    不以 ``pre_state`` 的值冒充。

    **住在這裡的理由**（ML-WP-VAL-RESAMPLE1 上抽；原本住 ``api/routers/recap.py``）：
    消費者有兩個——``api/routers/recap``（``/recap-wp`` 生產路徑）與本模組的驗證
    harness——而 ``models`` 不得 import ``api``；留在 api 側還會構成
    ``winprob_val → recap → winprob_scorer → winprob_val`` 迴圈。同一條紅線只能有一份
    實作（本卡的病灶正是同一語意有兩份讀法），故上抽到 models 由兩邊共用，
    ``recap`` 以別名 re-export 保持既有 import 路徑相容（同 ``winprob_scorer`` 前例）。

    ⚠️ 語意上更貼近的家其實是 ``models/pa_facts``（就在 ``annotate_scores`` 隔壁），
    但該檔不在本卡寫入集；若日後獲授權，搬過去只是移動函式 + 調整 re-export。
    """
    ordered = annotate_scores(events)
    by_event_no = {str(e["main_event_no"]): e for e in ordered}
    scores: dict[int, tuple[int, int]] = {}
    for row in pa_rows:
        start = row.get("start_event_no")
        event = by_event_no.get(str(start)) if start is not None else None
        if event is None:
            continue
        scores[row["pa_index"]] = (event["_pre_away"], event["_pre_home"])
    return scores


# ───────────────────────── 驗證資料：canonical PA + 賽果 ─────────────────────────
PRE_SCORE_SOURCES = ("events", "pre_state")


def _resolve_pre_scores(cur, kind: str, year: int,
                        pa_rows_by_game: dict[int, list[dict]]) -> dict[tuple[int, int], tuple[int, int]]:
    """``(game_sno, pa_index)`` → 該打席**開始之前**的 ``(away, home)``。

    語意與紅線見 :func:`pre_scores_from_events`；此處只負責取事件流與逐場分組。
    """
    cur.execute(
        "SELECT game_sno, main_event_no, visiting_score, home_score "
        "FROM cpbl.game_livelog WHERE year=%s AND kind_code=%s", (year, kind))
    events_by_game: dict[int, list[dict]] = defaultdict(list)
    for sno, event_no, visiting, home in cur.fetchall():
        events_by_game[sno].append({"main_event_no": event_no,
                                    "visiting_score": visiting, "home_score": home})
    resolved: dict[tuple[int, int], tuple[int, int]] = {}
    for sno, rows in pa_rows_by_game.items():
        # 全場逐事件都要餵進去：annotate_scores 是 running 比分，只取打席起始列
        # 會漏掉打席**之間**造成得分的事件（盜壘／暴投）。
        for index, score in pre_scores_from_events(rows, events_by_game.get(sno, [])).items():
            resolved[(sno, index)] = score
    return resolved


def load_eval_season(cur, kind: str, year: int, *,
                     pre_score_source: str = "events") -> dict:
    """驗證季資料：published build 的 canonical PA + games 賽果 + 場況分類。

    fail closed：只評 state='ready'；其餘逐 state 計數回報。
    irregular（敏感度切片）：縮短賽（<9 局）、未達和局上限的和局（宵禁/雙重賽
    首場）、保留賽（delay_kind 非空）。

    ``pre_score_source``（ML-WP-VAL-RESAMPLE1）：
    * ``"events"``（預設，唯一正確）：局面分差取**打席前**比分，由事件流解出。
      解不出來的 ready 打席 fail closed 排除並計入 ``ready_pre_score_unresolved``。
    * ``"pre_state"``：**已知受污染的舊讀法**，只保留給 A/B 對照用。canonical
      ``pre_state.away_score``／``home_score`` 是起始事件列的比分欄原值，而 livelog
      的比分欄是事件**後**快照——單一事件即結束的得分打席（首球全壘打等）起始列
      ＝終結列，存到的已是得分**後**的比分（DATA-RECAP-WP-PRESTATE1）。**不得用於
      任何對外數字**。
    """
    if pre_score_source not in PRE_SCORE_SOURCES:
        raise ValueError(f"pre_score_source 必須是 {PRE_SCORE_SOURCES} 之一：{pre_score_source}")
    cur.execute(
        "SELECT g.game_sno, g.home_score, g.away_score, g.delay_kind, mx.max_inn "
        "FROM cpbl.games g "
        "LEFT JOIN (SELECT year, kind_code, game_sno, max(inning_seq) AS max_inn "
        "           FROM cpbl.game_livelog GROUP BY 1,2,3) mx "
        "  ON mx.year=g.year AND mx.kind_code=g.kind_code AND mx.game_sno=g.game_sno "
        "WHERE g.year=%s AND g.kind_code=%s "
        "AND g.home_score + g.away_score > 0 AND g.game_date <= CURRENT_DATE",
        (year, kind))
    rules = ruleset_for(kind, year)
    games: dict[int, dict] = {}
    for sno, hs, aw, delay, max_inn in cur.fetchall():
        outcome = 1.0 if hs > aw else (0.0 if hs < aw else 0.5)
        tie = hs == aw
        irregular = ((max_inn is not None and max_inn < REGULATION)
                     or (tie and max_inn is not None and max_inn < rules.max_inning)
                     or delay is not None)
        games[sno] = {"outcome": outcome, "irregular": irregular}
    cur.execute(
        "SELECT pa.game_sno, pa.state, pa.pre_state, pa.pa_index, pa.start_event_no "
        "FROM cpbl.game_plate_appearances pa "
        "JOIN cpbl.game_recap_builds b ON b.build_id = pa.build_id "
        "  AND b.state = 'published' "
        "WHERE pa.year=%s AND pa.kind_code=%s", (year, kind))
    # 先物化：打席前比分要以「整場事件流」解，必須先看過全季所有列才能逐場分組。
    # 之後的計數／建樣本迴圈**沿用同一份 fetch 順序**——叢集 bootstrap 以
    # `list(by_game.values())` 抽樣，順序變動會改變抽出的重抽樣本（紅線：重放
    # harness 必須忠實既有累加順序）。
    fetched = list(cur.fetchall())
    pa_rows_by_game: dict[int, list[dict]] = defaultdict(list)
    for sno, _state, _pre, pa_index, start_event_no in fetched:
        pa_rows_by_game[sno].append({"pa_index": pa_index, "start_event_no": start_event_no})
    pre_scores = (_resolve_pre_scores(cur, kind, year, pa_rows_by_game)
                  if pre_score_source == "events" else {})
    pas: list[dict] = []
    state_counts: Counter = Counter()
    built_games: set[int] = set()
    for sno, state, pre, pa_index, _start_event_no in fetched:
        built_games.add(sno)
        state_counts[state] += 1
        if state != "ready" or sno not in games:
            continue
        if any(pre.get(f) is None for f in ("inning", "half", "outs",
                                            "home_score", "away_score")):
            # fail closed：pre_state 關鍵欄位缺值（僅 2018–2020 livelog 早年
            # out_cnt 缺值，2021+ 為 0）→ 不評分、獨立計數回報
            #
            # 判準刻意**不動**（含已不再用於 diff 的 home_score/away_score）：本卡要量的
            # 是「同一批打席換一把尺」的差異，改動母體會把取樣修正與母體變動混在一起。
            state_counts["ready_incomplete_state"] += 1
            continue
        if pre_score_source == "events":
            resolved = pre_scores.get((sno, pa_index))
            if resolved is None:
                # fail closed：打席起始事件對不回事件流 → 不評分，不以受污染的
                # pre_state 值冒充（同 recap 的 pre_score_unresolved 語意）
                state_counts["ready_pre_score_unresolved"] += 1
                continue
            away_score, home_score = resolved
        else:
            away_score, home_score = int(pre["away_score"]), int(pre["home_score"])
        bs = pre.get("bases") or []
        pas.append({
            "game_sno": sno,
            "pa_index": pa_index,            # A/B 對照與逐打席稽核的對齊鍵
            "game_key": (year, kind, sno),   # 跨季池化時的叢集鍵
            "inning": int(pre["inning"]),
            "vht": str(pre["half"]),
            "diff": int(home_score) - int(away_score),
            "bases": (("1" if "1" in bs else "_") + ("2" if "2" in bs else "_")
                      + ("3" if "3" in bs else "_")),
            "outs": int(pre["outs"]),
            "outcome": games[sno]["outcome"],
            "irregular": games[sno]["irregular"],
        })
    n_completed = len(games)
    coverage = (len(built_games & set(games)) / n_completed) if n_completed else 0.0
    return {
        "year": year, "kind": kind, "rules": rules,
        "games": games, "pas": pas,
        "pre_score_source": pre_score_source,
        "n_completed_games": n_completed,
        "n_built_games": len(built_games & set(games)),
        "coverage": round(coverage, 4),
        "pa_state_counts": dict(state_counts),
        "n_irregular_games": sum(1 for g in games.values() if g["irregular"]),
    }


# ───────────────────────── 指標 ─────────────────────────
def score_pas(dist: dict, rules: RuleSet, pas: list[dict]
              ) -> list[tuple[float, float, bool, object]]:
    """回傳 [(wp, outcome, irregular, game_key), ...]；game_key 供叢集 bootstrap。"""
    we_top, we_bot = we_solver_rules(dist, rules)
    return [(wp_state_rules(dist, we_top, we_bot, rules, p["inning"], p["vht"],
                            p["diff"], p["bases"], p["outs"]),
             p["outcome"], p["irregular"], p.get("game_key", p["game_sno"]))
            for p in pas]


def _decile_bins(rows: list[tuple[float, float]]) -> list[list[float]]:
    bins = [[0.0, 0.0, 0] for _ in range(10)]
    for wp, y in rows:
        b = bins[min(int(wp * 10), 9)]
        b[0] += wp
        b[1] += y
        b[2] += 1
    return bins


def _game_bin_matrix(scored: Sequence[tuple[float, float, bool, object]]
                     ) -> tuple[np.ndarray, list[object]]:
    """逐場 × 十分位的 (Σwp, Σy, n) 矩陣，形狀 (n_games, 30)。

    累加順序＝`scored` 的出場順序，與 v2 的 `by_game.setdefault` 逐列累加逐位相同
    （紅線：重放 harness 必須忠實既有累加順序）。
    """
    by_game: dict[object, list[float]] = {}
    order: list[object] = []
    for wp, y, _, gk in scored:
        row = by_game.get(gk)
        if row is None:
            row = by_game[gk] = [0.0] * 30
            order.append(gk)
        off = min(int(wp * 10), 9) * 3
        row[off] += wp
        row[off + 1] += y
        row[off + 2] += 1.0
    return np.array([by_game[g] for g in order], dtype=np.float64), order


def _resample_counts(n_games: int, reps: int, seed: int) -> np.ndarray:
    """(reps, n_games) 的整場重抽次數矩陣。

    索引序列刻意逐個重現 `random.Random(seed).choices(games, k=n)`
    （CPython 的無權重 `choices` 即 `floor(random() * n)`，逐次呼叫、rep-major），
    故 v3 的向量化重抽與 v2 的純 Python 迴圈**抽到同一批場次**——
    判定的差異只能來自機制，不能來自實作漂移（tests 以參考實作釘住）。
    """
    rng_random = random.Random(seed).random
    total = reps * n_games
    idx = np.fromiter((int(rng_random() * n_games) for _ in range(total)),
                      dtype=np.int64, count=total).reshape(reps, n_games)
    flat = (np.arange(reps, dtype=np.int64)[:, None] * n_games + idx).ravel()
    return np.bincount(flat, minlength=reps * n_games).reshape(reps, n_games).astype(np.float64)


def _bin_devs_for_seed(gmat: np.ndarray, reps: int, seed: int) -> np.ndarray:
    """(reps, 10) 的逐分箱偏差；該 rep 該分箱無樣本者為 NaN（v2 是略過不計）。"""
    counts = _resample_counts(gmat.shape[0], reps, seed)
    agg = (counts @ gmat).reshape(reps, 10, 3)
    n = agg[:, :, 2]
    with np.errstate(invalid="ignore", divide="ignore"):
        devs = np.where(n > 0, (agg[:, :, 0] - agg[:, :, 1]) / n, np.nan)
    return devs


def _wilson(k: int, n: int, z: float) -> tuple[float, float]:
    """比例的 Wilson 區間；k=0／k=n 也給得出有限寬度（Wald 在端點會塌成 0）。"""
    if n <= 0:
        return (0.0, 1.0)
    ph = k / n
    denom = 1.0 + z * z / n
    centre = ph + z * z / (2 * n)
    rad = z * math.sqrt(ph * (1 - ph) / n + z * z / (4 * n * n))
    return (max(0.0, (centre - rad) / denom), min(1.0, (centre + rad) / denom))


def _tail_state(devs: np.ndarray, ci: float, z: float) -> dict:
    """把一組 bootstrap 重抽值化為「與 0 有無差異」的**三態**決策。

    為什麼不是「CI 端點含不含 0」（v2 的做法）：那等價於拿單一 seed 估出的
    **極端分位數**當硬性判準，而 500 次重抽估 0.5% 分位數只倚賴 ~2.5 個次序統計量，
    Monte Carlo 誤差大到足以讓邊界分箱的 Go/No-Go 翻面（RESAMPLE1 §5 實測）。

    v3 改判**母體語意等價、但估得準**的量：單尾機率 `p_one = P(dev 跨過 0 的那一側)`。
    百分位法下「99% CI 排除 0」與 `p_one < α_one`（`α_one = (1-ci)/2`）**在精確算術下
    等價**——CI 排除 0 ⟺ `k ≤ floor(α_one·(n-1))`，`p_one < α_one` ⟺
    `k ≤ ceil(α_one·n) - 1`，兩者對所有整數 n 相同（`tests` 以 `Fraction` 窮舉 n=2..300,000
    釘住）。**但它不是實作層的精確恆等**，本實作有兩處有限樣本偏離，方向都是
    「更難判顯著」（保守）：

    1. `α_one` 由 `(1 - ci)/2` 以二進位浮點算出（0.99 → 0.0050000000000000044 ≠ 1/200），
       在 `k` 正好落在 `α_one·n` 的邊界時兩式會分岔（實測 n=6,000 的 k=30、n=12,000 的
       k=60）；
    2. :func:`_percentile_ci` 回傳前把端點捨入到小數 4 位，真實下界若是微小正值
       （如 3e-5）會被讀成 0.0，於是「排除 0」判否。

    判定實際採用的是 Wilson 區間對 α_one 的比較（見下），**不是**上面任一個式子，
    故這兩處偏離不影響任何判定；寫在這裡是因為這句話是本機制的核心語意，
    後人可能拿它當恆等式往上推導（ROBUST1-R1-01）。

    p_one 是所有重抽的平均，MC 誤差是標準的二項誤差，可直接量：對 p̂ 配一個 Wilson 區間
    （水準 z，**計算容忍度**），再拿整條區間與 α_one 比：

    * 區間整段在 α_one 之下 → `significant`（再多抽也不會翻）
    * 區間整段在 α_one 之上 → `not_significant`
    * 區間跨過 α_one → `undetermined`——「這台機器在目前重抽預算下解析不出來」，
      **既不是通過也不是失敗**。這就是 v2 缺的那一格：它會把這種情況按 seed 運氣
      隨機丟進 significant 或 not_significant。

    近似處：p̂ 取單尾計數故為真二項；跨 seed 池化的重抽在同一份資料上並非完全獨立
    （共用同一批場次），但 MC 誤差本身只由重抽次數決定，池化不改變這一點。
    """
    valid = devs[~np.isnan(devs)]
    n = int(valid.size)
    if n == 0:
        return {"n_reps": 0, "state": SIG_UNDETERMINED, "p_one": None,
                "p_one_mc_ci": None}
    k = int(min((valid <= 0).sum(), (valid >= 0).sum()))
    alpha_one = (1 - ci) / 2
    lo, hi = _wilson(k, n, z)
    if hi < alpha_one:
        state = SIG_SIGNIFICANT
    elif lo > alpha_one:
        state = SIG_NOT_SIGNIFICANT
    else:
        state = SIG_UNDETERMINED
    return {"n_reps": n, "state": state, "p_one": round(k / n, 6),
            "p_one_mc_ci": [round(lo, 6), round(hi, 6)], "alpha_one": alpha_one}


def _percentile_ci(devs: np.ndarray, ci: float) -> list[float]:
    valid = np.sort(devs[~np.isnan(devs)])
    if valid.size == 0:
        return [0.0, 0.0]
    lo_q, hi_q = (1 - ci) / 2, 1 - (1 - ci) / 2
    n = valid.size
    return [round(float(valid[int(lo_q * (n - 1))]), 4),
            round(float(valid[int(hi_q * (n - 1))]), 4)]


def cluster_bootstrap_devs(scored: Sequence[tuple[float, float, bool, object]],
                           reps: int, ci: float, seed: int = LEGACY_BOOT_SEED
                           ) -> dict[int, dict]:
    """**v2 相容入口**：單一 seed 的逐十分位 SE 與百分位 CI。

    保留是因為 `docs/research/ML-WP-VAL-RESAMPLE1/bin_stability.py`（已交付、
    不在本卡寫入集）以此簽章呼叫，且 v3 的逐分箱 `dev_ci_legacy_seed` 也靠它產生
    A/B 對照。實作已換成向量化重抽，抽樣序列與舊版逐個相同（見 `_resample_counts`）。

    **不要拿它的 `ci` 當判定依據**——單一 seed 的極端分位數正是本卡要修掉的病灶。
    """
    gmat, _ = _game_bin_matrix(scored)
    if gmat.size == 0:
        return {}
    devs = _bin_devs_for_seed(gmat, reps, seed)
    out: dict[int, dict] = {}
    for i in range(10):
        col = devs[:, i]
        valid = col[~np.isnan(col)]
        if valid.size == 0:
            continue
        out[i] = {"se": round(float(valid.std(ddof=1)) if valid.size > 1 else 0.0, 4),
                  "ci": _percentile_ci(col, ci)}
    return out


def seed_ladder(k: int, base: Sequence[int] = BOOT_SEEDS) -> list[int]:
    """前 k 個 bootstrap seed：註冊 seed 集打頭，之後由固定串流確定性延伸。"""
    seeds = list(base)
    rng = random.Random(BOOT_LADDER_SEED)
    seen = set(seeds)
    while len(seeds) < k:
        s = rng.randrange(1, 2 ** 31)
        if s not in seen:
            seen.add(s)
            seeds.append(s)
    return seeds[:k]


def _escalate(compute, *, reps: int, base_seeds: Sequence[int], max_reps: int):
    """重抽預算自動加碼：解析不出來就把 seed 集倍增，直到解析得出來或撞上限。

    **為什麼需要**：三態判定若停在固定的 seed 數上，「undetermined」就只是
    「我沒抽夠」的別名，而「註冊了幾個 seed」會變成新的任意數字直接左右 Go/No-Go
    （本卡實測：D 池化十分位 2 在 6,000 次重抽下 undetermined，加碼後即解析）。
    加碼後，唯一還會左右結果的任意數字只剩 :data:`BOOT_MAX_REPS` 這個**上限**，
    而撞上限是可觀測、可回報的事件（`hit_reps_cap`）。

    `compute(seeds)` 須回傳 `(結果, 是否還有 undetermined)`。
    """
    n = len(base_seeds)
    while True:
        seeds = seed_ladder(n)
        result, unresolved = compute(seeds)
        total = n * reps
        if not unresolved or total * 2 > max_reps:
            return result, seeds, total, bool(unresolved)
        n *= 2


def cluster_bootstrap_bins(scored: Sequence[tuple[float, float, bool, object]], *,
                           reps: int, ci: float,
                           seeds: Sequence[int] = BOOT_SEEDS,
                           max_reps: int = BOOT_MAX_REPS) -> dict[int, dict]:
    """v3 逐十分位不確定度：跨 seed 池化的 SE／CI／尾機率三態＋預算自動加碼。

    另回報 `n_seeds_significant`——**註冊 12 seed** 各自以 v2 的判準（該 seed 的
    百分位 CI 含不含 0）投一票。這一欄不參與判定，只是把 RESAMPLE1 §5 那份手動
    診斷收進 harness，讓「這個分箱在 v2 下有多會擲硬幣」在 artifact 裡直接看得到。
    """
    gmat, _ = _game_bin_matrix(scored)
    if gmat.size == 0:
        return {}
    cache: dict[int, np.ndarray] = {}

    def compute(seed_set: Sequence[int]):
        for s in seed_set:
            if s not in cache:
                cache[s] = _bin_devs_for_seed(gmat, reps, s)
        pooled = np.concatenate([cache[s] for s in seed_set], axis=0)
        states = {}
        unresolved = False
        for i in range(10):
            col = pooled[:, i]
            if col[~np.isnan(col)].size == 0:
                continue
            states[i] = (col, _tail_state(col, ci, MC_TOLERANCE_Z))
            unresolved |= states[i][1]["state"] == SIG_UNDETERMINED
        return states, unresolved

    states, _used_seeds, total_reps, hit_cap = _escalate(
        compute, reps=reps, base_seeds=seeds, max_reps=max_reps)
    out: dict[int, dict] = {}
    for i, (col, tail) in states.items():
        valid = col[~np.isnan(col)]
        votes = 0
        legacy_ci = None
        for s in seeds:                      # 投票一律以註冊 seed 集為準
            lo, hi = _percentile_ci(cache[s][:, i], ci)
            if s == LEGACY_BOOT_SEED:
                legacy_ci = [lo, hi]
            votes += int(lo > 0 or hi < 0)
        out[i] = {
            "se": round(float(valid.std(ddof=1)) if valid.size > 1 else 0.0, 4),
            "ci": _percentile_ci(col, ci),
            "ci_legacy_seed": legacy_ci,
            "sig_state": tail["state"],
            "p_one": tail["p_one"],
            "p_one_mc_ci": tail["p_one_mc_ci"],
            "n_seeds_significant": votes,
            "n_seeds": len(seeds),
            "reps_total": total_reps,
            "hit_reps_cap": hit_cap and tail["state"] == SIG_UNDETERMINED,
        }
    return out


def cluster_bootstrap_brier_delta(scored: Sequence[tuple[float, float, bool, object]],
                                  baseline_p: float, *, reps: int, ci: float,
                                  seeds: Sequence[int] = BOOT_SEEDS,
                                  max_reps: int = BOOT_MAX_REPS) -> dict:
    """`Brier(模型) − Brier(全押主場常數)` 的整場重抽不確定度（同一台三態機器）。

    存在理由：v2 拿**單季點估計**「Brier 未勝過基準」當硬性失敗，於是 E2025 那樣
    只有 4 場的季就能一票否決整個 scope（RESEARCH-VERDICT-AUDIT1 §3.1-E）。
    Δ 的不確定度一量出來，「輸給基準」與「測不出誰贏」就分得開。
    """
    by_game: dict[object, list[float]] = {}
    order: list[object] = []
    for wp, y, _, gk in scored:
        row = by_game.get(gk)
        if row is None:
            row = by_game[gk] = [0.0, 0.0, 0.0]
            order.append(gk)
        row[0] += (wp - y) ** 2
        row[1] += (baseline_p - y) ** 2
        row[2] += 1.0
    if not order:
        return {"n_games": 0, "delta": None, "sig_state": SIG_UNDETERMINED}
    gmat = np.array([by_game[g] for g in order], dtype=np.float64)
    cache: dict[int, np.ndarray] = {}

    def compute(seed_set: Sequence[int]):
        for s in seed_set:
            if s not in cache:
                agg = _resample_counts(gmat.shape[0], reps, s) @ gmat
                cache[s] = (agg[:, 0] - agg[:, 1]) / agg[:, 2]
        pooled = np.concatenate([cache[s] for s in seed_set])
        tail = _tail_state(pooled, ci, MC_TOLERANCE_Z)
        return (pooled, tail), tail["state"] == SIG_UNDETERMINED

    (pooled, tail), _used_seeds, total_reps, hit_cap = _escalate(
        compute, reps=reps, base_seeds=seeds, max_reps=max_reps)
    votes = 0
    legacy_ci = None
    for s in seeds:
        lo, hi = _percentile_ci(cache[s], ci)
        if s == LEGACY_BOOT_SEED:
            legacy_ci = [lo, hi]
        votes += int(lo > 0 or hi < 0)
    total = gmat.sum(axis=0)
    return {
        "n_games": len(order),
        "delta": round(float((total[0] - total[1]) / total[2]), 5),
        "se": round(float(pooled.std(ddof=1)), 5),
        "ci": _percentile_ci(pooled, ci),
        "ci_legacy_seed": legacy_ci,
        "sig_state": tail["state"],
        "p_one": tail["p_one"],
        "p_one_mc_ci": tail["p_one_mc_ci"],
        "n_seeds_significant": votes,
        "n_seeds": len(seeds),
        "reps_total": total_reps,
        "hit_reps_cap": hit_cap and tail["state"] == SIG_UNDETERMINED,
    }


def null_ece_reference(deciles: Sequence[dict]) -> dict | None:
    """完美校準零假設下，這個樣本量會量到多大的 ECE。

    ECE 是**加權絕對**偏差，有限樣本下恆為正偏——完美校準的模型也量不到 0。
    在 H0: `dev_b ~ N(0, se_b)`（se_b 直接用同一份 game-cluster bootstrap SE，
    不引入新的變異假設）下 `E[ECE] = Σ w_b·se_b·√(2/π)`，另以 Monte Carlo 取分位數。

    方法出處 `RESEARCH-VERDICT-AUDIT1/analyze_gates.py`（本卡把它從事後稽核腳本
    收進 harness 本體，讓「這道門檻在這個樣本量下可不可能通過」變成判定的一部分，
    而不是要有人事後另外算一次）。近似兩處（分箱間獨立、常態）方向不定，
    故只作**量級**判讀、不當正式檢定——但量級差距大到判讀不受近似影響。
    """
    ses = [d.get("dev_se") for d in deciles]
    ns = [d.get("n") for d in deciles]
    if not deciles or any(s is None for s in ses) or not sum(ns):
        return None
    se = np.array(ses, dtype=float)
    w = np.array(ns, dtype=float)
    w = w / w.sum()
    rng = np.random.default_rng(NULL_ECE_MC_SEED)
    sim = np.abs(rng.normal(0.0, 1.0, size=(NULL_ECE_MC_REPS, se.size)) * se) @ w
    return {
        "analytic_mean": round(float((w * se * HALF_NORMAL_MEAN).sum()), 5),
        "mc_mean": round(float(sim.mean()), 5),
        "mc_p95": round(float(np.quantile(sim, 0.95)), 5),
        "mc_reps": NULL_ECE_MC_REPS,
        "mc_seed": NULL_ECE_MC_SEED,
    }


def metrics(scored: Sequence[tuple[float, float, bool, object]], *,
            exclude_irregular: bool = False, bootstrap: bool = False) -> dict:
    rows = [(wp, y) for wp, y, irr, _ in scored if not (exclude_irregular and irr)]
    n = len(rows)
    if not n:
        return {"n_pa": 0}
    brier = sum((wp - y) ** 2 for wp, y in rows) / n
    bins = _decile_bins(rows)
    deciles = [{"bin": i, "pred": round(sw / bn, 4), "actual": round(so / bn, 4),
                "n": bn} for i, (sw, so, bn) in enumerate(bins) if bn]
    ece = sum(abs(d["pred"] - d["actual"]) * d["n"] for d in deciles) / n
    big = [abs(d["pred"] - d["actual"]) for d in deciles if d["n"] >= 300]
    out = {
        "n_pa": n,
        "n_games": len({gk for _, _, irr, gk in scored
                        if not (exclude_irregular and irr)}),
        "brier": round(brier, 5),
        "ece_weighted": round(ece, 5),
        "decile_max_dev": round(max(big), 4) if big else None,
        "deciles": deciles,
    }
    if bootstrap:
        kept = [r for r in scored if not (exclude_irregular and r[2])]
        cis = cluster_bootstrap_bins(kept, reps=THRESHOLDS["boot_reps"],
                                     ci=THRESHOLDS["boot_ci"])
        sig, undet = [], []
        for d in deciles:
            c = cis.get(d["bin"])
            if not c:
                continue
            d["dev_se"] = c["se"]
            d["dev_ci"] = c["ci"]
            d["dev_ci_legacy_seed"] = c["ci_legacy_seed"]
            d["sig_state"] = c["sig_state"]
            d["p_one"] = c["p_one"]
            d["p_one_mc_ci"] = c["p_one_mc_ci"]
            d["n_seeds_significant"] = c["n_seeds_significant"]
            d["n_seeds"] = c["n_seeds"]
            d["reps_total"] = c["reps_total"]
            d["hit_reps_cap"] = c["hit_reps_cap"]
            if d["n"] >= 300:
                if c["sig_state"] == SIG_SIGNIFICANT:
                    sig.append(d["bin"])
                elif c["sig_state"] == SIG_UNDETERMINED:
                    undet.append(d["bin"])
        out["significant_bins"] = sig
        # v3 新增：解析不出來的分箱**必須自成一格**，不能默默併進上面那條或消失。
        out["undetermined_bins"] = undet
        out["null_ece"] = null_ece_reference(deciles)
    return out


def brier_constant(scored: Sequence[tuple[float, float, bool, object]], p: float) -> float:
    rows = [y for _, y, _, _ in scored]
    return round(sum((p - y) ** 2 for y in rows) / len(rows), 5) if rows else 0.0


def home_rate_from_games(cur, kind: str, y0: int, y1: int) -> float:
    """訓練窗聯盟主隊勝率（和=0.5）；作「全押主場」常數基準（leakage-safe）。"""
    cur.execute(
        "SELECT avg(CASE WHEN home_score>away_score THEN 1.0 "
        "WHEN home_score<away_score THEN 0.0 ELSE 0.5 END) FROM cpbl.games "
        "WHERE year BETWEEN %s AND %s AND kind_code=%s "
        "AND home_score+away_score>0 AND game_date<=CURRENT_DATE", (y0, y1, kind))
    v = cur.fetchone()[0]
    return round(float(v), 4) if v is not None else 0.5


def inning_slices(scored_pas: list[dict], dist: dict, rules: RuleSet) -> dict:
    """依局數帶（1-3/4-6/7-9/10+）分箱的校準摘要——直接檢驗 9 局門檻、
    和局與突破僵局邊界的統計行為。"""
    we_top, we_bot = we_solver_rules(dist, rules)
    groups: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for p in scored_pas:
        wp = wp_state_rules(dist, we_top, we_bot, rules, p["inning"], p["vht"],
                            p["diff"], p["bases"], p["outs"])
        g = ("1-3" if p["inning"] <= 3 else "4-6" if p["inning"] <= 6
             else "7-9" if p["inning"] <= 9 else "10+")
        groups[g].append((wp, p["outcome"]))
    out = {}
    for g, rows in sorted(groups.items()):
        n = len(rows)
        out[g] = {"n": n,
                  "pred": round(sum(w for w, _ in rows) / n, 4),
                  "actual": round(sum(y for _, y in rows) / n, 4),
                  "brier": round(sum((w - y) ** 2 for w, y in rows) / n, 5)}
    return out


# ───────────────────────── 生產 artifact 等價性對帳 ─────────────────────────
def verify_counting_machine(cur, per_year_a: dict[int, Counter]) -> dict:
    """記憶體快照機器 vs 生產 cpbl.run_dist（span 2018-2025/A）逐列對帳。

    等價 ⇒ 本 harness 的訓練管線與已上線 build_run_dist 同語意，
    walk-forward 結果可歸因於「時間切分」而非實作差異。
    """
    mine = dist_from_counts(per_year_a, 2018, 2025)
    prod = load_production_dist(cur, "2018-2025", "A")
    if prod is None:
        return {"status": "skipped", "reason": "DB 無 run_dist 2018-2025/A"}
    mismatches = []
    for state in set(mine) | set(prod):
        a, b = mine.get(state), prod.get(state)
        if a is None or b is None or any(abs(x - y) > 1e-9
                                         for x, y in zip(a, b, strict=True)):
            mismatches.append({"state": list(state), "mine": a, "prod": b})
    return {"status": "match" if not mismatches else "MISMATCH",
            "states_mine": len(mine), "states_prod": len(prod),
            "mismatches": mismatches[:20]}


# ───────────────────────── 驗證主流程 ─────────────────────────
def run_validation(kinds: list[str], out_path: Path, *,
                   pre_score_source: str = "events") -> dict:
    result: dict = {"thresholds": THRESHOLDS, "pre_score_source": pre_score_source,
                    "scopes": {}}
    with conn() as c:
        cur = c.cursor()
        # 訓練計數（A、D 各一次；C/E 皆一軍季後 → proxy 均借 A 分布，FIX1 修正）
        per_year: dict[str, dict[int, Counter]] = {}
        for kind in ("A", "D"):
            needed = {TRAIN_PROXY[k] for k in kinds}
            if kind in needed:
                per_year[kind] = collect_training_counts(cur, kind, FIRST_YEAR, 2026)
        if "A" in per_year:
            result["counting_machine_check"] = verify_counting_machine(cur, per_year["A"])
        prod_dist_a = load_production_dist(cur, "2018-2025", "A")

        for kind in kinds:
            train_kind = TRAIN_PROXY[kind]
            eval_years = {"A": range(2021, 2027), "C": range(2021, 2026),
                          "D": range(2021, 2027), "E": range(2022, 2026)}[kind]
            # in-sample 對照：全期 2018..2026（含驗證季）——只用於量化樂觀偏差
            is_dist = dist_from_counts(per_year[train_kind], FIRST_YEAR, 2026)
            seasons = []
            pooled_scored: list = []
            pooled_baseline_num = 0.0
            for y in eval_years:
                season = load_eval_season(cur, kind, y,
                                          pre_score_source=pre_score_source)
                if not season["pas"]:
                    continue
                rules = season["rules"]
                # walk-forward 訓練窗：本 scope 到 Y-1；proxy scope（C/E）季後賽
                # 開打前該年例行賽已全數完成，訓練窗含當年例行季仍為時間外。
                train_to = y if kind in ("C", "E") else y - 1
                wf_dist = dist_from_counts(per_year[train_kind], FIRST_YEAR, train_to)
                wf_scored = score_pas(wf_dist, rules, season["pas"])
                is_scored = score_pas(is_dist, rules, season["pas"])
                home_p = home_rate_from_games(cur, train_kind, FIRST_YEAR, train_to)
                row = {
                    "year": y,
                    "model_span": f"{FIRST_YEAR}-{train_to}/{train_kind}",
                    "ruleset": rules.tag,
                    "coverage": season["coverage"],
                    "n_completed_games": season["n_completed_games"],
                    "n_irregular_games": season["n_irregular_games"],
                    "pa_state_counts": season["pa_state_counts"],
                    "tiebreak_state_in_train": (("1", "_2_", 0) in wf_dist
                                                and ("2", "_2_", 0) in wf_dist),
                    "walk_forward": metrics(wf_scored, bootstrap=True),
                    "walk_forward_regular_only": metrics(wf_scored, exclude_irregular=True),
                    "in_sample_full_span": {k: v for k, v in metrics(is_scored).items()
                                            if k in ("n_pa", "brier", "ece_weighted",
                                                     "decile_max_dev")},
                    "baseline_home_const": {
                        "p": home_p,
                        "brier": brier_constant(wf_scored, home_p),
                        # v3：這道閘門過去只比點估計，於是 4 場的季也能一票否決 scope
                        "delta_boot": cluster_bootstrap_brier_delta(
                            wf_scored, home_p, reps=THRESHOLDS["boot_reps"],
                            ci=THRESHOLDS["boot_ci"]),
                    },
                    "baseline_half": {"p": 0.5, "brier": brier_constant(wf_scored, 0.5)},
                    "inning_slices": inning_slices(season["pas"], wf_dist, rules),
                }
                row["optimism_brier"] = round(
                    row["baseline_home_const"]["brier"] - row["walk_forward"]["brier"], 5)
                row["insample_optimism"] = round(
                    row["walk_forward"]["brier"] - row["in_sample_full_span"]["brier"], 5)
                # 生產 artifact（2018-2025/A）對照：對 A 全季評，2026 為真時間外
                if kind == "A" and prod_dist_a is not None:
                    pm = metrics(score_pas(prod_dist_a, rules, season["pas"]))
                    row["production_artifact_2018_2025"] = {
                        "brier": pm["brier"],
                        "ece_weighted": pm["ece_weighted"],
                        "in_sample_for_this_season": y <= 2025,
                    }
                seasons.append(row)
                pooled_scored.extend(wf_scored)
                pooled_baseline_num += (row["baseline_home_const"]["brier"]
                                        * row["walk_forward"]["n_pa"])
                log.info("%s %d [%s] wf Brier=%.4f ECE=%.4f n=%d（主場基準 %.4f）",
                         kind, y, row["model_span"], row["walk_forward"]["brier"],
                         row["walk_forward"]["ece_weighted"],
                         row["walk_forward"]["n_pa"],
                         row["baseline_home_const"]["brier"])
            pooled: dict = (metrics(pooled_scored, bootstrap=True) if pooled_scored
                            else {"n_pa": 0})
            if pooled["n_pa"]:
                pooled["baseline_home_const_brier"] = round(
                    pooled_baseline_num / pooled["n_pa"], 5)
            result["scopes"][kind] = {
                "seasons": seasons,
                "pooled_walk_forward": pooled,
                "verdict": verdict_for(kind, seasons, pooled),
            }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=1))
    log.info("artifact → %s", out_path)
    return result


def _gate(name: str, decision: str, detail: str, **extra) -> dict:
    """單一閘門的判定紀錄。`decision` ∈ fail / pass / undetermined / unreachable。"""
    return {"gate": name, "decision": decision, "detail": detail, **extra}


def verdict_for(kind: str, seasons: list[dict], pooled: dict) -> dict:
    """雜訊感知 Go/No-Go **v3**（ML-WP-VERDICT-ROBUST1）。

    ## 判定詞彙：三態不夠，要四態

    v2 只有 `supported` / `proxy_with_warning` / `unsupported`，於是三種完全不同的
    認識論狀態被壓成兩格：

    1. 測了，通過 → `supported`
    2. 測了，不通過 → `unsupported`
    3. **測不了** → v2 也回 `unsupported`（連「無可評樣本」都是，見 v2 首行）

    第 3 種另立 ``insufficient_evidence``。它**不是**通過：不能上線的處置與
    `unsupported` 相同，改的是「為什麼不能上線」的說法——「模型校準不良」與
    「這個樣本量測不出模型好不好」是兩件事，寫錯會誤導讀者，也會讓永遠拿不到樣本的
    scope（C 全期 25 場、E 全期 13 場）背上它沒有的罪名。

    ## 每道閘門都必須先回答「這道閘門在這個樣本量下判得動嗎」

    判準全部**可計算**，不用「場數 < N」這種寫死的數字（那只是換一個任意門檻，
    而且不隨指標與門檻變動）：

    * **逐季 Brier vs 主場常數基準**：Δ 改用整場重抽的三態決策。Δ 與 0 分不開時，
      該季既不算贏也不算輸 → `undetermined` → 進 `insufficient`，不再一票否決。
    * **池化十分位偏差**：|dev| 超界仍是點估計比門檻（門檻**未動**），但「顯著」
      改用 :func:`_tail_state` 的三態。`undetermined` 代表判定在目前重抽預算下
      不可重現——v2 在這裡是擲 seed 的硬幣。
    * **proxy 池化 ECE**：先算完美校準零假設下的期望 ECE
      （:func:`null_ece_reference`）。若 H0 期望值本身就超過門檻，那道門檻在此樣本量
      下**不可能通過**，它不是判準而是雜訊產生器 → `unreachable` → 進 `insufficient`。
      即使可達，觀測值若落在 H0 的 p95 之內，也與完美校準不可區分 → `undetermined`。
    * **coverage**：純計數、無抽樣成分，維持硬性。

    ## 優先序

    `unsupported` > `insufficient_evidence` > `proxy_with_warning` > `supported`。
    有一道閘門**解析得出來的失敗**就是真失敗（其他閘門測不了不能救它）；沒有真失敗
    但有測不了的閘門，就不得宣稱通過。**門檻數值一律未動**，改的只有判定方法與詞彙。
    """
    if not seasons or not pooled.get("n_pa"):
        # v2 這裡回 unsupported——「沒有樣本可評」被寫成「評過了，不合格」。
        return {"status": VERDICT_INSUFFICIENT, "reasons": [],
                "insufficient": ["無可評樣本"], "disclosure": [], "v1_flags": [],
                "gates": [_gate("evaluable_sample", "undetermined", "無可評樣本")]}
    hard, insufficient, disclosure, v1_flags = [], [], [], []
    gates: list[dict] = []
    for s in seasons:
        wf = s["walk_forward"]
        tag = f"{kind}{s['year']}"
        if s["coverage"] < THRESHOLDS["min_coverage"]:
            msg = f"{tag} coverage {s['coverage']} < {THRESHOLDS['min_coverage']}"
            hard.append(msg)
            gates.append(_gate("coverage", "fail", msg, season=s["year"]))
        # ── 逐季 Brier vs 主場常數基準（三態）──
        base = s["baseline_home_const"]
        boot = base.get("delta_boot") or {}
        delta = boot.get("delta")
        if delta is None:
            delta = round(wf["brier"] - base["brier"], 5)
        state = boot.get("sig_state", SIG_SIGNIFICANT)   # 無 bootstrap 資訊→退回 v2 行為
        stat = (f"Δ={delta:+.5f} CI{boot.get('ci')} p_one={boot.get('p_one')} "
                f"reps={boot.get('reps_total')} "
                f"v2seeds={boot.get('n_seeds_significant')}/{boot.get('n_seeds')}")
        if state == SIG_SIGNIFICANT:
            if delta >= 0:
                msg = (f"{tag} Brier {wf['brier']} 未勝過主場常數基準 "
                       f"{base['brier']}（差距顯著；{stat}）")
                hard.append(msg)
                gates.append(_gate("season_brier_vs_baseline", "fail", msg,
                                   season=s["year"]))
            else:
                gates.append(_gate("season_brier_vs_baseline", "pass",
                                   f"{tag} 顯著勝過主場常數基準（{stat}）",
                                   season=s["year"]))
        else:
            msg = (f"{tag} Brier {wf['brier']} vs 主場常數基準 {base['brier']}："
                   f"差距與 0 不可區分（{state}；{stat}），該季無判別力")
            insufficient.append(msg)
            gates.append(_gate("season_brier_vs_baseline", "undetermined", msg,
                               season=s["year"]))
        if wf["ece_weighted"] > THRESHOLDS["ece_weighted_max"]:
            v1_flags.append(f"{tag} ECE {wf['ece_weighted']}（v1 點估計參考）")
        if wf["decile_max_dev"] is not None and \
                wf["decile_max_dev"] > THRESHOLDS["decile_max_dev"]:
            v1_flags.append(f"{tag} maxdev {wf['decile_max_dev']}（v1 點估計參考）")
        if wf.get("significant_bins"):
            disclosure.append(f"{tag} 逐季顯著偏差分箱 {wf['significant_bins']}"
                              "（99% 叢集 CI 排除 0，跨 seed 一致）")
        if wf.get("undetermined_bins"):
            disclosure.append(f"{tag} 逐季顯著性無法解析的分箱 "
                              f"{wf['undetermined_bins']}（重抽預算內判不動）")
    # ── 池化十分位偏差（門檻不動，顯著性換三態）──
    for d in pooled.get("deciles", []):
        if d.get("sig_state") is None or d["n"] < 1000:
            continue
        dev = d["pred"] - d["actual"]
        over = abs(dev) > THRESHOLDS["pooled_bin_dev_max"]
        stat = (f"n={d['n']} CI{d['dev_ci']} p_one={d['p_one']}{d['p_one_mc_ci']} "
                f"reps={d.get('reps_total')} "
                f"v2seeds={d['n_seeds_significant']}/{d['n_seeds']}")
        if d["sig_state"] == SIG_SIGNIFICANT:
            if over:
                msg = (f"池化十分位 {d['bin']} 偏差 {dev:+.4f} 顯著且超過 "
                       f"±{THRESHOLDS['pooled_bin_dev_max']}（{stat}）")
                hard.append(msg)
                gates.append(_gate("pooled_bin_dev", "fail", msg, bin=d["bin"]))
            else:
                disclosure.append(f"池化十分位 {d['bin']} 偏差 {dev:+.4f} 顯著但幅度受控"
                                  f"（{stat}）")
                gates.append(_gate("pooled_bin_dev", "pass",
                                   f"十分位 {d['bin']} 幅度受控", bin=d["bin"]))
        elif d["sig_state"] == SIG_UNDETERMINED and over:
            # v2 的病灶就住在這一格：|dev| 超界、顯著性剛好卡在門檻上，
            # 於是 Go/No-Go 由 bootstrap seed 決定。現在它有自己的名字。
            msg = (f"池化十分位 {d['bin']} 偏差 {dev:+.4f} 超過 "
                   f"±{THRESHOLDS['pooled_bin_dev_max']}，但顯著性在重抽預算內"
                   f"無法解析（{stat}；已加碼重抽至上限 "
                   f"{BOOT_MAX_REPS}）——不具證據等級")
            insufficient.append(msg)
            gates.append(_gate("pooled_bin_dev", "undetermined", msg, bin=d["bin"]))
        elif over:
            disclosure.append(f"池化十分位 {d['bin']} 偏差 {dev:+.4f} 超界但與 0 "
                              f"不可區分（{stat}）")
            gates.append(_gate("pooled_bin_dev", "pass",
                               f"十分位 {d['bin']} 超界但不顯著", bin=d["bin"]))
    small = all(s["walk_forward"]["n_pa"] < THRESHOLDS["min_season_pa"] for s in seasons)
    proxy = kind in ("C", "E")
    if proxy:
        gate_v = THRESHOLDS["proxy_pooled_ece_max"]
        obs = pooled["ece_weighted"]
        null = pooled.get("null_ece") or null_ece_reference(pooled.get("deciles") or [])
        if null is None:
            if obs > gate_v:
                msg = (f"proxy 池化 ECE {obs} > {gate_v}，代理證據不足以掛警示上線")
                hard.append(msg)
                gates.append(_gate("proxy_pooled_ece", "fail", msg))
        elif null["analytic_mean"] > gate_v:
            msg = (f"proxy 池化 ECE 門檻 {gate_v} 在此樣本量下不可達："
                   f"完美校準零假設的期望 ECE 就有 {null['analytic_mean']}"
                   f"（觀測 {obs}，H0 p95 {null['mc_p95']}）——該門檻不是判準，"
                   f"是雜訊產生器")
            insufficient.append(msg)
            gates.append(_gate("proxy_pooled_ece", "unreachable", msg,
                               null_ece=null, observed=obs, threshold=gate_v))
        elif obs > gate_v and obs <= null["mc_p95"]:
            msg = (f"proxy 池化 ECE {obs} > {gate_v}，但落在完美校準零假設的 p95 "
                   f"{null['mc_p95']} 之內——與完美校準不可區分")
            insufficient.append(msg)
            gates.append(_gate("proxy_pooled_ece", "undetermined", msg,
                               null_ece=null, observed=obs, threshold=gate_v))
        elif obs > gate_v:
            msg = (f"proxy 池化 ECE {obs} > {gate_v}（H0 期望 "
                   f"{null['analytic_mean']}、p95 {null['mc_p95']}），"
                   f"代理證據不足以掛警示上線")
            hard.append(msg)
            gates.append(_gate("proxy_pooled_ece", "fail", msg,
                               null_ece=null, observed=obs, threshold=gate_v))
        else:
            gates.append(_gate("proxy_pooled_ece", "pass",
                               f"proxy 池化 ECE {obs} ≤ {gate_v}",
                               null_ece=null, observed=obs, threshold=gate_v))
    if hard:
        status = VERDICT_UNSUPPORTED
    elif insufficient:
        status = VERDICT_INSUFFICIENT
    elif proxy or small:
        status = VERDICT_PROXY_WITH_WARNING
        if proxy:
            disclosure.append("模型分布借自他 scope（C←A、E←A），規則邊界已換用該 scope 配置")
        if small:
            disclosure.append(f"單季樣本皆 < {THRESHOLDS['min_season_pa']}，統計檢定力不足")
    else:
        status = VERDICT_SUPPORTED
    if status == VERDICT_INSUFFICIENT and (proxy or small):
        disclosure.append("本 scope 另受 proxy／小樣本上限限制，即使閘門判得動亦不得高於 "
                          "proxy_with_warning")
    return {"status": status, "reasons": hard, "insufficient": insufficient,
            "disclosure": disclosure, "v1_flags": v1_flags, "gates": gates}


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    ap = argparse.ArgumentParser(description="GAME-RECAP-WP-VAL1 時間外驗證（唯讀）")
    ap.add_argument("--kinds", default="A,C,D,E")
    ap.add_argument("--out", default="docs/research/game_recap_wp_val1_metrics.json")
    ap.add_argument("--pre-score-source", default="events", choices=list(PRE_SCORE_SOURCES),
                    help="局面分差的打席前比分來源。events＝事件流（預設，唯一正確）；"
                         "pre_state＝已知受污染的舊讀法，只給 ML-WP-VAL-RESAMPLE1 的 A/B "
                         "對照用，產出不得作為對外數字")
    args = ap.parse_args()
    kinds = [k.strip().upper() for k in args.kinds.split(",") if k.strip()]
    result = run_validation(kinds, Path(args.out),
                            pre_score_source=args.pre_score_source)
    for kind, scope in result["scopes"].items():
        v = scope["verdict"]
        pooled = scope["pooled_walk_forward"]
        print(f"\n=== scope {kind}: {v['status']} ===")
        for label, items in (("硬性", v["reasons"]),
                             ("測不了", v.get("insufficient", [])),
                             ("揭露", v.get("disclosure", [])),
                             ("v1參考", v.get("v1_flags", []))):
            for r in items:
                print(f"  [{label}] {r}")
        if pooled.get("n_pa"):
            print(f"  池化 walk-forward：n_pa={pooled['n_pa']} n_games={pooled['n_games']} "
                  f"Brier={pooled['brier']}（主場基準 {pooled.get('baseline_home_const_brier')}） "
                  f"ECE={pooled['ece_weighted']} 顯著分箱={pooled.get('significant_bins')}")
        for s in scope["seasons"]:
            wf = s["walk_forward"]
            print(f"  {s['year']} [{s['model_span']}|{s['ruleset']}] "
                  f"n={wf['n_pa']} Brier={wf['brier']} ECE={wf['ece_weighted']} "
                  f"maxdev={wf['decile_max_dev']} sig={wf.get('significant_bins')} "
                  f"主場基準={s['baseline_home_const']['brier']} "
                  f"同母體樂觀={s['insample_optimism']}")


if __name__ == "__main__":
    main()
