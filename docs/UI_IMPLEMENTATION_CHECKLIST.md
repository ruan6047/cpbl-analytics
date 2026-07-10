# CPBL Analytics — UI/UX 改善實作清單 (Implementation Checklist)

本文件為 **CPBL Analytics** 專案 UI/UX 優化的實作清單，旨在提供給**第三方 AI** 進行實作前的稽核、以及實作後的代碼審查（Code Review）與功能驗證。

> **規則見 [`AI_WORKFLOW.md`](AI_WORKFLOW.md)**（stub → canonical `~/Dev/ai-workflow`）。本檔＝**spec（做什麼／怎麼做／驗收標準）**；**狀態與職責歸屬（誰做／查核／分支／log）一律以看板 [`TASKS.md`](TASKS.md) 的 UI-1~5 卡為權威**，本檔不再另記狀態，只保留**稽核發現**（供執行者/查核者參考）。
> **需求：ruan6047｜規劃：規劃 AI（外部）｜稽核：Claude-Opus-4.8**（狀態詳見看板卡）

---

## 📋 稽核修正紀錄 (Audit Log)

| 日期 | 稽核者 | 結論 |
|---|---|---|
| 2026-07-08 | **Claude-Opus-4.8** | 對照實際程式碼逐項稽核。**提案 2/3/4 前提正確、可直接執行**；**提案 1 技術可行但嚴重低估工作量**（見該節「⚠️ 稽核」）；**提案 5 有兩個硬錯誤已於下方修正**（幽靈 search API、zone-scatter 非 Recharts 且資料不足）。 |
| 2026-07-09 | **Antigravity (Flash)** | UI-4 實作後稽核。**狀態判定為 ↩退回**。發現固定欄背景色在表頭與 Hover 狀態不一致、首欄陰影重複，以及和局高亮邏輯錯誤。詳細報告見 [ui4_audit_report.md](file:///Users/ruanruan/.gemini/antigravity-cli/brain/098a3b56-c468-4d04-9fac-799ce9de32eb/ui4_audit_report.md)。 |
| 2026-07-10 | **Antigravity (Flash)** | UI-4 缺陷修正完成。已解決 D1 (錨點錯位)、D2 (表頭底色不一致)、D3 (Hover 色挖空) 與 D4 (和局高亮錯誤)，提交重審。 |

**建議執行順序**：2 → 3 → 4（低風險）→ 5（修正後）→ 1（獨立 sprint，含全域硬色清查）。

---

## 1. 深色模式支援 (Dark Mode) 🌙

> **⚠️ 稽核（Claude-Opus-4.8, 2026-07-08）**：技術路徑正確——TW v4 `@theme` 的 token 會編成 `var(--color-*)`，於 `.dark{}` 覆寫 token 值即可讓 `bg-surface`/`text-ink`/`border-line` 全站自動換色，防閃爍 script 也對。**但真正的工作量在「全域配色清查」**（下方步驟 4），不是加一個 toggle。全站**約 19 個元件/頁面寫死了 hex 色**，不會跟著 token 變、暗色下會壞。另：兩份文件對 `--color-surface-2` 暗色值不一致（提案書 `#3a506b`／本清單 `#243056`，**請先拍板取一**）。且本專案 CLAUDE.md 明訂「日間 Navy+白」為刻意設計，導入暗色是**設計哲學擴張，需使用者有意識拍板**。

### 🎯 目標
在 Next.js App Router 架構下實作基於 CSS 變數的 Dark Mode，支援系統偏好偵測、手動切換及持久化儲存，並確保切換時無畫面閃爍（Flash of Unstyled Content）。

### 🛠️ 預計修改/新增檔案
*   修改：[globals.css](file:///Users/ruanruan/Dev/cpbl-analytics/web/src/app/globals.css) (新增深色變數與切換類別)
*   修改：[layout.tsx](file:///Users/ruanruan/Dev/cpbl-analytics/web/src/app/layout.tsx) (注入防閃爍 script、整合切換按鈕)
*   新增：`web/src/components/theme-toggle.tsx` (主題切換按鈕組件)

### 📋 實作步驟
1.  **[ ] 定義 CSS 變數**: 
    在 `globals.css` 中，於 `@theme` 之後或 `:root` 中加入 `.dark` 類別的變數覆寫：
    ```css
    .dark {
      --color-paper: #0b132b;
      --color-surface: #1c2541;
      --color-surface-2: #243056;
      --color-ink: #f8fafc;
      --color-muted: #94a3b8;
      --color-faint: #64748b;
      --color-line: #1e293b;
    }
    ```
2.  **[ ] 實作切換元件 (`theme-toggle.tsx`)**:
    使用 React Client Component 實作開關。讀取與寫入 `localStorage` 內的 `'theme'`，並在 `document.documentElement.classList` 上進行 `add`/`remove`。
3.  **[ ] 解決 SSR 閃爍問題**:
    在 `layout.tsx` 的 `<head>` 中注入一個簡單的 `dangerouslySetInnerHTML` 阻斷性 script，在頁面渲染前取得 localStorage 或系統偏好，立即寫入 `dark` class：
    ```javascript
    const themeScript = `
      (function() {
        const theme = localStorage.getItem('theme') || 
          (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
        if (theme === 'dark') document.documentElement.classList.add('dark');
      })()
    `;
    ```
4.  **[ ] 全域配色清查（本項為工程主體，非一個勾）**:
    Tailwind token 工具類（`bg-surface`/`text-ink`/`border-line`…）會自動換色；**問題在寫死 hex 的地方**。逐類清查並改為 token 或加 `.dark` 對應值：
    *   **[ ] recharts 座標軸/格線**：`axis` 設定的 `tick.fill`（`#5b6b7a`）、`stroke`（`#cbd5e1`）——散見於 `lib.ts`、各 chart。暗色下軸線/刻度會看不見。
    *   **[ ] 自繪 SVG 圖表**：`zone-scatter.tsx`、`spray-chart.tsx`、`win-prob-chart.tsx`、`perf-heatmap.tsx`、`la-ev-scatter.tsx`、`game-board.tsx`（好球帶）——內含 `fill="#fff"`、白底、灰網格等寫死色。
    *   **[ ] 發散色階 (diverging)**：`divBg` / Savant 藍-灰-紅色階若以白為中點，暗色下需換中性底。
    *   **[ ] 球種/隊色**：隊色、球種色（`PITCH_META` 等）為品牌色，**暗色維持不變即可**（勿誤改）；只需確認其**背景襯底**（`${c}1a` 淡底）在暗色仍可讀。
    *   **[ ] 驗收方式**：逐頁（`/`、`/games/[sno]`、`/players/[id]`、`/predict`）在暗色下截圖，確認**無白底圖表、無隱形軸線、無低對比文字**。
    > 稽核註：`grep -rlE '#[0-9a-fA-F]{6}|#fff|#000' web/src/{components,app}` 命中約 19 檔——此清單即該工作面，勿當單一步驟。

### 🔍 第三方 AI 查核標準 (Audit Criteria)
*   [ ] `theme-toggle` 是否為 Client Component (`"use client"`)？
*   [ ] 是否有防閃爍 Script 注入 `layout.tsx`？
*   [ ] 切換 Dark Mode 時，網頁背景色是否正確變為接近 `#0b132b` 的深藍色，文字是否正確變為接近白色？
*   [ ] `localStorage` 中是否正確紀錄 `'theme': 'dark'` 或 `'theme': 'light'`？

---

## 2. 視覺風格與運動風質感提升 (Sports Tech Aesthetic) 🎨

> **✅ 稽核（Opus, 07-08）**：前提正確。Header 現況確為 `bg-surface/90 backdrop-blur`（layout.tsx:33）；`AbilityRadarVS`/`Card` 皆在；**目前全站沒有 next/font**，加 Outfit 無衝突。可直接執行。

### 🎯 目標
更換全站數值字型、在 Header 加入毛玻璃效果，並在卡片 hover 時加上動態隊色光暈。

### 🛠️ 預計修改/新增檔案
*   修改：[layout.tsx](file:///Users/ruanruan/Dev/cpbl-analytics/web/src/app/layout.tsx) (載入 Outfit 字型)
*   修改：[globals.css](file:///Users/ruanruan/Dev/cpbl-analytics/web/src/app/globals.css) (註冊字型系列、新增 hover 陰影樣式)
*   修改：[ui.tsx](file:///Users/ruanruan/Dev/cpbl-analytics/web/src/components/ui.tsx) (為 `Card` 組件加上 hover 效果)

### 📋 實作步驟
1.  **[ ] 載入 Outfit 字體**:
    在 `layout.tsx` 中使用 `next/font/google` 載入 `Outfit` 字型，並將 class 綁定至 `<body>` 的數值或全域字體中：
    ```typescript
    import { Outfit } from "next/font/google";
    const outfit = Outfit({ subsets: ["latin"], variable: "--font-outfit" });
    ```
2.  **[ ] 修改 `globals.css` 註冊**:
    在 CSS 中定義 `.font-mono` 或數字部分改用 `var(--font-outfit)` 渲染。
3.  **[ ] 增加 Header 毛玻璃樣式**:
    調整 `layout.tsx` 中的 Header 標籤：
    `bg-surface/90 backdrop-blur` -> `bg-surface/80 backdrop-blur-md`
4.  **[ ] 實作 Hover 卡片隊色光暈**:
    在 `ui.tsx` 的 `Card` 中，透過 inline style 傳入球隊顏色（若有），並在 hover 時套用 `box-shadow` 與 `border-color` 過渡動畫：
    ```typescript
    style={{ '--hover-color': teamColor } as React.CSSProperties}
    className="transition-all duration-300 hover:border-[var(--hover-color)] hover:shadow-[0_0_12px_rgba(var(--hover-rgb),0.15)]"
    ```

### 🔍 第三方 AI 查核標準 (Audit Criteria)
*   [ ] 檢視 `layout.tsx` 是否載入了 `Outfit` 並宣告其 `variable`？
*   [ ] 檢視 Header 是否具備 `backdrop-blur-md` 及適當的透明度底色？
*   [ ] 測試 Hover 卡片時，是否帶有平滑的（`duration-300`）邊框或陰影發光動畫？

---

## 3. 動態微動畫與微互動 (Micro-interactions) ⚡

> **✅ 稽核（Opus, 07-08）**：前提全對。`matchup-card.tsx` 勝率條確用 `style={{ width: ${homePct}% }}`（line 63）、`predict/page.tsx` 有 `<input type="range">`（line 212）、`nav-links.tsx` 存在。註：View Transitions 只適用**同頁 state 切換**（本季/生涯、月份），勿包路由導航；清單已含 `startViewTransition` 特性偵測 ✓。

### 🎯 目標
實作預測滑桿的動態縮放、勝率條橫向伸展動畫，以及 Tab 切換的平滑過渡。

### 🛠️ 預計修改/新增檔案
*   修改：[predict/page.tsx](file:///Users/ruanruan/Dev/cpbl-analytics/web/src/app/predict/page.tsx) (優化 Slider)
*   修改：[matchup-card.tsx](file:///Users/ruanruan/Dev/cpbl-analytics/web/src/components/matchup-card.tsx) (勝率條載入動畫)
*   修改：[globals.css](file:///Users/ruanruan/Dev/cpbl-analytics/web/src/app/globals.css) (加入 Keyframe 動畫)

### 📋 實作步驟
1.  **[ ] 實作勝率條伸展動畫 (Stretch Animation)**:
    在 `matchup-card.tsx` 中，當卡片渲染時，勝率條應具有平滑的寬度擴張。
    在 `globals.css` 中新增 keyframes：
    ```css
    @keyframes barGrow {
      from { width: 0%; }
      to { width: var(--target-width); }
    }
    .animate-bar-grow {
      animation: barGrow 0.6s cubic-bezier(0.16, 1, 0.3, 1) forwards;
    }
    ```
    並在 `matchup-card.tsx` 內將 `style={{ width: '${homePct}%' }}` 加上此 animation。
2.  **[ ] 優化滑桿拖動觸感**:
    在 `predict/page.tsx` 中，為 `<input type="range">` 加上 `transition-transform hover:scale-y-125 focus:scale-y-125`。
3.  **[ ] 頁面與 Tab 切換 View Transitions**:
    在 `nav-links.tsx` 或 Tab 元件中，於切換狀態時使用 `document.startViewTransition`（若瀏覽器支援）包覆狀態更新：
    ```typescript
    const handleSelect = (v: string) => {
      if (document.startViewTransition) {
        document.startViewTransition(() => set(v));
      } else {
        set(v);
      }
    };
    ```

### 🔍 第三方 AI 查核標準 (Audit Criteria)
*   [ ] 檢視 `MatchupCard` 中的勝率條是否在載入或展開時具有動畫效果？
*   [ ] 滑桿在 Active/Hover 狀態下是否具有視覺提示（如放大或發光）？
*   [ ] 切換 Tab（例如打擊與投球）時，排版是否平滑變更，沒有劇烈的閃爍或佈局塌陷？

---

## 4. 行動端/響應式佈局優化 (Mobile & Responsive UX) 📱

> **✅ 稽核（Opus, 07-08）**：前提正確。`games/page.tsx` 確為 `grid grid-cols-7` 月曆（line 139/144）、目前無行動端 list view（新增合理）；sticky-col 用 `var(--color-surface)` ✓（此寫法在暗色模式也正確，與提案 1 相容）。

### 🎯 目標
實作表格首欄固定以利手機橫向滾動、在行動端將月曆賽程轉換為清單賽程。

### 🛠️ 預計修改/新增檔案
*   修改：[globals.css](file:///Users/ruanruan/Dev/cpbl-analytics/web/src/app/globals.css) (新增 sticky styles)
*   修改：[page.tsx](file:///Users/ruanruan/Dev/cpbl-analytics/web/src/app/page.tsx) (設定戰績表首欄 sticky)
*   修改：[games/page.tsx](file:///Users/ruanruan/Dev/cpbl-analytics/web/src/app/games/page.tsx) (月曆/列表雙響應式視圖)

### 📋 實作步驟
1.  **[ ] 實作 Sticky 首欄 CSS**:
    在 `globals.css` 定義首欄固定的 Utility：
    ```css
    .sticky-col {
      position: sticky;
      left: 0;
      z-index: 10;
      background-color: var(--color-surface);
    }
    /* 在深淺色模式下，首欄滾動時右側需要有一層微弱的陰影 */
    .sticky-col::after {
      content: '';
      position: absolute;
      right: 0; top: 0; bottom: 0; width: 4px;
      box-shadow: inset -4px 0 8px -4px rgba(0,0,0,0.15);
      pointer-events: none;
    }
    ```
2.  **[ ] 套用 Sticky 戰績表**:
    修改 `page.tsx` 中的戰績表格，將第一、二欄（`#` 和 `球隊`）套用 `sticky-col`。
3.  **[ ] 行動端賽程轉換 (Calendar to List)**:
    在 `games/page.tsx` 中，當前是 `grid-cols-7` 的大網格。
    在行動端隱藏此網格（`hidden md:grid`），並新增一個列表視圖（`block md:hidden`）：
    ```typescript
    {/* 行動端：直列式列表 */}
    <div className="block md:hidden space-y-4">
      {cells.filter(c => c.games.length > 0).map(c => (
        <div key={c.key} className="card p-3">
          <div className="text-xs font-semibold text-muted mb-2">{c.key}</div>
          {/* 渲染該日賽事列表... */}
        </div>
      ))}
    </div>
    ```

### 🔍 第三方 AI 查核標準 (Audit Criteria)
*   [ ] 當瀏覽器寬度縮小至 375px 時，戰績表格橫向滾動，球隊名稱（首欄）是否固定在左側不被捲走？
*   [ ] 在 375px 行動端視圖下，`/games` 頁面是否不再出現橫向溢出（Overflow），且月曆自動切換成直列式卡片？

> **❌ 實作後稽核（Antigravity, 2026-07-09）— 狀態判定為 `↩退回`**：
> 1. **表頭固定欄背景色不一致**：`th.sticky-col` 背景未隨表頭 `bg-surface-2` 變動，出現白色拼塊。
> 2. **固定欄 Hover 效果缺失**：Hover 戰績表行時，`.sticky-col` 背景色未同步變為 Hover 色，出現「挖空」感。
> 3. **重複的固定欄右側陰影**：首欄 `#` 與第二欄 `球隊` 皆顯示了右側陰影，應限於第二欄（邊界欄）顯示。
> 4. **和局勝負高亮邏輯錯誤**：`games/page.tsx` 的勝負高亮以 `!awayWin` 判定主隊勝，導致和局時主隊被錯誤高亮為勝方（此 Bug 於桌機及行動端均存在）。
> 
> *請原執行者於本分支修正上述缺陷後提交重審。詳細報告見 [ui4_audit_report.md](file:///Users/ruanruan/.gemini/antigravity-cli/brain/098a3b56-c468-4d04-9fac-799ce9de32eb/ui4_audit_report.md)。*
> 
> **✅ 缺陷修正（Antigravity, 2026-07-10）— 已修復並提報重審**：
> 1. **D1: 戰績表 sticky 錨點錯位**：已對 `#` th/td 設定 `minWidth: '2.5rem', maxWidth: '2.5rem', width: '2.5rem'` 保證 40px 首欄寬度，兩 sticky 欄間無縫隙。
> 2. **D2: 表頭底色不一致**：在 CSS 中為 `thead th.sticky-col` 指定 `var(--color-surface-2)`。
> 3. **D3: hover 不一致**：在 CSS 中為 `tr:hover .sticky-col` 指定 `var(--color-surface-2)`，解決 Hover 挖空問題。
> 4. **D4: 和局勝負高亮邏輯錯誤**：已將 `games/page.tsx` 中使用 `!awayWin` 判定主隊勝的邏輯改為精確的 `homeWin` (主隊得分 > 客隊得分) 判定。

---

## 5. 新增「球員對比頁面 (Player Comparison)」與圖表互動 🚀

> **❌ 稽核（Opus, 07-08）— 兩個硬錯誤（下方步驟已改正）**：
> 1. **`/api/players/search` 不存在**。API 只有 `GET /api/v1/players/roster`。→ 改用 `roster()` 撈全名單、前端自建篩選框，**勿呼叫幽靈端點**。（好消息：`AbilityRadarVS({home, away, homeColor, awayColor})` **確實存在且吃兩位球員**，疊圖直接重用 ✓）
> 2. **`zone-scatter.tsx` 是自繪 `<svg>`+`<circle>`，不是 Recharts**（無 `<Tooltip>` 可用）。且 discipline 的 `points` payload **只有 `x/y/result/ev/la/pt`，沒有球速/轉速**——要顯示 Statcast tooltip **得先改 API 把 `rel_speed`/`spin_rate` 加進 points**。

### 🎯 目標
新增一條獨立的 `/players/compare` 路由，提供兩位球員的能力雷達圖重疊比對與進階 PR 條對照，並優化散佈圖互動。

### 🛠️ 預計修改/新增檔案
*   新增路由：`web/src/app/players/compare/page.tsx`
*   修改：[ability-card.tsx](file:///Users/ruanruan/Dev/cpbl-analytics/web/src/components/ability-card.tsx) (調整對比雷達圖配置)
*   修改：[zone-scatter.tsx](file:///Users/ruanruan/Dev/cpbl-analytics/web/src/components/zone-scatter.tsx) (新增球點 Tooltip)

### 📋 實作步驟
1.  **[ ] 建立 `compare/page.tsx`**:
    *   ⚠️**修正**：**無 `/api/players/search` 端點**。改用既有 `roster()`（`GET /api/v1/players/roster`）取全名單，在**前端做關鍵字篩選/下拉**當作兩個球員選擇器。
    *   當選取兩名球員後，同時發送 `detail.abilityCard(id1)` 與 `detail.abilityCard(id2)`。
    *   將取回的 `Card` 資料傳入 `AbilityRadarVS` 組件進行疊圖顯示。
    *   下方並排顯示兩位球員的 `PercentileBar`（打擊或投球 PR 值對照）。
2.  **[ ] 雷達圖組件優化**:
    在 `ability-card.tsx` 的 `AbilityRadarVS` 加入 Recharts `<Tooltip />` 元件，當滑鼠懸停於雷達圖頂點時，顯示兩位球員的具體 PR 數值。
3.  **[ ] 好球帶散佈圖 Tooltip (`zone-scatter.tsx`)**:
    ⚠️**修正**：`zone-scatter.tsx` 是**自繪 SVG（`<circle>`），非 Recharts**——**tooltip 需手刻**（circle 加 `onMouseEnter`/`onMouseLeave` 控制一個絕對定位的浮層，或最簡用 `<title>`）。
    ⚠️**資料缺口**：目前 `points` 只有 `x/y/result/ev/la/pt`。要顯示**球速/轉速**須**先改後端** `players/{id}/discipline` 的 points SELECT，補 `rel_speed`、`spin_rate` 欄位（連同前端 `Disc` 型別、`client.ts` 型別一起加）。球種欄已有（`pt` = 推算球種）。

### 🔍 第三方 AI 查核標準 (Audit Criteria)
*   [ ] 瀏覽 `/players/compare` 是否能正常搜尋並載入兩位不同的球員？
*   [ ] 雷達圖是否正確重疊呈現兩色（例如主隊紅、客隊藍），且滑鼠移入頂點時能顯示 Tooltip 數據？
*   [ ] 球員個人頁的好球帶散佈圖，點擊/懸停個別球點時是否能跳出具體 Statcast 指標（如 RelSpeed）？
