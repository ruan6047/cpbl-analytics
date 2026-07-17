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

## Log

- 2026-07-17 執行中：現況重現「本機 scrape 成功、production migration 失敗，但
  `last-status.json` 仍 `ok=true`／process exit 0」。先紅測精確重現 sync exit 17 被吞掉，
  修正後以 fake boundary 驗證 success、scrape failure、sync failure、DB missing 四條流程。
- 新狀態契約：`running|succeeded|failed`、`trigger=manual|launchd`、
  `failed_phase=scrape|sync`；`last-launchd-status.json` 不被手動 fallback 覆蓋，checker
  exit 2–6 可區分未觸發、兩階段失敗、無效狀態與執行中。
- production sync 改為每次 migration/upsert 前先 dump `cpbl` schema 至原子 `.partial`
  檔、`gzip -t` 通過才晉升為備份；同步完成後寫 `prod-sync` marker，並以 `/api/info`
  的 15 分鐘 freshness gate 作為成功條件。
- 自測：聚焦 10 passed；全套 `255 passed, 10 skipped`；ruff、`bash -n`、plist lint、
  Ledger check 全通過。另以 `/usr/bin/python3` 發現並修正 launchd Python 3.9 相容性。
- 待獨立 T4 查核與 main merge 後執行：正式 bootstrap 10:10 launchd、一次 launchctl
  測跑、production 備份／同步與 local／production freshness 對帳。未在 source branch
  提前部署。
