# 多關卡查核要求盤點 — 完整結果（2026-07-31，iteration 2）

> **本檔全文由腳本產生，未經人工編輯**（本說明區塊除外）。重跑：
>
> ```bash
> uv run python scripts/review_gate_inventory.py                # 工作目錄
> uv run python scripts/review_gate_inventory.py --rev 81bcd4d  # 附錄那份
> ```
>
> iteration 2（依需求方 2026-07-31 指示）新增：真正輸出**分類與計數**（不再只印原始欄位）、
> 新增信號 E（`## Plan Gate` 章節）與 F（〈查核〉欄與正文互相矛盾）、
> 區分 human→cross-family／human→一般 AI／Plan Gate→implementation、
> 區分同輪多關卡與同輪第二意見、區分 Plan Gate 型與孤兒 review，
> 並固定列出需求方指定重檢的 9 張卡（零命中也列，並說明為什麼）。
>
> **基準：`37431a0`（WF-21 審核契約採用後的 origin/main）。** 先前版本以 `063d12d` 產生，
> 分類與命中數不變，母體／事件數依新基準更新。契約對應章節見
> [`../archive/REVIEW_GATE_CONTRACT.md`](../archive/REVIEW_GATE_CONTRACT.md) §6，與 WF-21 的衝突見 §9。

---

# 多關卡查核要求盤點（rev=（工作目錄））

卡片母體 123 張；event log 892 筆／121 張卡；review 事件 172 筆，其中 **106 筆沒有 `review_result`**；查核輪次 177 輪。

**命中 32 張**（實質 30、僅引文嫌疑 2）。

> **分類欄是建議，待人工確認。** 它讀中文自由文字，**不得被守衛／preflight／gate 判定消費**——流程門檻只能來自結構化的 `review_gates` 與 handoff snapshot。

## 計數：卡面宣告的關卡型態（一張卡可落在多型）

| 型態 | 張數 |
|---|---|
| Plan／Design Gate → 實作查核 | 14 |
| 人工審 → 跨家族查核 | 3 |
| 人工審 → 一般 AI 查核（未要求跨家族） | 3 |

## 計數：event log 的實然型態

| 型態 | 卡數 |
|---|---|
| **全卡沒有任何 handoff 事件**，review 無所依附（新契約的 snapshot 無處可放） | 7 |
| 同輪多關卡（不同性質的查核者） | 6 |
| 有 handoff，但第一次 handoff 之前就有 review（Plan Gate 型） | 3 |
| 同輪第二意見（同性質查核者再查一次） | 1 |
| 跨輪不同性質關卡（人工審 → 新 handoff → AI 查核） | 1 |

## 需求方指定重檢的卡


### DEV-REVIEW-INDEP-FIELD1　[A]　⚠**全部命中皆疑為引用他卡**

- 檔案：`docs/archive/tasks/DEV-REVIEW-INDEP-FIELD1.md`
- 信號 A L40　⚠引用他卡（交給：cross_family）：1. **值域夠不夠**：現有活卡與封存卡的〈查核〉欄實際出現過哪些要求？四個值涵蓋得了嗎？是否存在「先 A 後 B」這種**有順序**的要求（`UX-ENTITY-LINKS2` 的「先本地人工審再交跨家族查核」就是），順序要不要進值域？

### DEV-REVIEW-PROMPT-GATE1　[A]　⚠**全部命中皆疑為引用他卡**

