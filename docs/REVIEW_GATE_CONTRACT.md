# Review Gate 契約（草案 v0.3，**未生效**；**v0.4 對齊前不得開卡**）

> 🚧 **阻塞：與已生效的 WF-21 審核契約有硬衝突，見 §9。** v0.1–v0.3 是在過期基準
> （`063d12d`）上寫的；`origin/main` 已推進到 `37431a0`，WF-21 於 2026-07-31 10:41 全鏈落地
> （`contract_baseline: review-escalation-v1`），`workflow_ledger.py` 多了 409 行 fail-loud
> 契約驗證。§3.3 的 `review-correction` 與 §3.2 的 `gate_result`／`review_result` 定位
> **會被驗證器擋下或與 canonical 相反**。**兩張卡在 v0.4 對齊前不得 register。**
>
> **狀態：草案。** `scripts/review_prompt.py` 目前仍走 `closes_review_round` 舊路徑。
> 本檔是 `DEV-REVIEW-GATE-CONTRACT1` 與 `DEV-REVIEW-GATE-DECLARE1` 的 **spec 基線 v0.3**；
> 兩卡合併後 §2–§5 併入 [`CONTROL_PLANE_CONTRACT.md`](CONTROL_PLANE_CONTRACT.md) 與
> [`TEMPLATES.md`](TEMPLATES.md)，本檔降為歷史紀錄。
>
> **v0.3 變更（2026-07-31，需求方採納規劃者對五項未決的建議）**：
> **移除 `satisfied_by`**（跨輪繼承不做，一輪內的 gate 必須在該輪內完成，§3.1）、
> Plan Gate 改為**先寫 handoff 再送查核**（修流程不修 schema，§5.3）、
> **merge 順序對調為 CONTRACT1 → DECLARE1**（legacy 相容讓守衛可先無害落地，無空窗，§7）、
> 第二意見維持可推翻、`review_result` 不結構化、卡 ID 用後繼卡；
> 新增 release 後追蹤指標（§8）。
>
> **v0.2 變更（2026-07-31 需求方對 Q2／Q4 裁定）**：遷移策略改為 cutover ＋ preflight
> 強制（§5）、保證邊界五條（§2.1，自由文字**不再**是流程依據）、`review_gates: []`
> 取得語意、盤點升級為分類與計數並新增兩種語式（§6）。
>
> 前身：`DEV-REVIEW-PROMPT-GATE1`（`closes_review_round`，已合併 `9177ee8`）
> 與 `DEV-REVIEW-INDEP-FIELD1`（卡面 `review_independence`，已合併）。

## §1 問題：兩個來源各自宣告「有幾關、跑到哪一關」

前身兩卡各自正確，合起來是雙重狀態來源。`DEV-REVIEW-INDEP-FIELD1` 的 Discovery 提的
「切開維度」（卡面＝應然、event log＝實然、互不為事實來源）沒有解決下面五件事：

**（一）`closes_review_round` 是布林，承載不了「是哪一關」。** 三關的卡，工具只知道
「還沒結束」，不知道下一位查核者該查哪一關，也察覺不到第二關被跳過。

**（二）終局 REJECT 可被一筆追加事件重新開啟，且被錯標為「已通過的中繼關卡」。**
2026-07-31 直接呼叫 `_assert_no_review_supersedes_handoff()` 實測：

```
守衛結果：放行，回傳 gates = [('C-REVIEW-002', 'REJECT（3 blocking）'), ...]
### 本輪已通過的中繼關卡（**不代表本輪查核已結束**）
#### 跨家族查核者
- 結論：REJECT（3 blocking）
```

一筆 REJECT 被印在「**已通過**的中繼關卡」標題下，還附「不要重開已定案的爭點」。

**（三）「多關卡」與「同一關的第二意見複審」在現行 schema 裡長得一模一樣。**
盤點（§6）分出來：同輪多關卡 6 張、同輪第二意見 1 張——**分辨的唯一依據是 actor 的中文**，
那正是 `GUARD1` 三輪被打穿的路線。

**（四）結論欄位的值域不一致（v0.3 修正，原文寫「沒有機器可讀來源」是錯的）。**
WF-21 baseline（2026-07-31 10:41）**之後**的 review 結論必為 `APPROVE`／`REQUEST_CHANGES`
且由 `workflow_ledger.py` 強制；**之前**的 172 筆 review 裡 95 筆帶 `verdict`，值域卻有七種
（`APPROVE`／`REJECT`／`REQUEST_CHANGES`／`✅通過`／`APPROVE_WITH_FINDINGS`／`RETURN`／
`REQUEST_CHANGES_ESCALATED`），另 76 筆完全沒有；`review_result` 只有 65 筆有值。
`delivery_status` 又同時被拿來記別的東西。所以問題是**baseline 前的值域不一致**，
不是「沒有來源」——這一點影響 §3.2 的設計，見 §9.1（二）。

