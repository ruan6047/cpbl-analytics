import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).parents[1]
SCRIPT_PATH = ROOT / "scripts" / "review_prompt.py"
SPEC = importlib.util.spec_from_file_location("review_prompt_for_lint", SCRIPT_PATH)
assert SPEC and SPEC.loader
review_prompt = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(review_prompt)

ENFORCEMENT_EVENT_ID = "OPS-PROCESS-GUARD1-REGISTER-001"
REVIEW_TOKENS = ("驗收", "驗證", "Gate")


def _events() -> list[dict[str, object]]:
    path = ROOT / "docs" / "control-plane" / "events.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def test_active_cards_with_new_lifecycle_events_have_review_sections() -> None:
    events = _events()
    start = next(
        index for index, event in enumerate(events) if event["event_id"] == ENFORCEMENT_EVENT_ID
    )
    affected = {str(event["card_id"]) for event in events[start:]}
    latest = {str(event["card_id"]): event for event in events}
    active = sorted(
        card_id for card_id in affected if latest[card_id]["delivery_status"] != "🏁完成"
    )

    missing = []
    for card_id in active:
        if not review_prompt.card_sections(card_id, REVIEW_TOKENS):
            missing.append(card_id)

    assert not missing, (
        "流程守門生效後有 lifecycle event 的活卡必須包含標題含"
        f" {REVIEW_TOKENS} 任一詞的驗收章節；缺少：{', '.join(missing)}"
    )


def test_ci_web_job_runs_contract_tests() -> None:
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    web_job = workflow.split("  web:\n", maxsplit=1)[1]

    assert "working-directory: web" in web_job
    assert "run: npx tsc --noEmit" in web_job
    assert "run: npm test" in web_job