- 檔案：`docs/archive/tasks/DEV-REVIEW-PROMPT-GATE1.md`
- 信號 A L17　⚠引用他卡（交給：cross_family）：那是拿**「有沒有 review 事件」當作「這一輪結束了沒」的標記**。兩者在單關卡的卡上重合，在**多關卡**的卡上不重合——`UX-ENTITY-LINKS2` 卡面 L40 明訂「先本地人工審再交跨家族查核」，2026-07-29 需求方的人工審 APPROVE 寫成 `REVIEW-007`（`delivery_sta

### OPS-LIVE-SHADOW1　[EC]

- 檔案：`docs/tasks/OPS-LIVE-SHADOW1.md`
- 宣告型態（建議）：Plan／Design Gate → 實作查核
- 實然型態：有 handoff，但第一次 handoff 之前就有 review（Plan Gate 型）
- 信號 E L13（交給：impl）：## Plan Gate
- 信號 C3 **第一次 handoff 之前**的 review：
    - `OPS-LIVE-SHADOW1-REVIEW-002`　2026-07-26T20:44　[same_family] GPT-5.6 sibling context@Codex（獨立 Plan 　↩退回
    - `OPS-LIVE-SHADOW1-REVIEW-004`　2026-07-26T21:08　[cross_family] Antigravity（Gemini 3.6 Flash / Google 　⏳待執行

### UX-DESIGN-CONFORM1　[AB]

- 檔案：`docs/archive/tasks/UX-DESIGN-CONFORM1.md`
- 宣告型態（建議）：人工審 → 跨家族查核、Plan／Design Gate → 實作查核
- 信號 A L18（交給：cross_family）：- [ ] `npm run build:check` 通過；上線前依 UX 慣例先開本地環境給需求方人工審，OK 後才交跨家族（非 Claude）或人工查核。
- 信號 B L10（交給：impl）：- Design：**Design Gate = ruan6047**（修改清單與上線前人工審，依 [[ux-manual-review-before-ai]] 慣例）

### UX-ENTITY-LINKS1　[AB]

- 檔案：`docs/archive/tasks/UX-ENTITY-LINKS1.md`
- 宣告型態（建議）：人工審 → 跨家族查核、Plan／Design Gate → 實作查核
- 信號 A L23（交給：cross_family）：- [ ] 驗證：`build:check` + 深淺色截圖 + 鍵盤焦點 + a11y（連結非色彩單獨可辨識）。**先本地人工審再交跨家族查核**。
- 信號 B L10（交給：impl）：- Design：**Design Gate = ruan6047**（實際連結觀感於本地審微調）

### UX-ENTITY-LINKS2　[ABC]

- 檔案：`docs/archive/tasks/UX-ENTITY-LINKS2.md`
- 宣告型態（建議）：人工審 → 跨家族查核、Plan／Design Gate → 實作查核
- 實然型態：同輪多關卡（不同性質的查核者）
- 信號 A L40（交給：cross_family）：- [ ] `build:check` 全路由 ✓、`npm test` ✓、深淺色截圖、鍵盤焦點、a11y（連結非色彩單獨可辨識）。**先本地人工審再交跨家族查核**。
- 信號 B L10（交給：impl）：- Design：**Design Gate = ruan6047**（每點的 block→text-only 觀感於本地審微調）
- 信號 C1 同輪多筆 review（同輪多關卡（不同性質的查核者））：
    - `UX-ENTITY-LINKS2-REVIEW-007`　2026-07-29T18:09　[human] ruan6047（需求方本地人工審／Design Gate）　🔍待查核　APPROVE（人工審／Design Gate 階段；跨家族查核尚未進行）
    - `UX-ENTITY-LINKS2-REVIEW-008`　2026-07-29T20:11　[cross_family] GPT@Codex（跨模型家族查核者，非 Claude；需求方轉錄，確切模型　✅可合併　APPROVE（跨家族終局查核；零阻塞 findings，2 筆 informa

### UX-TEAM-HOTZONE1　[AF]

- 檔案：`docs/archive/tasks/UX-TEAM-HOTZONE1.md`
- 宣告型態（建議）：人工審 → 一般 AI 查核（未要求跨家族）
- 信號 A L84（交給：ai）：- **UX 卡流程**：執行完先開本地環境給需求方人工審核，OK 後才交 AI 查核。
- 信號 F L84：〈查核〉欄要求跨家族／人工（待指派（跨模型家族或人工，且 ≠ 執行）），正文卻只寫交 AI 查核（L84）

### UX-TEAM-RECORDS1　[AF]

- 檔案：`docs/archive/tasks/UX-TEAM-RECORDS1.md`
- 宣告型態（建議）：人工審 → 一般 AI 查核（未要求跨家族）
- 信號 A L181（交給：ai）：- **UX 卡流程**：執行完先開本地環境給需求方人工審核，OK 後才交 AI 查核。
- 信號 F L181：〈查核〉欄要求跨家族／人工（待指派（跨模型家族或人工，且 ≠ 執行）），正文卻只寫交 AI 查核（L181）

### UX-TEAM-STYLE1　[A]

- 檔案：`docs/archive/tasks/UX-TEAM-STYLE1.md`
- 宣告型態（建議）：人工審 → 一般 AI 查核（未要求跨家族）
- 信號 A L59（交給：ai）：- [ ] 本機開發環境人工走查（依 UX 慣例：先人工審再交 AI 查核）。

## 其餘命中


### DOC-GAME-RECAP1　[BC]

- 檔案：`docs/archive/tasks/DOC-GAME-RECAP1.md`
- 宣告型態（建議）：Plan／Design Gate → 實作查核
- 實然型態：**全卡沒有任何 handoff 事件**，review 無所依附（新契約的 snapshot 無處可放）
- 信號 B L10（交給：impl）：- Design：本卡即為 Design／Plan 權威文件查核；Design Gate 維持待需求方核可
- 信號 C3 **第一次 handoff 之前**的 review：
    - `DOC-GAME-RECAP1-REVIEW-003`　2026-07-19T08:53　[ai_unspecified] Claude　↩退回
    - `DOC-GAME-RECAP1-REVIEW-004`　2026-07-19T08:54　[human] ruan6047　✅通過

### GAME-RECAP-DATA1　[C]

- 檔案：`docs/archive/tasks/GAME-RECAP-DATA1.md`
- 實然型態：同輪多關卡（不同性質的查核者）
- 信號 C1 同輪多筆 review（同輪多關卡（不同性質的查核者））：
    - `GAME-RECAP-DATA1-REVIEW-004`　2026-07-19T13:55　[ai_unspecified] Claude Opus 4.8@Claude Code　✅通過　（result 未填）
    - `GAME-RECAP-DATA1-REVIEW-005`　2026-07-19T14:02　[human] ruan6047　✅通過　（result 未填）

### GAME-RECAP-PA1-BUILD1　[C]

- 檔案：`docs/archive/tasks/GAME-RECAP-PA1-BUILD1.md`
- 實然型態：**全卡沒有任何 handoff 事件**，review 無所依附（新契約的 snapshot 無處可放）
- 信號 C3 **第一次 handoff 之前**的 review：
    - `GAME-RECAP-PA1-BUILD1-REVIEW-004`　2026-07-24T15:05　[cross_family] Gemini 3.6 Flash（跨模型家族查核者，非 Claude，≠ 執　✅通過／待合併

### GAME-RECAP-PA1-EXPAND1　[C]

- 檔案：`docs/archive/tasks/GAME-RECAP-PA1-EXPAND1.md`
- 實然型態：**全卡沒有任何 handoff 事件**，review 無所依附（新契約的 snapshot 無處可放）
- 信號 C3 **第一次 handoff 之前**的 review：
    - `GAME-RECAP-PA1-EXPAND1-REVIEW-004`　2026-07-24T13:05　[cross_family] Antigravity（Gemini 3.6 Flash，跨模型家族查核者）　✅通過／待合併

### GAME-RECAP-PA1-FIX1　[E]

- 檔案：`docs/archive/tasks/GAME-RECAP-PA1-FIX1.md`
- 宣告型態（建議）：Plan／Design Gate → 實作查核
- 信號 E L181（交給：impl）：## Design Gate

### GAME-RECAP-PA1-TAXONOMY1　[C]

- 檔案：`docs/archive/tasks/GAME-RECAP-PA1-TAXONOMY1.md`
- 實然型態：**全卡沒有任何 handoff 事件**，review 無所依附（新契約的 snapshot 無處可放）
- 信號 C3 **第一次 handoff 之前**的 review：
    - `GAME-RECAP-PA1-TAXONOMY1-REVIEW-003`　2026-07-24T11:25　[cross_family] Antigravity（Gemini 3.6 Flash，跨模型家族查核者）　✅通過／待合併

### GAME-RECAP-WP-STRENGTH1　[C]

- 檔案：`docs/archive/tasks/GAME-RECAP-WP-STRENGTH1.md`
- 實然型態：同輪多關卡（不同性質的查核者）
- 信號 C1 同輪多筆 review（同輪多關卡（不同性質的查核者））：
    - `GAME-RECAP-WP-STRENGTH1-REVIEW-006`　2026-07-27T03:26　[cross_family] Google Gemini 3.6 Flash (High)（跨模型家族獨立　🔍待查核　（result 未填）
    - `GAME-RECAP-WP-STRENGTH1-REVIEW-007`　2026-07-27T10:01　[ai_unspecified] 獨立查核者（第二份；需求方轉錄）　🔧修正中　（result 未填）

### INGEST-GAME-TM-REFACTOR1　[C]

- 檔案：`docs/tasks/INGEST-GAME-TM-REFACTOR1.md`
- 實然型態：**全卡沒有任何 handoff 事件**，review 無所依附（新契約的 snapshot 無處可放）
- 信號 C3 **第一次 handoff 之前**的 review：
    - `INGEST-GAME-TM-REFACTOR1-REVIEW-005`　2026-07-24T11:13　[cross_family] Gemini（跨模型家族查核者）　✅通過／待合併
    - `INGEST-GAME-TM-REFACTOR1-REVIEW-008`　2026-07-24T12:53　[cross_family] Antigravity（Gemini 3.6 Flash，跨模型家族查核者）　✅通過／待合併

### INGEST-SPLITS-PA-SPLIT1　[EC]

- 檔案：`docs/archive/tasks/INGEST-SPLITS-PA-SPLIT1.md`
- 宣告型態（建議）：Plan／Design Gate → 實作查核
- 實然型態：同輪第二意見（同性質查核者再查一次）
- 信號 E L153（交給：impl）：## Design Gate
- 信號 C1 同輪多筆 review（同輪第二意見（同性質查核者再查一次））：
    - `INGEST-SPLITS-PA-SPLIT1-REVIEW-007`　2026-07-30T01:05　[cross_family] 跨模型家族查核者（非 Claude；需求方轉錄，確切工具／模型待補正）　↩退回　REJECT（2 High＋1 Medium）
    - `INGEST-SPLITS-PA-SPLIT1-REVIEW-008`　2026-07-30T01:40　[cross_family] 第二跨模型家族查核者（非 Claude；需求方轉錄，確切工具／模型待補正）　↩退回　REJECT（1 High＋1 Medium；第二獨立查核）

### LIVE-GAME-BACKEND1　[C]

- 檔案：`docs/archive/tasks/LIVE-GAME-BACKEND1.md`
- 實然型態：同輪多關卡（不同性質的查核者）
- 信號 C1 同輪多筆 review（同輪多關卡（不同性質的查核者））：
    - `LIVE-GAME-BACKEND1-REVIEW-009`　2026-07-30T09:08　[cross_family] Claude Fable 5@Claude Code（查核者；跨模型家族，≠　✅可合併　APPROVE
    - `LIVE-GAME-BACKEND1-REVIEW-010`　2026-07-30T17:08　[ai_unspecified] 獨立複審者（由 ruan6047 轉錄；查核者身份未提供）　⏸阻塞　REJECT

### ML-MATCHUP1　[C]

- 檔案：`docs/archive/tasks/ML-MATCHUP1.md`
- 實然型態：**全卡沒有任何 handoff 事件**，review 無所依附（新契約的 snapshot 無處可放）
- 信號 C3 **第一次 handoff 之前**的 review：
    - `ML-MATCHUP1-REVIEW-003`　2026-07-16T17:06　[human] ruan6047　↩退回
    - `ML-MATCHUP1-REVIEW-004`　2026-07-16T21:30　[human] ruan6047　✅通過／待合併

### ML-OUTCOME-LEAK1　[C]

- 檔案：`docs/archive/tasks/ML-OUTCOME-LEAK1.md`
- 實然型態：有 handoff，但第一次 handoff 之前就有 review（Plan Gate 型）
- 信號 C3 **第一次 handoff 之前**的 review：
    - `ML-OUTCOME-LEAK1-REVIEW-006`　2026-07-27T03:30　[same_family] Claude subagent（Coordinator 委派之第二查核；新 　📦已合併

### ML-PITCHER-SCORELESS1　[C]

- 檔案：`docs/archive/tasks/ML-PITCHER-SCORELESS1.md`
- 實然型態：同輪多關卡（不同性質的查核者）
- 信號 C1 同輪多筆 review（同輪多關卡（不同性質的查核者））：
    - `ML-PITCHER-SCORELESS1-REVIEW-004`　2026-07-28T11:52　[cross_family] GPT-5.6@Codex（查核者；獨立 session，≠ 執行者）　↩退回　REJECT
    - `ML-PITCHER-SCORELESS1-REVIEW-005`　2026-07-28T12:02　[ai_unspecified] 第二位查核者（獨立 session；以 `git archive a0ba6　↩退回　REJECT

