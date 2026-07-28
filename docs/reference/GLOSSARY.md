# GLOSSARY — 跨檔術語單一出處

> **收錄判準**：只收「同一詞在兩處被不同定義過」或「新執行者會腦補錯」的詞；每詞恰一個 SSoT 出處。不做全字典。
> 其他文件與卡片**引用本檔，不得另寫第二份定義**；發現定義衝突時，以本檔標注的 SSoT（優先序：DB 實證 > 程式碼 > 註解／docstring）為準並回頭修正。

## 賽別與場次

### `kind_code`（games 賽別代碼）

DB 實證（2026-07-26，本機 `cpbl.games` 全史 GROUP BY；場次數／起始年／主隊碼字尾）：

| 代碼 | 語意 | 佐證 |
|---|---|---|
| `A` | 一軍例行賽 | 1990 起、9,808 場 |
| `C` | 一軍總冠軍賽（台灣大賽） | 1990 起、184 場；冠軍隊由 C 場次推導（`migrations/036_championship_members.sql`） |
| `D` | 二軍例行賽 | 2005 起、3,379 場（`migrations/037_fielding_kind_code.sql`） |
| `E` | **一軍季後挑戰賽** | 1998 起僅 40 場、只出現在半季冠軍歧異年份（1998–99、2005–08、2017–18、2022–25）、主隊碼皆 `*011`（一軍實體） |
| `F` | **二軍總冠軍賽** | 2005 起年年出現、103 場、主隊碼以 `*022`（二軍實體）為主 |

- SSoT：`cpbl.games` DB 實證＋`src/cpbl/ingest/run_scrape.py` `KINDS` 註解（A/C/E 與實證一致）。
- `winprob_val.py` 原「E＝二軍季後」誤標與 `{"E": "D"}` proxy **已由 GAME-RECAP-WP-VAL1-FIX1 修正**（proxy 改 A、E 規則實證重推為無和局＋無突破僵局；`TRAIN_PROXY` 常數＋測試釘住）。E scope 結論（unsupported，樣本極小）修正前後皆成立。
- `ingest/cpbl_home_runs.py` `KIND_CODES` 另列官網完整枚舉（含 B、D9、G、H、X），**語意未驗證，勿腦補**；季後賽制規則（挑戰賽 5 戰 3 勝／讓一勝、台灣大賽 7 戰 4 勝）見 [`reference/`](./) 聯盟規章第 60–63 條。
- 隊碼字尾 `011`/`022` 為一／二軍實體（`team_dim`）；判軍別以 `kind_code` 為準（F 場次偶見 `*011` 混雜，屬來源資料雜訊）。

### 保留賽／`delay_kind`

同一 `sno` 的排程歷程推導：官網 `GameResult` `2`＝**保留**（已開賽中止，優先判定）、`1`＝**延賽**；`orig_date` 保留取該場開賽日、延賽取最早原定日（可能多次延期）。同 sno 多筆排程 entry 依 PK 聚合，主記錄取完成場。

- SSoT：`src/cpbl/ingest/cpbl_site.py` `_delay_info`（含 docstring）。

### 完成場判定

`home_score + away_score > 0 AND game_date <= CURRENT_DATE`。**缺日期界線會誤判**：保留賽會掛未來補賽日卻已帶比分。

- SSoT：`src/cpbl/completion.py` `completed_games_sql`（各處查詢一律引用此函式，勿手寫條件）。

## 逐打席（livelog / canonical PA）

### island

livelog 逐事件切候選 PA 的分組單位：**連續同 `(game, inning, half, hitter)` 的事件島**；換人公告列（`is_change_player`）與空 hitter 列不 seed／不切界，附掛於當前 island。

- SSoT：`scripts/pa_transition_taxonomy.py` `_island_starts`（`island_rule` 定義處）；`src/cpbl/ingest/pa_build.py` `build_islands` 為對齊實作（測試鎖定兩者一致，杜絕語意漂移）。

### 幽靈島

換人公告列掛「即將上場打者」的 acnt＋傳播的結果字串**自成一島（無投球）**——不是真打席。splits／PA 計算必須排除（以 `distinct_pitches`／無投球特徵識別）。

- SSoT：`src/cpbl/ingest/splits_calc.py`（「幽靈島」註解處）；審計輸出見 `src/cpbl/ingest/run_verify_splits.py`。

### canonical PA／`pa_id`

物化打席表 `cpbl.game_plate_appearances`（published build、`state='ready'` 才可消費，fail closed）。`pa_id` 為 deterministic UUIDv5，seed＝`year|kind|game|start_event_no|event_order_version`——同一打席跨重跑穩定。

- SSoT：`src/cpbl/ingest/pa_build.py` module docstring；分類 role／outcome_family 讀版本化 taxonomy JSON `src/cpbl/resources/pa_transition_taxonomy.v1.json`。

