import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT_PATH = Path(__file__).parents[1] / "scripts" / "review_prompt.py"
SPEC = importlib.util.spec_from_file_location("review_prompt", SCRIPT_PATH)
assert SPEC and SPEC.loader
review_prompt = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(review_prompt)


def _write_card(root: Path, heading: str) -> None:
    path = root / "docs" / "tasks" / "CARD-A.md"
    path.parent.mkdir(parents=True)
    path.write_text(
        f"# CARD-A\n\n## 背景\n\n背景內容\n\n## {heading}\n\n- [ ] 必須成立\n\n"
        "## Log\n\n- 建卡\n",
        encoding="utf-8",
    )


@pytest.mark.parametrize(
    "heading",
    ["驗收條件", "目標與驗收", "驗收", "驗收與回滾", "Gate 與驗證"],
)
def test_card_sections_matches_review_heading_variants(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, heading: str
) -> None:
    _write_card(tmp_path, heading)
    monkeypatch.setattr(review_prompt, "ROOT", tmp_path)

    sections = review_prompt.card_sections("CARD-A", ("驗收", "驗證", "Gate"))

    assert f"## {heading}" in sections
    assert "必須成立" in sections
    assert "## Log" not in sections


def test_card_sections_warns_when_no_review_heading(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_card(tmp_path, "實作範圍")
    monkeypatch.setattr(review_prompt, "ROOT", tmp_path)

    sections = review_prompt.card_sections("CARD-A", ("驗收", "驗證", "Gate"))

    assert sections == ""
    assert "警告：CARD-A 找不到可錨定的驗收章節" in capsys.readouterr().err


# --- spec 基線一致性（OPS-REVIEW-BASELINE1；canonical baseline-cascade §5） ---
def _write_child(root: Path, initiative: str, baseline: str | None) -> None:
    path = root / "docs" / "tasks" / "CHILD-1.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    base = f"　spec 基線：{baseline}" if baseline else ""
    path.write_text(
        f"# CHILD-1 子卡\n\n- Initiative：{initiative}{base}\n\n## 驗收條件\n\n- [ ] x\n",
        encoding="utf-8",
    )


def _write_parent(root: Path, baseline: str | None, archived: bool = False) -> None:
    sub = "archive/tasks" if archived else "tasks"
    path = root / "docs" / sub / "INIT-X.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    base = f"- spec 基線：{baseline}\n" if baseline else "- 無基線欄\n"
    path.write_text(f"# INIT-X 父卡\n\n{base}\n## 基線變更紀錄\n\n- v?\n", encoding="utf-8")


def test_baseline_check_consistent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_child(tmp_path, "INIT-X", "v1.3")
    _write_parent(tmp_path, "v1.3")
    monkeypatch.setattr(review_prompt, "ROOT", tmp_path)

    block = review_prompt.baseline_check("CHILD-1")

    assert "INIT-X" in block
    assert "`v1.3`" in block
    assert "→ 一致" in block          # 判定行本身
    assert "舊基線交付" not in block  # 不得出現退回判定


def test_baseline_check_mismatch_flags_return(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_child(tmp_path, "INIT-X", "v1.2")
    _write_parent(tmp_path, "v1.3")
    monkeypatch.setattr(review_prompt, "ROOT", tmp_path)

    block = review_prompt.baseline_check("CHILD-1")

    assert "不一致" in block and "退回" in block
    assert "`v1.3`" in block and "`v1.2`" in block


def test_baseline_check_no_initiative_stays_silent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "docs" / "tasks" / "CHILD-1.md"
    path.parent.mkdir(parents=True)
    path.write_text("# CHILD-1\n\n- Initiative：—　spec 基線：—\n\n## 驗收條件\n\n- [ ] x\n",
                    encoding="utf-8")
    monkeypatch.setattr(review_prompt, "ROOT", tmp_path)

    assert review_prompt.baseline_check("CHILD-1") == ""


def test_baseline_check_missing_field_demands_manual(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_child(tmp_path, "INIT-X", "v1.3")
    _write_parent(tmp_path, None)  # 父卡無 spec 基線欄
    monkeypatch.setattr(review_prompt, "ROOT", tmp_path)

    block = review_prompt.baseline_check("CHILD-1")

    assert "人工核對" in block
    assert "基線變更紀錄" in block


def test_baseline_check_finds_archived_parent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_child(tmp_path, "INIT-X", "v2.0")
    _write_parent(tmp_path, "v2.0", archived=True)  # 父卡已封存
    monkeypatch.setattr(review_prompt, "ROOT", tmp_path)

    block = review_prompt.baseline_check("CHILD-1")

    assert "archive/tasks" in block and "一致" in block


# --- 查核環境隔離（DEV-REVIEW-PROMPT-GUARD1 缺陷 1；HANDOFF_CONTRACT §3／§5） ---
SHA = "c577fc863c1ea571166e7cd6de0c5d4216413262"
EXEC_WT = ".claude/worktrees/ux-entity-links2-execution"


def test_review_worktree_block_builds_detached_worktree(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(review_prompt, "MAIN_ROOT", Path("/repo"))

    block = review_prompt.review_worktree_block(
        "UX-ENTITY-LINKS2", {"source_sha": SHA, "worktree": EXEC_WT})

    # §5 的建立指令，帶完整 40 字元 SHA 與 §3 的兩項自我驗證
    assert f"worktree add --detach .claude/worktrees/ux-entity-links2-review {SHA}" in block
    assert "git status --short" in block and "git rev-parse HEAD" in block
    assert "worktree remove" in block                      # 用畢清理


def test_review_worktree_block_never_sends_reviewer_into_executor_worktree(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """執行者 worktree 可以出現，但只能以「不得進駐」的形式出現。"""
    monkeypatch.setattr(review_prompt, "MAIN_ROOT", Path("/repo"))

    block = review_prompt.review_worktree_block(
        "UX-ENTITY-LINKS2", {"source_sha": SHA, "worktree": EXEC_WT})

    assert "不得在執行者的 worktree 上查核" in block
    assert "僅供對照，不得進駐" in block
    # 舊版的致命寫法：叫查核者進駐執行者的 worktree 並在該處執行指令
    assert "進駐 worktree" not in block
    assert f"cd /repo/{EXEC_WT}" not in block


# --- 重現指令依改動路徑（DEV-REVIEW-PROMPT-GUARD1 缺陷 2） ---
def _repro(monkeypatch: pytest.MonkeyPatch, paths: list[str], err: str | None = None) -> str:
    monkeypatch.setattr(review_prompt, "changed_paths", lambda _sha: (paths, err))
    return review_prompt.repro_commands({"source_sha": SHA})


def test_repro_frontend_card_uses_npm_not_pytest(monkeypatch: pytest.MonkeyPatch) -> None:
    out = _repro(monkeypatch, ["web/src/components/ui.tsx", "web/src/app/standings/page.tsx"])

    assert "npm ci" in out and "npm run build:check" in out and "npm test" in out
    # 前端卡跑 ruff／pytest 掃不到任何被審改動，全綠也證明不了事
    assert "uv run pytest" not in out and "uv run ruff" not in out


def test_repro_frontend_card_excludes_interactive_lint(monkeypatch: pytest.MonkeyPatch) -> None:
    """本專案未設定 ESLint，`next lint` 會進互動式精靈——不是驗證失敗。"""
    out = _repro(monkeypatch, ["web/src/components/ui.tsx"])

    assert "不要跑 `npm run lint`" in out
    assert "不得據此開 finding" in out


def test_repro_python_card_uses_ruff_and_pytest(monkeypatch: pytest.MonkeyPatch) -> None:
    out = _repro(monkeypatch, ["src/cpbl/api/main.py", "migrations/060_x.sql"])

    assert "uv run ruff check" in out and "uv run pytest -q" in out
    assert "npm" not in out


def test_repro_mixed_card_emits_both(monkeypatch: pytest.MonkeyPatch) -> None:
    out = _repro(monkeypatch, ["src/cpbl/api/routers/teams.py", "web/src/app/teams/page.tsx"])

    assert "混合卡" in out
    assert "uv run pytest -q" in out and "npm run build:check" in out


def test_repro_docs_only_card_offers_no_default_commands(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    out = _repro(monkeypatch, ["docs/AI_RUNBOOK.md", "docs/reference/GLOSSARY.md"])

    assert "沒有標準重現指令" in out
    assert "uv run pytest" not in out and "npm ci" not in out


def test_repro_undecidable_fails_loud_without_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """判不出來時明講，不得靜默退回任一預設指令組（紅線 2）。"""
    out = _repro(monkeypatch, [], err="git diff 失敗：fatal: bad revision")

    assert "無法判定卡片型態" in out
    assert "bad revision" in out
    assert "uv run pytest" not in out and "npm ci" not in out


# --- 獨立性：只給下限、不給結論（DEV-REVIEW-PROMPT-GUARD1 缺陷 3，iteration 3 定案） ---
def _write_indep_card(root: Path, review_field: str | None, body: str = "") -> None:
    path = root / "docs" / "tasks" / "CARD-I.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    header = "- 執行：待指派（建議 L2）"
    if review_field is not None:
        header += f"　查核：{review_field}"
    path.write_text(f"# CARD-I 卡\n\n{header}\n\n## 驗收條件\n\n- [ ] x\n{body}\n",
                    encoding="utf-8")


# --- 獨立性：只給下限、不給結論（iteration 3，升級裁定路線 A） ---
# 舊測試斷言的是「腳本推導出哪一級」。那個能力已被移除：三輪查核證實從卡面自由文字
# 推斷流程門檻不可靠（REVIEW-005／007／009）。現在要斷言的性質換成一句話——
# **工具不得宣稱上限**，因此不可能把卡面要求說低。
_REVIEW_009_COUNTEREXAMPLES = [
    # REVIEW-005：AND 被讀成 OR
    "先跨家族查核，並由需求方人工核可",
    # REVIEW-007：條件句被讀成二擇一
    "跨家族查核，若失敗或有疑問再人工核可",
    # REVIEW-009：否定句與引文覆蓋真正要求；第二例的命中是把「人工智慧」從中切斷
    "需求方人工核可；不得沿用舊文案「跨家族或人工」",
    "需求方人工核可（不可由跨家族或人工智慧代理取代）",
]


@pytest.mark.parametrize("field", _REVIEW_009_COUNTEREXAMPLES)
def test_independence_never_claims_a_conclusion_for_prose(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, field: str
) -> None:
    """三輪反例全部失去適用對象——不是被更聰明的規則擋掉，是工具不再下結論。"""
    _write_indep_card(tmp_path, field)
    monkeypatch.setattr(review_prompt, "ROOT", tmp_path)

    summary, detail = review_prompt.independence("CARD-I", "T2")

    assert "以卡面〈查核〉欄為準" in summary        # 摘要講的是「去看卡面」
    assert field in detail                          # 原文照登
    assert "腳本不解讀卡面語意" in detail
    assert "不得自行放寬" in detail


@pytest.mark.parametrize(
    ("tier", "floor"),
    [("T2", "新 context／session 即可（不得為執行者本人）"),
     ("T3", "新 context／session 即可（不得為執行者本人）"),
     ("T4", "跨模型家族（非執行者所屬家族）或人工")],
)
def test_independence_floor_comes_from_tier_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, tier: str, floor: str
) -> None:
    """下限來自 tier 這個結構化欄位，不來自任何文字推斷。"""
    _write_indep_card(tmp_path, "待指派（≠ 執行）")
    monkeypatch.setattr(review_prompt, "ROOT", tmp_path)

    summary, detail = review_prompt.independence("CARD-I", tier)

    assert floor in summary and floor in detail


def test_independence_keeps_card_face_verbatim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    field = "待指派（≠ 執行；跨家族或人工）"
    _write_indep_card(tmp_path, field)
    monkeypatch.setattr(review_prompt, "ROOT", tmp_path)

    _, detail = review_prompt.independence("CARD-I", "T2")

    assert f"`{field}`" in detail


def test_independence_missing_field_says_so_without_relaxing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """缺欄位不得被讀成「所以沒有額外要求」。"""
    _write_indep_card(tmp_path, None)
    monkeypatch.setattr(review_prompt, "ROOT", tmp_path)

    _, detail = review_prompt.independence("CARD-I", "T2")

    assert "**未找到**" in detail
    assert "這不代表沒有額外要求" in detail
    assert "找不到〈查核〉欄" in capsys.readouterr().err


# --- 機器可讀獨立性欄位 review_independence（DEV-REVIEW-INDEP-FIELD1） ---
def _write_field_card(
    root: Path, field_value: str | None, review_field: str = "待指派（≠ 執行）"
) -> None:
    """卡面 header：〈查核〉自由文字欄 ＋（可選）`review_independence` 宣告行。"""
    path = root / "docs" / "tasks" / "CARD-F.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    header = f"- 執行：待指派（建議 L2）　查核：{review_field}"
    if field_value is not None:
        header += f"\n- review_independence: {field_value}"
    path.write_text(f"# CARD-F 卡\n\n{header}\n\n## 驗收條件\n\n- [ ] x\n", encoding="utf-8")


def test_independence_without_field_is_verbatim_previous_behaviour(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """紅線 2：缺欄＝現況等價。新欄位的任何字樣都不得出現，且事件脈絡不改變輸出。"""
    _write_field_card(tmp_path, None, review_field="待指派（≠ 執行；跨家族或人工）")
    monkeypatch.setattr(review_prompt, "ROOT", tmp_path)
    events = [_review(2, actor="Claude Opus 5（同家族）")]

    baseline = review_prompt.independence("CARD-F", "T3")
    with_events = review_prompt.independence("CARD-F", "T3", events)

    assert with_events == baseline                       # 事件不得讓缺欄卡多出任何一行
    summary, detail = baseline
    assert summary == "下限 新 context／session 即可（不得為執行者本人）；實際要求以卡面〈查核〉欄為準"
    assert "卡面〈查核〉欄原文（**以此為準**）：`待指派（≠ 執行；跨家族或人工）`" in detail
    assert "review_independence" not in detail           # 缺欄不多話，也不放寬
    assert "留痕" not in detail and "對照" not in detail


def test_independence_single_gate_field_is_printed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_field_card(tmp_path, "[cross_family]")
    monkeypatch.setattr(review_prompt, "ROOT", tmp_path)

    summary, detail = review_prompt.independence("CARD-F", "T3")

    assert "卡面宣告 1 關：跨家族" in summary
    assert "第 1 關 `cross_family`（跨模型家族的查核者，非執行者所屬家族）" in detail
    assert "留痕，不是保證" in detail
    assert "第 2 關" not in detail


def test_independence_multi_gate_keeps_declared_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """有序清單：印出的順序必須是卡面宣告的順序，不是值域或字母序。"""
    _write_field_card(tmp_path, "[human, cross_family]")
    monkeypatch.setattr(review_prompt, "ROOT", tmp_path)

    summary, detail = review_prompt.independence("CARD-F", "T3")

    assert "卡面宣告 2 關：人工審 → 跨家族" in summary
    assert detail.index("第 1 關 `human`") < detail.index("第 2 關 `cross_family`")
    assert "尚未完成的那一關" in detail          # 幾關由欄位、跑到哪一關由事件
    assert "不說跑到哪一關" in detail


def test_independence_reversed_order_is_not_normalised(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_field_card(tmp_path, "[cross_family, human]")
    monkeypatch.setattr(review_prompt, "ROOT", tmp_path)

    summary, detail = review_prompt.independence("CARD-F", "T3")

    assert "卡面宣告 2 關：跨家族 → 人工審" in summary
    assert detail.index("第 1 關 `cross_family`") < detail.index("第 2 關 `human`")


@pytest.mark.parametrize(
    ("value", "expected"),
    [("human", "不是清單"),                       # 非清單
     ("[]", "空清單"),                             # 空清單
     ("[cross_family_and_human]", "不在值域"),      # 元素不在值域（合成值）
     ("[cross_family, ]", "不在值域")],             # 空元素同樣不得靜默略過
)
def test_independence_illegal_value_fails_loud(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, value: str, expected: str
) -> None:
    """比照 closes_review_round：寫壞不得被當成缺席帶過（那是靜默放寬）。"""
    _write_field_card(tmp_path, value)
    monkeypatch.setattr(review_prompt, "ROOT", tmp_path)

    with pytest.raises(SystemExit) as exc:
        review_prompt.independence("CARD-F", "T3")

    message = str(exc.value)
    assert expected in message
    assert "拒絕產生提示詞" in message
    assert "review_independence: [human, cross_family]" in message   # 給出正確寫法


def test_independence_duplicate_field_lines_fail_loud(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_field_card(tmp_path, "[human]")
    path = tmp_path / "docs" / "tasks" / "CARD-F.md"
    path.write_text(path.read_text(encoding="utf-8").replace(
        "- review_independence: [human]",
        "- review_independence: [human]\n- review_independence: [cross_family]"),
        encoding="utf-8")
    monkeypatch.setattr(review_prompt, "ROOT", tmp_path)

    with pytest.raises(SystemExit) as exc:
        review_prompt.independence("CARD-F", "T3")

    assert "2 行" in str(exc.value)


def test_independence_field_ignores_prose_below_header(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """正文與程式碼區塊裡的同名字樣是敘述，不是宣告（本卡自己的卡面就有舉例）。"""
    path = tmp_path / "docs" / "tasks" / "CARD-F.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# CARD-F 卡\n\n- 執行：待指派　查核：待指派（≠ 執行）\n\n## 目標\n\n"
        "候選寫法：\n\n- review_independence: [human, cross_family]\n",
        encoding="utf-8")
    monkeypatch.setattr(review_prompt, "ROOT", tmp_path)

    assert review_prompt.card_review_independence("CARD-F") is None


def test_independence_field_invariant_under_guard1_counterexamples(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """GUARD1 三輪四類反例：全部無處可施——自由文字根本不參與判定。

    證明方式不是「規則擋掉了它們」，而是**輸出的關卡宣告在四種反例文字下逐字相同**，
    且與卡面欄位一致；自由文字只以原文形式出現。
    """
    monkeypatch.setattr(review_prompt, "ROOT", tmp_path)
    declarations: list[str] = []
    for prose in _REVIEW_009_COUNTEREXAMPLES:
        _write_field_card(tmp_path, "[context]", review_field=prose)

        assert review_prompt.card_review_independence("CARD-F") == ["context"]
        summary, detail = review_prompt.independence("CARD-F", "T3")

        assert "卡面宣告 1 關：新 context" in summary        # 反例文字動不了宣告
        assert f"`{prose}`" in detail                        # 原文照登
        assert "照登，不解讀" in detail
        declarations.append(
            "\n".join(ln for ln in detail.splitlines() if "宣告" in ln or "第 1 關" in ln))

    assert len(set(declarations)) == 1, "自由文字改變了宣告輸出＝推斷邏輯復活"


def test_independence_parallels_last_review_actor_as_advisory_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Q4：宣告值與上一輪 review 的 actor 並列，明示輔助判讀、非保證、不仲裁。"""
    _write_field_card(tmp_path, "[cross_family]")
    monkeypatch.setattr(review_prompt, "ROOT", tmp_path)
    events = [_handoff(), _review(2, actor="Claude Opus 5（與執行者同家族）")]

    _, detail = review_prompt.independence("CARD-F", "T3", events)

    assert "Claude Opus 5（與執行者同家族）" in detail
    assert "CARD-G-REVIEW-002" in detail
    assert "輔助判讀，非保證" in detail
    assert "不做一致性仲裁" in detail
    assert "不替任何人下結論" in detail


def test_independence_parallel_states_when_no_review_events(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_field_card(tmp_path, "[human, cross_family]")
    monkeypatch.setattr(review_prompt, "ROOT", tmp_path)

    _, detail = review_prompt.independence("CARD-F", "T3", [_handoff()])

    assert "尚無任何 review 事件" in detail


def test_no_prose_inference_helpers_remain() -> None:
    """路線已放棄：推斷用的常數與函式不得復活（復活即代表同一個病回來了）。"""
    for name in ("_CROSS_TOKENS", "_INDEP_OR_RE", "_INDEP_JOIN",
                 "_card_indep_level", "card_body_cross_family_hint"):
        assert not hasattr(review_prompt, name), f"{name} 不該存在"


# --- 中繼查核關卡（DEV-REVIEW-PROMPT-GATE1） ---
def _write_events(root: Path, *events: dict) -> None:
    path = root / "docs" / "control-plane" / "events.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in events),
                    encoding="utf-8")


def _handoff(**over: object) -> dict:
    return {"card_id": "CARD-G", "type": "handoff", "event_id": "CARD-G-HANDOFF-001",
            "state_version": 1, "source_sha": SHA, "branch": "ai/x/CARD-G", **over}


def _review(sv: int, **over: object) -> dict:
    return {"card_id": "CARD-G", "type": "review", "event_id": f"CARD-G-REVIEW-{sv:03d}",
            "state_version": sv, "review_result": "APPROVE", "actor": "查核者",
            "occurred_at": "2026-07-29T18:00:00+08:00", "evidence": "裁定內容", **over}


def _prepare(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *events: dict) -> None:
    _write_events(tmp_path, *events)
    monkeypatch.setattr(review_prompt, "ROOT", tmp_path)
    # 分支 HEAD 比對是另一道守衛，本組測試不涉及
    monkeypatch.setattr(review_prompt, "_assert_handoff_matches_branch_head", lambda _ev: None)


def test_review_without_field_still_closes_the_round(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """欄位缺席＝終結本輪：146 筆歷史事件的判定不得因本次改動而改變。"""
    _prepare(tmp_path, monkeypatch, _handoff(), _review(2))

    with pytest.raises(SystemExit) as exc:
        review_prompt.latest_handoff("CARD-G")

    assert "拒絕產生提示詞" in str(exc.value)


def test_interim_gate_does_not_close_the_round(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """UX-ENTITY-LINKS2 的實況：人工審 APPROVE 是第一關，本輪尚未結束。"""
    _prepare(tmp_path, monkeypatch,
             _handoff(), _review(2, closes_review_round=False, actor="ruan6047（人工審）"))

    ev, gates = review_prompt.latest_handoff("CARD-G")

    assert ev["event_id"] == "CARD-G-HANDOFF-001"
    assert [g["event_id"] for g in gates] == ["CARD-G-REVIEW-002"]


def test_interim_gate_then_final_reject_still_blocks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """中繼關卡不得成為繞過退回的手段。"""
    _prepare(tmp_path, monkeypatch, _handoff(),
             _review(2, closes_review_round=False),
             _review(3, review_result="REJECT"))

    with pytest.raises(SystemExit) as exc:
        review_prompt.latest_handoff("CARD-G")

    assert "REJECT" in str(exc.value)


def test_appended_correction_can_reopen_a_wrongly_closed_round(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """event log 是 append-only：寫錯只能追加更正，且更正必須以 corrects_event_id 指名對象。"""
    _prepare(tmp_path, monkeypatch, _handoff(), _review(2),
             _review(3, closes_review_round=False, corrects_event_id="CARD-G-REVIEW-002",
                     evidence="更正 REVIEW-002：那是中繼關卡"))

    _, gates = review_prompt.latest_handoff("CARD-G")

    assert [g["event_id"] for g in gates] == ["CARD-G-REVIEW-002", "CARD-G-REVIEW-003"]


def test_uncorrected_false_cannot_reopen_a_closed_round(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """iteration 1 退回 finding 1：終局 REJECT 後追加「任意」`false` 不得重開本輪，
    否則中繼欄位就是繞過退回的後門；重開還會把該 REJECT 標成已通過關卡（finding 2）。"""
    _prepare(tmp_path, monkeypatch, _handoff(),
             _review(2, review_result="REJECT"),
             _review(3, closes_review_round=False))

    with pytest.raises(SystemExit) as exc:
        review_prompt.latest_handoff("CARD-G")

    message = str(exc.value)
    assert "REJECT" in message
    assert "corrects_event_id" in message   # 訊息給出的是「指名更正」這條路，不是任意追加


def test_correction_without_field_restores_terminal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """更正事件自身缺席欄位＝宣告 true：誤標的中繼可被改回終局，兩個方向對稱。"""
    _prepare(tmp_path, monkeypatch, _handoff(),
             _review(2, closes_review_round=False),
             _review(3, corrects_event_id="CARD-G-REVIEW-002",
                     evidence="更正：REVIEW-002 其實是終局查核"))

    with pytest.raises(SystemExit) as exc:
        review_prompt.latest_handoff("CARD-G")

    assert "拒絕產生提示詞" in str(exc.value)


def test_correction_target_must_precede_it_in_current_round(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """更正只能指向同輪內較早的 review；上一輪的判定已被新 handoff 重置。"""
    _prepare(tmp_path, monkeypatch, _handoff(), _review(2),
             _handoff(event_id="CARD-G-HANDOFF-003", state_version=3),
             _review(4, closes_review_round=False, corrects_event_id="CARD-G-REVIEW-002"))

    with pytest.raises(SystemExit) as exc:
        review_prompt.latest_handoff("CARD-G")

    assert "沒有這筆 review" in str(exc.value)


def test_correction_target_type_fails_loud(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _prepare(tmp_path, monkeypatch, _handoff(), _review(2),
             _review(3, closes_review_round=False, corrects_event_id=2))

    with pytest.raises(SystemExit) as exc:
        review_prompt.latest_handoff("CARD-G")

    assert "event_id 字串" in str(exc.value)


def test_correction_cannot_target_itself(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _prepare(tmp_path, monkeypatch, _handoff(),
             _review(2, closes_review_round=False, corrects_event_id="CARD-G-REVIEW-002"))

    with pytest.raises(SystemExit) as exc:
        review_prompt.latest_handoff("CARD-G")

    assert "指向自己" in str(exc.value)


def test_malformed_field_on_earlier_review_is_not_masked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """iteration 1 退回 finding 3：型別驗證涵蓋每一筆 review，
    較早的 malformed 事件不得被後續 `false` 掩蓋。"""
    _prepare(tmp_path, monkeypatch, _handoff(),
             _review(2, closes_review_round="false"),
             _review(3, closes_review_round=False))

    with pytest.raises(SystemExit) as exc:
        review_prompt.latest_handoff("CARD-G")

    message = str(exc.value)
    assert "只接受布林值" in message
    assert "CARD-G-REVIEW-002" in message   # 指名的是 malformed 那一筆，不是最後一筆


def test_malformed_field_in_previous_round_still_fails_loud(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """型別驗證不分輪：新 handoff 重置的是本輪判定，不是資料錯誤的追究。"""
    _prepare(tmp_path, monkeypatch, _handoff(),
             _review(2, closes_review_round=1),
             _handoff(event_id="CARD-G-HANDOFF-003", state_version=3))

    with pytest.raises(SystemExit) as exc:
        review_prompt.latest_handoff("CARD-G")

    assert "只接受布林值" in str(exc.value)


def test_new_handoff_resets_the_round(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _prepare(tmp_path, monkeypatch, _handoff(), _review(2),
             _handoff(event_id="CARD-G-HANDOFF-003", state_version=3))

    ev, gates = review_prompt.latest_handoff("CARD-G")

    assert ev["event_id"] == "CARD-G-HANDOFF-003"
    assert gates == []


def test_non_boolean_field_fails_loud(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """猜錯的兩個方向都有代價——型別不對就吵，不當成缺席帶過。"""
    _prepare(tmp_path, monkeypatch, _handoff(), _review(2, closes_review_round="false"))

    with pytest.raises(SystemExit) as exc:
        review_prompt.latest_handoff("CARD-G")

    assert "只接受布林值" in str(exc.value)


def test_refusal_message_no_longer_asserts_review_is_unnecessary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """舊訊息斷言「APPROVE → 不需要再查核一次」，對多關卡的卡是叫人 merge 未查核的交付。"""
    _prepare(tmp_path, monkeypatch, _handoff(), _review(2))

    with pytest.raises(SystemExit) as exc:
        review_prompt.latest_handoff("CARD-G")

    message = str(exc.value)
    assert "不需要再查核一次" not in message
    assert "closes_review_round" in message      # 指出中繼關卡的正確表達方式
    assert "本守衛分不出來" in message            # 不替人斷言


def test_gates_block_carries_rulings_and_warns_round_is_open() -> None:
    block = review_prompt.review_gates_block(
        [_review(2, closes_review_round=False, actor="ruan6047（本地人工審）",
                 evidence="RosterChips 隊色文字裁定接受")])

    assert "不代表本輪查核已結束" in block
    assert "不要重開已定案的爭點" in block
    assert "RosterChips 隊色文字裁定接受" in block   # 裁定原文帶給下一位查核者
    assert "ruan6047（本地人工審）" in block


def test_gates_block_is_empty_without_gates() -> None:
    assert review_prompt.review_gates_block([]) == ""


# --- 職權劃分：卡面欄位＝應然、event log＝實然（DEV-REVIEW-INDEP-FIELD1） ---
def _write_gate_card(root: Path, field_value: str | None) -> None:
    path = root / "docs" / "tasks" / "CARD-G.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    header = "- 執行：待指派　查核：待指派（≠ 執行）"
    if field_value is not None:
        header += f"\n- review_independence: {field_value}"
    path.write_text(f"# CARD-G 卡\n\n{header}\n\n## 驗收條件\n\n- [ ] x\n", encoding="utf-8")


def test_field_declaring_multiple_gates_does_not_block_without_events(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """宣告 N>1 關但本輪無中繼關卡事件：照登、**不擋**（欄位是宣告不是保證）。"""
    _write_gate_card(tmp_path, "[human, cross_family]")
    _prepare(tmp_path, monkeypatch, _handoff())
    monkeypatch.setattr(review_prompt, "changed_paths", lambda _sha: (["scripts/x.py"], None))

    prompt = review_prompt.build_prompt("CARD-G")

    assert "卡面宣告 2 關：人工審 → 跨家族" in prompt
    assert "尚無任何 review 事件" in prompt
    assert "### 本輪已通過的中繼關卡" not in prompt   # 不因宣告而虛構關卡


def test_guard_verdict_is_unaffected_by_the_card_field(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """守衛只看 event log：同一組事件下，卡面欄位不論宣告幾關，放行判定逐字相同。"""
    _prepare(tmp_path, monkeypatch, _handoff(), _review(2))

    verdicts = []
    for field_value in (None, "[context]", "[human, cross_family]"):
        _write_gate_card(tmp_path, field_value)
        with pytest.raises(SystemExit) as exc:
            review_prompt.latest_handoff("CARD-G")
        verdicts.append(str(exc.value))

    assert len(set(verdicts)) == 1
    assert "review_independence" not in verdicts[0]


def test_interim_event_without_field_declaration_still_passes_through(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """反向：欄位宣告單一關卡、事件卻有中繼關卡時，以事件為實然放行（不被欄位否決）。"""
    _write_gate_card(tmp_path, "[context]")
    _prepare(tmp_path, monkeypatch, _handoff(),
             _review(2, closes_review_round=False, actor="ruan6047（人工審）"))

    _, gates = review_prompt.latest_handoff("CARD-G")

    assert [g["event_id"] for g in gates] == ["CARD-G-REVIEW-002"]
