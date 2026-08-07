"""ML-WP-VAL-RESAMPLE1：池化十分位「顯著性」對 bootstrap seed 的穩健度（唯讀）。

為什麼需要這支：VAL1 的硬性判定是「|dev| 超界 **且** 99% game-cluster CI 排除 0」。
CI 由固定 seed（20260725）的整場重抽算出，**點估計沒動、CI 端點卻跨過 0** 時，
判定會翻面而讀者看不出那是抽樣實現的隨機性。本卡在 A/B 對照中就撞到兩處這種邊界
（A 十分位 7、D 十分位 2），故把「換 seed 後這個分箱還顯不顯著」明確量出來，
而不是拿單一 seed 的翻面當結論。

管線與 `winprob_val.run_validation()` 的池化路徑**逐步同序**：同樣逐 eval year
`score_pas()` 後 `extend`，只有 bootstrap 的 seed 換。

執行（worktree 內）::

    uv run python docs/research/ML-WP-VAL-RESAMPLE1/bin_stability.py \
        --out docs/research/ML-WP-VAL-RESAMPLE1/bin_stability.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from cpbl.db import conn
from cpbl.models.winprob_val import (
    FIRST_YEAR,
    THRESHOLDS,
    TRAIN_PROXY,
    _decile_bins,
    cluster_bootstrap_devs,
    collect_training_counts,
    dist_from_counts,
    load_eval_season,
    score_pas,
)

EVAL_YEARS = {"A": range(2021, 2027), "D": range(2021, 2027)}
SEEDS = [20260725, 1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144]
WATCH = {"A": (2, 3, 7, 8), "D": (1, 2, 3)}


def pooled_scored(cur, kind: str, per_year, source: str) -> list:
    """完全比照 `run_validation()` 的池化累加順序（逐年 score_pas → extend）。"""
    out: list = []
    for year in EVAL_YEARS[kind]:
        season = load_eval_season(cur, kind, year, pre_score_source=source)
        if not season["pas"]:
            continue
        train_to = year - 1
        dist = dist_from_counts(per_year, FIRST_YEAR, train_to)
        out.extend(score_pas(dist, season["rules"], season["pas"]))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="docs/research/ML-WP-VAL-RESAMPLE1/bin_stability.json")
    args = ap.parse_args()
    report: dict = {"seeds": SEEDS, "boot_reps": THRESHOLDS["boot_reps"],
                    "boot_ci": THRESHOLDS["boot_ci"], "scopes": {}}
    with conn() as c:
        cur = c.cursor()
        counts = {k: collect_training_counts(cur, k, FIRST_YEAR, 2026) for k in ("A", "D")}
        for kind in EVAL_YEARS:
            report["scopes"][kind] = {}
            for source in ("events", "pre_state"):
                scored = pooled_scored(cur, kind, counts[TRAIN_PROXY[kind]], source)
                rows = [(wp, y) for wp, y, _, _ in scored]
                bins = _decile_bins(rows)
                devs = {i: (sw / bn - so / bn) for i, (sw, so, bn) in enumerate(bins) if bn}
                ns = {i: bn for i, (_s, _o, bn) in enumerate(bins) if bn}
                per_bin: dict[str, dict] = {}
                for b in WATCH[kind]:
                    per_bin[str(b)] = {"n": ns.get(b), "dev": devs.get(b),
                                       "ci_by_seed": {}, "n_seeds_significant": 0}
                for seed in SEEDS:
                    cis = cluster_bootstrap_devs(scored, THRESHOLDS["boot_reps"],
                                                 THRESHOLDS["boot_ci"], seed=seed)
                    for b in WATCH[kind]:
                        ci = cis.get(b)
                        if ci is None:
                            continue
                        sig = ci["ci"][0] > 0 or ci["ci"][1] < 0
                        per_bin[str(b)]["ci_by_seed"][str(seed)] = {"ci": ci["ci"],
                                                                   "significant": sig}
                        per_bin[str(b)]["n_seeds_significant"] += int(sig)
                report["scopes"][kind][source] = per_bin
                for b, info in per_bin.items():
                    print(f"{kind}/{source} bin{b}: n={info['n']} dev={info['dev']:+.4f} "
                          f"顯著 {info['n_seeds_significant']}/{len(SEEDS)} seeds")
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"artifact → {out}")


if __name__ == "__main__":
    main()
