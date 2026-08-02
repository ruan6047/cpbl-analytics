# DEV-CI-RED-OWNERSHIP1 main 紅燈無歸屬：「非本卡引入」沒有強制去向〔T3；🟡流程〕

- 需求：ruan6047（2026-08-02 於 `UX-LIVE-TRACKMAN1` 基線欄修復後指示一併處理，授權開卡）　規劃：本卡 spec　分支：`ai/<執行者>/DEV-CI-RED-OWNERSHIP1`
- 執行：待指派（建議 L3；要在「不新增儀式性負擔」與「紅燈不得無限期繼承」之間取捨，且守衛不能誤傷正當的延後決定）　查核：待指派（建議 L2；≠ 執行）
- review_independence: [cross_family]
- Initiative：—　spec 基線：—
- DB：`db_scope: none`
- 部署：否　環境：—　PR：—　Merge SHA：—
- 範圍：`docs/CONTROL_PLANE_CONTRACT.md`、`docs/REVIEW_GATE_CONTRACT.md`，視 Discovery 結論可能加 `scripts/review_prompt.py`、`scripts/workflow_ledger.py` 與對應測試
- Discovery：**本卡第一項交付是「該不該用工具擋、以及擋在哪一關」的判斷**，不是直接改碼。
- Design：Design Gate N/A——無使用者可見介面。

## 問題陳述

查核與 merge 流程**能標示**外部紅燈，但**沒有機制把它變成待辦**。當紅燈落在別人的卡上時，最省力的路徑是在 evidence 寫一句「非本卡引入」然後繼續，而流程不會攔——merge gate 只看本卡交付，不看 main 當前是否已紅。

`pytest` 的 `test_initiative_children_baseline_matches_parent_version` 是完整的一次示範。它自 `3c95dce`（2026-08-01T17:48，`UX-LIVE-TRACKMAN1` 註冊時漏填 `spec 基線`）起紅燈，到 `8711afd`（2026-08-02T12:34）才修，窗期 **18 小時 46 分**。期間：

- 被 **5 筆 lifecycle event 記錄**為「非本卡引入」：`UX-TOKEN-ACCENT-CONTRAST1-MERGE-008`、`UX-BRAND-HOME1-HANDOFF-006`／`HANDOFF-008`／`REVIEW-010`／`MERGE-011`。其中 `MERGE-008` 還特地回頭在前一個 commit 復現失敗以自證清白——**診斷做得比修復還徹底**。
- 被 **1 張新卡寫成豁免條款**：`DEV-EVENT-SCHEMA-GUARD1` 的驗收條件明列「既有紅燈 `test_initiative_children_baseline_matches_parent_version` 屬 `UX-LIVE-TRACKMAN1`，不計入本卡」。紅燈開始被**下游卡繼承為背景噪音**。
- main 累積 **24 個 commit**，含 `UX-TOKEN-ACCENT-CONTRAST1`（`a739b60`）與 `UX-BRAND-HOME1`（`44deedf`）兩張卡的 `--no-ff` merge，以及一次生產部署紀錄（`634fbcb`）。CI 設定為 `push: [main]`，故這段期間**每一次 push 都是紅的**，兩次 merge 與一次部署都在紅燈上完成。
- 最終修復的觸發不是流程，是**需求方手動把它當成一件雜事派給一個 session**。若沒有這一步，`DEV-EVENT-SCHEMA-GUARD1` 的豁免條款會繼續被後續卡複製。

歸屬的斷點很明確：**發現者不是責任人**（紅燈屬別卡，代改會污染受審範圍，這個判斷本身是對的），**責任人不在場**（`UX-LIVE-TRACKMAN1` 是 Backlog 卡、owner 待指派、沒有 session 在跑），於是觀察落地成文字就停住。

## 既有路徑有時是有效的（不可一概而論）

同型觀察在別處確實有被接住，本卡**不應**把「寫下非本卡引入」本身當成缺陷：

- **另開卡並指名**：`UX-LEADERS-ORPHAN1-REVIEW-004` 把 `npm ci` 的 3 high＋1 critical 指向 `OPS-WEB-DEPS1` 追蹤——去向明確，這是正解。
- **收進自己的驗收條件**：`ML-OUTCOME-SIMPLE-LEAK2` 把 `refresh-cpbl-prod.sh:236` 的既有缺陷寫成驗收項目，沒有另開卡但有人負責。
- **就地修掉**：`UX-NAV-IA1`、`UX-PLAYER-IA2`、`UX-TEAM-HOTZONE1` 三卡都在自己範圍內修了線上既有缺陷。
- **正確地丟棄**：`UX-PLAYER-SECTIONS1-HANDOFF-003` 記的 dev StrictMode 重複請求只存在於開發模式，不轉卡是對的。