### ML-UMP2　[E]

- 檔案：`docs/archive/tasks/ML-UMP2.md`
- 宣告型態（建議）：Plan／Design Gate → 實作查核
- 信號 E L22（交給：impl）：## Plan Gate（07-16 需求方核可）

### OPS-REFRESH1　[C]

- 檔案：`docs/archive/tasks/OPS-REFRESH1.md`
- 實然型態：同輪多關卡（不同性質的查核者）
- 信號 C1 同輪多筆 review（同輪多關卡（不同性質的查核者））：
    - `OPS-REFRESH1-REVIEW-007`　2026-07-17T12:57　[human] ruan6047　↩退回　（result 未填）
    - `OPS-REFRESH1-REVIEW-009`　2026-07-18T14:20　[ai_unspecified] Claude Sonnet 5@Claude Code　✅通過　（result 未填）

### UX-DESIGN-SYSTEM1　[B]

- 檔案：`docs/archive/tasks/UX-DESIGN-SYSTEM1.md`
- 宣告型態（建議）：Plan／Design Gate → 實作查核
- 信號 B L13（交給：impl）：- Design：**Design Gate = ruan6047**（產出的 canonical 規格須經需求方 sign-off 才成為全站事實）

### UX-ENTITY-LINKS3　[BC]

- 檔案：`docs/archive/tasks/UX-ENTITY-LINKS3.md`
- 宣告型態（建議）：Plan／Design Gate → 實作查核
- 實然型態：跨輪不同性質關卡（人工審 → 新 handoff → AI 查核）
- 信號 B L11（交給：impl）：- Design：**Design Gate = ruan6047**（哪些出現位置該連、哪些不連；列表頁的互動取捨）
- 信號 C2 跨輪不同性質關卡：
    - `UX-ENTITY-LINKS3-REVIEW-005`　2026-07-29T22:31　[human] ruan6047（需求方本地人工審／Design Gate）
    - `UX-ENTITY-LINKS3-REVIEW-007`　2026-07-29T22:43　[cross_family] 跨模型家族查核者（非 Claude；需求方轉錄，確切工具／模型待補正）

