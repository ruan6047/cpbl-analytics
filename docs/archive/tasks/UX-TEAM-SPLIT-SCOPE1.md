# UX-TEAM-SPLIT-SCOPE1 球隊頁全年／上下半季數據切換〔T4；🟡資料範圍〕

- 需求：ruan6047　規劃：待指派　分支：`ai/<執行者>/UX-TEAM-SPLIT-SCOPE1`
- 執行：待指派　查核：待指派（跨模型家族或人工，且 ≠ 執行）
- Initiative：INIT-PRODUCT-UX　spec 基線：UX-TEAM-FOCUS1（本季現況頁）
- **依賴：`UX-DESIGN-SYSTEM1`**（全站 UI/UX 統一規則地基）通過 + Design Gate sign-off 後才認領；本卡未動即釋回重排，改照 canonical 規格實作以免返工（2026-07-24 排程調整）。
- DB：`db_scope: read`（若採官網分半季爬蟲則升為 ingest，另切子卡）
- 部署：是　環境：production　PR：—　Merge SHA：—
- 範圍：球隊頁攻守概覽等當季團隊指標，讓使用者在「全年／上半季／下半季」間切換範圍。

## 背景（資料現況，勿腦補）

- `team_current`（官網 teamscore 爬蟲）預設回**當前半季**（現為下半季），下半季初小樣本會與全年印象背離（UX-TEAM-FOCUS1 已改由 `batting_current`／`pitching_current` **全年**個人數據即時彙總團隊 OPS／ERA／WHIP，`standings.py::_team_advanced_current_computed`）。
- 目前頁面固定顯示**全年**，無法切上/下半季。
- 上/下半季拆分無現成聚合：需 (a) teamscore 帶 `GameSeason` 參數分別爬存半季團隊值，或 (b) 由逐場 `games` 依 `game_date` 切半季邊界重算團隊值；個人層級半季拆分同樣缺表。半季邊界須以官方賽制界定（見 postseason／split-season 規則）。

## 驗收條件

- [x] 球隊頁提供全年／上半季／下半季範圍切換（預設全年）；切換僅影響當季團隊指標區塊，不破壞其他區塊。
- [x] 三種範圍的團隊 OPS／ERA／WHIP／得失分等口徑一致且來源明確（同一聚合路徑，非混用 team_current 與個人彙總）。
- [x] 半季邊界依官方賽制界定；跨半季無資料或資料未就緒時範圍選項退化（禁止顯示誤導的空/零值）。
- [x] 名次（rankOf）依所選範圍在同範圍內比較，不得跨範圍比名次。

### 追加驗收（2026-07-25 需求方審後擴充）

- [x] 導覽與全站統一：改用 canonical `HierarchicalTabs`（§4.3），上下半季為「賽季」子頁籤（廢除獨立膠囊切換器）。
- [x] 「本季」改為「賽季」並加年度軸（`?year=`，2018–當季 ∩ franchise 活躍年）；賽季各區塊隨年度變動。
- [x] 「近期賽事」獨立為「近日焦點」頁籤，且置於**第一個**頁籤（落地預設）。

## 驗證與依賴

- 驗證：三範圍切換走查、375 px／鍵盤、`tsc`、`build:check`、`ruff`＋`pytest`（新端點同步 EXPECTED 快照）。
- 依賴：UX-TEAM-FOCUS1（同頁基礎）；若採 (a) 官網分半季爬蟲，需另切 ingest 子卡並遵守爬蟲紅線（本機爬→同步生產）。
- 預估範圍：M（純前端+既有全年聚合擴半季）～L（需新增半季資料源）。

## Log

- 2026-07-22 註冊：源自 UX-TEAM-FOCUS1 審核，使用者指出頁面無法區分全年與上/下半季；WHIP 全年修正先落地（預設全年），本卡負責提供範圍切換。
- 2026-07-25 Discovery 定方向（純讀對帳）：半季邊界＝官方內建 `games.game_season_code`（非需自行界定讓一勝規則）；`batting_gamelog`／`pitching_gamelog` join `games`（year+kind_code+game_sno，2026 A 覆蓋 4834→4834）可依半季聚合，全年加總對帳現行 `*_current` 僅捨入級差異。需求方裁定採**路線 (b) gamelog 純讀重算**（非路線 (a) 官網分半季爬蟲）→ `db_scope` 維持 `read`、不觸發爬蟲紅線、免 ingest 子卡。附帶定案：DER 切半季標「全年」不硬湊；下半季小樣本照常顯示＋樣本量標示。
- 2026-07-25 需求方審後擴充範圍：要求導覽與全站統一（改 canonical `HierarchicalTabs`、上下半季降為「賽季」子頁籤）、「本季」改「賽季」並加**歷年年度軸**、「近期賽事」獨立為「近日焦點」頁籤並置於第一頁。年度下限 2018＝逐場 gamelog 起點（早於此不開放而非顯示誤導值）。歷史年守備位置圖需 union `fielding_seasons`（`fielding_current` 僅 2025+）→ 現為明示退化文案，另開 follow-up 卡。
- 2026-07-25 交付與跨家族查核：`288a3ad`（4 commits，真實變更 7 檔）。**Gemini 3.6 APPROVE**（跨模型家族、非 Claude、≠ 執行者），自建獨立環境實測（PG 5433／FastAPI 4022／Next 3009）。ruff clean、pytest 455 passed、tsc／build:check 通過；三範圍×多年度走查、375px／鍵盤、球員頁共用元件無回歸、dev overlay React key 警告修正歸零。merge 前置：分支落後 main 13 commits 需先同步，`docs/control-plane/**` 與 `docs/TASKS.md` 衝突以 main 為準；merge 待 ruan6047 授權。
