# DEV-REVIEW-GATE-DECLARE1 卡面 review_gates 宣告與 handoff 快照〔T3；🟡工具＋流程〕

> ⚠ **本卡尚未 register**：規劃階段交付，未寫任何 lifecycle event、未動 `docs/TASKS.md`。
> 契約 [`../REVIEW_GATE_CONTRACT.md`](../REVIEW_GATE_CONTRACT.md) §8 的未決事項已於 2026-07-31 全數定案。
> **本卡是兩卡中的第二步，須待 `DEV-REVIEW-GATE-CONTRACT1` 合併後才動工。**
> 🚧 **開卡阻塞（2026-07-31）**：與已生效的 WF-21 審核契約（`contract_baseline:
> review-escalation-v1`，adapter merge `f86bd5e`）有硬衝突——`review-correction` 型別撞名、
> `review_result` 已是 enum、「一輪」與 WF-21 的 attempt 識別鍵不同、preflight 重複發明。
> 逐項見契約 §9。**v0.4 對齊前不得 register。**

- 需求：ruan6047（2026-07-31 指示重規劃 `DEV-REVIEW-PROMPT-GATE1` ＋ `DEV-REVIEW-INDEP-FIELD1`）　規劃：本卡 spec ＋ 契約草案 v0.3　分支：`ai/<執行者>/DEV-REVIEW-GATE-DECLARE1`
- 執行：待指派（建議 L3；動到全專案卡片填寫慣例與三份契約文件，屬跨檔取捨）　查核：待指派（建議 L2；≠ 執行）
- review_gates: [final=cross_family_or_human]
- Initiative：—　spec 基線：`REVIEW_GATE_CONTRACT.md` v0.3
- DB：`db_scope: none`
- 部署：否　環境：—　PR：—　Merge SHA：—
- 範圍：`docs/REVIEW_GATE_CONTRACT.md`（§2／§3.1／§5 併入下列文件後降為歷史）、`docs/TEMPLATES.md`、`docs/CONTROL_PLANE_CONTRACT.md`、`docs/HANDOFF_CONTRACT.md`、**新增 `scripts/review_gate_preflight.py`**、`scripts/review_gate_inventory.py` ＋兩者的測試、活卡按需回填
- Discovery：[`../discovery/DEV-REVIEW-GATE-DECLARE1-discovery.md`](../discovery/DEV-REVIEW-GATE-DECLARE1-discovery.md)（承接並修正 `DEV-REVIEW-INDEP-FIELD1` 的四問答案）
- Design：Design Gate N/A——無使用者可見介面。
- **依賴：`DEV-REVIEW-GATE-CONTRACT1`**（契約 v0.3 §7）——守衛先就位（合併時全庫走 legacy、行為零變更），本卡合併後 snapshot 開始出現、狀態機自動生效，中間無空窗。**merge 順序固定 CONTRACT1 → DECLARE1**；CONTRACT1 若被退回改寫，本卡須 rebase 重驗。
- 前身：`DEV-REVIEW-INDEP-FIELD1`（🏁完成）。本卡把該卡交付的 `review_independence` 升級為帶 `gate_id` 的 `review_gates`，並補上它缺的那一半：**要求要能被快照進事件**。

## 問題陳述

`DEV-REVIEW-INDEP-FIELD1` 讓「這張卡需要哪一種查核獨立性」變成機器可讀欄位，這一步是對的。
但它把「有幾關」放在卡面、把「跑到哪一關」放在 event log，並宣告兩者「互不為事實來源」。
**互不為事實來源的代價是：沒有任何一邊知道完整答案。** 卡面知道有三關卻不知道跑到哪，
事件知道跑了兩筆卻不知道那是哪兩關；工具因此無法察覺跳關，也無法告訴下一位查核者
「你負責的是第幾關、那一關要什麼獨立性」。

更根本的是**卡面會被就地改寫**。`UX-LIVE-GAME1` 的〈Design〉欄原本寫「Design Gate 待需求方
核可」，2026-07-30 核可後被改成「2026-07-30 需求方核可 live-only v1」——**要求本身從卡面
消失了**。盤點腳本在 `81bcd4d` 與 HEAD 兩個 revision 上跑出的差異就是這一張。只要要求只活在
卡面，歷史就會被日後的編輯重新解釋。