**（五）關卡不一定發生在某一輪之內。** 盤點新查出兩種形態：`OPS-LIVE-SHADOW1` 的
Plan Gate 發生在**第一次 handoff 之前**（3 張）；另有 **7 張卡從未寫過任何 handoff 事件**
卻有 review。兩者在 snapshot 模型下都**無處可掛快照**，必須在契約裡明講怎麼處理（§5.3）。

結論：需要的不是第三個布林，而是**一個有序、有 id、有結果的 gate 模型**，且同一份 gate
定義同時被卡面（宣告）與 event log（進度）使用。

## §2 卡面宣告：`review_gates`

卡面 header（第一個 `## ` 標題之前）**獨立一行**：

```
- review_gates: [design=human, final=cross_family_or_human]
- review_gates: [final=cross_family]     # 單一關卡
- review_gates: []                       # 本卡不直接交付查核（Initiative 專用，見 §5.2）
```

- **有序清單**，順序即關卡先後；長度即關卡數。元素格式 `gate_id=requirement`。
- `gate_id`：`^[a-z][a-z0-9_]{0,23}$`，卡內唯一，**穩定**——一經任何一輪 handoff 快照即
  不得改名、不得改語意；要換語意就換新 `gate_id`。慣用值 `plan`（Plan Gate）、
  `design`（Design Gate／需求方本地人工審）、`final`（終局查核）、`data`（資料紅線複核）。
- `requirement` 值域四值：`context`（新 context／session，不得為執行者本人）、
  `cross_family`（跨模型家族）、`cross_family_or_human`（二擇一）、`human`（需求方人工，
  不得由 AI 代理）。**「兩者皆須」寫成兩個 gate**；「兩者皆須但不限順序」不支援。
- **`ai` 不是值域的一員**，但盤點顯示現實有「先人工審再交**一般 AI** 查核」的卡
  （§6：3 張，且其中 2 張的〈查核〉欄同時寫著「跨模型家族或人工」——互相矛盾）。
  這類卡回填時必須由需求方裁定要哪一個，**不得由工具或執行者代選**；若確實只要求
  「≠ 執行者的新 session」，正確的值是 `context`。
- 寫壞（非清單／`gate_id` 重複或不合 pattern／`requirement` 不在值域／同卡多行）
  一律 **fail loud**。
- 舊欄名 `review_independence`：遷移期同時接受，單元素等價 `[final=<value>]`；
  多元素者 fail loud 要求改寫（現況 0 張）。現存使用者 3 張。

### §2.1 保證邊界（2026-07-31 需求方裁定，Q4）

1. **`review_gates` 是「本輪要求什麼」的權威來源。**
2. **handoff snapshot 是該輪不可變的流程基線**（§3.1）。
3. **review event 的 `gate_id` 是「完成哪一關」的留痕**（§3.2）。
4. **工具不能可信驗證 reviewer 的真實模型家族或人類身分。** 它只顯示宣告值與 actor
   字串，並**明講這是人工核對輔助，不宣稱已自動驗證身分**；不據此擋任何流程。
5. **欄位與舊〈查核〉自由文字衝突時，以結構化欄位決定流程**；自由文字只作說明。

> 第 5 條**推翻**了現行 `review_prompt.py` 輸出的「卡面〈查核〉欄原文（**以此為準**）」
> 與「卡面若要求得比下限嚴……一律以卡面為準」。cutover 後那兩句必須改寫：
> 〈查核〉欄仍**原文照登**（人可讀），但**不再是流程依據**。這是 v0.2 相對
> `DEV-REVIEW-INDEP-FIELD1` 的**行為變更**，不是措辭調整。

### §2.2 Preflight（新增工具）

`review_gates` 的驗證不能等到產生查核提示詞才做——那時 handoff 已經寫進 append-only
log 了。新增 preflight：**寫 handoff event 之前**執行，驗卡面欄位合法、產生要寫進事件的
snapshot、並在缺欄或寫壞時**擋下 handoff**。

