# LIFECYCLE: standing · 常設工具——這就是給你跑的；不要刪
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

## 為什麼 Gate 欄不接受逐卡覆寫

`v7`–`v8` 有一張 `GATE_OVERRIDES`：逐卡硬編的 Gate 說明文字，且**優先於狀態導出**。
那讓 Gate 欄成為混血欄位——一半機器導出、一半人手寫——而人寫的那半**沒有真實性
來源、也沒有到期機制**。

實證（`DEV-ROADMAP-GATE-DERIVED1`）：`DATA-BOX-DEEP-SILENT-FAIL1` 那條覆寫寫於
2026-08-14 上午、**同日下午即過期**——它引用的「7 場在 08-17 後掉出重抓窗」被 #131
的規劃階段 Discovery 推翻（`days_back` 是 CLI 位置參數，不是物理限制）。而消費本區塊
的 ROADMAP 正文已正確承認該例被推翻，於是同一份文件出現兩套互相矛盾的權威敘述。
文件的擁有者修不掉它（文字住在本檔），手改區塊又會讓 `--check` 失配。

**「加一個到期檢查」不是解法**：到期檢查需要一個可機械驗證的真實性來源，而 Gate
說明文字的來源是需求方與規劃者的判斷。`v9` 因此把整張表移除——Gate 欄**只承載
由交付狀態導得出來的東西**，狀態導不出來的（阻塞對象、閘門理由、部署等待）
屬於各張卡自己的狀態，歸位到各自的 Issue（`GATE_BY_STATUS` 的文案因此指向卡片，
而非指向本檔的另一張表）。

同一理由下，`GATE_BY_STATUS` 的任何值都不得回指本檔的逐卡例外——那會把剛拆掉的
混血欄位用文案再接回去。測試對此有斷言。

## 為什麼接受兩種輸入 schema——而且**不是** fallback

`v9` 只讀 `payload.get("items", [])`，也就是 `gh project item-list --format json`
的形狀。但官方認可的狀態面匯出 `wfcli snapshot` 吐的是 `{generated_at, schema, cards}`。
鍵名不符時 `.get("items", [])` 回空陣列，於是本工具**靜默回報零活卡並 `exit 0`**
（`DEV-ROADMAP-LINES-SILENT-ZERO1`）。那是本檔最該防的形狀的極致版：不只是
「對帳通過而它比對的東西是假的」，是**連比對對象都沒讀到卻宣稱一致**。

實害已經發生過：`#162` R2 要附 as-of 快照當證據時，因為本工具只吃 `items`，
執行者把 `gh project item-list` 的逐字輸出存進 repo——同一份看板（實測 181 items）
`gh` 輸出 2.58 MB（幾乎全是 Issue body），`wfcli snapshot` 只有 0.19 MB。

因此本檔**同時接受兩種 schema**，以**容器鍵的存在與否**辨識：

| 容器鍵 | 產生者 | 欄位風格 |
|---|---|---|
| `items` | `gh project item-list --format json` | Project 欄名（中文；emoji 前綴實測會壞） |
| `cards` | `wfcli snapshot --out-dir` 的 `snapshot.json` | `SnapshotRow` 的 snake_case |

**辨識是互斥判定，不是 fallback**：兩個鍵都在、或都不在，一律失敗並印出實際收到的
最上層鍵與自陳 schema。⛔ **不得寫成「試著讀 `items`，讀不到就讀 `cards`」**——
那只是把本節在修的病換個位置：安靜地換一條路，讀者無從得知走了哪條。走了哪一條
會印在 stderr，並寫進 `--json` 的 `source_schema`。

**判準是容器鍵在不在，不是取到的清單空不空**：`{"items": []}` 是「看板上真的沒有
活卡」，缺容器鍵是「這份 payload 根本不是本工具讀得懂的東西」。前者 `exit 0`、
後者 `exit 1`——**兩者必須可區分**，把後者也算成 0 正是本卡在修的病。

### 兩條路徑不等價，而這個不等價本檔補救不了

