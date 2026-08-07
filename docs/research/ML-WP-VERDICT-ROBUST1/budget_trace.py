"""ML-WP-VERDICT-ROBUST1 §A — 邊界分箱在 v2 與 v3 兩種讀法下的可重現性實測。

回答兩個問題，全部由指令輸出產生，不靠「我覺得比較穩」：

1. **v2 的判定有多會擲硬幣**：同一份資料、同一個分箱，換 12 個 bootstrap seed，
   「99% CI 排除 0」這個硬性判準各投出什麼票。這是 `ML-WP-VAL-RESAMPLE1` §5
   `bin_stability.py` 量過的同一件事，本卡把它與新判定並排。
2. **v3 的判定收不收斂**：把同一批重抽依 seed 前綴切成 6,000 / 12,000 / 24,000 /
   48,000 / 96,000 五級預算，看三態決策沿預算的軌跡。收斂到某一態 = 原本的
   翻面只是 Monte Carlo 雜訊；到上限仍 undetermined = 那是資料本身的知識界線。

全程唯讀。重抽只算一次（192 個 seed），各級預算取 seed 前綴，故軌跡內部一致。

輸出 `budget_trace.json` 與 `budget_trace.md`。**它與 `verdict_metrics.json` 一樣是
依賴 DB 的 as-of 快照**（母體每天在長，見統計紅線 #9），故不提供 `--check`
逐位比對——查核者重跑要看的是**決策軌跡是否一致**，不是位元相同。
`compare_verdicts.py --check` 才是「分析由腳本產生、非人工謄寫」的那道保證。

用法::

    uv run python docs/research/ML-WP-VERDICT-ROBUST1/budget_trace.py
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from cpbl.db import conn
from cpbl.models.winprob_val import (
    BOOT_MAX_REPS,
    BOOT_SEEDS,
    FIRST_YEAR,
    MC_TOLERANCE_Z,
    THRESHOLDS,
    TRAIN_PROXY,
    _bin_devs_for_seed,
    _decile_bins,
    _game_bin_matrix,
    _percentile_ci,
    _tail_state,
    collect_training_counts,
    dist_from_counts,
    load_eval_season,
    score_pas,
    seed_ladder,
)

HERE = Path(__file__).resolve().parent
EVAL_YEARS = {"A": range(2021, 2027), "D": range(2021, 2027)}
LADDER = [12, 24, 48, 96, 192]          # seed 數；× boot_reps = 6k…96k 重抽
STATE_MARK = {"significant": "顯著", "not_significant": "不顯著",
              "undetermined": "**判不動**"}


def pooled_scored(cur, kind: str, per_year, source: str = "events") -> list:
    """比照 `run_validation()` 的池化累加順序（逐年 score_pas → extend）。"""
    out: list = []
    for year in EVAL_YEARS[kind]:
        season = load_eval_season(cur, kind, year, pre_score_source=source)
        if not season["pas"]:
            continue
        dist = dist_from_counts(per_year, FIRST_YEAR, year - 1)
        out.extend(score_pas(dist, season["rules"], season["pas"]))
    return out


def trace_scope(scored: list) -> dict:
    reps, ci = THRESHOLDS["boot_reps"], THRESHOLDS["boot_ci"]
    seeds = seed_ladder(LADDER[-1])
    gmat, _ = _game_bin_matrix(scored)
    per_seed = {s: _bin_devs_for_seed(gmat, reps, s) for s in seeds}
    bins = _decile_bins([(wp, y) for wp, y, _, _ in scored])
    rows = []
    for i, (sw, so, bn) in enumerate(bins):
        if not bn or bn < 1000:
            continue
        dev = sw / bn - so / bn
        # v2：註冊 12 seed 各自的單一 seed 判定（本卡病灶的直接量測）
        votes = {}
        for s in BOOT_SEEDS:
            lo, hi = _percentile_ci(per_seed[s][:, i], ci)
            votes[str(s)] = {"ci": [lo, hi], "significant": bool(lo > 0 or hi < 0)}
        n_sig = sum(v["significant"] for v in votes.values())
        # v3：同一批重抽，依 seed 前綴逐級加碼
        traj = []
        for k in LADDER:
            col = np.concatenate([per_seed[s][:, i] for s in seeds[:k]])
            tail = _tail_state(col, ci, MC_TOLERANCE_Z)
            traj.append({"n_seeds": k, "reps_total": k * reps,
                         "state": tail["state"], "p_one": tail["p_one"],
                         "p_one_mc_ci": tail["p_one_mc_ci"],
                         "ci": _percentile_ci(col, ci)})
        rows.append({
            "bin": i, "n": bn, "dev": round(dev, 4),
            "over_threshold": abs(dev) > THRESHOLDS["pooled_bin_dev_max"],
            "v2_seed_votes": {"n_significant": n_sig, "n_seeds": len(BOOT_SEEDS),
                              "unanimous": n_sig in (0, len(BOOT_SEEDS)),
                              "by_seed": votes},
            "v3_trajectory": traj,
            "v3_final_state": traj[-1]["state"],
            "v3_converged_at_reps": next(
                (t["reps_total"] for t in traj if t["state"] != "undetermined"), None),
        })
    return {"n_games": gmat.shape[0], "bins": rows}


def _md(out: dict) -> str:
    L = ["<!-- 由 budget_trace.py 產生，勿手改。 -->", "",
         "### 表 A｜決定性分箱（n≥1000）：v2 的 seed 擲硬幣 vs v3 的預算軌跡", "",
         "| scope-分箱 | n | dev | 超 ±0.03？ | v2 顯著 seed 數 | v2 一致？ | "
         + " | ".join(f"v3 @{k * THRESHOLDS['boot_reps'] // 1000}k" for k in LADDER)
         + " | v3 定案於 |",
         "|---|---:|---:|---|---:|---|" + "---|" * (len(LADDER) + 1)]
    for kind, sc in out["scopes"].items():
        for b in sc["bins"]:
            traj = " | ".join(STATE_MARK[t["state"]] for t in b["v3_trajectory"])
            conv = (f"{b['v3_converged_at_reps']:,}" if b["v3_converged_at_reps"]
                    else "**未定案（撞上限）**")
            L.append(
                f"| {kind}-{b['bin']} | {b['n']:,} | {b['dev']:+.4f} | "
                f"{'**是**' if b['over_threshold'] else '否'} | "
                f"{b['v2_seed_votes']['n_significant']}/{b['v2_seed_votes']['n_seeds']} | "
                f"{'是' if b['v2_seed_votes']['unanimous'] else '**否（擲硬幣）**'} | "
                f"{traj} | {conv} |")
    L += ["", f"> 重抽上限 {BOOT_MAX_REPS:,} 次；各級預算取同一批重抽的 seed 前綴，"
              "故同一列的軌跡內部一致（不是各跑各的）。", ""]
    return "\n".join(L) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--kinds", default="A,D",
                    help="只有 A/D 的池化分箱達到 n≥1000 的決定性門檻；C/E 不適用")
    args = ap.parse_args()
    kinds = [k.strip().upper() for k in args.kinds.split(",") if k.strip()]
    out: dict = {"note": "唯讀；as-of 快照（母體逐日增長，見統計紅線 #9）",
                 "boot_reps_per_seed": THRESHOLDS["boot_reps"],
                 "boot_ci": THRESHOLDS["boot_ci"],
                 "mc_tolerance_z": MC_TOLERANCE_Z,
                 "seed_ladder": LADDER, "scopes": {}}
    with conn() as c:
        cur = c.cursor()
        counts = {k: collect_training_counts(cur, k, FIRST_YEAR, 2026)
                  for k in {TRAIN_PROXY[k] for k in kinds}}
        for kind in kinds:
            scored = pooled_scored(cur, kind, counts[TRAIN_PROXY[kind]])
            out["scopes"][kind] = trace_scope(scored)
    (HERE / "budget_trace.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    (HERE / "budget_trace.md").write_text(_md(out), encoding="utf-8")
    for kind, sc in out["scopes"].items():
        for b in sc["bins"]:
            print(f"{kind}-{b['bin']}: n={b['n']} dev={b['dev']:+.4f} "
                  f"v2顯著 {b['v2_seed_votes']['n_significant']}/12 → "
                  f"v3 {b['v3_final_state']}（定案於 {b['v3_converged_at_reps']}）")
    print(f"artifact → {HERE.name}/budget_trace.json, budget_trace.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
