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
REVIEW_CONTRACT = "review-escalation-v1"
REVIEW_RESULTS = {"APPROVE", "REQUEST_CHANGES"}
FINDING_FIELDS = {
    "finding_id", "severity", "blocking", "accepted", "status", "finding_class",
    "attribution", "root_cause_id", "evidence", "disposition",
}
COUNTED_FINDING_CLASSES = {"implementation", "authoritative-artifact"}
FINDING_CONFLICT_FIELDS = {
    "severity", "blocking", "accepted", "status", "finding_class", "attribution",
    "root_cause_id",
}


def _require_fields(event: dict[str, object], fields: set[str]) -> None:
    missing = fields - event.keys()
    if missing:
        raise ValueError(
            f"{event.get('event_id', '?')} 事件缺少欄位：{', '.join(sorted(missing))}"
        )


def _is_counted_finding(finding: dict[str, object]) -> bool:
    return (
        finding["accepted"] is True
        and finding["status"] == "open"
        and finding["blocking"] is True
        and finding["finding_class"] in COUNTED_FINDING_CLASSES
        and finding["attribution"] == "executor"
    )


def _counted_review(event: dict[str, object]) -> bool:
    if event["review_result"] != "REQUEST_CHANGES":
        return False
    return any(_is_counted_finding(finding) for finding in event["findings"])


def _validate_finding(event_id: object, finding: object) -> dict[str, object]:
    if not isinstance(finding, dict):
        raise ValueError(f"{event_id} finding 必須為物件")
    _require_fields(finding, FINDING_FIELDS)
    if finding["severity"] not in {"critical", "major", "minor", "info"}:
        raise ValueError(f"{event_id} finding severity 不合法")
    if finding["status"] not in {"open", "resolved", "withdrawn"}:
        raise ValueError(f"{event_id} finding status 不合法")
    if finding["finding_class"] not in {
        "implementation", "authoritative-artifact", "governance", "coordination",
        "environment",
    }:
        raise ValueError(f"{event_id} finding_class 不合法")
    if finding["attribution"] not in {
        "executor", "planner", "coordinator", "reviewer", "external",
    }:
        raise ValueError(f"{event_id} finding attribution 不合法")
    if finding["root_cause_id"] == "unknown":
        raise ValueError(
            f"{event_id} unknown root_cause_id 必須加 finding-specific 識別子"
        )
    if not isinstance(finding["blocking"], bool) or not isinstance(finding["accepted"], bool):
        raise ValueError(f"{event_id} finding blocking／accepted 必須為布林值")
    return finding


def _validate_review_event(event: dict[str, object]) -> None:
    _require_fields(event, {
        "attempt_id", "escalation_epoch", "preflight_passed", "review_result",
        "findings", "counts_toward_escalation",
    })
    if event["preflight_passed"] is not True:
        raise ValueError(f"{event['event_id']} review 必須 preflight_passed=true")
    if event["review_result"] not in REVIEW_RESULTS:
        raise ValueError(f"{event['event_id']} review_result 必須為 APPROVE 或 REQUEST_CHANGES")
    if type(event["escalation_epoch"]) is not int or event["escalation_epoch"] < 0:
        raise ValueError(f"{event['event_id']} escalation_epoch 必須為非負整數")
    expected_attempt = (
        f"{event['card_id']}-e{event['escalation_epoch']}-{event['source_sha']}"
    )
    if event["attempt_id"] != expected_attempt:
        raise ValueError(f"{event['event_id']} attempt_id 與 card／epoch／source_sha 不一致")
    if not isinstance(event["source_sha"], str) or len(event["source_sha"]) != 40:
        raise ValueError(f"{event['event_id']} source_sha 必須為完整 40 字元")
    if not isinstance(event["findings"], list):
        raise ValueError(f"{event['event_id']} findings 必須為陣列")
    finding_ids: set[str] = set()
    for finding in event["findings"]:
        finding = _validate_finding(event["event_id"], finding)
        finding_id = str(finding["finding_id"])
        if finding_id in finding_ids:
            raise ValueError(f"{event['event_id']} finding_id 重複：{finding_id}")
        finding_ids.add(finding_id)
    if event["review_result"] == "APPROVE" and any(
        finding["accepted"] is True and finding["blocking"] is True
        and finding["status"] == "open" for finding in event["findings"]
    ):
        raise ValueError(f"{event['event_id']} APPROVE 不得含未閉合 blocking finding")
    derived = _counted_review(event)
    if event["counts_toward_escalation"] is not derived:
        raise ValueError(
            f"{event['event_id']} counts_toward_escalation 必須由結構化 findings 推導為 {derived}"
        )


