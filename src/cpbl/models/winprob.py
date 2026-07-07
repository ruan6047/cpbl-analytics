"""逐打席勝率 [Win Probability]：run_dist（半局剩餘得分分布）+ WE 邊界表（DP 倒推）。

方法（全自算；rebas.tw 僅作圖形對照，不取其數值）：
1. run_dist：P(半局再得 k 分 | 上/下半局,壘位,出局)。與 RE 矩陣同一套快照機器
   （非更換列打席首事件、事件前比分=前列事件後比分、排除每場末半局），保留整個分布。
   **上/下半局分開估**：主場優勢（主隊下半局得分較強）由資料自然浮現——共用分布
   會構造性抹掉主場優勢（DP 對稱 → 開局恆 0.500），不可合併。
2. WE 邊界：以上/下半局各自的空壘 0 出局分布動態規劃自 12 局倒推。規則：
   - 9 局起「上半局結束時主隊領先 → 比賽結束」；下半局主隊打完若落後 → 客勝；
   - 12 局下結束仍平 → 和局（CPBL 例行賽）；
   - 再見截斷不失真：未截斷分布只用於判「是否跨過門檻」，與現實（跨過即停）等價。
3. 場中狀態 WP = Σ_k P(k|壘位,出局) × WE(下一邊界, 分差±k)，下半局 9 局起用門檻邏輯。
4. 驗證：2018–2025 全打席校準（十分位 預測 vs 實際主隊勝率，和局計 0.5）+ Brier。

天花板揭露：WP 是「局面」勝率（中性隊伍 + 資料內含主場優勢），不含先發投手/戰力差；
賽前狀態 ≈ 聯盟主場基準率，隨比賽進行收斂到確定。
"""

from __future__ import annotations

import logging
from collections import defaultdict
from functools import cache

from cpbl.db import conn

log = logging.getLogger("cpbl.winprob")

K_CAP = 6           # 6 = 6+
MAX_INNING = 12     # CPBL 例行賽 12 局和局
DIFF_CLIP = 15


# ───────────────────────── run_dist ─────────────────────────
def build_run_dist(from_year: int, to_year: int, kind: str = "A") -> dict:
    """半局剩餘得分分布 → run_dist。與 build_run_expectancy 同快照語意。"""
    from cpbl.models.sabr import _load_game
    span = f"{from_year}-{to_year}"
    cnt: dict[tuple[str, str, int], list[int]] = defaultdict(lambda: [0] * (K_CAP + 1))
    with conn() as c:
        cur = c.cursor()
        cur.execute("SELECT DISTINCT year, game_sno FROM cpbl.game_livelog "
                    "WHERE year BETWEEN %s AND %s AND kind_code=%s", (from_year, to_year, kind))
        games = cur.fetchall()
        for gy, sno in games:
            events = _load_game(cur, gy, kind, sno)
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
            for hk in order[:-1]:               # 排除末半局（可能截斷；與 RE 矩陣同population）
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
                    cnt[(vht, bases, outs)][min(rest, K_CAP)] += 1
    rows = []
    for (side, bases, outs), ks in cnt.items():
        n = sum(ks)
        if n < 30:
            continue
        rows += [(span, kind, side, bases, outs, k, round(v / n, 5), n)
                 for k, v in enumerate(ks)]
    with conn() as c:
        c.execute("DELETE FROM cpbl.run_dist WHERE span=%s AND kind_code=%s", (span, kind))
        c.cursor().executemany(
            "INSERT INTO cpbl.run_dist (span, kind_code, side, bases, outs, k, p, samples) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)", rows)
    log.info("run_dist %s/%s：%d 場，%d 狀態", span, kind, len(games), len(cnt))
    return {"games": len(games), "states": len(cnt)}


