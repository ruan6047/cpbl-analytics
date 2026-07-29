import importlib.util
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


# --- 獨立性取較嚴者（DEV-REVIEW-PROMPT-GUARD1 缺陷 3） ---
def _write_indep_card(root: Path, review_field: str | None, body: str = "") -> None:
    path = root / "docs" / "tasks" / "CARD-I.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    header = "- 執行：待指派（建議 L2）"
    if review_field is not None:
        header += f"　查核：{review_field}"
    path.write_text(f"# CARD-I 卡\n\n{header}\n\n## 驗收條件\n\n- [ ] x\n{body}\n",
                    encoding="utf-8")


def test_independence_card_face_beats_looser_tier(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """UX-ENTITY-LINKS2 的實況：T2 但卡面寫「跨家族或人工」，須取卡面。"""
    _write_indep_card(tmp_path, "待指派（≠ 執行；跨家族或人工）")
    monkeypatch.setattr(review_prompt, "ROOT", tmp_path)

    summary, detail = review_prompt.independence("CARD-I", "T2")

    assert "跨模型家族" in summary
    assert "新 context" not in summary
    assert "`待指派（≠ 執行；跨家族或人工）`" in detail   # 卡面原文原樣附上
    assert "tier 推導（T2）" in detail                    # 推導過程可覆核


def test_independence_tier_beats_looser_card_face(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """反向：卡面沒寫強化要求時，T4 的跨家族要求不得被卡面稀釋。"""
    _write_indep_card(tmp_path, "待指派（≠ 執行）")
    monkeypatch.setattr(review_prompt, "ROOT", tmp_path)

    summary, _ = review_prompt.independence("CARD-I", "T4")

    assert "跨模型家族" in summary


def test_independence_card_face_human_only_is_strictest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_indep_card(tmp_path, "ruan6047（需求方人工審）")
    monkeypatch.setattr(review_prompt, "ROOT", tmp_path)

    summary, _ = review_prompt.independence("CARD-I", "T2")

    assert summary == "人工（需求方本人）"


def test_independence_missing_field_warns_instead_of_silently_relaxing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_indep_card(tmp_path, None)
    monkeypatch.setattr(review_prompt, "ROOT", tmp_path)

    _, detail = review_prompt.independence("CARD-I", "T2")

    assert "未找到" in detail
    assert "別讓工具替你放寬要求" in detail
    assert "找不到〈查核〉欄" in capsys.readouterr().err


def test_independence_unrecognised_field_keeps_verbatim_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """辨識不到的寫法不得被靜默吃掉——原文照登，交給人判斷。"""
    _write_indep_card(tmp_path, "待指派（須由熟悉 TrackMan 的人接）")
    monkeypatch.setattr(review_prompt, "ROOT", tmp_path)

    _, detail = review_prompt.independence("CARD-I", "T2")

    assert "熟悉 TrackMan 的人接" in detail
    assert "以卡面為準" in detail


def test_independence_flags_cross_family_written_only_in_body(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """欄位沒寫、正文寫了（UX-ENTITY-LINKS2 L40 的實況）→ 附提示要人確認。"""
    _write_indep_card(tmp_path, "待指派（≠ 執行）",
                      body="\n- [ ] **先本地人工審再交跨家族查核**。\n")
    monkeypatch.setattr(review_prompt, "ROOT", tmp_path)

    _, detail = review_prompt.independence("CARD-I", "T2")

    assert "卡片正文另提到跨家族" in detail
    assert "先本地人工審再交跨家族查核" in detail


# --- REVIEW-005 的三項退回（iteration 1） ---
def test_repro_shell_script_is_not_treated_as_docs(monkeypatch: pytest.MonkeyPatch) -> None:
    """F1 blocking：可執行變更被說成「純文件／沒有標準重現指令」比不給指令更糟。"""
    out = _repro(monkeypatch, ["scripts/scrape-daily.sh"])

    assert "純文件" not in out
    assert "無法判定" in out
    assert "uv run pytest" not in out and "npm ci" not in out


@pytest.mark.parametrize(
    "path", ["scripts/scrape-daily.sh", "Dockerfile", ".github/workflows/ci.yml",
             "docker-compose.yml", "data/fixtures.csv"],
)
def test_repro_unknown_kinds_never_get_a_default_command(
    monkeypatch: pytest.MonkeyPatch, path: str
) -> None:
    out = _repro(monkeypatch, [path])

    assert "無法判定" in out and path in out
    assert "uv run pytest" not in out and "npm ci" not in out


def test_repro_unknown_paths_surface_next_to_recognised_ones(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """未知路徑旁邊有 Python 改動時同樣要被講出來，不得被指令區塊蓋過去。"""
    out = _repro(monkeypatch, ["src/cpbl/api/main.py", "Dockerfile", ".github/workflows/ci.yml"])

    assert "uv run pytest -q" in out                    # 認得的那部分照常給指令
    assert "不在自動判定範圍" in out                     # 認不得的那部分照樣吵
    assert "Dockerfile" in out and ".github/workflows/ci.yml" in out


def test_repro_docs_only_uses_extension_allowlist(monkeypatch: pytest.MonkeyPatch) -> None:
    out = _repro(monkeypatch, ["docs/AI_RUNBOOK.md", "README.md"])

    assert "純文件卡" in out and "沒有標準重現指令" in out
    assert "無法判定" not in out


def test_independence_composite_and_is_not_downgraded_to_either_or(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """F2 blocking：「先跨家族查核，並由需求方人工核可」曾被讀成「跨家族或人工」。"""
    _write_indep_card(tmp_path, "先跨家族查核，並由需求方人工核可")
    monkeypatch.setattr(review_prompt, "ROOT", tmp_path)

    summary, detail = review_prompt.independence("CARD-I", "T2")

    assert "且" in summary and "兩者皆須" in summary
    assert summary != "跨模型家族（非執行者所屬家族）或人工"
    assert "無法判定是二擇一還是兩者皆須" in detail   # 明講腳本沒在推斷
    assert "以卡面原文為準" in detail


@pytest.mark.parametrize(
    "field",
    ["待指派（≠ 執行；跨家族或人工）",
     "待指派（≠ 執行；**跨模型家族或人工**——本卡有統計紅線）",
     "待指派（人工或跨家族皆可）"],
)
def test_independence_explicit_or_stays_either_or(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, field: str
) -> None:
    """明寫「或」的既有寫法不得被誤升為 AND——只可升不可降不是「一律往上猜」。"""
    _write_indep_card(tmp_path, field)
    monkeypatch.setattr(review_prompt, "ROOT", tmp_path)

    summary, _ = review_prompt.independence("CARD-I", "T2")

    assert summary == "跨模型家族（非執行者所屬家族）或人工"


def test_independence_body_hint_is_clipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """F3 minor：提示是指路標不是引文轉載，整行照登會稀釋旁邊真正該讀的字。"""
    long_line = "- [ ] " + "描述另一張卡的問題時提到先本地人工審再交跨家族查核" * 6
    _write_indep_card(tmp_path, "待指派（≠ 執行）", body=f"\n{long_line}\n")
    monkeypatch.setattr(review_prompt, "ROOT", tmp_path)

    _, detail = review_prompt.independence("CARD-I", "T2")

    hint = next(line for line in detail.splitlines() if "卡片正文另提到跨家族" in line)
    assert "…" in hint
    assert len(hint) < len(long_line)


def test_independence_body_hint_absent_when_already_strict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """已經是跨家族時不再重複提示，避免雜訊淹沒真正需要看的那行。"""
    _write_indep_card(tmp_path, "待指派（跨家族或人工）",
                      body="\n- [ ] 交跨家族查核。\n")
    monkeypatch.setattr(review_prompt, "ROOT", tmp_path)

    _, detail = review_prompt.independence("CARD-I", "T2")

    assert "卡片正文另提到跨家族" not in detail

