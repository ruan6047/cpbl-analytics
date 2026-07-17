# UX-OUTCOME-HOME 查核報告 — 可嵌入賽前勝率卡

- **卡片 ID**: [UX-OUTCOME-HOME](tasks/UX-OUTCOME-HOME.md)
- **Initiative**: `INIT-PRODUCT-UX`
- **變更層級**: `T4` (🔴 統計／ML 及文案紅線)
- **分支/Worktree**: `ai/fable-5/UX-OUTCOME-HOME` @ `.claude/worktrees/cpbl-analytics-blueprint-a734ec`
- **查核基準 SHA**: `e7e2c7adbf90e787530a8f8b21532afa54d60788` (handoff commit)
- **查核者**: `Gemini 3.5 Flash (High)@Antigravity` (跨模型家族審查)
- **執行者**: `Fable-5@Claude Code`
- **對照規格**: `docs/tasks/UX-OUTCOME-HOME.md` 與 `PRODUCT_UX_BLUEPRINT v0.2`

---

## 結論：核可 (APPROVE)

本卡實作符合所有紅線約束。元件解耦良好，狀態機轉換正確，已由 Node 單元測試及 Python 後端測試完整保護。

---

## 🔍 驗收條件檢查清單

### 1. 點機率與單一主訊號 (PASS)
- **只顯示點機率**：在 [pregame-card.ts](file:///Users/ruanruan/Dev/cpbl-analytics/web/src/lib/pregame-card.ts) 中，`PregameCardModel` 的 available 狀態僅含有 `homeWinProbability` 與 `probabilityText`，不帶任何區間欄位，亦未洩漏給 UI。
- **單一主訊號規則**：在 [pregame-card.ts](file:///Users/ruanruan/Dev/cpbl-analytics/web/src/lib/pregame-card.ts) 定義了固定群優先序：
  ```typescript
  export const PRIMARY_SIGNAL_GROUP_ORDER = ["suppression", "strength", "offense", "schedule"] as const;
  ```
  當 `suppression`（先發投手 ERA 差）缺值時自動退位至下個順位。在 `available_no_starter` fixture 已正確驗證該退位行為。
- **文案紅線**：卡片內不含「信賴區間」或「區間」等字眼。已由 [pregame-card.test.ts](file:///Users/ruanruan/Dev/cpbl-analytics/web/src/lib/pregame-card.test.ts) 進行回歸測試防護。

### 2. 五態 Fixtures 與非阻塞設計 (PASS)
- **五態覆蓋**：[pregame-card-fixtures.ts](file:///Users/ruanruan/Dev/cpbl-analytics/web/src/lib/pregame-card-fixtures.ts) 完整定義了六個 fixtures（五態加上退位變體）。
- **無假數字**：非 available 狀態一律回傳不可用說明，不回傳 `homeWinProbability`。
- **不阻塞外層**：當 status 非 available 時，[pregame-card.tsx](file:///Users/ruanruan/Dev/cpbl-analytics/web/src/components/pregame-card.tsx) 只渲染一個淡色的附註 `<p className="text-xs text-faint" role="note">{model.message}</p>`，不會干擾或阻塞外層賽程卡片渲染。

### 3. 元件解耦與嵌入契約 (PASS)
- **純展示元件**：`PregameCard` 為純 Stateless Functional Component，不直接獲取資料，不決定區塊排序，也不修改首頁文案，皆由傳入 props 的 view model 控制。
- **無首頁資源衝突**：本分支完全沒有修改 `web/src/app/page.tsx`。首頁 Owner 仍乾淨歸屬給 `UX-GAME-HOME1`。

---

## 🛠 測試與技術品質指標

- **前端單元測試**：36 個測試全綠（`npm test`）。
- **前端建置檢查**：`npm run build:check` 編譯成功，無 TypeScript 錯誤（/dev/pregame-card 頁面會在 production build 時正確回傳 404 防止假資料洩漏）。
- **後端單元測試**：255 個 pytest 測試及 Ruff 檢查全部通過。
- **對帳檢驗**：`workflow_ledger.py --check` 對帳無漂移。
- **無障礙 (a11y) 與 UX 走查**：
  - 行動端（375px）走查無橫向溢出。
  - 元件根部採用 `role="group"` 與 `aria-label` 正確傳達語意。
  - 視覺填充條採用 `aria-hidden` 並限定在 `[1%, 99%]` 的百分比，防範極端機率下的 UI 突兀感。

---

## 📝 Findings 紀錄

- **P0-P2 Findings**: **0 筆** (無未解決 Blocking 問題)。

建議 Coordinator 可以將此卡之實作分支合併至 `main`。
