# UX-ENTITY-LINKS3 賽事情境的隊名連結化〔T3；🟦前端／設計〕

> **狀態 📥Backlog**：需求方 ruan6047 於 2026-07-29 `UX-ENTITY-LINKS2` 人工審時提出
> （`/games/224?kind=A&year=2026` 的隊名希望可連）。**與 LINKS2 是不同型的改動**，故另立卡。

- 需求：ruan6047　規劃：待指派　分支：`ai/<執行者>/UX-ENTITY-LINKS3`
- 執行：待指派　查核：待指派（≠ 執行；跨家族或人工）
- Initiative：`INIT-PRODUCT-UX`
- 依據 spec：[`../design/UI_UX_SYSTEM.md`](../design/UI_UX_SYSTEM.md) §3.5 實體連結 pattern、§9.3 隊名連結（gating／圖表內不連）
- DB：`db_scope: none`　部署：**是**（前端）　環境：web
- Design：**Design Gate = ruan6047**（哪些出現位置該連、哪些不連；列表頁的互動取捨）

## 為什麼不併進 `UX-ENTITY-LINKS2`

|  | `UX-ENTITY-LINKS2` | 本卡 |
|---|---|---|
| 改動型態 | 既有連結的**視覺**收斂到 `ENTITY_LINK` | **新增原本不存在的連結** |
| 影響面 | 純視覺 | **導覽路徑／IA 變更** |
| 卡面關係 | 〈非目標〉明寫「不涉產品/IA」 | 本卡即為該非目標 |

2026-07-29 實測 `/games/224?kind=A&year=2026`：`document.querySelectorAll('a[href^="/teams/"]')` 
**長度為 0**——該頁隊名完全沒有連結，不是「有連結但視覺不對」。

## 範圍調查（2026-07-29，行號待實作時複核）

隊名渲染點約 **47 處**，橫跨 8 檔：

- `web/src/app/games/[sno]/page.tsx`（記分板、逐局比分表、摘要列）
- `web/src/app/games/[sno]/overview.tsx`、`box-tabs.tsx`
- `web/src/app/games/page.tsx`（賽事列表）
- `web/src/components/game-board.tsx`、`pregame-card.tsx`、`daily-hub.tsx`、`mini-standings.tsx`

## 🔴 技術限制：列表頁會產生 nested `<a>`

`web/src/app/games/page.tsx:189`、`:247`——**每張賽事卡本身已是 `<Link>`**（連向單場頁）。
在其內再放隊名 `<Link>` 即 **nested anchor，HTML 無效**，瀏覽器行為未定義。

因此本卡**必須分兩層處理**，且第二層是 IA 決策而非視覺調整：

| 層 | 位置 | 可行性 |
|---|---|---|
| **A（低風險）** | 單場頁 `/games/[sno]` 的記分板與逐局比分表 | 不在任何 `<Link>` 內，可直接加連結 |
| **B（需 Design Gate 裁定）** | `/games` 列表、`daily-hub` 等已被卡片 `<Link>` 包住者 | 要連就得**改變卡片互動語意**（卡片不再整塊可點、改附「看單場 →」CTA），屬 IA 變更 |

**建議先只做 A，B 另行決策**——不要為了「隊名都可連」而拆掉既有的整卡可點。

## 目標與驗收

- [ ] A 層：單場頁記分板與逐局比分表的隊名連向 `/teams/[teamPageCode(code)]`，走 `ENTITY_LINK`；
      §9.3 gating（`isCurrentTeam`）；logo 與名稱的可點範圍取捨比照 `UX-ENTITY-LINKS2` 的結論
      （保留整塊可點、底線只跟文字，用 `ENTITY_LINK_TEXT`）。
- [ ] **不得連的位置逐一確認**（§9.3「圖表內不連」與敘事文案）：
      勝率條上的「中信兄弟 +9%」等**統計標籤**、關鍵時刻**圖例**、「統一 中計（滿壘未得分）」等**敘事 chip**。
- [ ] B 層：只出**選項與取捨分析**交 Design Gate，不逕自實作。
- [ ] `build:check` 全路由 ✓、`npm test` ✓、深淺色截圖、鍵盤焦點、a11y。
- [ ] **全站掃 nested `<a>`**：實作後須驗證無任何 `<a>` 巢狀（本卡最大風險）。

## 依賴與非目標

- **依賴**：`UX-ENTITY-LINKS2`（`ENTITY_LINK_TEXT` 與「保留可點範圍」的結論須先定案）。
- **非目標**：不改 `ENTITY_LINK`／`ENTITY_LINK_TEXT` 常數；不改 §3.5／§9.3 規格；
  不動球員名連結（已由 `PlayerLink` 涵蓋）；B 層不在未取得 Design Gate 前實作。

## Log

- 2026-07-29 需求方於 `UX-ENTITY-LINKS2` 人工審期間提出（`/games/224` 隊名希望可連）。
  Coordinator 實測確認該頁 `/teams/` 連結數為 0、範圍約 47 處／8 檔，
  並查出 `/games` 列表卡片已是 `<Link>`（`page.tsx:189`、`:247`）會造成 nested anchor，
  故分 A／B 兩層並另立本卡，不擴張 `UX-ENTITY-LINKS2`（該卡〈非目標〉明寫不涉 IA）。
