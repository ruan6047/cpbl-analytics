import importlib.util
import json
from pathlib import Path

import pytest

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


BASELINE_CASES = [
    # (欄位原文, 期望宣告值)
    ("v1", {"v1"}),
    ("v1.3", {"v1.3"}),
    ("—", set()),
    # 括號說明：說明裡的版本是敘述，不是宣告（本測試守衛的破口）
    ("v2（v1 範圍過窄，見背景「v1 範圍錯誤」節）", {"v2"}),
    ("v2（範圍過窄，見背景節）", {"v2"}),
    ("v1（＝父卡當前版本）", {"v1"}),
    ("`REVIEW_GATE_CONTRACT.md` v1.0（沿用；本卡不改契約語意）", {"v1.0"}),
    # 沒有括號的散文說明：子句只取第一個 token，後面的敘述不算宣告
    ("v2 — v1 範圍過窄故改版", {"v2"}),
    ("v2，因 v1 過窄", {"v2"}),
    # 複合基線：一張卡同時受兩份 spec 約束，兩個版本都是宣告值
    ("GAME_RECAP v1.3＋PRODUCT_UX_BLUEPRINT v0.2", {"v1.3", "v0.2"}),
    ("PRODUCT_UX_BLUEPRINT v0.2、LIVE_GAME_PRODUCT_SPEC v1.1", {"v0.2", "v1.1"}),
    ("`UI_UX_SYSTEM` v1 §2.1／§8", {"v1"}),
    # 括號說明內含複合分隔符：說明必須先剝掉，否則會被切成子句而抽出說明裡的舊版本
    ("GAME_RECAP v1.3（含 v1.2、v1.1 的變更）", {"v1.3"}),
    # 字元邊界：版本 token 必須獨立成詞，不得從別的字裡撈出來（DECL1-F001）
    ("rev1", set()),
    ("v1beta", set()),
    ("v2rev1", set()),
    ("SPEC_v1", set()),
    ("`GAME_RECAP` v1.3", {"v1.3"}),  # 名稱含底線但版本獨立成詞，仍算宣告
    # 以文件連結或卡名表示：無版本可解析，回空集合（由呼叫端退回人工核對）
    ("[`../research/OFFICIAL_DATA_GAP1_RESULTS.md`](../research/OFFICIAL_DATA_GAP1_RESULTS.md) §4", set()),
    ("UX-TEAM-SPLIT-SCOPE1", set()),
]


@pytest.mark.parametrize("raw, expected", BASELINE_CASES)
def test_baseline_declaration_reads_the_declared_value_only(raw: str, expected: set[str]) -> None:
    """`spec 基線` 欄的判定基準是**宣告值**，不是整段欄位文字。

    2026-08-03 的破口：下一支測試以整段欄位抽 token 再取交集，於是
    `spec 基線：v2（v1 範圍過窄，見背景節）`——宣告值是錯的 v2，只因說明文字提到
    父卡的 v1——交集非空而放行。`INGEST-PLAYER-BIO-GAP2` 與
    `INGEST-SPLITS-IMPORT-RESTATE1` 兩卡同時中招，守衛全綠，最後由獨立查核者以
    PREFLIGHT_FAILED 擋下，燒掉一輪送審。

    本表是該判定的直接守衛（上面三列即當時的實測重現：紅／紅／綠）；下一支測試
    只負責把它套到真實卡面語料上。複合基線必須維持可通過——`docs/tasks/` 下有實例。

    **iteration 1 的查核 finding `DECL1-F001`**：版本 token 原本沒有字元邊界，於是
    `spec 基線：rev1` 被抽成 `{v1}` 而放行。這不是假想輸入——卡面正好有「卡面修訂：rev2」
    這種相鄰欄位（`INGEST-PLAYER-BIO-GAP2`），兩欄混用正是本卡要擋的那個錯誤本身。
    邊界只排除 ASCII 英數與底線；抽不到版本時判定會落到「無宣告值」那條路（pytest 硬紅），
    **失敗方向是過嚴而非過寬**——過嚴只會逼人把欄位寫清楚，過寬會讓錯的基線交付。
    """
    line = f"- Initiative：INIT-X　spec 基線：{raw}\n"
    assert review_prompt.baseline_declaration(line) == (raw, expected)


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

    **第二次修補（2026-08-03）**：token 原本自**整段欄位文字**抽出，於是
    `spec 基線：v2（v1 範圍過窄，見背景節）` 因說明文字含 `v1` 而放行——同型的第三次，
    這回是「檢查該成立的性質，但取樣範圍多含了不該算數的敘述」。改為只看
    `review_prompt.baseline_declaration()` 抽出的宣告值（括號說明不計、每個宣告子句
    只取第一個 token），與查核提示詞 `baseline_check()` 共用同一支抽取器——兩處各寫
    一份正是上一輪誤報的來源（提示詞把 `v1（＝父卡當前版本）` 判成不一致）。
    抽取規則本身的守衛在上一支參數化測試。
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
        parent_raw, parent_vers = review_prompt.baseline_declaration(
            parent_path.read_text(encoding="utf-8")
        )
        if not parent_vers:
            continue  # 父卡自己沒有版本可比，非子卡之過
        child_raw, child_vers = review_prompt.baseline_declaration(text)
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
