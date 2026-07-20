# UX-PLAYER-FIELDVIZ1 球員守備呈現獨立查核報告

- **被審 SHA**：`4e671cf7bd55d47cc40104c3ae89231979340e37`
- **交付分支**：`ai/opus-4-8/UX-PLAYER-FIELDVIZ1`
- **審查結論**：✅ 審核通過（`APPROVE`）
- **Findings**：`P0=0`；`P1=0`；`P2=0`

---

## 🔍 核心稽核結果與證據（Findings & Evidence）

前次 iteration 1 提出的二軍資料滲透 P0 問題，已在 iteration 2 中完美解決，findings 全部歸零：

### 1. 成功排除二軍（`kind_code='D'`）守備數據滲入

- **修正機制**：
  引入 [fielding-metrics.ts:vizRows](file:///Users/ruanruan/Dev/cpbl-analytics/.claude/worktrees/ux-player-fieldviz1-execution/web/src/app/players/[id]/fielding-metrics.ts#L77-L82) 集中過濾資料。
  在二軍視角下（`isFarmView === true`），本季二軍數據將不被身分圖與價值卡使用，改以一軍生涯列（`careerRows`，本身只包含一軍資料）進行身分描述，且不渲染價值卡（因為一軍生涯列無 outs，二軍列不得評價）。
- **實測證據**：
  - 對純二軍投手 **李家明 (0000006954)** 進行實測：
    - 「本季」表格正常顯示二軍的投手守備 9 場。
    - 身分圖正確顯示一軍生涯的「投手 8 場」（outs 為 null 退回場數，未混入二軍數據）。
    - 價值卡被正確隱藏（`primaryRow` 為 null），完全排除了二軍。
    - 降級文案已修正為：「此範圍無守備局數資料（局數自 2018 年起重建）...」，更為準確貼切。
    
    ![李家明純二軍身分圖正常](file:///Users/ruanruan/.gemini/antigravity-cli/brain/06f27187-b089-44fd-8301-76ac1141e62e/screenshot_0000006954_李家明_二軍.png)

  - 對一二軍均有出賽的 **黃劼希 (0000006931)** 進行實測：
    - 在一軍視角下，本季一軍 6 場（32 outs，二壘 11 局）與 1 場（24 outs，三壘 8 局）的守備局數正確出現在身分圖上。
    - 價值卡正確針對一軍二壘手進行指標評價，顯示其 outs 及本人數值（雙殺參與 2.53, 守備機會 19.41, 守備率 0.957），且因為未達 100 局 (300 outs)，標示為「樣本不足以與聯盟對照」，無任何二軍數據干擾。
    
    ![黃劼希一軍守備正常](file:///Users/ruanruan/.gemini/antigravity-cli/brain/06f27187-b089-44fd-8301-76ac1141e62e/screenshot_0000006931_黃劼希_二軍.png)

### 2. 回歸測試保障

- 在 [fielding-metrics.test.ts](file:///Users/ruanruan/Dev/cpbl-analytics/.claude/worktrees/ux-player-fieldviz1-execution/web/src/app/players/[id]/fielding-metrics.test.ts) 中加入了 4 個 vizRows 單元測試。經實測若還原回缺陷版代碼，單元測試會直接報錯，保證了程式碼安全性。

### 3. 可及性與排版驗證

- SVG 結構包含正確的 `role="img"` 及 `aria-label`。
- 在 375px 視區下實測，`scrollWidth` 均為 375，無任何水平溢出。
- 本地編譯測試 `npm test`（91 passed，新增 4 個）、`tsc --noEmit`、`build:check`、`ruff check` 及 `pytest` 均全數通過。

---

獨立查核通過，核准進入受保護分支合併與生產部署流程。
