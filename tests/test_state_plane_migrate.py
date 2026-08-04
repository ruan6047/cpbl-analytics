"""OPS-STATE-PLANE-MIG1 Task 2：state_plane_migrate.py 的最小單元測試。

全部針對純函式（Ledger table 解析、卡面欄位抽取、mutation 字串組裝），零網路呼叫、
零 `gh`／`git` 依賴，可在任何環境（含 CI）跑。真正呼叫 GitHub API 的部分
（`create_issue`／`add_item_to_project`／`graphql` 等）刻意不測試——那是整合行為，
已由 2026-08-04 的 dry-run（39 卡零例外）與單卡試跑（見對帳表）覆蓋。
"""

import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPT_PATH = Path(__file__).parents[1] / "scripts" / "state_plane_migrate.py"
SPEC = importlib.util.spec_from_file_location("state_plane_migrate", SCRIPT_PATH)
assert SPEC and SPEC.loader
m = importlib.util.module_from_spec(SPEC)
# 腳本用了 `from __future__ import annotations` + `@dataclass`：dataclasses 內部解析
# 型別註記時會找 `sys.modules[cls.__module__]`，動態載入的模組不先掛進 sys.modules
# 就會是 None 而炸掉（AttributeError: 'NoneType' object has no attribute '__dict__'）。
sys.modules[SPEC.name] = m
SPEC.loader.exec_module(m)


SAMPLE_LEDGER = """\
# 任務看板

## Ledger 總表（活卡）

| 卡ID | Initiative | 級別 | 功能 | owner | 分支／worktree | iteration | 交付狀態 | 部署狀態 | 最後交接 |
|---|---|---|---|---|---|---|---|---|---|
| [CARD-A](tasks/CARD-A.md) | WF-22 | T3 | 測試卡 A | 待指派 | — | 0 | 📥Backlog | —不適用 | 2026-08-04T10:00:00+08:00 |
| [CARD-B](tasks/CARD-B.md) | — | T4 | 測試卡 B | ruan6047 | `ai/x/CARD-B @ wt` | 2 | 🚧執行中 | ⏸未部署 | 2026-08-04T11:00:00+08:00 |

## 依賴與資源註記

- 這行不應被當成卡片列解析。
"""


def test_parse_ledger_extracts_only_card_rows() -> None:
    rows = m.parse_ledger(SAMPLE_LEDGER)
    assert [r.card_id for r in rows] == ["CARD-A", "CARD-B"]
    assert rows[0].tier == "T3"
    assert rows[0].delivery_status == "📥Backlog"
    assert rows[1].branch_worktree == "`ai/x/CARD-B @ wt`"
    assert rows[1].iteration == "2"


def test_parse_ledger_skips_header_and_separator_and_notes() -> None:
    rows = m.parse_ledger(SAMPLE_LEDGER)
    assert len(rows) == 2  # 表頭、分隔線、依賴註記段落皆不應被誤判為卡片列


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("- DB：`db_scope: none`（不碰資料庫）", "none"),
        ("- DB：`db_scope: write`（實作階段）", "write"),
        ("- DB：`none`", "none"),
        ("沒有 DB 行的卡面全文", None),
    ],
)
def test_extract_db_scope(text: str, expected: str | None) -> None:
    assert m.extract_db_scope(text) == expected


def test_extract_resources_only_reads_labelled_line() -> None:
    text = (
        "- 分支：`ai/x/CARD-A`　資源：`file:scripts/a.py`、`file:docs/b.md`\n"
        "本段敘述提到 `file:scripts/unrelated.py` 但不在資源：標籤後，不應被誤收。\n"
    )
    assert m.extract_resources(text) == ["file:scripts/a.py", "file:docs/b.md"]


def test_extract_resources_empty_when_no_label() -> None:
    assert m.extract_resources("完全沒有資源宣告的卡面文字") == []


def test_extract_original_goal() -> None:
    text = "- 服務的原始目標：消除「示例痛點」（根因一）"
    assert m.extract_original_goal(text) == "消除「示例痛點」（根因一）"


def test_extract_original_goal_absent() -> None:
    assert m.extract_original_goal("沒有這個欄位的卡面") is None


