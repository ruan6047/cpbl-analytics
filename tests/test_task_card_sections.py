import importlib.util
import json
import re
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


_BASELINE_FIELD_RE = re.compile(r"spec 基線：\s*([^　\n]+)")
_VERSION_TOKEN_RE = re.compile(r"v\d+(?:\.\d+)*")


def _baseline_versions(text: str) -> tuple[str | None, set[str]]:
    """卡面 spec 基線欄的原文與其中的版本 token 集合。

    欄位以全形空格分隔（同一行還有 Initiative 等欄），故切到 `　` 或行尾為止；
    版本 token 取整段比對而非子字串包含——否則 `v1.0` 會被誤判為滿足父卡的 `v1`。
    """
    m = _BASELINE_FIELD_RE.search(text)
    if not m:
        return None, set()
    raw = m.group(1).strip()
    return raw, set(_VERSION_TOKEN_RE.findall(raw))


def test_initiative_children_baseline_matches_parent_version() -> None:
    """Initiative 子卡的 spec 基線欄必須含父卡當前版本（canonical baseline-cascade §5）。

    本測試原本只擋「欄位為『—』」，於是 `spec 基線：UX-TEAM-SPLIT-SCOPE1（近日焦點
    頁籤骨架）`——填的是**卡名不是版本**——一路通過，最後由 UX-TEAM-FOCUS2 的跨家族
    查核整輪退回才發現，且同型錯誤同時存在於四張卡。教訓與 INGEST-PLAYER-BIO-GAP1
    的閘門缺陷同型：**檢查哨兵值的缺席，不等於檢查該成立的性質**。

    改為實質比對：抽出子卡基線欄中的版本 token（`v1`／`v0.2`／`v1.3`…），要求父卡
    當前版本在其中。允許複合基線（如 `GAME_RECAP v1.3＋PRODUCT_UX_BLUEPRINT v0.2`）
    ——只要父卡版本是其中之一即可，因為那類卡確實同時受兩份 spec 約束。
    token 取整段相等而非子字串，否則 `v1.0` 會被 `v1` 誤放行。
    """
    events = _events()
    start = next(
        index for index, event in enumerate(events) if event["event_id"] == ENFORCEMENT_EVENT_ID
    )
    affected = {str(event["card_id"]) for event in events[start:]}
    latest = {str(event["card_id"]): event for event in events}
    bad = []
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
        parent_id = m.group(1)
        parent_path = ROOT / "docs" / "tasks" / f"{parent_id}.md"
        if not parent_path.exists():
            continue  # 父卡已封存；版本由查核時人工核對
        parent_raw, parent_vers = _baseline_versions(parent_path.read_text(encoding="utf-8"))
        if not parent_vers:
            continue  # 父卡自己沒有版本可比，非子卡之過
        child_raw, child_vers = _baseline_versions(text)
        if child_vers & parent_vers:
            continue
        bad.append(
            f"{card_id}（Initiative={parent_id}；卡面「{child_raw or '缺欄'}」"
            f"未含父卡當前版本 {sorted(parent_vers)}，父卡欄為「{parent_raw}」）"
        )
    assert not bad, (
        "Initiative 子卡的 spec 基線欄必須含父卡當前版本（baseline-cascade §5）；"
        "填卡名或舊版本皆會在查核時整輪退回：\n  " + "\n  ".join(bad)
    )
