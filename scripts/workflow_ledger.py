# LIFECYCLE: standing · 常設工具——這就是給你跑的；不要刪
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
    if _is_counted_finding(finding):
        current_open.add(finding_id)
    else:
        current_open.discard(finding_id)


def _findings_conflict(
    previous: dict[str, object], current: dict[str, object],
) -> bool:
    return any(previous[field] != current[field] for field in FINDING_CONFLICT_FIELDS)


SCHEMA_REPAIR_FIELDS = {"repaired_event_id", "before", "after", "reason"}


def _validate_schema_repair_event(event: dict, seen_by_id: dict[str, dict]) -> None:
    """`schema-repair` 事件的專屬驗證（DEV-EVENT-SCHEMA-GUARD1 F002 iteration 4）。

    契約要求此型事件承載修復留痕，但 iteration 3 只在文件裡定義、**驗證器完全不認識它**
    ——跨家族查核實測：造一筆缺全部 payload 的 `schema-repair`，完整 replay 仍通過。
    等於「以獨立事件留痕」這條規則沒有任何強制力。

    本函式要求：payload 四欄齊備；`repaired_event_id` 指向**已出現過**的事件；
    `before`／`after` 為 dict；兩者的差異必須通過 `diff_schema_repair()` 白名單；
    且 `after` 必須與 log 中該事件的**現況一致**——否則留痕會與實際修復內容脫節。
    """
    eid = event.get("event_id")
    missing = sorted(SCHEMA_REPAIR_FIELDS - set(event))
    if missing:
        raise ValueError(f"{eid} schema-repair 事件缺少欄位：{', '.join(missing)}")
    target_id = str(event["repaired_event_id"])
    target = seen_by_id.get(target_id)
    if target is None:
        raise ValueError(f"{eid} schema-repair 的 repaired_event_id 不存在：{target_id}")
    before, after = event["before"], event["after"]
    if not isinstance(before, dict) or not isinstance(after, dict):
        raise ValueError(f"{eid} schema-repair 的 before／after 必須為物件")
    if not str(event["reason"]).strip():
        raise ValueError(f"{eid} schema-repair 必須說明無法以追加事件修復的理由")
    violations = diff_schema_repair(before, after)
    if violations:
        raise ValueError(
            f"{eid} schema-repair 的 before→after 逾越白名單：{violations}"
        )
    if after != target:
        raise ValueError(
            f"{eid} schema-repair 的 after 與 log 中 {target_id} 的現況不一致——"
            "留痕必須反映實際修復結果"
        )


def _validate_review_contract(events: list[dict[str, object]]) -> None:
    """Baseline 前事件保持原貌；marker 之後 fail loud 驗證 WF-21 契約。"""
    enabled = False
    counted_attempts: dict[tuple[str, int], set[str]] = {}
    counted_attempt_order: dict[tuple[str, int], list[str]] = {}
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
    seen_by_id: dict[str, dict] = {}
    for event in events:
        seen_by_id[str(event.get("event_id"))] = event
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
        correction_can_resolve_conflict = (
            event_type == "review-correction"
            and bool(pending_finding_conflicts.get(card_id))
        )
        if (
            card_id in pending_checkpoint
            and event_type != "escalation-checkpoint"
            and not correction_can_resolve_conflict
        ):
            raise ValueError(
                f"{event['event_id']} 前必須先為 {card_id} 寫 escalation-checkpoint"
            )
        if event_type == "schema-repair":
            _validate_schema_repair_event(event, seen_by_id)
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
                counted_attempt_order.setdefault(key, []).append(attempt_id)
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
                migrated_occurrences = {
                    occurrence
                    for occurrences in root_cause_findings.get(key, {}).values()
                    for occurrence in occurrences
                    if occurrence[1] == finding_id
                }
                if revokes_count or root_changed:
                    for occurrences in root_cause_findings.get(key, {}).values():
                        occurrences.difference_update(migrated_occurrences)
                if root_changed and not revokes_count:
                    roots = root_cause_findings.setdefault(key, {})
                    roots.setdefault(str(finding["root_cause_id"]), set()).update(
                        migrated_occurrences
                    )
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
                    if target_attempt not in counted_attempt_order.setdefault(key, []):
                        counted_attempt_order[key].append(target_attempt)
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
            pending = pending_checkpoint.get(card_id)
            if pending is not None and pending[0] == epoch:
                if len(attempts) < 3:
                    del pending_checkpoint[card_id]
                else:
                    trigger = pending[2]
                    if trigger not in attempts:
                        trigger = next(
                            attempt
                            for attempt in reversed(counted_attempt_order.get(key, []))
                            if attempt in attempts
                        )
                    pending_checkpoint[card_id] = (epoch, len(attempts), trigger)
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
    events = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    _require_contract_baseline(events)
    return events