```bash
uv run python scripts/review_gate_preflight.py <CARD_ID>     # 印出待寫入的 snapshot JSON
uv run python scripts/review_gate_preflight.py <CARD_ID> --check   # 只驗證，非 0 即擋
```

Preflight 失敗時**不得退化為 tier 下限或自由文字人工猜測**（§5.1）。

## §3 Event schema

### 3.1 `handoff`：快照該輪的 gates

```json
{
  "event_id": "UX-X-HANDOFF-006",
  "card_id": "UX-X",
  "type": "handoff",
  "state_version": 6,
  "source_sha": "…40 字元…",
  "review_gates": [
    {"gate_id": "design", "requirement": "human"},
    {"gate_id": "final",  "requirement": "cross_family_or_human"}
  ]
}
```

- 由 sender 在寫 handoff 時**從卡面快照**（經 §2.2 preflight 產生）。
- **快照是該輪不可變的流程基線**：卡面日後被改都不重解已發生的輪次。這不是假想——
  `UX-LIVE-GAME1` 的〈Design〉欄在 2026-07-30 從「Design Gate 待需求方核可」被就地改寫成
  「2026-07-30 需求方核可 live-only v1」，**要求本身消失**（盤點在 `81bcd4d` 命中它、
  在 HEAD 不命中，差異就是這一張）。
- **一輪內的 gate 必須在該輪內完成；新 handoff 一律從第一關重來，不繼承任何已通過的
  gate。** v0.2 曾設計 `satisfied_by` 讓 handoff 指名承接前一輪的 review，v0.3 移除它：
  - 它唯一的支撐案例是 `UX-ENTITY-LINKS3`（人工審 → 新 handoff → 跨家族），而那個中間的
    handoff 是 Coordinator 為了「轉交下一關」補的——**在 gate 模型裡關卡靠 `gate_id` 推進，
    那個 handoff 根本不需要存在**。支撐案例在新模型下自己消失了。
  - 另兩個曾被引為理由的形態（Plan Gate 型、孤兒 review）改由 §5.3 的流程規則處理。
  - 它是全份契約最容易寫錯的欄位（要驗同卡、同 `gate_id`、`approve`、跨輪且不得回指
    更早的輪次），為一個不存在的需求付這個複雜度不划算。
  - **純新增欄位，日後真的再發生跨輪繼承時補上不需任何遷移**——現在不做不是關門。
- 欄位缺席 → 該輪走 §5.4 legacy 解讀（僅限 cutover 前的 handoff）。
- 快照與卡面當前值不一致時：**以快照為準**，提示詞並列印出、不擋、工具不仲裁。

### 3.2 `review`：記錄本次完成的 gate

```json
{
  "event_id": "UX-X-REVIEW-007",
  "type": "review",
  "gate_id": "design",
  "gate_result": "approve",
  "review_result": "APPROVE（人工審／Design Gate 階段；跨家族查核尚未進行）"
}
```

- `gate_id` 必填（本輪 handoff 有快照時），**須存在於該輪快照**，否則 fail loud。
- `gate_result` 必填，enum **只有** `approve` 與 `request_changes`。
- `review_result` 維持自由文字，**只供人閱讀，不參與任何判定**。
- **`closes_review_round` 廢止**；未來事件若仍帶該欄位 → fail loud 並指向本節。

### 3.3 `review-correction`：更正錯誤事件的唯一路徑

```json
{
  "event_id": "UX-X-REVIEW-CORRECTION-009",
  "type": "review-correction",
  "corrects_event_id": "UX-X-REVIEW-007",
  "corrected": {"gate_id": "final", "gate_result": "approve"},
  "reason": "轉錄時誤植 gate_id，原文查核的是終局關卡",
  "reopens_round": false
}
```

- 只能指向**同一輪**較早的 `review` 事件。
- **一個 target 只能被更正一次**；correction 不得指向 correction。**這條消滅
  latest-wins**——沒有「以最新一筆為準」，就沒有「再追加一筆就翻盤」。
- correction **本身永不完成任何 gate**（型別不同，不進 gate 完成集合）。
- `corrected` 帶新的 `gate_id`／`gate_result`，或 `{"voided": true}`（該筆作廢）。
- **若更正會讓一輪從 `changes_requested` 變回 open，必須顯式帶 `reopens_round: true`
  ＋ `reason`**；缺旗標 → fail loud。重開可以，但**不能是副作用**。
- 提示詞須完整印出 correction 鏈；`gate_result: request_changes` 的事件
  **永遠不得出現在「已通過的關卡」段落**。

