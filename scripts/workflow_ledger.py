"""由 append-only control-plane events 產生活卡 Ledger。"""

import argparse
import json
from collections.abc import Iterable
from pathlib import Path

ROOT = Path(__file__).parents[1]
EVENTS_PATH = ROOT / "docs/control-plane/events.jsonl"
LEDGER_PATH = ROOT / "docs/TASKS.md"
REQUIRED_FIELDS = {
    "event_id", "card_id", "type", "actor", "occurred_at", "state_version", "iteration",
    "source_sha", "evidence", "initiative", "tier", "feature", "owner", "branch_worktree",
    "delivery_status", "deployment_status",
}


def _latest_events(events: Iterable[dict[str, object]]) -> list[dict[str, object]]:
    by_card: dict[str, list[dict[str, object]]] = {}
    for event in events:
        missing = REQUIRED_FIELDS - event.keys()
        if missing:
            raise ValueError(f"事件缺少欄位：{', '.join(sorted(missing))}")
        if not isinstance(event["state_version"], int):
            raise ValueError("state_version 必須為整數")
        by_card.setdefault(str(event["card_id"]), []).append(event)

    latest: list[dict[str, object]] = []
    for card_id, card_events in by_card.items():
        ordered = sorted(card_events, key=lambda event: int(event["state_version"]))
        versions = [int(event["state_version"]) for event in ordered]
        if versions != list(range(1, len(ordered) + 1)):
            raise ValueError(f"{card_id} 的 state_version 必須從 1 連續遞增")
        latest.append(ordered[-1])
    return sorted(latest, key=lambda event: str(event["card_id"]))


def _cell(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", "<br>")


# 活卡 Ledger 排除已結案卡（archive header：「已完成（🏁）的卡片移到 archive，
# 讓 TASKS.md 只留活卡」）；封存索引與卡片明細在 docs/archive/。event log 仍保留全史。
_CLOSED_STATUSES = {"🏁完成"}


def render_ledger(events: Iterable[dict[str, object]]) -> str:
    """渲染可由事件重建的 `docs/TASKS.md` current-state projection（僅活卡）。"""
    rows = []
    for event in _latest_events(events):
        if str(event["delivery_status"]) in _CLOSED_STATUSES:
            continue
        card_id = _cell(event["card_id"])
        branch_worktree = _cell(event["branch_worktree"])
        if branch_worktree != "—":
            branch_worktree = f"`{branch_worktree}`"
        rows.append(
            "| "
            f"[{card_id}](tasks/{card_id}.md) | {_cell(event['initiative'])} | "
            f"{_cell(event['tier'])} | {_cell(event['feature'])} | {_cell(event['owner'])} | "
            f"{branch_worktree} | {_cell(event['iteration'])} | "
            f"{_cell(event['delivery_status'])} | {_cell(event['deployment_status'])} | "
            f"{_cell(event['occurred_at'])} |"
        )

    return "\n".join([
        "# 任務看板（cpbl-analytics）", "",
        "> 規則見 canonical [`../.ai-workflow/AI_WORKFLOW.md`](../.ai-workflow/AI_WORKFLOW.md) 與本專案 [`AI_WORKFLOW.md`](AI_WORKFLOW.md)。git 是程式碼／文件事實來源；[`control-plane event log`](control-plane/events.jsonl) 是作業狀態事實來源；本檔是它的 current-state projection。",
        "> **不可手動修改表格**：以 `uv run python scripts/workflow_ledger.py --write` 重建；`--check` 驗證投影未漂移。每張卡的範圍與歷史 Log 位於 [`tasks/`](tasks/)；結案後移至 [`archive/tasks/`](archive/tasks/)，索引列移至 [`archive/TASKS_ARCHIVE.md`](archive/TASKS_ARCHIVE.md)。",
        "", "## Ledger 總表（活卡）", "",
        "| 卡ID | Initiative | 級別 | 功能 | owner | 分支／worktree | iteration | 交付狀態 | 部署狀態 | 最後交接 |",
        "|---|---|---|---|---|---|---|---|---|---|", *rows, "", "## 依賴與資源註記", "",
        "- `MATCHUP-DATA1 → ML-MATCHUP1 → UX-MATCHUP1 → UX-MATCHUP2`；前兩卡已結案（ML-MATCHUP1 三輪跨家族審核後 merge `336ee01`，封存於 archive），UI 卡可啟動。",
        "- `RECORD-DATA1 → RECORD-API1 → UX-RECORD1` 已全數結案；UX-RECORD1 已部署並封存。",
        "- `ML-UMP1 → ML-UMP2`：前者已結案封存；身高比例帶重跑可複用其引擎與敏感度框架，方向性呈現仍以 ML-UMP2 翻轉測試為前置閘門。",
        "- `ML-SIM1` 已完成跨家族複查、合併與 production 驗證並封存；`UX-OUTCOME-HOME` 的模型依賴已解除，但仍待 Design／派工。",
        "- `INIT-GAME-RECAP` 仍在 Design Gate；依賴主鏈為 `GAME-RECAP-DATA1 → GAME-RECAP-PA1 → GAME-RECAP-WP-VAL1 → GAME-RECAP-WP-API1 → UX-GAME-RECAP1 → UX-GAME-PA1`，`GAME-RECAP-STATUS1` 與 `UX-GAME-HOME1` 走平行狀態／入口切片。未核可前不得 claim 實作卡。",
        "- 升級前歷史仍封存於 [`archive/TASKS_PRE_WF12.md`](archive/TASKS_PRE_WF12.md)，不得為新格式回寫。", "",
    ])


def _load_events(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def main() -> None:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--write", action="store_true")
    group.add_argument("--check", action="store_true")
    args = parser.parse_args()
    rendered = render_ledger(_load_events(EVENTS_PATH))
    if args.write:
        LEDGER_PATH.write_text(rendered)
    elif LEDGER_PATH.read_text() != rendered:
        raise SystemExit("docs/TASKS.md 與 control-plane event log 不一致；請執行 --write")


if __name__ == "__main__":
    main()
