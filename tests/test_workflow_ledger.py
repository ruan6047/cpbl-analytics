import importlib.util
from pathlib import Path

SCRIPT_PATH = Path(__file__).parents[1] / "scripts" / "workflow_ledger.py"
SPEC = importlib.util.spec_from_file_location("workflow_ledger", SCRIPT_PATH)
assert SPEC and SPEC.loader
workflow_ledger = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(workflow_ledger)


FULL_SHA = "a" * 40


def _contract_event(event_id: str, event_type: str, state_version: int) -> dict:
    return {
        "event_id": event_id,
        "card_id": "CARD-WF21",
        "type": event_type,
        "actor": "ruan6047",
        "occurred_at": f"2026-07-30T12:00:0{state_version}+08:00",
        "state_version": state_version,
        "iteration": 0,
        "source_sha": FULL_SHA,
        "evidence": "test",
        "initiative": "—",
        "tier": "T4",
        "feature": "WF-21 contract test",
        "owner": "reviewer",
        "branch_worktree": "ai/test/CARD-WF21 @ wt",
        "delivery_status": "🔍待查核",
        "deployment_status": "—不適用",
    }


def _finding(**overrides: object) -> dict:
    finding = {
        "finding_id": "F-001",
        "severity": "major",
        "blocking": True,
        "accepted": True,
        "status": "open",
        "finding_class": "implementation",
        "attribution": "executor",
        "root_cause_id": "missing-boundary-check",
        "evidence": "reproduced",
        "disposition": "fix the boundary",
    }
    finding.update(overrides)
    return finding


def _review_event(state_version: int = 2, **overrides: object) -> dict:
    event = _contract_event("REVIEW-002", "review", state_version)
    event.update({
        "attempt_id": f"CARD-WF21-e0-{FULL_SHA}",
        "escalation_epoch": 0,
        "preflight_passed": True,
        "review_result": "REQUEST_CHANGES",
        "findings": [_finding()],
        "counts_toward_escalation": True,
        "delivery_status": "↩退回",
    })
    event.update(overrides)
    return event


def test_review_contract_keeps_pre_baseline_history_unchanged() -> None:
    legacy = _contract_event("LEGACY-REVIEW-001", "review", 1)
    legacy["review_result"] = "REJECT（free text legacy）"

    workflow_ledger.render_ledger([legacy])


def test_review_contract_rejects_free_text_review_after_baseline() -> None:
    baseline = _contract_event("BASELINE-001", "contract-baseline", 1)
    baseline["contract_baseline"] = workflow_ledger.REVIEW_CONTRACT
    review = _review_event(review_result="REJECT")

    try:
        workflow_ledger.render_ledger([baseline, review])
    except ValueError as error:
        assert "APPROVE 或 REQUEST_CHANGES" in str(error)
    else:
        raise AssertionError("WF-21 baseline 後不得接受自由文字 REJECT")


def test_review_contract_rejects_duplicate_baseline_marker() -> None:
    baseline = _contract_event("BASELINE-001", "contract-baseline", 1)
    baseline["contract_baseline"] = workflow_ledger.REVIEW_CONTRACT
    bypass = _review_event(review_result="REJECT")
    bypass["contract_baseline"] = workflow_ledger.REVIEW_CONTRACT

    try:
        workflow_ledger.render_ledger([baseline, bypass])
    except ValueError as error:
        assert "contract_baseline" in str(error)
    else:
        raise AssertionError("baseline marker 只能出現一次，不得略過後續 review 驗證")


def test_review_contract_rejects_baseline_marker_on_review_event() -> None:
    bypass = _review_event(state_version=1, review_result="REJECT")
    bypass["contract_baseline"] = workflow_ledger.REVIEW_CONTRACT

    try:
        workflow_ledger.render_ledger([bypass])
    except ValueError as error:
        assert "contract-baseline 事件" in str(error)
    else:
        raise AssertionError("baseline marker 不得附在 review 事件上略過驗證")


def test_review_contract_derives_count_from_executor_finding() -> None:
    baseline = _contract_event("BASELINE-001", "contract-baseline", 1)
    baseline["contract_baseline"] = workflow_ledger.REVIEW_CONTRACT

    rendered = workflow_ledger.render_ledger([baseline, _review_event()])

    assert "CARD-WF21" in rendered