def _apply_finding_state(
    finding: dict[str, object], current_open: set[str],
) -> None:
    finding_id = str(finding["finding_id"])
    if finding["status"] in {"resolved", "withdrawn"}:
        current_open.discard(finding_id)
    elif (
        finding["accepted"] is True
        and finding["blocking"] is True
        and finding["finding_class"] in COUNTED_FINDING_CLASSES
        and finding["attribution"] == "executor"
    ):
        current_open.add(finding_id)


def _findings_conflict(
    previous: dict[str, object], current: dict[str, object],
) -> bool:
    return any(previous[field] != current[field] for field in FINDING_CONFLICT_FIELDS)


def _validate_review_contract(events: list[dict[str, object]]) -> None:
    """Baseline 前事件保持原貌；marker 之後 fail loud 驗證 WF-21 契約。"""
    enabled = False
    counted_attempts: dict[tuple[str, int], set[str]] = {}
    open_findings: dict[tuple[str, int], set[str]] = {}
    root_cause_findings: dict[
        tuple[str, int], dict[str, set[tuple[str, str]]]
    ] = {}
    unresolved_carry: dict[tuple[str, int], set[str]] = {}
    pending_checkpoint: dict[str, tuple[int, int, str]] = {}
    pending_finding_conflicts: dict[str, set[tuple[int, str, str]]] = {}
    current_epochs: dict[str, int] = {}
    known_attempts: dict[tuple[str, int], set[str]] = {}
    count_eligible_attempts: dict[tuple[str, int], set[str]] = {}
    counted_finding_ids: dict[tuple[str, int, str], set[str]] = {}
    attempt_previous_open: dict[tuple[str, int, str], set[str]] = {}
    attempt_findings: dict[tuple[str, int, str], dict[str, dict[str, object]]] = {}
    for event in events:
        if event.get("contract_baseline") == REVIEW_CONTRACT:
            if enabled:
                raise ValueError(
                    f"{event['event_id']} contract_baseline={REVIEW_CONTRACT} 只能出現一次"
                )
            if event.get("type") != "contract-baseline":
                raise ValueError(
                    f"{event['event_id']} contract_baseline 只能由 contract-baseline 事件啟用"
                )
            enabled = True
            continue
        if not enabled:
            continue
        event_type = event.get("type")
        card_id = str(event["card_id"])
        if (
            pending_finding_conflicts.get(card_id)
            and event_type != "review-correction"
        ):
            raise ValueError(
                f"{event['event_id']} 前必須先以 review-correction 裁決 {card_id} "
                "同一 attempt 的 finding 衝突"
            )
        if card_id in pending_checkpoint and event_type != "escalation-checkpoint":
            raise ValueError(
                f"{event['event_id']} 前必須先為 {card_id} 寫 escalation-checkpoint"
            )
        if event_type == "review":
            _validate_review_event(event)
            epoch = int(event["escalation_epoch"])
            expected_epoch = current_epochs.setdefault(card_id, 0)
            if epoch != expected_epoch:
                raise ValueError(
                    f"{event['event_id']} escalation_epoch={epoch} 未經需求方授權；"
                    f"目前 epoch={expected_epoch}"
                )
            key = (card_id, epoch)
            attempt_id = str(event["attempt_id"])
            attempt_key = (card_id, epoch, attempt_id)
            known_attempts.setdefault(key, set()).add(attempt_id)
            if event["counts_toward_escalation"] is True:
                count_eligible_attempts.setdefault(key, set()).add(attempt_id)
            per_attempt = attempt_findings.setdefault(attempt_key, {})
            conflicting_ids: set[str] = set()
            for finding in event["findings"]:
                finding_id = str(finding["finding_id"])
                previous = per_attempt.get(finding_id)
                if previous is not None and _findings_conflict(previous, finding):
                    pending_finding_conflicts.setdefault(card_id, set()).add(
                        (epoch, attempt_id, finding_id)
                    )
                    conflicting_ids.add(finding_id)
                    continue
                per_attempt.setdefault(finding_id, finding)

            attempts = counted_attempts.setdefault(key, set())
            previous_open = set(open_findings.setdefault(key, set()))
            attempt_previous_open.setdefault(attempt_key, previous_open)
            for finding in event["findings"]:
                finding_id = str(finding["finding_id"])
                if finding_id in conflicting_ids:
                    continue
                _apply_finding_state(finding, open_findings[key])
                if event["counts_toward_escalation"] is True and _is_counted_finding(finding):
                    counted_finding_ids.setdefault(attempt_key, set()).add(finding_id)
                    roots = root_cause_findings.setdefault(key, {})
                    roots.setdefault(str(finding["root_cause_id"]), set()).add(
                        (attempt_id, finding_id)
                    )
            is_new_counted_attempt = (
                bool(counted_finding_ids.get(attempt_key)) and attempt_id not in attempts
            )
            if is_new_counted_attempt:
                attempts.add(attempt_id)
                unresolved_carry.setdefault(key, set()).update(
                    previous_open & open_findings[key]
                )
                if len(attempts) >= 3:
                    pending_checkpoint[card_id] = (
                        epoch, len(attempts), attempt_id,
                    )
        elif event_type == "escalation-epoch-change":
            _require_fields(event, {
                "from_escalation_epoch", "to_escalation_epoch", "epoch_change_reason",
                "requester_approved",
            })
            current = current_epochs.setdefault(card_id, 0)
            if (
                event["requester_approved"] is not True
                or type(event["from_escalation_epoch"]) is not int
                or type(event["to_escalation_epoch"]) is not int
                or event["epoch_change_reason"] not in {"replan", "change-executor"}
                or event["from_escalation_epoch"] != current
                or event["to_escalation_epoch"] != current + 1
            ):
                raise ValueError(
                    f"{event['event_id']} escalation epoch 切換必須由需求方授權、"
                    "逐一遞增，且理由為 replan 或 change-executor"
                )
            current_epochs[card_id] = current + 1
        elif event_type == "review-correction":
            _require_fields(event, {
                "escalation_epoch", "target_attempt_id", "finding_updates",
            })
            epoch = event["escalation_epoch"]
            if type(epoch) is not int or epoch != current_epochs.setdefault(card_id, 0):
                raise ValueError(f"{event['event_id']} correction escalation_epoch 不合法")
            key = (card_id, epoch)
            target_attempt = str(event["target_attempt_id"])
            target_key = (card_id, epoch, target_attempt)
            updates = event["finding_updates"]
            if target_attempt not in known_attempts.get(key, set()):
                raise ValueError(f"{event['event_id']} correction target_attempt_id 不存在")
            if not isinstance(updates, list) or not updates:
                raise ValueError(f"{event['event_id']} finding_updates 必須為非空陣列")
            target_findings = attempt_findings[target_key]
            update_ids: set[str] = set()
            for finding in updates:
                finding = _validate_finding(event["event_id"], finding)
                finding_id = str(finding["finding_id"])
                if finding_id in update_ids:
                    raise ValueError(f"{event['event_id']} finding_id 重複：{finding_id}")
                update_ids.add(finding_id)
                if finding_id not in target_findings:
                    raise ValueError(
                        f"{event['event_id']} correction finding_id 不存在：{finding_id}"
                    )
                previous_finding = target_findings[finding_id]
                target_findings[finding_id] = finding
                _apply_finding_state(finding, open_findings.setdefault(key, set()))
                pending_finding_conflicts.setdefault(card_id, set()).discard(
                    (epoch, target_attempt, finding_id)
                )
                revokes_count = (
                    finding["status"] == "withdrawn"
                    or finding["accepted"] is False
                    or (finding["status"] == "open" and not _is_counted_finding(finding))
                )
                root_changed = finding["root_cause_id"] != previous_finding["root_cause_id"]
                if revokes_count or root_changed:
                    for occurrences in root_cause_findings.get(key, {}).values():
                        occurrences.difference_update({
                            occurrence
                            for occurrence in occurrences
                            if occurrence[1] == finding_id
                        })
                if revokes_count:
                    counted_finding_ids.setdefault(target_key, set()).discard(finding_id)
                    unresolved_carry.setdefault(key, set()).discard(finding_id)
                elif (
                    target_attempt in count_eligible_attempts.get(key, set())
                    and _is_counted_finding(finding)
                ):
                    counted_finding_ids.setdefault(target_key, set()).add(finding_id)
                    roots = root_cause_findings.setdefault(key, {})
                    roots.setdefault(str(finding["root_cause_id"]), set()).add(
                        (target_attempt, finding_id)
                    )
            attempts = counted_attempts.setdefault(key, set())
            was_counted = target_attempt in attempts
            if counted_finding_ids.get(target_key):
                attempts.add(target_attempt)
                if not was_counted:
                    unresolved_carry.setdefault(key, set()).update(
                        attempt_previous_open.get(target_key, set())
                        & open_findings.setdefault(key, set())
                    )
                    if len(attempts) >= 3:
                        pending_checkpoint[card_id] = (
                            epoch, len(attempts), target_attempt,
                        )
            else:
                attempts.discard(target_attempt)
            if not pending_finding_conflicts.get(card_id):
                pending_finding_conflicts.pop(card_id, None)
        elif event_type == "preflight-failed":
            _require_fields(event, {"preflight_passed", "failure_reasons"})
            if event["preflight_passed"] is not False or not isinstance(
                event["failure_reasons"], list
            ) or not event["failure_reasons"]:
                raise ValueError(
                    f"{event['event_id']} preflight-failed 必須帶 false 與非空 failure_reasons"
                )
        elif event_type == "review-invalid":
            _require_fields(event, {"preflight_passed", "invalid_reasons"})
            if (
                not isinstance(event["preflight_passed"], bool)
                or not isinstance(event["invalid_reasons"], list)
                or not event["invalid_reasons"]
            ):
                raise ValueError(
                    f"{event['event_id']} review-invalid 必須帶布林 preflight_passed "
                    "與非空 invalid_reasons"
                )
        elif event_type == "escalation-checkpoint":
            _require_fields(event, {
                "escalation_epoch", "trigger_attempt_id", "unique_attempt_count",
                "checkpoint_decision", "checkpoint_rationale",
            })
            if (
                type(event["unique_attempt_count"]) is not int
                or event["unique_attempt_count"] < 3
            ):
                raise ValueError(f"{event['event_id']} escalation checkpoint 至少需三個 attempt")
            if event["checkpoint_decision"] not in {
                "continue", "replan", "change-executor", "escalate",
            }:
                raise ValueError(f"{event['event_id']} checkpoint_decision 不合法")
            expected = pending_checkpoint.get(card_id)
            if expected is None:
                raise ValueError(f"{event['event_id']} 沒有待處理的第三次以後 attempt")
            expected_epoch, expected_count, trigger_attempt = expected
            if (
                event["escalation_epoch"] != expected_epoch
                or
                event["unique_attempt_count"] != expected_count
                or event["trigger_attempt_id"] != trigger_attempt
            ):
                raise ValueError(
                    f"{event['event_id']} checkpoint 必須對應 {expected_count} 個唯一 attempt"
                )
            key = (card_id, expected_epoch)
            repeated_root = any(
                len({attempt_id for attempt_id, _finding_id in occurrences}) >= 3
                for occurrences in root_cause_findings.get(key, {}).values()
            )
            must_escalate = repeated_root or bool(unresolved_carry.get(key))
            if must_escalate and event["checkpoint_decision"] != "escalate":
                raise ValueError(
                    f"{event['event_id']} 存在三次重複根因或未閉合 finding，"
                    "checkpoint_decision 必須為 escalate"
                )
            del pending_checkpoint[card_id]
    if pending_finding_conflicts:
        cards = ", ".join(sorted(pending_finding_conflicts))
        raise ValueError(f"同一 attempt 的 finding 衝突缺 review-correction：{cards}")
    if pending_checkpoint:
        cards = ", ".join(sorted(pending_checkpoint))
        raise ValueError(f"第三次以後可計數 attempt 缺 escalation-checkpoint：{cards}")


