# CPBL 專案注意事項

本檔只列 CPBL 專有、每張卡都適用的決策邊界。操作事實見 `docs/AI_RUNBOOK.md`、`docs/DATABASE_CONTRACT.md`，模型分工見 `.wf/model-policy.md`；`CLAUDE.md`／`AGENTS.md` 的程式與產品準則照常適用。

## 專案速覽

- **產品**：中華職棒 [CPBL] 資料管線＋本季／進階數據呈現＋單場賽果預測，公開站 https://cpbl.ruan-ruan.com ；是主站 PersonalWebsite 的子專案（git submodule），主站經 `/api/info` 輪詢它。
- **資料來源**：歷史逐年彙總來自 `ldkrsi/cpbl-opendata`；逐場／逐打席由官網 `https://www.cpbl.com.tw` 爬蟲補足（有反爬，須 Playwright、只能本機跑）；官方進階數據與逐球 TrackMan 來自官方進階站 `https://stats.cpbl.com.tw`（httpx 直連）。站台結構事實見 `docs/CPBL_SITE_MAP.md`。
- **儲存與服務**：PostgreSQL 17 schema `cpbl`（生產與主站共用同一顆 DB）；後端 FastAPI（Python 3.12／uv／psycopg3 raw SQL，無 ORM）；前端 `web/` 為獨立 Next.js 15 App Router。
- **部署入口**：本 repo CI 只跑 lint／測試、不部署；部署＝在主站 bump submodule 指標後由主站 CI push-to-deploy（Runbook §7.3）。

## 任務框架

- CPBL 新任務採用 ai-workflow vNext 已安裝 `wfx` 套件隨附的規則（套件內 `wfx/rules/`）；`wfx` 只提供 `brief`／`facts`／`write`，開卡／關卡由 PM 以 `gh` 執行。`.wf/` 是本專案補充層，只補 CPBL 專有邊界，不取代框架核心規則。
- 新卡一律開在 GitHub Issues＋user Project #10「cpbl-analytics vNext 任務看板」（`.wf/config.json`）。
- Project #4 已於 ai-workflow#417 結案時關閉；未結案舊卡依 #417 Q6 改照 vNext 繼續（各卡已留通知）。舊流程（T 級、舊狀態值、claim／lease、Ledger、`wfcli`）⛔ 不帶入任何卡；`docs/AI_WORKFLOW.md`、`docs/CONTROL_PLANE_CONTRACT.md`、`docs/TASKS.md` 只作歷史查閱，⛔ 不當活卡狀態讀寫。

## 工作樹與共用資源

- 主 checkout `~/Dev/cpbl-analytics` 必須停在 `main`：本機排程直接從它執行，它停在哪個分支排程就跑哪個分支的碼。分支工作一律開獨立 worktree。
- 本機 DB、服務、排程與既有 worktree 都是多個 session 共用；改動前依 vNext 資源租用（`rules/core/github.md` §6）。`Resource` 欄只記當前占用狀態，不是鎖；占用或 owner 不明時先請 PM 協調，⛔ 不清除、不重設、不覆蓋別人的未提交變更。

## DB 寫入與 migration

- DB 技術邊界以 `docs/DATABASE_CONTRACT.md` 為準。
- 同一環境的 `cpbl` schema 同時只有一個 migration writer；schema migration 與 data migration ⛔ 不並行，互相依賴的 migration 依序合併。
- migration 只新增、不改既有檔，且須冪等；破壞性 DDL 或大量資料轉換須獨立卡，並於既有階段確認（`rules/core/flow.md`）取得需求方授權，不另設關卡。
- production migration 只由 main 部署鏈在 `prod_cpbl_api` 內執行；結構或資料操作前須先有已驗證備份，⛔ 不臨時手改 production DB。

## 部署與資料刷新

- 產品變更、部署、資料刷新是三件事，分開交付、分別授權與驗證；產品成果通過不等於授權部署或刷新資料。
- 部署不在本 repo 發生：本 repo CI 不部署，須在主站 bump submodule（Runbook §7.3），且需需求方授權。
- 卡面未明列的 production 資料寫入不做。官網爬蟲只能在本機跑；同步、冷卻與止損程序見 Runbook §3。

## 產品交付完成判定

- 需求與規劃須講清楚使用者要看的內容從哪個正式資料來源來、經哪條更新鏈到哪個頁面入口，以及多久內要反映新資料，並寫進驗收。
- 可以分階段交付，但總目標未達時卡片維持未完成，並列出剩餘依賴（資料接入、設定啟用、部署、刷新等）與各自需要的授權。
- CI 通過、合併、部署成功或 fixture 測試都不能替代正式站證據：須在真實正式資料下，以一般點擊進入、重新載入，以及資料更新後仍能正常使用的結果證明。
- 產品、部署、資料、設定分屬不同授權時，須在需求／規劃階段就揭露並排入計畫，不留到最後才發現；只完成其中一段時如實說明剩下哪段，⛔ 不稱整體已修復。
