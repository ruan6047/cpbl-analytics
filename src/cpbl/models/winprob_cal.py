"""GAME-RECAP-WP-CAL1：場中 WP 事後校準層（唯讀；A 一軍例行）。

在既有局面 WP（models/winprob.py run_dist × WE DP）之上加一層**單調事後校準**
[post-hoc calibration]，消除 GAME-RECAP-WP-VAL1 證實的時間外 S 型偏差
（池化低分箱 +4.2~+6.0pt／高分箱 −4.3pt）。isotonic（等量分箱 + 加權 PAV）
為主、beta calibration（3 參數）為低複雜度對照。全程復用 winprob_val 的
walk-forward 管線（host 可跑、無 LightGBM 相依、不寫任何表）。

統計紅線（卡面四條 + 診斷；違反即退回）：
1. **校準器只能用時間外預測擬合**：驗證季 Y 的校準器，訓練資料＝各季
   s < Y 的 walk-forward 預測-結果對（該預測由 span ≤ s−1 的 base 模型產生，
   即 winprob_val 的 wf 輸出）。嚴禁用 in-sample 預測擬合——WP-VAL1 §1 證明
   in-sample 偏差剖面不同（低分箱偏差主要來自時間外才可見的主場優勢漂移），
   fit 在 in-sample 上會學到錯誤修正。`calibration_pairs()` 是唯一取數入口，
   對 s >= Y 直接拒絕；runner 另 assert 每季 wf 預測的 base span 恆 ≤ s−1。
2. **嵌套時間分離**：base 模型窗（2018..s−1）、校準器訓練窗（2021..Y−1 的
   wf 對）、驗證季 Y 三者嚴格分離且皆 ≤ Y−1；首個可校準驗證季自 2023 起
   （2021–22 wf 預測供第一個校準窗），驗證 2023–2026 逐季 + 池化。
3. **單調性與端點行為**：兩族校準函數皆單調、值域 [0,1]、f(0)=0、f(1)=1
   （不破壞終場收斂 0/1 與再見門檻語意——單調映射不改變門檻跨越的次序）。
   isotonic 以「每箱樣本下限 + 箱數上限」防小樣本尾端過擬合；beta 以
   a,b > 0 的參數化保證單調與端點收斂。
4. **判定沿用 WP-VAL1 v2 門檻，不得放寬**：池化 walk-forward（n≥1000 分箱）
   |dev| ≤ 0.03 或 99% game-cluster CI 含 0；每季 Brier 勝主場常數基準且
   **不得劣於未校準 base**；coverage ≥ 0.98。
5. **診斷不得惡化**：逐局帶（1-3/4-6/7-9）校準摘要相對 base 不得系統性惡化
   （門檻預先註冊於 CAL_THRESHOLDS，見下）；10+（2024+ 突破僵局）樣本小，
   只列揭露不作支持或否決證據。
6. **選型不得以驗證季表現挑選**：isotonic vs beta 以校準訓練窗內指標定案
   （fit 2021 → 內部前向評估 2022；兩者皆早於全部驗證季）。兩族在驗證季的
   結果仍並排回報供對照，但判定只用預先選定的一族。

執行（host 即可；~3 分鐘）：
    uv run python -m cpbl.models.winprob_cal
    uv run python -m cpbl.models.winprob_cal --out /path/to/scratch.json  # 部分重跑導向 scratch
產出：docs/research/game_recap_wp_cal1_metrics.json（機器 artifact）+ stdout 表。
"""

from __future__ import annotations

import argparse
import json
import logging
import math
from dataclasses import dataclass
from pathlib import Path

from cpbl.db import conn
from cpbl.models.winprob_val import (
    FIRST_YEAR,
    THRESHOLDS,
    brier_constant,
    collect_training_counts,
    dist_from_counts,
    home_rate_from_games,
    load_eval_season,
    metrics,
    score_pas,
)

log = logging.getLogger("cpbl.winprob_cal")

