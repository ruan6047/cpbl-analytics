# DEV-REVIEW-GATE-CONTRACT1 守衛改以 gate 狀態機判定本輪查核〔T3；🟡工具〕

> ⚠ **本卡尚未 register**：規劃階段交付，未寫任何 lifecycle event、未動 `docs/TASKS.md`。
> 契約 [`../REVIEW_GATE_CONTRACT.md`](../REVIEW_GATE_CONTRACT.md) §8 的未決事項已於 2026-07-31 全數定案，
> 開卡即可執行。**本卡是兩卡中的第一步。**
> 🚧 **開卡阻塞（2026-07-31）**：與已生效的 WF-21 審核契約（`contract_baseline:
> review-escalation-v1`，adapter merge `f86bd5e`）有硬衝突——`review-correction` 型別撞名、
> `review_result` 已是 enum、「一輪」與 WF-21 的 attempt 識別鍵不同、preflight 重複發明。
> 逐項見契約 §9。**v0.4 對齊前不得 register。**

- 需求：ruan6047（2026-07-31 指示重規劃 `DEV-REVIEW-PROMPT-GATE1` ＋ `DEV-REVIEW-INDEP-FIELD1`）　規劃：本卡 spec ＋ 契約草案 v0.3　分支：`ai/<執行者>/DEV-REVIEW-GATE-CONTRACT1`
- 執行：待指派（建議 L3；判定邏輯換模型且要保住 legacy 逐字相容）　查核：待指派（建議 L2；≠ 執行。與 `DEV-REVIEW-GATE-DECLARE1` 同一契約，兩卡不得由同一人連續查核放行）
- review_gates: [final=cross_family_or_human]
- Initiative：—　spec 基線：`REVIEW_GATE_CONTRACT.md` v0.3
- DB：`db_scope: none`
- 部署：否　環境：—　PR：—　Merge SHA：—
- 範圍：`scripts/review_prompt.py`、`tests/test_review_prompt.py`、`docs/CONTROL_PLANE_CONTRACT.md`（§3.2／§3.3 事件欄位的定義處）
- Discovery：—（T3，判準已由契約草案 §3／§4 完全界定）
- Design：Design Gate N/A——無使用者可見介面。
- **依賴：無。本卡先行。**（契約 v0.3 §7 對調順序）legacy 相容讓本卡可**無害落地**：合併當下全庫沒有任何 snapshot，100% 走 legacy、行為零變更；`DEV-REVIEW-GATE-DECLARE1` 隨後合併，snapshot 開始出現，狀態機自動生效，**中間沒有空窗**。反過來做會讓「卡面已帶 gate、守衛仍用舊邏輯」的空窗期繼續誤擋多關卡的卡。本卡只依賴契約文件的 schema 定義，測試用 fixture。
- 前身：`DEV-REVIEW-PROMPT-GATE1`（🏁完成）。本卡以 gate 狀態機取代該卡交付的 `closes_review_round`／`corrects_event_id`。

## 問題陳述

`DEV-REVIEW-PROMPT-GATE1` 讓「中繼關卡」變成顯式欄位，方向正確；但它給的是**一個布林**，
而要表達的是**一個有序序列的進度**。三個後果，全部可在現行 main 上重現：

**一、終局 REJECT 可以被一筆追加事件重新開啟。** 追加一筆帶 `corrects_event_id` 指向該
REJECT 的 `closes_review_round: false`，守衛即放行同一個 handoff。`GATE1` iteration 1 曾用
「以最新一筆為準」達成同樣效果並被退回，改為「更正須指名對象」後**路徑變窄但沒有消失**，
且更正之間仍是 latest-wins。

**二、被重開後，那筆 REJECT 會被印在「已通過的中繼關卡」標題下。** 2026-07-31 實測輸出：
標題寫「本輪已通過的中繼關卡」，內文寫「結論：REJECT（3 blocking）」，下一行還告訴查核者
「不要重開已定案的爭點」。守衛把一次退回描述成一次通過——這是 `GATE1` 紅線 3
（「守衛不知道那件事，它只知道事件裡寫了什麼」）的同型復發。