# schema-repair 的欄位白名單（DEV-EVENT-SCHEMA-GUARD1 F002，iteration 3 收緊）。
#
# 就地修復的唯一正當理由是「原值不合法導致 log 無法 replay」。因此白名單有**兩道**條件，
# 缺一不可：(1) 欄位在允許清單內；(2) **修復前的值必須是非法的、修復後必須合法**。
# 第 (2) 條是 iteration 2 漏掉的——當時只查欄位名，導致 `attribution: executor → coordinator`
# 與 `status: open → withdrawn` 都回傳合法（跨家族查核實測），等於可用「修格式」之名改寫
# 責任歸屬與 finding 狀態。已合法的值一律不得改寫，要改語意請走 review／review-correction。
REPAIRABLE_EVENT_FIELDS = frozenset({"counts_toward_escalation"})
REPAIRABLE_FINDING_FIELDS = frozenset({"severity", "status", "finding_class", "attribution"})

_LEGAL_FINDING_VALUES: dict[str, frozenset[str]] = {
    "severity": frozenset({"critical", "major", "minor", "info"}),
    "status": frozenset({"open", "resolved", "withdrawn"}),
    "finding_class": frozenset({
        "implementation", "authoritative-artifact", "governance", "coordination", "environment",
    }),
    "attribution": frozenset({"executor", "planner", "coordinator", "reviewer", "external"}),
}


def _repair_is_legalising(
    field: str, before: object, after: object, event: dict | None = None
) -> bool:
    """修復是否為「非法 → 合法」。已合法的值改成另一個合法值不算修復，算改寫。

    `counts_toward_escalation` 是**推導值**而非自由欄位：它的「合法」定義是「等於由結構化
    findings 推導出來的值」，不是「是個布林」。故此處以 `_counted_review()` 重算——
    2026-08-02 的 `REVIEW-007` 正是 `True` 與推導結果不符而必須修為 `False`，
    若僅以型別判斷會把那次正當修復誤判為改寫。
    """
    if field == "counts_toward_escalation":
        if event is None:
            return False
        try:
            derived = _counted_review(event)
        except (KeyError, TypeError):
            return False
        return before != derived and after == derived
    legal = _LEGAL_FINDING_VALUES.get(field)
    if legal is None:
        return False
    return before not in legal and after in legal


def diff_schema_repair(before: dict, after: dict) -> list[str]:
    """回傳 `before → after` 中**逾越 schema-repair 白名單**的欄位路徑；空 list 代表合法。

    供 CI 與查核者機械驗證一次就地修復，不必靠人工閱讀 commit。
    白名單內但屬「合法值改合法值」者一律視為違規並標 `（已合法值不得改寫）`。
    """
    violations: list[str] = []
    for key in set(before) | set(after):
        if key == "findings":
            continue
        if before.get(key) == after.get(key):
            continue
        if key not in REPAIRABLE_EVENT_FIELDS:
            violations.append(key)
        elif not _repair_is_legalising(key, before.get(key), after.get(key), after):
            violations.append(f"{key}（已合法值不得改寫）")
    fb = {str(x.get("finding_id")): x for x in before.get("findings", [])}
    fa = {str(x.get("finding_id")): x for x in after.get("findings", [])}
    for fid in set(fb) | set(fa):
        if fid not in fb or fid not in fa:
            violations.append(f"findings[{fid}]（不得新增或移除 finding）")
            continue
        for key in set(fb[fid]) | set(fa[fid]):
            if fb[fid].get(key) == fa[fid].get(key):
                continue
            path = f"findings[{fid}].{key}"
            if key not in REPAIRABLE_FINDING_FIELDS:
                violations.append(path)
            elif not _repair_is_legalising(key, fb[fid].get(key), fa[fid].get(key)):
                violations.append(f"{path}（已合法值不得改寫）")
    return sorted(violations)


