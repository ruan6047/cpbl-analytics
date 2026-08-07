"""ML-WP-VAL-RESAMPLE1：受影響打席母體的**逐季**普查（唯讀；由指令產生，非人工聲明）。

對每個 (kind, year)，以同一支 `winprob_val.load_eval_season()` 各跑一次
`pre_score_source="events"`（修正）與 `"pre_state"`（舊讀法），逐打席
（key＝`(game_sno, pa_index)`）比對局面分差，輸出：

* `n_ready_scored`：兩讀法皆進入評分樣本的打席數（共同母體）
* `n_changed` / `pct_changed`：分差改變的打席數與比例
* `delta_hist`：Δdiff（新 − 舊）的完整分布
* `n_unresolved`：事件流解不出打席前比分而 fail closed 排除的 ready 打席
* `n_legacy_only`：舊讀法有、修正後被排除的打席（＝`n_unresolved`，對帳用）

跨季不得以單季推論全期——每一季各自出數，全期只是逐季相加。

執行（worktree 內）::

    uv run python docs/research/ML-WP-VAL-RESAMPLE1/census.py \
        --out docs/research/ML-WP-VAL-RESAMPLE1/population_census.json
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from cpbl.db import conn
from cpbl.models.winprob_val import load_eval_season

# VAL1 的驗證 scope 與年段（winprob_val.run_validation 的 eval_years），另把 A/D
# 往前補到 canonical PA 起始年，讓「跨季」宣稱涵蓋全部有 published build 的季。
SCOPES: dict[str, range] = {
    "A": range(2018, 2027),
    "C": range(2018, 2026),
    "D": range(2018, 2027),
    "E": range(2018, 2026),
}


def census_one(cur, kind: str, year: int) -> dict | None:
    fixed = load_eval_season(cur, kind, year, pre_score_source="events")
    legacy = load_eval_season(cur, kind, year, pre_score_source="pre_state")
    if not fixed["pas"] and not legacy["pas"]:
        return None
    fixed_by = {(p["game_sno"], p["pa_index"]): p["diff"] for p in fixed["pas"]}
    legacy_by = {(p["game_sno"], p["pa_index"]): p["diff"] for p in legacy["pas"]}
    common = fixed_by.keys() & legacy_by.keys()
    hist: Counter = Counter(fixed_by[k] - legacy_by[k] for k in common)
    changed = sum(n for d, n in hist.items() if d != 0)
    unresolved = int(fixed["pa_state_counts"].get("ready_pre_score_unresolved", 0))
    return {
        "kind": kind,
        "year": year,
        "n_completed_games": fixed["n_completed_games"],
        "n_ready_scored": len(common),
        "n_fixed_pas": len(fixed_by),
        "n_legacy_pas": len(legacy_by),
        "n_legacy_only": len(legacy_by.keys() - fixed_by.keys()),
        "n_unresolved": unresolved,
        "n_changed": changed,
        "pct_changed": round(100.0 * changed / len(common), 4) if common else None,
        "delta_hist": {str(d): n for d, n in sorted(hist.items())},
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="docs/research/ML-WP-VAL-RESAMPLE1/"
                                     "population_census.json")
    args = ap.parse_args()
    rows: list[dict] = []
    with conn() as c:
        cur = c.cursor()
        for kind, years in SCOPES.items():
            for year in years:
                row = census_one(cur, kind, year)
                if row is None:
                    continue
                rows.append(row)
                print(f"{kind} {year}: ready={row['n_ready_scored']:>7} "
                      f"changed={row['n_changed']:>5} "
                      f"({row['pct_changed']}%) unresolved={row['n_unresolved']} "
                      f"Δ={row['delta_hist']}")
    totals = {
        "n_ready_scored": sum(r["n_ready_scored"] for r in rows),
        "n_changed": sum(r["n_changed"] for r in rows),
        "n_unresolved": sum(r["n_unresolved"] for r in rows),
    }
    totals["pct_changed"] = (round(100.0 * totals["n_changed"] / totals["n_ready_scored"], 4)
                             if totals["n_ready_scored"] else None)
    merged: Counter = Counter()
    for r in rows:
        for d, n in r["delta_hist"].items():
            merged[int(d)] += n
    totals["delta_hist"] = {str(d): n for d, n in sorted(merged.items())}
    # 逐 scope 彙總：報告表格直接引這裡，不得人工加總
    by_scope: dict[str, dict] = {}
    for r in rows:
        s = by_scope.setdefault(r["kind"], {"years": [], "n_ready_scored": 0,
                                            "n_changed": 0, "n_unresolved": 0})
        s["years"].append(r["year"])
        for key in ("n_ready_scored", "n_changed", "n_unresolved"):
            s[key] += r[key]
    for kind, s in by_scope.items():
        s["year_range"] = [min(s["years"]), max(s["years"])]
        s["pct_changed"] = (round(100.0 * s["n_changed"] / s["n_ready_scored"], 4)
                            if s["n_ready_scored"] else None)
        print(f"[{kind} {s['year_range'][0]}–{s['year_range'][1]}] "
              f"ready={s['n_ready_scored']} changed={s['n_changed']} "
              f"({s['pct_changed']}%) unresolved={s['n_unresolved']}")
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"by_scope_year": rows, "by_scope": by_scope,
                               "totals": totals}, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print(f"\n全期合計：{totals}")
    print(f"artifact → {out}")


if __name__ == "__main__":
    main()