**三、布林分不出「多關卡」與「同一關的第二意見複審」。** 盤點分出同輪多關卡 6 張、
同輪第二意見 1 張，但**分辨的唯一依據是 actor 字串的中文**：`UX-ENTITY-LINKS2` 是真的兩關
（需求方人工審 → 跨家族），`INGEST-SPLITS-PA-SPLIT1` 是同一關找第二位跨家族查核者，
`ML-PITCHER-SCORELESS1` 兩位查核者的字串一個寫「GPT-5.6@Codex」一個寫「第二位查核者
（獨立 session）」——**盤點只能把它歸成「不同性質」，判不出那其實是第二意見**。
`LIVE-GAME-BACKEND1` 更是 APPROVE 之後複審翻成 REJECT。這個洞正是 `gate_id` 要補的：
同 `gate_id` ＝ 第二意見，不同 `gate_id` ＝ 多關卡，不必讀任何中文。

另外，判定通過與否目前也沒有機器可讀來源：171 筆 review 中 **106 筆沒有 `review_result`**，
其餘是自由文字。

> **對前提的一項修正**：「非布林欄位只驗最後一筆、較早 malformed 可被掩蓋」在現行實作上
> **不成立**——`_closes_review_round()` 對該卡每一筆 review 都驗，含前幾輪，已有測試覆蓋。
> 真正未涵蓋的是 **`corrects_event_id`**：上一輪一筆 `corrects_event_id: 99`（int）
> 完全不被檢查即通過（2026-07-31 實測）。本卡按「本輪逐筆全驗」收斂，順帶蓋掉這個缺口。

## 目標

守衛改以 [`../REVIEW_GATE_CONTRACT.md`](../REVIEW_GATE_CONTRACT.md) §4 的狀態機判定：
handoff 快照定義本輪 gates，review 以 `gate_id` ＋ `gate_result` 推進，
所有 gate 完成才算本輪通過，任一 `request_changes` 立即終結本輪，終結後普通 review
一律 fail loud、只有新 handoff 能開新一輪；更正走顯式 `review-correction`，且
**由終結變回 open 必須帶 `reopens_round: true`**。`closes_review_round` 廢止。
legacy（無快照）行為與現況**逐字相同**。

## 紅線（違反即退回）

1. **不得從 `review_result`／`owner`／`delivery_status`／evidence 的字面推斷 gate 或結果。**
2. **歷史不得被重新解讀**：全庫 887 筆事件的判定結果不得有任何一筆改變，且**須由腳本
   窮舉比對新舊兩版**（差異數 0），不得以人工聲明承載。
3. **終結後不得由普通 review 重開**；重開只能經 `review-correction` ＋ `reopens_round: true`
   ＋ `reason`，且該情形須在提示詞**置頂**告示、印出原 REJECT 全文。
4. **`gate_result: request_changes` 的事件永遠不得出現在「已通過的關卡」段落。**
5. **不得提供跳過守衛的 CLI 旗標**；放行必須留痕在 event log。
6. 型別／值域／`gate_id` 不合預期時 **fail loud**，且驗證涵蓋本輪**每一筆** review 與
   correction，不得只驗最後一筆。

## 驗收條件

- [ ] `review_prompt.py` 依契約 §4 的狀態機判定；`CLOSES_ROUND_FIELD` 移除，事件若仍帶該
      欄位則 fail loud 並指向新契約。
- [ ] 放行時提示詞明講：本輪共幾關、**pending 是哪一關**、該關 requirement 為何、
      已通過的關卡逐筆（actor／時間／`gate_id`／evidence 原文）、以及「這不代表本輪結束」。
- [ ] 拒絕訊息依終結原因分流：`passed` → 接 merge／結案；`changes_requested` → 退回原
      執行者、修正後補**新 handoff**（不再是「兩種可能請你判斷」）。
- [ ] correction 的全部非法形態 fail loud（見契約 §4 末四列）；合法更正重算整輪並印出更正鏈。
- [ ] **不繼承**（契約 v0.3 §3.1）：第一關 approve 之後出現新 handoff → pending 回到第一關；
      事件若帶 `satisfied_by` → fail loud（該欄位不在契約裡，默默忽略等於讓寫的人誤以為生效）。
