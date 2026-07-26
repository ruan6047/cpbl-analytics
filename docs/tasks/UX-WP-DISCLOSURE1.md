# UX-WP-DISCLOSURE1 賽況頁 WP 曲線誠實註記〔T3〕

- 需求：ruan6047（2026-07-26 會話裁定「獨立開卡」；源自 WP-VAL1 §7 第 5 點產品過渡決策）　規劃：本卡 spec（事實基線＝VAL1/CAL1 研究報告）　分支：依認領時 worktree 慣例
- 執行：待指派　查核：待指派（≠ 執行；文案數字須對 research artifact 逐位核對）
- Initiative：—（獨立 UX 卡；事實依據為 [`GAME-RECAP-WP-VAL1_RESULTS.md`](../research/GAME-RECAP-WP-VAL1_RESULTS.md) 與 [`GAME-RECAP-WP-CAL1_RESULTS.md`](../research/GAME-RECAP-WP-CAL1_RESULTS.md)）
- DB：`db_scope: none`（純前端文案與方法頁）
- 部署：是（文案上線才有意義；`/methodology` 為 ISR 路由，部署驗證照 ISR 慣例等 revalidate 到期重測）　環境：production　PR：—　Merge SHA：—
- current-state：📥Backlog；已註冊，可認領（建議與 UX-LIVE-GAME1 排程協調後再 claim，見邊界）。

## 背景（為什麼）

賽況頁 WP 曲線是「局面勝率」（比分/壘位/出局 + 歷史主場優勢，不含戰力差與先發投手），
辨別力真實（Brier 0.155 vs 主場常數基準 0.247），但時間外驗證（WP-VAL1）證實極端區間有
系統性偏差：落後方被高估、領先方被低估各約 4–6 個百分點——而這兩端正是「翻盤」與
「勝券在握」的敘事區。事後校準嘗試（WP-CAL1）已證 No-Go（修正不具時間平穩性），短期無
修復路徑；治本的戰力感知模型（VAL1 §7 路徑 2）尚未開卡。偏差將長期存在 → 依「誠實第一」
紅線（同賽果預測「永遠回傳全押主場基準」的精神），曲線繼續提供但必須揭露已知限制。

## 目標

1. **賽況頁 WP 曲線旁一行註記**（caption 或 tooltip，桌機/手機皆可見）：
   文案基準（執行者可微調語氣、不得改動事實內容）：
   「局面勝率：僅依比分・壘位・出局數與歷史主場優勢，未含兩隊戰力與先發投手；
   領先／落後方極端區間有已知 ±4–6 個百分點偏差」＋連結 `/methodology` 對應節。
2. **`/methodology` 新增一節**：時間外驗證結論（walk-forward、S 型偏差結構、單季雜訊底線）、
   校準嘗試 No-Go 的一句話摘要、與「為何仍提供曲線」（辨別力 vs 校準的區分）。
   數字一律引自兩份 research 報告，不得腦補或改寫。

## 驗收條件

- [ ] 註記在賽況頁 WP 曲線區塊渲染（桌機＋手機皆驗證截圖）；連結可達 `/methodology` 對應錨點。
- [ ] `/methodology` 新節數字與 `game_recap_wp_val1_metrics.json`／`game_recap_wp_cal1_metrics.json` 逐位一致（查核核對項）。
- [ ] 文案為正式語氣：禁球迷暱稱／禁浮誇包裝；不得暗示「即將修復」（路徑 2 未開卡）。
- [ ] 視覺遵循 `docs/design/UI_UX_SYSTEM.md` token（零硬編 hex；深色模式可讀）。
- [ ] 驗證：`cd web && npx tsc --noEmit`＋`npm test`＋`npm run build:check`；部署後 ISR revalidate 到期重測 `/methodology` 更新生效。

## 邊界與並行注意

- **不改** WP 計算、API、圖表資料流——純文案與方法頁內容。
- 賽況頁（`web/` games 區塊）預期被 `UX-LIVE-GAME1` 改版：本卡 claim 前與該卡對帳資源；
  若該卡已啟動，本卡限縮為曲線區塊單點插入或併入其 scope（由 Coordinator 裁定，避免雙卡同頁互踩）。
- 純前端版面迭代期間先不部署、滿意後一次上線（既有慣例）；但本卡部署本身是交付的一部分。

## 依賴與交付

- 依賴：無（事實基線報告皆已 merge）。
- 後續：戰力感知模型若另卡完成並通過驗證，本註記文案隨之修訂（屆時另卡處理）。

## Log

- 2026-07-26 依 ruan6047 指示開卡（WP-CAL1 結案後續；VAL1 §7 第 5 點裁定為「做、獨立卡」）。Coordinator register 併同 commit。
