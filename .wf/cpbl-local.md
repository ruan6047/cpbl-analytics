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

專案方向沿 `docs/ROADMAP.md` 有效 §0 四目標與原排序、§1 成果定義／投資取捨及其中原來源（需求方 2026-08-13／08-14、[#130 共同設計附錄](https://github.com/ruan6047/cpbl-analytics/issues/130#issuecomment-5284078990)），並沿各卡後續有效裁定承接；其中候選成果群只是內容示例，不是投入、排序或驗收。2026-10-24／25 本次對話確認的產品／架構目標及未落地界線見 ROADMAP §1「本輪確認的產品與架構目標」，文檔採納待本固定版本審核，未冒稱已有本次 GitHub 裁定。產品設計見 `docs/PRODUCT_UX_BLUEPRINT.md` §1、§2 與本次適用頁面段落，定案不代表已交付；未投入方向見 `docs/REQUIREMENT_IDEAS.md`。任務契約、狀態及最新裁定留在原 GitHub 正式來源；ROADMAP 的 Project #4 流程／排程與 PRODUCT_UX 的舊註冊／優先安排只作歷史，所有卡（含原舊卡）流程均依已安裝 `wfx` 的 vNext 規則。以上是方向短定位，不是「專案規範」宣告；只讀本次適用片段，不整本注入、不自動改鎖定卡。

架構參考沿用既有原本體：`AGENTS.md`「核心定位與邊界」「專案結構」「賽果預測 — 現役模型與舊互動探索器」及「子專案契約」定位元件、現役／保留模型與主站介面；`docs/AI_RUNBOOK.md` §3「資料流與本機爬 → 同步生產」的架構參考段定位已核版本的執行位置／資料流、必要依賴、目標責任與保存缺口，§7.3「部署」保留操作交界；DB 技術與寫入責任依本檔已引用的 `docs/DATABASE_CONTRACT.md` §1，不宣稱其已有新的發布契約。這是架構短定位，不新增專案規範、不重建本體或改變藍圖／各卡裁定；只查本次相關段落及有效來源，不以歷史描述證明現況。Runbook §1 的舊即時訓練描述、§7.1 舊控制平面與過時命令不因此成為現行指示；遇原文矛盾先停受影響判斷並回報，不自行選邊。

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

- 承接相關資料產品行為的卡，需求與規劃須講清楚使用者要看的內容從哪個正式資料來源來、經哪條更新鏈到哪個頁面入口，以及多久內要反映新資料，並寫進本卡驗收。
- 可以分階段交付；本卡核定成果或仍承接的跨卡組合驗收未達時，本卡維持未完成，列出剩餘前提（資料接入、設定啟用、部署、刷新等）與各自需要的授權。只有上位目標尚未全達成、而本卡核定範圍與證據均已完成時，本卡可依原程序結案並如實列有限貢獻；純文件、研究或支援卡不自動承接全站產品驗收。這不是本卡既有驗收的豁免，已接受的證據亦不因改引用而重跑。
- 本卡承接正式站產品成果時，CI 通過、合併、部署成功或 fixture 測試都不能替代本卡核定的正式站證據：須在真實正式資料下，以一般點擊進入、重新載入，以及資料更新後仍能正常使用的結果證明。哪些機械／正式站證據適用，仍依本卡核定需求／規劃與有效產品規範，不自動追加至純文件、研究或支援卡。
- 產品、部署、資料、設定分屬不同授權時，須在需求／規劃階段就揭露並排入計畫，不留到最後才發現；只完成其中一段時如實說明剩下哪段，⛔ 不稱整體已修復。

## 專案規範

- AGENTS.md：修改本專案程式、資料呈現或主站介接時，對照「修改程式碼的準則」、「子專案契約」及「給 AI 的工作備忘」中適用的工程與產品準則；流程治理以 wfx 為準，驗收外檢查仍依規劃裁定。
- docs/design/UI_UX_SYSTEM.md：修改 web UI 時，對照 §1、§2、§4、§5、§6、§7、§10 的適用視覺／元件契約與其中明示的提案／歷史限制；不把建議視為已核定實作，遇與其他節或正式來源衝突先停該項回報，不自行擇一。
- docs/design/GAME-PAGE-THREE-STATES.md：修改完賽態記分條時，只以已核可 §1.1.1 對照「總覽終場比分／逐打席局面」及共用元素保留界線；其餘待人工審章節不因此取得核定效力。

## 已有經驗的適用界線

- 隔離來源已正式同步名單角色後，若該任務亦經授權須對齊共享本機資料，核對同份角色版本與角色列（含 changed_at）；共享本機對齊與生產寫入是不同授權，不能由前者或部署成功推得另一者。來源：[#316 結案](https://github.com/ruan6047/cpbl-analytics/issues/316#issuecomment-6230391915)；最後核對 2026-10-18。此處只保存該經驗，不授權查庫或寫資料。
- [#316 已登記裁定](https://github.com/ruan6047/cpbl-analytics/issues/316#issuecomment-6229676780) 要求保留 PR #328 的共用 UI、InfoDot 與動態 notes 再疊角色。這是該交集的歷史依據，不外推為所有未來介面都不可修改；新任務須讀當下有效規範與核定需求。
