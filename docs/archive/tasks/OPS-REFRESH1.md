# OPS-REFRESH1 白天自動刷新與失敗快篩〔T4；🔴維運／資料正確性〕

- 需求：ruan6047　規劃：GPT-5@Codex＋Fable-5　分支：`ai/<執行者>/OPS-REFRESH1`
- 執行：GPT-5@Codex　查核：Claude Sonnet 5@Claude Code（跨模型家族）
- Initiative：INIT-PRODUCT-UX　spec 基線：PRODUCT_UX_BLUEPRINT v0.2
- DB：`db_scope: write`；local `cpbl`，production 同步另取 lock／備份　部署：是　環境：local＋production　PR：—　Merge SHA：`1e4572aa88a0f77ebddd40dd8c6b0459b9bb2375`
- 範圍：[`PRODUCT_UX_BLUEPRINT.md`](../PRODUCT_UX_BLUEPRINT.md) §8.1、§9 Phase 0；[`AI_RUNBOOK.md`](../AI_RUNBOOK.md) §3
- Discovery：launchd 已停用且 production cron 不可靠　Design：Design Gate N/A；屬維運可靠性，不改使用者流程

## 目標與驗收

- [x] 恢復 10:10 白天 launchd 排程並完成一次可重現測跑；手動 `scrape-daily.sh` 保持安全 fallback，禁止改成 VPS 爬蟲。
- [x] `last-status.json`、refresh log 與 DB `refresh_log` 能區分排程未觸發、爬取失敗與同步失敗，並提供 fail-fast 檢查方式。
- [x] 生產同步遵守備份、cpbl schema scope 與 API freshness 驗證；失敗不連續冷啟動重跑，Runbook 與實際操作一致。

## 驗證與依賴

- 驗證：launchctl 狀態、成功與故障注入各一次、local／production freshness 對帳；T4 獨立實測查核。
- 依賴：無；操作時獨占 crawler、local DB 與 production `cpbl` 資源。
- 預估範圍：M；任何 production 寫入仍需 Coordinator 明確授權與備份。

## 結案待辦（2026-07-17 記）

- 結案清理時一併回收 worktree `.claude/worktrees/ux-nav-ia1-review-43d6af`：它目前掛著本卡的 T4 稽核分支 `claude/ops-refresh1-t4-audit-31c612`，UX-NAV-IA1 於 07-17 release 時因此暫留（見 UX-NAV-IA1-RELEASE-008 evidence）。回收前照例確認無未提交變更。

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
- 初次自測：聚焦 10 passed；全套 `255 passed, 10 skipped`；ruff、`bash -n`、plist
  lint、Ledger check 全通過。初次只驗證 helper 可由 `/usr/bin/python3` 載入，未覆蓋
  `check --scheduled` 的時間解析，因此不足以證明完整 Python 3.9 相容性。
- 待獨立 T4 查核與 main merge 後執行：正式 bootstrap 10:10 launchd、一次 launchctl
  測跑、production 備份／同步與 local／production freshness 對帳。未在 source branch
  提前部署。
- 2026-07-17 Claude Opus 4.8 T4 查核退回（iteration 1）：P1 指出 Python 3.9 無法解析
  `date +%z` 產生的 `+0800`，合法 scheduled status 被誤報 `INVALID_STATUS`；另有 scheduled
  狀態／deadline 零覆蓋及同步步驟 `1/3` 文案兩項 P2。原執行者於原分支修正中。
- iteration 1 修正：checker 新增 basic offset（`+0800`）正規化後再交給 Python 3.9
  `fromisoformat()`，同時保留 `+08:00` 支援；新增 scheduled OK／RUNNING／scrape failure／
  sync failure／expired／custom deadline 六條決定性測試，且 subprocess 明確使用 macOS
  `/usr/bin/python3`。同步進度統一為 `1/4`–`4/4`。聚焦 `17 passed`、全套
  `262 passed, 10 skipped`；ruff、shell syntax、plist lint、Ledger check 均通過。
- 2026-07-18 Claude Opus 4.8 T4 查核退回（iteration 2）：P0 指出 stdin 餵入 production
  `psql` 未啟用 `ON_ERROR_STOP`，SQL 錯誤可能 rollback 卻以 exit 0 寫入成功 marker；另有
  running 無時效上限、手動與 launchd 無互斥、備份位於 `/tmp` 且不輪替三項 P2。
- iteration 2 修正：所有逐表 sync 的 `psql` 加 `-v ON_ERROR_STOP=1`，新增 SQL error
  全鏈路回歸測試，確認整體保留非零碼且 `failed_phase=sync`；marker 前先對帳真實
  `last_game_date`／`season_games_completed`，不吻合不得宣告成功。running 超過 180 分鐘
  回 `STALE_RUNNING`／exit 7；每日腳本以原子 mkdir lock 阻止 crawler 併發（exit 75）；
  備份移至使用者持久目錄並預設保留最近 7 份。聚焦 `26 passed`；完整 suite 以本
  worktree `src` 隔離共用 editable venv 後為 `271 passed, 10 skipped`；ruff、shell syntax、
  plist lint、macOS `/usr/bin/python3` helper、Ledger 與 diff check 均通過。
- 2026-07-18 release：Claude Sonnet 5 固定 source SHA `38040bb` 跨家族 T4 複審
  APPROVE（P0–P2=0）；non-fast-forward merge `1e4572a` 進 main，並以 `2e3053c` 對齊
  並行 lifecycle 更新。cpbl-analytics CI `29640869680`、主站 CI `29641149799`、Deploy
  `29641212903` 全綠。真實 Docker／SSH manual sync 先產生並驗證持久備份，再完成全部
  migration／逐表 upsert／outcome 回測／資料對帳與 freshness gate。launchd 正式 bootstrap
  每日 10:10，單次 kickstart `runs=1`、exit 0；`trigger=launchd`、scrape／sync 皆成功，
  production 最終 `last_game_date=2026-09-15`、`season_games_completed=353`、freshness 小於
  15 分鐘。任務卡完成並移入 archive。
