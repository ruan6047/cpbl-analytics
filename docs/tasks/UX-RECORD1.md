# UX-RECORD1 `/records` 歷史重要性導向重製〔⚪一般〕

- 需求：ruan6047　規劃：Opus-4.8@ClaudeCode　分支：`ai/opus-4.8/UX-RECORD1`
- 執行：Opus-4.8@ClaudeCode　查核：待指派（須 ≠ 執行）
- worktree：`../cpbl-analytics-record`
- DB：`db_scope: read`
- 部署：是　環境：production　PR：—　Merge SHA：—
- 範圍：重排 `/records` 為冠軍王朝、第二段生涯排行、逐年冠亞軍與球員冠軍榜；coverage 不完整時 fail closed，不呈現累計王朝結論。

## Log

- 07-15 執行完成：`b593181`；`npm run build:check`、`tsc --noEmit` 與深淺色截圖驗證通過。
- 07-15 WF-12 遷移：保留待查核狀態與既有 worktree，部署狀態設為未部署。
