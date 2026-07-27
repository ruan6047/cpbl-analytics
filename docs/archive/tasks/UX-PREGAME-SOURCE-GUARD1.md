# UX-PREGAME-SOURCE-GUARD1 賽前勝率單一來源守衛改為全域不變式〔T2〕

- 需求：ruan6047（2026-07-27 LEAK2 iteration 6 裁定：不在 LEAK2 內擴 scope，獨立開卡）　規劃：本卡 spec　分支：依認領時 worktree 慣例
- 執行：待指派　查核：待指派（≠ 執行；T2 不跨家族）
- Initiative：—　spec 基線：—
- DB：`db_scope: none`（不碰 DB）
- 部署：否（測試層變更；隨下次例行部署帶上即可）　環境：—　PR：—　Merge SHA：—
- current-state：🚧執行中（2026-07-27 派工）；前置條件已解除（ML-OUTCOME-SIMPLE-LEAK2 已 merge 2aa27a3 並上線驗證）。

## 背景（為什麼）

ML-OUTCOME-SIMPLE-LEAK2 連續三輪出現同一個結構問題：**同一個畫面上兩個必須一致的事實，
來自不同來源／不同新鮮度**。iteration 4 以「單一 response」根治，並加了結構守衛
`web/src/lib/pregame-single-source.test.ts`，禁止渲染頁面另外取 `api.pregameServing()`。

但那支守衛靠一份**手寫**的 `RENDERING_SOURCES` 檔案清單。它的失效模式已經真實發生過一次：
賽況頁 `games/[sno]` 是第三個渲染介面，開卡時 scope 沒寫全，直到 iteration 5 才補上——
在那之前守衛對它**靜默無效**。新增同類頁面而忘了加清單，守衛不會報錯，只會不保護。

一個「漏列就靜默失效」的守衛，正是它自己要防的那種缺陷。

## 目標（2026-07-27 需求方裁定改寫；原方案為「掃描反查渲染介面」）

**不做自動反查。** 自動反查得先定義「什麼算渲染介面」，最自然的錨點是「有沒有 import
`resolvePregameCard`／`homePregameNotice`」——但**真正危險的新頁面正好不會 import 它們**：
它可以自己打 `api.pregame()`、直接讀 `item.home_win_probability` 渲染，再自己抓一次 serving
狀態。這種頁面對 import 掃描完全隱形。自動反查只是把手寫清單的盲點換個位置。

問題出在**量詞方向**。現行守衛是「對每個渲染介面，斷言它不做 X」——這需要窮舉介面，而窮舉
正是會漏的那一步。反過來寫就不必窮舉：**在整個 `web/src` 裡，X 只准出現在指定的幾個位置**。
新檔案一存在就自動被涵蓋，因為規則列舉的是例外，不是主體。

改為兩條全域規則（現況已查證，兩條都套得上）：

**規則 1｜第二來源不可達。** `api.pregameServing` 在 web 端**零呼叫者**（只有 `lib/api.ts`
的定義本身），ops 對帳走 `curl`。**直接從 client 刪掉這個方法**——刪掉之後「取第二份
response」不是被測試擋住，而是根本沒有那個東西可以呼叫；要用得先明著加回來、經過 review。
`/api/v1/outcome/pregame/serving` **端點本身保留**（ops 探針，且已在路由快照測試內），本卡
只動 web client。

**規則 2｜機率只有一條推導路徑。** `home_win_probability` 只准在下列三處被讀，其他任何
位置出現即失敗：`lib/pregame-card.ts`（賽況頁 resolver）、`lib/daily-summary.ts`（首頁
resolver）、`lib/pregame-card-fixtures.ts`（假資料）。**這條原卡面完全沒寫，但它才是真正
防住「新頁面自己解一次機率」的那一條**——規則 1 只防了 serving 狀態，沒防機率本身。

## 實作邊界

1. **不引入 ESLint。** `no-restricted-syntax` 走 AST、語意上最正確（不會被註解與字串誤判，
   上一輪就踩過一次假陽性），但 `web/` 目前**沒有 eslint 設定也沒有 eslint 依賴**
   （`next lint` 會要求先初始化）。為一條規則引入 lint 工具鏈＋設定＋CI 接線，以本專案的
   維護成本取向不划算。維持讀原始碼的測試，但把比對收嚴到 import／property access 形態，
   並排除註解行，避免上一輪那種假陽性。
2. **`RENDERING_SOURCES` 手寫清單移除**，不以任何形式（含自動產生的清單）復活——規則以
   allowlist 表達例外，不表達主體。
3. 反向驗證（交付必附，兩條各一）：
   - 規則 1：在任一頁面加回 `api.pregameServing()` 的呼叫 → 測試須紅（型別層先紅亦可，
     但須明確說明是哪一層擋下的）；移除後回綠。
   - 規則 2：在 `app/` 下新建一個假頁面讀 `item.home_win_probability` → 測試須紅；移除後回綠。
     **這條是重點**：它證明新頁面自己解機率會被抓到，而這正是舊守衛照不到的情形。
4. 掃描不得顯著拖慢 `npm test`（目前全套 < 1s，維持同量級）。

## 驗收條件

- [ ] `api.pregameServing` 自 `web/src/lib/api.ts` 移除；連帶未使用的型別一併清掉；`/api/v1/outcome/pregame/serving` 端點與其路由快照**不動**。
- [ ] 新增規則 2 守衛：`home_win_probability` 僅允許出現在 `lib/pregame-card.ts`、`lib/daily-summary.ts`、`lib/pregame-card-fixtures.ts`；allowlist 以外任何位置出現即失敗。
- [ ] `RENDERING_SOURCES` 手寫清單移除，且未以自動產生的清單復活。
- [ ] 兩條規則各附反向驗證原始輸出（加回去 → 紅；移除 → 綠）。
- [ ] `docs/research/ML-OUTCOME-SIMPLE-LEAK2_RESULTS.md` §9 第 2 條（`RENDERING_SOURCES` 手動維護）改寫為已解決，並說明改用全域規則。
- [ ] `cd web && npx tsc --noEmit`＋`npm test`＋`npm run build:check` 全綠；`uv run ruff check`＋`uv run pytest` 未受影響。

## 驗證

- [ ] 查核者自行在 `app/` 下新建一個假頁面直接讀 `item.home_win_probability`（**不 import 任何
      共用 symbol**），確認規則 2 會抓到——這正是舊守衛照不到的情形，不採信執行者轉述。
- [ ] 查核者確認 `api.pregameServing` 確實已從 web client 消失，且 `/api/v1/outcome/pregame/serving`
      端點與路由快照未被動到。
- [ ] 查核者確認執行期行為零改動：三個介面的賽前勝率與降級告示與 merge 前一致（`npm run build:check`
      路由型態不變，`daily-summary.test.ts`／`pregame-card.test.ts` 既有斷言全數保留）。

## 邊界

- 不改文案、不改渲染邏輯、不改後端。唯一的執行期改動是刪掉 web client 裡零呼叫者的
  `api.pregameServing`（規則 1）；其餘為測試層。
- 預估 S（半天內）；若發現必須動執行期程式碼才做得到，即停並回報需求方重新裁定 tier。

## Log

- 2026-07-27 依 ruan6047 裁定改寫「目標」與驗收（原方案「掃描反查渲染介面」補不完盲點；改為兩條全域規則，量詞由「對每個介面斷言」反轉為「X 只准出現在這幾處」）。
- 2026-07-27 依 ruan6047 裁定開卡（LEAK2 iteration 6 自主判斷 (3)：不在已六輪的 LEAK2 內再擴 scope，獨立成卡）。
