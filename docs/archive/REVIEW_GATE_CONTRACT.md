# Review Preflight Gate 契約（草案 v1.0，**未生效**）

> **狀態：草案，等 `DEV-REVIEW-PREFLIGHT-GATE1` 執行並通過查核後生效。**
> 本檔是該卡的 **spec 基線 v1.0**；合併後 §2–§5 併入
> [`CONTROL_PLANE_CONTRACT.md`](CONTROL_PLANE_CONTRACT.md) 與 [`TEMPLATES.md`](TEMPLATES.md)，
> 本檔降為歷史紀錄。
>
> **v1.0 是路線改寫，不是版本遞增。** v0.1–v0.3 設計的是「review 事件帶 `gate_id` 的 gate
> 狀態機」，那份設計建立在過期基準上，與 2026-07-31 生效的 WF-21 審核契約硬衝突（稽核逐項見
> §9）。需求方 2026-07-31 對抗式質詢後改採**前置關卡＝preflight 條件**：canonical 已經替這件
> 事選好路，我們補的是它沒定義的那一半。連帶效果是 `gate_id`、`gate_result`、gate 狀態機、
> `review-correction` 撞名**全部不必存在**。
>
> 前身：`DEV-REVIEW-PROMPT-GATE1`（`closes_review_round`，`9177ee8`）、
> `DEV-REVIEW-INDEP-FIELD1`（卡面 `review_independence`，`c29657b`），兩張皆 🏁完成。

## §1 問題：canonical 要求了一件事，卻沒有人能機器可讀地宣告它

WF-21 把 canonical 的流程改成 `執行與自測 → {Review preflight} → 獨立查核`，preflight 的必驗項
**明文包含**「Gate／依賴狀態」與「規定在跨家族查核前完成的**人工檢查**」。

**但 canonical 沒有定義那些人工檢查要怎麼被宣告。** 現況它們散在四種互不相交的中文語式裡
（§6 盤點）：正文順序語式、〈Design〉欄、`## Plan Gate` 章節標題，以及**根本沒寫在該寫的地方**
——`UX-TEAM-STYLE1` 的〈查核〉欄只寫「≠ 執行；T3 一般查核」，完全看不出它的驗證段要求先人工審。
preflight 要驗這一項，只剩下讀中文一途，而**從中文自由文字推流程門檻已被連續三輪打穿**
（`DEV-REVIEW-PROMPT-GUARD1`：否定句、引文、條件句、詞邊界）。

四件已證實的事實構成本契約的必要性：

**（一）要求本身會從卡面消失。** `UX-LIVE-GAME1` 的〈Design〉欄在 2026-07-30 從「Design Gate 待
需求方核可」被就地改寫成「2026-07-30 需求方核可 live-only v1」。盤點腳本在 `81bcd4d` 命中它、
在 `37431a0` 不命中，差異就是這一張。**只要要求只活在卡面，歷史就會被日後的編輯重新解釋**
——所以送審那一刻必須快照。

**（二）同一張卡的兩處要求會互相矛盾。** `UX-TEAM-HOTZONE1`、`UX-TEAM-RECORDS1` 的〈查核〉欄
寫「跨模型家族或人工」，正文卻寫「交 AI 查核」（§6 信號 F）。沒有結構化欄位時，preflight 要
驗哪一個是無解的。

**（三）三種前置關卡流程在現實中都存在，且不是同一種**：human → cross-family（3 張）、
human → 一般 AI（3 張）、Plan／Design Gate → implementation（14 張）。把它們寫成同一種，
就是把「需求方親自審過」和「另一個 AI 看過」混為一談。

**（四）前一版的機制從來沒被用過。** `closes_review_round`／`corrects_event_id` 在全庫
892 筆事件裡使用次數是 **0**，而它們帶著兩個實測可重現的缺陷（終局 REJECT 可被一筆指名它的
更正重開；重開後那筆 REJECT 會被印在「已通過的中繼關卡」標題下）。**移除比修好。**

## §2 卡面宣告

### 2.1 `review_preflight_gates`（新欄位）

卡面 header（第一個 `## ` 標題之前）**獨立一行**：

```
- review_preflight_gates: [design=human]                      # 送審前需求方人工審
- review_preflight_gates: [plan=cross_family]                  # 送審前跨家族 Plan Gate
- review_preflight_gates: [design=human, data=cross_family]    # 兩道，依序
- review_preflight_gates: []                                   # 沒有前置關卡（必須明寫）
```