## 目標

一、卡面欄位由 `review_independence`（值的清單）升級為 `review_gates`（`gate_id=requirement`
的有序清單），`gate_id` 卡內唯一且穩定；空清單 `[]` 是「本卡不直接交付查核」的**顯式宣告**。

二、**handoff event 必須快照該輪的 `review_gates`**，該快照即該輪不可變的流程基線；卡面日後
被改不重解歷史。快照與卡面不一致時並列印出、不擋、工具不仲裁。

三、**新增 preflight（`scripts/review_gate_preflight.py`）**：在寫 handoff event **之前**驗卡面
欄位、產生 snapshot，缺欄或寫壞就擋下 handoff。驗證不能等到產生提示詞——那時事件已經進
append-only log 了。

四、把上述寫進 `TEMPLATES.md`（卡面寫法、cutover 與遷移程序）、`CONTROL_PLANE_CONTRACT.md`
（envelope、職權與保證邊界）、`HANDOFF_CONTRACT.md`（sender 快照責任、receiver 確認 pending gate）。

五、多關卡盤點腳本 `scripts/review_gate_inventory.py` 納管並補測試——遷移決策依它的**分類與
計數**輸出，不依人工聲明。

規格逐條見 [`../REVIEW_GATE_CONTRACT.md`](../REVIEW_GATE_CONTRACT.md) §2、§3.1、§5、§6，
**本卡不重複數字**。

## 紅線（違反即退回）

1. **不得從任何自由文字推斷流程門檻**——`GUARD1` 三輪被打穿後的定案。`gate_id` 與
   `requirement` 只做語法檢查與值域比對；盤點腳本的分類欄**不得**被 preflight 消費。
2. **cutover 後缺欄一律 preflight fail**：不得退化成 tier 下限，也不得回退成自由文字人工
   猜測；**不得用缺欄暗示不需查核**（不需要就明寫 `[]`）。
3. **不得回填猜測的值**：自由文字語意不明或自我矛盾（信號 F 的 2 張）時標為待需求方裁定並
   **暫不填**。封存卡一律不動。
4. **不得改寫既有事件、不得回填歷史 handoff 的快照。** cutover 前沒有快照的輪次走 legacy。
5. **盤點的完整性宣稱必須由腳本產生**：任何「共 N 張」都要指向可重跑的輸出檔。

## 驗收條件

- [ ] `TEMPLATES.md` 的 `review_independence` 段改寫為 `review_gates`：格式、`gate_id`
      pattern 與穩定性、值域、`[]` 的語意、舊欄名等價規則、**cutover 日期**與遷移程序。
- [ ] `CONTROL_PLANE_CONTRACT.md` 的 `closes_review_round` 條目換成 gate 契約，並載明
      「快照是該輪不可變的流程基線」與契約 §2.1 的**保證邊界五條**（含「工具不能驗證
      reviewer 身分」與「衝突時以結構化欄位決定流程、自由文字只作說明」）。
- [ ] `HANDOFF_CONTRACT.md`：sender 寫 handoff 前須跑 preflight 並快照 `review_gates`；
      receiver acceptance checklist 增一項「確認本輪 pending gate 的 `gate_id` 與 requirement」。
- [ ] `scripts/review_gate_preflight.py`：`--check` 與 snapshot 產生兩種模式；缺欄／
      `gate_id` 重複或不合 pattern／值域外／多行一律非 0 退出，**訊息不得提供任何 fallback**；
      宣告 `[]` 的卡 `--check` 通過但寫 handoff 時 fail。
- [ ] 活卡按需回填：僅回填**下一次 handoff 前**需要的卡，逐張由需求方裁定值；交付摘要逐張
      列出「填了什麼、依據是什麼」，未裁定者明列為待裁定（含信號 F 的自我矛盾卡）。
- [ ] `scripts/review_gate_inventory.py` 納管並補測試：信號 A／B／D／E／F 與 C1／C2／C3 各至少
      一個 fixture、引文標記、分類三型（human→cross_family／human→一般 AI／plan→impl）
      不得互相污染、`--rev` 可重現。
- [ ] `uv run ruff check` ＋ `uv run pytest` 全綠。

## 驗證