def test_review_contract_does_not_count_governance_finding() -> None:
    baseline = _contract_event("BASELINE-001", "contract-baseline", 1)
    baseline["contract_baseline"] = workflow_ledger.REVIEW_CONTRACT
    review = _review_event(
        findings=[_finding(finding_class="governance", attribution="coordinator")],
        counts_toward_escalation=False,
    )

    workflow_ledger.render_ledger([baseline, review])


def test_review_contract_rejects_manually_declared_count() -> None:
    baseline = _contract_event("BASELINE-001", "contract-baseline", 1)
    baseline["contract_baseline"] = workflow_ledger.REVIEW_CONTRACT
    review = _review_event(counts_toward_escalation=False)

    try:
        workflow_ledger.render_ledger([baseline, review])
    except ValueError as error:
        assert "推導為 True" in str(error)
    else:
        raise AssertionError("counts_toward_escalation 必須由 finding 推導")


def test_review_contract_deduplicates_same_attempt_before_checkpoint() -> None:
    baseline = _contract_event("BASELINE-001", "contract-baseline", 1)
    baseline["contract_baseline"] = workflow_ledger.REVIEW_CONTRACT
    same_attempt = _review_event(state_version=3)
    same_attempt["event_id"] = "REVIEW-003"
    second_sha = "b" * 40
    second = _review_event(
        state_version=4,
        source_sha=second_sha,
        attempt_id=f"CARD-WF21-e0-{second_sha}",
        findings=[
            _finding(status="resolved"),
            _finding(
                finding_id="F-002", root_cause_id="missing-schema-check",
                disposition="fix schema check",
            ),
        ],
    )
    third_sha = "c" * 40
    third = _review_event(
        state_version=5,
        source_sha=third_sha,
        attempt_id=f"CARD-WF21-e0-{third_sha}",
        findings=[
            _finding(
                finding_id="F-002", root_cause_id="missing-schema-check",
                status="resolved", disposition="fixed",
            ),
            _finding(
                finding_id="F-003", root_cause_id="missing-epoch-check",
                disposition="fix epoch check",
            ),
        ],
    )
    checkpoint = _contract_event("CHECKPOINT-006", "escalation-checkpoint", 6)
    checkpoint.update({
        "escalation_epoch": 0,
        "trigger_attempt_id": third["attempt_id"],
        "unique_attempt_count": 3,
        "checkpoint_decision": "continue",
        "checkpoint_rationale": "three distinct and converging findings",
    })

    workflow_ledger.render_ledger([
        baseline, _review_event(), same_attempt, second, third, checkpoint,
    ])


def test_review_contract_requires_checkpoint_after_third_unique_attempt() -> None:
    baseline = _contract_event("BASELINE-001", "contract-baseline", 1)
    baseline["contract_baseline"] = workflow_ledger.REVIEW_CONTRACT
    reviews = [_review_event()]
    for state_version, sha in ((3, "b" * 40), (4, "c" * 40)):
        reviews.append(_review_event(
            state_version=state_version,
            source_sha=sha,
            attempt_id=f"CARD-WF21-e0-{sha}",
        ))

    try:
        workflow_ledger.render_ledger([baseline, *reviews])
    except ValueError as error:
        assert "缺 escalation-checkpoint" in str(error)
    else:
        raise AssertionError("第三個可計數 attempt 必須先進 checkpoint")


def test_review_contract_forces_escalation_for_repeated_root_cause() -> None:
    baseline = _contract_event("BASELINE-001", "contract-baseline", 1)
    baseline["contract_baseline"] = workflow_ledger.REVIEW_CONTRACT
    reviews = [_review_event()]
    for state_version, sha in ((3, "b" * 40), (4, "c" * 40)):
        reviews.append(_review_event(
            state_version=state_version,
            source_sha=sha,
            attempt_id=f"CARD-WF21-e0-{sha}",
        ))
    checkpoint = _contract_event("CHECKPOINT-005", "escalation-checkpoint", 5)
    checkpoint.update({
        "escalation_epoch": 0,
        "trigger_attempt_id": reviews[-1]["attempt_id"],
        "unique_attempt_count": 3,
        "checkpoint_decision": "continue",
        "checkpoint_rationale": "incorrectly ignore repeated cause",
    })

    try:
        workflow_ledger.render_ledger([baseline, *reviews, checkpoint])
    except ValueError as error:
        assert "checkpoint_decision 必須為 escalate" in str(error)
    else:
        raise AssertionError("三次重複根因必須 fail loud 升級")


