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