### UX-GAME-PA1　[B]

- 檔案：`docs/tasks/UX-GAME-PA1.md`
- 宣告型態（建議）：Plan／Design Gate → 實作查核
- 信號 B L10（交給：impl）：- Design：spec v1.1 與 Design Brief 待需求方核可；實作前須補行動版與桌機互動 prototype

### UX-GAME-RECAP1　[B]

- 檔案：`docs/tasks/UX-GAME-RECAP1.md`
- 宣告型態（建議）：Plan／Design Gate → 實作查核
- 信號 B L10（交給：impl）：- Design：spec v1.1 與 Design Brief 待需求方核可；實作前須補 prototype／wireframe 與 Design Gate

### UX-NAV-INTEGRATE1　[B]

- 檔案：`docs/archive/tasks/UX-NAV-INTEGRATE1.md`
- 宣告型態（建議）：Plan／Design Gate → 實作查核
- 信號 B L11（交給：impl）：- Design：**Design Gate = ruan6047**（§4.3 方向已 sign-off 2026-07-24；各頁成品仍須 UI 審）

### UX-PLAYER-FIELDVIZ1　[C]

- 檔案：`docs/archive/tasks/UX-PLAYER-FIELDVIZ1.md`
- 實然型態：有 handoff，但第一次 handoff 之前就有 review（Plan Gate 型）
- 信號 C3 **第一次 handoff 之前**的 review：
    - `UX-PLAYER-FIELDVIZ1-REVIEW-010`　2026-07-20T20:13　[cross_family] Antigravity　↩退回

### UX-TEAM-SPLIT-SCOPE1　[C]

- 檔案：`docs/archive/tasks/UX-TEAM-SPLIT-SCOPE1.md`
- 實然型態：**全卡沒有任何 handoff 事件**，review 無所依附（新契約的 snapshot 無處可放）
- 信號 C3 **第一次 handoff 之前**的 review：
    - `UX-TEAM-SPLIT-SCOPE1-REVIEW-005`　2026-07-25T02:10　[cross_family] Claude Opus 4.8（執行者，代 Coordinator 記錄跨家　🔍待查核

### UX-TOKEN-HYGIENE1　[B]

- 檔案：`docs/archive/tasks/UX-TOKEN-HYGIENE1.md`
- 宣告型態（建議）：Plan／Design Gate → 實作查核
- 信號 B L11（交給：impl）：- Design：**Design Gate = ruan6047**（動到色票須 sign-off）

