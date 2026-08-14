"""CPBL 藍圖排程區塊的任務線歸屬驗證器（唯讀，fail-closed）。

回應 `DOC-CPBL-ROADMAP1` R1 finding `CPBL-ROADMAP1-R1-03`：前一版 ROADMAP 在 §3 附了
一行 `python3 scripts/roadmap_lines.py`，**而那個腳本不存在**，卻在驗收裡宣稱清單可重現。
查核者只好臨時自行重寫集合比對。本檔把那個宣稱變成真的。

**唯讀**：只讀 stdin 的 Project JSON，不連 GitHub、不碰 DB、不寫任何狀態面。

    gh project item-list 4 --owner ruan6047 --format json --limit 300 \
      | uv run python scripts/roadmap_lines.py --check docs/ROADMAP.md

## 為什麼是 fail-closed

歸屬判定的失效方向不對稱：**漏掉一張卡**（某卡不屬於任何線）會讓它從排程表消失、
永遠沒人看到；**多算一張**只是噪音。因此任何未歸屬、重複、或與 ROADMAP 表對不上的
情形一律 `exit 1`，不提供「忽略」開關。

## 為什麼用 marker 界定而不是找節標題

`v1`–`v4` 靠 markdown 結構定位 §3，於是連續三輪查核各找到一個新的邊界情形：
程式碼區塊裡的假 `## 3.`、重複的 `## 3.`、縮排／引言的表格列、四反引號圍籬被三反引號
提前關閉。**那個清單沒有盡頭**——CommonMark 的邊界情形有幾十頁，而這裡並不需要一個
markdown 解析器。

`v5` 改用 marker 界定，沿用本專案 Issue body 的 `resource-claims` 既有慣例：

    <!-- roadmap-lines:begin -->
    ...表格...
    <!-- roadmap-lines:end -->

marker 是 HTML 註解，**不受縮排、引言、圍籬影響**，定位是字面比對而非結構推導。
因此 `_FENCE`／`_outside_fences()`／節標題偵測／重複標題偵測**整層移除**——
它們保護的不變量（歧義即失敗）改由 marker 的成對性檢查承接。

**這也解除了對文件作者的四條隱形禁令**（不得縮排、不得引用、不得有第二個 `## 3.`、
示範須放圍籬）。那些禁令從未寫在 ROADMAP 裡，只寫在本檔的 docstring。

## 版本化

`SCHEMA_VERSION` 隨判定規則變動遞增，並寫進輸出。判定規則改了而版本沒動，
等於讓兩次執行的輸出無法區分——那正是 R1-03 的病。
"""

from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from pathlib import Path

SCHEMA_VERSION = "cpbl-roadmap-lines/v6"

#: 五條任務線。key 為線代號，value 為對外名稱（須與 ROADMAP §1／§3 的標題一致）。
LINES: dict[str, str] = {
    "L1": "資料正確性",
    "L2": "每日鏈可靠性",
    "L3": "產品／UX",
    "L4": "ML／研究",
    "L5": "開發／文件基礎",
}

#: 卡 ID 前綴 → 線。順序有意義：由上而下第一個命中者勝。
PREFIX_RULES: tuple[tuple[str, str], ...] = (
    ("DATA-", "L1"),
    ("INGEST-", "L1"),
    ("OPS-", "L2"),
    ("UX-", "L3"),
    ("ML-", "L4"),
    ("DEV-", "L5"),
    ("DOC-", "L5"),
)

#: 前綴規則判不對的卡逐張列舉。**這是人工分類，會過期**——所以下面的
#: `unassigned` 檢查是 fail-closed 的：新卡若前綴與此表都不命中即失敗，
#: 強迫作者做出判斷，而不是靜默落進某個預設線。
EXPLICIT_RULES: dict[str, str] = {
    "MATCHUP-DATA2": "L1",
    "DEV-VERIFY-TM-ASSERTS1": "L1",
    "INIT-OFFICIAL-DATA1": "L1",
    "API-INFO-UNRESOLVED-GAMES1": "L2",
    "LIVE-WORKER-RESCHEDULE-FILTER1": "L2",
    "OPS-SCHEDULE-FAILURE-BLIND1": "L2",
    "DAILY-MIXED-DAY-UX1": "L3",
    "INIT-PRODUCT-UX": "L3",
    "INIT-GAME-RECAP": "L3",
    "WP-DISCLOSURE-SYNC1": "L4",
    "RESEARCH-REASON-RESTATE1": "L4",
}