def test_review_contract_forces_escalation_for_unresolved_carry() -> None:
    baseline = _contract_event("BASELINE-001", "contract-baseline", 1)
    baseline["contract_baseline"] = workflow_ledger.REVIEW_CONTRACT
    first = _review_event()
    second_sha = "b" * 40
    second = _review_event(
        state_version=3,
        source_sha=second_sha,
        attempt_id=f"CARD-WF21-e0-{second_sha}",
        findings=[
            _finding(),
            _finding(finding_id="F-002", root_cause_id="root-2"),
        ],
    )
    third_sha = "c" * 40
    third = _review_event(
        state_version=4,
        source_sha=third_sha,
        attempt_id=f"CARD-WF21-e0-{third_sha}",
        findings=[
            _finding(status="resolved", disposition="fixed late"),
            _finding(finding_id="F-002", root_cause_id="root-2", status="resolved"),
            _finding(finding_id="F-003", root_cause_id="root-3"),
        ],
    )
    checkpoint = _contract_event("CHECKPOINT-005", "escalation-checkpoint", 5)
    checkpoint.update({
        "escalation_epoch": 0,
        "trigger_attempt_id": third["attempt_id"],
        "unique_attempt_count": 3,
        "checkpoint_decision": "continue",
        "checkpoint_rationale": "incorrectly ignores carry from first to second attempt",
    })

    try:
        workflow_ledger.render_ledger([baseline, first, second, third, checkpoint])
    except ValueError as error:
        assert "checkpoint_decision 必須為 escalate" in str(error)
    else:
        raise AssertionError("前輪 finding 延續到下一 attempt 必須 fail loud 升級")


def test_review_contract_rejects_unauthorized_epoch_jump() -> None:
    baseline = _contract_event("BASELINE-001", "contract-baseline", 1)
    baseline["contract_baseline"] = workflow_ledger.REVIEW_CONTRACT
    second_sha = "b" * 40
    second = _review_event(
        state_version=3,
        source_sha=second_sha,
        attempt_id=f"CARD-WF21-e0-{second_sha}",
        findings=[_finding(finding_id="F-002", root_cause_id="root-2")],
    )
    third_sha = "c" * 40
    jumped = _review_event(
        state_version=4,
        source_sha=third_sha,
        escalation_epoch=1,
        attempt_id=f"CARD-WF21-e1-{third_sha}",
        findings=[_finding(finding_id="F-003", root_cause_id="root-3")],
    )

    try:
        workflow_ledger.render_ledger([baseline, _review_event(), second, jumped])
    except ValueError as error:
        assert "escalation_epoch" in str(error)
    else:
        raise AssertionError("未經需求方授權不得切換 escalation epoch")


def test_review_contract_rejects_boolean_epoch() -> None:
    baseline = _contract_event("BASELINE-001", "contract-baseline", 1)
    baseline["contract_baseline"] = workflow_ledger.REVIEW_CONTRACT
    review = _review_event(
        escalation_epoch=False,
        attempt_id=f"CARD-WF21-eFalse-{FULL_SHA}",
    )

    try:
        workflow_ledger.render_ledger([baseline, review])
    except ValueError as error:
        assert "非負整數" in str(error)
    else:
        raise AssertionError("Python bool 不得冒充 escalation epoch 整數")


def test_review_contract_accepts_requester_authorized_next_epoch() -> None:
    baseline = _contract_event("BASELINE-001", "contract-baseline", 1)
    baseline["contract_baseline"] = workflow_ledger.REVIEW_CONTRACT
    epoch_change = _contract_event("EPOCH-002", "escalation-epoch-change", 2)
    epoch_change.update({
        "from_escalation_epoch": 0,
        "to_escalation_epoch": 1,
        "epoch_change_reason": "replan",
        "requester_approved": True,
    })
    source_sha = "b" * 40
    review = _review_event(
        state_version=3,
        source_sha=source_sha,
        escalation_epoch=1,
        attempt_id=f"CARD-WF21-e1-{source_sha}",
    )

    workflow_ledger.render_ledger([baseline, epoch_change, review])