`wfcli snapshot` 的 `build_rows` 在**上游**就丟掉沒有卡ID的 item（`if not card_id:
continue`），而 `items` 路徑對「活卡缺卡ID」是 fail closed 的（`VERIFIER1-R3-001`）。
也就是說 `cards` 路徑通過的對帳是**弱一階**的宣稱：它證明不了「看板上沒有漏填
卡ID的活卡」。`source_schema` 之所以要露出來，就是為了讓讀者判斷手上這次通過是哪一階。

`cards` schema **沒有 `repository` 欄**，repo 只能從 `issue_url` 取；取不出來一律
失敗而非跳過——跳過會讓卡從排程表消失，正是本檔開頭說的那個不對稱失效方向。

## 版本化

`SCHEMA_VERSION` 隨判定規則變動遞增，並寫進輸出。判定規則改了而版本沒動，
等於讓兩次執行的輸出無法區分——那正是 R1-03 的病。

- `v9`：移除 `GATE_OVERRIDES`，Gate 欄純由狀態導出；`⏸阻塞` 文案改為指向卡片。
  **五張卡的 Gate 欄文字因此改變**，既有區塊會失配——這正是版本比對該擋下的事，
  消費端須重跑產生指令重生區塊。
- `v10`：新增**來源辨識**（`detect_source`）、接受 `wfcli snapshot` 的 `cards` schema
  並定義其欄位映射、缺容器鍵時 fail closed、`--json` 露出 `source_schema`。
  **產生的區塊內容不變**——對任何原本就讀得懂的 `items` payload，`render()` 的輸出
  逐位元組相同（歸屬規則、欄位契約、Gate 文字全未動），故重生 §3 區塊時**只有版本
  註解那一行改變**。

  ⚠️ **「區塊內容不變」不是不遞增的理由**（`DEV-ROADMAP-LINES-SILENT-ZERO1` `R1-001`）。
  本節開頭的政策寫的是「**判定規則**變動遞增」，而本次動的正是判定規則與介面契約
  本身：哪一種 payload 讀得懂、哪個欄位對應哪個語意、`--json` 多了一個欄位。
  區塊逐位元組相同是這次改動的**必要不變量**（若區塊隨來源而異，`--check` 就綁死了
  產生當時用的來源，封存 artifact 的離線重現會失效），**不是遞增與否的判準**——
  必要條件不能當充分理由用。本卡 iteration 1 曾以它為由掛一條「`v9` 刻意不遞增」的
  例外，那條例外與同一節開頭的政策直接互相矛盾，已隨本次遞增移除。

  併帶後果：`reconcile()` 第 1 層會讓**所有 `v9` 產生的區塊失配**，消費端須重跑
  產生指令重生區塊。ROADMAP §3 已於本卡重生（所憑的 as-of 快照在該節逐字指名）。
- `v11`：`GATE_BY_STATUS` 補上 `🔬研究中`；`⏳待執行`／`🚧進行中` 就地標記為
  **廢止但仍須讀得懂**的歷史值並保留（`DEV-ROADMAP-GATE-RESEARCH-STATUS1`）。

  **為什麼這算判定規則變動**：本節開頭的政策寫的是「隨**判定規則**變動遞增」。
  `gate_of()` 是判定函式，`GATE_BY_STATUS` 的**鍵集就是它的定義域**——「哪些交付
  狀態讀得懂、哪些一律 fail closed」正是一條判定規則。加一個鍵把
  `gate_of(_, "🔬研究中")` 由 `raise CheckFailed` 改成回傳字串，**同一份輸入在新舊
  兩版產生不同結果**（實測：改動前 `render()` 以 `CheckFailed` 中止、`--check`
  exit 1；改動後 exit 0 並多導出一列）。那正是版本存在的目的：讓兩次執行的輸出
  可區分。

  ⛔ **不得以「今天板上 0 張、故區塊逐位元組不變」當不遞增的理由。** `#143`
  `R1-001` 已判過這個形狀：區塊不變是必要不變量（否則封存快照的離線重現失效），
  不是充分理由。`v10` 擴的是「哪一種 payload 讀得懂」，`v11` 擴的是「哪一種交付
  狀態讀得懂」——**同一個軸：讀者的定義域**；差別只在 `v10` 順帶動了 `--json` 的
  欄位。**「有沒有動介面契約」不是本檔政策的判準**，拿它當判準等於把 `#143` 剛
  移除的那條例外換個說法裝回來。

  併帶後果同 `v9`／`v10`：`reconcile()` 第 1 層會讓所有 `v10` 產生的區塊失配，
  消費端須重跑產生指令。ROADMAP §3 已於本卡重生——**所憑快照與 `v10` 那次是同一
  份**，故卡片列逐位元組不變，只有版本註解那一行改變。