### 3.4 驗證範圍

**最新 handoff 之後的每一筆 `review` 與 `review-correction` 逐筆驗證**型別、`gate_id` 是否
在快照內、`gate_result` 是否在 enum、correction target 是否合法。較早的 malformed 事件
不得被後續事件掩蓋。

> 對照現況（2026-07-31 實測）：`closes_review_round` 的布林檢查**已經**涵蓋該卡每一筆
> review（含前幾輪），這點現行實作正確；**未涵蓋的是 `corrects_event_id`**——上一輪一筆
> `corrects_event_id: 99`（int）可完全不被檢查地通過。新契約一併蓋掉。

## §4 狀態轉移表

一「輪」＝ 一筆 `handoff` 起，至該輪終結或下一筆 `handoff` 止。狀態
`open(pending=g)`／`passed`／`changes_requested`；`pending` 是快照順序中第一個尚未
`approve` 的 gate。**新 handoff 一律重置為第一關**（§3.1：不繼承）。

| 現態 | 事件 | 條件 | 新態 | `review_prompt.py` 行為 |
|---|---|---|---|---|
| （無 handoff） | — | — | — | 拒絕：尚未交付查核 |
| 任意 | `handoff`（帶快照） | preflight 通過 | `open(gates[0])` | 放行；印出全部 gate、標明 pending 是哪一關 |
| 任意 | `handoff`（無快照） | cutover 前 | `open(legacy)` | 放行（§5.4） |
| 任意 | `handoff`（無快照） | cutover 後 | — | **preflight 擋在寫入前**；事後遇到則 fail loud |
| `open(g)` | `review(gate_id=g, approve)` | g 是 pending | 還有未完成 gate → `open(下一關)`；否則 `passed` | 放行並帶出已通過關卡；`passed` 則拒絕並指示接 merge／結案 |
| `open(g)` | `review(gate_id=j, approve)` | j 已完成（第二意見） | 不變 | 放行；列為附加意見，不推進 |
| `open(g)` | `review(gate_id=j, approve)` | j 在快照中但尚未輪到（跳關） | 不變 | **fail loud** |
| `open(g)` | `review(任一快照內 gate, request_changes)` | — | `changes_requested` | 拒絕：退回原執行者，修正後補**新 handoff** |
| 任意 | `review(gate_id 不在快照)` | — | — | **fail loud** |
| 任意 | `review`（缺 `gate_id` 或 `gate_result`，該輪有快照） | — | — | **fail loud** |
| `passed` ／ `changes_requested` | `review`（任何） | — | 不變 | **fail loud**：本輪已終結，普通 review 不得重開；要重來請補新 handoff |
| 任意 | `review-correction`（同輪、合法、target 未被更正過） | — | 依更正後**重算整輪** | 依重算結果；完整印出 correction 鏈 |
| `changes_requested` | `review-correction`（重算後變 open） | 缺 `reopens_round: true` | 不變 | **fail loud** |
| `changes_requested` | `review-correction`（重算後變 open） | 帶 `reopens_round: true` ＋ `reason` | `open(…)` | 放行，**置頂**印出重開告示與原 REJECT 全文 |
| 任意 | `review-correction`（跨輪／指向自己／指向 correction／target 已被更正／型別錯） | — | — | **fail loud** |
| `open(legacy)` | `review`（任何） | legacy 輪 | `terminated(legacy)` | 拒絕——**與現行行為逐字相同** |

## §5 Migration（2026-07-31 需求方裁定，Q2）

### 5.1 cutover 與缺欄

- **cutover ＝ `DEV-REVIEW-GATE-DECLARE1` 合併之日**，寫進契約與 `TEMPLATES.md`。
- **新卡自 cutover 起強制填 `review_gates`。**
- **活卡不做一次性全面回填**，但**在下一次 handoff 前必須補齊**，由 §2.2 preflight 驗證；
  補什麼值**由需求方逐張裁定**，執行者與工具不得推定。
- **cutover 後缺欄 → preflight fail，擋下 handoff。不得退化成 tier 下限，也不得回退成
  自由文字人工猜測。**（這與 cutover 前的「明示缺欄＋tier 下限＋原文照登」不同：
  cutover 前是**沒有欄位可讀**，cutover 後是**該填而沒填**。）
- **封存卡與 cutover 前的事件不回填、不改寫。**

### 5.2 Initiative 與不直接交付查核的卡

