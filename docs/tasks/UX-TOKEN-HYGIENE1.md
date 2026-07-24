# UX-TOKEN-HYGIENE1 設計系統 token/元件 hygiene 修復〔T2；⚪前端／token〕

> **狀態 📥 提案草稿（PROPOSAL，待 Coordinator 註冊）**：由 UX-DESIGN-SYSTEM1 執行者於 2026-07-24 依需求方裁定「另草擬修復卡 spec」產出。
> **本檔僅 spec，未執行、未註冊**——需 Coordinator 依 CONTROL_PLANE_CONTRACT 決定是否登錄 `docs/TASKS.md` 並排程。執行者不自行註冊 ledger。

- 需求：ruan6047　規劃：待指派　分支：`ai/<執行者>/UX-TOKEN-HYGIENE1`
- 執行：待指派　查核：待指派（≠ 執行；跨家族或人工）
- Initiative：`INIT-PRODUCT-UX`
- 依據 spec：[`../design/UI_UX_SYSTEM.md`](../design/UI_UX_SYSTEM.md)（§2.8 hex 白名單、§6 圖表）、[`../design/UI_UX_CONFORMANCE.md`](../design/UI_UX_CONFORMANCE.md)（H1–H7）
- DB：`db_scope: none`　部署：**是**（動 `globals.css` + 前端元件，需前端 build + 上線）　環境：web
- Design：**Design Gate = ruan6047**（動到色票須 sign-off）

## 背景與問題

`UX-DESIGN-SYSTEM1` 在 codify canonical 規格時，audit 出數項**屬改碼範疇**的 token/元件 hygiene 缺口。該卡紅線禁改 `globals.css`/元件碼，故僅記錄於 conformance 清單（H1–H7），修復拆出本卡執行。這些缺口不影響現況功能，但影響「規格與現實一致」與深色/色盲可及性。

## 目標與驗收

逐項修復（皆冪等、可獨立 commit）：

- [ ] **H1**：移除 `globals.css` 中 `--chart-7`/`--chart-8` 的重複（dead）定義（`#f472b6/#d4a373`），只留生效值 `#db2777/#a16207`。驗收：`@theme` 內每個 `--chart-N` 只出現一次。
- [ ] **H2**：`[data-theme="dark"]` 補 `--chart-7`/`--chart-8` 深色覆寫（現況只到 chart-6）。驗收：深色下 chart-7/8 有專屬值，且 on `surface #101f33` 對比達標。
- [ ] **H3**：對 `--chart-1..8`（淺/深各一組）跑 `dataviz` 的 `validate_palette.js`，修正相鄰對 ΔE<8 或對比 FAIL 的色槽（保持固定序語意，只調亮度/彩度）。驗收：validator 淺/深皆 pass（或 6–8 段落附 secondary encoding 說明）。
- [ ] **H4**：釐清 `zone-*`/`status-*` 在 `@theme` 與 `chart-theme.ts` 常數盤的**單一事實來源**（擇一為準、另一 import 或註明鏡像），消除 drift。驗收：兩處值一致且有註解指明 owner。
- [ ] **H5**：`app/standings/page.tsx`、`components/matchup-card.tsx` 的 Tailwind 數字色階 `amber-100/500/600/700` → 改語意 `--color-amber` token（或 `StatusBadge`/`Pill`/`Notice`）。驗收：兩檔無 `amber-[0-9]`。
- [ ] **H6**：`app/umpires/page.tsx`、`app/games/[sno]/box-tabs.tsx` 的 ad-hoc「載入中…」→ 改 `Skeleton`/`EmptyState`/`ErrorState` 三態。驗收：兩檔無 ad-hoc 載入字串。
- [ ] **H7**：sub-legible `text-[8px]/[9px]`（~12 處）上調 ≥ `text-[10px]` 或改 icon。驗收：全站無 `text-[8px]`/`text-[9px]`。

**驗證**：`cd web && npm run build:check` 通過；深淺主題各截圖抽驗圖表/標籤；`uv run ruff check`/`pytest` 不受影響（純前端）。**部署**：前端 build → 上線（依 Runbook §3）。

## 依賴、序列與非目標

- **依賴**：`UX-DESIGN-SYSTEM1` 規格 merge 後才有 canonical 依據；與 `UX-DESIGN-CONFORM1`（頁面對齊卡）**互補不重疊**——本卡專攻 token/元件層 hygiene（H1–H4 + H7），CONFORM 專攻頁面用語對齊；H5/H6 兩卡皆可，建議歸本卡（改碼集中）。
- **非目標**：不重排版面、不改資訊架構、不動 API/DB；不改變任何色票的**語意**（只修 dead code/深色缺值/可讀性，不重新選色）。

## Log

- 2026-07-24 propose by UX-DESIGN-SYSTEM1 執行者（Opus 4.8），依 ruan6047 裁定「另草擬修復卡 spec」；iteration 0，**待 Coordinator 註冊**。
