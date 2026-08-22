"""`scripts/roadmap_lines.py` 的行為斷言（不需 DB、不需網路）。

釘住的是 **fail-closed 性質本身**：未歸屬、重複、marker 不成對、區塊內出現非標準
卡片列——四種情形一律失敗。`R1-03` 的病是「宣稱可重現而工具不存在」，這裡的反面是
「工具存在但預設放行」，同樣沒有守住任何東西，故每一條 fail 路徑都要有測試。

> **v5 的測試重整**：`v1`–`v4` 靠 markdown 結構定位 §3，故有一組測試在釘圍籬長度、
> 巢狀圍籬、重複節標題等 markdown 邊界情形。`v5` 改用 marker 界定後**那層機制不存在了**，
> 對應的測試一併移除——它們保護的不變量（歧義即失敗）由本檔的 marker 成對性測試承接。
> 移除的是對已刪機制的斷言，不是放寬對現存行為的要求。

> **v9 的移除**：`GATE_OVERRIDES` 整張表刪除，故 `test_override_still_wins_for_known_statuses`
> （斷言「覆寫優先於狀態導出」）一併移除——它斷言的是**被刻意刪掉的行為**，留著只能靠
> 放寬來通過。`test_override_card_with_unknown_status_still_fails_closed` 則**不是移除而是
> 擴大**：`CONV-001` 的不變量（未知狀態 fail closed）從「覆寫表裡那一張卡也擋」變成
> 「每一張卡都擋」，見 `test_unknown_status_fails_closed_for_every_card`。端到端那條保留
> 且仍以 `#53`（當初被實測繞過的那張）為對象，另補上 `match` 以免它因無關原因假通過。
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
                          "交付狀態": "💡需求", "級別": "T2", "content": {"number": 7}}]}
    with pytest.raises(rl.CheckFailed, match="缺必填欄位"):
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
    assert rl.SCHEMA_VERSION.startswith("cpbl-roadmap-lines/v")


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


# --- VERIFIER1-R3-001：必填 Project 欄位缺一即 fail closed ---

_REPO = "https://github.com/ruan6047/cpbl-analytics"


def test_missing_status_fails_closed_instead_of_becoming_an_active_card():
    """v6 收為 status='' 並一路通過 render→reconcile——不完整的 payload 被偽裝成排程。

    活卡的判定本身依賴 status；取不到時**無從判斷它是不是活卡**，
    不能以「空字串不在終態集合」推論它是活的。
    """
    payload = {"items": [{"repository": _REPO, "卡ID": "DATA-A1", "級別": "T2",
                          "content": {"number": 1}}]}
    with pytest.raises(rl.CheckFailed, match="取不到交付狀態"):
        rl.active_cards(payload)


@pytest.mark.parametrize("item,missing", [
    ({"卡ID": "DATA-A1", "交付狀態": "💡需求", "級別": "T2"}, "content.number"),
    ({"卡ID": "DATA-A1", "交付狀態": "💡需求", "content": {"number": 1}}, "級別"),
], ids=["缺 content.number", "缺 級別"])
def test_missing_required_fields_fail_closed(item, missing):
    with pytest.raises(rl.CheckFailed, match="缺必填欄位"):
        rl.active_cards({"items": [{"repository": _REPO, **item}]})


def test_round_trip_no_longer_launders_an_incomplete_payload():
    """round-trip 回歸：缺欄位的 payload 不得走完 active_cards → render → reconcile。

    v6 兩條路徑都能走完並回報「一致」——那是本卡最該防的形狀：
    **對帳通過而它比對的東西本身是假的。**
    """
    for broken in (
        {"repository": _REPO, "卡ID": "DATA-A1", "級別": "T2", "content": {"number": 1}},
        {"repository": _REPO, "卡ID": "DATA-A1", "交付狀態": "💡需求", "級別": "T2"},
    ):
        with pytest.raises(rl.CheckFailed):
            res = rl.assign(rl.active_cards({"items": [broken]}))
            rl.reconcile(res, rl.render(res))


def test_unknown_status_is_not_silently_rendered_as_dash():
    """v6 對不認得的狀態靜默導成「—」，於是產生一列看起來正常的表格。"""
    with pytest.raises(rl.CheckFailed, match="不在已知詞彙表"):
        rl.gate_of("DATA-A1", "🆕沒見過的狀態")


def test_closed_statuses_are_still_excluded_before_the_required_check():
    """終態卡不必有完整欄位——它們本來就不進排程表，不該因缺欄位而讓整份失敗。"""
    payload = {"items": [
        {"repository": _REPO, "交付狀態": "🏁完成"},
        {"repository": _REPO, "卡ID": "DATA-A1", "交付狀態": "💡需求", "級別": "T2",
         "content": {"number": 1}},
    ]}
    assert [c["card_id"] for c in rl.active_cards(payload)] == ["DATA-A1"]


# --- v9（DEV-ROADMAP-GATE-DERIVED1）：Gate 欄純由狀態導出，無逐卡例外 ---

#: `v8` 的 `GATE_OVERRIDES` 曾收錄的五張卡。移除後它們**不得**再有專屬 Gate 文字。
#: 列舉出來是為了讓回歸釘在具體對象上——尤其 `INGEST-GAME-TM-REFACTOR1-G4`
#: 正是 `CONV-001` 當初被實測繞過的那一張。
_FORMERLY_OVERRIDDEN = (
    "INGEST-GAME-TM-REFACTOR1-G4",
    "DATA-RE24-PROD-REBUILD1",
    "DATA-BOX-DEEP-SILENT-FAIL1",
    "DATA-BOX-REVISION-SNAPSHOT1",
    "UX-GAME-PA1",
)


def test_no_per_card_gate_exception_table_exists():
    """逐卡覆寫表不得回來。

    它沒有真實性來源也沒有到期機制：`DATA-BOX-DEEP-SILENT-FAIL1` 那條寫於
    2026-08-14 上午、**同日下午即被 #131 的 Discovery 推翻**，而消費區塊的 ROADMAP
    正文已承認該例被推翻——同一份文件因此有兩套互相矛盾的權威敘述。
    """
    assert not hasattr(rl, "GATE_OVERRIDES")


def test_gate_texts_do_not_point_back_at_a_per_card_table():
    """`v8` 的 `⏸阻塞` 寫「見逐卡覆寫」。留著那句等於用文案把混血欄位接回來。"""
    assert not [s for s, text in rl.GATE_BY_STATUS.items() if "覆寫" in text]


@pytest.mark.parametrize("card_id", _FORMERLY_OVERRIDDEN)
@pytest.mark.parametrize("status", sorted(rl.GATE_BY_STATUS))
def test_gate_is_purely_derived_from_status(card_id, status):
    """同一狀態的任兩張卡，Gate 欄必須逐字相同——卡的身分不得影響輸出。"""
    assert rl.gate_of(card_id, status) == rl.GATE_BY_STATUS[status]
    assert rl.gate_of(card_id, status) == rl.gate_of("DATA-ANY-OTHER1", status)


@pytest.mark.parametrize("card_id", (*_FORMERLY_OVERRIDDEN, "DATA-PLAIN1"))
def test_unknown_status_fails_closed_for_every_card(card_id):
    """`CONV-001` 的不變量。

    `v7` 先回傳覆寫才驗狀態，於是覆寫表裡的卡帶著未知狀態可完全繞過驗證；`v8` 把
    驗證移到覆寫之前，`v9` 移除覆寫後該旁路在結構上不存在。**檢查本身仍須在**——
    這條測試釘的是那個檢查，不是那張表；對曾在表裡與從未在表裡的卡一律要求擋下。
    """
    with pytest.raises(rl.CheckFailed, match="不在已知詞彙表"):
        rl.gate_of(card_id, "🆕未知狀態")


def test_unknown_status_round_trip_is_blocked():
    """端到端回歸：查核者曾實測此路徑 `override_unknown_round_trip=UNEXPECTED_PASS`。

    仍以 `#53`（當初被繞過的那張）為對象。`match` 是刻意的——不加會讓這條測試在
    任何 `CheckFailed` 下通過，包含與本不變量無關的原因。
    """
    payload = {"items": [{"repository": _REPO, "卡ID": "INGEST-GAME-TM-REFACTOR1-G4",
                          "級別": "T4", "交付狀態": "🆕未知狀態",
                          "content": {"number": 53}}]}
    with pytest.raises(rl.CheckFailed, match="不在已知詞彙表"):
        res = rl.assign(rl.active_cards(payload))
        rl.reconcile(res, rl.render(res))


def test_schema_version_is_pinned_to_the_current_ruleset():
    """判定規則每動一次就要遞增，且**逐字釘住**——不釘就沒有東西擋下「忘了 bump」。

    `v9` 是 Gate 欄改由狀態導出（五張卡的文字因此改變）；`v10` 是來源辨識、`cards`
    欄位映射與 `--json.source_schema`。**`v10` 那次區塊內容逐位元組不變**，本卡
    iteration 1 據此掛了「刻意不遞增」的例外，`R1-001` 判該例外與檔頭政策矛盾：
    區塊不變是必要不變量（否則離線重現失效），不是不遞增的充分理由。
    """
    assert rl.SCHEMA_VERSION == "cpbl-roadmap-lines/v10"


# --- DEV-ROADMAP-LINES-SILENT-ZERO1：容器鍵辨識——「讀不到活卡」≠「真的零活卡」 ---
#
# `v9` 讀 `payload.get("items", [])`。官方認可的狀態面匯出 `wfcli snapshot` 吐的是
# `{generated_at, schema, cards}`；鍵名不符時 `.get` 回空陣列，於是工具**靜默回報
# `active_total=0` 並 exit 0**。下面每一條釘的都是這兩件事必須可區分。
#
# 本段刻意全部附加在檔尾：`scripts/README.md` 的〈分段路徑〉清冊逐字記著本檔的
# `:28`，在該行之前增刪任何一行都會讓 `script_inventory.py --write` 改寫那份清冊，
# 而它不在本卡宣告的寫入集內。同理，本段需要的 `io`／`json` 一律在函式內 import。

_WF = rl.WF_SNAPSHOT_SCHEMA


def _wf_card(card_id: str, status: str = "💡需求", tier: str = "T2", number: int = 1,
             repo: str = "cpbl-analytics", **over) -> dict:
    """一列 `wfcli snapshot` 的 `SnapshotRow`（只列本檔會讀的欄位）。"""
    row = {"card_id": card_id, "tier": tier, "delivery_status": status,
           "issue_number": number, "content_type": "Issue",
           "issue_url": f"https://github.com/ruan6047/{repo}/issues/{number}"}
    row.update(over)
    return row


def _wf(*rows: dict) -> dict:
    return {"generated_at": "2026-08-22T13:14:59+08:00", "schema": _WF, "cards": list(rows)}


def test_wf_snapshot_payload_is_no_longer_silently_zero():
    """病灶本身：`payload.get("items", [])` 對 `cards` payload 回空陣列並一路成功。"""
    assert [c["card_id"] for c in rl.active_cards(_wf(_wf_card("DATA-A1")))] == ["DATA-A1"]


@pytest.mark.parametrize("payload", [
    {},
    {"foo": []},
    {"schema": "wf-cli/state-snapshot/v1"},
    {"totalCount": 181},
], ids=["空 object", "無關鍵", "只有 schema 沒有容器鍵", "只有 totalCount"])
def test_missing_container_key_fails_closed(payload):
    """驗收 1：缺容器鍵一律失敗，⛔ 不得回報 active_total=0。"""
    with pytest.raises(rl.CheckFailed, match="不含任何已知的容器鍵"):
        rl.active_cards(payload)


def test_failure_message_names_what_schema_it_received():
    """驗收 1 的後半：必須**指名收到的是什麼**——最上層鍵與 payload 自陳的 schema。"""
    with pytest.raises(rl.CheckFailed) as exc:
        rl.active_cards({"rows": [], "schema": "wf-cli/state-snapshot/v2"})
    msg = str(exc.value)
    assert "'rows'" in msg and "'schema'" in msg
    assert "'wf-cli/state-snapshot/v2'" in msg
    assert "items" in msg and "cards" in msg          # 也要指出預期的是什麼


@pytest.mark.parametrize("payload", [{"items": []}, {"schema": _WF, "cards": []}],
                         ids=["items 空陣列", "cards 空陣列"])
def test_empty_container_is_a_real_zero_not_a_failure(payload):
    """驗收 2：判準是**容器鍵在不在**，不是取到的清單空不空。"""
    assert rl.active_cards(payload) == []


def test_real_zero_and_unreadable_are_distinguishable():
    """驗收 2 的正反面並排：真的零活卡通過，讀不到活卡失敗。"""
    assert rl.assign(rl.active_cards({"items": []}))["active_total"] == 0
    with pytest.raises(rl.CheckFailed):
        rl.active_cards({"itemz": []})


def test_both_container_keys_fail_closed_instead_of_picking_one():
    """驗收 3：辨識是互斥判定。以優先序挑一個讀＝安靜地換一條路，正是本卡在修的病。"""
    with pytest.raises(rl.CheckFailed, match="同時含"):
        rl.active_cards({"items": [], "schema": _WF, "cards": [_wf_card("DATA-A1")]})


def test_detect_source_is_the_single_discriminator():
    """驗收 3：辨識方式明確且可獨立呼叫——不是散在讀取路徑裡的 try/except。"""
    assert rl.detect_source({"items": []}) == ("items", "gh-project-item-list")
    assert rl.detect_source({"schema": _WF, "cards": []}) == ("cards", _WF)


def test_unhandled_source_key_cannot_fall_through_to_another_adapter():
    """`active_cards` 的 else 分支是 `cards`：只在 `SOURCE_SCHEMAS` 加鍵而不加分派，
    新來源會被當成 wfcli snapshot 讀。釘住這個封閉集合，讓那種改法先在測試上紅。"""
    assert set(rl.SOURCE_SCHEMAS) == {"items", "cards"}


@pytest.mark.parametrize("declared", [None, "wf-cli/state-snapshot/v2", ""],
                         ids=["沒有自陳", "另一個版本", "空字串"])
def test_wf_snapshot_of_another_version_fails_closed(declared):
    """欄名還在不代表語意沒變——用 v1 的欄名讀 v2 與讀錯 schema 沒有兩樣。"""
    payload = {"cards": [_wf_card("DATA-A1")]}
    if declared is not None:
        payload["schema"] = declared
    with pytest.raises(rl.CheckFailed, match="自陳 schema"):
        rl.active_cards(payload)


@pytest.mark.parametrize("over,pat", [
    ({"delivery_status": None}, "取不到 delivery_status"),
    ({"tier": None}, "缺必填欄位"),
    ({"issue_number": None}, "缺必填欄位"),
    ({"card_id": None}, "缺必填欄位"),
], ids=["缺狀態", "缺 tier", "缺 issue_number", "缺 card_id"])
def test_wf_snapshot_missing_required_fields_fail_closed(over, pat):
    """`items` 路徑的 `VERIFIER1-R3-001` 不變量逐條搬到 `cards` 路徑。"""
    row = _wf_card("DATA-A1")
    row.update(over)                                  # 事後覆寫：`card_id` 與位置參數同名
    with pytest.raises(rl.CheckFailed, match=pat):
        rl.active_cards(_wf(row))


def test_wf_snapshot_other_repo_and_closed_statuses_are_excluded():
    assert [c["card_id"] for c in rl.active_cards(_wf(
        _wf_card("DATA-ACTIVE1", number=1),
        _wf_card("DATA-DONE1", status="🏁完成", number=2),
        _wf_card("WF-OTHER1", number=3, repo="ai-workflow"),
    ))] == ["DATA-ACTIVE1"]


def test_wf_snapshot_draft_issue_is_skipped_like_an_item_without_repository():
    """draft 不屬於任何 repo；`items` 路徑也因為沒有 `repository` 而跳過。**未經實測資料
    驗證**——實測的 181 張卡全是 `content_type="Issue"`，此分支只有本測試走過。"""
    assert rl.active_cards(_wf(_wf_card("DATA-DRAFT1", content_type="DraftIssue",
                                        issue_url=None, issue_number=None))) == []


@pytest.mark.parametrize("over,pat", [
    ({"issue_url": None, "content_type": "Issue"}, "不是 DraftIssue"),
    ({"issue_url": "https://example.com/whatever"}, "解析不出 repo"),
], ids=["非 draft 卻沒有 issue_url", "issue_url 解析不出 repo"])
def test_wf_snapshot_unidentifiable_repo_fails_closed(over, pat):
    """判不出 repo 就跳過＝讓卡從排程表消失，正是本檔開頭說的不對稱失效方向。"""
    with pytest.raises(rl.CheckFailed, match=pat):
        rl.active_cards(_wf(_wf_card("DATA-A1", **over)))


def test_gh_shaped_rows_inside_cards_are_not_silently_dropped():
    """把 `items` 形狀的列塞進 `cards` 不得整批靜默跳過——那又是一次靜默零。"""
    with pytest.raises(rl.CheckFailed):
        rl.active_cards({"schema": _WF, "cards": [_item("DATA-A1")]})


@pytest.mark.parametrize("payload", [[], "items", 0, None], ids=["陣列", "字串", "數字", "null"])
def test_non_object_payload_fails_closed(payload):
    with pytest.raises(rl.CheckFailed, match="最上層不是 JSON object"):
        rl.active_cards(payload)


def test_container_value_must_be_a_list():
    with pytest.raises(rl.CheckFailed, match="不是陣列"):
        rl.active_cards({"items": {"nope": 1}})


def test_both_schemas_produce_the_same_assignment_for_the_same_board():
    """同一份看板的兩種匯出必須導出同一份排程——否則「換來源」就是換結果。"""
    gh = {"items": [_item("DATA-A1", number=1),
                    _item("UX-B1", status="🔍待查核", tier="T3", number=2)]}
    wf = _wf(_wf_card("DATA-A1", number=1),
             _wf_card("UX-B1", status="🔍待查核", tier="T3", number=2))
    assert rl.assign(rl.active_cards(gh)) == rl.assign(rl.active_cards(wf))


def test_rendered_block_is_identical_across_both_input_schemas():
    """區塊內容不隨輸入來源而異——**這是離線重現的必要條件，不是不遞增的理由**。

    若區塊會因來源而異，`--check` 就綁死了產生當時用的來源，封存 artifact 的離線
    重現會失效（ROADMAP §3 正是靠這一點用存檔快照重現 `exit 0`）。這條釘住的是
    那個不變量本身。

    ⚠️ **`R1-001` 推翻的是拿它當「不遞增 `SCHEMA_VERSION`」的理由**：必要條件不
    等於充分理由，遞增與否看的是判定規則有沒有動（來源辨識、欄位映射、`--json`
    多一個欄位，三者都是），不是輸出長不長得一樣。版本現況見
    `test_schema_version_is_pinned_to_the_current_ruleset`。
    """
    gh = {"items": [_item("DATA-A1", number=1),
                    _item("UX-B1", status="🔍待查核", tier="T3", number=2)]}
    wf = _wf(_wf_card("DATA-A1", number=1),
             _wf_card("UX-B1", status="🔍待查核", tier="T3", number=2))
    block = rl.render(rl.assign(rl.active_cards(gh)))
    assert block == rl.render(rl.assign(rl.active_cards(wf)))
    rl.reconcile(rl.assign(rl.active_cards(wf)), block)      # 跨來源對帳仍成立


def test_source_schema_never_leaks_into_the_block():
    """`source_schema` 只進 `--json` 與 stderr，不進區塊——理由同上一條。"""
    res = rl.assign(rl.active_cards(_wf(_wf_card("DATA-A1"))))
    res["source_schema"] = _WF
    assert "source_schema" not in rl.render(res)


def _main(monkeypatch, capsys, payload, *argv: str):
    """跑 `main()`，回 `(exit code, stdout, stderr)`。`io`／`json` 在函式內 import 的
    理由見本段開頭（檔頭增行會改寫不在寫入集內的 `scripts/README.md`）。"""
    import io
    import json as _json
    text = payload if isinstance(payload, str) else _json.dumps(payload, ensure_ascii=False)
    monkeypatch.setattr(rl.sys, "stdin", io.StringIO(text))
    monkeypatch.setattr(rl.sys, "argv", ["roadmap_lines.py", *argv])
    code = rl.main()
    cap = capsys.readouterr()
    return code, cap.out, cap.err


def test_main_exits_nonzero_and_names_the_schema_instead_of_reporting_zero(monkeypatch, capsys):
    """驗收 1 的端到端形式：**非零退出**＋指名收到的是什麼，且 stdout 沒有假的零。"""
    code, out, err = _main(monkeypatch, capsys, '{"rows": [], "schema": "nope/v1"}', "--json")
    assert code == 1
    assert "active_total" not in out
    assert "'nope/v1'" in err and "'rows'" in err


def test_main_still_exits_zero_on_a_genuinely_empty_board(monkeypatch, capsys):
    """驗收 2 的端到端形式：真的零活卡仍是 exit 0，不被上一條連坐。"""
    code, out, err = _main(monkeypatch, capsys, '{"items": []}', "--json")
    assert code == 0
    assert '"active_total": 0' in out


@pytest.mark.parametrize("payload,schema,key", [
    ({"items": [_item("DATA-A1")]}, "gh-project-item-list", "'items'"),
    (_wf(_wf_card("DATA-A1")), _WF, "'cards'"),
], ids=["gh 路徑", "wfcli snapshot 路徑"])
def test_main_reports_which_path_it_took(monkeypatch, capsys, payload, schema, key):
    """禁 fallback 的理由是「讀者無從得知走了哪條」，所以走了哪條必須說出來。"""
    code, out, err = _main(monkeypatch, capsys, payload, "--json")
    assert code == 0
    assert schema in err and key in err
    assert f'"source_schema": "{schema}"' in out


# --- R1-001：遞增了就必須有東西承載它 ---
#
# `SCHEMA_VERSION` 的機械作用只有一個——`reconcile()` 第 1 層讓**自陳舊版的區塊**失配。
# 遞增而不重生已出貨的區塊，全庫唯一那份區塊就會停在舊版；而 `--check` 不在 CI 裡跑
# （它要一份看板快照），沒有人會發現。下面這條把「已出貨的區塊自陳版本 == 現行版本」
# 變成 pytest 斷言，讓遞增這個動作**有東西承載**。
#
# ⚠️ 它**不**對帳卡片列——那需要一份 as-of 快照當基準，而快照會過期。§3 的離線重現
# 指令（用隨卡存檔的快照跑 `--check`）仍是人工步驟，ROADMAP §6 已記著「重生至今仍然
# 靠人記得，沒有替它建立機械執行者」，那是另一張卡的射程。


def test_shipped_roadmap_block_declares_the_current_schema_version():
    """`docs/ROADMAP.md` 的排程區塊必須自陳現行版本——遞增後忘了重生即紅。"""
    roadmap = Path(__file__).resolve().parents[1] / "docs" / "ROADMAP.md"
    assert rl.block_version(roadmap.read_text(encoding="utf-8")) == rl.SCHEMA_VERSION
