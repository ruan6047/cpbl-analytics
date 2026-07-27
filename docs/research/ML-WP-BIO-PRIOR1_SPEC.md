# ML-WP-BIO-PRIOR1 預註冊 spec（凍結；先落此 commit 才開始計算）

- 卡片：`docs/tasks/ML-WP-BIO-PRIOR1.md`〔T3；輕量研究層〕
- 目的：把卡面「統計最低限」三件具體化成可執行、無自由度的協定。
  本檔 commit **先於**任何計算 commit；此後不得增刪特徵、不得改判準、不得掃網格。
- DB 全程唯讀；scratch 先跑、定稿才落 `docs/research/`。

## 1. 母體與協定（卡面第 1 件）

- 母體：`cpbl.games` kind_code='A'（一軍例行）、year 2018–2026、完成場判定
  `home_score + away_score > 0 AND game_date <= AS_OF`；**AS_OF = 2026-07-27（凍結）**，
  與 STRENGTH1 artifact `data_as_of` 相同 → 逐季母體逐場可對帳。
- 載入：直接 import `cpbl.models.winprob_strength.load_game_rows`（勿重寫）；
  隊伍四項特徵取其 `GameRow.team_feats`（賽前 running／prior 欄，leakage-safe）。
- 目標值 y：主隊勝 1／和 0.5／敗 0（沿 loader 慣例；擬合與 Brier 同口徑）。
- 協定：對每個驗證季 Y ∈ {2023, 2024, 2025, 2026}，fit 窗 = 2018..Y−1 全部完成場
  → 只評 Y。模型 = L2 邏輯斯迴歸（沿 `fit_logistic_l2`：fit 窗標準化、intercept
  不懲罰、決定性 Newton），**λ = 100 一組，不掃網格**。收縮參數 kappa 不使用
  （七項特徵皆不經 starter 投球率收縮路徑）。

## 2. 特徵七項（凍結；執行前不得增刪）

方向一律「主 − 客」。

| # | key | 定義 |
|---|-----|------|
| 1 | `prior_winpct_diff` | 沿 STRENGTH1 `team_feats`（主−客上季最終勝率） |
| 2 | `winrate_diff` | 沿 STRENGTH1 `team_feats`（套用該場結果前的本季勝率差） |
| 3 | `run_margin_diff` | 沿 STRENGTH1 `team_feats`（場均得分差 − 場均失分差） |
| 4 | `rest_days_diff` | 沿 STRENGTH1 `team_feats`（賽前休息天數差） |
| 5 | `starter_age_diff` | 主先發年齡 − 客先發年齡；年齡 = (game_date − players.birthday).days / 365.25 |
| 6 | `starter_import_diff` | 主先發身分值 − 客先發身分值；見 §3 |
| 7 | `starter_seniority_diff` | 主先發年資 − 客先發年資；見 §4 |

先發 = `games.home_starter_id` / `games.away_starter_id`（母體內無 NULL，已對帳）。

## 3. 身分（卡面第 2 件；canonical 判定）

- 用 `cpbl.imports.classify(player_id, players.country)`（canonical，含羅力／永田
  條款 override）；**禁用** `country != '中華民國'` 粗規則。
- 二值化（凍結）：`{"import", "loree"} → 1`；`{"local", "nagata"} → 0`。
  理由：機制假設是「外籍職業補強池的先發平均強於本土」——羅力條款（羅力／伍鐸）
  是洋將名額的行政豁免、其人才來源仍是外籍職業補強；永田條款（高塩將樹）出自
  台灣學生棒球體系選秀，人才池與本土同。
- **已知資料缺陷（誠實揭露，不改協定）**：canonical `classify` 對 `country IS NULL`
  保守回 `local`。母體內 14 位缺生日的先發**同時**缺 country（皆為 2025 年短期
  洋將，音譯名），故 2025 有 144 場的身分特徵被 canonical 規則標為本土。本卡
  照凍結協定執行（canonical 判定就是卡面規則），此缺陷於 memo 與 artifact 逐年
  計數揭露，作為 2025 season 解讀 caveat；**不得**因結果不理想而事後改判定重跑。