- **有序清單**，順序即先後；元素格式 `gate_id=requirement`。
- `gate_id`：`^[a-z][a-z0-9_]{0,23}$`，卡內唯一，**穩定**——一經快照即不得改名或改語意；
  要換語意就換新 id。慣用值 `plan`、`design`、`data`。
- `requirement` 值域沿用 `review_independence` 的四值：`context`、`cross_family`、
  `cross_family_or_human`、`human`。「兩者皆須」寫成兩個 gate。
- **`[]` 是顯式宣告「本卡沒有前置關卡」**，與缺欄不同（§5.2）。
- 寫壞（非清單／`gate_id` 重複或不合 pattern／`requirement` 不在值域／同卡多行）一律 fail loud。

### 2.2 `review_independence`（沿用，不動）

`DEV-REVIEW-INDEP-FIELD1` 已上線的欄位維持原樣，表達**終局那一關**的查核者資格，
現有 3 張卡不需遷移、不需改名。兩個欄位的分工是：

- `review_preflight_gates` ＝ **送審前必須先完成什麼**（preflight 驗，不通過就不派 reviewer）。
- `review_independence` ＝ **誰有資格做終局查核**（提示詞照登，不擋流程）。

### 2.3 保證邊界（2026-07-31 需求方裁定）

1. 兩個欄位是各自維度的**權威來源**；handoff 快照是該輪**不可變的流程基線**。
2. **工具不能可信驗證 reviewer 的真實模型家族或人類身分。** 它只顯示宣告值與 actor 字串，
   並明講這是**人工核對輔助，不宣稱已自動驗證身分**。
3. **欄位與舊〈查核〉自由文字衝突時，以結構化欄位決定流程**；自由文字只作說明。
   > 這推翻現行 `review_prompt.py` 輸出的「卡面〈查核〉欄原文（**以此為準**）」與「卡面若要求
   > 得比下限嚴……一律以卡面為準」兩處措辭。〈查核〉欄仍原文照登（人可讀），但不再是流程依據。
   > 這是**行為變更**，不是措辭調整。

## §3 Event schema（**不新增任何 event type**）

### 3.1 `handoff`：快照本輪的前置關卡與其結果

```json
{
  "event_id": "UX-X-HANDOFF-006",
  "card_id": "UX-X",
  "type": "handoff",
  "state_version": 6,
  "source_sha": "…40 字元…",
  "preflight_passed": true,
  "preflight_gates": [
    {"gate_id": "design", "requirement": "human",
     "actor": "ruan6047", "occurred_at": "2026-07-29T18:09:35+08:00",
     "decision": "approve",
     "evidence": "本地環境人工審：每點 block→text-only 觀感確認"}
  ]
}
```

- 由 sender 在寫 handoff 時，以 `review_prompt.py --preflight` 產生（§7）。
- 快照的來源是卡面 `review_preflight_gates`；**卡面日後被改不重解已發生的輪次**（§1（一））。
- `decision` 只有 `approve`（未通過就不會有 handoff，見 3.2）。
- `preflight_passed: true` 是 canonical `review-escalation.md` §5 對 preflight pass event 的要求。
- **快照與卡面當前值不一致時以快照為準**，提示詞並列印出、不擋、工具不仲裁。

### 3.2 `preflight-failed`：前置關卡未過（WF-21 既有型別）

```json
{
  "type": "preflight-failed",
  "preflight_passed": false,
  "failure_reasons": ["卡面 review_preflight_gates 缺欄", "design 關卡尚未完成"],
  "preflight_gates": [
    {"gate_id": "design", "requirement": "human", "decision": "request_changes",
     "actor": "ruan6047", "occurred_at": "…", "evidence": "…"}
  ]
}
```

依 canonical：`preflight-failed` **不建立 review event、不派 reviewer、不遞增 iteration、
不計 escalation**。前置人工關卡退回走這條路，而不是寫一筆 review。

### 3.3 `review`：完全照 WF-21，本契約不加任何欄位

