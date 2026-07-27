# TEAM-STYLE1 球隊球風研究 — 描述性風格向量

- 卡片：`docs/tasks/TEAM-STYLE1.md`〔T4；🔴統計〕
- 執行：Claude Opus 5（iteration 1）　分支：`ai/opus-5/TEAM-STYLE1`
- 消費表面：球隊頁「球風」區塊（標籤或雷達）——本報告是它的統計基礎。
- **性質聲明：本研究為純描述性 [descriptive]。所有軸值描述「這支球隊打球的樣子」，
  不對賽果、勝率或任何未來表現做任何宣稱；候選特徵是否進 outcome 模型屬另一張卡
  （須增量回測勝出），與本報告無關。**

---

## 0. 預註冊規格（凍結）

> 本節在任何計算執行之前寫死並先行 commit（以 git 歷史為證）。執行中不增刪軸、
> 不改判準；若某軸資料不支撐，標記「不成立／不穩定」保留在報告裡，不刪除。

### 0.1 樣本邊界

| 項目 | 定義 | 理由 |
|---|---|---|
| 賽別 | `kind_code = 'A'`（一軍例行賽） | 卡面指定主體；季後賽樣本極小且語境不同 |
| 完成場 | `home_score + away_score > 0 AND game_date <= CURRENT_DATE`（引用 `src/cpbl/completion.py` `completed_games_sql()`，GLOSSARY SSoT） | 保留賽掛未來日期卻帶比分，缺日期界線會誤判 |
| 年份 | 2018–2026 | `batting_gamelog`/`pitching_gamelog` 自 2018 起完整（逐年覆蓋已實查：2018–2026 kind A 每年皆有資料）；季彙總表雖有 1990+ 但無法做季內分半穩定性檢定，故不採 |
| 2026 特別處理 | 軸值照算（消費表面要顯示本季），但**排除於全部穩定性檢定**（分半、跨季自相關） | 進行中球季樣本不完整，混入會污染穩定性估計 |
| 資料來源 | `cpbl.batting_gamelog`、`cpbl.pitching_gamelog` join `cpbl.games`；隊別歸屬用 `visiting_home_type`（'2'=主隊、'1'=客隊，SSoT：`src/cpbl/ingest/run_refresh_recent.py` 註解與 `championships.py` 同款 join） | 單一路徑；全部軸出自同兩張表，避免多來源口徑混雜 |

**母體對帳（計算前查定）**：kind A 完成場的隊季母體＝
2018–2020 各 4 隊、2021–2023 各 5 隊、2024–2026 各 6 隊 → **45 隊季**。
artifact 必須逐年列出「games 完成場數 vs gamelog 實際覆蓋場數」對帳表；
任何「全部隊季已計算」的宣稱以 45 列窮舉為準。

### 0.2 風格軸定義（7 軸，凍結）

原始值一律為**隊季（或半季）加總後的比率**（sum-of-counts 相除，非逐場比率平均）。
`BB` 欄位含故意四壞（`splits_calc.py` L99「故四」同時累加 bb 與 ibb，故 gamelog `bb` 已含 `ibb`，不重複相加）。
IP 出局數 = `inning_pitched_cnt * 3 + inning_pitched_div3`（SSoT：`splits_calc.py` §pitching）。

| # | 軸名（代碼） | 一句話（給一般球迷） | 計算式（隊季原始值） | 來源 |
|---|---|---|---|---|
| 1 | 速度戰（`speed`） | 上壘後有多愛啟動盜壘 | 盜壘企圖率 = (SB + CS) / (一壘安打 + BB + HBP) | batting_gamelog |
| 2 | 短打戰術（`smallball`） | 多常用犧牲短打換推進 | 犧短率 = SH / PA | batting_gamelog |
| 3 | 長打火力（`power`） | 進攻多依賴長打的額外壘打 | ISO = (TB − H) / AB | batting_gamelog |
| 4 | 選球紀律（`discipline`） | 多選保送、少吃三振 | 複合軸 = mean( z(BB/PA), −z(SO/PA) ) 後再季內重新標準化 | batting_gamelog |
| 5 | 先發吃局（`starter_ip`） | 先發投手吃局的深度 | 先發局數佔比 = 先發(role_type='先發')出局數 / 全隊投手出局數 | pitching_gamelog |
| 6 | 三振型投手（`pitch_k`） | 投手群靠三振解決打者的比例 | K% = 被三振數 / 面對打席數 | pitching_gamelog |
| 7 | 守備效率（`defense`） | 把場內球轉成出局的效率 | DER = 1 − (被安打 − 被HR) / (面對PA − BB − HBP − K − 被HR) | pitching_gamelog |