## 4. 年資（卡面第 2 件）

- 年資 S = game_year − min(year)（該 player_id 於 `cpbl.pitching_seasons` 中
  year < game_year 的最小年份）；查無 year < game_year 的列 → S = 0（含當季
  初登板與零 CPBL 前史洋將）。只用嚴格早於比賽年的列 → 賽前可得、無洩漏。
- **不用** `players.debut`（覆蓋僅 65%，卡面禁用）。

## 5. 生日缺值 fail-closed 規則（卡面第 2 件；凍結，二選一已選定）

- 規則：**聯盟均值中性填補**（不排除場次）。缺生日的先發，其年齡以「fit 窗
  2018..Y−1 內全部非缺值先發席次（per-slot，逐場計）年齡均值」填補；同一 Y
  迭代內，fit 窗與驗證季用同一個填補值（該值只由 fit 窗算出 → 賽前可得）。
- 選擇理由：整場排除會使 2025 驗證母體掉 144/359 場，與主場常數基準及
  STRENGTH1 母體失去可比性；中性填補保母體完整，且該 14 位年資恰為 0、
  身分依 §3 canonical 規則處理，特徵向量仍完整。
- 揭露義務：逐年「受影響場數」與「缺值先發席次數」入 artifact 與 memo。

## 6. 基準與判準（卡面第 3 件；三項同時成立才過關）

- 基準：leakage-safe 主場常數 p_c(Y) = 2018..Y−1 完成場主隊得點率
  （勝 1／和 0.5；沿 `home_rate_exact`，未捨入）；逐場 Brier = (p_c(Y) − y)²。
- 評分：驗證季 Y 逐場 p_model 與 p_c(Y) 各自算逐場 Brier；池化 = 2023–2026
  全部驗證場合併（各場用各自 Y 的模型與常數）。
- bootstrap（凍結）：逐場（game-level）重抽、**reps = 10000**、percentile CI、
  **99%**；索引法沿倉內慣例 `sorted[int(q*(n−1))]`。seed：池化 = **20260727**；
  逐年診斷 = 20260727 + Y。配對量 Δ_g = (p_model−y)² − (p_c−y)²，CI 對 Δ 的
  game 平均。
- **判準（未捨入值判定）**：
  - C1 池化：pooled Brier(model) < pooled Brier(const)。
  - C2 池化：Δ 的 99% 逐場 bootstrap CI 排除 0 且方向為改善（CI 上界 < 0）。
  - C3 2026 方向檢查：「顯著反向」定義 = Δ(2026) 點估計 > 0 **且** 2026 子集
    99% 逐場 bootstrap CI 下界 > 0。顯著反向 → 不過關。（點估計 > 0 但 CI 含 0
    → C3 通過，但 memo 必須揭露方向警訊。）
  - 三項同時成立才過關；差一項即 No-Go，不得事後解釋或改協定重跑。

## 7. 對照與對帳（完整性宣稱窮舉）

- 與 STRENGTH1 卡面八項對照：引 `docs/research/game_recap_wp_strength1_metrics.json`
  `prior_signal_diagnostics` 的 `out_of_time` vs `home_const`（同母體、同 as_of），
  不重跑八項。
- 母體對帳：逐年 SQL 完成場數 vs 實際評分場數必須相等（腳本 assert）；
  逐年缺生日場數／席次、身分分布逐年入 artifact。

## 8. 產出與可重現

- 腳本：`scripts/wp_bio_prior1.py`（唯讀 SELECT；`--out` 可導向 scratch）。
- artifact：`docs/research/ml_wp_bio_prior1_metrics.json`；memo：
  `docs/research/ML-WP-BIO-PRIOR1_MEMO.md`（數字一律出自腳本輸出）。
- 單元測試：年齡／年資／身分二值化／中性填補的純函式測試。
- 驗證：`uv run ruff check` + `uv run pytest -q` 全綠。