def test_review_contract_credits_resolution_in_non_counted_review() -> None:
    baseline = _contract_event("BASELINE-001", "contract-baseline", 1)
    baseline["contract_baseline"] = workflow_ledger.REVIEW_CONTRACT
    first = _review_event()
    second_sha = "b" * 40
    second = _review_event(
        state_version=3,
        source_sha=second_sha,
        attempt_id=f"CARD-WF21-e0-{second_sha}",
        findings=[
            _finding(status="resolved", disposition="fixed"),
            _finding(finding_id="F-002", root_cause_id="root-2"),
        ],
    )
    resolution_sha = "d" * 40
    resolution = _review_event(
        state_version=4,
        source_sha=resolution_sha,
        attempt_id=f"CARD-WF21-e0-{resolution_sha}",
        review_result="APPROVE",
        findings=[_finding(
            finding_id="F-002", root_cause_id="root-2", status="resolved",
            disposition="verified fixed",
        )],
        counts_toward_escalation=False,
        delivery_status="🔍待查核",
    )
    third_sha = "c" * 40
    third = _review_event(
        state_version=5,
        source_sha=third_sha,
        attempt_id=f"CARD-WF21-e0-{third_sha}",
        findings=[_finding(finding_id="F-003", root_cause_id="root-3")],
    )
    checkpoint = _contract_event("CHECKPOINT-006", "escalation-checkpoint", 6)
    checkpoint.update({
        "escalation_epoch": 0,
        "trigger_attempt_id": third["attempt_id"],
        "unique_attempt_count": 3,
        "checkpoint_decision": "continue",
        "checkpoint_rationale": "all earlier findings are closed and roots converge",
    })

    workflow_ledger.render_ledger([
        baseline, first, second, resolution, third, checkpoint,
    ])


def test_review_contract_credits_resolution_from_correction_event() -> None:
    baseline = _contract_event("BASELINE-001", "contract-baseline", 1)
    baseline["contract_baseline"] = workflow_ledger.REVIEW_CONTRACT
    correction = _contract_event("CORRECTION-003", "review-correction", 3)
    correction.update({
        "escalation_epoch": 0,
        "target_attempt_id": f"CARD-WF21-e0-{FULL_SHA}",
        "finding_updates": [_finding(status="resolved", disposition="withdrawn after evidence")],
    })

    workflow_ledger.render_ledger([baseline, _review_event(), correction])


def test_review_contract_allows_append_only_correction_after_same_attempt_conflict() -> None:
    baseline = _contract_event("BASELINE-001", "contract-baseline", 1)
    baseline["contract_baseline"] = workflow_ledger.REVIEW_CONTRACT
    conflicting = _review_event(
        state_version=3,
        review_result="APPROVE",
        findings=[_finding(status="resolved", disposition="reviewer says fixed")],
        counts_toward_escalation=False,
    )
    conflicting["event_id"] = "REVIEW-003"
    correction = _contract_event("CORRECTION-004", "review-correction", 4)
    correction.update({
        "escalation_epoch": 0,
        "target_attempt_id": f"CARD-WF21-e0-{FULL_SHA}",
        "finding_updates": [_finding(
            status="withdrawn", accepted=False, blocking=False,
            disposition="Coordinator adjudicated the conflict",
        )],
    })

    workflow_ledger.render_ledger([
        baseline, _review_event(), conflicting, correction,
    ])


def test_review_contract_withdrawn_correction_clears_prior_carry() -> None:
    baseline = _contract_event("BASELINE-001", "contract-baseline", 1)
    baseline["contract_baseline"] = workflow_ledger.REVIEW_CONTRACT
    first = _review_event()
    second_sha = "b" * 40
    second = _review_event(
        state_version=3,
        source_sha=second_sha,
        attempt_id=f"CARD-WF21-e0-{second_sha}",
        findings=[
            _finding(),
            _finding(finding_id="F-002", root_cause_id="missing-boundary-check"),
        ],
    )
    correction = _contract_event("CORRECTION-004", "review-correction", 4)
    correction.update({
        "escalation_epoch": 0,
        "target_attempt_id": second["attempt_id"],
        "finding_updates": [_finding(
            status="withdrawn", accepted=False, blocking=False,
            disposition="evidence disproved the accepted finding",
        )],
    })
    third_sha = "c" * 40
    third = _review_event(
        state_version=5,
        source_sha=third_sha,
        attempt_id=f"CARD-WF21-e0-{third_sha}",
        findings=[
            _finding(
                finding_id="F-002", root_cause_id="missing-boundary-check", status="resolved",
                disposition="fixed",
            ),
            _finding(finding_id="F-003", root_cause_id="missing-boundary-check"),
        ],
    )
    checkpoint = _contract_event("CHECKPOINT-006", "escalation-checkpoint", 6)
    checkpoint.update({
        "escalation_epoch": 0,
        "trigger_attempt_id": third["attempt_id"],
        "unique_attempt_count": 3,
        "checkpoint_decision": "continue",
        "checkpoint_rationale": "withdrawn finding no longer contributes carry or root history",
    })

    workflow_ledger.render_ledger([
        baseline, first, second, correction, third, checkpoint,
    ])


