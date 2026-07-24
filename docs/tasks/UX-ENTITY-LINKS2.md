# UX-ENTITY-LINKS2 實體連結 pattern 普及化（整塊 `hover:underline` → ENTITY_LINK）〔T2；🟦前端／設計〕

> **狀態 📥Backlog**：由需求方 ruan6047 於 2026-07-25 在 `UX-DESIGN-CONFORM1` 稽核收尾時定案開卡（out-scope B），實作延後排程。CONFORM1 已處理「低風險 className 對齊」，本卡承接需**逐點結構重構**的普及化。

- 需求：ruan6047　規劃：待指派　分支：`ai/<執行者>/UX-ENTITY-LINKS2`
- 執行：待指派　查核：待指派（≠ 執行；跨家族或人工）
- Initiative：`INIT-PRODUCT-UX`
- 依據 spec：[`../design/UI_UX_SYSTEM.md`](../design/UI_UX_SYSTEM.md) §3.5 實體連結 pattern、§9.3 隊名連結（規格已定案，本卡只落地、不改規格）
- DB：`db_scope: none`　部署：**是**（前端）　環境：web
- Design：**Design Gate = ruan6047**（每點的 block→text-only 觀感於本地審微調）

## 背景

`UX-ENTITY-LINKS1` 落地了 `ENTITY_LINK` 常數（`text-ink`＋常駐細底線＋hover accent）並套用於 `PlayerLink`／`Leaderboard`／`teams` 教練名等；`UX-DESIGN-CONFORM1` 再把 games/賽況、award-races、teams 純教練等**單純 `PlayerLink` className 覆寫**收斂到 ENTITY_LINK。

**尚未普及**的是一批「**整塊 `<Link>` 包 logo＋文字、用 block `hover:underline`**」或「**bare 文字 `hover:underline`**」的實體連結——它們**已非紅字**（ENTITY-LINKS1 本地審認可現狀），但**缺常駐細底線**、且底線若直接套會**橫跨 logo**（§3.5：只有文字帶底線）。普及化需**逐點把 block 連結重構成「僅名稱文字連結（logo 不套底線）」**，屬結構調整（非機械 className 換），故 CONFORM1 外切至本卡。

## 範圍：待普及化站點（稽核於 2026-07-25，行號待實作時複核）

| 檔案 | 位置 | 型態 |
|---|---|---|
| `web/src/app/standings/page.tsx` | `LinkedTeam`（~:34、:153） | 隊名 block `hover:underline` |
| `web/src/app/records/page.tsx` | 冠軍表隊名（~:78） | `<Link><TeamBadge></Link>` block |
| `web/src/components/mini-standings.tsx` | 隊名（~:48） | 隊名 block |
| `web/src/components/roster-board.tsx` | 球員（~:19） | 球員 block |
| `web/src/components/league-leaders.tsx` | top1／item（~:139、:173） | 球員 block |
| `web/src/components/matchups/pair-card.tsx` | 打者/投手（~:91、:99） | 球員 bare `hover:underline` |
| `web/src/components/matchups/insight-section.tsx` | 名字（~:66） | bare `hover:underline` |
| `web/src/app/teams/[code]/parts.tsx` | 名冊/背號表（~:177、:194、:213、:231） | 球員 block/bare |
| `web/src/app/players/[id]/season.tsx` | 隊名（~:194、:248） | 隊名 block（**基準頁**，ENTITY-LINKS1 本地審已認可現狀→是否納入由 Design Gate 定） |

- **`records/dynasty-chart.tsx`（~:80、:96）**：屬**圖表情境**，§9.3「圖表內不連」——**預設不納入**（保留現狀或改純文字），實作前與 Design Gate 確認。
- **`matchups/opponents-table.tsx:71`**：是 `<button>`（排序/選取控制），非實體連結——**不屬本卡**。

## 目標與驗收

- [ ] 上列站點的**實體名連結**收斂到 `ENTITY_LINK`：block 連結重構為「僅名稱文字帶連結＋底線、logo 不套」（§3.5）；隊名依 §9.3 gating（`isCurrentTeam`）。
- [ ] 不改連結**目的地**與**可點範圍語意**只調視覺（logo 仍可點進同頁則保留其 wrapper，僅底線限文字）；避免 nested `<a>`。
- [ ] `players/[id]`（基準頁）隊名是否納入，依 Design Gate 定案（預設納入以求全站一致，除非觀感退步）。
- [ ] `build:check` 全路由 ✓、`npm test` ✓、深淺色截圖、鍵盤焦點、a11y（連結非色彩單獨可辨識）。**先本地人工審再交跨家族查核**。

## 依賴與非目標

- **依賴**：`UX-ENTITY-LINKS1`（已 merge，`ENTITY_LINK` 常數就緒）。
- **非目標**：不改 `ENTITY_LINK` 常數本身；不改規格；不涉產品/IA；圖表內文字不連結；不動裁判介面（`UX-UMPIRE-SCOPE1` territory）。

## Log

- 2026-07-25 register by Claude Opus 4.8（Coordinator，依 ruan6047 於 CONFORM1 收尾指示）；iteration 0。承接 UX-DESIGN-CONFORM1 out-scope B（整塊 `hover:underline` 實體連結普及化）。