#: 狀態 → 下一個必要 Gate／阻塞條件（基線 5）。由狀態導出，避免人工逐列填寫而過期。
GATE_BY_STATUS: dict[str, str] = {
    "💡需求": "規劃 Gate：Discovery → Design → Plan，需求方核可後才進 Backlog",
    "🧭規劃中": "完成規劃產物並取得需求方核可",
    "📥Backlog": "認領（線 WIP 須有空位）",
    "⏳待執行": "執行者進場",
    "🔨執行中": "交付並 handoff 送審",
    "🚧進行中": "交付並 handoff 送審",
    "🔍待查核": "查核者進場並寫入裁決",
    "↩退回": "依 finding 修正後重新送審",
    "✅通過": "需求方授權 merge → 結案（cleanup ＋ 終態寫入）",
    "⏸阻塞": "解除阻塞條件（見逐卡覆寫）",
    "🚨已升級": "需求方裁定升級去向",
}

#: 逐卡覆寫。**只有「從狀態導不出來」的才列**——例如阻塞的具體對象、
#: 或需求方已明示的排序位置。列在這裡的每一條都要能指出依據。
GATE_OVERRIDES: dict[str, str] = {
    "INGEST-GAME-TM-REFACTOR1-G4":
        "**L1 閘門**。Phase A 碼已上線（`eaf2154`，在生產 `d31cf4d`），但 Phase A → Phase B "
        "的四項放行條件**沒有量測工具**（`g4_phase_a_metrics.py` 只有 equipped／requests／"
        "rollback），故四項一項都判不了。另：第 2 輪 APPROVE 從未經 `wfcli` 寫入狀態面。"
        "Phase B 完成前佔用 L1 WIP（基線 6）",
    "DATA-RE24-PROD-REBUILD1":
        "等 `INGEST-GAME-TM-REFACTOR1-G4`（#53）結案。解阻後須**重新驗證前提並啟動新 "
        "iteration**，不得沿用 2026-08-08 的認領（基線 6）",
    "DATA-BOX-DEEP-SILENT-FAIL1":
        "規劃階段先做**唯讀查證**（31 場是否真的都未進快照／7 這個數字重算）。"
        "⏰ **2026-08-17 14:10** 週跑後 7 場掉出 `days_back=30` 窗；基線 5 的排序判準"
        "**無時效／可逆性維度**，是否插隊須需求方於 Design Gate 明示",
    "DATA-BOX-REVISION-SNAPSHOT1": "等需求方手動部署",
    "UX-GAME-PA1": "碼已 merge（`f9f2399`），等生產部署驗證後結案",
}

#: 不計入「活卡」的交付狀態。終態與已合併不佔排程表。
CLOSED_STATUSES = frozenset({"🏁完成", "🛑已停止", "📦已合併"})

REPO_SLUG = "cpbl-analytics"

_CARD_ROW = re.compile(r"^\|\s*`([A-Z0-9][A-Z0-9-]*)`\s*\|")

#: 「看起來像卡片列但不在標準位置」——縮排、引言符號（`>`）、或兩者。
#: `VERIFIER1-R1-002`：這些形狀原本被**靜默忽略**，方向與 fail-closed 相反。
#: 保留為區塊內的防呆（marker 之後這類寫法已極不可能，但忽略仍是錯的方向）。
_CARD_ROW_LOOSE = re.compile(r"^[ \t>]*\|\s*`([A-Z0-9][A-Z0-9-]*)`\s*\|")

#: 排程區塊的界定 marker。沿用 Issue body `resource-claims` 的既有慣例。
MARKER_BEGIN = "<!-- roadmap-lines:begin -->"
MARKER_END = "<!-- roadmap-lines:end -->"

#: 區塊內的版本註解。`--check` **會驗證它與 SCHEMA_VERSION 相同**。
#: 自審發現：`v5` 把版本寫進區塊卻從不比對，於是 v1 產生的區塊照樣通過 v5 的檢查——
#: 而本檔 docstring 正好寫著「版本沒動等於兩次輸出無法區分」。宣稱與實作對不上。
_VERSION_COMMENT = re.compile(r"^<!--\s*(cpbl-roadmap-lines/v\d+)\s*[；;]")