review 事件的必填欄位（`attempt_id`／`escalation_epoch`／`preflight_passed`／
`review_result` enum／結構化 findings／`counts_toward_escalation`）全部以 canonical
[`review-escalation.md`](../.ai-workflow/templates/review-escalation.md) 為準。
**本契約不碰 review 事件**，因此不會與 WF-21 的 attempt 模型（同 SHA 多 reviewer 合併為一次）
產生任何交互。

### 3.4 廢止欄位

`closes_review_round` 與 review 事件上的 `corrects_event_id` **廢止並從程式移除**。
baseline 後的 review 若仍帶這兩個欄位，`workflow_ledger.py --check` **fail loud** 並指向本節
——寫的人以為自己表達了「這一輪還沒結束」而實際沒有，那種靜默就是這批卡一直在治的病。
cutover 前的歷史不受影響（全庫使用次數為 0）。

## §4 狀態轉移

| 現況 | 動作／事件 | 條件 | 結果 |
|---|---|---|---|
| 🔨執行中 | 跑 `--preflight` | 卡面缺 `review_preflight_gates` | **fail**，列出疑似前置關卡供需求方裁定（§5.2） |
| 🔨執行中 | 跑 `--preflight` | 欄位寫壞（值域／pattern／重複／多行） | **fail loud**，不得當成缺席 |
| 🔨執行中 | 跑 `--preflight` | 宣告 `[]`，其餘機械條件通過 | 產生空 `preflight_gates` 快照 → 可寫 handoff |
| 🔨執行中 | 跑 `--preflight` | 有前置關卡且全部 `approve` | 產生快照 → 可寫 handoff |
| 🔨執行中 | 跑 `--preflight` | 有前置關卡尚未完成／被退回 | 寫 `preflight-failed`；**留在 🔨執行中**，不派 reviewer、不遞增 iteration |
| 🔨執行中 | 跑 `--preflight` | 外部條件未滿足（等 sign-off／上游卡／服務） | 依 canonical 改寫 `status-change` → `⏸阻塞`，非 preflight failure |
| 🔍待查核 | `review` | — | 完全由 WF-21 attempt 模型接手，本契約不介入 |
| 任意 | `review` 帶 `closes_review_round`／`corrects_event_id` | baseline 後 | **`--check` fail loud**（§3.4） |
| 任意 | `handoff` 缺 `preflight_gates` | baseline 後 | **`--check` fail loud**（§5.1） |
| 任意 | `handoff` 缺 `preflight_gates` | baseline 前 | 不驗，歷史原貌 |

## §5 Migration

### 5.1 cutover marker

以獨立的 one-shot 事件 `contract-baseline` 寫 `contract_baseline: review-gate-v1`。
其**之後**的 handoff 必須帶合法 `preflight_gates`，否則 `workflow_ledger.py --check` fail loud；
之前的事件不回填、不重新解讀。

`workflow_ledger.py` 目前把 `REVIEW_CONTRACT` 寫死為單一常數，須擴充成**支援多個 baseline
並存**（各自記錄啟用點）。canonical 的「marker 為 one-shot、再次出現必須 fail loud」是針對
**同一個 baseline 名**，不同名的 baseline 並存不違反。

> **為什麼要驗到 ledger 這一層**：事件實際上是需求方**親手** append（分類器把寫
> `events.jsonl` 當硬邊界，agent 繞不過），所以「工具擋在寫入前」只對走工具的人成立。
> 唯一真正硬的保證是 replay 驗證。

### 5.2 缺欄與回填

- **新卡自 cutover 起必填** `review_preflight_gates`（沒有前置關卡就寫 `[]`）。
- **活卡不做一次性全面回填**，但**下一次 handoff 前必須補齊**，由 preflight 擋住。
- **缺欄一律 fail**，不得退化成「所以沒有前置關卡」；**不得用缺欄暗示不需查核**。
- fail 訊息**列出盤點腳本（§6）在該卡找到的疑似前置關卡**（〈Design〉欄、`## Plan Gate`
  章節、正文順序語式），標明**這是提示、不是判定**，由需求方裁定後填。
- 值**由需求方逐張裁定**，執行者與工具不得推定；語意不明或自我矛盾（§6 信號 F 的 2 張）
  標為待裁定並暫不填。
- **封存卡與 cutover 前的事件一律不動。**

### 5.3 沒有 handoff 可依附的 review

