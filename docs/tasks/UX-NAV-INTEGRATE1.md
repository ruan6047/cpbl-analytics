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
- 2026-07-24 **需求方人工審 round 1 裁定與修訂**（Opus 4.8）：
  1. 排行 view tab 順序改「獎項排行榜、完整清單」（依 spec 例示；預設仍完整清單）。
  2. games inactive chips `bg-surface-2` 底：維持（採執行者建議）。
  3. matchups 查詢列**融入導覽欄**：explorer 加 `chrome="card"|"bar"`（球員頁維持卡片；/matchups 用 bar）＋`StickyNavBar` 加 `mobileStatic`（桌機 sticky 便於捲動中調篩選、**行動端 static** 避免高卡吃視口）；視角 ContextSwitcher 回到查詢列 header 槽。
  4. **一/二軍樣式統一參照選手頁**：`LevelYearNav` 層級改 ContextSwitcher 視覺（「層級」label＋segmented 膠囊、active `bg-surface shadow-sm` 凸起），保留 Link＋`aria-current` 路由語意；移除舊分隔線。
  5. **主/子頁籤視覺分層重設計**：`HierarchicalTabs` 未選取主頁籤由 `bg-surface-2` 實底（易與 active 群的灰底容器/子頁籤混淆）改**描邊 pill**（`border-line bg-surface text-muted`，hover 加深）；active 主頁籤維持實心 ink pill＋子頁籤同住灰底容器示從屬。
  - 修訂驗證：`tsc` ✓、`npm test` 126 ✓、瀏覽器深/淺 × 1280/375 重驗（matchups 桌機 sticky/行動 static 實測）。
- 2026-07-24 **人工審 round 2**：games 隊伍 chips `rounded-full` 太圓不像按鈕 → 改 control canonical `rounded-lg`（§2.5），與月份 stepper/層級膠囊同語彙；瀏覽器重驗 ✓。
- 2026-07-24 **人工審 round 3**：①所有主頁籤改「上圓角、下方角」經典頁籤造型（`rounded-t-md`/容器 `rounded-t-lg`，貼齊導覽欄下緣的分頁感）；②一/二軍與 `ContextSwitcher` 語彙改 **switch 造型**（`rounded-full` 軌道＋滑塊；球員頁 身分/層級、matchups 視角同步，維持全站一致）；`tsc`/`npm test` ✓、瀏覽器重驗 ✓。
- 2026-07-24 **人工審 round 4**：①頁籤下緣貼齊分隔線——`StickyNavBar` 加 `flush`（殼去下內距）＋`NavBarRow` 加 `align="end"`（controls 保留小間距），standings/rank/球員頁三處接上；②switch 瘦身——軌道視覺高 `h-8`、滑塊改內層 span，按鈕/Link 保持 `min-h-11` 44px 觸控熱區（垂直外溢不可見，a11y 守門測試不動）；③子頁籤較主頁籤「矮」：文字下沉錨定（`items-end`＋`pb-1`）＋字級 `text-xs`，底線壓在分隔線上，主次分明；`tsc`/`npm test` ✓、瀏覽器桌機/窄版重驗 ✓。
- 2026-07-24 **人工審 round 5**：子頁籤「框」仍與主頁籤同高 → 改**階梯式**：active 主頁籤全高（44px）、子頁籤住較矮灰色托盤（`h-8`＝32px、`rounded-tr-lg`、底對齊貼線），觸控熱區維持 44px 向上外溢；DOM 量測 main 44 / tray 32 / 底邊皆貼分隔線；`tsc`/`npm test` ✓。
- 2026-07-24 **人工審 round 6**：games/matchups 導覽欄改 **radio-pill 語彙**（需求方指定 uiverse.io/nhfiz/old-lion-54（MIT）風格改作：未選＝radio 圓圈＋文字、選中＝圓圈收合成實色膠囊；去原作 hover 光暈、色彩全走站內 token）。新增 `web/src/components/radio-pills.tsx`（`RadioPillFace` 共用面＋`RadioPills` button 群，鍵盤 ←→ 同 ContextSwitcher）；games 隊伍篩選（全部=ink、球隊=隊色 §9.3）與 matchups 視角採用；games 層級 switch 維持全站共用樣式不動。DOM 驗證：active 隊色膠囊/圓圈 12px→收合；`tsc`/`npm test`/`build:check` ✓。
