"""`scripts/roadmap_lines.py` 的行為斷言（不需 DB、不需網路）。

釘住的是 fail-closed 性質本身：**未歸屬、重複、與 ROADMAP 對不上** 三種情形一律失敗。
R1-03 的病是「宣稱可重現而工具不存在」，這裡的反面是「工具存在但預設放行」——
同樣沒有守住任何東西，故每一條 fail 路徑都要有測試。
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "roadmap_lines", Path(__file__).resolve().parents[1] / "scripts" / "roadmap_lines.py"
)
assert _SPEC is not None and _SPEC.loader is not None
rl = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(rl)


def _item(card_id: str, status: str = "💡需求", tier: str = "T2", number: int = 1,
          repo: str = "https://github.com/ruan6047/cpbl-analytics") -> dict:
    return {"repository": repo, "卡ID": card_id, "交付狀態": status,
            "級別": tier, "content": {"number": number}}


def test_every_line_code_has_a_display_name():
    """線代號與對外名稱必須一一對應，否則 §3 標題會對不上。"""
    assert set(rl.LINES) == {"L1", "L2", "L3", "L4", "L5"}
    assert all(name for name in rl.LINES.values())


def test_explicit_rules_only_point_at_defined_lines():
    """人工分類表會過期；至少釘住它不會指向不存在的線。"""
    assert set(rl.EXPLICIT_RULES.values()) <= set(rl.LINES)
    assert {line for _, line in rl.PREFIX_RULES} <= set(rl.LINES)


def test_explicit_rule_wins_over_prefix():
    """MATCHUP-DATA2 以 DATA- 起頭但實際屬 L1；DEV-VERIFY-TM-ASSERTS1 亦然（前綴會判 L5）。"""
    assert rl.line_of("DEV-VERIFY-TM-ASSERTS1") == "L1"
    assert rl.line_of("DEV-CI-LOCALE-UNDECLARED1") == "L5"


def test_unknown_prefix_is_not_silently_defaulted():
    """判不出來要回 None，讓呼叫端 fail closed——不得落進任何預設線。"""
    assert rl.line_of("ZZZ-SOMETHING-NEW1") is None


def test_unassigned_card_fails_closed():
    with pytest.raises(rl.CheckFailed, match="無法歸入任何一條線"):
        rl.assign([{"card_id": "ZZZ-NEW1", "tier": "T2", "status": "💡需求", "number": 9}])


def test_duplicate_card_id_fails():
    card = {"card_id": "DATA-X1", "tier": "T2", "status": "💡需求", "number": 1}
    with pytest.raises(rl.CheckFailed, match="重複"):
        rl.assign([card, dict(card)])


def test_closed_statuses_are_excluded_and_other_repos_ignored():
    payload = {"items": [
        _item("DATA-ACTIVE1", status="💡需求"),
        _item("DATA-DONE1", status="🏁完成"),
        _item("DATA-STOPPED1", status="🛑已停止"),
        _item("DATA-MERGED1", status="📦已合併"),
        _item("WF-OTHER1", repo="https://github.com/ruan6047/ai-workflow"),
    ]}
    assert [c["card_id"] for c in rl.active_cards(payload)] == ["DATA-ACTIVE1"]


def test_active_card_without_card_id_fails_closed():
    payload = {"items": [{"repository": "https://github.com/ruan6047/cpbl-analytics",
                          "交付狀態": "💡需求", "content": {"number": 7}}]}
    with pytest.raises(rl.CheckFailed, match="缺卡ID"):
        rl.active_cards(payload)


def test_reconcile_detects_both_directions():
    result = rl.assign([{"card_id": "DATA-A1", "tier": "T2", "status": "💡需求", "number": 1}])

    rl.reconcile(result, "| `DATA-A1` | #1 | T2 | 💡需求 | | |")

    with pytest.raises(rl.CheckFailed, match="只在 Project"):
        rl.reconcile(result, "（表是空的）")
    with pytest.raises(rl.CheckFailed, match="只在 ROADMAP"):
        rl.reconcile(result, "| `DATA-A1` | #1 | T2 | 💡需求 | | |\n| `DATA-GHOST1` | #2 | T2 | 💡需求 | | |")


def test_card_ids_are_read_only_from_table_rows():
    """行內 code（例如內文提到 `DATA-X1`）不得被誤讀成表格列。"""
    text = "內文提到 `DATA-GHOST1` 但那不是表格列。\n| `DATA-A1` | #1 | T2 | 💡需求 | | |"
    assert rl.cards_in_roadmap(text) == ["DATA-A1"]


def test_schema_version_is_emitted():
    """判定規則改了而版本沒動，兩次輸出就無法區分——那正是 R1-03 的病。"""
    result = rl.assign([{"card_id": "DATA-A1", "tier": "T2", "status": "💡需求", "number": 1}])
    assert result["schema_version"] == rl.SCHEMA_VERSION
    assert rl.SCHEMA_VERSION.startswith("cpbl-roadmap-lines/")