## 讀法

- 應然（A／B／D／E／F）是卡面宣告，實然（C1／C2／C3）是 event log 已發生的事；**兩者經常不一致**，不一致本身就是要搬進結構化欄位的理由。
- **零命中 ≠ 單關卡**：只代表沒有可機械辨識的語式。已知至少五種語式，不能排除第六種。任何回填都須由需求方逐張確認。
- `⚠引用他卡` 是機械判準（命中行含別張卡卡號），不是人工排除清單；腳本不隱藏任何命中。
- actor 分類讀的是人工轉錄的字串，**工具無法驗證真實模型家族或人類身分**（契約 §8 Q4）。


---

# 附錄：同一支腳本在 `81bcd4d`（INDEP-FIELD1 Discovery iteration 1 的基線）的結果

# 多關卡查核要求盤點（rev=81bcd4d）

卡片母體 119 張；event log 860 筆／118 張卡；review 事件 165 筆，其中 **106 筆沒有 `review_result`**；查核輪次 169 輪。

**命中 32 張**（實質 30、僅引文嫌疑 2）。

> **分類欄是建議，待人工確認。** 它讀中文自由文字，**不得被守衛／preflight／gate 判定消費**——流程門檻只能來自結構化的 `review_gates` 與 handoff snapshot。

## 計數：卡面宣告的關卡型態（一張卡可落在多型）

| 型態 | 張數 |
|---|---|
| Plan／Design Gate → 實作查核 | 15 |
| 人工審 → 跨家族查核 | 3 |
| 人工審 → 一般 AI 查核（未要求跨家族） | 3 |

## 計數：event log 的實然型態

| 型態 | 卡數 |
|---|---|
| **全卡沒有任何 handoff 事件**，review 無所依附（新契約的 snapshot 無處可放） | 7 |
| 同輪多關卡（不同性質的查核者） | 5 |
| 有 handoff，但第一次 handoff 之前就有 review（Plan Gate 型） | 3 |
| 同輪第二意見（同性質查核者再查一次） | 1 |
| 跨輪不同性質關卡（人工審 → 新 handoff → AI 查核） | 1 |

## 需求方指定重檢的卡


### DEV-REVIEW-INDEP-FIELD1　[A]　⚠**全部命中皆疑為引用他卡**

- 檔案：`docs/tasks/DEV-REVIEW-INDEP-FIELD1.md`
- 信號 A L40　⚠引用他卡（交給：cross_family）：1. **值域夠不夠**：現有活卡與封存卡的〈查核〉欄實際出現過哪些要求？四個值涵蓋得了嗎？是否存在「先 A 後 B」這種**有順序**的要求（`UX-ENTITY-LINKS2` 的「先本地人工審再交跨家族查核」就是），順序要不要進值域？

### DEV-REVIEW-PROMPT-GATE1　[A]　⚠**全部命中皆疑為引用他卡**

