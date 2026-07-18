# UX-MATCHUP1 查核報告 — /matchups 查詢式頁面重製

- **卡片 ID**: [UX-MATCHUP1](tasks/UX-MATCHUP1.md)
- **Initiative**: `INIT-PRODUCT-UX`
- **變更層級**: `T4` (🔴 統計／ML 紅線及文案紅線)
- **分支/Worktree**: `ai/fable-5/UX-MATCHUP1` @ `.claude/worktrees/ux-matchup1-execution`
- **查核基準 SHA**: `e81af6b3880ab8e74c2fb93bb4e8f5edbb8dde18` (handoff commit)
- **查核者**: `Gemini 3.5 Flash (High)@Antigravity` (跨模型家族審查)
- **執行者**: `Fable-5@Claude Code`
- **對照規格**: `docs/tasks/UX-MATCHUP1.md` 與 `matchups-redesign.md`

---

## 結論：核可 (APPROVE)

本卡實作完全符合 `UX-MATCHUP1` 任務所有驗收條件與紅線約束。新版 `/matchups` 成功轉型為精緻的查詢式投打對決工具，其空狀態與洞察判定正確，並擁有完善的單元測試防護。

---

## 🔍 驗收條件檢查清單

### 1. 基礎實績與洞察加值層分離 (PASS)
- **沒有洞察時照常查詢**：當對戰洞察觸發 fail-closed 退化或 API 故障（`insightsErr=true`）時，[matchups-client.tsx](file:///Users/ruanruan/Dev/cpbl-analytics/web/src/app/matchups/matchups-client.tsx) 中的對戰查詢與對手清單表格不受影響，依然可依年度、範圍、賽事類型及隊伍查詢原始對戰資料（PA、AVG、OPS 等）。
- **無「天敵」確定語氣**：
  - 洞察卡片標籤使用「對戰劣勢候選」與「對戰優勢候選」（`INSIGHT_LABELS`），文案表（`INSIGHT_COPY`）中無任何確定斷言式「天敵」語氣。
  - 前端單元測試 [insight-state.test.ts](file:///Users/ruanruan/Dev/cpbl-analytics/web/src/app/matchups/insight-state.test.ts) 中的 `"洞察標籤用候選語氣，全部文案不出現「天敵」斷言"` 進行了自動化防護。

### 2. 四種 Fail-Closed 狀態的獨立版面與文案 (PASS)
[insight-section.tsx](file:///Users/ruanruan/Dev/cpbl-analytics/web/src/app/matchups/insight-section.tsx) 配合 [insight-state.ts](file:///Users/ruanruan/Dev/cpbl-analytics/web/src/app/matchups/insight-state.ts) 將四種 fail-closed 狀態與無資料狀態獨立呈現：
- **low_coverage（覆蓋率不足）**：當 `coverage.passed === false` 時，呈現覆蓋率量尺（`CoverageMeter`），揭露目前樣本對官方生涯的可觀察比例，且提示基礎查詢照常。
- **no_prior（先驗無法估計）**：當 `method.prior_available === false` 時，說明配對不足以估計經驗貝氏先驗（tau²），不使用聯盟平均硬補，誠實隱藏排行。
- **gated（候選未過可信度閘門）**：展示候選總數與通過數，並明示「所有候選經回縮後皆未通過可信度閘門」，不給予暗示。
- **no_baseline（C–E 無比較基準）**：季後挑戰賽（E）與總冠軍賽（C）因官方未發布同賽事類型的季彙總 baseline，因此顯示無 baseline 說明，照常呈現原始對戰。
- **不重做統計（T4 紅線）**：所有判定（例如 `coverage.passed`、`method.prior_available`、`delta_shrunk`）完全直接讀取 API 明示欄位，前端無任何自創門檻。

### 3. 年度／範圍與隊伍語意隔離 (PASS)
- **範圍與涵蓋不混淆**：隊伍篩選（`team`）僅限縮 `query_sample`（本次查詢樣本數與對手數），`coverage`（全 scope 對戰覆蓋率）依舊以官方生涯全體對手之打席比例評估，兩者結構與語意在 UI 與 API 參數中清晰隔離。
- **年度範圍提示**：在 /matchups 選擇指定年度範圍（`range`）而查無對戰時，會明確提示官網對戰資料僅提供「本季年度列」與「生涯彙總列」，引導使用者正確查詢。

### 4. 角色翻轉與對稱性呈現 (PASS)
- **主角視角號向轉換**：利用 `subjectDelta` 函數在打者視角直接使用 `delta_shrunk`，而在投手視角取其相反數（`-delta_shrunk`）。保證同一組對決（如林泓育 vs 陳鴻文）在打者與投手不同視角下：
  - 同組對決的絕對差值 $|delta|$ 相同。
  - 優劣標籤與方向鏡像（打者的劣勢 = 投手的優勢）。
- 對稱性在 [insight-state.test.ts](file:///Users/ruanruan/Dev/cpbl-analytics/web/src/app/matchups/insight-state.test.ts) 中以 fixture 契約測試固定。

### 5. UI 與 UX 可及性驗證 (PASS)
- **行動端適配**：對手清單表格 wrapped 於 `overflow-x-auto`，確保 375px 寬度下頁面主體不產生橫向溢出，表格可獨立橫向捲動。
- **鍵棒與無障礙**：
  - `SearchCombobox` 完整實作 ARIA 規格，包含 `role="combobox"`、`role="listbox"`、`role="option"`、`aria-expanded`、`aria-controls` 等，並支援鍵盤 ArrowUp / ArrowDown 選取、Enter 確定、Escape 關閉。
  - 清除搜尋結果後，自動將 `focus()` 還給輸入框，鍵盤操作流程不中斷。
- **Deep-linking 可分享**：所有查詢變數皆存於 URL `SearchParams`（`role`、`kind`、`scope` , `from`, `to`, `pid`, `team`, `opp` 等），保證深層連結點入即可完全重現對決畫面。

---

## 🛠 測試與技術品質指標

- **前端單元測試**：49/49 測試全數通過（`npm test`），其中包含 14 個針對 UX-MATCHUP1 各種 empty / ok / flipped fixture 契約與 delta 轉換的專屬測試。
- **前端建置檢查**：`npm run build:check` 在獨立 `NEXT_DIST_DIR` 下 Next.js 15 編譯成功，無任何 TypeScript 與 Linter 錯誤，`/matchups` 頁面預渲染 Suspense 邊界正確。
- **後端回歸測試**：283 個 python pytest 測試全部通過。
- **後端代碼格式**：`ruff check` 檢查無缺陷。
- **版本控制與留痕**：無後端代碼與 db/migration 異動，變更範圍僅限 `web/src/app/matchups/` 底下檔案，乾淨解耦。

---

## 📝 Findings 紀錄

- **P0-P2 Findings**: **0 筆** (無未解決 Blocking 問題)。

建議 Coordinator 可以將此卡之實作分支合併至 `main`。