盤點查出 3 張卡的 review 早於第一次 handoff（Plan Gate 型），另有 7 張卡從未寫過任何 handoff
卻有 review。**cutover 後不得再出現沒有對應 handoff 的 review**：Plan 本身就是一次交付
（有卡面修訂當 `source_sha`、有 evidence、有查核者），先寫 handoff 再送查核。
既有 10 張屬歷史，不回填、不改寫。

## §6 多關卡盤點（可重現，用途改為 preflight 的缺欄提示）

腳本 [`../scripts/review_gate_inventory.py`](../scripts/review_gate_inventory.py)，完整輸出
[`discovery/review-gate-inventory-2026-07-31.md`](discovery/review-gate-inventory-2026-07-31.md)。
應然信號 A（正文順序語式，含「交給誰」判別）、B（〈Design〉欄待跑 Gate）、E（`## Plan Gate`
章節標題）、D（結構化欄位）、F（〈查核〉欄與正文矛盾）；實然信號 C1／C2／C3。

`37431a0`（123 張卡、892 筆事件、172 筆 review）：**命中 32 張，實質 30 張**。

| 卡面宣告的前置關卡型態 | 張數 |
|---|---|
| Plan／Design Gate → 實作查核 | 14 |
| 人工審 → 跨家族查核 | 3（`UX-DESIGN-CONFORM1`、`UX-ENTITY-LINKS1`、`UX-ENTITY-LINKS2`） |
| 人工審 → 一般 AI 查核（未要求跨家族） | 3（`UX-TEAM-HOTZONE1`、`UX-TEAM-RECORDS1`、`UX-TEAM-STYLE1`） |

**這三種不得被寫成同一種**；另有 2 張自我矛盾（信號 F），回填時必須由需求方裁定。

**分類是建議，待人工確認。** 它讀中文自由文字，**不得被 preflight 判定消費**——只能出現在
§5.2 的 fail 訊息裡當提示。盤點的用途是把要求搬進結構化欄位，搬完之後對那張卡就沒有用了。

## §7 受影響檔案與測試計畫

### 受影響檔案

`scripts/review_prompt.py`：新增 `--preflight` 模式（驗卡面欄位＋既有的 SHA 同一性／分支／
工作區檢查，輸出要寫進 handoff 的 `preflight_gates` JSON）；移除 `CLOSES_ROUND_FIELD`／
`CORRECTS_FIELD` 與 `_assert_no_review_supersedes_handoff()` 的中繼關卡邏輯；
`review_gates_block()` 改吃 handoff 快照；移除 §2.3 第 3 條指出的兩處措辭。
`scripts/workflow_ledger.py`：多 baseline 支援＋handoff `preflight_gates` 驗證＋廢止欄位 fail loud。
`tests/test_review_prompt.py`、`tests/test_workflow_ledger.py` 同步。
文件：`docs/CONTROL_PLANE_CONTRACT.md`、`docs/TEMPLATES.md`、`docs/HANDOFF_CONTRACT.md`。
`scripts/review_gate_inventory.py` 納管＋測試。活卡按需回填。

### 測試計畫（性質，不是示範）

**preflight**：合法卡面產生正確快照；缺欄 fail 且**訊息不得提供任何 fallback**、但**必須**
列出疑似前置關卡並標明是提示；`[]` 產生空快照且通過；欄位寫壞（值域外／pattern 不合／
`gate_id` 重複／同卡多行）逐一 fail loud；前置關卡未完成 → 產生 `preflight-failed` 內容
而非 handoff 快照；外部阻塞不得被歸成 preflight failure。

**ledger**：baseline 後 handoff 缺 `preflight_gates` → fail loud；快照結構不合（缺 `gate_id`／
`requirement` 值域外／`decision` 非 `approve`）→ fail loud；baseline **前**的 handoff 不受影響
（以現有 892 筆事件為 golden，差異必須為 0）；`review-gate-v1` marker 重複出現 → fail loud；
兩個 baseline（`review-escalation-v1` ＋ `review-gate-v1`）並存時互不干擾。

**廢止欄位**：baseline 後 review 帶 `closes_review_round` 或 `corrects_event_id` → fail loud；
baseline 前不受影響。

**保證邊界**：提示詞輸出**不得出現**任何把自由文字當流程依據的措辭（以字串斷言鎖住），
且**不宣稱**已驗證 reviewer 身分。