def _latest_events(events: Iterable[dict[str, object]]) -> list[dict[str, object]]:
    events = list(events)
    _validate_review_contract(events)
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
        "- `INIT-GAME-RECAP` 的資料紅線主鏈：`GAME-RECAP-DATA1 ✅ → GAME-RECAP-PA1 ✅ → GAME-RECAP-WP-VAL1 ✅（全 scope unsupported）→ GAME-RECAP-WP-CAL1 🏁（事後校準 No-Go）→ GAME-RECAP-WP-STRENGTH1 🏁（No-Go：八項凍結賽前特徵時間外無增量資訊，p0 相對主場常數僅 −0.0009 且兩季為負；merge 198ad87）→ GAME-RECAP-WP-API1 🏁✅（2026-07-27 需求方定位改寫 canonical→參考資訊＋揭露〔T3〕解阻塞，`/recap-wp` 已上線並帶 `wp_reliability` 揭露；統計改善鏈封存為升級路徑，未來 scope 通過原 v2 門檻只翻升 reliability、consumer 無 breaking change）→ UX-GAME-RECAP1 → UX-GAME-PA1（WP 契約阻塞已解除）`；首頁 v1 另走 `API-DAILY-SUMMARY1 + UX-OUTCOME-HOME → UX-GAME-HOME1`，不依賴 WPA。",
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