# ───────────────────────── WE 邊界 DP ─────────────────────────
def _load_dist(span: str, kind: str) -> dict[tuple[str, str, int], list[float]]:
    with conn() as c:
        cur = c.cursor()
        cur.execute("SELECT side, bases, outs, k, p FROM cpbl.run_dist "
                    "WHERE span=%s AND kind_code=%s", (span, kind))
        out: dict[tuple[str, str, int], list[float]] = defaultdict(lambda: [0.0] * (K_CAP + 1))
        for s, b, o, k, p in cur.fetchall():
            out[(s, b, o)][k] = float(p)
    if ("1", "___", 0) not in out or ("2", "___", 0) not in out:
        raise RuntimeError(f"run_dist 無 {span}/{kind}，先跑 build_run_dist")
    return dict(out)


def _we_solver(d0_top: list[float], d0_bot: list[float]):
    """回傳 (we_top(inning,diff), we_bot(inning,diff)) 遞迴求解器；值=(p_win, p_tie)。

    we_top(i,d)＝i 局上**開打前**、主隊視角分差 d 的 (勝,和)；we_bot 同理 i 局下開打前。
    上/下半局各用自己的得分分布（主場優勢由此浮現）。
    9 局起：上半局打完主隊領先即結束；下半局打完主隊落後即客勝；12 局下打完平手=和。
    """
    clip = lambda d: max(-DIFF_CLIP, min(DIFF_CLIP, d))  # noqa: E731

    @cache
    def we_bot(i: int, d: int) -> tuple[float, float]:
        w = t = 0.0
        for k, p in enumerate(d0_bot):
            if not p:
                continue
            nd = d + k
            if i >= 9:
                if nd > 0:
                    w += p                        # 主隊贏（含再見；門檻邏輯與截斷等價）
                elif i >= MAX_INNING:
                    t += p if nd == 0 else 0.0    # 12 局下打完：平=和、落後=客勝
                elif nd == 0:
                    nw, nt = we_top(i + 1, 0)
                    w += p * nw
                    t += p * nt
                # nd < 0：9–11 局下打完仍落後 → 客勝（不加 w/t）
            else:
                nw, nt = we_top(i + 1, clip(nd))
                w += p * nw
                t += p * nt
        return (w, t)

    @cache
    def we_top(i: int, d: int) -> tuple[float, float]:
        w = t = 0.0
        for k, p in enumerate(d0_top):
            if not p:
                continue
            nd = clip(d - k)
            if i >= 9 and nd > 0:
                w += p                            # 上半局打完主隊仍領先 → 免打下半局，主勝
            else:
                nw, nt = we_bot(i, nd)
                w += p * nw
                t += p * nt
        return (w, t)

    return we_top, we_bot


def build_win_expectancy(span: str, kind: str = "A") -> dict:
    """DP 倒推 WE 邊界表 → win_expectancy；並印 vs 全史逐局實績的抽樣對照。"""
    dist = _load_dist(span, kind)
    we_top, we_bot = _we_solver(dist[("1", "___", 0)], dist[("2", "___", 0)])
    rows = []
    for i in range(1, MAX_INNING + 1):
        for d in range(-DIFF_CLIP, DIFF_CLIP + 1):
            for half, fn in (("1", we_top), ("2", we_bot)):
                w, t = fn(i, d)
                rows.append((span, kind, i, half, d, round(w, 5), round(t, 5)))
    with conn() as c:
        c.execute("DELETE FROM cpbl.win_expectancy WHERE span=%s AND kind_code=%s", (span, kind))
        c.cursor().executemany(
            "INSERT INTO cpbl.win_expectancy (span, kind_code, inning, half, diff, p_win, p_tie) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)", rows)
    w0, t0 = we_top(1, 0)
    log.info("win_expectancy %s/%s：%d 列；開局 WE=%.3f（+0.5×和 %.3f → %.3f，聯盟主場基準對照）",
             span, kind, len(rows), w0, t0, w0 + 0.5 * t0)
    return {"rows": len(rows), "we_start": round(w0 + 0.5 * t0, 4)}


