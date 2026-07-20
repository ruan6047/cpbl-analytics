# UX-PLAYER-FIELDVIZ1 球員守備呈現獨立查核報告 (Iteration 1)

- **被審 SHA**：`43e674e1d51840e5046683d1e6db06e8b187289d`
- **交付分支**：`ai/opus-4-8/UX-PLAYER-FIELDVIZ1`
- **審查結論**：↩ 退回（`REQUEST_CHANGES`）
- **Findings**：`P0=1`；`P1=0`；`P2=0`

---

## 🔍 核心缺陷與證據（Findings & Evidence）

### P0 缺陷：二軍守備數據（`kind_code='D'`）錯誤滲入身分圖與價值卡元件

*   **Severity**: P0 (阻礙上線的嚴重資料正確性缺陷)
*   **檔案 / 行號**: 
    *   [`web/src/app/players/[id]/fielding.tsx` L198-202](file:///Users/ruanruan/Dev/cpbl-analytics/.claude/worktrees/ux-player-fieldviz1-execution/web/src/app/players/%5Bid%5D/fielding.tsx#L198-L202)
    *   [`web/src/app/players/[id]/fielding-metrics.ts`](file:///Users/ruanruan/Dev/cpbl-analytics/.claude/worktrees/ux-player-fieldviz1-execution/web/src/app/players/%5Bid%5D/fielding-metrics.ts)
*   **可重現步驟**:
    1.  啟動本地 API 服務於 port 4015、前端 Next.js 於 port 3015。
    2.  以瀏覽器（或 Playwright）訪問二軍球員 **高捷 (0000007091)** 的個人守備頁面：`http://localhost:3015/players/0000007091?sec=career`。
    3.  檢查守備位置身分圖（`FieldPositionMap`）渲染的文字標籤與守位分布。
*   **證據**:
    *   在該頁面加載後，API 返回了高捷 2026 年的二軍守備數據（`kind_code='D'`）。
    *   `FieldPositionMap` 正確渲染，且包含多個高捷在二軍守備的位置，標記的文字為：`['一壘', '10 場', '二壘', '10 場', '三壘', '8 場', '中外野', '5 場', '右外野', '1 場', '左外野', '1 場']`。
    *   其中「中外野 5 場」和二軍場次直接顯露在 SVG 示意圖中。
    *   這直接違反了驗收標準中 **「二軍（`kind_code='D'`）不得進入任一元件」** 的紅線。
*   **預期行為**:
    *   二軍守備列不得以任何形式進入身分圖或價值卡。
    *   在二軍登錄頁面下，身分圖應退回顯示其**一軍生涯歷史**累計守位分布（`careerRows`），價值卡應直接隱藏（因生涯列無局數且二軍不作評價）。
*   **修正方向**:
    *   在 `fielding-metrics.ts` 中新增一個純過濾邏輯函式（例如 `vizRows()`），傳入 `seasonRows`、`careerRows` 以及 `isFarmView`（或由 `seasonKind === 'D'` 判定），若為二軍視角則直接過濾排除所有二軍本季數據，並使其退回一軍生涯數據。
    *   在 `fielding-metrics.test.ts` 中補上對應的過濾回歸測試，保障二軍排除機制的正確性。

---

## ⚙️ 測試與編譯查核狀態

*   **單元測試**: `npm test` 87 Passed（缺二軍過濾相關測試）。
*   **Python 測試**: `uv run pytest` 357 Passed。
*   **類型檢查與建置**: `npx tsc --noEmit` 與 `npm run build:check` 均編譯通過。
*   **代碼風格**: `uv run ruff check` 通過。

---

## 🚫 處置裁決

本卡判定為 **REQUEST_CHANGES**。請原執行者依據上述修正方向處理 P0 資料滲透缺陷，修復完成後重新提交 Iteration 2 查核。
本次查核**不進行代碼修改、不合併分支、不部署生產環境，保留 Worktree 與本地租約**。
