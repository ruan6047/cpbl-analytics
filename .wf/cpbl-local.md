# CPBL 專案注意事項

本檔只列 CPBL 專有、每張卡都適用的決策邊界。操作事實見 `docs/AI_RUNBOOK.md`、`docs/DATABASE_CONTRACT.md`，模型分工見 `.wf/model-policy.md`。`CLAUDE.md`／`AGENTS.md` 仍混有舊治理（#193 待修）：其中的舊流程不適用新卡，只取操作安全部分。

## 專案速覽

- **產品**：中華職棒 [CPBL] 資料管線＋本季／進階數據呈現＋單場賽果預測，公開站 https://cpbl.ruan-ruan.com ；是主站 PersonalWebsite 的子專案（git submodule），主站經 `/api/info` 輪詢它。
- **資料來源**：歷史逐年彙總來自 `ldkrsi/cpbl-opendata`；逐場／逐打席由官網 `https://www.cpbl.com.tw` 爬蟲補足（有反爬，須 Playwright、只能本機跑）；官方進階數據與逐球 TrackMan 來自官方進階站 `https://stats.cpbl.com.tw`（httpx 直連）。站台結構事實見 `docs/CPBL_SITE_MAP.md`。
- **儲存與服務**：PostgreSQL 17 schema `cpbl`（生產與主站共用同一顆 DB）；後端 FastAPI（Python 3.12／uv／psycopg3 raw SQL，無 ORM）；前端 `web/` 為獨立 Next.js 15 App Router。
- **部署入口**：本 repo CI 只跑 lint／測試、不部署；部署＝在主站 bump submodule 指標後由主站 CI push-to-deploy（Runbook §7.3）。

## 任務框架

- CPBL 新任務採用 ai-workflow vNext 已安裝 `wfx` 套件隨附的規則（套件內 `wfx/rules/`）；`wfx` 只提供 `brief`／`facts`／`write`，開卡／關卡由 PM 以 `gh` 執行。`.wf/` 是本專案補充層，只補 CPBL 專有邊界，不取代框架核心規則。
- 舊 `.ai-workflow` submodule 的 canonical 規則（T 級、狀態值、claim／lease、Ledger、`wfcli`）只屬 Project #4 舊卡，⛔ 不帶入新卡。

## 任務入口

- 新卡一律開在 GitHub Issues＋user Project #10「cpbl-analytics vNext 任務看板」（`.wf/config.json`）。
- Project #4 舊卡凍結，停止舊流程派工與 `wfcli` 寫入，待逐張轉換、關閉；⛔ 不用 Project #4 或 `wfcli` 開新卡，新卡不沿用舊流程（分級、狀態值、claim／lease、Ledger）。`.ai-workflow` submodule 本注意事項工作包暫不移除，後續依 #193 切換。
- `docs/TASKS.md` 已封存唯讀，⛔ 不當活卡狀態讀寫。

## 工作樹與共用資源

- 主 checkout `~/Dev/cpbl-analytics` 必須停在 `main`：本機排程直接從它執行，它停在哪個分支排程就跑哪個分支的碼。分支工作一律開獨立 worktree。
- 本機 DB、服務、排程與既有 worktree 都是多個 session 共用；`Resource` 欄只記當前占用狀態，不是鎖；占用或 owner 不明時先請 PM 協調，⛔ 不清除、不重設、不覆蓋別人的未提交變更。舊卡的本機 lease 鎖不沿用新卡，但改動共享資源仍依 vNext 的資源租用（`rules/core/github.md` §6）。

## DB 寫入與 migration

- `docs/DATABASE_CONTRACT.md` 的技術邊界仍有效；其中 `docs/tasks/<CARD_ID>.md` 宣告、Coordinator claim、lease 等舊卡機制不適用新卡，該檔尚未依新框架修訂。
- migration 只新增、不改既有檔，且須冪等；破壞性 DDL 或大量資料轉換須獨立卡，並於既有階段確認（`rules/core/flow.md`）取得需求方授權，不另設關卡。
- production migration 只由 main 部署鏈在 `prod_cpbl_api` 內執行；結構或資料操作前須先有已驗證備份，⛔ 不臨時手改 production DB。

## 部署與資料刷新

- 產品變更、部署、資料刷新是三件事，分開交付、分別授權與驗證；產品成果通過不等於授權部署或刷新資料。
- 部署不在本 repo 發生：本 repo CI 不部署，須在主站 bump submodule（Runbook §7.3），且需需求方授權。
- 卡面未明列的 production 資料寫入不做。官網爬蟲只能在本機跑；同步、冷卻與止損程序見 Runbook §3。
