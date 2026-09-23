# CPBL 專案注意事項

本檔只列 CPBL 專有的穩定決策邊界；操作細節以 `docs/AI_RUNBOOK.md`、`docs/DATABASE_CONTRACT.md` 為準，模型分工見 `.wf/model-policy.md`。

## 任務入口

- 新卡開在 GitHub Issues＋user Project #10（`.wf/config.json`）。
- Project #4 舊卡凍結、待逐張轉換；⛔ 不用 Project #4 或 `wfcli` 開新卡。`.ai-workflow` submodule 本工作包暫不移除，待 #193 後續切換。
- `docs/TASKS.md` 已封存唯讀，⛔ 不當活卡狀態讀寫。

## 工作樹與共用資源

- 主 checkout `~/Dev/cpbl-analytics` 必須停在 `main`（本機排程直接從它執行）；分支工作一律開獨立 worktree。既有 worktree 可能屬於別人，⛔ 不清除、不重設、不覆蓋其未提交變更。
- 本機 DB、服務埠、排程等屬共用資源。`Resource` 欄只記占用狀態，不是鎖；共用資源的占用或 owner 不明時，先請 PM 協調。

## DB 寫入與 migration

- `docs/DATABASE_CONTRACT.md` 的技術安全邊界仍需遵循；其中舊 T 級、`wfcli`、claim event 流程不適用新卡，#193 後續會修訂混合段落。
- migration 只新增、不改既有檔，且須冪等；破壞性 DDL 或大量資料轉換須獨立卡與需求方 sign-off。
- ⛔ 不臨時手改 production DB；production 結構或資料操作前須先有已驗證備份。

## 部署與資料刷新

- 產品變更、部署、資料刷新分開交付與驗證；產品成果通過不自動授權部署或資料刷新；這兩個動作須依各自授權與結果分別驗證。
- 正式部署需需求方授權；卡面未明列的 production 資料寫入不做。
- 官網爬蟲只能在本機跑；部署路徑、同步、冷卻與止損程序見 Runbook。