def test_review_contract_withdrawn_correction_removes_attempt_from_count() -> None:
    baseline = _contract_event("BASELINE-001", "contract-baseline", 1)
    baseline["contract_baseline"] = workflow_ledger.REVIEW_CONTRACT
    correction = _contract_event("CORRECTION-003", "review-correction", 3)
    correction.update({
        "escalation_epoch": 0,
        "target_attempt_id": f"CARD-WF21-e0-{FULL_SHA}",
        "finding_updates": [_finding(
            status="withdrawn", accepted=False, blocking=False,
            disposition="finding was not valid",
        )],
    })
    reviews = []
    for state_version, sha, finding_id in (
        (4, "b" * 40, "F-002"),
        (5, "c" * 40, "F-003"),
    ):
        reviews.append(_review_event(
            state_version=state_version,
            source_sha=sha,
            attempt_id=f"CARD-WF21-e0-{sha}",
            findings=[_finding(
                finding_id=finding_id,
                root_cause_id=f"root-{finding_id}",
            )],
        ))

    workflow_ledger.render_ledger([
        baseline, _review_event(), correction, *reviews,
    ])


def _assert_open_correction_revocation_allows_continue(**finding_overrides: object) -> None:
    baseline = _contract_event("BASELINE-001", "contract-baseline", 1)
    baseline["contract_baseline"] = workflow_ledger.REVIEW_CONTRACT
    correction = _contract_event("CORRECTION-003", "review-correction", 3)
    correction.update({
        "escalation_epoch": 0,
        "target_attempt_id": f"CARD-WF21-e0-{FULL_SHA}",
        "finding_updates": [_finding(
            status="open", disposition="finding no longer counts", **finding_overrides,
        )],
    })
    reviews = []
    previous_id: str | None = None
    for state_version, sha, finding_id in (
        (4, "b" * 40, "F-002"),
        (5, "c" * 40, "F-003"),
        (6, "d" * 40, "F-004"),
    ):
        findings = []
        if previous_id is not None:
            findings.append(_finding(
                finding_id=previous_id,
                root_cause_id=f"root-{previous_id}",
                status="resolved",
                disposition="fixed",
            ))
        findings.append(_finding(
            finding_id=finding_id,
            root_cause_id=f"root-{finding_id}",
        ))
        reviews.append(_review_event(
            state_version=state_version,
            source_sha=sha,
            attempt_id=f"CARD-WF21-e0-{sha}",
            findings=findings,
        ))
        previous_id = finding_id
    checkpoint = _contract_event("CHECKPOINT-007", "escalation-checkpoint", 7)
    checkpoint.update({
        "escalation_epoch": 0,
        "trigger_attempt_id": reviews[-1]["attempt_id"],
        "unique_attempt_count": 3,
        "checkpoint_decision": "continue",
        "checkpoint_rationale": "revoked open finding does not recreate carry",
    })

    workflow_ledger.render_ledger([
        baseline, _review_event(), correction, *reviews, checkpoint,
    ])


def test_review_contract_accepted_false_open_correction_clears_open_state() -> None:
    _assert_open_correction_revocation_allows_continue(accepted=False)


def test_review_contract_nonblocking_open_correction_clears_open_state() -> None:
    _assert_open_correction_revocation_allows_continue(blocking=False)


