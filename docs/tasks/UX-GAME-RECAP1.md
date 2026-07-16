# UX-GAME-RECAP1 結論先行的單場賽後復盤〔T3；⚪一般〕

- 需求：ruan6047　規劃：GPT-5@Codex　分支：`ai/<執行者>/UX-GAME-RECAP1`
- 執行：待指派　查核：待指派（須 ≠ 執行）
- Initiative：INIT-GAME-RECAP　spec 基線：v1.2
- DB：`db_scope: read`
- 部署：是　環境：production　PR：—　Merge SHA：—
- 範圍：見 [`GAME_RECAP_PRODUCT_SPEC.md`](../GAME_RECAP_PRODUCT_SPEC.md) §4–§7、§9
- Discovery：需求方 2026-07-16 確認使用目標
- Design：spec v1.1 與 Design Brief 待需求方核可；實作前須補 prototype／wireframe 與 Design Gate
- current-state：📥Backlog；已由 Coordinator 註冊，正式實作等待 Design Gate 與 API contract freeze

## 目標

重整現有 `/games/[sno]`，讓每日追賽球迷先理解最終結果、比賽摘要與關鍵轉折，再依需要進入完整逐打席。保留既有 `WinProbChart`、`GameOverview`、`GameBoard` 能力，但移除即時轉播語意與錯誤的完賽狀態表現。

## 驗收條件

- [ ] 完賽頁首在 375 px 與桌機皆先呈現最終比分、官方狀態、Top 3 轉折、資料更新時間與 WP 模型限制；不得顯示成正在進行的 `TOP/BOT`、壘包或球數。
- [ ] WP 曲線、轉折卡與逐打席時間軸以 canonical `pa_id` 連動；點擊或鍵盤選擇後能在 2 次互動內到達打席詳情。
- [ ] 依 STATUS1 正交契約呈現 scheduled/final/延賽／取消、逐打席／逐球／WP availability、unknown 與 source_error；不得由前端自行推導 composite status。
- [ ] 行動版提供不需精準點圖的轉折／打席替代清單；不產生整頁水平捲動。
- [ ] 文字清楚區分「賽後復盤 WP」與「賽前隊伍實力預測」，且 WPA 不被描述為球員能力或責任。

## 驗證

- [ ] 元件測試涵蓋 Design Brief 情境矩陣、STATUS／PA／WP availability 的關鍵組合，以及完賽頁不顯示假現場狀態。
- [ ] 瀏覽器走查：375 px、桌機、鍵盤、`prefers-reduced-motion`、無 WP、無 livelog、進階資料晚到。
- [ ] 使用者任務走查：5 秒辨識結果／最大轉折；2 次互動內進入指定打席。
- [ ] `cd web && npx tsc --noEmit`、`npm run build:check` 及相關測試通過。
- [ ] 獨立 UX reviewer 對照 spec 與 Design Brief 驗收，不由實作者自核。

## 依賴與交付

- 依賴：`GAME-RECAP-PA1`、`GAME-RECAP-WP-API1`、`GAME-RECAP-STATUS1`；可先做 prototype，但正式串接須等 API contract freeze。
- 不得與 `UX-OUTCOME-HOME` 同時改同一首頁資源；本卡只改單場頁。
- 預估範圍：M；如需大幅拆 `page.tsx`，先另開純重構卡。

## Log

- 2026-07-16 proposed by GPT-5@Codex → 待 Coordinator 註冊 lifecycle event。
- 2026-07-16 Coordinator register → 已寫入 lifecycle event／Ledger；可做 prototype，不得提前串接未凍結契約。
