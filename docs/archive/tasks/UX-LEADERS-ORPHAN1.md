# UX-LEADERS-ORPHAN1 `LeagueLeaders` 元件已無 runtime consumer〔T2；🟦前端〕

- 需求：ruan6047（2026-07-29 依 `UX-ENTITY-LINKS2` 跨家族查核的 informational finding 2 指示開卡）　規劃：本卡 spec　分支：`ai/<執行者>/UX-LEADERS-ORPHAN1`
- 執行：待指派（建議 L1；刪除死碼與盤點，判準已由 blueprint 定案）　查核：待指派（建議 L2；≠ 執行）
- Initiative：`INIT-PRODUCT-UX`　spec 基線：—（本卡不改規格，只執行 blueprint §3.2／§7「應移除」的既有定案）
- DB：`db_scope: none`
- 部署：是（前端；但**移除本身無 runtime 效果**，見下）　環境：web　PR：—　Merge SHA：—
- 範圍：`web/src/components/league-leaders.tsx`（＋同類孤兒元件盤點）
- Discovery：—（T2，事實已於開卡時查證）
- Design：**Design Gate N/A**——該元件目前**不被任何頁面渲染**，移除對使用者可見介面**零影響**；下架決定早在 `UX-GAME-HOME1` 由 blueprint §3.2／§7 定案，本卡不重開該決定。

## 事實（開卡時查證，非轉述）

`web/src/components/league-leaders.tsx` 全站**零引用**（`rg "LeagueLeaders|league-leaders" web/src` 僅命中定義檔本身）。它是 `"use client"` 的純展示元件，靠 props 收 `batting`／`pitching`，**資料要由掛載它的頁面自己抓**。

**它不是失聯，是被刻意下架的。** 2026-07-18 的 `e3352e7`（`UX-GAME-HOME1`）把首頁重建為每日入口 hub，commit body 明寫「`page.tsx`：**移除 10 套領先榜與其請求**」，把 12 次請求收斂成單一 `GET /api/v1/daily/summary`。這正是 blueprint 要的：§3.2 禁止模式列有「首頁同時展示多套排行榜、戰績、預測與所有探索入口」，§7「應移除」第一條逐字列出「現行首頁一次抓取 AVG、H、HR、RBI、SB、ERA、W、HLD、SV、SO 十套榜單」。

**功能沒有消失**：打者／投手排行由 `web/src/components/leaderboard.tsx` 在 `/batters` 與 `/pitchers` 提供，是 `UX-RANKINGS1` 收斂過的版本。`LeagueLeaders` 是它的前身遺留，不是互補品。

## 為什麼值得處理而不是留著

留著的成本不是那 6KB，是**它會繼續吃掉工時與查核頻寬**。下架至今 11 天內，它已被兩張卡改過兩次：

- `3141b71`（`UX-ENTITY-LINKS1`）把它納入 `ENTITY_LINK` 收斂；
- `c577fc8`（`UX-ENTITY-LINKS2`）又為它加 `ENTITY_LINK_TEXT`、還原可點範圍。

兩次都是**對沒有任何使用者看得到的程式做視覺調整**。更精確的代價在查核端：`UX-ENTITY-LINKS2` 的跨家族查核者明確報告，該元件**只能做靜態審查與 build 驗證、無法在瀏覽器實測**——也就是說，它讓一張卡的驗收出現了一塊查不到的區域，而那塊區域根本不存在於產品裡。

## 目標

判定並執行：**移除**（預設）或**重新掛載**。

預設是移除，且**重新掛載需要先改 blueprint**——§3.2 與 §7 已把「首頁多套排行榜」列為禁止模式與應移除項，在不改規格的前提下沒有合法的掛載點。執行者若主張掛載，須先指出具體頁面與 blueprint 依據，並走規格變更流程，不得逕自掛回首頁。

## 次要交付：同類孤兒盤點

本元件是**被查核者順手發現**的，不是被任何機制抓到的——這代表可能還有別的。請掃一遍 `web/src/components/**` 與 `web/src/app/**`，列出**沒有任何 import 的模組**，對每一個標註：最後被引用於哪個 commit／哪張卡、是刻意下架還是遺漏。

**只出清單與分級，不要一次全刪。** 顯而易見的同類（同樣被 `UX-GAME-HOME1` 下架者）可併入本卡；其餘開後續卡，避免本卡變成大掃除。

## 驗收條件

- [ ] `LeagueLeaders` 的處置完成（移除，或有 blueprint 依據的掛載），且處置理由寫在 commit body。
- [ ] 移除後全站再次確認零殘留引用（含 `web/src/lib/**` 與型別）；`web/src/components/ui.tsx` 若有僅為它存在的匯出，一併確認是否還有其他使用者，**沒有才移除**。
- [ ] 確認移除不會連帶讓任何 API 端點失去唯一消費者；若有，於卡片記錄該端點與現況（**本卡不動後端**）。
- [ ] 同類孤兒盤點清單產出，每項標註最後引用 commit 與「刻意／遺漏」判斷。
- [ ] `npm run build:check` 全路由通過、`npm test` 通過。

## 驗證

- [ ] 查核者獨立以 `rg` 確認零引用（不採信執行者的搜尋結果）。
- [ ] 查核者確認移除**前後**首頁與 `/batters`／`/pitchers` 的渲染結果無差異——本卡若正確，差異必須為零，因為該元件本來就不在任何頁面上。
- [ ] 查核者抽驗盤點清單中至少兩項，確認「最後引用 commit」與「刻意／遺漏」判斷屬實。

## 邊界

- 不改 blueprint、不改 `/batters`／`/pitchers` 的排行呈現、不動後端與 API。
- 不處理「首頁要不要有領先榜」這個產品問題——那已由 blueprint §3.2／§7 定案，要翻案走規格變更。
- 預估 S。

## Log

- 2026-07-29 register by Claude Opus 5@Claude Code（Coordinator，依 ruan6047 指示）；iteration 0。來源為 `UX-ENTITY-LINKS2` 跨家族查核的 informational finding 2。開卡前查證：零引用、下架 commit 為 `e3352e7`（`UX-GAME-HOME1`，2026-07-18）、blueprint §3.2／§7 已將首頁多套排行榜列為禁止模式與應移除項、功能由 `/batters`／`/pitchers` 的 `Leaderboard` 承接。**查核者原述為「要重新掛載或移除」，查證後修正為「預設移除，掛載需先改規格」**。
