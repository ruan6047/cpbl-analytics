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

- [ ] 首頁依序呈現最近一個有資料的比賽日、資料 freshness、下一批賽事；每場可直接進入 `/games/[sno]`，不寫死昨天／今天。
- [ ] v1 不依賴 WPA；賽前卡只顯示點機率＋1 個主訊號。WPA 過閘後只能作漸進增強欄位。
- [ ] STATUS1 為 unknown、pending 或 source_error 時顯示正確退化，不以空白或 0–0 假裝無比賽。
- [ ] 本卡不實作／重訓賽前模型；季節性橫幅只預留 slot，沒有 DATA-EDITORIAL1 內容時可為空。
- [ ] 375 px 首屏可辨識最近賽果與資料日期，不被進階數據、區間或預測說明推至首屏之外。

## 驗證

- [ ] Design prototype 以最近有賽、連續休兵、refresh 未跑、部分資料到齊、API error 五種情境走查。
- [ ] 元件測試與瀏覽器走查確認連結、freshness、空／錯誤狀態和首頁區塊順序。
- [ ] `cd web && npx tsc --noEmit`、`npm run build:check` 及相關測試通過。
- [ ] 獨立 UX reviewer 對照首頁資源契約，確認未與 UX-OUTCOME-HOME 重複。

## 依賴與交付

- 依賴：`API-DAILY-SUMMARY1`、`UX-OUTCOME-HOME`；GAME-RECAP STATUS／WPA 為後續漸進增強，不阻塞首頁 v1。
- 資源衝突：`web/src/app/page.tsx` 與 `UX-OUTCOME-HOME` 共用；Coordinator 必須序列化，不得同時 claim。
- 預估範圍：M；若首頁需新聚合 API，先拆獨立 API 卡。

## Log

- 2026-07-16 proposed in author preflight v1.1 → 補齊昨日回顧與復盤入口 owner；待 Coordinator 註冊。
- 2026-07-16 Coordinator register → 已寫入 lifecycle event／Ledger；共用首頁資源尚未 claim。
- 2026-07-17 baseline v0.2 → 首頁改為最近比賽日／下一批賽事，移除 v1 WPA 依賴並取得唯一 owner。
