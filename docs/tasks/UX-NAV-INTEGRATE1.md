# UX-NAV-INTEGRATE1 全站多軸導引欄整合重構〔T2；🟦前端／重構〕

> **狀態 📥 提案草稿（PROPOSAL，待 Coordinator 註冊）**：由 UX-DESIGN-SYSTEM1 執行者於 2026-07-24 依需求方 ruan6047 對 `UI_UX_SYSTEM §4.3` 定案產出。**取代**先前分頁草稿（standings/rankings 各卡收斂為本傘型卡）。
> **本檔僅 spec，未執行、未註冊**——需 Coordinator 依 CONTROL_PLANE_CONTRACT 決定是否登錄 `docs/TASKS.md` 並排程/分階。執行者不自行註冊 ledger。

- 需求：ruan6047　規劃：待指派　分支：`ai/<執行者>/UX-NAV-INTEGRATE1`
- 執行：待指派　查核：待指派（≠ 執行；跨家族或人工）
- Initiative：`INIT-PRODUCT-UX`
- 依據 spec：[`../design/UI_UX_SYSTEM.md`](../design/UI_UX_SYSTEM.md) §4.3（A2/B1/C/D2 + 全站樣式與 pages 表）、§4.4、§9.3/§9.6
- DB：`db_scope: none`　部署：**是**（動前端元件，需 build + 上線）　環境：web
- Design：**Design Gate = ruan6047**（§4.3 方向已 sign-off 2026-07-24；各頁成品仍須 UI 審）

## 背景與問題

多數清單/排行/賽況頁**共用 `kind（一/二軍）＋ year（年度）` 基底 ＋ 各自主軸**，但現況**散置成多條 nav 分列、且部分頁把內容垂直堆疊**，一致性差、閱讀不易（見 `UI_UX_CONFORMANCE.md`）：

| 頁 | 現況痛點 |
|---|---|
| `/standings` | 層級/賽季階段/年度三軸散置＋孤立年度下拉 |
| `/batters`・`/pitchers` | `RankRoleTabs`＋`LevelYearNav` 兩列，且 `AwardRaces`(獎項排行榜) **垂直堆疊在** `Leaderboard`(完整清單) 上→難讀 |
| `/games` | 一軍/二軍＋年度（**手刻、未用 `LevelYearNav`**）、隊伍篩選 chips、月份 stepper 三列分置 |

`UI_UX_SYSTEM §4.3` 已定案以**現有積木**（`StickyNavBar` 殼＋`HierarchicalTabs`/`ContextSwitcher`/`YearSelect`/`LevelYearNav`/隊徽 chip）收斂成**一體式多軸導引欄**，比照球員頁 `PlayerNavigation`。**非發明新元件、不建 `AxisNav`**。

## 目標與驗收（分階，可各自獨立 PR/commit）

### Phase 0 — 基底
- [ ] 抽 `StickyNavBar` 殼：球員頁 `PlayerNavigation` 的 sticky 定位（`ResizeObserver` 量 header 高＋`sticky z-20 backdrop-blur bg-paper/95 border-b`）→ 可重用；球員頁改用後行為不變（無 CLS）。
- [ ] 推廣 `LevelYearNav`（kind＋year）：**standings、games 改用共用 `LevelYearNav` 消滅手刻**（現 batters/pitchers 已用）。驗收：kind＋year 控制全站同一元件。

### Phase 1 — standings（§4.3 A2/B1/C/D2）
- [ ] `seg`→單層 tablist（主分頁）；`kind`＋`year`→右側 controls（`LevelYearNav`）；一列呈現。
- [ ] **動態 seg**：`segsFor(kind)`——二軍無上下半季（[[postseason-format-rules]]），僅「全年/季後賽」；當前 seg 失效 fallback 回全年（照抄 `viewsFor`）。
- [ ] B1 窄螢幕堆疊＋native select；URL `kind`/`seg`/`year` 無回歸（含 `seg=3` 季後強制邏輯）。

### Phase 2 — batters／pitchers（§4.3 第二例）
- [ ] `role`(打者/投手)→`HierarchicalTabs` group（onChange 導路由 /batters↔/pitchers）；`view`(獎項排行榜/完整清單)→item（**新增 `?view=` 參數，改分頁取代 AwardRaces/Leaderboard 垂直堆疊**）；`kind`＋`year`→controls。
- [ ] 一次呈現一視圖，閱讀清楚；`?view=` 預設「完整清單」（或依需求方定），無 view 參數向後相容。

### Phase 3 — games（§4.3 第三例）
- [ ] `kind`＋`year`→`LevelYearNav`（controls）；**隊伍篩選**→隊徽 chip 群（§9.3；窄螢幕可改 Select）整進導引欄；月份 prev/next stepper 保留（月曆專屬）。
- [ ] URL `kind`/`year`/`team`/`month` 無回歸。

