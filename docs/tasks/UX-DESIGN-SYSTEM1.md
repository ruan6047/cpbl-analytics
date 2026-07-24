# UX-DESIGN-SYSTEM1 全站 UI/UX 統一規則 codify（球員頁為基準）〔T3；⚪設計系統／文件〕

> **狀態 📥Backlog**：由需求方 ruan6047 於 2026-07-24 指示開卡。INIT-PRODUCT-UX 的視覺/元件層地基卡——把球員頁旗艦已落地的設計語言，codify 成全站可強制對齊的 canonical UI/UX 系統規格。

- 需求：ruan6047　規劃：待指派　分支：`ai/<執行者>/UX-DESIGN-SYSTEM1`
- 執行：待指派（本週 Claude）　查核：待指派（≠ 執行；跨家族或人工）
- Initiative：`INIT-PRODUCT-UX`
- spec 基線（既有事實，須對齊不得推翻）：
  - 產品/IA 層：[`../PRODUCT_UX_BLUEPRINT.md`](../PRODUCT_UX_BLUEPRINT.md) v0.2（一頁一問、兩層資訊架構、freshness/availability）
  - **視覺基準（本卡參考依據）**：球員個人頁 [`web/src/app/players/[id]/page.tsx`](../../web/src/app/players/[id]/page.tsx)（P1/P2 旗艦，已完成）
  - 既有 token 來源：[`web/src/app/globals.css`](../../web/src/app/globals.css)、[`web/src/lib/chart-theme.ts`](../../web/src/lib/chart-theme.ts)、`web/src/components/theme-toggle.tsx`
- DB：`db_scope: none`（唯讀 web 原始碼 + docs，產出規格文件）　部署：否（純文件；頁面對齊由後續卡執行）　環境：—
- Design：**Design Gate = ruan6047**（產出的 canonical 規格須經需求方 sign-off 才成為全站事實）

## 背景與問題

專案已有產品/IA 藍圖，但**缺一份視覺/元件層的單一事實來源**。球員頁旗艦已 de-facto 定義了設計語言（日間 Navy+白、active 標籤 `bg-ink+text-paper`、圖表色走 `useChartTheme`、預設淺色不跟系統、排行精簡欄+完整欄切換、隊名併入名字隊徽、守位/角色 chip、手機 mobileHide 留主指標…），但散在 globals.css / chart-theme.ts / 各頁 JSX，未被 codify，導致 P3 各頁改版缺可對齊的強制規格、跨卡容易漂移。

## 目標與驗收

- [ ] 以球員頁為參考依據，逆向抽出並 codify canonical UI/UX 系統規格（建議 `docs/design/UI_UX_SYSTEM.md`），至少涵蓋：
  - **設計 token**：色票（Navy+白/ink/paper）、字級與行高、間距尺標、圓角、陰影、border——對齊 globals.css 既有變數，缺口補齊。
  - **深色模式約定**：預設淺色不跟系統；active 標籤 `bg-ink+text-paper`（禁 text-white 白底白字）；圖表色一律 `useChartTheme`（見 [[dark-mode-conventions]]）。
  - **元件模式與狀態**：卡片、chip、tab/segment、表格、Leaderboard（精簡欄 vs 完整欄切換、隊徽併名、mobileHide 規則，見 [[rankings-column-reduction]]）、empty/loading/error 狀態。
  - **圖表規範**：色盤、座標軸、tooltip、深淺色主題來源。
  - **響應式**：斷點、手機保留/隱藏欄位原則。
- [ ] 產出**逐頁 conformance 差距清單**（players 為 100% 基準；其餘頁面列出偏離項與嚴重度），供後續各頁對齊卡消費。
- [ ] 規格為**描述現況 + 明確化**，不得推翻球員頁已定案語言；與 PRODUCT_UX_BLUEPRINT 產品層不衝突。
- [ ] 需求方 ruan6047 Design Gate sign-off。

## 執行前對齊 Checkpoint（實作前多討論，避免落差）

> 需求方要求：本規格是全站 canonical，**實作前先對齊方向**，不要整份做完才發現落差。

1. **先交「設計決策 brief」，不要直接產完整規格**。執行者先盤點球員頁 + `globals.css`/`chart-theme.ts`，產出：
   - 範圍與方法 outline：打算 codify 哪些 token 類別、元件、狀態。
   - **可被 grill 的決策清單**：逐項列「**決策／理由／考慮過的替代方案／open questions／邊界風險**」。至少涵蓋爭議點：token 尺標粒度、色彩語意命名、深色模式在圖表的處理、Leaderboard 精簡欄 vs 完整欄的取捨標準、mobileHide 準則、與 blueprint 產品層的邊界。
2. **brief 先 handoff 為 checkpoint**（不一次做到底）；交需求方 ruan6047 以 **`/grilling`** 壓測討論、對齊方向。
3. **方向 sign-off 後**才展開完整 `docs/design/UI_UX_SYSTEM.md`。
4. grilling 由**需求方在自己的 session** 觸發質問這份 brief——**執行者不自跑 grilling**（無人可質問；自我批判用 `design:design-critique`）。

## 建議使用 skills（執行者以 `Skill` 工具 invoke）

- **`design:design-system`**：主工作流——audit 現況 → document canonical 規格 → 定義擴充規則。
- **`tailwind-patterns`**：Tailwind v4 CSS-first 設計 token 架構，對齊並整理 `globals.css` 變數。
- **`frontend-design`**：色票／字級／間距／圓角的設計原則判準（原則非硬值）。
- **`web-design-guidelines`** + **`design:accessibility-review`**：元件狀態與深色模式對比稽核（WCAG，呼應「禁 text-white 白底白字」）。
- **`dataviz`**：圖表規範段（色盤／座標軸／tooltip），對齊 `chart-theme.ts` 的 `useChartTheme`。
- 次要：`react-patterns`／`nextjs-best-practices`（元件模式文件化）。
- **不使用** `shadcn`：專案未採 shadcn/ui（Tailwind + recharts 手刻），避免引入不相干元件庫慣例。

## 依賴、序列與非目標

- **與進行中前端卡的關係**：`UX-UMPIRE-SCOPE1`、`UX-TEAM-SPLIT-SCOPE1` 已在執行；在本卡規格產出前，兩者一律**以球員頁 + globals.css/chart-theme 為 pattern 來源**對齊（同一事實來源），並於各自人工審核關檢查一致性。本卡產出後，未來 INIT-PRODUCT-UX 各頁卡須引用本規格；既有頁面對齊由後續卡 `UX-DESIGN-CONFORM1`（重新稽核已完成 UI/UX 頁面是否需修改）處理。
- **非目標**：不重構任何頁面、不改 globals.css/元件程式碼（那是後續對齊卡）；不新增 API/DB；不涉及產品/IA 決策（那是 blueprint 的範疇）。

## Log

- 2026-07-24 register by Claude Opus 4.8（Coordinator，依 ruan6047 指示）；iteration 0。需求方指定球員個人頁為視覺基準。
