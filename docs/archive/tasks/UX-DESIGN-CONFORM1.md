# UX-DESIGN-CONFORM1 既有已完成 UI/UX 頁面 conformance 稽核與對齊〔T3；⚪設計系統／前端〕

> **狀態 📥Backlog（阻塞中）**：依賴 `UX-DESIGN-SYSTEM1` 產出 canonical 規格並經 Design Gate sign-off 後才可認領。由需求方 ruan6047 於 2026-07-24 指示：DESIGN-SYSTEM1 完成後，重新檢查已完成的 UI/UX 卡/頁面是否需修改以對齊統一規則。

- 需求：ruan6047　規劃：待指派　分支：`ai/<執行者>/UX-DESIGN-CONFORM1`
- 執行：待指派（本週 Claude）　查核：待指派（≠ 執行；跨家族或人工）
- Initiative：`INIT-PRODUCT-UX`
- spec 基線：`UX-DESIGN-SYSTEM1` 產出的 canonical UI/UX 規格（`docs/design/UI_UX_SYSTEM.md`）+ 其逐頁 conformance 差距清單
- DB：`db_scope: none`（前端）　部署：是（對齊修改會上線）　環境：production
- Design：**Design Gate = ruan6047**（修改清單與上線前人工審，依 [[ux-manual-review-before-ai]] 慣例）

## 目標與驗收

- [ ] 以 DESIGN-SYSTEM1 的 canonical 規格與差距清單為準，對**所有已完成／已上線的 UI/UX 卡涵蓋頁面**做 conformance 稽核（球員頁為 100% 基準）。
- [ ] 逐頁/逐卡產出判定：**Go（已符合）／Modify（需改）**＋偏離項＋嚴重度＋預估工作量。至少涵蓋已結案的頁面：players、team（UX-TEAM-FOCUS1）、leaderboard（UX-RANKINGS1）、game/賽況、home（UX-GAME-HOME1）、matchup、以及本批次完成的 umpire（UX-UMPIRE-SCOPE1）、team-split（UX-TEAM-SPLIT-SCOPE1）。
- [ ] **in-scope 的低風險偏離**（token、chip、active 標籤、圖表主題、mobileHide…）直接套對齊修改並上線；**大型或高風險重構**另切 scoped 後續卡，不塞進本卡。
- [ ] 修改不得改變各頁「一頁一問」的產品/IA 決策（那是 blueprint 範疇）；歷史能力零退化（年份選擇器/紀錄室/月曆保留）。
- [ ] `npm run build:check` 通過；上線前依 UX 慣例先開本地環境給需求方人工審，OK 後才交跨家族（非 Claude）或人工查核。

## 建議使用 skills（執行者以 `Skill` 工具 invoke）

- **`web-design-guidelines`**：逐頁對照規格/Web Interface Guidelines 做 conformance 稽核。
- **`design:design-critique`**：結構化評估各頁與基準的偏離。
- **`design:accessibility-review`**：對比/可及性回歸檢查（深色模式）。
- **`tailwind-patterns`**：套對齊修改時的 v4 token 用法。
- 次要：`frontend-design`、`dataviz`（圖表對齊）。

## 依賴與非目標

- **依賴**：`UX-DESIGN-SYSTEM1` 通過 + Design Gate sign-off。未滿足前不得認領（無 canonical 基準無法判 Go/Modify）。
- **非目標**：不重新定義設計規格（那是 SYSTEM1）；不做產品/IA 改動；大型頁面重寫外切 scoped 卡。

## Log

- 2026-07-24 register by Claude Opus 4.8（Coordinator，依 ruan6047 指示）；iteration 0。作為 UX-DESIGN-SYSTEM1 的既有頁對齊後續卡。
- 2026-07-25 claim by Claude Opus 4.8（依 ruan6047 指派）；iteration 1、🔨執行中。分支 `claude/ux-design-conformance-audit-1faa48` @ `.claude/worktrees/ux-design-system-phase-1-f092c0`。
- 2026-07-25 執行完成（Opus 4.8）：以球員頁為 100% 基準，聚焦稽核**新規則**（§3.5 ENTITY_LINK／§9.3 隊名連結／§4.3 導覽）在尚未被觸及頁的落實。逐頁 Go/Modify 完成。
  - **低風險對齊已套（commit `94e53e4`，5 檔）**：(1) `award-races`（/batters・/pitchers）#1 名字去 `text-accent` 紅字（唯一 red-at-rest 實體名）→ ENTITY_LINK＋`font-medium`；(2) games/賽況（`box-tabs` 打者/投手、`overview` MVP＋決勝、`page` 決勝/MVP）6 處 `PlayerLink` 覆寫 hover-only→ENTITY_LINK 預設（補常駐底線）；(3) `teams/[code]/parts` 純教練連結對齊 ENTITY_LINK。純視覺 idiom，零 IA/產品改動。
  - **Go（已符合，無改）**：/games 月曆（隊名純文字正確不連，整列已包 Link 避 nested <a>）、home、matchup-card、standings/records/venues/people（隊名/球員已連非紅字）。
  - **刻意外切**：裁判名連結 → `UX-UMPIRE-SCOPE1`（T4 territory）；bare `hover:underline` 整塊實體連結普及化 → 新開 `UX-ENTITY-LINKS2`（ruan6047 定案開卡、實作延後）。
  - **驗證**：`build:check` 全 11 路由 ✓、`npm test` 126 ✓；實測 live DOM 淺色（/batters award #1、/games/167 18 球員連結全 text-ink＋常駐底線、red-at-rest=0、MVP 16px bold）＋深色（球員名 #e8eef6 on #0a1626 高對比、底線 #24374f、零紅字、無對比回歸）。
  - **需求方本地人工審通過**（[[ux-manual-review-before-ai]]，2026-07-25：「密集底線可接受」）→ handoff 待跨家族查核。