def _conflict_checkpoint_events(*, withdraw_conflict: bool) -> list[dict]:
    baseline = _contract_event("BASELINE-001", "contract-baseline", 1)
    baseline["contract_baseline"] = workflow_ledger.REVIEW_CONTRACT
    first = _review_event()
    second_sha = "b" * 40
    second = _review_event(
        state_version=3,
        source_sha=second_sha,
        attempt_id=f"CARD-WF21-e0-{second_sha}",
        findings=[_finding(finding_id="F-002", root_cause_id="root-2")],
    )
    withdraw_second = _contract_event("CORRECTION-004", "review-correction", 4)
    withdraw_second.update({
        "escalation_epoch": 0,
        "target_attempt_id": second["attempt_id"],
        "finding_updates": [_finding(
            finding_id="F-002", root_cause_id="root-2", status="withdrawn",
            accepted=False, blocking=False, disposition="temporarily withdrawn",
        )],
    })
    third_sha = "c" * 40
    third = _review_event(
        state_version=5,
        source_sha=third_sha,
        attempt_id=f"CARD-WF21-e0-{third_sha}",
        findings=[_finding(finding_id="F-003", root_cause_id="root-3")],
    )
    conflict = _review_event(
        state_version=6,
        source_sha=third_sha,
        attempt_id=third["attempt_id"],
        review_result="APPROVE",
        findings=[_finding(
            finding_id="F-003", root_cause_id="root-3", status="resolved",
            disposition="conflicting reviewer result",
        )],
        counts_toward_escalation=False,
    )
    reinstate_second = _contract_event("CORRECTION-007", "review-correction", 7)
    reinstate_second.update({
        "escalation_epoch": 0,
        "target_attempt_id": second["attempt_id"],
        "finding_updates": [_finding(
            finding_id="F-002", root_cause_id="root-2",
            disposition="reinstated after evidence",
        )],
    })
    resolve_conflict = _contract_event("CORRECTION-008", "review-correction", 8)
    conflict_resolution = (
        _finding(
            finding_id="F-003", root_cause_id="root-3", status="withdrawn",
            accepted=False, blocking=False,
            disposition="Coordinator withdrew the conflicted finding",
        )
        if withdraw_conflict
        else _finding(
            finding_id="F-003", root_cause_id="root-3",
            disposition="Coordinator adjudicated open",
        )
    )
    resolve_conflict.update({
        "escalation_epoch": 0,
        "target_attempt_id": third["attempt_id"],
        "finding_updates": [conflict_resolution],
    })
    checkpoint = _contract_event("CHECKPOINT-009", "escalation-checkpoint", 9)
    checkpoint.update({
        "escalation_epoch": 0,
        "trigger_attempt_id": second["attempt_id"],
        "unique_attempt_count": 3,
        "checkpoint_decision": "escalate",
        "checkpoint_rationale": "conflict resolved before mandatory checkpoint",
    })

    events = [
        baseline, first, second, withdraw_second, third, conflict,
        reinstate_second, resolve_conflict,
    ]
    if not withdraw_conflict:
        events.append(checkpoint)
    return events


def test_review_contract_allows_conflict_correction_before_pending_checkpoint() -> None:
    workflow_ledger.render_ledger(_conflict_checkpoint_events(withdraw_conflict=False))


def test_review_contract_withdrawn_conflict_clears_pending_checkpoint() -> None:
    workflow_ledger.render_ledger(_conflict_checkpoint_events(withdraw_conflict=True))


def test_review_contract_root_change_migrates_all_finding_occurrences() -> None:
    baseline = _contract_event("BASELINE-001", "contract-baseline", 1)
    baseline["contract_baseline"] = workflow_ledger.REVIEW_CONTRACT
    first = _review_event()
    resolve_one_sha = "d" * 40
    resolve_one = _review_event(
        state_version=3,
        source_sha=resolve_one_sha,
        attempt_id=f"CARD-WF21-e0-{resolve_one_sha}",
        review_result="APPROVE",
        findings=[_finding(status="resolved", disposition="closed before next attempt")],
        counts_toward_escalation=False,
    )
    second_sha = "b" * 40
    second = _review_event(
        state_version=4,
        source_sha=second_sha,
        attempt_id=f"CARD-WF21-e0-{second_sha}",
    )
    resolve_two_sha = "e" * 40
    resolve_two = _review_event(
        state_version=5,
        source_sha=resolve_two_sha,
        attempt_id=f"CARD-WF21-e0-{resolve_two_sha}",
        review_result="APPROVE",
        findings=[_finding(status="resolved", disposition="closed before correction")],
        counts_toward_escalation=False,
    )
    root_change = _contract_event("CORRECTION-006", "review-correction", 6)
    root_change.update({
        "escalation_epoch": 0,
        "target_attempt_id": second["attempt_id"],
        "finding_updates": [_finding(
            root_cause_id="rediagnosed-root", disposition="root cause re-diagnosed",
        )],
    })
    resolve_correction_sha = "f" * 40
    resolve_correction = _review_event(
        state_version=7,
        source_sha=resolve_correction_sha,
        attempt_id=f"CARD-WF21-e0-{resolve_correction_sha}",
        review_result="APPROVE",
        findings=[_finding(
            root_cause_id="rediagnosed-root", status="resolved",
            disposition="closed after re-diagnosis",
        )],
        counts_toward_escalation=False,
    )
    third_sha = "c" * 40
    third = _review_event(
        state_version=8,
        source_sha=third_sha,
        attempt_id=f"CARD-WF21-e0-{third_sha}",
        findings=[_finding(root_cause_id="rediagnosed-root")],
    )
    checkpoint = _contract_event("CHECKPOINT-009", "escalation-checkpoint", 9)
    checkpoint.update({
        "escalation_epoch": 0,
        "trigger_attempt_id": third["attempt_id"],
        "unique_attempt_count": 3,
        "checkpoint_decision": "continue",
        "checkpoint_rationale": "incorrectly ignores migrated repeated root",
    })

    try:
        workflow_ledger.render_ledger([
            baseline, first, resolve_one, second, resolve_two, root_change,
            resolve_correction, third, checkpoint,
        ])
    except ValueError as error:
        assert "checkpoint_decision 必須為 escalate" in str(error)
    else:
        raise AssertionError("root re-diagnosis 必須遷移該 finding 的所有 attempt occurrences")


