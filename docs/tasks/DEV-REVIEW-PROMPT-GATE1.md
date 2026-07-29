# DEV-REVIEW-PROMPT-GATE1 中繼查核關卡被守衛當成「本輪已結束」〔T2；🟡工具〕

- 需求：ruan6047（2026-07-29 於 `DEV-REVIEW-PROMPT-GUARD1` 交付時順帶發現，需求方指示直接執行）　規劃：本卡 spec　分支：`ai/<執行者>/DEV-REVIEW-PROMPT-GATE1`
- 執行：待指派（建議 L2；判準已由事件資料界定，非未知根因）　查核：待指派（建議 L2；≠ 執行。與 `DEV-REVIEW-PROMPT-GUARD1` 同檔，兩卡不得由同一人連續查核放行）
- Initiative：—　spec 基線：—
- DB：`db_scope: none`
- 部署：否　環境：—　PR：—　Merge SHA：—
- 範圍：`scripts/review_prompt.py`＋`tests/test_review_prompt.py`＋`docs/CONTROL_PLANE_CONTRACT.md`（新欄位的定義處）
- Discovery：—（T2，判準已由事件資料界定，見〈已排除的兩個直覺解〉）
- Design：Design Gate N/A——無使用者可見介面。
- **依賴：`DEV-REVIEW-PROMPT-GUARD1`（🔍待查核）**——同一支 `scripts/review_prompt.py`。本卡分支須從 GUARD1 的 `364112cfac889166eeeb92061536dbabc12dad24` 開，**merge 順序固定 GUARD1 → GATE1**；GUARD1 若被退回改寫，本卡須 rebase 重驗。

## 問題陳述

`_assert_no_review_supersedes_handoff()` 在「最新 handoff 之後存在 review 事件」時拒絕產生提示詞，理由是「這一輪查核已結束」。

那是拿**「有沒有 review 事件」當作「這一輪結束了沒」的標記**。兩者在單關卡的卡上重合，在**多關卡**的卡上不重合——`UX-ENTITY-LINKS2` 卡面 L40 明訂「先本地人工審再交跨家族查核」，2026-07-29 需求方的人工審 APPROVE 寫成 `REVIEW-007`（`delivery_status` 維持 `🔍待查核`、`owner` 改為「待指派（跨家族查核者）」），那是**第一關通過**，不是本輪結束。守衛據此拒絕產生提示詞，**該卡現在無法派跨家族查核**。

**比阻擋更危險的是它給的處置建議。** 拒絕訊息寫死：

> 若為 APPROVE：接續 merge／結案流程，不需要再查核一次。

對這張卡而言，照做就是**把一個必要查核從未發生的交付直接 merge**。守衛把自己的誤判包裝成了指令。

## 已排除的兩個直覺解（依 146 筆 review 事件實測，勿再提案）

**不能用 `delivery_status` 判斷。** 全部 146 筆 review 事件中，17 筆的 `delivery_status` 是 `🔍待查核`；其中 9 筆 `review_result` 明寫 APPROVE，且逐一追下一個事件——`UX-ENTITY-LINKS1`、`UX-DESIGN-CONFORM1`、`GAME-RECAP-WP-CAL1`、`OPS-LIVE-SHADOW1` 的下一筆都是 `merge`。**最終 APPROVE 與中繼關卡在這個欄位上長得一模一樣**，拿它當判準會讓守衛對真正該擋的情形失效。

**不能用 `owner` 字串比對。** 中繼關卡的 owner 是「待指派（跨家族查核者；≠ 執行者 Claude Opus 5）」，看似可用「owner 還在查核方」判定；但最終 APPROVE 的 owner 寫的是「Opus 4.8（執行，**交付待查核**）」——**本身就含「查核」二字**。子字串比對會把終局判成中繼，方向正好是最危險的那一邊。free-text 欄位承載不了這個性質。

結論：**這個性質目前沒有任何機器可讀的欄位表達它**。正解不是從既有欄位猜得更聰明——那是同一種病的複發——而是**讓它變成顯式欄位**。