# ───────────────────────── 場中狀態 WP + 校準驗證 ─────────────────────────
def wp_state(dist, we_top, we_bot, inning: int, vht: str, diff: int,
             bases: str, outs: int) -> float:
    """半局進行中任意狀態的主隊 WP（勝 + 0.5×和）。diff=主隊視角、bases/outs=打擊方狀態。"""
    dk = dist.get((vht, bases, min(outs, 2))) or dist[(vht, "___", 0)]
    w = t = 0.0
    clip = lambda d: max(-DIFF_CLIP, min(DIFF_CLIP, d))  # noqa: E731
    inning = min(inning, MAX_INNING)
    for k, p in enumerate(dk):
        if not p:
            continue
        if vht == "1":                             # 客隊進攻中 → 打完進同局下半
            nd = clip(diff - k)
            if inning >= 9 and nd > 0:
                w += p
            else:
                nw, nt = we_bot(inning, nd)
                w += p * nw
                t += p * nt
        else:                                      # 主隊進攻中 → 打完進下一局上半
            nd = diff + k
            if inning >= 9:
                if nd > 0:
                    w += p
                elif nd == 0:
                    if inning >= MAX_INNING:
                        t += p
                    else:
                        nw, nt = we_top(inning + 1, 0)
                        w += p * nw
                        t += p * nt
                # nd<0：i>=9 下半局打完落後 → 客勝
            else:
                nw, nt = we_top(inning + 1, clip(nd))
                w += p * nw
                t += p * nt
    return w + 0.5 * t


def validate_calibration(from_year: int, to_year: int, span: str, kind: str = "A") -> dict:
    """校準驗證：全打席預測 WP 十分位 vs 實際主隊結果（勝 1／和 0.5／負 0）+ Brier。"""
    from cpbl.models.sabr import _load_game
    dist = _load_dist(span, kind)
    we_top, we_bot = _we_solver(dist[("1", "___", 0)], dist[("2", "___", 0)])
    buckets = [[0.0, 0.0, 0] for _ in range(10)]   # [Σwp, Σoutcome, n]
    brier_sum, n_pa = 0.0, 0
    with conn() as c:
        cur = c.cursor()
        cur.execute(
            "SELECT g.year, g.game_sno, g.home_score, g.away_score FROM cpbl.games g "
            "WHERE g.year BETWEEN %s AND %s AND g.kind_code=%s "
            "AND g.home_score + g.away_score > 0", (from_year, to_year, kind))
        games = cur.fetchall()
        for gy, sno, hs, aw in games:
            outcome = 1.0 if hs > aw else (0.0 if hs < aw else 0.5)
            events = _load_game(cur, gy, kind, sno)
            pv, ph = 0, 0
            seen: set = set()
            for e in events:
                pre_v, pre_h = pv, ph
                pv = e["visiting_score"] if e.get("visiting_score") is not None else pv
                ph = e["home_score"] if e.get("home_score") is not None else ph
                if e.get("is_change_player") or not e.get("hitter_acnt"):
                    continue
                pa_key = (e["inning_seq"], str(e["visiting_home_type"]),
                          e.get("batting_order"), e["hitter_acnt"])
                if pa_key in seen:
                    continue
                seen.add(pa_key)
                bases = (("1" if e.get("first_base") else "_")
                         + ("2" if e.get("second_base") else "_")
                         + ("3" if e.get("third_base") else "_"))
                wp = wp_state(dist, we_top, we_bot, int(e["inning_seq"]),
                              str(e["visiting_home_type"]), pre_h - pre_v,
                              bases, int(e.get("out_cnt") or 0))
                b = buckets[min(int(wp * 10), 9)]
                b[0] += wp
                b[1] += outcome
                b[2] += 1
                brier_sum += (wp - outcome) ** 2
                n_pa += 1
    log.info("calibration %s–%s（%d 場 %d 打席）Brier=%.4f", from_year, to_year,
             len(games), n_pa, brier_sum / n_pa)
    for i, (sw, so, n) in enumerate(buckets):
        if n:
            log.info("  十分位 %d0%%：預測均值 %.3f vs 實際 %.3f（n=%d）",
                     i, sw / n, so / n, n)
    return {"n_pa": n_pa, "brier": round(brier_sum / n_pa, 4)}
