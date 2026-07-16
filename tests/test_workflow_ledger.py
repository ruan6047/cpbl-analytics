import importlib.util
from pathlib import Path

SCRIPT_PATH = Path(__file__).parents[1] / "scripts" / "workflow_ledger.py"
SPEC = importlib.util.spec_from_file_location("workflow_ledger", SCRIPT_PATH)
assert SPEC and SPEC.loader
workflow_ledger = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(workflow_ledger)


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
