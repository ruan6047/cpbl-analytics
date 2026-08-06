"""RESEARCH-VERDICT-AUDIT1 §1 — 否定判定的指令窮舉掃描。

用途：產生「哪些研究產物帶否定判定」的清單，作為重審母體。**不得人工挑選**——
本腳本掃 `docs/research/` 底下**全部**檔案，命中清單與行號一律由輸出 artifact 提供。

設計取捨：

- **寧可過度命中**。詞彙表刻意寬鬆（含 `失敗`／`❌`／`不足` 這類會大量誤中的詞），
  漏掉一份帶否定判定的報告，比多列十份無關檔案嚴重得多。收斂交給第二階段的
  人工三問，且每一次排除都必須在 VERDICTS.md 留下理由。
- **分層而非過濾**。tier1＝判定語彙本身（`No-Go`／`unsupported`／`不採用`…），
  tier2＝三準則的病灶語彙（`小樣本`／`覆蓋`／`落後`／`漂移`…）。tier2 單獨命中
  不構成否定判定，但會標記出「該檔的判定可能踩到準則 1/2/3」。
- **JSON 另走結構化擷取**。研究 artifact 常把判定存在 `verdict` 欄，正則掃全文會
  漏掉巢狀結構，故對 `.json` 另做遞迴走訪，記錄 `verdict`-類鍵的實際值與路徑。

輸出：
- `verdict_scan.json` — 逐檔逐行命中明細（機器可讀，供 VERDICTS.md 引用）
- stdout — 摘要表

唯讀：本腳本不讀 DB、不寫 `docs/research/RESEARCH-VERDICT-AUDIT1/` 以外的任何路徑。

用法：
    uv run python docs/research/RESEARCH-VERDICT-AUDIT1/scan_verdicts.py
"""

from __future__ import annotations

import json
import re
import subprocess
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SCAN_ROOT = REPO_ROOT / "docs" / "research"
OUT_DIR = REPO_ROOT / "docs" / "research" / "RESEARCH-VERDICT-AUDIT1"
OUT_PATH = OUT_DIR / "verdict_scan.json"

# tier1：判定語彙。命中即進入重審母體。
TIER1_PATTERNS: dict[str, str] = {
    "no_go": r"No[-\s]?Go|NO[-\s]?GO|NoGo|NOGO",
    "unsupported": r"unsupported|UNSUPPORTED",
    "not_adopted": r"不採用|不予採用|未採用|不採納|否決|駁回",
    "not_passed": r"未通過|不通過|未達標|未達門檻|不達標|沒有?通過",
    "infeasible": r"不可行|infeasible|INFEASIBLE|做不到|辦不到|無法實作",
    "rejected_gate": r"❌",
    "not_supported_claim": r"不支持|不支援(?!的)|無法支撐|不足以支撐|不成立",
    "not_recommended": r"不建議|建議不|勿採用|應放棄|予以封存",
    "abandon": r"放棄|封存|停止追查|終止追查|收攤",
    "fail_word": r"\bFAIL\b|\bFAILED\b|失敗",
    "negative_verdict_zh": r"結論[：:]\s*(不|否|無)|判定[：:]\s*(不|否|無)",
}

# tier2：三準則的病灶語彙。不構成否定判定，用來標記「這份可能踩到準則 1/2/3」。
TIER2_PATTERNS: dict[str, str] = {
    "c1_drift": r"漂移|drift|母體增長|隨時間變動|as-of|as of|快照時點|管線落後|落後\s*\d+\s*場|尚未重建|尚未回填",
    "c2_outlier": r"離群|outlier|少數幾筆|個案|異常值|單一案例|逐筆查證|人工判讀|資料錯誤|資料缺失|覆蓋缺口|非隨機",
    "c3_small_n": r"小樣本|樣本不足|樣本數不足|樣本極小|n\s*=\s*[0-9]\b|僅\s*\d+\s*場|只有\s*\d+\s*場|統計檢定力|power",
}

# 掃描副檔名。研究產物只有 md 與 json 兩種。
SCAN_SUFFIXES = {".md", ".json"}

# JSON 結構化擷取：這些鍵名的值直接當判定紀錄。
VERDICT_KEY_RE = re.compile(r"verdict|decision|go_no_go|gate|conclusion|status|result", re.I)
NEGATIVE_VALUE_RE = re.compile(
    r"^(unsupported|no[-_\s]?go|fail(ed)?|reject(ed)?|false|不採用|未通過|不可行)$", re.I
)

TIER1_RE = {name: re.compile(pat) for name, pat in TIER1_PATTERNS.items()}
TIER2_RE = {name: re.compile(pat) for name, pat in TIER2_PATTERNS.items()}


@dataclass
class Hit:
    """一筆命中：檔案相對路徑 + 行號 + 類別 + 該行原文（截斷）。"""

    path: str
    line: int
    tier: int
    category: str
    matched: str
    snippet: str


