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

