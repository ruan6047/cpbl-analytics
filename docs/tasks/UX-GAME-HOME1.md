# UX-GAME-HOME1 昨日回顧與賽事復盤首頁入口〔T3；⚪一般〕

- 需求：ruan6047　規劃：GPT-5@Codex　分支：`ai/<執行者>/UX-GAME-HOME1`
- 執行：待指派　查核：待指派（須 ≠ 執行）
- Initiative：INIT-GAME-RECAP　spec 基線：v1.2
- DB：`db_scope: read`
- 部署：是　環境：production　PR：—　Merge SHA：—
- 範圍：見 [`GAME_RECAP_PRODUCT_SPEC.md`](../GAME_RECAP_PRODUCT_SPEC.md) §5、§6.1、§7
- Discovery：需求方確認每日追賽球迷是核心受眾，且通常隔日刷新
- Design：依 [`GAME_RECAP_DESIGN_BRIEF.md`](../design/GAME_RECAP_DESIGN_BRIEF.md)；首頁 wireframe 與 UX-OUTCOME-HOME 區塊契約待核可
- current-state：📥Backlog；已由 Coordinator 註冊，等待 STATUS／賽事總覽並與 `UX-OUTCOME-HOME` 序列化

## 目標

在首頁提供昨日戰果與單場復盤入口，讓球迷快速選擇值得深入的比賽；今日賽程與既有 `UX-OUTCOME-HOME` 賽前預測模組保持清楚分工，不把隔日資料包裝成即時戰況。

## 驗收條件

- [ ] 首頁依序呈現昨日戰果／可復盤場次、資料 freshness、今日賽程；每場可直接進入 `/games/[sno]`。
- [ ] 昨日代表性比賽只使用可解釋規則（如最大 abs WPA／逆轉），揭露口徑，不宣稱主觀「最精彩」。
- [ ] STATUS1 為 unknown、pending 或 source_error 時顯示正確退化，不以空白或 0–0 假裝無比賽。
- [ ] 與 `UX-OUTCOME-HOME` 凍結首頁區塊責任：本卡不實作／重訓賽前模型；預測卡不重做昨日回顧。
- [ ] 375 px 首屏可辨識昨日結果與資料日期，不被進階數據或預測說明推至首屏之外。

## 驗證

- [ ] Design prototype 以昨日有賽、休兵日、refresh 未跑、部分資料到齊、API error 五種情境走查。
- [ ] 元件測試與瀏覽器走查確認連結、freshness、空／錯誤狀態和首頁區塊順序。
- [ ] `cd web && npx tsc --noEmit`、`npm run build:check` 及相關測試通過。
- [ ] 獨立 UX reviewer 對照首頁資源契約，確認未與 UX-OUTCOME-HOME 重複。

## 依賴與交付

- 依賴：`GAME-RECAP-STATUS1`、`UX-GAME-RECAP1`。
- 資源衝突：`web/src/app/page.tsx` 與 `UX-OUTCOME-HOME` 共用；Coordinator 必須序列化，不得同時 claim。
- 預估範圍：M；若首頁需新聚合 API，先拆獨立 API 卡。

## Log

- 2026-07-16 proposed in author preflight v1.1 → 補齊昨日回顧與復盤入口 owner；待 Coordinator 註冊。
- 2026-07-16 Coordinator register → 已寫入 lifecycle event／Ledger；共用首頁資源尚未 claim。