def _iter_files() -> list[Path]:
    """列出掃描母體。用 git ls-files 而非 os.walk：確保只掃版控內的檔案，
    避免把本卡自己的中間產物或 .gitignore 的雜物算進母體。"""
    out = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "ls-files", "--", "docs/research"],
        capture_output=True,
        text=True,
        check=True,
    )
    paths = []
    for line in out.stdout.splitlines():
        p = REPO_ROOT / line
        if p.suffix.lower() in SCAN_SUFFIXES and p.is_file():
            paths.append(p)
    return sorted(paths)


def _scan_text(path: Path) -> list[Hit]:
    rel = str(path.relative_to(REPO_ROOT))
    hits: list[Hit] = []
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return hits
    for lineno, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        for tier, table in ((1, TIER1_RE), (2, TIER2_RE)):
            for category, rx in table.items():
                m = rx.search(line)
                if m:
                    hits.append(
                        Hit(
                            path=rel,
                            line=lineno,
                            tier=tier,
                            category=category,
                            matched=m.group(0)[:60],
                            snippet=stripped[:240],
                        )
                    )
    return hits


def _walk_json(node: object, path: str, out: list[dict[str, object]]) -> None:
    if isinstance(node, dict):
        for k, v in node.items():
            child = f"{path}.{k}" if path else str(k)
            if isinstance(v, str) and VERDICT_KEY_RE.search(str(k)):
                out.append(
                    {
                        "json_path": child,
                        "key": str(k),
                        "value": v[:120],
                        "negative": bool(NEGATIVE_VALUE_RE.match(v.strip())),
                    }
                )
            elif isinstance(v, bool) and VERDICT_KEY_RE.search(str(k)):
                out.append(
                    {"json_path": child, "key": str(k), "value": v, "negative": v is False}
                )
            _walk_json(v, child, out)
    elif isinstance(node, list):
        # 只走前 400 個元素：大 artifact 的逐筆陣列不含判定欄，走完只是浪費時間。
        for i, v in enumerate(node[:400]):
            _walk_json(v, f"{path}[{i}]", out)


def _scan_json_structure(path: Path) -> list[dict[str, object]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return []
    found: list[dict[str, object]] = []
    _walk_json(data, "", found)
    return found


def main() -> None:
    files = _iter_files()
    all_hits: list[Hit] = []
    json_verdicts: dict[str, list[dict[str, object]]] = {}

    for p in files:
        all_hits.extend(_scan_text(p))
        if p.suffix.lower() == ".json":
            found = _scan_json_structure(p)
            neg = [f for f in found if f["negative"]]
            if neg:
                rel = str(p.relative_to(REPO_ROOT))
                # 同一 json_path 前綴可能重複數百筆，壓成 (key, value) 計數
                counter = Counter((str(f["key"]), str(f["value"])) for f in neg)
                json_verdicts[rel] = [
                    {"key": k, "value": v, "count": c} for (k, v), c in counter.most_common()
                ]

    per_file: dict[str, dict[str, object]] = {}
    for h in all_hits:
        entry = per_file.setdefault(
            h.path,
            {"tier1_count": 0, "tier2_count": 0, "tier1_categories": [], "tier2_categories": []},
        )
        key_count = "tier1_count" if h.tier == 1 else "tier2_count"
        key_cats = "tier1_categories" if h.tier == 1 else "tier2_categories"
        entry[key_count] = int(entry[key_count]) + 1  # type: ignore[arg-type]
        cats = entry[key_cats]
        assert isinstance(cats, list)
        if h.category not in cats:
            cats.append(h.category)

    # 重審母體＝任一 tier1 命中，或 JSON 結構化判定欄為否定值。
    population = sorted(
        set(k for k, v in per_file.items() if int(v["tier1_count"]) > 0) | set(json_verdicts)
    )

    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "repo_head": subprocess.run(
            ["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip(),
        "scan_root": str(SCAN_ROOT.relative_to(REPO_ROOT)),
        "scanned_file_count": len(files),
        "scanned_files": [str(p.relative_to(REPO_ROOT)) for p in files],
        "tier1_patterns": TIER1_PATTERNS,
        "tier2_patterns": TIER2_PATTERNS,
        "population_size": len(population),
        "population": population,
        "per_file": per_file,
        "json_structured_negative_verdicts": json_verdicts,
        "hits": [asdict(h) for h in all_hits],
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"scanned files      : {len(files)}")
    print(f"total hits         : {len(all_hits)}  (tier1={sum(1 for h in all_hits if h.tier == 1)})")
    print(f"review population  : {len(population)} files with >=1 tier1 hit or negative json verdict")
    print(f"artifact           : {OUT_PATH.relative_to(REPO_ROOT)}")
    print()
    print(f"{'tier1':>6} {'tier2':>6}  file")
    for rel in population:
        e = per_file.get(rel, {"tier1_count": 0, "tier2_count": 0})
        print(f"{e['tier1_count']:>6} {e['tier2_count']:>6}  {rel}")


if __name__ == "__main__":
    main()
