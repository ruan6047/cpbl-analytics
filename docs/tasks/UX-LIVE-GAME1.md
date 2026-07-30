# UX-LIVE-GAME1 賽前情報到比賽中狀態板 〔T3；⚪使用者可見功能〕

- 需求：ruan6047　規劃：GPT-5.6@Codex　分支：`ai/<執行者>/UX-LIVE-GAME1`
- 執行：待指派（建議 L2；既有 game board 上的狀態式 React UI 與 polling）　查核：待指派（L2 獨立 UX／browser review；須 ≠ 執行）
- review_independence: [cross_family]
- Initiative：INIT-PRODUCT-UX　spec 基線：v0.2　product spec：`LIVE_GAME_PRODUCT_SPEC v1.1`
- DB：`db_scope: none`
- 部署：是　環境：production　PR：—　Merge SHA：—
- 範圍：見 [`../LIVE_GAME_PRODUCT_SPEC.md`](../LIVE_GAME_PRODUCT_SPEC.md) §3、§5–§7
- Discovery：[`../LIVE_GAME_PRODUCT_SPEC.md`](../LIVE_GAME_PRODUCT_SPEC.md) §1–§2；需求方 2026-07-26 確認賽前一天預告先發、賽前一小時 lineup 與 live 賽況需求
- Design：[`../LIVE_GAME_PRODUCT_SPEC.md`](../LIVE_GAME_PRODUCT_SPEC.md) §6；2026-07-30 需求方核可 live-only v1
- owner、worktree、iteration、最後交接、阻塞與 current-state 見 [`../TASKS.md`](../TASKS.md) Ledger

## 驗收條件

- [ ] `/games` 與 `/games/[sno]` 只依 backend canonical phase 呈現 `scheduled／lineup_announced／live／final／postponed／reserved／unknown`；兩隊 lineup 可各自 partial，來源錯誤／stale 不得偽裝成未公布；v1 不呈現 probable starter。
- [ ] lineup 實際出現後才呈現棒次、守位與球員連結；`live` 在既有 `/games/[sno]` 狀態板與 Recent Plays 原地更新比分、局況、壘況、球數、最近事件及最後更新時間，不新增文字轉播頁；`final` 停止 polling 並保留既有賽後入口。
- [ ] 賽中 TrackMan unavailable 時不顯示空好球帶或「無設備」結論；stale 時保留 last-known-good 並明顯標示更新中斷，恢復後自動回到 live freshness。

## 驗證

- [ ] component／integration tests 使用 backend contract fixtures 覆蓋兩隊不同步公布、9 人不完整、代碼未知、stale、source error、延期／保留、比分 0-0 但已 `START`、final 停止 polling。
- [ ] 真實瀏覽器 network evidence 證明只打本站 API、前景約 10–15 秒 polling、背景分頁暫停或降頻、無整頁 reload／重複 timer／request storm；API stale 時畫面不冒充即時。
- [ ] 375 px 與桌機驗證無水平捲動，打序／守位可辨識；比分與局況變動以 `aria-live=polite` 適量播報、控制具鍵盤焦點與觸控區。
- [ ] `cd web && npm test`、`npx tsc --noEmit`、`npm run build:check` 通過。

## 依賴與範圍

- 依賴：`LIVE-GAME-BACKEND1` additive API contract 與 fixtures 固定後才可 claim。
- v1 僅修改既有 `/games` 與 `/games/[sno]`；首頁 live 模組、通知／推播另開卡。
- 不重做 `UX-GAME-RECAP1`／`UX-GAME-PA1` 的賽後復盤與逐球進階探索器。

## Log

- 2026-07-26T17:29:31+08:00 register by GPT-5.6@Codex（依 ruan6047 指示開前端卡；依賴後端卡）。
- 2026-07-30 Design Gate by ruan6047 → v1 只把 live polling 整合進既有賽事頁狀態板與 Recent Plays；不新增獨立文字轉播頁，預告先發延後。
- 2026-07-30 review independence by ruan6047 → 指定 Claude Fable 5，採跨模型家族 UX／browser 查核。