- 檔案：`docs/archive/tasks/DEV-REVIEW-PROMPT-GATE1.md`
- 信號 A L17　⚠引用他卡（交給：cross_family）：那是拿**「有沒有 review 事件」當作「這一輪結束了沒」的標記**。兩者在單關卡的卡上重合，在**多關卡**的卡上不重合——`UX-ENTITY-LINKS2` 卡面 L40 明訂「先本地人工審再交跨家族查核」，2026-07-29 需求方的人工審 APPROVE 寫成 `REVIEW-007`（`delivery_sta

### OPS-LIVE-SHADOW1　[EC]

- 檔案：`docs/tasks/OPS-LIVE-SHADOW1.md`
- 宣告型態（建議）：Plan／Design Gate → 實作查核
- 實然型態：有 handoff，但第一次 handoff 之前就有 review（Plan Gate 型）
- 信號 E L13（交給：impl）：## Plan Gate
- 信號 C3 **第一次 handoff 之前**的 review：
    - `OPS-LIVE-SHADOW1-REVIEW-002`　2026-07-26T20:44　[same_family] GPT-5.6 sibling context@Codex（獨立 Plan 　↩退回
    - `OPS-LIVE-SHADOW1-REVIEW-004`　2026-07-26T21:08　[cross_family] Antigravity（Gemini 3.6 Flash / Google 　⏳待執行

### UX-DESIGN-CONFORM1　[AB]

- 檔案：`docs/archive/tasks/UX-DESIGN-CONFORM1.md`
- 宣告型態（建議）：人工審 → 跨家族查核、Plan／Design Gate → 實作查核
- 信號 A L18（交給：cross_family）：- [ ] `npm run build:check` 通過；上線前依 UX 慣例先開本地環境給需求方人工審，OK 後才交跨家族（非 Claude）或人工查核。
- 信號 B L10（交給：impl）：- Design：**Design Gate = ruan6047**（修改清單與上線前人工審，依 [[ux-manual-review-before-ai]] 慣例）

### UX-ENTITY-LINKS1　[AB]

- 檔案：`docs/archive/tasks/UX-ENTITY-LINKS1.md`
- 宣告型態（建議）：人工審 → 跨家族查核、Plan／Design Gate → 實作查核
- 信號 A L23（交給：cross_family）：- [ ] 驗證：`build:check` + 深淺色截圖 + 鍵盤焦點 + a11y（連結非色彩單獨可辨識）。**先本地人工審再交跨家族查核**。
- 信號 B L10（交給：impl）：- Design：**Design Gate = ruan6047**（實際連結觀感於本地審微調）

### UX-ENTITY-LINKS2　[ABC]

- 檔案：`docs/archive/tasks/UX-ENTITY-LINKS2.md`
- 宣告型態（建議）：人工審 → 跨家族查核、Plan／Design Gate → 實作查核
- 實然型態：同輪多關卡（不同性質的查核者）
- 信號 A L40（交給：cross_family）：- [ ] `build:check` 全路由 ✓、`npm test` ✓、深淺色截圖、鍵盤焦點、a11y（連結非色彩單獨可辨識）。**先本地人工審再交跨家族查核**。
- 信號 B L10（交給：impl）：- Design：**Design Gate = ruan6047**（每點的 block→text-only 觀感於本地審微調）
- 信號 C1 同輪多筆 review（同輪多關卡（不同性質的查核者））：
    - `UX-ENTITY-LINKS2-REVIEW-007`　2026-07-29T18:09　[human] ruan6047（需求方本地人工審／Design Gate）　🔍待查核　APPROVE（人工審／Design Gate 階段；跨家族查核尚未進行）
    - `UX-ENTITY-LINKS2-REVIEW-008`　2026-07-29T20:11　[cross_family] GPT@Codex（跨模型家族查核者，非 Claude；需求方轉錄，確切模型　✅可合併　APPROVE（跨家族終局查核；零阻塞 findings，2 筆 informa

### UX-TEAM-HOTZONE1　[AF]

- 檔案：`docs/archive/tasks/UX-TEAM-HOTZONE1.md`
- 宣告型態（建議）：人工審 → 一般 AI 查核（未要求跨家族）
- 信號 A L84（交給：ai）：- **UX 卡流程**：執行完先開本地環境給需求方人工審核，OK 後才交 AI 查核。
- 信號 F L84：〈查核〉欄要求跨家族／人工（待指派（跨模型家族或人工，且 ≠ 執行）），正文卻只寫交 AI 查核（L84）

### UX-TEAM-RECORDS1　[AF]

- 檔案：`docs/archive/tasks/UX-TEAM-RECORDS1.md`
- 宣告型態（建議）：人工審 → 一般 AI 查核（未要求跨家族）
- 信號 A L181（交給：ai）：- **UX 卡流程**：執行完先開本地環境給需求方人工審核，OK 後才交 AI 查核。
- 信號 F L181：〈查核〉欄要求跨家族／人工（待指派（跨模型家族或人工，且 ≠ 執行）），正文卻只寫交 AI 查核（L181）

### UX-TEAM-STYLE1　[A]

- 檔案：`docs/archive/tasks/UX-TEAM-STYLE1.md`
- 宣告型態（建議）：人工審 → 一般 AI 查核（未要求跨家族）
- 信號 A L59（交給：ai）：- [ ] 本機開發環境人工走查（依 UX 慣例：先人工審再交 AI 查核）。

## 其餘命中


### DOC-GAME-RECAP1　[BC]

- 檔案：`docs/archive/tasks/DOC-GAME-RECAP1.md`
- 宣告型態（建議）：Plan／Design Gate → 實作查核
- 實然型態：**全卡沒有任何 handoff 事件**，review 無所依附（新契約的 snapshot 無處可放）
- 信號 B L10（交給：impl）：- Design：本卡即為 Design／Plan 權威文件查核；Design Gate 維持待需求方核可
- 信號 C3 **第一次 handoff 之前**的 review：
    - `DOC-GAME-RECAP1-REVIEW-003`　2026-07-19T08:53　[ai_unspecified] Claude　↩退回
    - `DOC-GAME-RECAP1-REVIEW-004`　2026-07-19T08:54　[human] ruan6047　✅通過

### GAME-RECAP-DATA1　[C]

- 檔案：`docs/archive/tasks/GAME-RECAP-DATA1.md`
- 實然型態：同輪多關卡（不同性質的查核者）
- 信號 C1 同輪多筆 review（同輪多關卡（不同性質的查核者））：
    - `GAME-RECAP-DATA1-REVIEW-004`　2026-07-19T13:55　[ai_unspecified] Claude Opus 4.8@Claude Code　✅通過　（result 未填）
    - `GAME-RECAP-DATA1-REVIEW-005`　2026-07-19T14:02　[human] ruan6047　✅通過　（result 未填）

### GAME-RECAP-PA1-BUILD1　[C]

- 檔案：`docs/archive/tasks/GAME-RECAP-PA1-BUILD1.md`
- 實然型態：**全卡沒有任何 handoff 事件**，review 無所依附（新契約的 snapshot 無處可放）
- 信號 C3 **第一次 handoff 之前**的 review：
    - `GAME-RECAP-PA1-BUILD1-REVIEW-004`　2026-07-24T15:05　[cross_family] Gemini 3.6 Flash（跨模型家族查核者，非 Claude，≠ 執　✅通過／待合併

### GAME-RECAP-PA1-EXPAND1　[C]

- 檔案：`docs/archive/tasks/GAME-RECAP-PA1-EXPAND1.md`
- 實然型態：**全卡沒有任何 handoff 事件**，review 無所依附（新契約的 snapshot 無處可放）
- 信號 C3 **第一次 handoff 之前**的 review：
    - `GAME-RECAP-PA1-EXPAND1-REVIEW-004`　2026-07-24T13:05　[cross_family] Antigravity（Gemini 3.6 Flash，跨模型家族查核者）　✅通過／待合併

### GAME-RECAP-PA1-FIX1　[E]

- 檔案：`docs/archive/tasks/GAME-RECAP-PA1-FIX1.md`
- 宣告型態（建議）：Plan／Design Gate → 實作查核
- 信號 E L181（交給：impl）：## Design Gate

### GAME-RECAP-PA1-TAXONOMY1　[C]

- 檔案：`docs/archive/tasks/GAME-RECAP-PA1-TAXONOMY1.md`
- 實然型態：**全卡沒有任何 handoff 事件**，review 無所依附（新契約的 snapshot 無處可放）
- 信號 C3 **第一次 handoff 之前**的 review：
    - `GAME-RECAP-PA1-TAXONOMY1-REVIEW-003`　2026-07-24T11:25　[cross_family] Antigravity（Gemini 3.6 Flash，跨模型家族查核者）　✅通過／待合併

### GAME-RECAP-WP-STRENGTH1　[C]

- 檔案：`docs/archive/tasks/GAME-RECAP-WP-STRENGTH1.md`
- 實然型態：同輪多關卡（不同性質的查核者）
- 信號 C1 同輪多筆 review（同輪多關卡（不同性質的查核者））：
    - `GAME-RECAP-WP-STRENGTH1-REVIEW-006`　2026-07-27T03:26　[cross_family] Google Gemini 3.6 Flash (High)（跨模型家族獨立　🔍待查核　（result 未填）
    - `GAME-RECAP-WP-STRENGTH1-REVIEW-007`　2026-07-27T10:01　[ai_unspecified] 獨立查核者（第二份；需求方轉錄）　🔧修正中　（result 未填）

### INGEST-GAME-TM-REFACTOR1　[C]

- 檔案：`docs/tasks/INGEST-GAME-TM-REFACTOR1.md`
- 實然型態：**全卡沒有任何 handoff 事件**，review 無所依附（新契約的 snapshot 無處可放）
- 信號 C3 **第一次 handoff 之前**的 review：
    - `INGEST-GAME-TM-REFACTOR1-REVIEW-005`　2026-07-24T11:13　[cross_family] Gemini（跨模型家族查核者）　✅通過／待合併
    - `INGEST-GAME-TM-REFACTOR1-REVIEW-008`　2026-07-24T12:53　[cross_family] Antigravity（Gemini 3.6 Flash，跨模型家族查核者）　✅通過／待合併

### INGEST-SPLITS-PA-SPLIT1　[EC]

- 檔案：`docs/tasks/INGEST-SPLITS-PA-SPLIT1.md`
- 宣告型態（建議）：Plan／Design Gate → 實作查核
- 實然型態：同輪第二意見（同性質查核者再查一次）
- 信號 E L151（交給：impl）：## Design Gate
- 信號 C1 同輪多筆 review（同輪第二意見（同性質查核者再查一次））：
    - `INGEST-SPLITS-PA-SPLIT1-REVIEW-007`　2026-07-30T01:05　[cross_family] 跨模型家族查核者（非 Claude；需求方轉錄，確切工具／模型待補正）　↩退回　REJECT（2 High＋1 Medium）
    - `INGEST-SPLITS-PA-SPLIT1-REVIEW-008`　2026-07-30T01:40　[cross_family] 第二跨模型家族查核者（非 Claude；需求方轉錄，確切工具／模型待補正）　↩退回　REJECT（1 High＋1 Medium；第二獨立查核）

### ML-MATCHUP1　[C]

- 檔案：`docs/archive/tasks/ML-MATCHUP1.md`
- 實然型態：**全卡沒有任何 handoff 事件**，review 無所依附（新契約的 snapshot 無處可放）
- 信號 C3 **第一次 handoff 之前**的 review：
    - `ML-MATCHUP1-REVIEW-003`　2026-07-16T17:06　[human] ruan6047　↩退回
    - `ML-MATCHUP1-REVIEW-004`　2026-07-16T21:30　[human] ruan6047　✅通過／待合併

### ML-OUTCOME-LEAK1　[C]

- 檔案：`docs/archive/tasks/ML-OUTCOME-LEAK1.md`
- 實然型態：有 handoff，但第一次 handoff 之前就有 review（Plan Gate 型）
- 信號 C3 **第一次 handoff 之前**的 review：
    - `ML-OUTCOME-LEAK1-REVIEW-006`　2026-07-27T03:30　[same_family] Claude subagent（Coordinator 委派之第二查核；新 　📦已合併

### ML-PITCHER-SCORELESS1　[C]

- 檔案：`docs/archive/tasks/ML-PITCHER-SCORELESS1.md`
- 實然型態：同輪多關卡（不同性質的查核者）
- 信號 C1 同輪多筆 review（同輪多關卡（不同性質的查核者））：
    - `ML-PITCHER-SCORELESS1-REVIEW-004`　2026-07-28T11:52　[cross_family] GPT-5.6@Codex（查核者；獨立 session，≠ 執行者）　↩退回　REJECT
    - `ML-PITCHER-SCORELESS1-REVIEW-005`　2026-07-28T12:02　[ai_unspecified] 第二位查核者（獨立 session；以 `git archive a0ba6　↩退回　REJECT