#: 卡片列的欄位契約。前四欄由指令產生、**逐欄比對**；`去留` 由需求方手填、**放行**。
#: 自審發現：`v5` 只比對卡 ID，於是 tier 竄改 T2→T4、狀態改 🏁完成 都靜默通過，
#: 而 §3 宣稱「本表由指令產生」。只守一維而宣稱守全表，是同一族的宣稱過度。
MACHINE_COLUMNS = ("卡", "#", "tier", "狀態", "下一個必要 Gate／阻塞條件")
HUMAN_COLUMNS = ("去留",)
_EXPECTED_CELLS = len(MACHINE_COLUMNS) + len(HUMAN_COLUMNS)


class CheckFailed(Exception):
    """歸屬或對帳失敗。訊息即失敗原因，呼叫端直接印出後 exit 1。"""


def line_of(card_id: str) -> str | None:
    """回傳卡所屬的線；判不出來回 None（呼叫端據此 fail closed）。"""
    if card_id in EXPLICIT_RULES:
        return EXPLICIT_RULES[card_id]
    for prefix, line in PREFIX_RULES:
        if card_id.startswith(prefix):
            return line
    return None


#: Project 欄位的正式名稱 → 退而求其次的後綴。
#: **為什麼需要後綴**：`gh project item-list --format json` 回來的 key 前綴會壞掉
#: （實測為 `'\ufffd\ufffd\ufffdID'`、`'\ufffd\ufffd\ufffd付狀態'`——欄名開頭的 emoji 被打爛），
#: 精確比對取不到值。**但後綴比對可被遮蔽**：任何新欄位只要同後綴就可能搶先命中
#: （自審實測：加一個「外部ID」欄，卡 ID 會取到它）。故**先精確、後後綴**。
_FIELD_KEYS: dict[str, tuple[str, str]] = {
    "card_id": ("卡ID", "ID"),
    "tier": ("級別", "別"),
    "status": ("交付狀態", "付狀態"),
}


def _field(item: dict, name: str, suffix: str) -> str:
    """取 Project 欄位值：先以正式名精確比對，取不到才退回後綴比對。"""
    if name in item:
        return str(item[name])
    hits = [str(v) for k, v in item.items() if k.endswith(suffix)]
    if len(hits) > 1:
        raise CheckFailed(
            f"欄位後綴 {suffix!r} 命中 {len(hits)} 個 key，無法判定哪一個是 {name}——"
            "fail closed（精確名稱取不到時才會走到後綴，而後綴可被同尾欄位遮蔽）"
        )
    return hits[0] if hits else ""


def active_cards(payload: dict) -> list[dict]:
    """自 `gh project item-list --format json` 的輸出取出本 repo 的活卡。"""
    out = []
    for item in payload.get("items", []):
        repo = (item.get("repository") or "").rsplit("/", 1)[-1]
        if repo != REPO_SLUG:
            continue
        status = _field(item, *_FIELD_KEYS["status"])
        if status in CLOSED_STATUSES:
            continue
        card_id = _field(item, *_FIELD_KEYS["card_id"])
        if not card_id:
            raise CheckFailed(
                f"活卡缺卡ID 欄位：{item.get('content', {}).get('number')}——"
                "無卡 ID 即無法歸屬，fail closed"
            )
        out.append({
            "card_id": card_id,
            "tier": _field(item, *_FIELD_KEYS["tier"]),
            "status": status,
            "number": item.get("content", {}).get("number"),
        })
    return out


def assign(cards: list[dict]) -> dict:
    """歸屬並檢查三項不變量。任一不成立即 raise。"""
    assigned = []
    unassigned = []
    for card in cards:
        line = line_of(card["card_id"])
        if line is None:
            unassigned.append(card["card_id"])
        else:
            assigned.append({**card, "line": line})

    if unassigned:
        raise CheckFailed(
            "以下卡無法歸入任何一條線，請在 EXPLICIT_RULES 明確分類或新增前綴規則"
            f"（不得靜默落進預設線）：{sorted(unassigned)}"
        )

    dupes = [cid for cid, n in collections.Counter(c["card_id"] for c in assigned).items() if n > 1]
    if dupes:
        raise CheckFailed(f"卡 ID 重複：{sorted(dupes)}")

    unknown = sorted({c["line"] for c in assigned} - set(LINES))
    if unknown:
        raise CheckFailed(f"歸屬到未定義的線：{unknown}")

    return {
        "schema_version": SCHEMA_VERSION,
        "active_total": len(assigned),
        "per_line": {ln: sum(1 for c in assigned if c["line"] == ln) for ln in sorted(LINES)},
        "cards": sorted(assigned, key=lambda c: (c["line"], c["card_id"])),
    }