**窮舉回歸（紅線）**：對全庫事件跑新舊兩版 `--check`，baseline 前逐筆一致，**差異數 0**，
證據由腳本產生，不得以人工聲明承載。

## §8 決策紀錄（2026-07-31 對抗式質詢，ruan6047 裁定）

1. 前置關卡＝preflight 條件，不是 review event。
2. `closes_review_round`／`corrects_event_id` 直接廢止移除（兩個 bug 隨之消失，不需修）。
3. 卡面兩欄位分開：`review_preflight_gates` 新增、`review_independence` 沿用不遷移。
4. 通過的關卡快照進 handoff、未通過寫 WF-21 既有 `preflight-failed`；**不新增 event type**。
5. 工具落在 `review_prompt.py --preflight`（共用既有檢查，避免兩份漂移）。
6. ledger 要驗 handoff 快照 → 第二個 marker `review-gate-v1` ＋ 多 baseline 支援。
7. 缺欄 fail，且 fail 訊息列出盤點找到的疑似前置關卡（提示，不判定）。
8. 合成一張卡（`DEV-REVIEW-PREFLIGHT-GATE1`）。
9. 兩張未 register 的舊卡檔刪除；本契約改寫 v1.0，保留 §9 稽核。
10. 先 adapter 落地、驗證後再提 canonical（WF-22）。
11. 本卡先，認領 `file:scripts/workflow_ledger.py`；`DEV-REVIEW-DEACCEPT-TRAIL1` 之後 rebase。
12. 廢止欄位再出現 → fail loud。

### Release 後追蹤（不是驗收條件）

`closes_review_round` 在全庫 892 筆事件裡用過 **0 次**——前一張卡建好的機制從未被使用。
合併後第一個月追蹤「新寫的 handoff 是否 **100%** 帶 `preflight_gates`」；
`--check` 會擋，所以這個數字若不是 100%，代表有人繞過驗證或事件根本沒寫進去。

```bash
jq -r 'select(.type=="handoff" and .occurred_at > "<cutover>") | .preflight_gates == null' docs/control-plane/events.jsonl | sort | uniq -c
```

## §9 與 WF-21 的稽核紀錄（v0.1–v0.3 為何被推翻）

規劃期間工作樹停在 `063d12d`，而 `origin/main` 已推進到 `37431a0`：WF-21 於 2026-07-31 10:41
全鏈落地（canonical `b113617` → adapter merge `f86bd5e` → marker `WF21-ADOPT-BASELINE-001`），
`workflow_ledger.py` 因此多了 409 行 fail-loud 契約驗證。舊版設計的四項衝突與現在的處置：

| v0.3 的設計 | 與 WF-21 的衝突 | v1.0 的處置 |
|---|---|---|
| `review-correction` 型別帶 `corrects_event_id`／`reopens_round` | WF-21 已佔用同名型別且必填 `escalation_epoch`／`target_attempt_id`／`finding_updates`，canonical 明文不得混用 | **不需要了**——中繼關卡不是 review，沒有要更正的東西 |
| review 新增 `gate_result` enum，`review_result` 降為自由文字 | WF-21 已強制 `review_result ∈ {APPROVE, REQUEST_CHANGES}` | **不需要了**——本契約不碰 review 事件 |
| 「一輪」＝handoff→終結，任一 request_changes 即終結 | WF-21 的 attempt ＝ `(card, epoch, source_sha)`，同 SHA 多 reviewer 合併；舊設計會擋掉合法的第二位 reviewer | **不需要了**——review 之後的狀態機完全交給 WF-21 |
| 另立 `scripts/review_gate_preflight.py` | WF-21 已有 preflight 概念、`preflight-failed` 型別與 `preflight_passed` 欄位 | 併入 `review_prompt.py --preflight`，用 WF-21 既有型別 |

**順帶更正 v0.1–v0.3 的一項事實錯誤**：舊版寫「判定結果沒有機器可讀來源」是錯的。
baseline 後結論必為 enum 且由驗證器強制；baseline 前也有 95／172 筆帶 `verdict`，
只是值域有七種（`APPROVE`／`REJECT`／`REQUEST_CHANGES`／`✅通過`／`APPROVE_WITH_FINDINGS`／
`RETURN`／`REQUEST_CHANGES_ESCALATED`）、76 筆完全缺。正確說法是「baseline 前值域不一致」。