### ML-UMP2　[E]

- 檔案：`docs/archive/tasks/ML-UMP2.md`
- 宣告型態（建議）：Plan／Design Gate → 實作查核
- 信號 E L22（交給：impl）：## Plan Gate（07-16 需求方核可）

### OPS-REFRESH1　[C]

- 檔案：`docs/archive/tasks/OPS-REFRESH1.md`
- 實然型態：同輪多關卡（不同性質的查核者）
- 信號 C1 同輪多筆 review（同輪多關卡（不同性質的查核者））：
    - `OPS-REFRESH1-REVIEW-007`　2026-07-17T12:57　[human] ruan6047　↩退回　（result 未填）
    - `OPS-REFRESH1-REVIEW-009`　2026-07-18T14:20　[ai_unspecified] Claude Sonnet 5@Claude Code　✅通過　（result 未填）

### UX-DESIGN-SYSTEM1　[B]

- 檔案：`docs/archive/tasks/UX-DESIGN-SYSTEM1.md`
- 宣告型態（建議）：Plan／Design Gate → 實作查核
- 信號 B L13（交給：impl）：- Design：**Design Gate = ruan6047**（產出的 canonical 規格須經需求方 sign-off 才成為全站事實）

### UX-ENTITY-LINKS3　[BC]

- 檔案：`docs/archive/tasks/UX-ENTITY-LINKS3.md`
- 宣告型態（建議）：Plan／Design Gate → 實作查核
- 實然型態：跨輪不同性質關卡（人工審 → 新 handoff → AI 查核）
- 信號 B L11（交給：impl）：- Design：**Design Gate = ruan6047**（哪些出現位置該連、哪些不連；列表頁的互動取捨）
- 信號 C2 跨輪不同性質關卡：
    - `UX-ENTITY-LINKS3-REVIEW-005`　2026-07-29T22:31　[human] ruan6047（需求方本地人工審／Design Gate）
    - `UX-ENTITY-LINKS3-REVIEW-007`　2026-07-29T22:43　[cross_family] 跨模型家族查核者（非 Claude；需求方轉錄，確切工具／模型待補正）