KIND = "A"                # 本卡僅 A 一軍例行；C/D/E 維持 unsupported（卡面範圍）
WF_FIRST = 2021           # walk-forward 預測可得的第一季（WP-VAL1 §3.1）
WF_LAST = 2026
VAL_FIRST = 2023          # 首個可校準驗證季（2021–22 供第一個校準窗）
VAL_LAST = 2026
SELECT_FIT = 2021         # 選型內部窗：fit 2021 → eval 2022（皆 < VAL_FIRST）
SELECT_EVAL = 2022
EPS = 1e-6                # beta calibration 的機率 clip
MIN_AB = 1e-3             # beta a,b 下限（單調與端點收斂的硬保證）

# 校準層門檻。v2 門檻（pooled_bin_dev_max / min_coverage / boot_*）直接沿用
# winprob_val.THRESHOLDS，不另立寬鬆標準。以下為本卡新增、跑驗證前預先註冊：
CAL_THRESHOLDS = {
    "min_cal_pairs": 5000,       # 校準訓練對下限（不足即拒絕擬合，fail closed）
    "iso_min_bin_n": 500,        # isotonic 每箱最少 PA（尾端小樣本過擬合防護）
    "iso_max_bins": 50,          # isotonic 箱數上限（段數上限）
    # 逐局帶診斷（紅線 5）：帶 |pred−actual| 相對 base 增加 > 1pt 記一次惡化
    # （≈ 池化帶級叢集雜訊底線）；例行帶（1-3/4-6/7-9）有 ≥2 帶惡化、或單帶
    # 惡化 > 2pt → 硬性失敗；單帶 (1,2]pt → disclosure。10+ 帶只列揭露。
    "band_dev_worsen_pt": 0.01,
    "band_dev_worsen_hard_pt": 0.02,
}


# ───────────────────────── isotonic（等量分箱 + 加權 PAV + 端點釘） ─────────────────────────
@dataclass(frozen=True)
class IsotonicCalibrator:
    """分段線性單調校準：knots 首尾釘 (0,0)/(1,1)，中間為 PAV 區塊加權質心。"""

    xs: tuple[float, ...]
    ys: tuple[float, ...]
    bin_ns: tuple[int, ...]      # 各 PAV 區塊樣本數（留痕；不含端點錨）

    family = "isotonic"

    def predict(self, p: float) -> float:
        p = min(max(p, 0.0), 1.0)
        xs, ys = self.xs, self.ys
        if p <= xs[0]:
            return ys[0]
        if p >= xs[-1]:
            return ys[-1]
        lo, hi = 0, len(xs) - 1
        while hi - lo > 1:                    # 二分找區段
            mid = (lo + hi) // 2
            if xs[mid] <= p:
                lo = mid
            else:
                hi = mid
        x0, x1, y0, y1 = xs[lo], xs[hi], ys[lo], ys[hi]
        if x1 <= x0:
            return y1
        return y0 + (y1 - y0) * (p - x0) / (x1 - x0)

    @property
    def n_segments(self) -> int:
        return len(self.bin_ns)

    def params(self) -> dict:
        return {"family": "isotonic", "n_segments": self.n_segments,
                "knots_x": [round(x, 5) for x in self.xs],
                "knots_y": [round(y, 5) for y in self.ys],
                "bin_ns": list(self.bin_ns)}