- Initiative 若不直接交付查核，**明示 `review_gates: []`**——空清單是**顯式宣告**
  「本卡不直接交付查核」，不是「沒寫」。
- **不得用缺欄暗示不需查核。** 缺欄一律 preflight fail。
- 宣告 `[]` 的卡若真的出現 `handoff` 事件 → **preflight fail**：要交付查核就必須先宣告關卡。
  （查證：全庫 `INIT-*` 的 review 事件為 0 筆，此路徑目前是防呆而非常態。）

### 5.3 沒有 handoff 可掛快照的兩種歷史形態

盤點查出 **3 張**卡的 review 早於第一次 handoff（Plan Gate 型），另有 **7 張**卡
**從未寫過任何 handoff 事件**卻有 review。cutover 後兩者用同一條規則處理，
**修的是流程不是 schema**：

- **查核必須有一輪可依附：cutover 後不得再出現沒有對應 handoff 的 review。**
  preflight 與守衛都以此為前提。
- **Plan Gate 是一次交付，就先寫 handoff 再送查核。** `OPS-LIVE-SHADOW1` 的 Plan Gate
  在第一次 handoff 之前，成因是「Plan 不算交付」這個習慣，不是 schema 缺欄位——
  Plan 有 `source_sha`（卡面修訂）、有 evidence、有查核者，它就是一次 handoff。
  Plan Gate 這一關照樣進 `review_gates`（例 `[plan=cross_family, final=cross_family]`），
  在它自己那一輪完成。
- 既有 10 張屬歷史，**不回填、不改寫**。

### 5.4 Legacy 解讀

- handoff 無 `review_gates` 快照（僅限 cutover 前）→ 該輪視為**單一隱含關卡**，
  **任一 review 事件即終結本輪**，拒絕訊息與現行**逐字相同**。
- 既有事件中 `review_gates` 0 筆、`closes_review_round` **0 筆**、
  `corrects_event_id` 3 筆（皆在 `correction` 型別事件上，非 review）——
  **全庫 100% 走 legacy**，行為零變更，須由回歸腳本窮舉證明（§7）。
  母體以執行當時的 `origin/main` 為準（`37431a0`：892 筆事件／121 張卡／172 筆 review；
  v0.1–v0.3 引用的 887／119／171 是 `063d12d` 的數字，見 §9.4）。

## §6 多關卡盤點（可重現，含分類與計數）

腳本 [`../scripts/review_gate_inventory.py`](../scripts/review_gate_inventory.py)，完整輸出
[`discovery/review-gate-inventory-2026-07-31.md`](discovery/review-gate-inventory-2026-07-31.md)。
應然信號 A（正文順序語式，含「交給誰」判別）、B（〈Design〉欄待跑 Gate）、
**E（`## Plan Gate` 章節標題，iteration 1 沒有這個信號，整張 `OPS-LIVE-SHADOW1` 因此在
視野外）**、D（結構化欄位長度 > 1）、**F（〈查核〉欄與正文互相矛盾）**；
實然信號 C1（同輪多筆 review，再分多關卡／第二意見）、C2（跨輪不同性質關卡）、
C3（handoff 之前的 review，再分 Plan Gate 型／孤兒 review）。

HEAD（122 張卡、887 筆事件）：**命中 32 張，實質 30 張**。分類與計數：

| 卡面宣告的關卡型態 | 張數 |
|---|---|
| Plan／Design Gate → 實作查核 | 14 |
| 人工審 → 跨家族查核 | 3（`UX-DESIGN-CONFORM1`、`UX-ENTITY-LINKS1`、`UX-ENTITY-LINKS2`） |
| 人工審 → 一般 AI 查核（未要求跨家族） | 3（`UX-TEAM-HOTZONE1`、`UX-TEAM-RECORDS1`、`UX-TEAM-STYLE1`） |

| event log 的實然型態 | 卡數 |
|---|---|
| 全卡沒有任何 handoff 事件，review 無所依附 | 7 |
| 同輪多關卡（不同性質的查核者） | 6 |
| 有 handoff 但 review 更早（Plan Gate 型） | 3 |
| 同輪第二意見（同性質查核者再查一次） | 1 |
| 跨輪不同性質關卡 | 1（`UX-ENTITY-LINKS3`） |