四條路徑都合理，問題在於**選哪一條完全靠當事人自覺，且「什麼都不選」沒有成本**。本卡要補的是那個缺口，不是取消判斷空間。

## 非目標

- **不要求每個「非本卡引入」的觀察都開卡。** 上一節四條路徑都該保留；強制開卡會製造儀式性負擔並淹沒 Backlog。
- **不要求發現者代修別卡的紅燈。** 代修會污染受審範圍，現行判斷是對的。
- 不改 review 契約的 escalation 計數、finding 衝突裁決或 `closes_review_round` 語意。
- 不處理「紅燈以外的既有缺陷」（線上 bug、效能問題）的歸屬——本卡只收**可由 CI 機械判定的紅燈**，範圍才守得住。

## Discovery 必答（先答再改碼）

1. **擋在哪一關？** 候選：(a) merge gate 前置條件加「main 當前為綠，或紅燈已有指名的 owner 卡」；(b) `review_prompt.py` 產生提示詞時帶入 main 當前 CI 狀態，讓查核者無法「不知道」；(c) 只寫進契約，不做工具。**各自擋得住什麼、擋不住什麼要明寫**——特別是 (a) 會不會在紅燈期間把所有卡一起鎖死，那是比紅燈更貴的代價。
2. **判準是什麼？** 「main 是紅的」要如何機械判定：本地重跑 `pytest`？讀 GitHub Actions 最近一次 `push: main` 的結論？前者慢且環境相依，後者需要 API 且離線時無解。**選一邊並說明離線／API 不可用時的退化行為。**
3. **紅燈的合法去向有哪幾種、各自要留什麼痕？** 上一節的四條路徑要不要收斂成機器可讀的宣告（例如 handoff 事件的 `known_red` 欄位帶 `owner_card` 或 `disposition`）？若收斂，**baseline 前的既有事件不得因此開始失敗**。
4. **要不要處理「紅燈被下游卡寫成豁免條款」？** `DEV-EVENT-SCHEMA-GUARD1` 已示範這種繼承。豁免條款本身是誠實的（不讓執行者為別人的紅燈背鍋），但它會讓紅燈**看起來已被處理**。工具能不能區分「有 owner 的豁免」與「無主的豁免」？**若不能，明講守不住。**

## 驗收條件

- [ ] Discovery 四問有書面答案，第 1、4 問明列**涵蓋範圍與不涵蓋範圍**。
- [ ] 決定的機制落地，並以**負向測試**證明有效：構造「main 紅燈且無 owner 卡」的情境，證明它在預定關卡被擋下或被強制標示（不是只看正常情況通過）。
- [ ] 同時證明**不誤傷**：上節四條有效路徑各構造一個案例，證明它們仍可通過（特別是「收進自己驗收條件」與「正確地丟棄」兩種不開卡的路徑）。
- [ ] 若動 `workflow_ledger.py` 或事件 schema：完整 `events.jsonl` replay 通過，baseline 前事件數與現況一致（附指令輸出，不接受人工聲明）。
- [ ] 規則寫進 `docs/CONTROL_PLANE_CONTRACT.md`，並以本次 18h46m 窗期為範例說明。
- [ ] `uv run ruff check` ＋ `uv run pytest` 全綠。

## 驗證

- [ ] 查核者以**自己構造的情境**獨立驗證守衛會擋（不沿用執行者的測試案例）。
- [ ] 查核者確認四條有效路徑的不誤傷證據可重現，附指令。
- [ ] 查核者確認新機制**不會在紅燈期間把無關卡片一併鎖死**——若會，須為刻意設計並在契約寫明理由。
- [ ] 查核通過前不得 merge main。

## 邊界

- 只動 control-plane 契約與工具，不動任何交付程式碼、不動既有卡片內容。
- 預估 M（Discovery 與取捨是主體，實作本身不大）。
- 與 `DEV-REVIEW-PREFLIGHT-SELFCHECK1` 相鄰但不重疊：該卡擋的是「交接前提不成立」（卡檔未上 main、lease 未建），本卡擋的是「main 已紅且無人認領」。若兩卡同時在跑且都要動 `review_prompt.py`，該卡先、本卡 rebase。

## Log

- 2026-08-02T12:41:27+08:00 register by Claude Opus 5@Claude Code（依 ruan6047 授權開卡）；iteration 0。來源：`UX-LIVE-TRACKMAN1` 的 `spec 基線` 漏填造成 main 紅燈 18h46m，期間 5 筆 lifecycle event 記錄為「非本卡引入」、1 張新卡寫成豁免條款、24 個 commit 含兩次 merge 與一次生產部署照常落地，最終靠需求方手動指派才修。**開卡動機不是「有人沒修」，而是「發現者不是責任人、責任人不在場時，紅燈沒有去向」**——四條既有的有效路徑都保留，缺的是「什麼都不選」要有成本。
