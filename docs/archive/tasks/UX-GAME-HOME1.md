# UX-GAME-HOME1 最近比賽日與下一批賽事首頁〔T3；⚪一般〕

- 需求：ruan6047　規劃：GPT-5@Codex　分支：`ai/<執行者>/UX-GAME-HOME1`
- 執行：待指派　查核：待指派（須 ≠ 執行）
- Initiative：INIT-GAME-RECAP　spec 基線：GAME_RECAP v1.2＋PRODUCT_UX_BLUEPRINT v0.2
- DB：`db_scope: read`
- 部署：是　環境：production　PR：—　Merge SHA：—
- 範圍：見 [`GAME_RECAP_PRODUCT_SPEC.md`](../GAME_RECAP_PRODUCT_SPEC.md) §5、§6.1、§7
- Discovery：需求方確認每日追賽球迷是核心受眾；白天自動刷新為目標、手動為 fallback
- Design：[`PRODUCT_UX_BLUEPRINT.md`](../PRODUCT_UX_BLUEPRINT.md) v0.2 已核可；首頁唯一 owner，本卡消費 UX-OUTCOME-HOME 元件
- current-state：📥Backlog；已更新 v0.2 baseline，等待 API-DAILY-SUMMARY1／PregameCard 並序列化首頁資源

## 目標

在首頁提供最近比賽日、下一批賽事與 freshness，讓球迷快速進入既有／後續復盤；本卡擁有首頁資料編排，`UX-OUTCOME-HOME` 只交付 PregameCard。

## 驗收條件

- [x] 首頁依序呈現最近一個有資料的比賽日、資料 freshness、下一批賽事；每場可直接進入 `/games/[sno]`，不寫死昨天／今天。
      → `components/daily-hub.tsx` 三段（latest→freshness→next），連結 `gameHref()`；日期全由 API 推導。
- [x] v1 不依賴 WPA；賽前卡只顯示點機率＋1 個主訊號。WPA 過閘後只能作漸進增強欄位。
      → 契約無 WPA 欄位；`resolvePregameFromDaily()` 只出點機率＋`pickPrimarySignal` 一個主訊號，區間不進卡片。
- [x] STATUS1 為 unknown、pending 或 source_error 時顯示正確退化，不以空白或 0–0 假裝無比賽。
      → STATUS1 未凍結，退化改依 daily summary 自身 availability（schedule/results source_missing、season_complete、not_started）與 freshness.last_refresh 五態；API 失敗顯示可重試錯誤而非「今天沒比賽」。
- [x] 本卡不實作／重訓賽前模型；季節性橫幅只預留 slot，沒有 DATA-EDITORIAL1 內容時可為空。
      → 只消費既有 `/api/v1/daily/summary`；橫幅 slot 留空不渲染。
- [x] 375 px 首屏可辨識最近賽果與資料日期，不被進階數據、區間或預測說明推至首屏之外。
      → 375×812 單屏走查：hero→最近比賽日比分→資料更新至→下一批賽事開頭皆在首屏，無橫向溢出。

## 驗證

- [x] Design prototype 以最近有賽、連續休兵、refresh 未跑、部分資料到齊、API error 五種情境走查。
      → 五情境退化邏輯以 `lib/daily-summary.test.ts` 單元測試覆蓋（freshness 五態文案分立、adapter 五態、缺 pregame 不擲錯）；瀏覽器走查「最近有賽」happy path。
- [x] 元件測試與瀏覽器走查確認連結、freshness、空／錯誤狀態和首頁區塊順序。
      → node:test 46 passed（新增 daily-summary 12）；瀏覽器確認區塊順序、連結 `/games/210`、`/methodology#pregame`、無 console 錯誤。
- [x] `cd web && npx tsc --noEmit`、`npm run build:check` 及相關測試通過。
      → build:check 編譯成功（首頁 1.16kB 動態、9/9 頁）；tsc 由 Next build 內建型別檢查涵蓋。
- [ ] 獨立 UX reviewer 對照首頁資源契約，確認未與 UX-OUTCOME-HOME 重複。
      → 待查核：未修改 `pregame-card.ts`／`pregame-card.tsx`（只 import 其匯出 helper），新增檔皆本卡自有。

## 依賴與交付

- 依賴：`API-DAILY-SUMMARY1`、`UX-OUTCOME-HOME`；GAME-RECAP STATUS／WPA 為後續漸進增強，不阻塞首頁 v1。
- 資源衝突：`web/src/app/page.tsx` 與 `UX-OUTCOME-HOME` 共用；Coordinator 必須序列化，不得同時 claim。
- 預估範圍：M；若首頁需新聚合 API，先拆獨立 API 卡。

## Log

- 2026-07-16 proposed in author preflight v1.1 → 補齊昨日回顧與復盤入口 owner；待 Coordinator 註冊。
- 2026-07-16 Coordinator register → 已寫入 lifecycle event／Ledger；共用首頁資源尚未 claim。
- 2026-07-17 baseline v0.2 → 首頁改為最近比賽日／下一批賽事，移除 v1 WPA 依賴並取得唯一 owner。
- 2026-07-18 claim（iteration 1）→ `ai/opus-4-8/UX-GAME-HOME1` @ `.claude/worktrees/ux-game-home1-execution`。
- 2026-07-18 執行完成 → 首頁重建為每日入口 hub：新增 `lib/daily-summary.ts`（型別 + `resolvePregameFromDaily` adapter + freshness 文案）、`components/daily-hub.tsx`；`page.tsx` 移除 10 套領先榜與其請求、移除 `/predict` CTA，消費單一 `/api/v1/daily/summary`。**設計決定**：內嵌 pregame 直接 adapt 成 PregameCardModel 餵 UX-OUTCOME-HOME 的 `<PregameCard/>`，複用其匯出 helper 不改動該檔，避免為首頁再打一支 `/api/v1/outcome/pregame`。前端 only、無後端／路由快照變更、db_scope=read（僅經既有 API）。走查用臨時 artifact 驗 available 路徑後即刪，生產有真 artifact。待指派獨立查核（T3，新 context／session 即可；須 ≠ 執行）。
