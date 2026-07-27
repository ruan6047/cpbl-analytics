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


def test_cal1_band_figures_are_consistent():
    """§6.4 的質性對照表引用了 CAL1 局帶數字；它必須與 generated:cal1_contrast 同源。

    iteration 5 發現 §4.3 引 isotonic（−2.41pt）而 §6.4 引 beta（≈2.6pt），兩處各引一個
    校準器且都沒說明——本測試把「表格未產生」的例外收斂成「數字仍須一致」。
    """
    gen = _generator()
    _, iso_pt = gen.cal1_band_contrast()
    figure = f"{iso_pt:+.2f}".replace("-", "−") + "pt"
    report = REPORT.read_text(encoding="utf-8")
    section = report[report.index("## §6.4") if "## §6.4" in report
                     else report.index("### 6.4"):]
    assert figure in section, f"§6.4 未引用與 artifact 一致的 CAL1 局帶偏差 {figure}"


def test_generator_detects_a_stale_number():
    """反向驗證：手改一個數字後測試必須紅，否則這道守衛是擺設。"""
    gen = _generator()
    artifact = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    tampered = gen.apply(REPORT.read_text(encoding="utf-8"), gen.render(artifact))
    n_games = artifact["population"]["n_games"]
    tampered = tampered.replace(f"**{n_games:,} 場**", f"**{n_games + 1:,} 場**", 1)
    with pytest.raises(AssertionError):
        assert tampered == gen.apply(tampered, gen.render(artifact))