def test_extract_chain_depth_only_matches_labelled_bullet() -> None:
    assert m.extract_chain_depth("- 鏈深：2") == 2
    # 決議規則文字裡提到「鏈深」但不是欄位值，不應誤判
    prose = "鏈深硬上限＝原始目標之下 2 層；如鏈深入 body 結構化區塊"
    assert m.extract_chain_depth(prose) is None


def test_validate_row_options_accepts_known_variant_strings() -> None:
    row = m.LedgerRow(
        card_id="X", initiative="—", tier="T3", feature="f", owner="o",
        branch_worktree="—", iteration="0", delivery_status="🚧執行中",
        deploy_status="⏸未部署", last_handoff="2026-08-04T00:00:00+08:00",
    )
    assert m.validate_row_options(row) == []


def test_validate_row_options_flags_unknown_value() -> None:
    row = m.LedgerRow(
        card_id="X", initiative="—", tier="T99", feature="f", owner="o",
        branch_worktree="—", iteration="0", delivery_status="👽未知狀態",
        deploy_status="—不適用", last_handoff="2026-08-04T00:00:00+08:00",
    )
    problems = m.validate_row_options(row)
    assert any("級別" in p for p in problems)
    assert any("交付狀態" in p for p in problems)


def _sample_field_defs() -> dict:
    def sel(name: str, options: list[str]) -> dict:
        return {"id": f"FID_{name}", "options": [{"id": f"OPT_{o}", "name": o} for o in options]}

    return {
        "卡ID": {"id": "FID_card"},
        "Initiative": {"id": "FID_init"},
        "級別": sel("級別", m.TIER_OPTIONS),
        "功能": {"id": "FID_feature"},
        "owner": {"id": "FID_owner"},
        "分支／worktree": {"id": "FID_bw"},
        "iteration": {"id": "FID_iter"},
        "交付狀態": sel("交付狀態", m.DELIVERY_STATUS_OPTIONS),
        "部署狀態": sel("部署狀態", m.DEPLOY_STATUS_OPTIONS),
        "最後交接": {"id": "FID_lh"},
        "服務的原始目標": {"id": "FID_goal"},
        "鏈深": {"id": "FID_depth"},
    }


def _sample_row() -> "m.LedgerRow":
    return m.LedgerRow(
        card_id="CARD-A", initiative="WF-22", tier="T3", feature="測試",
        owner="待指派", branch_worktree="—", iteration="0",
        delivery_status="📥Backlog", deploy_status="—不適用",
        last_handoff="2026-08-04T10:00:00+08:00",
    )


def test_build_field_mutations_omits_chain_depth_when_unclassified() -> None:
    mutations = m.build_field_mutations(
        "PID", "ITEM", _sample_field_defs(), _sample_row(), None, None,
    )
    joined = "\n".join(mutations)
    assert "chainDepth" not in joined  # 未分類時完全不寫入該欄位，不用 -1／0 佔位
    assert '"未填寫（本卡於新制欄位定案前建立，2026-08-04）"' in joined


def test_build_field_mutations_includes_chain_depth_when_known() -> None:
    mutations = m.build_field_mutations(
        "PID", "ITEM", _sample_field_defs(), _sample_row(), "真實原始目標", 1,
    )
    joined = "\n".join(mutations)
    assert "chainDepth" in joined
    assert "number: 1" in joined
    assert "真實原始目標" in joined


def test_build_field_mutations_raises_on_unknown_select_value() -> None:
    bad_row = _sample_row()
    bad_row.tier = "T99"
    with pytest.raises(m.MigrationError):
        m.build_field_mutations("PID", "ITEM", _sample_field_defs(), bad_row, None, None)


def test_build_issue_body_contains_marker_and_resource_json() -> None:
    card_text = (
        "- DB：`db_scope: read`\n"
        "- 分支：`ai/x/CARD-A`　資源：`file:scripts/a.py`\n"
    )
    body = m.build_issue_body(_sample_row(), card_text, "a" * 40)
    assert "<!-- state-plane-mig1:card_id=CARD-A -->" in body
    assert '"db_scope": "read"' in body
    assert '"file:scripts/a.py"' in body
    assert "未分類（決議 5 剛定案，尚未逐卡分類；非 0）" in body


def test_build_issue_title() -> None:
    assert m.build_issue_title(_sample_row()) == "CARD-A：測試"
