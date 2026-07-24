# UX-STANDINGS-NAV1 standings 一體式多軸導引欄重構〔T2；🟦前端／重構〕

> **狀態 📥 提案草稿（PROPOSAL，待 Coordinator 註冊）**：由 UX-DESIGN-SYSTEM1 執行者於 2026-07-24 依需求方 ruan6047 對 `UI_UX_SYSTEM §4.3` 之 A2/B1/C/D2 定案產出。
> **本檔僅 spec，未執行、未註冊**——需 Coordinator 依 CONTROL_PLANE_CONTRACT 決定是否登錄 `docs/TASKS.md` 並排程。執行者不自行註冊 ledger。

- 需求：ruan6047　規劃：待指派　分支：`ai/<執行者>/UX-STANDINGS-NAV1`
- 執行：待指派　查核：待指派（≠ 執行；跨家族或人工）
- Initiative：`INIT-PRODUCT-UX`
- 依據 spec：[`../design/UI_UX_SYSTEM.md`](../design/UI_UX_SYSTEM.md) §4.3（A2/B1/C/D2 定案）、§4.4、§9.6
- DB：`db_scope: none`　部署：**是**（動前端元件，需 build + 上線）　環境：web
- Design：**Design Gate = ruan6047**（§4.3 方向已 sign-off 2026-07-24；成品仍須 UI 審）

## 背景與問題

`/standings` 同頁有三軸——**層級 `kind`**（一軍/二軍）、**賽季階段 `seg`**（全年/上半季/下半季/季後賽）、**年度 `year`**（下拉）——現況為**散置的獨立控制 ＋ 一顆孤立年度下拉**，與球員頁的一體式導引欄不一致（見 `UI_UX_CONFORMANCE.md` standings 列）。`UI_UX_SYSTEM §4.3` 已定案以現有積木收斂成**一條一體式多軸導引欄**（非發明新元件）。

## 目標與驗收

- [ ] **抽 `StickyNavBar` 殼**（D2）：把球員頁 `PlayerNavigation` 的 sticky 定位邏輯（`ResizeObserver` 量 header 高 ＋ `sticky z-20 backdrop-blur bg-paper/95 border-b`）抽成可重用殼，球員頁與 standings 共用。**不**抽 `AxisNav` 全套（3+ 頁才抽）。驗收：球員頁改用 `StickyNavBar` 後行為不變（sticky 定位、無 CLS）。
- [ ] **standings 一體式導引欄（A2）**：`seg` → 單層 tablist（主分頁，比照 `TabItems` 語意/鍵盤）；`kind` → `ContextSwitcher`；`year` → `YearSelect`；`kind`＋`year` 置右側 `controls`（`md:border-l md:pl-3` 分隔）。一列呈現 `全年 上半季 下半季 季後賽 ┃ 〔一軍│二軍〕 年度▾`。
- [ ] **動態 seg（C）**：`segsFor(kind)`——一軍＝全年/上半季/下半季/季後賽；**二軍＝全年/季後賽（無上下半季，[[postseason-format-rules]]）**。切 `kind` 後若當前 `seg` 失效 → fallback 回「全年」（照抄球員頁 `viewsFor` + fallback）。
- [ ] **窄螢幕（B1）**：手機 `flex-col` 堆疊，年度用 native `<select>`（OS 原生 picker）；**不**縮 icon。375px 無橫向溢出。觸控 ≥44px。
- [ ] **無回歸**：URL 三參數 `kind`/`seg`/`year` 行為不變（含 `seg=3` 季後賽強制 `season_code` 邏輯、二軍分支）；深/淺色皆正常；鍵盤 ↑↓/方向鍵可操作、`aria-*` 正確。
- [ ] **（可併，非必須）** 順手清 standings 的 `UI_UX_CONFORMANCE` 偏離：amber 數字色階（H5）、ad-hoc 三態（H6）——若併入須在 PR 分段 commit，否則留 `UX-TOKEN-HYGIENE1`。

**驗證**：`cd web && npm run build:check` 通過；深/淺 × 桌機/375px 截圖抽驗；鍵盤導覽與 `aria-selected/current` 檢查；`uv run ruff check`/`pytest` 不受影響（純前端）。**部署**：前端 build → 上線（Runbook §3）。

## 依賴、序列與非目標

- **依賴**：`UI_UX_SYSTEM §4.3` 定案（已 sign-off）；`UX-DESIGN-SYSTEM1` 規格 merge 後執行。
- **序列**：`StickyNavBar` 抽殼須先於 standings 改造（standings 消費它）；球員頁遷移到 `StickyNavBar` 與 standings 可同 PR。
- **非目標**：不建 `AxisNav` 通用件（第 3 個多軸頁再議）；不改其他頁；不改 API/DB；不改 standings 的資料計算與季後賽 bracket 邏輯（只換導覽外殼）。

## Log

- 2026-07-24 propose by UX-DESIGN-SYSTEM1 執行者（Opus 4.8），依 ruan6047 對 §4.3 A2/B1/C/D2 定案；iteration 0，**待 Coordinator 註冊**。
