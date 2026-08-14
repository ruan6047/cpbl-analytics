"""`scripts/roadmap_lines.py` 的行為斷言（不需 DB、不需網路）。

釘住的是 **fail-closed 性質本身**：未歸屬、重複、marker 不成對、區塊內出現非標準
卡片列——四種情形一律失敗。`R1-03` 的病是「宣稱可重現而工具不存在」，這裡的反面是
「工具存在但預設放行」，同樣沒有守住任何東西，故每一條 fail 路徑都要有測試。

> **v5 的測試重整**：`v1`–`v4` 靠 markdown 結構定位 §3，故有一組測試在釘圍籬長度、
> 巢狀圍籬、重複節標題等 markdown 邊界情形。`v5` 改用 marker 界定後**那層機制不存在了**，
> 對應的測試一併移除——它們保護的不變量（歧義即失敗）由本檔的 marker 成對性測試承接。
> 移除的是對已刪機制的斷言，不是放寬對現存行為的要求。
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


def _row(cid: str, num: int = 1, tier: str = "T2", status: str = "💡需求",
         gate: str | None = None, keep: str = "") -> str:
    """產生一列符合欄位契約的卡片列（六欄）。`gate` 省略時由 `gate_of` 導出。"""
    g = rl.gate_of(cid, status) if gate is None else gate
    return f"| `{cid}` | #{num} | {tier} | {status} | {g} | {keep} |"


def _blk(*rows: str) -> str:
    """把行包進最小的排程區塊。前後刻意放會干擾 markdown 結構解析的內容——
    這些在 v4 以前都會出事，v5 之後應完全無害。"""
    noise_before = ["# 藍圖", "", "## 3. 現行排程", "", "````markdown", "```",
                    "## 3. 假的節", "| `DATA-FENCED1` | #9 |", "````", "",
                    "> | `DATA-QUOTED1` | #9 |", "  | `DATA-INDENT1` | #9 |", ""]
    noise_after = ["", "## 3. 又一個節標題", "", "| `DATA-AFTER1` | #9 |", ""]
    version = f"<!-- {rl.SCHEMA_VERSION}；活卡 0；每線 {{}} -->"
    return "\n".join(noise_before + [rl.MARKER_BEGIN, version] + list(rows)
                     + [rl.MARKER_END] + noise_after)


_VER = f"<!-- {rl.SCHEMA_VERSION}；活卡 0；每線 {{}} -->"


def _item(card_id: str, status: str = "💡需求", tier: str = "T2", number: int = 1,
          repo: str = "https://github.com/ruan6047/cpbl-analytics") -> dict:
    return {"repository": repo, "卡ID": card_id, "交付狀態": status,
            "級別": tier, "content": {"number": number}}


# --- 歸屬規則 ---

def test_every_line_code_has_a_display_name():
    assert set(rl.LINES) == {"L1", "L2", "L3", "L4", "L5"}
    assert all(name for name in rl.LINES.values())


def test_rules_only_point_at_defined_lines():
    """人工分類表會過期；至少釘住它不會指向不存在的線。"""
    assert set(rl.EXPLICIT_RULES.values()) <= set(rl.LINES)
    assert {line for _, line in rl.PREFIX_RULES} <= set(rl.LINES)


def test_explicit_rule_wins_over_prefix():
    """DEV-VERIFY-TM-ASSERTS1 屬 L1，但前綴會判 L5。"""
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
        _item("DATA-ACTIVE1"),
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


# --- marker 界定（v5 取代 markdown 結構解析） ---

def test_only_rows_inside_the_marker_block_are_read():
    """區塊外的一切都不該被讀到——包含圍籬內的假節、引言列、縮排列、後續章節的表格。

    這一條同時涵蓋 v1–v4 那四輪各自修掉的邊界情形：`_blk()` 的雜訊區就是那些形狀。
    """
    assert rl.cards_in_roadmap(_blk(_row("DATA-REAL1"))) == ["DATA-REAL1"]


@pytest.mark.parametrize("text", [
    "（沒有任何 marker）",
    rl.MARKER_BEGIN + "\n" + _VER + "\n" + _row("DATA-A1"),
    _row("DATA-A1") + "\n" + rl.MARKER_END,
    rl.MARKER_BEGIN + "\n" + rl.MARKER_BEGIN + "\n" + rl.MARKER_END,
    rl.MARKER_BEGIN + "\n" + rl.MARKER_END + "\n" + rl.MARKER_END,
], ids=["兩個都缺", "缺 end", "缺 begin", "begin 兩個", "end 兩個"])
def test_marker_pairing_fails_closed(text):
    """marker 不成對即失敗——回空集會讓「區塊不見了」與「區塊是空的」無法區分。"""
    with pytest.raises(rl.CheckFailed, match="marker 數量不正確"):
        rl.cards_in_roadmap(text)


def test_reversed_markers_fail_closed():
    with pytest.raises(rl.CheckFailed, match="順序顛倒"):
        rl.cards_in_roadmap(rl.MARKER_END + "\n" + _row("DATA-A1") + "\n" + rl.MARKER_BEGIN)


def test_marker_match_is_whole_line_not_substring():
    """內文提到 marker 字串**不得**被當成 marker，因此該行被正常忽略、解析成功。

    比對是整行去空白後的字面相等。若改成部分比對，一句解釋 marker 用途的散文就會
    讓 begin 變成兩個而整份文件失敗——同 `review-marker-literal-quarantines-card`
    的教訓：marker 的管轄要看形狀（是否整行），不是看字串有沒有出現。
    """
    text = ("本節說明 " + rl.MARKER_BEGIN + " 這個標記的用途。\n"
            + rl.MARKER_BEGIN + "\n" + _VER + "\n" + _row("DATA-A1") + "\n" + rl.MARKER_END)
    assert rl.cards_in_roadmap(text) == ["DATA-A1"]


@pytest.mark.parametrize("row", [
    "  | `DATA-INDENT2` | #1 |",
    "> | `DATA-QUOTED2` | #1 |",
    ">   | `DATA-BOTH2` | #1 |",
    "\t| `DATA-TAB2` | #1 |",
])
def test_indented_or_quoted_rows_inside_the_block_fail_closed(row):
    """`R1-002`：靜默忽略的方向與 fail-closed 相反。區塊由指令產生，
    出現這種形狀代表有人手改過而且改壞了。"""
    with pytest.raises(rl.CheckFailed, match="縮排或帶引言符號"):
        rl.cards_in_roadmap(_blk(row))


def test_prose_and_table_headers_inside_the_block_do_not_trigger():
    """收窄不得矯枉過正：表頭、分隔列、內文提及卡 ID 都不是卡片列，也不該失敗。"""
    assert rl.cards_in_roadmap(_blk(
        "| 卡 | # | tier |", "|---|---|---|",
        "本區塊由指令產生，勿手改；`DATA-MENTION1` 只是內文提及。",
        _row("DATA-REAL2"),
    )) == ["DATA-REAL2"]


# --- 對帳 ---

def test_reconcile_detects_both_directions():
    result = rl.assign([{"card_id": "DATA-A1", "tier": "T2", "status": "💡需求", "number": 1}])

    rl.reconcile(result, _blk(_row("DATA-A1")))

    with pytest.raises(rl.CheckFailed, match="只在 Project"):
        rl.reconcile(result, _blk("（區塊是空的）"))
    with pytest.raises(rl.CheckFailed, match="只在 ROADMAP"):
        rl.reconcile(result, _blk(_row("DATA-A1"), _row("DATA-GHOST1", 2)))


def test_duplicate_row_inside_the_block_fails():
    result = rl.assign([{"card_id": "DATA-A1", "tier": "T2", "status": "💡需求", "number": 1}])
    with pytest.raises(rl.CheckFailed, match="區塊內卡 ID 重複"):
        rl.reconcile(result, _blk(_row("DATA-A1"), _row("DATA-A1")))


# --- 產出 ---

def test_render_is_wrapped_in_markers_and_round_trips():
    """`render()` 的輸出必須能被 `cards_in_roadmap()` 讀回來——產生端與消費端同一份契約。"""
    result = rl.assign([
        {"card_id": "DATA-A1", "tier": "T2", "status": "💡需求", "number": 1},
        {"card_id": "UX-B1", "tier": "T3", "status": "🔍待查核", "number": 2},
    ])
    out = rl.render(result)
    assert out.splitlines()[0].strip() == rl.MARKER_BEGIN
    assert out.splitlines()[-1].strip() == rl.MARKER_END
    assert sorted(rl.cards_in_roadmap(out)) == ["DATA-A1", "UX-B1"]


def test_schema_version_is_emitted_and_bumped():
    """解析規則改了而版本沒動，兩次執行的輸出就無法區分——那正是 R1-03 的病。"""
    result = rl.assign([{"card_id": "DATA-A1", "tier": "T2", "status": "💡需求", "number": 1}])
    assert result["schema_version"] == rl.SCHEMA_VERSION
    assert rl.SCHEMA_VERSION == "cpbl-roadmap-lines/v6"


# --- v6：自審補上的三層檢查 ---

def _res(*cards):
    return rl.assign([{"card_id": c, "tier": "T2", "status": "💡需求", "number": i + 1}
                      for i, c in enumerate(cards)])


def test_block_version_must_match_current():
    """v5 把版本寫進區塊卻從不比對，於是 v1 產生的區塊照樣通過 v5 的檢查。"""
    res = _res("DATA-A1")
    blk = rl.render(res)
    rl.reconcile(res, blk)                                   # 基準
    stale = blk.replace(rl.SCHEMA_VERSION, "cpbl-roadmap-lines/v1")
    with pytest.raises(rl.CheckFailed, match="判定規則已變更"):
        rl.reconcile(res, stale)


def test_missing_version_comment_fails_closed():
    """區塊必須自陳由哪一版產生——缺了就無從判斷比對結果有沒有意義。"""
    res = _res("DATA-A1")
    blk = "\n".join(ln for ln in rl.render(res).splitlines()
                    if not ln.startswith("<!-- cpbl-roadmap-lines/"))
    with pytest.raises(rl.CheckFailed, match="找不到版本註解"):
        rl.reconcile(res, blk)


@pytest.mark.parametrize("old,new,col", [
    ("| T2 |", "| T4 |", "tier"),
    ("💡需求", "🏁完成", "狀態"),
    ("| #1 |", "| #99 |", "#"),
])
def test_machine_columns_drift_is_caught(old, new, col):
    """v5 只比對卡 ID，於是這三種竄改全部靜默通過，而 §3 宣稱「本表由指令產生」。"""
    res = _res("DATA-A1")
    with pytest.raises(rl.CheckFailed, match="機器產生欄與 Project 現值不符"):
        rl.reconcile(res, rl.render(res).replace(old, new, 1))


def test_human_column_is_passed_through():
    """`去留` 由需求方手填，比對必須放行——否則每次重跑都會洗掉裁決。"""
    res = _res("DATA-A1")
    filled = rl.render(res).replace("| |", "| 繼續，需求方 2026-08-14 |")
    rl.reconcile(res, filled)


def test_wrong_cell_count_fails_closed():
    """欄數不符即失敗——否則逐欄比對會靜默略過該列，又回到只守一維。"""
    with pytest.raises(rl.CheckFailed, match="欄數為"):
        rl.cards_in_roadmap(_blk("| `DATA-A1` | #1 |"))


def test_exact_field_name_wins_over_suffix():
    """後綴比對可被同尾欄位遮蔽（實測：加「外部ID」會搶走卡 ID）。故先精確。"""
    item = {"repository": "https://github.com/ruan6047/cpbl-analytics",
            "交付狀態": "💡需求", "外部ID": "WRONG-ID", "卡ID": "DATA-A1",
            "級別": "T2", "content": {"number": 1}}
    assert rl.active_cards({"items": [item]})[0]["card_id"] == "DATA-A1"


def test_ambiguous_suffix_fails_closed_when_exact_name_is_unavailable():
    """`gh` 回來的 key 前綴會壞掉，精確名取不到；此時多個同尾 key 一律失敗。"""
    item = {"repository": "https://github.com/ruan6047/cpbl-analytics",
            "�付狀態": "💡需求", "外部ID": "WRONG-ID", "�ID": "DATA-A1",
            "�別": "T2", "content": {"number": 1}}
    with pytest.raises(rl.CheckFailed, match="命中 2 個 key"):
        rl.active_cards({"items": [item]})