- [ ] 查核者以 `--rev 81bcd4d` 重跑盤點，確認結果與交付的輸出檔逐字相同（數字可獨立重現）。
- [ ] 查核者確認需求方指定重檢的 9 張卡在報告中**逐張出現**，且三種流程分類正確：
      `UX-DESIGN-CONFORM1`／`UX-ENTITY-LINKS1`／`UX-ENTITY-LINKS2` 為 human→cross_family；
      `UX-TEAM-HOTZONE1`／`UX-TEAM-RECORDS1`／`UX-TEAM-STYLE1` 為 human→一般 AI；
      `OPS-LIVE-SHADOW1` 為 Plan Gate→implementation；兩張 `DEV-REVIEW-*` 為引文命中。
- [ ] 查核者確認 `workflow_ledger.py --check` 對帶 `review_gates` 快照的 handoff 事件
      不報錯（ledger 對未知欄位寬容，須**實測**而非引用）。
- [ ] 查核者確認三份契約文件對「卡面 vs 快照」「欄位 vs 自由文字」的敘述互不矛盾，
      且沒有任何一處要求工具仲裁或宣稱已驗證 reviewer 身分。
- [ ] 查核者抽驗回填的活卡：發現任何一張的值是推定而非需求方裁定，即退回。

## Release 後追蹤（非驗收條件，契約 §8）

- 合併後第一個月追蹤「新寫的 handoff 是否 **100%** 帶 snapshot」。preflight 若真的擋在寫入
  路徑上，這個數字必然是 100%；不是就代表有人繞過 preflight 手寫事件——那是機制沒落地的
  早期訊號。`closes_review_round` 在全庫 887 筆事件裡用過 **0 次**，這個追蹤就是為了不重蹈。

## 邊界

- 只改「要求怎麼被宣告、驗證與快照」；**守衛與狀態機由 `DEV-REVIEW-GATE-CONTRACT1` 承接**，
  本卡不動 `scripts/review_prompt.py` 的判定邏輯（讀新欄位的改動屬該卡）。
- 不處理「誰有權宣告 gate」的治理問題。**Design Gate／Plan Gate 進 `review_gates` 屬本卡
  範圍**（契約 §5.3：Plan 本身就是一次交付，先寫 handoff 再送查核），但既有 14 張宣告
  Plan／Design Gate 的卡不批次回填。
- **不做跨輪繼承**（契約 v0.3 §3.1 移除 `satisfied_by`）：一輪內的 gate 必須在該輪內完成。
- 不批次回填、不動封存卡、不補歷史 handoff。
- 預估 M。

## Log

- 2026-07-31 規劃 by Claude Fable 5@Claude Code。需求方指出 `DEV-REVIEW-PROMPT-GATE1`
  與 `DEV-REVIEW-INDEP-FIELD1` 形成雙重狀態來源，指示收斂成單一 Review Gate 契約。
  本卡承接後者，未 register。
- 2026-07-31 需求方裁定 Q2 遷移策略與 Q4 保證邊界（契約 v0.2 §5.1／§5.2／§2.1）；
  據此新增 preflight 為本卡交付物，缺欄行為由「明示＋tier 下限」改為 **cutover 後硬失敗**，
  自由文字由「以此為準」降為「只作說明」。盤點腳本同日升級為分類與計數，
  並查出第五種語式（`## Plan Gate` 章節）與兩種無 handoff 可掛快照的歷史形態。
- 2026-07-31 需求方採納規劃者對五項未決的建議（契約 v0.3 §8）：本卡**改為第二步**
  （CONTRACT1 先無害落地、無空窗）、`satisfied_by` 移除、Plan Gate 改為先寫 handoff 再送查核、
  新增 release 後追蹤指標。
- 2026-07-31 **WF-21 稽核（開卡前）**：發現規劃期工作樹停在 `063d12d`，而 `origin/main`
  已推進到 `37431a0`——WF-21 審核契約當日 10:41 全鏈落地（`contract_baseline:
  review-escalation-v1`），`workflow_ledger.py` 多 409 行 fail-loud 驗證。本卡與其有
  硬衝突（`review-correction` 撞名、`review_result` 已是 enum、輪次識別鍵不同、
  preflight 重複）。逐項與處置寫入契約 §9，**兩卡暫緩 register，待 v0.4 對齊**。
