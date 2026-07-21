# UX-TEAM-SPLIT-SCOPE1 球隊頁全年／上下半季數據切換〔T4；🟡資料範圍〕

- 需求：ruan6047　規劃：待指派　分支：`ai/<執行者>/UX-TEAM-SPLIT-SCOPE1`
- 執行：待指派　查核：待指派（跨模型家族或人工，且 ≠ 執行）
- Initiative：INIT-PRODUCT-UX　spec 基線：UX-TEAM-FOCUS1（本季現況頁）
- DB：`db_scope: read`（若採官網分半季爬蟲則升為 ingest，另切子卡）
- 部署：是　環境：production　PR：—　Merge SHA：—
- 範圍：球隊頁攻守概覽等當季團隊指標，讓使用者在「全年／上半季／下半季」間切換範圍。

## 背景（資料現況，勿腦補）

- `team_current`（官網 teamscore 爬蟲）預設回**當前半季**（現為下半季），下半季初小樣本會與全年印象背離（UX-TEAM-FOCUS1 已改由 `batting_current`／`pitching_current` **全年**個人數據即時彙總團隊 OPS／ERA／WHIP，`standings.py::_team_advanced_current_computed`）。
- 目前頁面固定顯示**全年**，無法切上/下半季。
- 上/下半季拆分無現成聚合：需 (a) teamscore 帶 `GameSeason` 參數分別爬存半季團隊值，或 (b) 由逐場 `games` 依 `game_date` 切半季邊界重算團隊值；個人層級半季拆分同樣缺表。半季邊界須以官方賽制界定（見 postseason／split-season 規則）。

## 驗收條件

- [ ] 球隊頁提供全年／上半季／下半季範圍切換（預設全年）；切換僅影響當季團隊指標區塊，不破壞其他區塊。
- [ ] 三種範圍的團隊 OPS／ERA／WHIP／得失分等口徑一致且來源明確（同一聚合路徑，非混用 team_current 與個人彙總）。
- [ ] 半季邊界依官方賽制界定；跨半季無資料或資料未就緒時範圍選項退化（禁止顯示誤導的空/零值）。
- [ ] 名次（rankOf）依所選範圍在同範圍內比較，不得跨範圍比名次。

## 驗證與依賴

- 驗證：三範圍切換走查、375 px／鍵盤、`tsc`、`build:check`、`ruff`＋`pytest`（新端點同步 EXPECTED 快照）。
- 依賴：UX-TEAM-FOCUS1（同頁基礎）；若採 (a) 官網分半季爬蟲，需另切 ingest 子卡並遵守爬蟲紅線（本機爬→同步生產）。
- 預估範圍：M（純前端+既有全年聚合擴半季）～L（需新增半季資料源）。

## Log

- 2026-07-22 註冊：源自 UX-TEAM-FOCUS1 審核，使用者指出頁面無法區分全年與上/下半季；WHIP 全年修正先落地（預設全年），本卡負責提供範圍切換。
