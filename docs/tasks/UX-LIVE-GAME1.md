# UX-LIVE-GAME1 賽前情報到比賽中狀態板 〔T3；⚪使用者可見功能〕

- 需求：ruan6047　規劃：GPT-5.6@Codex　分支：`ai/<執行者>/UX-LIVE-GAME1`
- 執行：待指派（建議 L2；既有 game board 上的狀態式 React UI 與 polling）　查核：待指派（L2 獨立 UX／browser review；須 ≠ 執行）
- Initiative：INIT-PRODUCT-UX　spec 基線：v0.2
- DB：`db_scope: none`
- 部署：是　環境：production　PR：—　Merge SHA：—
- 範圍：見 [`../LIVE_GAME_PRODUCT_SPEC.md`](../LIVE_GAME_PRODUCT_SPEC.md) §3、§5–§7
- Discovery：[`../LIVE_GAME_PRODUCT_SPEC.md`](../LIVE_GAME_PRODUCT_SPEC.md) §1–§2；需求方 2026-07-26 確認賽前一天預告先發、賽前一小時 lineup 與 live 賽況需求
- Design：[`../LIVE_GAME_PRODUCT_SPEC.md`](../LIVE_GAME_PRODUCT_SPEC.md) §6；Design Gate 待需求方核可
- owner、worktree、iteration、最後交接、阻塞與 current-state 見 [`../TASKS.md`](../TASKS.md) Ledger

## 驗收條件

- [ ] `/games` 與 `/games/[sno]` 只依 backend canonical phase 呈現 `scheduled／probable_announced／lineup_announced／live／final／postponed／reserved／unknown`；兩隊預告先發與 lineup 可各自 partial，未公布顯示「尚未公布」，來源錯誤／stale 不得偽裝成未公布。
- [ ] 賽前呈現預告先發與觀測時間，lineup 公布後呈現棒次、守位與球員連結；`live` 原地切換比分、局況、壘況、球數、最近事件、最後更新時間，`final` 停止 polling 並保留既有賽後入口。
- [ ] 賽中 TrackMan unavailable 時不顯示空好球帶或「無設備」結論；stale 時保留 last-known-good 並明顯標示更新中斷，恢復後自動回到 live freshness。

## 驗證

- [ ] component／integration tests 使用 backend contract fixtures 覆蓋兩隊不同步公布、9 人不完整、代碼未知、stale、source error、延期／保留、比分 0-0 但已 `START`、final 停止 polling。
- [ ] 真實瀏覽器 network evidence 證明只打本站 API、前景依契約 polling、背景分頁暫停或降頻、無重複 timer／request storm；API stale 時畫面不冒充即時。
- [ ] 375 px 與桌機驗證無水平捲動，打序／守位可辨識；比分與局況變動以 `aria-live=polite` 適量播報、控制具鍵盤焦點與觸控區。
- [ ] `cd web && npm test`、`npx tsc --noEmit`、`npm run build:check` 通過。

## 依賴與範圍

- 依賴：`LIVE-GAME-BACKEND1` additive API contract 與 fixtures 固定後才可 claim。
- v1 僅修改既有 `/games` 與 `/games/[sno]`；首頁 live 模組、通知／推播另開卡。
- 不重做 `UX-GAME-RECAP1`／`UX-GAME-PA1` 的賽後復盤與逐球進階探索器。

## Log

- 2026-07-26T17:29:31+08:00 register by GPT-5.6@Codex（依 ruan6047 指示開前端卡；依賴後端卡）。