## 目標

review 事件新增一個**選填**欄位，明確表達「這一筆是否終結本輪查核」（欄名由執行者定，例如 `closes_review_round: false` 表示中繼關卡）。守衛改為：最新 handoff 之後的 review 中**存在終結本輪者**才拒絕；全部都是中繼關卡時放行，並把**已通過關卡的結論帶進提示詞**（Design Gate 的裁定是下一位查核者必須知道的前提，不能只留在事件裡）。

欄位定義寫進 `CONTROL_PLANE_CONTRACT.md`（envelope 的擁有者），否則沒人會寫這個欄位。

## 紅線（違反即退回）

1. **不得用 free-text 欄位（`owner`／`review_result`／`evidence`）的子字串比對推斷**——上節資料已證明會把終局判成中繼。
2. **歷史事件不得被重新解讀**：欄位缺席一律視為終結本輪，行為與現況逐字相同。146 筆既有事件的判定結果不得有任何一筆改變（須以腳本窮舉比對，不得人工聲明）。
3. **拒絕訊息不得斷言「不需要再查核一次」**。守衛不知道那件事，它只知道事件裡寫了什麼。訊息須呈現事件實況並列出兩種可能與各自處置。
4. **不得提供跳過守衛的 CLI 旗標。** 可被靜默使用的逃生口正是這批卡在修的病；要放行必須留痕在 event log（寫欄位＝留痕），不能留在某人的 shell history 裡。
5. 欄位型別不合預期（非布林）時 **fail loud**，不得當成缺席帶過。

## 驗收條件

- [ ] review 事件支援表達「中繼關卡」的顯式選填欄位；欄位語意、預設值與寫入時機寫進 `CONTROL_PLANE_CONTRACT.md`。
- [ ] 守衛只在「存在終結本輪的 review」時拒絕；全為中繼關卡時放行。
- [ ] 放行時，提示詞含「已通過的中繼關卡」段落，逐筆列出關卡的 actor、時間、結論與 evidence 原文，並明講**這不代表本輪結束**。
- [ ] 拒絕訊息重寫：不再斷言「不需要再查核一次」，改為呈現事件實況＋兩種可能的處置（終局 → 接 merge／結案；其實是中繼關卡 → 依新欄位補留痕再重跑）。
- [ ] 紅線 2 的窮舉證明：對現有 146 筆 review 事件跑新舊兩版判定，逐筆一致（差異數 0），證據由腳本產生而非人工聲明。
- [ ] `uv run ruff check` ＋ `uv run pytest` 全綠；新增涵蓋中繼／終局／混合／欄位型別錯誤四種情形的迴歸測試。

## 驗證

- [ ] 查核者以 `UX-ENTITY-LINKS2` 實測：補上中繼欄位的事件後守衛放行、提示詞帶出人工審的 Design Gate 裁定；不補則維持拒絕但訊息正確。
- [ ] 查核者確認 `workflow_ledger.py --check` 對帶新欄位的事件不報錯（ledger 對未知欄位寬容，須實測而非引用）。
- [ ] 查核者自行構造「中繼關卡之後又有終局 REJECT」的事件序列，確認守衛仍拒絕（中繼不得成為繞過退回的手段）。
- [ ] 查核者確認 `DEV-REVIEW-PROMPT-GUARD1` 的三處修正在本卡分支上未被破壞。

## 邊界

- 只動守衛與其訊息、新欄位的契約定義與測試；不改 review 事件的既有欄位、不改 `workflow_ledger.py`、不回填歷史事件。
- 不處理「誰有權宣告中繼關卡」的治理問題（那是流程決定，不是工具）。
- 預估 S。

## Log

- 2026-07-29 register by Claude Opus 5@Claude Code（Coordinator）。於 `DEV-REVIEW-PROMPT-GUARD1` 交付時順帶發現並回報，需求方同日指示「直接執行任務」。開卡前先對 146 筆 review 事件實測，排除 `delivery_status` 與 `owner` 兩個直覺解，判準因此改為新增顯式欄位。