def test_review_contract_rejects_conflicting_finding_in_same_attempt() -> None:
    baseline = _contract_event("BASELINE-001", "contract-baseline", 1)
    baseline["contract_baseline"] = workflow_ledger.REVIEW_CONTRACT
    conflicting = _review_event(
        state_version=3,
        review_result="APPROVE",
        findings=[_finding(status="resolved", disposition="another reviewer says fixed")],
        counts_toward_escalation=False,
    )
    conflicting["event_id"] = "REVIEW-003"

    try:
        workflow_ledger.render_ledger([baseline, _review_event(), conflicting])
    except ValueError as error:
        assert "finding" in str(error) and "衝突" in str(error)
    else:
        raise AssertionError("同一 attempt 的 finding 衝突必須 fail loud")


def test_review_invalid_requires_boolean_preflight_status() -> None:
    baseline = _contract_event("BASELINE-001", "contract-baseline", 1)
    baseline["contract_baseline"] = workflow_ledger.REVIEW_CONTRACT
    invalid = _contract_event("INVALID-002", "review-invalid", 2)
    invalid.update({"preflight_passed": "false", "invalid_reasons": ["wrong family"]})

    try:
        workflow_ledger.render_ledger([baseline, invalid])
    except ValueError as error:
        assert "preflight_passed" in str(error)
    else:
        raise AssertionError("review-invalid.preflight_passed 必須是布林值")


def test_preflight_failed_requires_false_and_nonempty_reasons() -> None:
    baseline = _contract_event("BASELINE-001", "contract-baseline", 1)
    baseline["contract_baseline"] = workflow_ledger.REVIEW_CONTRACT
    invalid = _contract_event("PREFLIGHT-002", "preflight-failed", 2)
    invalid.update({"preflight_passed": True, "failure_reasons": []})

    try:
        workflow_ledger.render_ledger([baseline, invalid])
    except ValueError as error:
        assert "preflight-failed" in str(error)
    else:
        raise AssertionError("preflight-failed schema 不合法時必須拒絕")


def test_approve_rejects_open_accepted_blocking_finding() -> None:
    baseline = _contract_event("BASELINE-001", "contract-baseline", 1)
    baseline["contract_baseline"] = workflow_ledger.REVIEW_CONTRACT
    invalid = _review_event(review_result="APPROVE", counts_toward_escalation=False)

    try:
        workflow_ledger.render_ledger([baseline, invalid])
    except ValueError as error:
        assert "APPROVE" in str(error) and "blocking finding" in str(error)
    else:
        raise AssertionError("APPROVE 不得保留 accepted blocking finding")


def test_render_ledger_uses_latest_event_for_each_card() -> None:
    events = [
        {
            "event_id": "base-a",
            "card_id": "CARD-A",
            "type": "migration-baseline",
            "actor": "ruan6047",
            "occurred_at": "2026-07-16T12:30:00+08:00",
            "state_version": 1,
            "iteration": 0,
            "source_sha": "abc1234",
            "evidence": "baseline",
            "initiative": "—",
            "tier": "T2",
            "feature": "測試卡",
            "owner": "待指派",
            "branch_worktree": "—",
            "delivery_status": "📥Backlog",
            "deployment_status": "—不適用",
        },
        {
            "event_id": "claim-a",
            "card_id": "CARD-A",
            "type": "claim",
            "actor": "GPT-5@Codex",
            "occurred_at": "2026-07-16T13:00:00+08:00",
            "state_version": 2,
            "iteration": 1,
            "source_sha": "def5678",
            "evidence": "claim",
            "initiative": "—",
            "tier": "T2",
            "feature": "測試卡",
            "owner": "GPT-5@Codex",
            "branch_worktree": "ai/gpt-5/CARD-A",
            "delivery_status": "🔨執行中",
            "deployment_status": "—不適用",
        },
    ]

    rendered = workflow_ledger.render_ledger(events)

    assert "| [CARD-A](tasks/CARD-A.md) | — | T2 | 測試卡 | GPT-5@Codex" in rendered
    assert "| `ai/gpt-5/CARD-A` | 1 | 🔨執行中 | —不適用 | 2026-07-16T13:00:00+08:00 |" in rendered