**這三種流程不得被寫成同一種**：`human → cross_family`、`human → 一般 AI`、
`plan → implementation` 的 requirement 與 `gate_id` 都不同。另有 **2 張卡自我矛盾**
（信號 F：`UX-TEAM-HOTZONE1`、`UX-TEAM-RECORDS1` 的〈查核〉欄寫「跨模型家族或人工」、
正文寫「交 AI 查核」）——回填時**必須由需求方裁定**，這正是 §2.1 第 5 條
「欄位決定流程、自由文字只作說明」要處理的情形。

**分類欄是建議，待人工確認**：它讀中文自由文字，**不得被守衛／preflight／gate 判定
消費**。盤點的用途是把要求搬進結構化欄位，不是當判定依據。

## §7 受影響檔案與測試計畫

### 落地順序：CONTRACT1 → DECLARE1（v0.3 對調）

**守衛先行、宣告在後**，理由是 legacy 相容讓第一步可以無害落地：

- **CONTRACT1 先合併**：狀態機就位，但全庫沒有任何 snapshot，**100% 走 legacy → 行為零變更**
  （窮舉回歸差異 0 就是它的驗收）。DECLARE1 一合併，snapshot 開始出現，狀態機**自動生效**，
  中間**沒有空窗**。
- 反過來（DECLARE1 先）會製造空窗：卡面與事件都已帶 gate，守衛卻仍用 `closes_review_round`
  判定，多關卡的卡在空窗期照樣被誤擋——等於把現在這個 bug 多留一段時間。
- CONTRACT1 **不依賴** DECLARE1 的產出，只依賴本檔的 schema 定義；它的測試用 fixture，
  不需要真實卡片帶 snapshot。

### 受影響檔案

`DEV-REVIEW-GATE-CONTRACT1`（第一步）：`scripts/review_prompt.py`
（`_assert_no_review_supersedes_handoff()`／`_closes_review_round()` → `round_state()`；
`review_gates_block()` 改吃 gate 狀態；`independence()` 改讀快照並標明 pending 關卡；
**移除「以卡面〈查核〉欄為準」的兩處措辭**，改為 §2.1 第 5 條）、
`tests/test_review_prompt.py`、`docs/CONTROL_PLANE_CONTRACT.md` 的事件欄位定義處。

`DEV-REVIEW-GATE-DECLARE1`（第二步）：`docs/TEMPLATES.md`（`review_independence` 段改寫）、
`docs/CONTROL_PLANE_CONTRACT.md`（`closes_review_round` 條目換成 gate 契約＋保證邊界）、
`docs/HANDOFF_CONTRACT.md`（sender 快照責任、receiver 確認 pending gate）、
**新增 `scripts/review_gate_preflight.py` ＋ `tests/test_review_gate_preflight.py`**、
`scripts/review_gate_inventory.py` 納管＋測試、活卡按需回填。

### 測試計畫（性質，不是示範）

**gate 序列**：單 gate approve → `passed`；兩 gate 第一關 approve → 放行且 pending 指向
第二關；第二關 approve → `passed`；**任一關 request_changes → 終結，後續普通 review 一律
fail loud**（含「中繼關卡之後才出現終局 REJECT」與「終局 REJECT 之後追加任何 review」）。

**不繼承（v0.3）**：第一關 approve 之後出現新 handoff → **pending 回到第一關**，
前一輪的 approve 不帶過來；事件若帶 `satisfied_by` → **fail loud**（該欄位不在契約裡，
默默忽略等於讓寫的人以為它生效了）。

**gate_id 驗證**：不在快照內、跳關 approve、缺 `gate_id`、缺 `gate_result`、
`gate_result` 不在 enum、型別錯——逐一 fail loud，且**錯誤事件位於本輪較早位置時同樣
fail loud**。

**correction**：合法更正（改 gate_id／改 gate_result／void）重算正確；correction 本身不
完成 gate；同一 target 被兩筆 correction 指名 → fail loud；指向 correction／指向自己／
跨輪 → fail loud；**由 `changes_requested` 變回 open 而缺 `reopens_round` → fail loud**；
帶旗標時放行且輸出置頂告示。

**preflight**：合法卡面產生正確 snapshot；缺欄 → 非 0 退出且**訊息不提供任何 fallback**；
`gate_id` 重複／不合 pattern／`requirement` 不在值域／多行 → fail；`[]` 的卡通過 `--check`
但**寫 handoff 時 fail**。

**保證邊界**：輸出必須同時出現宣告值與最近 review 的 actor，且**明寫「工具無法驗證身分、
這是人工核對輔助」**；輸出中**不得**出現「以卡面〈查核〉欄為準」這類把自由文字當成流程
依據的措辭（以字串斷言鎖住）。