def schedule_block_lines(text: str) -> list[str]:
    """截出排程區塊：`MARKER_BEGIN` 與 `MARKER_END` 之間的行（不含 marker 本身）。

    以下情形一律 **fail closed**，因為每一種都代表文件本身出了問題，
    而**猜哪一個才是對的不是解析器該做的事**：

    - 缺任一 marker——回空集會讓「區塊不見了」與「區塊是空的」無法區分，前者嚴重得多
    - marker 不成對或數量不為 1
    - `end` 出現在 `begin` 之前

    marker 比對是**整行去空白後的字面相等**，不做部分比對——避免內文提到 marker
    字串時被誤認（同 `review-marker-literal-quarantines-card` 的教訓）。
    """
    lines = text.splitlines()
    begins = [i for i, ln in enumerate(lines) if ln.strip() == MARKER_BEGIN]
    ends = [i for i, ln in enumerate(lines) if ln.strip() == MARKER_END]

    if len(begins) != 1 or len(ends) != 1:
        raise CheckFailed(
            f"排程區塊 marker 數量不正確（begin {len(begins)} 個、end {len(ends)} 個，"
            f"各須恰好 1 個）——預期 {MARKER_BEGIN} 與 {MARKER_END}，fail closed"
        )
    if ends[0] < begins[0]:
        raise CheckFailed(
            f"排程區塊 marker 順序顛倒（end 在第 {ends[0] + 1} 行、"
            f"begin 在第 {begins[0] + 1} 行）——fail closed"
        )
    return lines[begins[0] + 1:ends[0]]


def _cells(line: str) -> list[str]:
    """把一列 markdown 表格拆成儲存格（去掉頭尾的 `|`，各格去空白）。"""
    return [c.strip() for c in line.strip().strip("|").split("|")]


def rows_in_roadmap(text: str) -> list[list[str]]:
    """自排程區塊抽出卡片列的**逐欄內容**。

    兩層：marker 界定區塊 → 區塊內嚴格錨定行首 `|`。區塊外的一切
    （其他章節的表格、程式碼區塊、行內 code）都不會誤中，**且不需要理解 markdown**。

    區塊內的兩種形狀 **fail closed** 而非忽略——區塊由指令產生，出現它們代表有人
    手改過而且改壞了：

    - 縮排或帶引言符號的卡片列（`VERIFIER1-R1-002`）
    - 欄數不符 `_EXPECTED_CELLS` 的卡片列（否則逐欄比對會靜默略過該列）
    """
    rows: list[list[str]] = []
    for line in schedule_block_lines(text):
        strict = _CARD_ROW.match(line)
        if strict:
            cells = _cells(line)
            if len(cells) != _EXPECTED_CELLS:
                raise CheckFailed(
                    f"排程區塊內卡片列欄數為 {len(cells)}，預期 {_EXPECTED_CELLS}"
                    f"（{'／'.join(MACHINE_COLUMNS + HUMAN_COLUMNS)}）——"
                    f"fail closed：{line.strip()!r}"
                )
            rows.append(cells)
            continue
        loose = _CARD_ROW_LOOSE.match(line)
        if loose:
            raise CheckFailed(
                f"排程區塊內出現縮排或帶引言符號的卡片列，fail closed："
                f"{line.strip()!r}（卡 ID {loose.group(1)}）"
            )
    return rows


def cards_in_roadmap(text: str) -> list[str]:
    """自排程區塊抽出卡 ID（`rows_in_roadmap` 的第一欄，去掉反引號）。"""
    return [r[0].strip("`") for r in rows_in_roadmap(text)]


def block_version(text: str) -> str:
    """讀排程區塊內的版本註解。缺少即 fail closed——區塊必須自陳由哪一版產生。"""
    for line in schedule_block_lines(text):
        m = _VERSION_COMMENT.match(line.strip())
        if m:
            return m.group(1)
    raise CheckFailed(
        f"排程區塊內找不到版本註解（預期形如 `<!-- {SCHEMA_VERSION}；… -->`）——"
        "無從判斷區塊由哪一版產生，fail closed"
    )


