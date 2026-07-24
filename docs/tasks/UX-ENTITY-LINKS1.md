# UX-ENTITY-LINKS1 實體連結：球員名改沉穩色 + 隊名超連結〔T2；🟦前端／設計〕

> 由需求方 ruan6047 於 2026-07-24 在 UX-DESIGN-SYSTEM1 grilling 中提出並定案（名字紅色觀感突兀；隊名應可連隊伍頁）。

- 需求：ruan6047　規劃：待指派　分支：`ai/<執行者>/UX-ENTITY-LINKS1`
- 執行：待指派　查核：待指派（≠ 執行；跨家族或人工）
- Initiative：`INIT-PRODUCT-UX`
- 依據 spec：[`../design/UI_UX_SYSTEM.md`](../design/UI_UX_SYSTEM.md)（本卡順帶新增 §3「實體連結 pattern」、§9.3「隊名連結規則」，須 Design Gate sign-off）
- DB：`db_scope: none`　部署：**是**（前端）　環境：web
- Design：**Design Gate = ruan6047**（實際連結觀感於本地審微調）

## 背景與問題

1. **球員名紅色突兀**：全站連結統一用 `accent`（紅 #d62839），而 `accent` 同時是「行動色」＋「數據差(down)」色，導致紅色球員名潛意識讀成負面。
2. **隊名多半不連結**：`NameTag`/`TeamBadge` 目前不連 `/teams/[code]`（僅少數頁手動連），使用者無法從隊名直接進隊伍頁。

## 目標與驗收（grilling 定案）

- [ ] **實體連結 pattern**（新增 spec §3）：球員/隊名 = `text-ink` + 常駐細底線（可辨識）、hover 顯 `accent`；**不再紅字**。**行動連結**（「看單場 →」/導覽/CTA）**保留 `accent` 紅**。
  - 落地：`PlayerLink`、`Leaderboard` 名字欄、其餘實體名連結。實際觀感（常駐底線 vs 更明顯）於本地審微調。
- [ ] **隊名連結**（新增 spec §9.3）：`NameTag`/`TeamBadge` 可選連 `/teams/[teamPageCode]`；**圖表（recharts/SVG）內關**；**歷史/已解散隊不連**（走 `isCurrentTeam`）。
- [ ] spec §3/§9.3 更新 + **Design Gate sign-off**。
- [ ] 驗證：`build:check` + 深淺色截圖 + 鍵盤焦點 + a11y（連結非色彩單獨可辨識）。**先本地人工審再交跨家族查核**。

## 依賴、序列與非目標

- **依賴**：`UX-DESIGN-SYSTEM1`（已 merge）。
- **序列**：排在 `UX-TOKEN-HYGIENE1` 之後（小卡、獨立）。
- **非目標**：不改 `accent` token 本身；不改連結以外的視覺；不涉產品/IA；圖表內文字不連結。

## Log

- 2026-07-24 register by Claude Opus 4.8（Coordinator，依 ruan6047 指示）；iteration 0。源自 UX-DESIGN-SYSTEM1 grilling 定案。
