"""由 append-only control-plane events 產生活卡 Ledger。"""

import argparse
import json
import subprocess
from collections.abc import Iterable
from datetime import datetime
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
        "> **本表即當前狀態**：lifecycle 事件一律直接 commit 至 main 並同 commit 重建本檔（[`CONTROL_PLANE_CONTRACT.md`](CONTROL_PLANE_CONTRACT.md)）；執行分支不得改動 control-plane 與本檔。`--live` 可稽核是否有事件違規漏留在分支。",
        "", "## Ledger 總表（活卡）", "",
        "| 卡ID | Initiative | 級別 | 功能 | owner | 分支／worktree | iteration | 交付狀態 | 部署狀態 | 最後交接 |",
        "|---|---|---|---|---|---|---|---|---|---|", *rows, "", "## 依賴與資源註記", "",
        "- `MATCHUP-DATA1 → ML-MATCHUP1 → UX-MATCHUP1` 前置已解除；之後分流至 `UX-PA-SIM-MATCHUP1`，或待 `UX-PLAYER-SECTIONS1` 後進 `UX-MATCHUP2`。",
        "- `RECORD-DATA1 → RECORD-API1 → UX-RECORD1` 已全數結案；UX-RECORD1 已部署並封存。",
        "- `ML-UMP1 → ML-UMP2` 已結案封存，方向性裁判／球隊產品維持 NO-GO；`UX-UMPIRE-SCOPE1` 只負責移除排行與收斂中性介面。",
        "- `ML-SIM1` 已完成跨家族複查、合併與 production 驗證；`UX-OUTCOME-HOME` 只交付 PregameCard，首頁唯一 owner 為 `UX-GAME-HOME1`。",
        "- `INIT-GAME-RECAP` 的資料紅線主鏈維持 `GAME-RECAP-DATA1 → GAME-RECAP-PA1 → GAME-RECAP-WP-VAL1 → GAME-RECAP-WP-API1 → UX-GAME-RECAP1 → UX-GAME-PA1`；首頁 v1 另走 `API-DAILY-SUMMARY1 + UX-OUTCOME-HOME → UX-GAME-HOME1`，不依賴 WPA。",
        "- `INIT-PRODUCT-UX` 建議波次：刷新／IA／daily API／PregameCard → 首頁／方法頁 → 舊 predict 退場；球員 IA 與 Matchups 可在不同資源上平行。",
        "- 升級前歷史仍封存於 [`archive/TASKS_PRE_WF12.md`](archive/TASKS_PRE_WF12.md)，不得為新格式回寫。", "",
    ])


def _load_events(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


# --live：稽核用。lifecycle 事件依契約直接落 main，分支不得攜帶事件；
# union 工作樹與所有 ai/*（含 origin/ai/*）分支頂端的 event log 後，
# 若結果與 TASKS.md 不一致，代表有事件違規漏留在分支。
_IDLE_STATUSES = {"📥Backlog", "💡需求"}


def _collect_live_events() -> list[dict[str, object]]:
    rel_path = EVENTS_PATH.relative_to(ROOT)
    refs = subprocess.run(
        ["git", "-C", str(ROOT), "for-each-ref", "--format=%(refname:short)",
         "refs/heads/ai/", "refs/remotes/origin/ai/"],
        capture_output=True, text=True, check=True,
    ).stdout.split()
    texts = [EVENTS_PATH.read_text()]
    for ref in refs:
        shown = subprocess.run(
            ["git", "-C", str(ROOT), "show", f"{ref}:{rel_path}"],
            capture_output=True, text=True,
        )
        if shown.returncode == 0:
            texts.append(shown.stdout)
    merged: dict[tuple[str, int], dict[str, object]] = {}
    for text in texts:
        for line in text.splitlines():
            if not line.strip():
                continue
            event = json.loads(line)
            merged.setdefault((str(event["card_id"]), int(event["state_version"])), event)
    return list(merged.values())


def render_live(events: Iterable[dict[str, object]], generated_at: str) -> str:
    """渲染在途卡即時視圖（跨分支 union，不做單一 log 的連續性驗證）。"""
    latest: dict[str, dict[str, object]] = {}
    for event in events:
        card_id = str(event["card_id"])
        current = latest.get(card_id)
        rank = (int(event["state_version"]), str(event["occurred_at"]))
        if current is None or rank > (int(current["state_version"]), str(current["occurred_at"])):
            latest[card_id] = event
    live = [e for e in latest.values() if str(e["delivery_status"]) not in _CLOSED_STATUSES]
    in_flight = sorted(
        (e for e in live if str(e["delivery_status"]) not in _IDLE_STATUSES),
        key=lambda e: str(e["occurred_at"]), reverse=True,
    )
    rows = []
    for e in in_flight:
        branch_worktree = _cell(e["branch_worktree"])
        if branch_worktree != "—":
            branch_worktree = f"`{branch_worktree}`"
        rows.append(
            f"| {_cell(e['card_id'])} | {_cell(e['delivery_status'])} | {_cell(e['iteration'])} | "
            f"{_cell(e['owner'])} | {branch_worktree} | {_cell(e['occurred_at'])} |"
        )
    if not rows:
        rows.append("| —（無在途卡） | | | | | |")
    idle_count = len(live) - len(in_flight)
    return "\n".join([
        "# 在途卡跨分支稽核視圖（--live）", "",
        f"> 產生時間：{generated_at}；來源：main ∪ `ai/*`（含 `origin/ai/*`）分支頂端 event log。",
        "> 事件依契約直接落 main；本視圖與 TASKS.md 不一致＝有事件違規漏留在分支（未 commit 的事件仍不可見）。",
        "", "| 卡ID | 交付狀態 | iteration | owner | 分支／worktree | 最後事件 |",
        "|---|---|---|---|---|---|", *rows, "",
        f"另有 {idle_count} 張 {'／'.join(sorted(_IDLE_STATUSES))} 卡，見 [TASKS.md](TASKS.md)。", "",
    ])


def main() -> None:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--write", action="store_true")
    group.add_argument("--check", action="store_true")
    group.add_argument("--live", action="store_true",
                       help="稽核：彙整 main 與所有 ai/* 分支的 event log，與 TASKS.md 不一致＝有事件漏留在分支")
    args = parser.parse_args()
    if args.live:
        generated_at = datetime.now().astimezone().isoformat(timespec="seconds")
        print(render_live(_collect_live_events(), generated_at))
        return
    rendered = render_ledger(_load_events(EVENTS_PATH))
    if args.write:
        LEDGER_PATH.write_text(rendered)
    elif LEDGER_PATH.read_text() != rendered:
        raise SystemExit("docs/TASKS.md 與 control-plane event log 不一致；請執行 --write")


if __name__ == "__main__":
    main()