def gate_of(card_id: str, status: str) -> str:
    """該卡的「下一個必要 Gate／阻塞條件」——逐卡覆寫優先，否則由狀態導出。"""
    return GATE_OVERRIDES.get(card_id) or GATE_BY_STATUS.get(status, "—")


def reconcile(result: dict, roadmap_text: str) -> None:
    """比對 Project 活卡與 ROADMAP 排程區塊。

    三層檢查，任一不成立即失敗：

    1. **版本**：區塊自陳的版本須與 `SCHEMA_VERSION` 相同。不同代表區塊過期，
       其內容由不同的判定規則產生，比對結果無意義。
    2. **集合**：雙向差集皆須為空，且無重複。
    3. **逐欄**：`MACHINE_COLUMNS` 每一欄都須與由 Project 現值導出的期望相同。
       `HUMAN_COLUMNS`（`去留`）由需求方手填，**放行不比對**。

    第 3 層是自審補上的：`v5` 只做第 2 層，於是 tier 竄改、狀態改成 🏁完成 都靜默
    通過，而 §3 宣稱「本表由指令產生」。**只守一維而宣稱守全表**是同一族的宣稱過度。
    """
    found = block_version(roadmap_text)
    if found != SCHEMA_VERSION:
        raise CheckFailed(
            f"排程區塊由 {found} 產生，目前為 {SCHEMA_VERSION}——判定規則已變更，"
            "請重跑產生指令後再對帳"
        )

    rows = rows_in_roadmap(roadmap_text)
    listed = [r[0].strip("`") for r in rows]
    dupes = [cid for cid, n in collections.Counter(listed).items() if n > 1]
    if dupes:
        raise CheckFailed(f"排程區塊內卡 ID 重複：{sorted(dupes)}")

    by_id = {c["card_id"]: c for c in result["cards"]}
    only_project = sorted(set(by_id) - set(listed))
    only_roadmap = sorted(set(listed) - set(by_id))
    if only_project or only_roadmap:
        raise CheckFailed(
            "排程區塊與 Project 活卡對不上——"
            f"只在 Project：{only_project}；只在 ROADMAP：{only_roadmap}"
        )

    drifted: list[str] = []
    for row in rows:
        cid = row[0].strip("`")
        card = by_id[cid]
        expected = [f"`{cid}`", f"#{card['number']}", card["tier"], card["status"],
                    gate_of(cid, card["status"])]
        for name, want, got in zip(MACHINE_COLUMNS, expected, row, strict=False):
            if want != got:
                drifted.append(f"{cid} 的「{name}」：區塊 {got!r} vs 現值 {want!r}")
    if drifted:
        raise CheckFailed(
            "排程區塊的機器產生欄與 Project 現值不符（`去留` 欄不在比對範圍）——\n  "
            + "\n  ".join(drifted)
        )


def render(result: dict) -> str:
    lines = [f"{MARKER_BEGIN}", "",
             f"<!-- {result['schema_version']}；活卡 {result['active_total']}；"
             f"每線 {result['per_line']} -->", ""]
    for code, name in sorted(LINES.items()):
        rows = [c for c in result["cards"] if c["line"] == code]
        lines.append(f"### {code} {name}（{len(rows)} 張）\n")
        cols = MACHINE_COLUMNS + HUMAN_COLUMNS
        lines.append("| " + " | ".join(cols) + " |")
        lines.append("|" + "---|" * len(cols))
        for c in rows:
            lines.append(
                f"| `{c['card_id']}` | #{c['number']} | {c['tier']} | {c['status']} "
                f"| {gate_of(c['card_id'], c['status'])} | |"
            )
        lines.append("")
    lines.append(MARKER_END)
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="CPBL 藍圖排程區塊的任務線歸屬驗證器（唯讀，fail-closed）")
    ap.add_argument("--check", type=Path, default=None,
                    help="ROADMAP.md 路徑；有給則額外對帳排程區塊與 Project 活卡")
    ap.add_argument("--json", action="store_true", help="輸出 JSON 而非 Markdown 表")
    args = ap.parse_args()

    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(f"[roadmap-lines] stdin 不是合法 JSON：{exc}", file=sys.stderr)
        return 1

    try:
        result = assign(active_cards(payload))
        if args.check is not None:
            reconcile(result, args.check.read_text(encoding="utf-8"))
    except CheckFailed as exc:
        print(f"[roadmap-lines] FAIL：{exc}", file=sys.stderr)
        return 1

    print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else render(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