### Phase 4 — matchups 對齊 ＋ teams/venues 稽核確認（範圍較小，誠實標注）
- [ ] `/matchups`：explorer **已有整合控制列**；align 共享軸（role/kind 走一致元件）＋套 `StickyNavBar`；explorer 專屬控制（scope／年範圍／對手／主角 combobox）保留不動。
- [ ] `/teams/[code]`：**稽核確認**——已用 canonical `Tabs`、`searchParams` 僅 `code`、**無 kind/year 散置**；除確認 section `Tabs` 一致（＋可選 sticky）外**預期無改動**。
- [ ] `/venues`・`/venues/[venue]`：**稽核確認**——無軸選擇器、清單/詳情；**預期無改動**（未來若加年份選擇器再納整合）。

**共通驗收**：各階 `cd web && npm run build:check` 通過；深/淺 × 桌機/375px 截圖；鍵盤 ↑↓/方向鍵＋`aria-*`；44px 觸控；`uv run ruff/pytest` 不受影響。**部署**：前端 build→上線（Runbook §3）。

## 依賴、序列與非目標

- **依賴**：`UI_UX_SYSTEM §4.3` 定案（已 sign-off）；`UX-DESIGN-SYSTEM1` 規格 merge。
- **序列**：Phase 0（StickyNavBar＋LevelYearNav 推廣）先行；Phase 1–3 各頁可並行或分卡。
- **非目標**：不建 `AxisNav` 通用件（現有件足夠；第 5+ 種軸型再議）；不改各頁資料計算/季後賽 bracket/月曆邏輯（只換導覽外殼）；不改 API/DB。token/三態 hygiene（`UI_UX_CONFORMANCE` H5/H6）可順手併入對應頁 PR 或留 `UX-TOKEN-HYGIENE1`。

## Log

- 2026-07-24 propose by UX-DESIGN-SYSTEM1 執行者（Opus 4.8），依 ruan6047 §4.3 定案；收斂 standings/rankings/games 為單一傘型卡；iteration 0，**待 Coordinator 註冊**。
- 2026-07-24 Coordinator 註冊（REGISTER-001）；19:31 依 ruan6047 指示由 Opus 4.8 認領執行（CLAIM-002；worktree `.claude/worktrees/ux-player-scope1-audit-15cb43`，branch `claude/ux-nav-integrate1-af0daf`）。
- 2026-07-24 Phase 0–4 實作完成（Opus 4.8）：
  - **Phase 0**：新增 `web/src/components/sticky-nav-bar.tsx`（`StickyNavBar` sticky 殼＋`NavBarRow` 版面，自球員頁 `PlayerNavigation` 抽出）；`HierarchicalTabs` 內部改用 `NavBarRow`（同 class、零視覺變更）並 export `TabItems`；`LevelYearNav` 改裸 controls＋`params` 保留頁面主軸參數；`YearSelect` 加 `params`＋**H8 圓角統一 `rounded-lg`（conformance 明文「圓角交 NAV」）**＋`min-h-11`；球員頁改用 `StickyNavBar`（行為不變）。
  - **Phase 1**：`standings/nav.tsx`（seg 單層 tablist＋`LevelYearNav` controls 一列）；`segsFor(kind)` 動態（二軍僅 全年/總冠軍）＋失效 seg fallback 全年（實測 `?kind=D&seg=1` → 全年 active）；移除 header 散置 level pills/YearSelect 與獨立 seg pill 列。
  - **Phase 2**：`rank-nav.tsx`（`HierarchicalTabs` role group×view item＋controls）；**`?view=` 值 `awards`／缺省＝完整清單（向後相容）**；tab 順序採「完整清單、獎項排行榜」（預設項在前；spec 例示順序相反，供 UI 審裁定）；刪 `rank-role-tabs.tsx`；實測 role 切換保留 view（/batters?view=awards → 點投手 → /pitchers?view=awards）。
  - **Phase 3**：games 手刻 kind/year 列改 `LevelYearNav`；隊伍 chips 整進 `StickyNavBar`（44px 觸控、窄螢幕橫向捲動；**inactive chips 補 `bg-surface-2` 底與「全部」chip 一致，係小幅視覺變更**）；月份 stepper 保留；實測 chip 篩選與 sticky 正常。
  - **Phase 4**：matchups 手刻 `Toggle` → canonical `ContextSwitcher` 置 `StickyNavBar`（視角＝頁級共享軸；主角 combobox 與 scope/年範圍/對手留 explorer 查詢卡不動——**未將整張查詢卡設 sticky**，因卡片含 combobox 高度過高、行動端會吃掉半個視口，供 UI 審裁定）；`/teams/[code]` 稽核✅（canonical `Tabs`、無 kind/year 散置、無改動）；`/venues` 稽核✅（無軸選擇器、無改動）。
  - **spec 順手修**：`UI_UX_SYSTEM §4.1` 路由切換 nav 語彙列去除已刪除的 `RankRoleTabs`。
  - **驗證**：`tsc` ✓、`npm run build:check` 全路由 ✓、`npm test` 126 ✓、`uv run ruff/pytest`（455 passed）✓；瀏覽器實測（真實點擊）standings 動態 seg/fallback、rankings view 分頁/role 保留、games chip 篩選/sticky、球員頁 sticky 無回歸；深/淺 × 桌機/375px 檢視。**待需求方本地人工審（dev :3000）**。
