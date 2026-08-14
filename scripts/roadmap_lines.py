"""CPBL 藍圖 §3 的任務線歸屬驗證器（唯讀，fail-closed）。

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

SCHEMA_VERSION = "cpbl-roadmap-lines/v2"

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

#: §3 的節標題與同級標題。解析**只在這個區間內**進行——`DEV-ROADMAP-VERIFIER1`
#: 的 R2-002：前一版對全檔逐行套 `_CARD_ROW`，於是 §3 以外任何合法格式的卡 ID
#: 表格列都會造成假失敗（實測在 §0 前插一列即 exit 1）。
_SECTION3_HEADING = re.compile(r"^##\s+3\.\s")
_SAME_LEVEL_HEADING = re.compile(r"^##\s")


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


def _field(item: dict, suffix: str) -> str:
    """Project 欄位名在 JSON 中可能帶前綴雜訊，故以後綴比對取值。"""
    for key, value in item.items():
        if key.endswith(suffix):
            return str(value)
    return ""


def active_cards(payload: dict) -> list[dict]:
    """自 `gh project item-list --format json` 的輸出取出本 repo 的活卡。"""
    out = []
    for item in payload.get("items", []):
        repo = (item.get("repository") or "").rsplit("/", 1)[-1]
        if repo != REPO_SLUG:
            continue
        status = _field(item, "付狀態")
        if status in CLOSED_STATUSES:
            continue
        card_id = _field(item, "ID")
        if not card_id:
            raise CheckFailed(
                f"活卡缺卡ID 欄位：{item.get('content', {}).get('number')}——"
                "無卡 ID 即無法歸屬，fail closed"
            )
        out.append({
            "card_id": card_id,
            "tier": _field(item, "別"),
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


def section3_lines(text: str) -> list[str]:
    """截出 §3「現行排程」的內容行：自其標題之後，至下一個同級 `##` 標題之前。

    找不到 §3 標題即 **fail closed**——回空集會讓「§3 不見了」與「§3 是空的」
    無法區分，而前者是嚴重得多的狀態。
    """
    lines = text.splitlines()
    start = next((i for i, ln in enumerate(lines) if _SECTION3_HEADING.match(ln)), None)
    if start is None:
        raise CheckFailed(
            "在 ROADMAP 中找不到 §3 節標題（預期形如 `## 3. 現行排程`）——"
            "無法界定解析範圍，fail closed"
        )
    end = next((i for i in range(start + 1, len(lines))
                if _SAME_LEVEL_HEADING.match(lines[i])), len(lines))
    return lines[start + 1:end]


def cards_in_roadmap(text: str) -> list[str]:
    """自 ROADMAP **§3 區間內**的表格列抽出卡 ID。

    兩層限縮：先截 §3 區間（`section3_lines`），再於區間內錨定行首 `|`。
    §3 以外的表格列與任何位置的行內 code 都不會誤中。
    """
    return [m.group(1) for line in section3_lines(text) if (m := _CARD_ROW.match(line))]


def reconcile(result: dict, roadmap_text: str) -> None:
    """比對 Project 活卡與 ROADMAP §3 表列。雙向差集皆須為空。"""
    listed = cards_in_roadmap(roadmap_text)
    dupes = [cid for cid, n in collections.Counter(listed).items() if n > 1]
    if dupes:
        raise CheckFailed(f"ROADMAP §3 表內卡 ID 重複：{sorted(dupes)}")

    project_ids = {c["card_id"] for c in result["cards"]}
    listed_ids = set(listed)
    only_project = sorted(project_ids - listed_ids)
    only_roadmap = sorted(listed_ids - project_ids)
    if only_project or only_roadmap:
        raise CheckFailed(
            "ROADMAP §3 與 Project 活卡對不上——"
            f"只在 Project：{only_project}；只在 ROADMAP：{only_roadmap}"
        )


def render(result: dict) -> str:
    lines = [f"schema_version: {result['schema_version']}",
             f"活卡總數: {result['active_total']}",
             f"每線: {result['per_line']}", ""]
    for code, name in sorted(LINES.items()):
        rows = [c for c in result["cards"] if c["line"] == code]
        lines.append(f"### {code} {name}（{len(rows)} 張）\n")
        lines.append("| 卡 | # | tier | 狀態 | 下一個必要 Gate／阻塞條件 | 去留 |")
        lines.append("|---|---|---|---|---|---|")
        for c in rows:
            gate = GATE_OVERRIDES.get(c["card_id"]) or GATE_BY_STATUS.get(c["status"], "—")
            lines.append(
                f"| `{c['card_id']}` | #{c['number']} | {c['tier']} | {c['status']} | {gate} | |"
            )
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="CPBL 藍圖 §3 的任務線歸屬驗證器（唯讀，fail-closed）")
    ap.add_argument("--check", type=Path, default=None,
                    help="ROADMAP.md 路徑；有給則額外對帳 §3 表列與 Project 活卡")
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
