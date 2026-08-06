"""ML-WP-VAL-RESAMPLE1：VAL1 指標的三路對照（canonical / 今日舊讀法 / 今日修正）。

為什麼一定要三路而不是兩路：canonical artifact 是 2026-07-2x 跑的，母體自那時起已增長
（A 1,826→1,855 場）。只拿 canonical 對「今日修正」，母體變動與取樣修正會混在同一個
差值裡。加跑一路「今日資料 × 舊讀法」當控制組後：

* canonical → pre_state ＝ **母體漂移**（同一把尺、不同資料）
* pre_state → events    ＝ **取樣修正**（同一批資料、不同尺）

一律讀 artifact 內的未捨入值，不先 round 再比。

執行（worktree 內；三份 artifact 需先產出）::

    uv run python docs/research/ML-WP-VAL-RESAMPLE1/compare.py \
        --out docs/research/ML-WP-VAL-RESAMPLE1/val1_comparison.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

BASE = Path("docs/research")
SOURCES = {
    "canonical": BASE / "game_recap_wp_val1_metrics.json",
    "pre_state": BASE / "ML-WP-VAL-RESAMPLE1/val1_metrics_pre_state.json",
    "events": BASE / "ML-WP-VAL-RESAMPLE1/val1_metrics_events.json",
}


def pooled_row(scope: dict) -> dict:
    p = scope["pooled_walk_forward"]
    return {
        "verdict": scope["verdict"]["status"],
        "n_pa": p["n_pa"],
        "n_games": p["n_games"],
        "brier": p["brier"],
        "baseline_home_const_brier": p.get("baseline_home_const_brier"),
        "ece_weighted": p["ece_weighted"],
        "significant_bins": p.get("significant_bins"),
        "deciles": {str(d["bin"]): {"n": d["n"], "dev": d["pred"] - d["actual"],
                                    "ci": d.get("dev_ci")}
                    for d in p["deciles"]},
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="docs/research/ML-WP-VAL-RESAMPLE1/val1_comparison.json")
    args = ap.parse_args()
    loaded = {tag: json.loads(path.read_text(encoding="utf-8"))
              for tag, path in SOURCES.items()}
    out: dict = {"sources": {t: str(p) for t, p in SOURCES.items()}, "scopes": {}}
    for kind in ("A", "C", "D", "E"):
        rows = {t: pooled_row(d["scopes"][kind]) for t, d in loaded.items()
                if kind in d["scopes"]}
        deltas = {}
        if {"canonical", "pre_state", "events"} <= rows.keys():
            for label, (a, b) in (("population_drift", ("canonical", "pre_state")),
                                  ("resampling", ("pre_state", "events"))):
                deltas[label] = {
                    "d_brier": rows[b]["brier"] - rows[a]["brier"],
                    "d_ece": rows[b]["ece_weighted"] - rows[a]["ece_weighted"],
                    "d_n_pa": rows[b]["n_pa"] - rows[a]["n_pa"],
                    "verdict": f'{rows[a]["verdict"]} → {rows[b]["verdict"]}',
                    "d_decile_dev": {
                        k: rows[b]["deciles"][k]["dev"] - rows[a]["deciles"][k]["dev"]
                        for k in rows[b]["deciles"] if k in rows[a]["deciles"]},
                }
        out["scopes"][kind] = {"rows": rows, "deltas": deltas}
        print(f"=== scope {kind} ===")
        for tag in ("canonical", "pre_state", "events"):
            if tag not in rows:
                continue
            r = rows[tag]
            print(f"  {tag:10} {r['verdict']:18} n_pa={r['n_pa']:>7} n_games={r['n_games']:>5} "
                  f"Brier={r['brier']} ECE={r['ece_weighted']} sig={r['significant_bins']}")
        for label, d in deltas.items():
            print(f"  Δ{label:18} ΔBrier={d['d_brier']:+.6f} ΔECE={d['d_ece']:+.6f} "
                  f"Δn_pa={d['d_n_pa']:+d} verdict={d['verdict']}")
    path = Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nartifact → {path}")


if __name__ == "__main__":
    main()