"""

from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from pathlib import Path

SCHEMA_VERSION = "cpbl-roadmap-lines/v11"

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

#: 狀態 → 下一個必要 Gate／阻塞條件（基線 5）。**這是 Gate 欄的唯一來源**。
#:
#: 每一條都必須是「對任何處於該狀態的卡都成立」的敘述。**不得寫進逐卡事實**
#: （阻塞的具體對象、閘門理由、在等哪一次部署），那些是各張卡自己的狀態，
#: 屬於各自的 Issue；寫進來就會過期而且沒有人會發現（`v8` 的 `GATE_OVERRIDES`
#: 即為此而移除，見模組 docstring）。
#:
#: 同理，**值裡不得回指本檔的逐卡例外表**——`v8` 的 `⏸阻塞` 寫「見逐卡覆寫」，
#: 那條交叉引用是把混血欄位用文案接回來。測試 `test_gate_texts_do_not_point_back_at_a_per_card_table` 釘住此點。
#:
#: **鍵集的定義域是「產生端的欄位 schema」，不是「今天板上出現過的值」**
#: （`DEV-ROADMAP-GATE-RESEARCH-STATUS1`）。本表 ∪ `CLOSED_STATUSES` 必須**恰好等於**
#: Project `交付狀態` single-select 的選項集，即 `wfcli` 的凍結欄位 schema
#: （`ai-workflow` `cli/src/wf_cli/project.py` 的 `FIELD_SPECS["交付狀態"]`）那 15 個值。
#: `gate_of()` 是 fail-closed 的**讀者**：讀者的封閉集少一個值，寫得出該值的看板就會讓
#: `active_cards → render → reconcile` 整條路徑失敗。因此**「板上目前 0 張」不是刪鍵的
#: 理由**——那是拿實例當形狀用。測試以逐字黃金值釘住這個等式。
GATE_BY_STATUS: dict[str, str] = {
    "💡需求": "規劃 Gate：Discovery → Design → Plan，需求方核可後才進 Backlog",
    #: canonical 序列 `💡需求 → 🔬研究中 → 🧭規劃中` 的中段（Discovery 進行中）。
    #: ⚠️ **`v10` 以前缺這一鍵**：任一活卡進 `🔬研究中`，`gate_of()` 即 fail closed，
    #: 整條 `active_cards → render → reconcile` 中止、§3 區塊重生不了。它不是理論值
    #: ——`wfcli` 有寫入它的動詞（`handoff --next-stage research` → `STAGE_STATUS`），
    #: 且 Project 的 `交付狀態` 欄從 `ai-workflow#102`（`ae8f741`）起就有這個選項。
    "🔬研究中": "Discovery Gate：問題、證據與成功條件成文，需求方確認後才進 Design",
    "🧭規劃中": "完成規劃產物並取得需求方核可",
    "📥Backlog": "認領（線 WIP 須有空位）",
    #: ⚠️ `⏳待執行` 與 `🚧進行中` 是 canonical 明列的**廢止歷史值**（逐字：「向後相容，
    #: 已寫的卡留著，新寫入不得用」）。**保留是刻意的裁斷，不是忘了刪**——廢止約束的是
    #: **寫入端**，本檔是**讀取端**；只要凍結欄位 schema 還留著這兩個選項，看板就寫得出
    #: 它們。兩者皆**不在** `CLOSED_STATUSES`，故帶該值的卡是活卡、必定走到 `gate_of()`，
    #: 刪鍵即等於替一條 canonical 仍認可的值裝上 fail closed。
    "⏳待執行": "執行者進場",
    "🔨執行中": "交付並 handoff 送審",
    "🚧進行中": "交付並 handoff 送審",
    "🔍待查核": "查核者進場並寫入裁決",
    "↩退回": "依 finding 修正後重新送審",
    "✅通過": "需求方授權 merge → 結案（cleanup ＋ 終態寫入）",
    "⏸阻塞": "解除阻塞條件（阻塞對象與解阻後的處置見該卡 Issue 的 handoff 事由）",
    "🚨已升級": "需求方裁定升級去向",
}

#: 不計入「活卡」的交付狀態。終態與已合併不佔排程表。
CLOSED_STATUSES = frozenset({"🏁完成", "🛑已停止", "📦已合併"})

REPO_SLUG = "cpbl-analytics"

#: 被接受的輸入 schema：**容器鍵** → 該 schema 的名稱。辨識以「容器鍵在不在」為準，
#: **不看取到的清單空不空**（見模組 docstring）。新增一種來源就在這裡加一個鍵，
#: 並在 `active_cards` 加一條 `elif`——**不得**改成試讀失敗就換下一個。
SOURCE_SCHEMAS: dict[str, str] = {
    "items": "gh-project-item-list",
    "cards": "wf-cli/state-snapshot/v1",
}

#: `wfcli snapshot` 在 payload 裡自陳的 schema。**逐字比對**：用 v1 的欄名去讀 v2 的
#: payload，與讀錯 schema 沒有兩樣——欄位還在不代表語意沒變。
WF_SNAPSHOT_SCHEMA = "wf-cli/state-snapshot/v1"

#: `wfcli snapshot` 的 `issue_url`。該 schema 沒有 `repository` 欄，repo 只能從這裡取。
_ISSUE_URL = re.compile(r"^https://github\.com/[^/]+/([^/]+)/issues/\d+$")

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


def _known_schemas_text() -> str:
    return "、".join(f"{key!r}（{name}）" for key, name in SOURCE_SCHEMAS.items())


def _self_declared(payload: dict) -> str:
    """payload 自陳的 schema（沒有就回空字串）——只用於失敗訊息的「收到的是什麼」。"""
    declared = payload.get("schema")
    return f"、自陳 schema 為 {declared!r}" if declared is not None else ""


def detect_source(payload: object) -> tuple[str, str]:
    """辨識輸入屬於哪一種 schema，回 `(容器鍵, schema 名稱)`。

    **判準是容器鍵的存在與否**（`DEV-ROADMAP-LINES-SILENT-ZERO1`）：
    `{"items": []}` 與 `{"cards": []}` 是「看板上真的沒有活卡」，該 `exit 0`；
    缺容器鍵是「讀不到活卡」，該 `exit 1`。**把後者也算成 `active_total=0`**
    正是本函式存在的理由——`v9` 的 `payload.get("items", [])` 讓那兩件事看起來一樣。

    兩個容器鍵同時出現一律失敗：**辨識是互斥判定，不做 fallback**。試讀失敗就換
    下一個 schema，等於安靜地換一條路而讀者無從得知走了哪條——與本函式在修的病同族。
    """
    if not isinstance(payload, dict):
        raise CheckFailed(
            f"輸入的最上層不是 JSON object 而是 {type(payload).__name__}——"
            f"預期 {_known_schemas_text()}，fail closed"
        )
    present = [key for key in SOURCE_SCHEMAS if key in payload]
    if len(present) == 1:
        return present[0], SOURCE_SCHEMAS[present[0]]
    if present:
        raise CheckFailed(
            f"輸入同時含 {present} 兩個容器鍵，無法判定是哪一種 schema——"
            "fail closed（辨識是互斥判定，不以優先序挑一個讀）"
        )
    raise CheckFailed(
        "輸入不含任何已知的容器鍵，讀不到活卡——"
        f"收到的最上層鍵為 {sorted(str(k) for k in payload)}{_self_declared(payload)}；"
        f"預期 {_known_schemas_text()}。fail closed："
        "**不得回報 active_total=0**，那會讓「真的零活卡」與「讀不到活卡」無法區分"
    )


def active_cards(payload: dict) -> list[dict]:
    """自狀態面匯出取出本 repo 的活卡。接受兩種 schema，見模組 docstring。

    **必填欄位缺一即 fail closed**（`VERIFIER1-R3-001`）：`v6` 對缺欄位一律以空值
    帶過——缺交付狀態的 item 會被收為 `status=''` 並一路通過 `render` → `reconcile`，
    缺 `content.number` 則產生 `#None` 同樣通過。**兩條都能把不完整的 Project payload
    偽裝成一份可對帳的排程**，而對帳的全部意義就是「這份表反映現況」。

    活卡的判定本身依賴 `status`；`status` 取不到時**無從判斷它是不是活卡**，
    因此不能以「空字串不在 CLOSED_STATUSES」推論它是活的。兩條路徑都要守住這條。
    """
    key, _schema = detect_source(payload)
    container = payload[key]
    if not isinstance(container, list):
        raise CheckFailed(
            f"容器鍵 {key!r} 的值不是陣列而是 {type(container).__name__}——fail closed"
        )
    if key == "items":
        return _active_from_gh_items(container)
    return _active_from_wf_cards(container, payload)


def _active_from_gh_items(items: list) -> list[dict]:
    """`gh project item-list --format json` 的 `items`。"""
    out = []
    for item in items:
        if not isinstance(item, dict):
            raise CheckFailed(f"`items` 內出現非 object 的元素（{type(item).__name__}）——fail closed")
        repo = (item.get("repository") or "").rsplit("/", 1)[-1]
        if repo != REPO_SLUG:
            continue
        number = (item.get("content") or {}).get("number")
        status = _field(item, *_FIELD_KEYS["status"])
        if not status:
            raise CheckFailed(
                f"item（content.number={number}）取不到交付狀態——無從判斷它是不是活卡，"
                "fail closed（不得以「空字串不在終態集合」推論它是活的）"
            )
        if status in CLOSED_STATUSES:
            continue
        card_id = _field(item, *_FIELD_KEYS["card_id"])
        tier = _field(item, *_FIELD_KEYS["tier"])
        missing = [name for name, value in
                   (("卡ID", card_id), ("級別", tier), ("content.number", number))
                   if value in (None, "")]
        if missing:
            raise CheckFailed(
                f"活卡缺必填欄位 {missing}（卡ID={card_id!r}、content.number={number!r}）"
                "——不完整的 payload 不得被當成可對帳的排程，fail closed"
            )
        out.append({"card_id": card_id, "tier": tier, "status": status, "number": number})
    return out


def _active_from_wf_cards(cards: list, payload: dict) -> list[dict]:
    """`wfcli snapshot` 的 `snapshot.json` 的 `cards`（`SnapshotRow` 逐欄 asdict）。

    欄位對應：`card_id`／`tier`／`delivery_status`／`issue_number`，repo 取自
    `issue_url`（該 schema **沒有 `repository` 欄**）。不變量與 `items` 路徑逐條對齊：
    取不到狀態、活卡缺必填欄位、判不出 repo 一律失敗。

    唯一刻意放行的是 `content_type == "DraftIssue"`：draft 不屬於任何 repo，
    與 `items` 路徑「沒有 `repository` 於是不等於 `REPO_SLUG`」的處置一致。
    **沒有 `issue_url` 又不是 draft 則失敗**——否則把一份 `items` 形狀的資料塞進
    `cards` 會被整批靜默跳過，那又是一次靜默零。
    """
    declared = payload.get("schema")
    if declared != WF_SNAPSHOT_SCHEMA:
        raise CheckFailed(
            f"`cards` payload 自陳 schema 為 {declared!r}，本檔只讀 {WF_SNAPSHOT_SCHEMA!r}"
            "——欄位語意可能已變更，fail closed（欄名還在不代表意思沒變）"
        )
    out = []
    for row in cards:
        if not isinstance(row, dict):
            raise CheckFailed(f"`cards` 內出現非 object 的元素（{type(row).__name__}）——fail closed")
        card_id = row.get("card_id") or ""
        url = row.get("issue_url")
        if not url:
            if row.get("content_type") == "DraftIssue":
                continue
            raise CheckFailed(
                f"card（card_id={card_id!r}）沒有 issue_url，而 content_type="
                f"{row.get('content_type')!r} 不是 DraftIssue——無從判斷它屬於哪個 repo，"
                "fail closed（跳過會讓卡從排程表消失，那是不對稱的失效方向）"
            )
        matched = _ISSUE_URL.match(str(url))
        if matched is None:
            raise CheckFailed(
                f"card（card_id={card_id!r}）的 issue_url {url!r} 解析不出 repo——"
                "無從判斷它是不是本 repo 的卡，fail closed"
            )
        if matched.group(1) != REPO_SLUG:
            continue
        status = row.get("delivery_status") or ""
        if not status:
            raise CheckFailed(
                f"card（card_id={card_id!r}）取不到 delivery_status——無從判斷它是不是活卡，"
                "fail closed（不得以「空字串不在終態集合」推論它是活的）"
            )
        if status in CLOSED_STATUSES:
            continue
        tier = row.get("tier") or ""
        number = row.get("issue_number")
        missing = [name for name, value in
                   (("card_id", card_id), ("tier", tier), ("issue_number", number))
                   if value in (None, "")]
        if missing:
            raise CheckFailed(
                f"活卡缺必填欄位 {missing}（card_id={card_id!r}、issue_number={number!r}）"
                "——不完整的 payload 不得被當成可對帳的排程，fail closed"
            )
        out.append({"card_id": card_id, "tier": tier, "status": status, "number": number})
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
    """該卡的「下一個必要 Gate／阻塞條件」——**純由交付狀態導出，無逐卡例外**。

    **未知狀態 fail closed**（`VERIFIER1-R3-001`）：`v6` 靜默導成 `"—"`，於是一個
    本檔不認得的狀態會產生一列看起來正常的表格。狀態詞彙表變更時應該要有人知道。

    **驗證先於產生文字**（`VERIFIER1-CONV-001`）：`v7` 先回傳 `GATE_OVERRIDES` 才檢查
    狀態詞彙，於是**覆寫成了跳過驗證的快速路徑**——一張在覆寫表裡的卡帶著本檔不認得
    的狀態，可以走完 `active_cards → render → reconcile` 而完全不被發現。`v8` 把驗證
    移到覆寫之前修掉了它；`v9` 移除覆寫後**那條旁路在結構上不再存在**（沒有任何分支
    能在檢查之前回傳）。下面的檢查仍是該不變量的唯一守門，**不得改為在查表命中時略過**。

    `card_id` 不參與文字產生，只用於失敗訊息——這正是本函式的契約：**卡的身分不影響
    Gate 欄的內容**。保留參數是為了讓 fail-closed 訊息指得出是哪一張卡。
    """
    if status not in GATE_BY_STATUS:
        raise CheckFailed(
            f"卡 {card_id} 的交付狀態 {status!r} 不在已知詞彙表中——fail closed"
            f"（已知：{sorted(GATE_BY_STATUS)}）"
        )
    return GATE_BY_STATUS[status]


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
        source_key, source_schema = detect_source(payload)
        result = assign(active_cards(payload))
        #: 走了哪一條路徑必須看得見——`--json` 的消費端與 stderr 的讀者都要能判斷
        #: 這次通過是哪一階（`cards` 路徑弱一階，見模組 docstring）。
        #: **刻意不進 `render()`**：區塊內容若隨輸入來源而異，同一份看板就會產生兩種
        #: 區塊，`--check` 便綁死了產生當時用的來源，封存 artifact 的離線重現會失效。
        result["source_schema"] = source_schema
        if args.check is not None:
            reconcile(result, args.check.read_text(encoding="utf-8"))
    except CheckFailed as exc:
        print(f"[roadmap-lines] FAIL：{exc}", file=sys.stderr)
        return 1

    print(f"[roadmap-lines] 輸入 schema：{source_schema}（容器鍵 {source_key!r}）；"
          f"活卡 {result['active_total']}", file=sys.stderr)
    print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else render(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
