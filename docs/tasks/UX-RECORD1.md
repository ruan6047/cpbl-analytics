# UX-RECORD1 `/records` 歷史重要性導向重製〔⚪一般〕

- 需求：ruan6047　規劃：Opus-4.8@ClaudeCode　分支：`ai/opus-4.8/UX-RECORD1`（已合併、已刪除）
- 執行：Opus-4.8@ClaudeCode　查核：通過（07-16，ruan6047 轉述獨立查核報告）
- worktree：已清（`../cpbl-analytics-record` 殘留目錄非 worktree，可手動刪除）
- DB：`db_scope: read`
- 部署：是　環境：production　PR：—　Merge SHA：`3b548dc`
- 範圍：重排 `/records` 為冠軍王朝、第二段生涯排行、逐年冠亞軍與球員冠軍榜；coverage 不完整時 fail closed，不呈現累計王朝結論。

## Log

- 07-15 執行完成：`b593181`；`npm run build:check`、`tsc --noEmit` 與深淺色截圖驗證通過。
- 07-15 WF-12 遷移：保留待查核狀態與既有 worktree，部署狀態設為未部署。
- 07-16 查核通過（ruff 綠、pytest 122 passed、build:check／tsc 綠）：DB 重算潘威倫生涯 2125⅓ 局（6376 outs，糾正 naive 2120.9）；例行賽紀錄口徑確認（單季、和局中斷、當年隊碼：統一 2006 連勝 17、兄弟象 2006 連敗 13、興農牛 2003 連續完封 4）；championship_managers 姓名對 players 無多重 ID、洪一中 10 冠（3 球員＋7 教練）；era 名稱正確（1997／2006 兄弟象、2016 中信兄弟）；coverage 突變測試 complete=false 且排行 fail-closed（測後已還原 DB）；真實瀏覽器實跑無 console error。
- 07-16 收尾對帳：實作 `b593181` 實際上已於查核前經 `3b548dc` 合併 main（流程上違反「查核先於合併」，記錄留痕；本次查核為事後補查並通過）。分支已刪，僅待部署。
