# UX-PLAYER-IA2 Independent Audit Report

*   **Reviewed SHA**: `c1d81e0028df5fccf5d175fbaf474db4b496ce08`
*   **Audit Iteration**: 2
*   **Verdict**: `✅通過` (APPROVE)
*   **Auditor**: Antigravity (Gemini 3.5 Flash (High), Independent Auditor)

---

## 1. 查核結論與 Findings 彙整

在對執行分支 `ai/opus-4-8/UX-PLAYER-IA2`（SHA: `c1d81e0`）進行獨立查核後，判定為 **APPROVE（✅通過）**。

前一輪發現的 P1 阻塞缺陷已完美修復。我們編寫並執行了基於 Playwright 的自動化查核腳本 [verify_ui.py](file:///Users/ruanruan/.gemini/antigravity-cli/brain/96e9b63b-869a-4fcf-8010-cbf2bd754f52/scratch/verify_ui.py)，在真實瀏覽器中量測 API 請求與佈局狀態，所有驗收指標皆高標準通過。

以下是針對五個查核重點的詳細實測數據與證據：

### (A) 上一輪 P1 快取失效缺陷的修正驗證
*   **修正機制**: 抽出 `loadGroup()` 與 `createLoadTracker()`。依 role 的資料組（如 `tracking`）之快取組名變更為 `tracking:batting` 與 `tracking:pitching`，各自獨立快取。
*   **實測數據 (余德龍 `0000003563` 雙棲點擊序列)**:
    1.  首載頁面 (打擊為預設 sec): 觸發 14 個 API 請求（包含 `trend?role=batting`, `trend?role=pitching` 及 `discipline?role=batting` 等）。
    2.  切換到「投球」層: 僅發送 4 個 API 請求（新加載的投球追蹤 `discipline?role=pitching`, `pitch-mix?role=pitching`, `arsenal?role=pitching`, `movement`），無重複請求。
    3.  切換到「分項與對戰」層: 發送 8 個 API 請求（`splits?role=batting`, `splits?role=pitching`, `vs-team?role=batting`, `trend-career?role=batting` 等）。
    4.  **切回「打擊」層**: **API 請求數 = 0！** (完全命中快取)
    5.  **再切回「投球」層**: **API 請求數 = 0！** (完全命中快取)
*   **結論**: 快取機制完全成立，重複訪問已看過的分頁確實為零 API 呼叫。

### (B) Sticky 標籤列被 Header 遮蔽之量測驗證
*   **修正機制**: 使用 `ResizeObserver` 在執行期量測 z-40 header 高度並寫入 SubNav style top。
*   **實測數據**:
    *   **行動端 375px**: 捲動 500px 後，z-40 header 實測高度 73px。五個標籤中心點（打擊、投球、分項與對戰、守備、生涯）皆未被 header 覆蓋，`document.elementFromPoint` 精確命中標籤按鈕本身。
    *   **桌面端 1280px**: 捲動 500px 後，z-40 header 實測高度 62.5px。同樣所有標籤點擊中心皆完全命中標籤按鈕本身。
*   **結論**: z-20 標籤列現在在捲動後會精準停留在 header 下方，不被遮蔽且完全可點擊。

### (C) Profile 載入前搶抓錯層資料驗證
*   **修正機制**: 為 trend / splits / career 等 effect 加上 `profile` 載入就緒門檻，避免空 profile 時誤判 role 狀態。
*   **實測數據 (羅戈 `0000005151` 純投手直入 ?sec=pitching)**:
    *   API 請求流：`profile` -> `career` -> `ability-card` -> `season?kind=A` -> `advanced?kind_code=A` -> `trend?role=pitching` -> `discipline?role=pitching` -> `movement?kind_code=A`。
    *   **無** `trend?role=batting` 請求，**無** `vs-team` 請求，**無** `trend-career` 請求。
*   **結論**: profile 載入前不會搶抓其他層/其他身分的不必要資料，無溢出請求。

### (D) 二軍過濾防護 (前輪 P0 回歸) 驗證
*   **修正機制**: 確保 `vizRows()` 在二軍鏡頭時不使用本季二軍守備列， usesSeason 判定為 false。
*   **實測數據 (高捷 `0000007091` 二軍選手)**:
    *   守備層下，usesSeason 正確為 false。
    *   **價值卡 (守備指標) 渲染數量 = 0** (正確隱藏，沒有被二軍數據污染)。
    *   本季守備表格 (出賽場次如一壘手10場、二壘手10場) 與生涯累計表格 (左外野手22場、一壘手9場) 數據對照完全正常且分離。
*   **結論**: 二軍過濾防護完好，二軍守備數據不會錯滲入價值卡。

### (E) 守位圖移除徹底性驗證
*   **修正機制**: 徹底刪除 `POS_COORD` / `posLabel` / `FieldPositionMap` 元件與測試。
*   **實測數據**:
    *   高捷頁面上「Found 0 SVG maps under Fielding section」，無殘留的守位圖。
    *   「多守位」標籤與原始表格保留正常。
*   **結論**: 守備身分圖已被乾淨移除，將由 `UI-FIELD-DIAGRAM1` 在 Backlog 中以轉播風格重做。

---

## 2. 驗收項目逐項檢查表

| 驗收項目 | 檢查結果 | 證據／實測數據 |
| :--- | :---: | :--- |
| **1. 標籤列組成與切換鈕移除** | **PASS** | 雙棲顯示 `['打擊', '投球', '分項與對戰', '守備', '生涯']`。純打者/純投手正確排除不擁有的身分頁。全頁無任何 role 切換鈕。 |
| **2. 守備獨立層** | **PASS** | 守備已成為獨立的 SubLayer，label 為「守備」。 |
| **3. 雙棲堆疊與身分小標** | **PASS** | 雙棲球員的總覽、分項對戰、生涯層上下堆疊，且各自標記「打擊」與「投球」身分小標；單一身分球員無身分小標。 |
| **4. 舊連結相容性 (P0 防線)** | **PASS** | `?sec=approach` 導向打擊；`?role=pitching` 未給 sec 導向投球，已給 sec（如 `sec=splits`）時不覆蓋。退役球員（彭政閔）預設落生涯層。 |
| **5. 依層延後載入與無重複請求** | **PASS** | 經 loadGroup() 修正，重複切換已看過的身分頁 0 API 呼叫，只有 RSC 請求。 |
| **6. 鍵盤導覽 (ArrowLeft/ArrowRight)** | **PASS** | 鍵盤操作 ←/→ 可在標籤列間切換且焦點跟隨正確。 |
| **7. 375px 寬度無水平溢出** | **PASS** | `SubNav` 的 button padding 縮減為 `px-3`，實測 375px 下 5 標籤剛好滿版不需橫捲。 |
| **8. 二軍過濾防護 (前輪 P0 回歸)** | **PASS** | `vizRows` 邏輯完好。實測二軍球員高捷，其守備價值卡正確隱藏，沒有取用二軍數據，且回歸測試通過。 |
| **9. 守位圖移除徹底性** | **PASS** | 項目中無 any `POS_COORD` / `posLabel` / `FieldPositionMap` 死程式碼及 orphan imports。多守位標記與表格完整保留。 |

---

## 3. 品質閘門 (Quality Gates) 自行驗證結果

*   **TypeScript 編編**: `npx tsc --noEmit` 通過 (clean)。
*   **Next.js 建置**: `npm run build:check` 成功編譯，靜態頁生成成功。
*   **React 單元測試**: `npm test` 共 103 項測試全數通過 (`103 passed, 0 failed`)。
*   **Python Ruff Linter**: `uv run ruff check` 通過 (clean)。
*   **Python Pytest 測試**: `uv run pytest` 共 357 項測試通過，1 項跳過 (`357 passed, 1 skipped`)。
*   **分支乾淨度**: `git diff main..HEAD` 顯示僅修改前端 `/players/[id]` 的 6 個程式與測試檔，未含 `docs/control-plane/**` 或 `docs/TASKS.md`。
*   **Commit 留痕**: commit 訊息均帶有：
    *   `Requested-by: ruan6047`
    *   `Planned-by: Claude Opus 4.8@Claude Code`
    *   `Implemented-by: Claude Opus 4.8@Claude Code`

---

## 4. 查核結論處置
本任務判定為 **✅通過** (APPROVE)。將進行 `--no-ff` 合併至 `main` 的操作，將 `deployment_status` 標註為 `🚀待部署`，等待需求方進一步指示。
後續重做守備圖之任務為 `UI-FIELD-DIAGRAM1`（於 Backlog 中）。
