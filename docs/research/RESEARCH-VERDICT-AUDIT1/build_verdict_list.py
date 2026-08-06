"""RESEARCH-VERDICT-AUDIT1 §3 — 把窮舉母體與逐檔處置合成裁決清單，並硬性檢查覆蓋。

「完整性宣稱一律由指令輸出產生」：本腳本不接受任何形式的人工聲明。它做三件事：

1. 讀 `verdict_scan.json` 的 `population`（指令窮舉出來的重審母體）與
   `dispositions.json` 的 `dispositions`（本卡唯一的人工判斷面）。
2. **雙向比對**——母體有而處置缺 → 漏審；處置有而母體無 → 幽靈條目。任一非空即
   **exit 1**，報告不得宣稱「已逐份重審」。
3. 產出 `verdict_list.json` 與 `verdict_list.md`（VERDICTS.md 的表格由此生成，不人工謄寫）。

用法：
    uv run python docs/research/RESEARCH-VERDICT-AUDIT1/build_verdict_list.py
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
SCAN = HERE / "verdict_scan.json"
DISPOSITIONS = HERE / "dispositions.json"
OUT_JSON = HERE / "verdict_list.json"
OUT_MD = HERE / "verdict_list.md"

CLASS_ORDER = {"S": 0, "S*": 1, "F": 2, "N": 3}
CLASS_LABEL = {
    "S": "S 統計判定",
    "S*": "S* 機器 artifact",
    "F": "F 可行性／規則判定",
    "N": "N 非否定判定",
}


def main() -> int:
    scan: dict[str, Any] = json.loads(SCAN.read_text(encoding="utf-8"))
    disp: dict[str, Any] = json.loads(DISPOSITIONS.read_text(encoding="utf-8"))["dispositions"]

    population = set(scan["population"])
    covered = set(disp)

    missing = sorted(population - covered)
    ghosts = sorted(covered - population)

    if missing or ghosts:
        for m in missing:
            print(f"MISSING DISPOSITION: {m}", file=sys.stderr)
        for g in ghosts:
            print(f"GHOST DISPOSITION (not in scanned population): {g}", file=sys.stderr)
        print(
            f"\nFAIL: population={len(population)} covered={len(covered)} "
            f"missing={len(missing)} ghosts={len(ghosts)}",
            file=sys.stderr,
        )
        return 1

    per_file = scan["per_file"]
    rows = []
    for path in sorted(population, key=lambda p: (CLASS_ORDER[disp[p]["class"]], p)):
        d = disp[path]
        e = per_file.get(path, {})
        rows.append(
            {
                "path": path,
                "class": d["class"],
                "verdict": d["verdict"],
                "scope_verdicts": d.get("scope_verdicts"),
                "parent": d.get("parent"),
                "reason": d["reason"],
                "tier1_hits": e.get("tier1_count", 0),
                "tier2_hits": e.get("tier2_count", 0),
                "tier1_categories": e.get("tier1_categories", []),
            }
        )

    by_class = Counter(r["class"] for r in rows)
    by_verdict = Counter(r["verdict"] for r in rows)
    # 裁決統計只算實際落裁決的（S / F 類）
    actionable = [r for r in rows if r["class"] in ("S", "F")]
    by_verdict_actionable = Counter(r["verdict"] for r in actionable)

    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "scan_generated_at": scan["generated_at"],
        "repo_head": scan["repo_head"],
        "scanned_file_count": scan["scanned_file_count"],
        "population_size": len(population),
        "coverage_check": {
            "population": len(population),
            "dispositions": len(covered),
            "missing": missing,
            "ghosts": ghosts,
            "complete": True,
        },
        "counts_by_class": dict(by_class),
        "counts_by_verdict_all": dict(by_verdict),
        "counts_by_verdict_actionable": dict(by_verdict_actionable),
        "rows": rows,
    }
    OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    lines: list[str] = []
    lines.append("<!-- 本檔由 build_verdict_list.py 產生，勿手改；改處置請改 dispositions.json 後重跑。 -->")
    lines.append("")
    lines.append(f"掃描檔數 {scan['scanned_file_count']}／重審母體 {len(population)}／處置覆蓋 {len(covered)}（missing 0、ghost 0）")
    lines.append("")
    lines.append("裁決分布（S＋F 類，即實際落裁決者）：" + "、".join(
        f"{k} {v}" for k, v in sorted(by_verdict_actionable.items())
    ))
    lines.append("")
    for cls in ("S", "S*", "F", "N"):
        sub = [r for r in rows if r["class"] == cls]
        if not sub:
            continue
        lines.append(f"## {CLASS_LABEL[cls]}（{len(sub)} 份）")
        lines.append("")
        lines.append("| 檔案 | 裁決 | tier1 | 理由 |")
        lines.append("|---|---|---:|---|")
        for r in sub:
            name = r["path"].removeprefix("docs/research/")
            v = r["verdict"]
            if r["scope_verdicts"]:
                v += "（" + "／".join(f"{k}:{x}" for k, x in r["scope_verdicts"].items()) + "）"
            if r["parent"]:
                v += f"（繼承 {r['parent'].removeprefix('docs/research/')}）"
            lines.append(f"| `{name}` | {v} | {r['tier1_hits']} | {r['reason']} |")
        lines.append("")
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"population        : {len(population)}")
    print(f"dispositions      : {len(covered)}  (missing 0, ghosts 0)")
    print(f"counts by class   : {dict(by_class)}")
    print(f"verdicts (S+F)    : {dict(by_verdict_actionable)}")
    print(f"artifacts         : {OUT_JSON.relative_to(REPO_ROOT)}, {OUT_MD.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