def _require_contract_baseline(events: list[dict[str, object]]) -> None:
    """真實 event log 必須恰有一筆 contract-baseline marker（DEV-EVENT-SCHEMA-GUARD1 F001）。

    `_validate_review_contract` 的所有 schema 驗證都以 marker **之後**為範圍：marker 不在，
    每一筆 review 都會被當成 baseline 前的舊格式而整批跳過，**整條守衛遂可被單一刪除動作
    完全繞過**（查核實測：刪掉該行後 35 項測試全綠）。

    刻意放在 `_load_events` 而非 `_validate_review_contract`：這是**真實檔案**的不變量，
    不是任意事件列表的性質——`render_ledger` 須維持能接受合成 fixture 的純函式語意，
    否則本檔既有的 render 測試會被迫全部塞進一個與其主題無關的 marker。
    """
    markers = [e for e in events if e.get("contract_baseline") == REVIEW_CONTRACT]
    if len(markers) != 1:
        raise ValueError(
            f"event log 必須且只能有一筆 contract_baseline={REVIEW_CONTRACT} 的事件"
            f"（實際 {len(markers)} 筆）；缺席會使全部 review 跳過 schema 驗證"
        )


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


#: `docs/TASKS.md` 於此 commit 被封存為唯讀（2026-08-04 cutover 的終筆）。
#: 橫幅是手工加上去的，**`render_ledger()` 不會產生它**——所以 `--write` 會把它刪掉。
_ARCHIVE_MARKER = "已於 2026-08-04 cutover 封存"

_ARCHIVED_MESSAGE = """\
docs/TASKS.md 已於 2026-08-04 cutover 封存唯讀，本腳本已停用。

現行任務狀態的唯一事實來源是 GitHub Issues ＋ user Project #4；
狀態寫入一律經 ai-workflow 的 `wfcli`（見 docs/AI_RUNBOOK.md §7.1）。

  gh project item-list 4 --owner ruan6047

為什麼要擋：本腳本的 `render_ledger()` 不產生封存橫幅（該橫幅是 e202d48
手工加上去的），因此 `--write` 會把它刪除，並還原「本表即當前狀態」與整張
活卡表——而重建來源 docs/control-plane/events.jsonl 同樣已封存，產出的是
一份過期投影卻標著「當前狀態」。且 `--check` 因橫幅永遠不匹配而必定失敗，
其失敗訊息又指向 `--write`，形成一條把讀者導向破壞性指令的路徑。

需求方 2026-08-15 裁定停用（DEV-SCRIPT-INVENTORY1 #141）。歷史行為在 git
歷史裡仍可讀取。
"""


def _refuse_if_archived() -> None:
    """封存後拒絕執行——見 `_ARCHIVED_MESSAGE`。

    **偵測而非硬編日期**：讀 `docs/TASKS.md` 找封存標記，找不到才放行。
    若日後該檔被解封（橫幅移除），本守衛自動失效而不需改碼；反之橫幅還在
    就一定擋得住，不依賴任何人記得更新常數。
    """
    try:
        text = LEDGER_PATH.read_text(encoding="utf-8")
    except OSError:
        return
    if _ARCHIVE_MARKER in text:
        raise SystemExit(_ARCHIVED_MESSAGE)


def main() -> None:
    _refuse_if_archived()
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
