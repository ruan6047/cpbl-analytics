# UX-PLAYER-IA2 Independent Audit Report

*   **Reviewed SHA**: `e8003b11ca3fcd9dbd319589dd64a8c7a016749f`
*   **Audit Iteration**: 1
*   **Verdict**: `↩退回` (REQUEST_CHANGES)
*   **Auditor**: Antigravity (Gemini 3.5 Flash (High), Independent Auditor)

---

## 1. 查核結論與 Findings 彙整

在對執行分支 `ai/opus-4-8/UX-PLAYER-IA2`（SHA: `e8003b1`）進行獨立查核後，判定為 **REQUEST_CHANGES（↩退回）**。

雖然本分支在標籤列佈局、375px 適應性、二軍 P0 防護回歸、守位圖移除徹底性以及 URL 參數相容性上皆完全達標，但發現了一項 **P1（高優先級阻擋級）** 的重複請求缺陷，違反了「無跨層重複請求」與「不重複請求同一端點」的驗收條件。

### 🚨 P1 缺陷：雙棲球員切換「打擊」與「投球」分頁時重複打 API 請求
*   **嚴重程度**: P1 (High)
*   **實測證據**:
    以 Playwright 監聽真實瀏覽器中的 API 請求，在雙棲球員（余德龍 `0000003563`）頁面進行分頁切換：
    1.  首頁載入後，切換至「投球」頁，觸發首次投球追蹤請求：
        *   `/api/v1/players/0000003563/discipline?role=pitching&kind_code=A`
        *   `/api/v1/players/0000003563/pitch-mix?role=pitching&kind_code=A`
        *   `/api/v1/players/0000003563/arsenal?role=pitching`
    2.  切換到「分項與對戰」頁。
    3.  **切回「打擊」頁**，再次觸發了打擊追蹤請求：
        *   `/api/v1/players/0000003563/discipline?role=batting&kind_code=A`
        *   `/api/v1/players/0000003563/pitch-mix?role=batting&kind_code=A`
        *   `/api/v1/players/0000003563/arsenal?role=batting`
    4.  **切回「投球」頁**，再次觸發了投球追蹤請求：
        *   `/api/v1/players/0000003563/discipline?role=pitching&kind_code=A`
        *   `/api/v1/players/0000003563/pitch-mix?role=pitching&kind_code=A`
        *   `/api/v1/players/0000003563/arsenal?role=pitching`
    這意味著每次在兩個主要身分分頁切換時，之前已抓過且緩存的數據均失效重抓。
*   **根因分析**:
    在 [page.tsx](file:///Users/ruanruan/Dev/cpbl-analytics/.claude/worktrees/ux-player-ia2-execution/web/src/app/players/%5Bid%5D/page.tsx#L132) 中：
    ```typescript
    once("tracking", `${id}-${pageRole}-${seasonKind}`, () => {
      setDisc(null);
      setPitchMix(null);
      setArsenal(null);
      detail.discipline(id, pageRole, seasonKind)...
    });
    ```
    快取快照函式 `once` 的 group 名被寫死為 `"tracking"`。這導致 `batting` 與 `pitching` 的載入共用同一個 `loaded.current["tracking"]`。
    當切換至 `pitching`，`tracking` 快取鍵被改寫為 `pitching` 相關鍵；切回 `batting` 時，`once` 判斷當前快取鍵不等於打擊鍵，因而判定快取失效並再次發送請求，將已快取的投球鍵覆蓋。如此循環造成頻繁重複請求。
*   **建議修正**:
    應比照 `trend-${r}` 的設計，將 group 名與 pageRole 綁定，改為：
    ```typescript
    once(`tracking-${pageRole}`, `${id}-${pageRole}-${seasonKind}`, () => {
    ```

---

## 2. 驗收項目逐項檢查表

| 驗收項目 | 檢查結果 | 證據／實測數據 |
| :--- | :---: | :--- |
| **1. 標籤列組成與切換鈕移除** | **PASS** | 雙棲（余德龍）顯示 `['打擊', '投球', '分項與對戰', '守備', '生涯']`。純打者（郭天信）/純投手（羅戈）正確排除不擁有的身分頁。全頁無任何 role 切換鈕。 |
| **2. 守備獨立層** | **PASS** | 守備已成為獨立的 SubLayer，label 為「守備」。 |
| **3. 雙棲堆疊與身分小標** | **PASS** | 雙棲球員的總覽、分項對戰、生涯層上下堆疊，且各自標記「打擊」與「投球」身分小標；單一身分球員無身分小標（避免雜訊）。 |
| **4. 舊連結相容性 (P0 防線)** | **PASS** | `?sec=approach` 導向打擊（郭天信）；`?role=pitching` 未給 sec 導向投球（余德龍），已給 sec（如 `sec=splits`）時不覆蓋。退役球員（彭政閔）預設落生涯層。 |
| **5. 依層延後載入與無重複請求** | **FAIL** | 發現 `tracking` 資料組在雙棲切換時，因為 once 鍵名共用 `"tracking"` 導致快取互相覆蓋，切換時重複打 API。 |
| **6. 鍵盤導覽 (ArrowLeft/ArrowRight)** | **PASS** | 鍵盤操作 ←/→ 可在標籤列間切換且焦點跟隨正確。 |
| **7. 375px 寬度無水平溢出** | **PASS** | `SubNav` 的 button padding 從 `px-3.5` 縮減為 `px-3`，實測 `tablist` 寬度剛好為 335px 塞滿。最後一個標籤「生涯」的 `getBoundingClientRect().right` 為 342px，小於 tablist 的右邊界 355px，完整可見、不需橫捲。 |
| **8. 二軍過濾防護 (前輪 P0 回歸)** | **PASS** | `vizRows` 邏輯完好。實測二軍球員高捷 (`0000007091`)，其守備價值卡正確隱藏，沒有取用二軍數據，且回歸測試通過。 |
| **9. 守位圖移除徹底性** | **PASS** | 項目中無任何 `POS_COORD` / `posLabel` / `FieldPositionMap` 死程式碼及 orphan imports。多守位標記與表格完整保留。 |

---

## 3. 品質閘門 (Quality Gates) 自行驗證結果

*   **TypeScript 編譯**: `npx tsc --noEmit` 通過 (clean)。
*   **Next.js 建置**: `npm run build:check` 成功編譯，靜態頁生成成功。
*   **React 單元測試**: `npm test` 共 99 項測試全數通過 (`99 passed, 0 failed`)。
*   **Python Ruff Linter**: `uv run ruff check` 通過 (clean)。
*   **Python Pytest 測試**: `uv run pytest` 共 357 項測試通過，1 項跳過 (`357 passed, 1 skipped`)。
*   **分支乾淨度**: `git diff main..HEAD` 顯示僅修改前端 `/players/[id]` 的 6 個程式與測試檔，未含 `docs/control-plane/**` 或 `docs/TASKS.md`。

---

## 4. 查核結論處置
本任務已退回（`REQUEST_CHANGES`）。需由原執行者修正 once 緩存鍵重複覆蓋的問題後，再次提交 Iteration 2 查核。
當前工作區 `.claude/worktrees/ux-player-ia2-execution` 與開發伺服器（API :4016 / Front :3016）予以保留供下一輪使用。
