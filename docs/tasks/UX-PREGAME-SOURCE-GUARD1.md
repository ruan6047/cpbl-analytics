# UX-PREGAME-SOURCE-GUARD1 賽前勝率單一來源守衛改為自動反查〔T2〕

- 需求：ruan6047（2026-07-27 LEAK2 iteration 6 裁定：不在 LEAK2 內擴 scope，獨立開卡）　規劃：本卡 spec　分支：依認領時 worktree 慣例
- 執行：待指派　查核：待指派（≠ 執行；T2 不跨家族）
- Initiative：—　spec 基線：—
- DB：`db_scope: none`（不碰 DB）
- 部署：否（測試層變更；隨下次例行部署帶上即可）　環境：—　PR：—　Merge SHA：—
- current-state：📥Backlog；**須待 ML-OUTCOME-SIMPLE-LEAK2 merge 後才可認領**（本卡要改的檔案是該卡新增的）。

## 背景（為什麼）

ML-OUTCOME-SIMPLE-LEAK2 連續三輪出現同一個結構問題：**同一個畫面上兩個必須一致的事實，
來自不同來源／不同新鮮度**。iteration 4 以「單一 response」根治，並加了結構守衛
`web/src/lib/pregame-single-source.test.ts`，禁止渲染頁面另外取 `api.pregameServing()`。

但那支守衛靠一份**手寫**的 `RENDERING_SOURCES` 檔案清單。它的失效模式已經真實發生過一次：
賽況頁 `games/[sno]` 是第三個渲染介面，開卡時 scope 沒寫全，直到 iteration 5 才補上——
在那之前守衛對它**靜默無效**。新增同類頁面而忘了加清單，守衛不會報錯，只會不保護。

一個「漏列就靜默失效」的守衛，正是它自己要防的那種缺陷。

## 目標

把 `RENDERING_SOURCES` 從手寫清單改成**自動反查**：掃描 `web/src/app/` 與
`web/src/components/`，找出所有渲染賽前勝率或其 serving 狀態的檔案，再對每一個檔案套用
既有斷言。清單漏列不再可能，因為沒有清單了。

**不改任何執行期程式碼、不改任何對外文案、不動 API。** 純測試層。

## 實作邊界

1. **判定「這是渲染介面」的規則要能自我證明**：不得只 grep 一個字串就當作窮舉。建議以
   「引用了 `pregame-card` 或 `daily-summary` 的告示／view-model symbol」為錨點反查，
   並在測試內**斷言至少涵蓋目前已知的三個介面**（首頁 `DailyHub`、`/methodology`、
   賽況頁 `PregameCard`）——若掃描結果少於這三個，測試必須失敗，代表掃描規則本身壞了。
2. 反向驗證（交付必附）：新建一個暫時性的假頁面呼叫 `api.pregameServing()`，確認測試
   **會紅**；刪掉後回綠。沒做反向驗證的守衛不算守衛。
3. 掃描不得因檔案數成長而顯著拖慢 `npm test`（目前全套 < 1s，維持同量級）。

## 驗收條件

- [ ] `RENDERING_SOURCES` 手寫清單移除，改為掃描 `web/src/app/`＋`web/src/components/` 反查。
- [ ] 掃描結果少於已知三介面時測試失敗（防掃描規則本身失效）。
- [ ] 附反向驗證：新增假渲染頁 → 測試紅；移除 → 綠。原始輸出貼進交付回報。
- [ ] `docs/research/ML-OUTCOME-SIMPLE-LEAK2_RESULTS.md` §9 第 2 條（`RENDERING_SOURCES` 手動維護）標記為已解決。
- [ ] `cd web && npx tsc --noEmit`＋`npm test`＋`npm run build:check` 全綠；`uv run ruff check`＋`uv run pytest` 未受影響。

## 驗證

- [ ] 查核者自行新增一個引用 `resolvePregameCard`／`homePregameNotice` 的假頁面並呼叫
      `api.pregameServing()`，確認測試會抓到（不採信執行者轉述）。
- [ ] 查核者確認未改動任何執行期程式碼（`git diff` 僅測試檔與必要的測試工具）。

## 邊界

- 純測試層；不改 API、不改文案、不改渲染邏輯。
- 預估 S（半天內）；若發現必須動執行期程式碼才做得到，即停並回報需求方重新裁定 tier。

## Log

- 2026-07-27 依 ruan6047 裁定開卡（LEAK2 iteration 6 自主判斷 (3)：不在已六輪的 LEAK2 內再擴 scope，獨立成卡）。
