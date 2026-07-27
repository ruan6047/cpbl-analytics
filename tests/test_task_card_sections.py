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


def test_statistical_t4_cards_have_a_redline_section() -> None:
    """🔴統計卡必須在**卡面**列「紅線（違反即退回）」章節（canonical §5）。

    TEAM-STYLE1 iteration 1 的教訓：預註冊 spec 齊全、研究內容零缺陷，仍因卡面
    缺紅線章節被整輪跨家族查核退回——開卡時的 canonical 對照原本沒有守衛，
    靠 Coordinator 記得，而已經忘過兩次（LEAK2 的 T3→T4 誤分級是同型）。
    範圍同上一支測試（守門生效後有 lifecycle event 的活卡），加一個條件：
    卡面標題帶 🔴統計 標記者，必須另有標題含「紅線」的章節。
    """
    events = _events()
    start = next(
        index for index, event in enumerate(events) if event["event_id"] == ENFORCEMENT_EVENT_ID
    )
    affected = {str(event["card_id"]) for event in events[start:]}
    latest = {str(event["card_id"]): event for event in events}
    missing = []
    for card_id in sorted(affected):
        if latest[card_id]["delivery_status"] == "🏁完成":
            continue
        path = ROOT / "docs" / "tasks" / f"{card_id}.md"
        if not path.exists():
            continue  # 已封存（archive 由結案流程對帳）
        text = path.read_text(encoding="utf-8")
        title = text.splitlines()[0] if text else ""
        if "🔴統計" not in title:
            continue
        if not review_prompt.card_sections(card_id, ("紅線",)):
            missing.append(card_id)
    assert not missing, (
        "🔴統計卡必須在卡面列「紅線（違反即退回）」章節（canonical §5），"
        f"缺少：{', '.join(missing)}"
    )


def test_ci_web_job_runs_contract_tests() -> None:
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    web_job = workflow.split("  web:\n", maxsplit=1)[1]

    assert "working-directory: web" in web_job
    assert "run: npx tsc --noEmit" in web_job
    assert "run: npm test" in web_job


def test_initiative_children_carry_the_parent_baseline_field() -> None:
    """Initiative 子卡的 spec 基線欄不得為「—」（canonical baseline-cascade §5）。

    UX-TEAM-STYLE1 iteration 1 整輪查核退在這一欄上——而 process-wf17-conventions
    的教訓原文就是「首戰命中規則作者自己」，同一位 Coordinator 當日二度命中。
    開卡層的 canonical 對照不能靠記得；範圍同前兩支（守門生效後有 lifecycle event
    的活卡），凡卡面 Initiative 欄指向具體父卡者，spec 基線欄必須非「—」。
    版本是否與父卡一致仍由 review_prompt.baseline_check 在查核時比對（父卡版本
    會演進，這裡只擋「根本沒填」）。
    """
    events = _events()
    start = next(
        index for index, event in enumerate(events) if event["event_id"] == ENFORCEMENT_EVENT_ID
    )
    affected = {str(event["card_id"]) for event in events[start:]}
    latest = {str(event["card_id"]): event for event in events}
    missing = []
    for card_id in sorted(affected):
        if latest[card_id]["delivery_status"] == "🏁完成":
            continue
        path = ROOT / "docs" / "tasks" / f"{card_id}.md"
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        m = review_prompt._INITIATIVE_RE.search(text)
        if not m or card_id.startswith("INIT-"):
            continue  # 無父卡或本身是 initiative
        if not review_prompt._BASELINE_RE.search(text):
            missing.append(f"{card_id}（Initiative={m.group(1)}，spec 基線欄缺或為「—」）")
    assert not missing, (
        "Initiative 子卡的 spec 基線欄必填父卡版本（baseline-cascade §5）：\n  "
        + "\n  ".join(missing)
    )