**legacy**：無快照的 handoff ＋ 任一 review → 拒絕訊息與現行**逐字相同**（golden 比對）。

**窮舉回歸（紅線）**：對全庫 887 筆事件跑新舊兩版判定，逐卡逐輪比對，**差異數 0**，
證據由腳本產生，不得以人工聲明承載。

## §8 已裁定事項與 release 後追蹤

**2026-07-31（ruan6047）**：Q2 遷移策略（§5.1／§5.2）、Q4 保證邊界（§2.1）。

**2026-07-31 第二批（ruan6047 採納規劃者建議）**，五項全數定案：

1. **卡 ID：用後繼卡**，不 reopen `DEV-REVIEW-PROMPT-GATE1`／`DEV-REVIEW-INDEP-FIELD1`。
   兩張皆 🏁完成、封存、結案對帳完成；reopen 會讓 `state_version` 接在 release 之後，
   Ledger 與封存索引都要回頭改，而**歷史沒有錯**——兩卡各自解決了當時的問題，
   是合起來才成為雙重來源。卡面以 `前身：` 欄指回。
2. **`satisfied_by`：不做**（§3.1 已移除）。唯一支撐案例在 gate 模型下自己消失，
   純新增欄位，日後真的需要再補、不需遷移。
3. **第二意見維持可推翻**（任何 gate 的 `request_changes` 終結本輪）。規則要吻合已經在跑的
   處置（`LIVE-GAME-BACKEND1` APPROVE 後複審翻 REJECT，卡確實退回）；反方向會讓第一個
   APPROVE 鎖死結論。
4. **`review_result` 不結構化**。`gate_result` 已承載判定，自由文字留給人讀；
   106 筆缺值是 cutover 前的歷史，不追、不回填。多一個必填欄位只是增加寫事件的摩擦，
   而摩擦正是這批卡片一直在製造的問題。
5. **順序：CONTRACT1 → DECLARE1**（§7 已改寫）。

### Release 後追蹤（不是驗收條件，見 §9 對 WF-21 的調整）

`closes_review_round` 在全庫 887 筆事件裡**用過 0 次**——`DEV-REVIEW-PROMPT-GATE1` 交付的
機制從來沒被實際使用。本契約比它大得多，有重蹈覆轍的風險：機制建好但沒人寫那些欄位。

因此 DECLARE1 合併後**第一個月追蹤一個可觀測事實：新寫的 handoff 是否 100% 帶 snapshot**。
preflight 若真的擋在寫入路徑上，這個數字必然是 100%；不是 100% 就代表有人繞過 preflight
手寫事件，那是機制沒落地的**早期訊號**，而不是等半年後才發現又是死欄位。
查法：`jq -r 'select(.type=="handoff" and .occurred_at > "<cutover>") | .review_gates == null'
docs/control-plane/events.jsonl | sort | uniq -c`。

## §9 與 WF-21 的介面與衝突（2026-07-31 稽核，**v0.4 對齊前不得開卡**）

**v0.1–v0.3 是在過期基準上寫的。** 規劃期間工作樹停在 `063d12d`，而 `origin/main` 已推進到
`37431a0`：WF-21「審核退回分流與升級計數去誤觸發」已於 2026-07-31 10:41 全鏈落地
（canonical `b113617` → adapter merge `f86bd5e` → one-shot marker
`WF21-ADOPT-BASELINE-001`，`contract_baseline: review-escalation-v1`）。
`scripts/workflow_ledger.py` 因此多了 409 行 **fail-loud 契約驗證**，
`scripts/review_prompt.py` 的〈產出格式〉段也已改寫。本節逐項列出衝突，
**在完成 v0.4 對齊之前，`DEV-REVIEW-GATE-CONTRACT1` 與 `DEV-REVIEW-GATE-DECLARE1` 不得 register**。

### 9.1 硬衝突（寫下去會被 `--check` 擋）

**（一）`review-correction` 型別已被 WF-21 佔用。** 已合併的驗證器要求該型別必填
`escalation_epoch`、既存的 `target_attempt_id` 與非空 `finding_updates`（每項是 §2 的十欄
finding schema），canonical 並明文「此專用 type **不得與其他 lifecycle correction 混用**」。
本契約 §3.3 用同名型別卻帶 `corrects_event_id`／`corrected`／`reason`／`reopens_round`——
寫下去 `workflow_ledger.py --check` 直接 fail。
→ **v0.4：改名 `gate-correction`**，或把 gate 更正併入 WF-21 的 `finding_updates` 流程。