### UX-GAME-PA1　[B]

- 檔案：`docs/tasks/UX-GAME-PA1.md`
- 宣告型態（建議）：Plan／Design Gate → 實作查核
- 信號 B L10（交給：impl）：- Design：spec v1.1 與 Design Brief 待需求方核可；實作前須補行動版與桌機互動 prototype

### UX-GAME-RECAP1　[B]

- 檔案：`docs/tasks/UX-GAME-RECAP1.md`
- 宣告型態（建議）：Plan／Design Gate → 實作查核
- 信號 B L10（交給：impl）：- Design：spec v1.1 與 Design Brief 待需求方核可；實作前須補 prototype／wireframe 與 Design Gate

### UX-LIVE-GAME1　[B]

- 檔案：`docs/tasks/UX-LIVE-GAME1.md`
- 宣告型態（建議）：Plan／Design Gate → 實作查核
- 信號 B L10（交給：impl）：- Design：[`../LIVE_GAME_PRODUCT_SPEC.md`](../LIVE_GAME_PRODUCT_SPEC.md) §6；Design Gate 待需求方核可

### UX-NAV-INTEGRATE1　[B]

- 檔案：`docs/archive/tasks/UX-NAV-INTEGRATE1.md`
- 宣告型態（建議）：Plan／Design Gate → 實作查核
- 信號 B L11（交給：impl）：- Design：**Design Gate = ruan6047**（§4.3 方向已 sign-off 2026-07-24；各頁成品仍須 UI 審）

### UX-PLAYER-FIELDVIZ1　[C]

- 檔案：`docs/archive/tasks/UX-PLAYER-FIELDVIZ1.md`
- 實然型態：有 handoff，但第一次 handoff 之前就有 review（Plan Gate 型）
- 信號 C3 **第一次 handoff 之前**的 review：
    - `UX-PLAYER-FIELDVIZ1-REVIEW-010`　2026-07-20T20:13　[cross_family] Antigravity　↩退回

### UX-TEAM-SPLIT-SCOPE1　[C]

- 檔案：`docs/archive/tasks/UX-TEAM-SPLIT-SCOPE1.md`
- 實然型態：**全卡沒有任何 handoff 事件**，review 無所依附（新契約的 snapshot 無處可放）
- 信號 C3 **第一次 handoff 之前**的 review：
    - `UX-TEAM-SPLIT-SCOPE1-REVIEW-005`　2026-07-25T02:10　[cross_family] Claude Opus 4.8（執行者，代 Coordinator 記錄跨家　🔍待查核

### UX-TOKEN-HYGIENE1　[B]

- 檔案：`docs/archive/tasks/UX-TOKEN-HYGIENE1.md`
- 宣告型態（建議）：Plan／Design Gate → 實作查核
- 信號 B L11（交給：impl）：- Design：**Design Gate = ruan6047**（動到色票須 sign-off）

## 讀法

- 應然（A／B／D／E／F）是卡面宣告，實然（C1／C2／C3）是 event log 已發生的事；**兩者經常不一致**，不一致本身就是要搬進結構化欄位的理由。
- **零命中 ≠ 單關卡**：只代表沒有可機械辨識的語式。已知至少五種語式，不能排除第六種。任何回填都須由需求方逐張確認。
- `⚠引用他卡` 是機械判準（命中行含別張卡卡號），不是人工排除清單；腳本不隱藏任何命中。
- actor 分類讀的是人工轉錄的字串，**工具無法驗證真實模型家族或人類身分**（契約 §8 Q4）。