- [ ] legacy：無快照的 handoff 走單關卡解讀，拒絕訊息與現行**逐字相同**（golden 比對）。
- [ ] 紅線 2 的窮舉證明：新舊兩版對全庫事件逐卡逐輪比對，差異 0，證據由腳本產生。
- [ ] **保證邊界落地（契約 §2.1）**：輸出移除「卡面〈查核〉欄原文（**以此為準**）」與
      「卡面若要求得比下限嚴……一律以卡面為準」兩處措辭——〈查核〉欄仍原文照登但**不再是流程
      依據**；同時把宣告值與最近 review 的 actor 並列，並**明寫工具無法驗證 reviewer 身分、
      這是人工核對輔助**。此為相對 `DEV-REVIEW-INDEP-FIELD1` 的**行為變更**，須有字串斷言鎖住。
- [ ] `uv run ruff check` ＋ `uv run pytest` 全綠；測試覆蓋契約 §7 列出的全部性質。

## 驗證

- [ ] 查核者自行構造「第一關 approve → 第二關 request_changes → 再追加一筆 approve」，
      確認第三筆 fail loud 而非放行。
- [ ] 查核者自行構造「終局 request_changes → correction 指名它改成 approve 但**不帶**
      `reopens_round`」，確認 fail loud；帶旗標時確認輸出置頂告示且原 REJECT 全文在列。
- [ ] 查核者確認任一含 `request_changes` 的事件在所有輸出路徑上都**不會**被歸入
      「已通過的關卡」。
- [ ] 查核者確認本卡實作與契約 v0.3 §3／§4 逐條對得上，不一致即退回（以文件為準）。
- [ ] 查核者確認**合併後行為零變更**：全庫沒有任何 handoff 帶 snapshot，所有卡都走 legacy。
- [ ] 查核者確認輸出中**不存在**任何把自由文字當成流程依據的措辭（契約 §2.1 第 5 條），
      且**不宣稱**已驗證 reviewer 的模型家族或人類身分（第 4 條）。
- [ ] 查核者實測既有卡（例：`UX-ENTITY-LINKS2`、`ML-PITCHER-SCORELESS1`）的提示詞產生結果
      與合併前逐字相同。

## 邊界

- 只動守衛、其訊息、事件欄位的消費與測試；**卡面欄位格式、preflight 與遷移屬 `DEV-REVIEW-GATE-DECLARE1`**（第二步）。
- 不回填歷史事件、不改 `workflow_ledger.py`、不動封存卡。
- 第二意見複審**可以**推翻已通過的 gate（契約 §8 第 3 項已定案），本卡照此實作，不另立規則。
- 預估 M。

## Log

- 2026-07-31 規劃 by Claude Fable 5@Claude Code。需求方指出 `closes_review_round` 與卡面
  `review_gates` 形成雙重狀態來源，並要求終局 REJECT 不得被追加事件重開。本卡承接
  `DEV-REVIEW-PROMPT-GATE1`，未 register。
- 2026-07-31 需求方裁定 Q4 保證邊界（契約 §2.1）：`review_gates` 是要求的權威來源、
  snapshot 是該輪不可變基線、`gate_id` 是完成哪一關的留痕、工具不宣稱驗證 reviewer 身分、
  **欄位與自由文字衝突以欄位決定流程**。末項使本卡多一項行為變更（移除兩處「以卡面為準」
  措辭），已寫入驗收條件。
- 2026-07-31 需求方採納規劃者對五項未決的建議（契約 v0.3 §8）：本卡**改為第一步**（legacy
  相容可無害落地、無空窗）、`satisfied_by` 移除（改為「不繼承」並對該欄位 fail loud）、
  第二意見維持可推翻、`review_result` 不結構化、卡 ID 用後繼卡。
- 2026-07-31 **WF-21 稽核（開卡前）**：發現規劃期工作樹停在 `063d12d`，而 `origin/main`
  已推進到 `37431a0`——WF-21 審核契約當日 10:41 全鏈落地（`contract_baseline:
  review-escalation-v1`），`workflow_ledger.py` 多 409 行 fail-loud 驗證。本卡與其有
  硬衝突（`review-correction` 撞名、`review_result` 已是 enum、輪次識別鍵不同、
  preflight 重複）。逐項與處置寫入契約 §9，**兩卡暫緩 register，待 v0.4 對齊**。