極性凍結：**每軸值越高＝該風格越強**（defense 越高＝守備效率越好）。

**預先排除項（非事後刪除）**：積極出棒／首球揮擊率——`pitch_tracking` 僅 2026
且球場設備覆蓋不全（花蓮/嘉義無設備），無法做跨季穩定性檢定，本卡不納入；
留待逐球覆蓋成熟後另立卡。

### 0.3 Normalization（凍結）

- **季內聯盟 z-score**：每軸在「同一球季全部球隊」內做 z = (x − mean) / std，
  std 用母體標準差（ddof=0）。跨季 raw 值不可比是已知事實，一律以季內 z 呈現。
- 單成分軸：z(raw)。複合軸（僅 `discipline`）：成分先各自季內 z，取平均後**再做一次
  季內 z**，使全部軸同尺度。
- 退化保護：若某季某軸 std = 0（各隊同值），該季該軸 z 一律為 0。
- 分半穩定性計算時，z 在「同季同半」內做（跨隊標準化），與全季 z 同式。

### 0.4 穩定性判準（凍結；先於計算寫死）

1. **季內分半穩定性**：每隊季將完成場依 (game_date, game_sno) 排序，
   前 n//2 場為 H1、其餘為 H2；各半算原始軸值 → 季內半內 z → 對 2018–2025
   全部隊季（4×3 + 5×3 + 6×2 = 39 觀測）算 Pearson r（H1 vs H2）。
   判讀帶：r ≥ 0.5 高穩定；0.3 ≤ r < 0.5 中度；r < 0.3 標記**不穩定**（保留並標記，不刪軸）。
2. **跨季自相關**：同一 franchise 的季 z 值，t vs t+1 配對（t 自 2018 至 2024，
   t+1 ≤ 2025；2026 排除）。franchise 對映凍結：`AJK011`（Lamigo）→`AJL011`（樂天）
   視為同一 franchise；味全 2021、台鋼 2024 為擴編首季，無 t−1 配對。
   預期配對數 = 4+4+4+5+5+5+6 = 33（artifact 逐對窮舉驗證）。
   判讀帶：r ≥ 0.3 中度延續；0.1 ≤ r < 0.3 弱；r < 0.1 無延續訊號。
   先驗預期：陣容延續下應有中度相關；未達即如實標記。
3. **Face validity 抽查（隊季先選定，凍結後才看結果；判準：該軸該季排名前 2 名＝PASS，否則 FAIL 照實報告）**：
   - **2023 味全龍** → `smallball` 排名 ≤ 2（葉君璋時期以短打小球戰術聞名，媒體廣泛報導）。
   - **2019 Lamigo 桃猿** → `power` 排名 ≤ 2（隊史著名重砲打線時期）。
   - **2021 中信兄弟** → `starter_ip` 與 `pitch_k` 至少一軸排名 ≤ 2（該年洋投先發輪值宰制、奪總冠軍）。

### 0.5 QA baseline（凍結）

- 逐年對帳：`games`（kind A 完成場）場數 vs `batting_gamelog`/`pitching_gamelog`
  distinct 場數，必須全等，否則在報告標記缺口。
- 口徑交叉驗證：以本管線聚合出的 2026 隊打擊三圍（AVG/OBP/SLG）對 `cpbl.team_current`
  （官網爬回的官方值）逐隊比對，差異須在捨入誤差內（|Δ| ≤ 0.002），驗證聚合路徑無誤。

### 0.6 產出與重跑

- 可重跑腳本：`scripts/team_style_vectors.py`（唯讀 SELECT；CLI 一鍵重算）。
- 機器可讀 artifact：`docs/research/team_style1_metrics.json`（規格回聲＋母體對帳＋
  45 隊季 × 7 軸向量（raw+z）＋穩定性統計＋face validity＋QA 對帳）。
- 本報告所有數字表格由腳本產生（stdout markdown）貼入，不人工謄寫。
- 單元測試：`tests/test_team_style.py`（z-score 數學性質、軸計算式封閉解、
  Pearson r 正確性、分半切法）。

---

## 1. 結果

（spec commit 後由腳本產出補入——本 commit 為預註冊版，尚未執行任何計算。）

## 2. 穩定性檢定

（待補）

## 3. Face validity 抽查

（待補）

## 4. 母體對帳與 QA

（待補）

## 5. 限制與後續

（待補）