def test_render_ledger_rejects_a_missing_state_version() -> None:
    event = {
        "event_id": "bad",
        "card_id": "CARD-A",
        "type": "migration-baseline",
        "actor": "ruan6047",
        "occurred_at": "2026-07-16T12:30:00+08:00",
        "iteration": 0,
        "source_sha": "abc1234",
        "evidence": "baseline",
        "initiative": "—",
        "tier": "T2",
        "feature": "測試卡",
        "owner": "待指派",
        "branch_worktree": "—",
        "delivery_status": "📥Backlog",
        "deployment_status": "—不適用",
    }

    try:
        workflow_ledger.render_ledger([event])
    except ValueError as error:
        assert "state_version" in str(error)
    else:
        raise AssertionError("缺少 state_version 的事件必須失敗")


def test_render_ledger_excludes_released_cards() -> None:
    def _event(card_id: str, state_version: int, delivery_status: str) -> dict:
        return {
            "event_id": f"{card_id}-{state_version}",
            "card_id": card_id,
            "type": "release" if delivery_status == "🏁完成" else "migration-baseline",
            "actor": "ruan6047",
            "occurred_at": "2026-07-16T22:00:00+08:00",
            "state_version": state_version,
            "iteration": 1,
            "source_sha": "abc1234",
            "evidence": "test",
            "initiative": "—",
            "tier": "T4",
            "feature": "測試卡",
            "owner": "—",
            "branch_worktree": "—",
            "delivery_status": delivery_status,
            "deployment_status": "—不適用",
        }

    rendered = workflow_ledger.render_ledger([
        _event("CARD-OPEN", 1, "📥Backlog"),
        _event("CARD-DONE", 1, "🏁完成"),
    ])

    # 活卡 Ledger 只留未結案卡；🏁完成 卡由 archive 索引承接。
    assert "CARD-OPEN" in rendered
    assert "CARD-DONE" not in rendered


def _live_event(
    card_id: str, state_version: int, delivery_status: str, occurred_at: str, owner: str = "待指派"
) -> dict:
    return {
        "event_id": f"{card_id}-{state_version}",
        "card_id": card_id,
        "type": "handoff",
        "actor": "test",
        "occurred_at": occurred_at,
        "state_version": state_version,
        "iteration": 1,
        "source_sha": "abc1234",
        "evidence": "test",
        "initiative": "—",
        "tier": "T4",
        "feature": "測試卡",
        "owner": owner,
        "branch_worktree": "ai/test/CARD @ wt",
        "delivery_status": delivery_status,
        "deployment_status": "⏸未部署",
    }


def test_render_live_takes_max_state_version_across_branch_unions() -> None:
    # main 只有 v1 Backlog；分支頂端另有 v2 交接——即時視圖必須顯示 v2。
    rendered = workflow_ledger.render_live([
        _live_event("CARD-A", 1, "📥Backlog", "2026-07-17T04:44:00+08:00"),
        _live_event("CARD-A", 2, "🔍待查核", "2026-07-17T14:35:00+08:00"),
        _live_event("CARD-B", 1, "📥Backlog", "2026-07-17T04:44:00+08:00"),
        _live_event("CARD-C", 1, "🏁完成", "2026-07-17T17:20:00+08:00"),
    ], generated_at="2026-07-17T18:00:00+08:00")

    assert "CARD-A" in rendered
    assert "🔍待查核" in rendered
    assert "CARD-B" not in rendered  # idle 卡只計數不列行
    assert "CARD-C" not in rendered  # 已結案卡排除
    assert "另有 1 張" in rendered


def test_render_live_orders_in_flight_by_recency() -> None:
    rendered = workflow_ledger.render_live([
        _live_event("CARD-OLD", 2, "🔍待查核", "2026-07-17T12:45:00+08:00"),
        _live_event("CARD-NEW", 2, "🔍待查核", "2026-07-17T16:28:00+08:00"),
    ], generated_at="2026-07-17T18:00:00+08:00")

    assert rendered.index("CARD-NEW") < rendered.index("CARD-OLD")
