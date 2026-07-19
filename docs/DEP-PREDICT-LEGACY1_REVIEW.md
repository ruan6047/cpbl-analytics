# DEP-PREDICT-LEGACY1 舊預測體驗退場獨立查核報告

- **卡片 ID**: [DEP-PREDICT-LEGACY1](tasks/DEP-PREDICT-LEGACY1.md)
- **Initiative**: `INIT-PRODUCT-UX`
- **變更層級**: `T3` (⚪ 一般)
- **分支/Worktree**: `ai/gpt-5-codex/DEP-PREDICT-LEGACY1` @ `.claude/worktrees/dep-predict-legacy1-execution`
- **查核基準 SHA**: `6e4a429e7bcde289bc716e84fba1895635e9271d` (handoff commit)
- **查核者**: `Antigravity（Gemini 3.5 Flash (High)）` (跨模型家族審查，符合獨立協作工作流)
- **執行者**: `GPT-5@Codex`
- **對照規格**: `docs/tasks/DEP-PREDICT-LEGACY1.md` 與 `PRODUCT_UX_BLUEPRINT v0.2 §7`

---

## 結論：核可 (APPROVE)

本卡之實作完全符合 `DEP-PREDICT-LEGACY1` 任務之驗收條件及設計準則：
1. **舊預測 UI 退場**：舊預測頁（`/predict`）已完全移除其前端互動，改以 307 導航指向 `/methodology#pregame` 作為深層連結的教育入口。
2. **導航與連結清理**：在頂部導覽「更多」選單中，正式移除「賽事預測」入口，並修正相關導航測試及邏輯判定（`isMoreActive` 正常）。
3. **未開賽單場頁驅動優化**：未開賽之單場賽況頁由舊有可選特徵互動之 `outcomeToday` API 呼叫，改為由固定語意的 `pregame` 模型（`/api/v1/outcome/pregame`）驅動，並調用 `<PregameCard/>` 呈現，實作乾淨。
4. **API 兼容性保留**：未直接移除 `/api/v1/outcome/matchups` 等後端 Public API 契約，符合「API退場另審」之兼容性約束。
5. **品質指標過關**：前端 TypeScript 靜態編譯無錯誤，Next.js build-check 成功通過，68 項單元測試全綠，後端 Python unit tests（340 passed）及 `ruff check` 亦全數通過。

---

## 🔍 驗收條件檢查清單

### 1. 稽核前端 Consumer (PASS)
- **舊元件與 API 調用清理**：
  - 成功移除了 `web/src/app/games/[sno]/page.tsx` 中對 `outcomeToday` API 的調用。
  - `web/src/lib/client.ts` 中的 `outcomeToday` 宣告已被安全移除，改為定義 `pregame` (對應底層 `/api/v1/outcome/pregame` 路由)。
  - `web/src/lib/api.ts` 中用於首頁 hub 的 `outcomeMatchups` API 行動與相關型別 (`HubMatchup`/`HubMatchupsResponse`) 已被全數移除，符合 §7 規範。
- **無殘留消費者**：
  - 執行 worktree 的 `grep` 搜索確認，前端除 `overview.tsx` 本身尚未使用的 legacy 舊 `Pregame` 元件（為安全不破壞編譯，僅保留內部宣告但不對外調用，無副作用）之外，沒有任何檔案引用或調用 legacy `/outcome/matchups` 等互動預測端點。

### 2. `/predict` 轉向與導覽死路排除 (PASS)
- **307 轉向**：
  - 在 `web/src/app/predict/page.tsx` 中，將整頁舊互動 UI 替換為以 `LegacyPredictPage` 調用 `redirect(methodologyHref("pregame"))` 的單一教育段落重導向。
- **導覽移除**：
  - 在 `web/src/lib/nav.ts` 中移除 `MORE_NAV` 內的 `{ href: "/predict", label: "賽事預測", group: "更多" }` 項。
  - 對應的 `web/src/lib/nav.test.ts` 新增/更新測試以確認「更多」僅收納紀錄室、球場與方法，且 `/predict` 不再啟動「更多」高亮，測試全綠通過。
- **Redirect 測試保護**：
  - 新增 `web/src/lib/predict-redirect.test.ts` 單元測試，強固驗證舊 predict 頁僅導向 pregame 方法段落，且不可再引用 `outcome/matchups` 或其他互動特徵，確保日後重構不發生 regression。

### 3. API 退場兼容性 (PASS)
- **後端 API 保留**：
  - 後端 `src/cpbl/api/routers/outcome.py` 依然維持 `/api/v1/outcome/matchups`、`/api/v1/outcome/simulate`、`/api/v1/outcome/evaluate`、`/api/v1/outcome/features` 等舊端點。
  - 本卡未破壞或修改後端 API 的 public contract，確保若有第三方 consumer（或主站舊輪詢）尚未遷移時不崩潰，完全符合 spec 要求。

---

## 🛠 測試與技術品質指標

- **前端測試**：運行 `npm test` 得到 68 項測試全數 PASS。
- **前端編譯**：在 `web/` 下執行 `npx tsc --noEmit` 無 any 型別報錯，且 `npm run build:check` (執行於 `.next-check` 獨立目錄) 成功產出 production build，確認無編譯障礙。
- **後端測試與 Lint**：在主庫執行 `uv run ruff check` 與 `uv run pytest` 全數通過（340 passed, 1 skipped），無回歸偏誤。

---

## 📝 Findings 紀錄

- **P0-P2 Findings**: **0 筆** (無 Blocking 問題)。

建議 Coordinator (ruan6047) 可以將此卡之實作分支合併至 `main` 並進行後續清理。
