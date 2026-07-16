# ML-SIM1 簡易勝負預測＋單一打席情境模擬〔🔴統計／ML〕

- 需求：ruan6047　規劃／執行：GPT-5@Codex　分支：`ai/gpt-5-codex/ML-SIM1`（已合併、已清理）
- 查核：Fable-5@Claude Code（跨模型家族；首輪退回、同分支修正後複查 PASS）
- worktree：已清理　Merge SHA：`a28170b`
- DB：`db_scope: read`；若新增特徵表／materialization，另列 `schema` 或 `data-migration` 卡
- 部署：是　環境：production　驗證 source SHA：`4f18cf8`
- 範圍：固定語意特徵群的賽前預測與單一打席互斥結果模擬；回測至少報 Accuracy、Brier、LogLoss、校準及主場／既有模型 baseline，未勝 baseline 不上線。

## Log

- 07-14 取代 UX-10O；完整全場模擬拆至 ML-SIM2。
- 07-15 WF-12 對帳：Ledger 仍 Backlog，但存在 worktree；須先確認 lease，不能直接視為已派工。
- 07-16 Fable 首輪查核退回 PA 換人列污染與 coverage 閘門缺陷；修正後複查 PASS，163 tests 與時間走查／真實 DB 對帳通過，七項 findings 全數關閉。
- 07-16 merge `a28170b`；正式站 `/api/v1/outcome/pregame/backtest` 已回傳 `available=true`、`gate.deployable=true`，且 production submodule 已推進至包含本卡的 `4f18cf8`。補對帳後轉 🏁完成並封存。
