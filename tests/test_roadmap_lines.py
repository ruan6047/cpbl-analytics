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


def _s3(*rows: str) -> str:
    """把表格列包進最小的 §3 區間——解析已限定在該區間內（R2-002）。"""
    return "## 3. 現行排程\n\n" + "\n".join(rows) + "\n\n## 4. 下一節\n"


def test_reconcile_detects_both_directions():
    result = rl.assign([{"card_id": "DATA-A1", "tier": "T2", "status": "💡需求", "number": 1}])

    rl.reconcile(result, _s3("| `DATA-A1` | #1 | T2 | 💡需求 | | |"))

    with pytest.raises(rl.CheckFailed, match="只在 Project"):
        rl.reconcile(result, _s3("（表是空的）"))
    with pytest.raises(rl.CheckFailed, match="只在 ROADMAP"):
        rl.reconcile(result, _s3("| `DATA-A1` | #1 | T2 | 💡需求 | | |",
                                 "| `DATA-GHOST1` | #2 | T2 | 💡需求 | | |"))


def test_card_ids_are_read_only_from_table_rows():
    """行內 code（例如內文提到 `DATA-X1`）不得被誤讀成表格列。"""
    text = _s3("內文提到 `DATA-GHOST1` 但那不是表格列。",
               "| `DATA-A1` | #1 | T2 | 💡需求 | | |")
    assert rl.cards_in_roadmap(text) == ["DATA-A1"]


def test_schema_version_is_emitted():
    """判定規則改了而版本沒動，兩次輸出就無法區分——那正是 R1-03 的病。"""
    result = rl.assign([{"card_id": "DATA-A1", "tier": "T2", "status": "💡需求", "number": 1}])
    assert result["schema_version"] == rl.SCHEMA_VERSION
    assert rl.SCHEMA_VERSION.startswith("cpbl-roadmap-lines/")


# --- R2-002：解析必須限定在 §3 區間內 ---

_DOC = """# 藍圖

## 0. 目標排序

| `DATA-OUTSIDE1` | 這一列在 §3 之外 |

## 3. 現行排程

### L1

| 卡 | # |
|---|---|
| `DATA-INSIDE1` | #1 |

## 4. 驗收政策

| `DATA-AFTER1` | 這一列在 §3 之後 |
"""


def test_only_section3_rows_are_read():
    """§3 以外的合法卡 ID 表格列必須被忽略——前一版對全檔套 regex，實測會假失敗。"""
    assert rl.cards_in_roadmap(_DOC) == ["DATA-INSIDE1"]


def test_section3_slice_stops_at_next_same_level_heading():
    """區間止於下一個 `##`，不吃到 §4。"""
    body = "\n".join(rl.section3_lines(_DOC))
    assert "DATA-INSIDE1" in body
    assert "DATA-AFTER1" not in body and "DATA-OUTSIDE1" not in body


def test_subheadings_inside_section3_do_not_end_the_slice():
    """§3 內的 `###` 小節（L1～L5）不得被當成區間結束。"""
    assert "### L1" in "\n".join(rl.section3_lines(_DOC))


def test_missing_section3_fails_closed():
    """找不到 §3 標題要失敗，不得靜默回空集——空集會讓「§3 不見了」與「§3 是空的」無法區分。"""
    with pytest.raises(rl.CheckFailed, match="找不到 §3 節標題"):
        rl.cards_in_roadmap("# 藍圖\n\n## 4. 驗收政策\n\n| `DATA-X1` | #1 |")


def test_reconcile_ignores_rows_outside_section3():
    """端到端：§3 外的幽靈列不得造成 only-in-ROADMAP 假失敗。"""
    result = rl.assign([{"card_id": "DATA-INSIDE1", "tier": "T2", "status": "💡需求", "number": 1}])
    rl.reconcile(result, _DOC)


def test_schema_version_bumped_for_the_parsing_change():
    """解析規則變了，版本必須跟著動——否則兩次執行的輸出無法區分。"""
    assert rl.SCHEMA_VERSION == "cpbl-roadmap-lines/v2"