**（二）`review_result` 已經是 enum，不是自由文字。** 驗證器強制 baseline 後的 review
`review_result ∈ {APPROVE, REQUEST_CHANGES}`，並強制 `attempt_id` ＝
`<card>-e<epoch>-<40 字 SHA>`、`preflight_passed=true`、結構化 `findings`、
adapter 推導的 `counts_toward_escalation`。本契約 §3.2／§8 第 4 項寫「`review_result`
維持自由文字、不參與判定」並另立 `gate_result` enum——**與已生效的契約相反且重複**。
→ **v0.4：刪掉 `gate_result`，結論沿用 `review_result`；review 只新增 `gate_id` 一個欄位。**
這讓本契約的 schema 變小，是好消息。

### 9.2 語意衝突（不擋寫入，但兩份規則會打架）

**（三）「一輪」的識別鍵不同。** 本契約：一輪＝一筆 handoff 到終結。WF-21：attempt＝
`(card_id, escalation_epoch, source_sha)`，且**同一 SHA 的多位 reviewer findings 合併為一個
attempt**（T4 跨家族＋人工 sign-off 明文允許）。本契約 §4 的「任一 request_changes 立即終結、
其後任何 review fail loud」會**擋掉 WF-21 明文允許的第二位 reviewer**。
→ **v0.4：終結判定改為在 attempt（同 SHA）合併之後**。這與 gate 模型天然對應——
同 SHA、同 `gate_id` ＝ 同一關的合併意見；不同 `gate_id` ＝ 不同關卡。

**（四）preflight 已經存在，不該再造一套。** WF-21 定義了 `preflight-failed` 事件與
`preflight_passed` 欄位，必查項甚至已含「**規定在跨家族查核前完成的人工檢查**」——那正是多關卡。
`review_prompt.py` 也已改為要求查核者先分類 `PREFLIGHT_FAILED`／`BLOCKED`／`REVIEW_INVALID`
再給結論。
→ **v0.4：`scripts/review_gate_preflight.py` 降為 WF-21 preflight 的一個檢查項**，
失敗寫 `preflight-failed` 事件，不自成一套非 0 退出的擋門機制。

**（五）cutover 機制重複。** WF-21 用 one-shot `contract-baseline` event 當唯一 cutover marker
（驗證器強制只能出現一次、只能由該型別啟用）。本契約 §5.1 把 cutover 定義成「DECLARE1 合併
之日」寫在文件裡。
→ **v0.4：改用 `contract-baseline` event（例 `review-gate-v1`）**；須先確認驗證器能否支援
第二個 baseline 名並存（目前 `REVIEW_CONTRACT` 是寫死的常數）。

### 9.3 排程衝突

**（六）同區域已有一張在途卡。** WF-21 的 minor 收尾 `DEV-REVIEW-DEACCEPT-TRAIL1`
（📥Backlog，2026-07-31 開）處理「plain-review 翻案缺 correction 留痕」，動的正是
review-correction 語意。需求方 2026-07-30 曾指示「WF-21 escalation 實作須等 GATE1 任務鏈收束
後再執行」，`DEV-REVIEW-INDEP-FIELD1-RELEASE-016` 也宣告「WF-21 escalation 實作解鎖」——
**現在反過來，本契約要等 WF-21 的收尾卡定位清楚**，否則兩邊在同一段語意上互寫。

### 9.4 本契約前幾版的事實錯誤（一併更正）

- §1（四）寫「判定結果沒有機器可讀來源」——**過期**。baseline 後結論必為 enum 且由驗證器強制；
  baseline 前也有 **95／172 筆**帶 `verdict`（值域不一致：`APPROVE`／`REJECT`／
  `REQUEST_CHANGES`／`✅通過`／`APPROVE_WITH_FINDINGS`／`RETURN`／`REQUEST_CHANGES_ESCALATED`）。
  正確說法是「**baseline 前的結論欄位值域不一致、76 筆完全缺**」，不是「沒有來源」。
- §5.4 寫「全庫 887 筆事件」——現為 **892 筆／121 張卡／172 筆 review**（`37431a0`）。
  §6 盤點數字在新基準重跑後不變（命中 32／實質 30），母體 123 張卡。
- 相容性一項**沒有變**：驗證器只做必填欄位檢查，不禁止額外欄位，
  所以 handoff 加 `review_gates`、review 加 `gate_id` 屬**additive，不會被擋**。
