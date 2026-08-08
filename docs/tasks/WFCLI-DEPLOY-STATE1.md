# WFCLI-DEPLOY-STATE1 wfcli 補齊部署狀態與 Project Status 的受控轉換　〔T2〕

- 需求：ruan6047　規劃：GPT-5@Codex（建議 L2；既有 CLI／Projects adapter 局部擴充）
- 執行：待指派（建議 L2；既有 CLI 命令、GraphQL adapter 與測試）　查核：待指派（L2；須 ≠ 執行）
- Initiative：—　spec 基線：2026-08-08 task-card audit：#94/#96/#109 部署狀態缺寫入路徑；#103/#106/#107/#110 的 Project Status 與交付狀態脫鉤
- DB：db_scope=none
- 服務的原始目標：讓任務生命週期的交付、部署與看板視覺狀態都能由可稽核的單一工具通道正確維護。
- owner、worktree、iteration、交付／部署狀態、最後交接、資源宣告與 Log
  current-state 見對應 GitHub Issue／Project item（卡ID：WFCLI-DEPLOY-STATE1），不重複於此檔。

## 核心痛點

- **痛點**：部署已合併與已驗證等生命周期無法透過唯一寫入通道轉換，造成卡片必須在不實完成、Todo 視覺狀態與違規手改之間選擇。

## 驗收條件

- [ ] 新增受控命令，能依明確合法轉換更新部署狀態、owner、最後交接與 Issue timeline 留痕；非法跳轉 fail closed。
- [ ] Project 內建 Status 僅可由 wfcli 對應更新；禁止直接改 Project 欄位定義，所有 item 值寫入只走 updateProjectV2ItemFieldValue。
- [ ] 支援將已開卡的 #94/#96/#109 等已合併或待部署卡轉成正確狀態，並以 dry-run 與真實 Project 最小 canary 驗證。
- [ ] 補齊單元與 mocked GraphQL 回歸：合法與非法轉換、Issue log、既有 handoff release gate，以及不觸及 updateProjectV2Field。

## 驗證

- [ ] cd .ai-workflow/cli && uv run pytest
- [ ] 以 Project #4 的測試卡或需求方指定可逆 canary 實測；輸出 before/after 與 Issue timeline 證據。