## 統計語意

### wf（walk-forward）

時間外驗證法：驗證季 Y 的模型訓練窗恆 ≤ Y−1；季後 scope（C／E）的訓練窗可含當年例行季——季後開打前例行季已全數完賽，仍屬時間外。in-sample 對照只用於量化樂觀偏差，不作支持證據。

- SSoT：`src/cpbl/models/winprob_val.py` docstring 與 `run_validation`。

### GO／FO（滾飛比語意）

「滾地型／飛球型非安打擊球」＝出局＋失誤上壘＋犧打：**犧短／內野失誤計 GO、犧飛／外野失誤計 FO**；趁傳／雙殺／野選／界飛照滾飛歸類（與官方值對帳係數≈0 證實）；「違規」與型態不明**不歸滾飛**。

- SSoT：`src/cpbl/ingest/splits_calc.py`（`_GO`/`_FO` 對照表與其上方註解）。

### 連續無自責分局數（**≠ 連續無失分**）

「連續無**自責**分局數」是本專案的口徑：失誤造成的非自責失分**不中斷**（與 ERA 語意一致）。媒體常用的「連續無失分」要求該場 `runs=0`，是**更嚴格**的另一個指標，數值通常較小（實例：呂彥青 2026-07-26 時點 28.1 局 vs 9.0 局）。**兩者混用即為錯誤陳述**，欄位名與文案一律帶「自責」。

自責分一律讀官方 `pitching_gamelog.earned_runs`，**本專案不重建自責分**（規則 9.16 要求反事實重播、內含「有疑慮時對投手有利」的裁量條款、繼承跑者按人數歸屬）。`game_livelog` 只用於**定位**中斷場的半局；所有不確定一律往「中斷」解讀，故輸出為**下界**。

賽別範圍：**只計例行賽局數**（一軍 A／二軍 D，不用 `KIND_GROUPS` 併入季後賽）。跨季時中間的季後賽出賽 ER=0 **跳過**（不計局數也不中斷）、ER>0 **中斷**——此規則使該值同時是「只算例行賽」與「一軍所有比賽都算」兩種讀法的下界。被跳過的場次必須對外揭露，不得沉默跳過。

- SSoT：`src/cpbl/models/scoreless_streak.py` 模組 docstring；窮舉對帳 `scripts/reconcile_scoreless_streak.py`。

## 當季累計快照

### `*_current` 口徑（team／batting／pitching／fielding_current）

官網「當季累計」四表**口徑不一致，勿一概當全年資料**。DB 實證（2026-07-27，本機 2026 kind A；球員表以 gamelog 分別聚合全季與 `game_season_code='2'` 對帳計數欄）：

| 表 | 口徑 | 佐證 |
|---|---|---|
| `team_current` | **當前半季**（官網 `/standings/season` 頁預設範圍） | 2026 全季聚合對帳**全數 FAIL**（max\|Δ\| 0.083）；改以 `game_season_code='2'` 聚合後 5/6 隊三圍逐位吻合（樂天殘差 0.0024 研判快照時點差）——[`TEAM-STYLE1_RESULTS.md`](../research/TEAM-STYLE1_RESULTS.md) §4 |
| `batting_current` | **全年** | 167 人中 166 人 G/PA/AB/H 四欄與全季聚合完全相等（唯一殘差為 1 安打差）；「吻合半季」的 7 人全是下半季才出賽者（兩口徑退化重合，非反證） |
| `pitching_current` | **全年** | 146 人中 145 人 G/SO/PA/BB/H 五欄與全季聚合完全相等（唯一殘差為 1 被安打差）；「吻合半季」的 10 人全是下半季才出賽者 |
| `fielding_current` | **非當前半季**（已證）；全年為合理推定，**未逐值對帳** | 出賽數上界：max g=73、107 人 g>20，遠超下半季單隊完成場上界 14；同 `/team/teamscoreaction` 端點同 Year 參數（僅 Position 異於 pitching），但無逐場守備 gamelog 可逐值對帳 |

- **`team_current` 勿當全年資料用**；全年團隊數據一律由 gamelog 聚合（單一路徑對帳先例：`/api/v1/season/team-split`，UX-TEAM-SPLIT-SCOPE1）。
- 口徑分家的機制：`fetch_team` 爬 `/standings/season`（GET、頁面預設＝當前半季）；球員三表走 `/team/teamscore(action)`（全季）——同在 `src/cpbl/ingest/cpbl_stats.py`。
- SSoT：本條目；證據出處 [`../research/TEAM-STYLE1_RESULTS.md`](../research/TEAM-STYLE1_RESULTS.md) §4（team）＋ DOC-TEAM-CURRENT-SCOPE1 查證紀錄（batting／pitching／fielding，2026-07-27 本機 DB）。
