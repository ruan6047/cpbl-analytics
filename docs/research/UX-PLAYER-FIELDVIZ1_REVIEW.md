# UX-PLAYER-FIELDVIZ1 球員守備呈現獨立查核報告

- **被審 SHA**：`43e674e1d51840e5046683d1e6db06e8b187289d`
- **交付分支**：`ai/opus-4-8/UX-PLAYER-FIELDVIZ1`
- **審查結論**：❌ 退回修正（`REQUEST_CHANGES`）
- **Findings**：`P0=1`；`P1=0`；`P2=0`

---

## 🚨 阻塞缺陷（Blockers）

### P0：二軍守備數據（`kind_code='D'`）錯誤進入身分圖與價值卡元件

- **Severity**：High
- **檔案與行號**：
  - [web/src/app/players/[id]/page.tsx](file:///Users/ruanruan/Dev/cpbl-analytics/.claude/worktrees/ux-player-fieldviz1-execution/web/src/app/players/[id]/page.tsx#L155-L160)
  - [web/src/app/players/[id]/fielding.tsx](file:///Users/ruanruan/Dev/cpbl-analytics/.claude/worktrees/ux-player-fieldviz1-execution/web/src/app/players/[id]/fielding.tsx#L198-L202)
- **證據與截圖**：
  在二軍視角下（`seasonKind === "D"`），二軍的本季守備數據被設給了 `fielding`  並傳入 `FieldingSection`。
  `FieldingSection` 內部未對二軍進行過濾或回退：
  ```typescript
  // 身分圖與價值卡以本季為準；退役／2018 前退回生涯列做身分描述。
  const mapRows = seasonRows.length > 0 ? seasonRows : careerRows;
  const primary = primaryPos(mapRows.map((r) => ({ pos: String(r.pos), g: numOf(r.g) })));
  const primaryRow = seasonRows.find((r) => String(r.pos) === primary) ?? null;
  ```
  這使得：
  1. **身分圖（FieldPositionMap）** 錯誤地將黃劼希的二軍守備「三壘手 8 場」、「二壘手 5 場」、「游擊手 3 場」標注在球場示意圖上。
  2. **價值卡（FieldingValueCard）** 錯誤地對二軍主守位「三壘手」進行守備評價。且因為二軍沒有 `outs`（局數為 null），導致文案顯示為不合邏輯的 `"2018 年以前無守備局數資料，無法計算每 9 局率..."`（實則該選手為 2026 年現役二軍，非 2018 年前退役球員）。

  ![黃劼希二軍守備圖表異常](file:///Users/ruanruan/.gemini/antigravity-cli/brain/06f27187-b089-44fd-8301-76ac1141e62e/screenshot_0000006931_黃劼希_二軍.png)

- **可重現步驟**：
  1. 啟動本機 API (:4015) 與前端 Next.js 伺服器 (:3015)
  2. 造訪二軍選手黃劼希的選手頁生涯分頁：`http://localhost:3015/players/0000006931?sec=career`
  3. 觀察身分圖和價值卡的渲染結果。
- **預期行為**：
  - 二軍守備數據不得進入身分圖和價值卡。
  - 當 `seasonKind === "D"` 時，身分圖與價值卡應回退至僅使用一軍生涯 `careerRows` 進行渲染，或是在此狀態下隱藏這兩個元件，不應把二軍的場數和守位繪製到示意圖上，也不應對二軍守位下價值評價。
- **修正方向**：
  - 建議將當前 `seasonKind` (或 `kind_code`) 作為 prop 傳遞給 `FieldingSection`。
  - 在 `FieldingSection` 內部，若為二軍（`seasonKind === "D"`），則在身分圖與價值卡的資料來源中將 `seasonRows` 當成空陣列（回退到 `careerRows`）或是直接在此狀態下隱藏這兩個元件。

---

## 🔍 其他非阻塞稽核結果（Carry-forwards / Passes）

除上述二軍資料滲透 P0 問題外，其餘查核項目皆順利通過：

1. **API 僅唯讀查詢**：擴充 `/api/v1/players/{id}/fielding` 僅加入 read-only 的 SQL JOIN。符合 `db_scope: read`。
2. **psycopg 參數化**：`players.py` 內所有 SQL 查詢皆正確參數化，無字串拼接或 SQL 注入風險。
3. **分母與合格門檻**：率值計算以 `outs` 為唯一分母，2018 年前 `outs` 為空時不計算率值，低於 100 局（300 outs）則不顯示聯盟中位數與對照值，完全合規。
4. **守位分流**：外野只列 A/9，內野呈現 DP/9, TC/9 與守備率，一壘只列計數不做評價，投手不予評價，捕手不做重複資料，完全合規。
5. **不混資料**：聯盟數據查詢按年、按守位、按 `kind_code` 分開，完全不混淆。
6. **身分圖非價值暗示**：尺寸和顏色與守備好壞無關，僅對主守位與一般守位區分（fill-accent vs fill-muted），不暗示好壞。
7. **可及性 (Accessibility)**：SVG 具備正確的 `role="img"` 及詳細的 `aria-label` 描述。
8. **375px 無溢出**：Playwright 實際測量 width=375 下 `document.body.scrollWidth` 與 `clientWidth` 均為 375，無水平溢出。
9. **驗證全綠**：本機 `npm test`（87 passed）、`tsc --noEmit`、`build:check`、`ruff check`、`pytest` 均全數通過。

請執行者在原分支修正該二軍資料滲透問題後，重新交查核。