def fit_isotonic(pairs: list[tuple[float, float]],
                 min_bin_n: int = CAL_THRESHOLDS["iso_min_bin_n"],
                 max_bins: int = CAL_THRESHOLDS["iso_max_bins"]) -> IsotonicCalibrator:
    """等量預分箱（每箱 ≥ min_bin_n、至多 max_bins 箱）後對箱均值跑加權 PAV。

    預分箱即卡面要求的「段數/樣本下限」尾端防護：任何 PAV 區塊估計至少
    基於 min_bin_n 個打席，極端分位不會出現由個位數樣本支撐的階梯。
    排序鍵含 y → 擬合對輸入順序完全不敏感（DB 列序無關，可重跑逐位一致）。
    """
    n = len(pairs)
    if n < CAL_THRESHOLDS["min_cal_pairs"]:
        raise ValueError(f"校準訓練對 {n} < {CAL_THRESHOLDS['min_cal_pairs']}，拒絕擬合")
    data = sorted(pairs)
    n_bins = max(1, min(max_bins, n // min_bin_n))
    # 等量切箱：前 rem 箱多 1 筆
    base, rem = divmod(n, n_bins)
    blocks: list[list[float]] = []           # [sum_x, sum_y, w]
    i = 0
    for b in range(n_bins):
        size = base + (1 if b < rem else 0)
        chunk = data[i:i + size]
        i += size
        blocks.append([sum(p for p, _ in chunk), sum(y for _, y in chunk), len(chunk)])
    # 加權 PAV：後塊均值低於前塊 → 合併
    pav: list[list[float]] = []
    for blk in blocks:
        pav.append(blk)
        while len(pav) >= 2 and pav[-2][1] * pav[-1][2] > pav[-1][1] * pav[-2][2]:
            sx, sy, w = pav.pop()
            pav[-1][0] += sx
            pav[-1][1] += sy
            pav[-1][2] += w
    xs = [0.0]
    ys = [0.0]
    bin_ns = []
    for sx, sy, w in pav:
        x, y = sx / w, min(max(sy / w, 0.0), 1.0)
        if x <= xs[-1] + 1e-12:              # 與前 knot 同位 → 保守取後值（仍單調）
            ys[-1] = max(ys[-1], y)
            if bin_ns:
                bin_ns[-1] += int(w)
            continue
        xs.append(x)
        ys.append(y)
        bin_ns.append(int(w))
    if xs[-1] < 1.0:
        xs.append(1.0)
        ys.append(1.0)
    else:
        ys[-1] = 1.0
    return IsotonicCalibrator(tuple(xs), tuple(ys), tuple(bin_ns))


# ───────────────────────── beta calibration（3 參數對照） ─────────────────────────
@dataclass(frozen=True)
class BetaCalibrator:
    """logit(q) = a·ln p − b·ln(1−p) + c，a,b ≥ MIN_AB > 0 ⇒ 單調且 f(0)=0、f(1)=1。"""

    a: float
    b: float
    c: float
    at_bound: bool               # a 或 b 收斂在下限（異常訊號，留痕）

    family = "beta"

    def predict(self, p: float) -> float:
        if p <= 0.0:
            return 0.0
        if p >= 1.0:
            return 1.0
        pc = min(max(p, EPS), 1.0 - EPS)
        z = self.a * math.log(pc) - self.b * math.log(1.0 - pc) + self.c
        if z >= 0:
            return 1.0 / (1.0 + math.exp(-z))
        e = math.exp(z)
        return e / (1.0 + e)

    def params(self) -> dict:
        return {"family": "beta", "a": round(self.a, 6), "b": round(self.b, 6),
                "c": round(self.c, 6), "at_bound": self.at_bound}


def fit_beta(pairs: list[tuple[float, float]]) -> BetaCalibrator:
    """以 Newton 法（帶回溯線搜尋 + 投影 a,b ≥ MIN_AB）最小化平均 log-loss。

    y ∈ {0, 0.5, 1}（和局 0.5）對 Bernoulli log-loss 仍是 proper score。
    問題凸、參數僅 3 個 → 決定性收斂，無隨機性。
    """
    import numpy as np

    n = len(pairs)
    if n < CAL_THRESHOLDS["min_cal_pairs"]:
        raise ValueError(f"校準訓練對 {n} < {CAL_THRESHOLDS['min_cal_pairs']}，拒絕擬合")
    data = sorted(pairs)
    p = np.clip(np.array([x for x, _ in data]), EPS, 1.0 - EPS)
    y = np.array([t for _, t in data])
    X = np.column_stack([np.log(p), -np.log(1.0 - p), np.ones(n)])
    theta = np.array([1.0, 1.0, 0.0])        # 起點 = 恆等映射

    def loss(th: np.ndarray) -> float:
        q = 1.0 / (1.0 + np.exp(-X @ th))
        q = np.clip(q, EPS, 1.0 - EPS)
        return float(-np.mean(y * np.log(q) + (1.0 - y) * np.log(1.0 - q)))

    cur_loss = loss(theta)
    for _ in range(100):
        q = 1.0 / (1.0 + np.exp(-X @ theta))
        grad = X.T @ (q - y) / n
        if float(np.max(np.abs(grad))) < 1e-9:
            break
        w = np.clip(q * (1.0 - q), 1e-12, None)
        hess = (X * w[:, None]).T @ X / n + 1e-10 * np.eye(3)
        step = np.linalg.solve(hess, grad)
        t = 1.0
        cand, cand_loss = theta, cur_loss        # 線搜尋全敗 → 原地不動即收斂
        for _ in range(30):
            trial = theta - t * step
            trial[0] = max(trial[0], MIN_AB)
            trial[1] = max(trial[1], MIN_AB)
            trial_loss = loss(trial)
            if trial_loss <= cur_loss + 1e-15:
                cand, cand_loss = trial, trial_loss
                break
            t *= 0.5
        if np.allclose(cand, theta, atol=1e-12):
            break
        theta, cur_loss = cand, cand_loss
    a, b, c = float(theta[0]), float(theta[1]), float(theta[2])
    return BetaCalibrator(a, b, c, at_bound=(a <= MIN_AB or b <= MIN_AB))


# ───────────────────────── 嵌套窗口（紅線 1/2 的唯一取數入口） ─────────────────────────
def calibration_pairs(wf_by_season: dict[int, list], target_year: int,
                      first_season: int = WF_FIRST) -> tuple[list[int], list[tuple[float, float]]]:
    """驗證季 target_year 的校準訓練對：只取 s ∈ [first_season, target_year−1]。

    wf_by_season[s] 是 winprob_val score_pas 的輸出（(wp, outcome, irregular,
    game_key) 元組），該 wp 由 span ≤ s−1 的 base 模型產生 → 對 target_year
    是嚴格時間外。含 irregular 場（與主評估母體一致；模型無法預知提前結束，
    排除反而引入選擇偏誤——WP-VAL1 §4 同語意）。
    """
    seasons = [s for s in sorted(wf_by_season) if first_season <= s < target_year]
    if not seasons:
        raise ValueError(f"驗證季 {target_year} 無可用校準窗（首季 {first_season}）")
    assert all(s < target_year for s in seasons), f"嵌套窗口洩漏：{seasons} vs {target_year}"
    pairs = [(wp, y) for s in seasons for wp, y, _irr, _gk in wf_by_season[s]]
    return seasons, pairs


def apply_calibrator(cal, scored: list) -> list:
    """對 score_pas 輸出逐 PA 套用校準；保留 outcome/irregular/game_key。"""
    return [(cal.predict(wp), y, irr, gk) for wp, y, irr, gk in scored]


# ───────────────────────── 選型（紅線 6：只用校準訓練窗內指標） ─────────────────────────
def select_family(internal: dict) -> tuple[str, str]:
    """isotonic vs beta 擇一：內部前向評估（fit 2021 → eval 2022）Brier 低者勝；
    差 < 1e-5 視為同分改比 ECE；再同分取低複雜度（beta，3 參數）。
    internal = {family: {"brier": float, "ece_weighted": float}}。"""
    iso, beta = internal["isotonic"], internal["beta"]
    d_brier = iso["brier"] - beta["brier"]
    if abs(d_brier) >= 1e-5:
        choice = "isotonic" if d_brier < 0 else "beta"
        return choice, (f"內部前向評估 Brier：isotonic {iso['brier']:.5f} vs "
                        f"beta {beta['brier']:.5f} → 取 {choice}")
    d_ece = iso["ece_weighted"] - beta["ece_weighted"]
    if abs(d_ece) >= 1e-5:
        choice = "isotonic" if d_ece < 0 else "beta"
        return choice, (f"Brier 同分（差 {d_brier:+.6f}），ECE：isotonic "
                        f"{iso['ece_weighted']:.5f} vs beta {beta['ece_weighted']:.5f} → 取 {choice}")
    return "beta", "Brier 與 ECE 皆同分 → 取低複雜度 beta（3 參數）"


# ───────────────────────── 逐局帶診斷（紅線 5） ─────────────────────────
BANDS = ("1-3", "4-6", "7-9", "10+")
REGULATION_BANDS = ("1-3", "4-6", "7-9")


def band_of(inning: int) -> str:
    return ("1-3" if inning <= 3 else "4-6" if inning <= 6
            else "7-9" if inning <= 9 else "10+")


def band_summary(innings: list[int], scored: list) -> dict:
    groups: dict[str, list[tuple[float, float]]] = {b: [] for b in BANDS}
    for inn, (wp, y, _irr, _gk) in zip(innings, scored, strict=True):
        groups[band_of(inn)].append((wp, y))
    out = {}
    for b in BANDS:
        rows = groups[b]
        if not rows:
            continue
        n = len(rows)
        out[b] = {"n": n,
                  "pred": round(sum(w for w, _ in rows) / n, 4),
                  "actual": round(sum(y for _, y in rows) / n, 4),
                  "brier": round(sum((w - y) ** 2 for w, y in rows) / n, 5)}
    return out


# ───────────────────────── 判定（v2 門檻 + 卡面新增條件） ─────────────────────────
def cal_verdict(season_rows: list[dict], pooled_cal: dict,
                pooled_bands_base: dict, pooled_bands_cal: dict) -> dict:
    """A scope（含校準層）Go/No-Go。硬性失敗任一 → unsupported（No-Go）：
    - 任一驗證季 coverage < 0.98；
    - 任一驗證季校準後 Brier 未勝主場常數基準，或劣於未校準 base；
    - 池化（2023–26）n≥1000 十分位 |dev| > 0.03 且 99% 叢集 CI 排除 0；
    - 例行局帶（1-3/4-6/7-9）相對 base 系統性惡化（≥2 帶 |dev| 增 >1pt，
      或單帶增 >2pt）。
    其餘 supported；顯著但受控的分箱、10+ 帶變化列 disclosure。"""
    hard: list[str] = []
    disclosure: list[str] = []
    for s in season_rows:
        tag = f"A{s['year']}"
        cal = s["calibrated"]
        base = s["base"]
        if s["coverage"] < THRESHOLDS["min_coverage"]:
            hard.append(f"{tag} coverage {s['coverage']} < {THRESHOLDS['min_coverage']}")
        if cal["brier"] >= s["baseline_home_const"]["brier"]:
            hard.append(f"{tag} 校準後 Brier {cal['brier']} 未勝主場常數基準 "
                        f"{s['baseline_home_const']['brier']}")
        if cal["brier"] > base["brier"]:
            hard.append(f"{tag} 校準後 Brier {cal['brier']} 劣於未校準 base {base['brier']}")
        if cal.get("significant_bins"):
            disclosure.append(f"{tag} 逐季顯著偏差分箱 {cal['significant_bins']}"
                              "（99% 叢集 CI 排除 0）")
    for d in pooled_cal.get("deciles", []):
        ci = d.get("dev_ci")
        if ci is None or d["n"] < 1000:
            continue
        dev = d["pred"] - d["actual"]
        if ci[0] > 0 or ci[1] < 0:
            if abs(dev) > THRESHOLDS["pooled_bin_dev_max"]:
                hard.append(f"池化十分位 {d['bin']} 偏差 {dev:+.4f} 顯著且超過 "
                            f"±{THRESHOLDS['pooled_bin_dev_max']}（n={d['n']}）")
            else:
                disclosure.append(f"池化十分位 {d['bin']} 偏差 {dev:+.4f} 顯著但幅度受控"
                                  f"（n={d['n']}）")
    worsened: list[str] = []
    for b in REGULATION_BANDS:
        pb, cb = pooled_bands_base.get(b), pooled_bands_cal.get(b)
        if not pb or not cb:
            continue
        delta = abs(cb["pred"] - cb["actual"]) - abs(pb["pred"] - pb["actual"])
        if delta > CAL_THRESHOLDS["band_dev_worsen_hard_pt"]:
            hard.append(f"局帶 {b} |dev| 相對 base 惡化 {delta * 100:+.1f}pt > 2pt")
        elif delta > CAL_THRESHOLDS["band_dev_worsen_pt"]:
            worsened.append(b)
            disclosure.append(f"局帶 {b} |dev| 相對 base 惡化 {delta * 100:+.1f}pt")
    if len(worsened) >= 2:
        hard.append(f"例行局帶系統性惡化：{worsened} 皆 |dev| 增 >1pt")
    if "10+" in pooled_bands_cal and "10+" in pooled_bands_base:
        pb, cb = pooled_bands_base["10+"], pooled_bands_cal["10+"]
        disclosure.append(
            f"10+ 帶（含 2024+ 突破僵局，n={cb['n']}，樣本小僅揭露）："
            f"base |dev| {abs(pb['pred'] - pb['actual']) * 100:.1f}pt → "
            f"校準後 {abs(cb['pred'] - cb['actual']) * 100:.1f}pt")
    status = "unsupported" if hard else "supported"
    return {"status": status, "reasons": hard, "disclosure": disclosure}


# ───────────────────────── 主流程 ─────────────────────────
def run_calibration(out_path: Path) -> dict:
    result: dict = {
        "card": "GAME-RECAP-WP-CAL1",
        "kind": KIND,
        "val_seasons": [VAL_FIRST, VAL_LAST],
        "thresholds": {**THRESHOLDS, **CAL_THRESHOLDS},
        "seasons": [],
    }
    with conn() as c:
        cur = c.cursor()
        per_year = collect_training_counts(cur, KIND, FIRST_YEAR, WF_LAST)
        # 逐季 walk-forward 預測（= winprob_val wf 輸出；span 恆 ≤ s−1）
        wf: dict[int, dict] = {}
        for y in range(WF_FIRST, WF_LAST + 1):
            season = load_eval_season(cur, KIND, y)
            if not season["pas"]:
                continue
            span_end = y - 1
            dist = dist_from_counts(per_year, FIRST_YEAR, span_end)
            wf[y] = {
                "scored": score_pas(dist, season["rules"], season["pas"]),
                "innings": [p["inning"] for p in season["pas"]],
                "coverage": season["coverage"],
                "pa_state_counts": season["pa_state_counts"],
                "n_completed_games": season["n_completed_games"],
                "n_irregular_games": season["n_irregular_games"],
                "span_end": span_end,
                "model_span": f"{FIRST_YEAR}-{span_end}/{KIND}",
                "home_p": home_rate_from_games(cur, KIND, FIRST_YEAR, span_end),
            }
            log.info("wf %s %d [%s]：n_pa=%d", KIND, y, wf[y]["model_span"],
                     len(wf[y]["scored"]))
    # 紅線 1 稽核：每季 wf 預測的 base span 必須 ≤ s−1
    for s, row in wf.items():
        assert row["span_end"] <= s - 1, f"wf {s} base span {row['span_end']} 洩漏"
    scored_by_season = {s: row["scored"] for s, row in wf.items()}

    # 選型（紅線 6）：fit 2021 → 內部前向評估 2022；皆 < VAL_FIRST
    assert SELECT_FIT < SELECT_EVAL < VAL_FIRST
    _, sel_pairs = calibration_pairs(scored_by_season, SELECT_EVAL)
    internal = {}
    sel_fits = {"isotonic": fit_isotonic(sel_pairs), "beta": fit_beta(sel_pairs)}
    for fam, cal in sel_fits.items():
        m = metrics(apply_calibrator(cal, scored_by_season[SELECT_EVAL]))
        internal[fam] = {"brier": m["brier"], "ece_weighted": m["ece_weighted"],
                         "n_pa": m["n_pa"], "params": cal.params()}
    base_sel = metrics(scored_by_season[SELECT_EVAL])
    chosen, rationale = select_family(internal)
    result["selection"] = {
        "window": {"fit": SELECT_FIT, "eval": SELECT_EVAL},
        "internal": internal,
        "internal_base": {"brier": base_sel["brier"],
                          "ece_weighted": base_sel["ece_weighted"]},
        "chosen": chosen,
        "rationale": rationale,
    }
    log.info("選型（內部窗 fit %d → eval %d）：%s；%s", SELECT_FIT, SELECT_EVAL,
             chosen, rationale)

    # 逐驗證季：校準窗 = [WF_FIRST, Y−1] 的 wf 對；兩族並行，判定只用 chosen
    pooled_scored = {"base": [], "isotonic": [], "beta": []}
    pooled_innings: list[int] = []
    pooled_baseline_num = 0.0
    for y in range(VAL_FIRST, VAL_LAST + 1):
        if y not in wf:
            continue
        row_wf = wf[y]
        cal_seasons, pairs = calibration_pairs(scored_by_season, y)
        assert max(cal_seasons) <= y - 1 and max(cal_seasons) < y
        fits = {"isotonic": fit_isotonic(pairs), "beta": fit_beta(pairs)}
        base_scored = row_wf["scored"]
        base_m = metrics(base_scored, bootstrap=True)
        home_p = row_wf["home_p"]
        srow: dict = {
            "year": y,
            "model_span": row_wf["model_span"],
            "cal_window": f"{cal_seasons[0]}-{cal_seasons[-1]}(wf)",
            "cal_n_pairs": len(pairs),
            "coverage": row_wf["coverage"],
            "n_completed_games": row_wf["n_completed_games"],
            "n_irregular_games": row_wf["n_irregular_games"],
            "pa_state_counts": row_wf["pa_state_counts"],
            "baseline_home_const": {"p": home_p,
                                    "brier": brier_constant(base_scored, home_p)},
            "base": base_m,
            "inning_bands": {"base": band_summary(row_wf["innings"], base_scored)},
            "calibrator_params": {},
        }
        for fam, cal in fits.items():
            cal_scored = apply_calibrator(cal, base_scored)
            srow[fam] = metrics(cal_scored, bootstrap=True)
            srow[f"{fam}_regular_only"] = metrics(cal_scored, exclude_irregular=True)
            srow["inning_bands"][fam] = band_summary(row_wf["innings"], cal_scored)
            srow["calibrator_params"][fam] = cal.params()
            pooled_scored[fam].extend(cal_scored)
        srow["calibrated"] = srow[chosen]        # 判定視角（chosen 族）
        pooled_scored["base"].extend(base_scored)
        pooled_innings.extend(row_wf["innings"])
        pooled_baseline_num += srow["baseline_home_const"]["brier"] * base_m["n_pa"]
        result["seasons"].append(srow)
        log.info("%s %d cal[%s] base Brier=%.5f iso=%.5f beta=%.5f（主場基準 %.5f）",
                 KIND, y, srow["cal_window"], base_m["brier"],
                 srow["isotonic"]["brier"], srow["beta"]["brier"],
                 srow["baseline_home_const"]["brier"])

    pooled: dict = {}
    pooled_bands: dict = {}
    for fam in ("base", "isotonic", "beta"):
        pooled[fam] = metrics(pooled_scored[fam], bootstrap=True)
        pooled_bands[fam] = band_summary(pooled_innings, pooled_scored[fam])
    if pooled["base"].get("n_pa"):
        pooled["baseline_home_const_brier"] = round(
            pooled_baseline_num / pooled["base"]["n_pa"], 5)
    result["pooled"] = pooled
    result["pooled_inning_bands"] = pooled_bands
    result["verdict"] = cal_verdict(result["seasons"], pooled[chosen],
                                    pooled_bands["base"], pooled_bands[chosen])
    result["verdict"]["chosen_family"] = chosen

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=1))
    log.info("artifact → %s", out_path)
    return result


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    ap = argparse.ArgumentParser(description="GAME-RECAP-WP-CAL1 事後校準層（唯讀）")
    ap.add_argument("--out", default="docs/research/game_recap_wp_cal1_metrics.json")
    args = ap.parse_args()
    result = run_calibration(Path(args.out))
    v = result["verdict"]
    sel = result["selection"]
    print(f"\n=== GAME-RECAP-WP-CAL1 A scope（校準族：{v['chosen_family']}）：{v['status']} ===")
    print(f"  選型：{sel['rationale']}")
    for label, items in (("硬性", v["reasons"]), ("揭露", v.get("disclosure", []))):
        for r in items:
            print(f"  [{label}] {r}")
    pooled = result["pooled"]
    for fam in ("base", "isotonic", "beta"):
        m = pooled[fam]
        if not m.get("n_pa"):
            continue
        print(f"  池化 2023–26 {fam}: n_pa={m['n_pa']} Brier={m['brier']} "
              f"ECE={m['ece_weighted']} 顯著分箱={m.get('significant_bins')}")
    print(f"  池化主場常數基準 Brier={pooled.get('baseline_home_const_brier')}")
    for s in result["seasons"]:
        print(f"  {s['year']} [{s['model_span']}|cal {s['cal_window']} n={s['cal_n_pairs']}] "
              f"base={s['base']['brier']} iso={s['isotonic']['brier']} "
              f"beta={s['beta']['brier']} 主場基準={s['baseline_home_const']['brier']} "
              f"cov={s['coverage']}")


if __name__ == "__main__":
    main()
