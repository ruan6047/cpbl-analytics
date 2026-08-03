# UX-LIVE-GAME1-FIX1 未開賽不得顯示局數〔T2；⚪使用者可見文案〕

- 需求：ruan6047　規劃／執行：Claude Opus 5@Claude Code　查核：須跨模型家族且 ≠ 執行
- review_independence: [cross_family]
- 父卡：`UX-LIVE-GAME1`　spec 基線：`LIVE_GAME_PRODUCT_SPEC v1.1`（沿用父卡）
- DB：`db_scope: none`　部署：是（純前端，隨 submodule bump）
- Design Gate：N/A；不新增介面或狀態，只收斂既有狀態列的局數顯示條件

## Discovery／成功條件

父卡 `UX-LIVE-GAME1` 於 2026-07-31 13:07 上線後，在生產發現未開賽場次的狀態列顯示
「▲ 1 局」、`aria-live` 播報「未開賽，⋯ 上1局」，讀起來像比賽已開打。比分本身誠實
（0-0），phase 標籤也正確寫「未開賽」，但局數是假的。

成因是狀態列只判 `liveSnapshot.inning` 是否 truthy，沒有同時看 phase。worker 對未開賽
場次回的是佔位值，靠 `inning` 本身無法與真值區分：

| 生產實測（2026-07-31） | phase | inning | half | event_count |
|---|---|---|---|---|
| sno 232／233／234 | `scheduled` | 1 | 1 | 0 |
| sno 231 | `final` | 9 | 2 | 355 |

成功條件：未開打場次不顯示局數、不播報局數；已開打場次（含已完賽）維持原有顯示。
判準必須同時服務保留賽——已打數局的保留賽仍應顯示局數，開賽前落雨延賽則否。

## 驗收條件

- [x] `scheduled`／`probable_announced`／`lineup_announced` 即使 worker 回 `inning=1`
      佔位，狀態列顯示「等待賽況」，`aria-live` 不帶局數。
- [x] `live` 與 `final` 維持原有局數顯示與上／下半局對應（worker `half` 1→上、2→下）。
- [x] 非 `live`／`final` 的其餘 phase 以 `event_count` 認定：保留賽已打數局顯示局數，
      開賽前延賽不顯示。
- [x] 狀態列與 `aria-live` 共用同一判準，不得再各自實作而分歧。

## 驗證與部署閘門

- [x] 先跑紅：對缺陷行為（只判 `inning` truthy）執行新測試，「未開打場次不顯示局數」
      與「保留賽以 `event_count` 認定」兩案失敗（240 tests／2 fail）；還原修正後 240 全綠。
- [x] `cd web && npm test`、`npx tsc --noEmit`、`npm run build:check`、`uv run ruff check`、
      `git diff --check` 全數通過；commit trailer guard 3 passed。
- [x] 瀏覽器驗證以本機修正版前端直打生產 API（真實佔位／真值資料）：sno 232 由
      「▲ 1 局」變「等待賽況」且 `aria-live` 不再帶局數；sno 231 仍顯示「▼ 9 局」
      「下9局」、本場焦點照常呈現，未回歸。console 零錯誤。
- [ ] 跨模型家族獨立查核 APPROVE 後才可 merge；部署由 ruan6047 確認。

## 紅線

- 不動後端 contract、DB、migration，不新增頁面或端點。
- 不以比分、時間窗或 `starts_at` 推論比賽是否開打；判準只用 canonical phase 與
  `event_count`。
- 不改動父卡已通過查核的其餘行為（賽後結論 gate、逐局 H/E、TrackMan 文案、
  last-known-good、polling 節奏）。

## Log

- 2026-07-31：父卡上線後由查核者於生產驗證時發現；ruan6047 指示「幫忙改」。缺陷源於
  查核階段的 mock 八個 phase 一律帶 `inning: 4`，未涵蓋 `scheduled` + `inning=1` 這個
  真實組合——測試設計盲點，非執行者隱瞞。
- 2026-07-31：分支 `ai/opus-5/UX-LIVE-GAME1-FIX1` @ `f2e259c` 交付待查核；執行者為
  Claude Opus 5，故查核須跨家族且 ≠ 執行。
- 2026-08-02T12:54:45+08:00 deploy 補記（`DEPLOY-006`）：碼已隨 2026-08-02T12:26 的 submodule bump
  上線——主站 `453a418` 指向 cpbl-analytics `3127ad0`，`git merge-base --is-ancestor c4c688f 3127ad0`
  為真。Ledger 先前的 `🚀待部署` 是留痕落後，非未上線。轉 `🚀部署待實測`：畫面行為（未開賽不得顯示
  局數）屬需求方人工實測，記錄者未在生產重現該情境，故不標 `✅已驗證`。
