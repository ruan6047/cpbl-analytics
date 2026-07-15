# ML-SIM1 簡易勝負預測＋單一打席情境模擬〔🔴統計／ML〕

- 需求：ruan6047　規劃：Fable-5@ClaudeCode（`PROPOSAL_EVALUATION.md`）　分支：—
- 執行：待指派　查核：待指派（跨家族或人工）
- worktree：待 Coordinator 對帳現存 `../cpbl-analytics-ML-SIM1` 後決定
- DB：`db_scope: read`；若新增特徵表／materialization，另列 `schema` 或 `data-migration` 卡
- 部署：否　環境：—　PR：—　Merge SHA：—
- 範圍：固定語意特徵群的賽前預測與單一打席互斥結果模擬；回測至少報 Accuracy、Brier、LogLoss、校準及主場／既有模型 baseline，未勝 baseline 不上線。

## Log

- 07-14 取代 UX-10O；完整全場模擬拆至 ML-SIM2。
- 07-15 WF-12 對帳：Ledger 仍 Backlog，但存在 worktree；須先確認 lease，不能直接視為已派工。
