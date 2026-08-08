"""DOC-G4-FREEZE-STALE1：全庫 G4 觀測凍結陳述盤點（唯讀）。

    uv run python docs/research/DOC-G4-FREEZE-STALE1/scan_g4_freeze.py
    uv run python docs/research/DOC-G4-FREEZE-STALE1/scan_g4_freeze.py --verify

輸出逐行保留命中與機器判定。輸出目錄本身不納入掃描，避免 artifact／掃描器對自身的
「G4／凍結」說明造成不穩定自指；其餘受 Git 追蹤檔案全部納入。
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ARTIFACT_DIR = Path("docs/research/DOC-G4-FREEZE-STALE1")
DEFAULT_OUT = ARTIFACT_DIR / "scan.json"
CANDIDATE_RE = re.compile(
    r"G4.{0,120}(凍結|收窗後|觀測窗)|(凍結|收窗後).{0,120}G4|G4.*freeze|freeze.*G4",
    re.IGNORECASE,
)


def _tracked_files() -> list[str]:
    files = subprocess.run(
        ["git", "ls-files"], capture_output=True, text=True, check=True
    ).stdout.splitlines()
    return [path for path in files if not path.startswith(f"{ARTIFACT_DIR}/")]


def _classify(path: str, text: str) -> tuple[str, str]:
    """回傳該命中現在的治理意義；不把所有「凍結」一律當成已解除的 Gate 3。"""
    if path.startswith("docs/research/DEV-CLI-HELP-GUARD"):
        return "historical_artifact", "已結案 audit 的當時寫入邊界與產出，不改寫歷史證據。"
    if path.startswith("docs/research/INIT-GAME-RECAP"):
        return "historical_artifact", "已結案 research／spike 的當時範圍說明，不改寫歷史證據。"
    if path == "docs/tasks/DOC-G4-FREEZE-STALE1.md":
        return "task_context", "本卡問題與驗收的描述，不是現行凍結宣稱。"
    if ("Phase B" in text or "#53" in text) and ("解除" in text or "提前收窗" in text):
        return (
            "resolved_gate3_with_phase_b_dependency",
            "Gate 3 觀測凍結已解除；鏈端後續仍依賴尚未完成的 #53 G4 Phase B。",
        )
    if "凍結例外" in text:
        return "active_data_exception", "需求方 2026-08-05 裁定的資料例外清單，非 Gate 3 觀測凍結。"
    if "解除" in text or "提前收窗" in text:
        return "resolved_gate3_fact", "明示 Gate 3 已收窗並解除觀測凍結。"
    if "Phase B" in text or "#53" in text:
        return "active_phase_b_dependency", "#53 G4 Phase B 尚未完成，屬目前的資源／實作依賴。"
    if path.startswith("docs/archive/") or path in {
        "docs/tasks/DEV-CLI-HELP-GUARD1.md",
        "docs/tasks/DATA-RE24-GHOST-RUNNER1.md",
    }:
        return "historical_task_record", "已結案卡的當時驗收或資源邊界，保留歷史紀錄。"
    if path in {
        "docs/design/GAME-PAGE-THREE-STATES.md",
        "src/cpbl/models/pa_facts.py",
    }:
        return "active_scope_exclusion", "不動逐球 writer 的範圍約束仍由 #53 資源佔用支撐；術語待其 owner 收斂。"
    return "needs_pm_followup", "未能自動歸入歷史紀錄、Gate 3 已解除事實、Phase B 依賴或資料例外。"


def scan() -> dict[str, Any]:
    hits = []
    for path in _tracked_files():
        try:
            lines = Path(path).read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        for line_no, line in enumerate(lines, 1):
            if not CANDIDATE_RE.search(line):
                continue
            disposition, rationale = _classify(path, line)
            hits.append({
                "file": path,
                "line": line_no,
                "text": line.strip(),
                "disposition": disposition,
                "rationale": rationale,
            })
    counts: dict[str, int] = {}
    for hit in hits:
        counts[hit["disposition"]] = counts.get(hit["disposition"], 0) + 1
    return {
        "generated_at": datetime.now(UTC).astimezone().isoformat(timespec="seconds"),
        "scope": "所有 Git 追蹤檔案，排除本 artifact 目錄以避免自指。",
        "patterns": [CANDIDATE_RE.pattern],
        "total_hits": len(hits),
        "by_disposition": dict(sorted(counts.items())),
        "needs_pm_followup": [hit for hit in hits if hit["disposition"] == "needs_pm_followup"],
        "hits": hits,
    }


def _write(payload: dict[str, Any], out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"written: {out} ({len(payload['hits'])} hits)")


def _verify(out: Path) -> None:
    stored = json.loads(out.read_text(encoding="utf-8"))
    fresh = scan()
    stable = ({k: v for k, v in stored.items() if k != "generated_at"}
              == {k: v for k, v in fresh.items() if k != "generated_at"})
    print(json.dumps({"artifact": str(out), "stable": stable}, ensure_ascii=False))
    if not stable:
        raise SystemExit("artifact 與目前 HEAD 樹不一致；請先重產再查核")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    if args.verify:
        _verify(args.out)
    else:
        _write(scan(), args.out)


if __name__ == "__main__":
    main()
