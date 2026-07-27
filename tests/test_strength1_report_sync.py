"""報告數字必須與 canonical artifact 同步（iteration 3 查核 F2）。

本卡四輪查核中三次是執行者人工謄寫數字後宣稱「已全數對帳」，實際共 8 處過期。
人工對帳在這條線上的失敗率是實測的，故改為結構保證：報告的數字區塊由
`scripts/strength1_report_tables.py` 從 artifact 產生，本測試釘住兩者同步——
artifact 重跑而忘了重新產生報告，這裡就會紅。
"""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/strength1_report_tables.py"
ARTIFACT = ROOT / "docs/research/game_recap_wp_strength1_metrics.json"
REPORT = ROOT / "docs/research/GAME-RECAP-WP-STRENGTH1_RESULTS.md"


def _generator():
    spec = importlib.util.spec_from_file_location("strength1_report_tables", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_report_numbers_match_artifact():
    gen = _generator()
    artifact = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    current = REPORT.read_text(encoding="utf-8")
    regenerated = gen.apply(current, gen.render(artifact))
    assert current == regenerated, (
        "報告數字與 artifact 不同步；跑 "
        "`uv run python scripts/strength1_report_tables.py` 重新產生")


def test_every_generated_block_is_present_in_the_report():
    """區塊被整段刪掉時，`apply()` 會報錯——這裡讓它在測試層就被擋下。"""
    gen = _generator()
    current = REPORT.read_text(encoding="utf-8")
    missing = [name for name in gen.BLOCKS
               if f"<!-- generated:{name} start -->" not in current]
    assert not missing, f"報告缺少產生區塊：{missing}"


_SEPARATOR = re.compile(r"^\|[\s:|-]+\|$")


def _tables_outside_generated_blocks(text: str, gen) -> list[str]:
    """報告中所有「不在產生區塊內」的 Markdown 表格**表頭**。

    表頭＝下一行是 `|---|` 分隔列的那一列；以表頭當識別鍵，一張表只需分類一次。
    """
    stripped = text
    for name in gen.BLOCKS:
        pattern = re.compile(
            rf"<!-- generated:{name} start -->.*?<!-- generated:{name} end -->", re.DOTALL)
        stripped = pattern.sub("", stripped)
    lines = stripped.splitlines()
    return [line.strip() for line, nxt in zip(lines, lines[1:], strict=False)
            if line.startswith("|") and _SEPARATOR.match(nxt.strip())]


def test_every_numeric_table_is_accounted_for():
    """完整性守衛：報告裡每一張表格，不是由 artifact 產生，就得在 UNGENERATED_TABLES 列明理由。

    iteration 4 的守衛只驗證既有 `BLOCKS`，於是 §3／§5／§6.3／§7.1 四張表在區塊外過期也照樣
    exit 0——查核者把選型 Brier 改成 0.999999 仍回報「同步」（iteration 4 查核 F1）。
    問題不是漏了幾張表，是量詞方向錯了：原本是「對每個已納管區塊斷言同步」，
    改成「對報告中的每一張表斷言它有歸屬」，新增表格沒分類就紅。
    """
    gen = _generator()
    outside = _tables_outside_generated_blocks(REPORT.read_text(encoding="utf-8"), gen)
    unclassified = [row for row in outside
                    if row.strip() not in gen.UNGENERATED_TABLES]
    assert not unclassified, (
        "下列表格既不在產生區塊內，也未在 UNGENERATED_TABLES 說明為何不需產生：\n"
        + "\n".join(unclassified))


def test_report_does_not_re_judge_the_hard_gates():
    """§5 只能格式化 `verdict.gate_results`，不得自行重新判定（iteration 5 查核 F1）。

    做法：把 artifact 的 gate_results 竄改成「4a 失敗」而不動任何底層數字。報告若仍照
    coverage 自己算一次，就會印成通過——那正是 iteration 5 的缺陷。
    """
    gen = _generator()
    artifact = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    for gate in artifact["verdict"]["gate_results"]:
        if gate["gate"] == "4a":
            gate["passed"] = False
            gate["failures"] = ["（測試注入）A2023 effective coverage 0.500000 < 0.98"]
    row = next(r for r in gen.hard_gate_block(artifact) if r.startswith("| 4a"))
    assert "❌" in row and "測試注入" in row, f"報告未反映 gate_results，實得：{row}"


def test_ungenerated_allowlist_reasons_are_structural():
    """allowlist 的理由必須是可檢查的結構性性質，不得是「已由某測試釘住」這類宣稱。

    iteration 5 用一句未經驗證的宣稱豁免了 §6.4（聲稱唯二數字皆已釘住，實際只釘了一個，
    查核者把另一個改成 +9.99pt 三道檢查全放行）。理由字串本身就是宣稱，會被相信而不被驗證。
    """
    gen = _generator()
    # 豁免理由只能說「這張表結構上不含 artifact 數值」，不能說「另有東西保證它正確」。
    claim_words = ("釘住", "保證", "已驗證", "已對帳")
    for header, reason in gen.UNGENERATED_TABLES.items():
        offending = [w for w in claim_words if w in reason]
        assert not offending, (
            f"{header} 的豁免理由訴諸另一道保證（{offending}），"
            f"那是未經驗證的宣稱而非結構性性質：{reason}")


def test_generator_detects_a_stale_number():
    """反向驗證：手改一個數字後測試必須紅，否則這道守衛是擺設。"""
    gen = _generator()
    artifact = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    tampered = gen.apply(REPORT.read_text(encoding="utf-8"), gen.render(artifact))
    n_games = artifact["population"]["n_games"]
    tampered = tampered.replace(f"**{n_games:,} 場**", f"**{n_games + 1:,} 場**", 1)
    with pytest.raises(AssertionError):
        assert tampered == gen.apply(tampered, gen.render(artifact))
