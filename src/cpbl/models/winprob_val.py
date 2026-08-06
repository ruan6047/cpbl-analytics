"""GAME-RECAP-WP-VAL1：場中 WP 時間外驗證 harness（唯讀；統計 Go/No-Go）。

沿用 models/winprob.py 的 run_dist + WE 動態規劃方法，但驗證打席改消費
GAME-RECAP-PA1 canonical 打席（cpbl.game_plate_appearances，published build、
state='ready'），以 walk-forward（訓練 2018..Y-1 → 驗證季 Y）檢驗 WP 校準與
規則邊界，產出各 scope（A 一軍例行／C 一軍總冠軍賽／D 二軍例行／E 一軍季後
挑戰賽）的 supported / proxy_with_warning / unsupported 結論。F（二軍總冠軍賽）
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

執行（host 即可，無 LightGBM 相依）：
    uv run python -m cpbl.models.winprob_val            # 全部 scope
    uv run python -m cpbl.models.winprob_val --kinds A  # 單一 scope
產出：docs/research/game_recap_wp_val1_metrics.json（機器 artifact）+ stdout 表。
"""

from __future__ import annotations

import argparse
import json
import logging
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from cpbl.db import conn

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


# ───────────────────────── 驗證資料：canonical PA + 賽果 ─────────────────────────
PRE_SCORE_SOURCES = ("events", "pre_state")


def _resolve_pre_scores(cur, kind: str, year: int,
                        pa_rows_by_game: dict[int, list[dict]]) -> dict[tuple[int, int], tuple[int, int]]:
    """``(game_sno, pa_index)`` → 該打席**開始之前**的 ``(away, home)``。

    唯一正確的打席前比分來源，語意與紅線見
    :func:`cpbl.api.routers.recap.pre_scores_from_events` 的 docstring。

    ⚠️ **這裡刻意用函式內 import**：``winprob_scorer`` 已 import 本模組，而
    ``api/routers/recap`` 又 import ``winprob_scorer``——模組層 import 會構成
    ``winprob_val → recap → winprob_scorer → winprob_val`` 迴圈。同一條紅線只能有一份
    實作（本卡的病灶就是同一語意有兩份讀法），故寧可延後 import 也不在此另刻一份。
    正解是把該純函式上抽到 ``models/``（``recap`` 已有 ``winprob_scorer`` 的前例），
    但那要動 ``api/routers/recap.py``——不在本卡寫入集，留待需求方裁決。
    """
    from cpbl.api.routers.recap import pre_scores_from_events

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


def cluster_bootstrap_devs(scored: Sequence[tuple[float, float, bool, object]],
                           reps: int, ci: float, seed: int = 20260725) -> dict[int, dict]:
    """game-cluster bootstrap：整場重抽，估各十分位 (pred-actual) 的 SE 與 CI。

    同場打席共享同一賽果 → 有效樣本≈場數；逐 PA 的 binomial 誤差會嚴重低估
    分箱偏差的不確定度，須以場為叢集重抽。
    """
    import random
    by_game: dict[object, list[list[float]]] = {}
    for wp, y, _, gk in scored:
        g = by_game.setdefault(gk, [[0.0, 0.0, 0] for _ in range(10)])
        b = g[min(int(wp * 10), 9)]
        b[0] += wp
        b[1] += y
        b[2] += 1
    games = list(by_game.values())
    rng = random.Random(seed)
    devs: dict[int, list[float]] = defaultdict(list)
    for _ in range(reps):
        agg = [[0.0, 0.0, 0] for _ in range(10)]
        for g in rng.choices(games, k=len(games)):
            for i in range(10):
                agg[i][0] += g[i][0]
                agg[i][1] += g[i][1]
                agg[i][2] += g[i][2]
        for i, (sw, so, bn) in enumerate(agg):
            if bn:
                devs[i].append(sw / bn - so / bn)
    lo_q, hi_q = (1 - ci) / 2, 1 - (1 - ci) / 2
    out: dict[int, dict] = {}
    for i, ds in devs.items():
        ds.sort()
        n = len(ds)
        mean = sum(ds) / n
        se = (sum((d - mean) ** 2 for d in ds) / max(n - 1, 1)) ** 0.5
        out[i] = {"se": round(se, 4),
                  "ci": [round(ds[int(lo_q * (n - 1))], 4),
                         round(ds[int(hi_q * (n - 1))], 4)]}
    return out


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
        cis = cluster_bootstrap_devs(kept, THRESHOLDS["boot_reps"], THRESHOLDS["boot_ci"])
        sig = []
        for d in deciles:
            c = cis.get(d["bin"])
            if not c:
                continue
            d["dev_se"] = c["se"]
            d["dev_ci"] = c["ci"]
            if d["n"] >= 300 and (c["ci"][0] > 0 or c["ci"][1] < 0):
                sig.append(d["bin"])
        out["significant_bins"] = sig
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
                    "baseline_home_const": {"p": home_p,
                                            "brier": brier_constant(wf_scored, home_p)},
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


