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

**共通驗收**：各階 `cd web && npm run build:check` 通過；深/淺 × 桌機/375px 截圖；鍵盤 ↑↓/方向鍵＋`aria-*`；44px 觸控；`uv run ruff/pytest` 不受影響。**部署**：前端 build→上線（Runbook §3）。

## 依賴、序列與非目標

- **依賴**：`UI_UX_SYSTEM §4.3` 定案（已 sign-off）；`UX-DESIGN-SYSTEM1` 規格 merge。
- **序列**：Phase 0（StickyNavBar＋LevelYearNav 推廣）先行；Phase 1–3 各頁可並行或分卡。
- **非目標**：不建 `AxisNav` 通用件（現有件足夠；第 5+ 種軸型再議）；不改各頁資料計算/季後賽 bracket/月曆邏輯（只換導覽外殼）；不改 API/DB。token/三態 hygiene（`UI_UX_CONFORMANCE` H5/H6）可順手併入對應頁 PR 或留 `UX-TOKEN-HYGIENE1`。

## Log

- 2026-07-24 propose by UX-DESIGN-SYSTEM1 執行者（Opus 4.8），依 ruan6047 §4.3 定案；收斂 standings/rankings/games 為單一傘型卡；iteration 0，**待 Coordinator 註冊**。
