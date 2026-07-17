# OPS-REFRESH1 白天自動刷新與失敗快篩〔T4；🔴維運／資料正確性〕

- 需求：ruan6047　規劃：GPT-5@Codex＋Fable-5　分支：`ai/<執行者>/OPS-REFRESH1`
- 執行：待指派　查核：待指派（跨模型家族或人工，且 ≠ 執行）
- Initiative：INIT-PRODUCT-UX　spec 基線：PRODUCT_UX_BLUEPRINT v0.2
- DB：`db_scope: write`；local `cpbl`，production 同步另取 lock／備份　部署：是　環境：local＋production　PR：—　Merge SHA：—
- 範圍：[`PRODUCT_UX_BLUEPRINT.md`](../PRODUCT_UX_BLUEPRINT.md) §8.1、§9 Phase 0；[`AI_RUNBOOK.md`](../AI_RUNBOOK.md) §3
- Discovery：launchd 已停用且 production cron 不可靠　Design：Design Gate N/A；屬維運可靠性，不改使用者流程

## 目標與驗收

- [ ] 恢復 10:10 白天 launchd 排程並完成一次可重現測跑；手動 `scrape-daily.sh` 保持安全 fallback，禁止改成 VPS 爬蟲。
- [ ] `last-status.json`、refresh log 與 DB `refresh_log` 能區分排程未觸發、爬取失敗與同步失敗，並提供 fail-fast 檢查方式。
- [ ] 生產同步遵守備份、cpbl schema scope 與 API freshness 驗證；失敗不連續冷啟動重跑，Runbook 與實際操作一致。

## 驗證與依賴

- 驗證：launchctl 狀態、成功與故障注入各一次、local／production freshness 對帳；T4 獨立實測查核。
- 依賴：無；操作時獨占 crawler、local DB 與 production `cpbl` 資源。
- 預估範圍：M；任何 production 寫入仍需 Coordinator 明確授權與備份。

## 結案待辦（2026-07-17 記）

- 結案清理時一併回收 worktree `.claude/worktrees/ux-nav-ia1-review-43d6af`：它目前掛著本卡的 T4 稽核分支 `claude/ops-refresh1-t4-audit-31c612`，UX-NAV-IA1 於 07-17 release 時因此暫留（見 UX-NAV-IA1-RELEASE-008 evidence）。回收前照例確認無未提交變更。