def verdict_for(kind: str, seasons: list[dict], pooled: dict) -> dict:
    """雜訊感知（v2）Go/No-Go：

    硬性失敗（→ unsupported）：
      - 任一季 coverage < min_coverage；
      - 任一季 walk-forward Brier 未勝過主場常數基準；
      - 池化 walk-forward 有 n>=1000 的十分位偏差 |dev| > pooled_bin_dev_max
        且 99% 叢集 CI 排除 0（真實且超界的偏差）。
    proxy 上限（→ 最高 proxy_with_warning）：
      - C/E 分布借自他 scope；或全部季樣本 < min_season_pa。
    其餘 → supported；池化顯著但幅度 ≤ 上限的分箱、逐季顯著漂移季列入
    disclosure（v1 逐季點估計旗標另列 reference，不進判定）。
    """
    if not seasons or not pooled.get("n_pa"):
        return {"status": "unsupported", "reasons": ["無可評樣本"], "v1_flags": []}
    hard, disclosure, v1_flags = [], [], []
    for s in seasons:
        wf = s["walk_forward"]
        tag = f"{kind}{s['year']}"
        if s["coverage"] < THRESHOLDS["min_coverage"]:
            hard.append(f"{tag} coverage {s['coverage']} < {THRESHOLDS['min_coverage']}")
        if wf["brier"] >= s["baseline_home_const"]["brier"]:
            hard.append(f"{tag} Brier {wf['brier']} 未勝過主場常數基準 "
                        f"{s['baseline_home_const']['brier']}")
        if wf["ece_weighted"] > THRESHOLDS["ece_weighted_max"]:
            v1_flags.append(f"{tag} ECE {wf['ece_weighted']}（v1 點估計參考）")
        if wf["decile_max_dev"] is not None and \
                wf["decile_max_dev"] > THRESHOLDS["decile_max_dev"]:
            v1_flags.append(f"{tag} maxdev {wf['decile_max_dev']}（v1 點估計參考）")
        if wf.get("significant_bins"):
            disclosure.append(f"{tag} 逐季顯著偏差分箱 {wf['significant_bins']}"
                              "（99% 叢集 CI 排除 0）")
    for d in pooled.get("deciles", []):
        ci = d.get("dev_ci")
        if ci is None or d["n"] < 1000:
            continue
        dev = d["pred"] - d["actual"]
        if (ci[0] > 0 or ci[1] < 0):
            if abs(dev) > THRESHOLDS["pooled_bin_dev_max"]:
                hard.append(f"池化十分位 {d['bin']} 偏差 {dev:+.4f} 顯著且超過 "
                            f"±{THRESHOLDS['pooled_bin_dev_max']}（n={d['n']}）")
            else:
                disclosure.append(f"池化十分位 {d['bin']} 偏差 {dev:+.4f} 顯著但幅度受控"
                                  f"（n={d['n']}）")
    small = all(s["walk_forward"]["n_pa"] < THRESHOLDS["min_season_pa"] for s in seasons)
    proxy = kind in ("C", "E")
    if proxy and pooled["ece_weighted"] > THRESHOLDS["proxy_pooled_ece_max"]:
        # proxy 掛警示的前提是池化證據至少不顯示嚴重失準；ECE 遠超上限時
        # （即便樣本小到不顯著）fail closed → unsupported
        hard.append(f"proxy 池化 ECE {pooled['ece_weighted']} > "
                    f"{THRESHOLDS['proxy_pooled_ece_max']}，代理證據不足以掛警示上線")
    if hard:
        status = "unsupported"
    elif proxy or small:
        status = "proxy_with_warning"
        if proxy:
            disclosure.append("模型分布借自他 scope（C←A、E←D），規則邊界已換用該 scope 配置")
        if small:
            disclosure.append(f"單季樣本皆 < {THRESHOLDS['min_season_pa']}，統計檢定力不足")
    else:
        status = "supported"
    return {"status": status, "reasons": hard, "disclosure": disclosure,
            "v1_flags": v1_flags}


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
        for label, items in (("硬性", v["reasons"]), ("揭露", v.get("disclosure", [])),
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
