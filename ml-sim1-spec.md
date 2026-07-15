# ML-SIM1：簡易勝負預測與單一打席情境模擬規格

## 目標

以可校準、可解釋且不重複計票的方式，取代目前 `/predict` 的自由特徵勾選與手調權重：

1. 賽前模式提供固定的主／客勝率，揭露實際訊號、方向、訓練期間、回測與不確定性。
2. 打席模式提供指定投手 × 打者的互斥結果機率，將每種結果映射為下一個局面，再以既有 `wp_state()` 計算結果後主隊勝率與加權勝率。

本卡是統計／ML 紅線。模型未通過時間走查、校準與資料覆蓋閘門時，只回傳研究結果，不接公開 UI。

## 既有事實與限制

- 賽前資料：`cpbl.game_features`，所有欄位皆於該場結果套用前產生。
- 場中資料：`cpbl.game_livelog` 自 2018 年起可重建打席前後壘況、出局與比分；實際涵蓋率須在實作前由本機 DB 稽核，不以文件敘述代替。
- 勝率引擎：`cpbl.models.winprob.wp_state()` 使用 2018–前一完整季的一軍 `run_dist` 與 12 局和局規則。
- `batting_action_name` 已有 `PA_OUTCOME` 詞彙表，但它是官方打擊統計分類，不等同完整的狀態轉移；安打後跑者推進、雙殺與犧牲打不能用單一固定規則猜測。
- API 維持唯讀；訓練、資料稽核與模型持久化均由離線 CLI 執行。

## 模式 A：固定賽前勝負預測

### 訊號設計

固定使用五個語意群，每群只產出一個模型欄位。候選代表訊號只能以時間走查決定，不得在全資料上挑選後回報同一批測試結果。

| 語意群 | 第一版候選 | 定向 | 去重複規則 |
|---|---|---|---|
| 整體戰力 | 上季勝率差；季內累積勝率差 | 正值有利主隊 | 兩者不得同時進模型；季初與季中若需融合，先定義單一 shrinkage 合成值 |
| 打線 | 場均得分差；OPS 差 | 正值有利主隊 | AVG、SLG、OPS、得分不得同時作為獨立證據 |
| 失分抑制／先發 | 場均失分差；先發 ERA／WHIP／K9 | 經定向後正值有利主隊 | ERA、WHIP、失分不得並列；若合成先發品質，公式須先固定 |
| 賽程 | 休息天數差 | 正值有利主隊 | 近況與季內勝率不另重複加入 |
| 主場 | 截距 [intercept] | 主場基準 | 不建立常數特徵欄，不經標準化 |

第一版模型使用 L2 正則邏輯回歸 [logistic regression]。理由是輸出需校準、方向可審核、樣本僅約萬場級且訊號刻意壓到四個實欄；LightGBM 保留為既有全特徵比較組，不作產品模型預設。

### 時間走查與模型選擇

- 外層走查：最近 5 個完整賽季逐季 `train(<season) → test(season)`；2026 未完整賽季不列入正式驗收。
- 代表訊號選擇：只在每個外層訓練集內以較早賽季做內層走查，依平均 Brier 最小決定每群代表或固定合成公式。
- 缺值：在每個訓練 fold 內，以中性值／訓練集統計填補；不得從測試季估計填補值。
- 校準：先驗證原始邏輯回歸；只有 out-of-fold reliability curve 顯示系統性偏差時，才在內層資料上比較 Platt／isotonic，並把校準器一併走查，禁止用測試季校準。
- 不確定性：以「季內曆週」為 block 做 paired bootstrap（同一抽樣索引套用全部比較模型），回報整體指標差值的 95% CI；每場預測另以 bootstrap refit ensemble 的 5th–95th percentile 作模型敏感度區間，不把它宣稱為不可約賽果區間。

### 比較組與上線閘門

同一 test pool 必須比較：

1. 全押主場：機率取該 fold 訓練集主場勝率。
2. 既有全特徵邏輯回歸。
3. 既有全特徵 LightGBM。
4. 本卡固定去重複邏輯回歸。

每組回報 Accuracy、Brier、LogLoss、校準截距／斜率、ECE 與 reliability bins。產品模型必須同時滿足：

- pooled Brier 與 LogLoss 都優於全押主場；95% block-bootstrap CI 至少不顯示明確劣化。
- 至少 3/5 個外層測試季的 Brier 優於全押主場，避免單季偶然勝出。
- 校準斜率落在 `[0.8, 1.2]`、截距落在 `[-0.1, 0.1]`；若未達標，只能標示研究版。
- 固定模型若未勝 baseline，不上線，現有公開互動探索器也不以新包裝保留。

### 產物與 API

- 新離線 CLI：`cpbl-train-outcome-simple`，持久化 `model_versions(task='outcome_simple')`；artifact 含 scaler、model、calibrator（若有）、訊號定義與訓練截止日。
- `GET /api/v1/outcome/pregame`：近期真實賽事固定預測；不得接受 features／weights。
- `GET /api/v1/outcome/pregame/backtest`：回傳版本、樣本期間、四組指標、校準與訊號 metadata。
- 舊 `/evaluate`、`/features`、帶 features 的 `/matchups`、`/simulate` 先保留相容，但新 UI 不再呼叫；刪除另開 migration/deprecation 卡。

## 模式 B：單一打席情境模擬

### 互斥結果

第一版結果空間固定為：`K`、`BB_HBP`、`1B`、`XBH`（2B/3B）、`HR`、`BIP_OUT`、`OTHER_REACH`。總和必須為 1；犧打、犧飛、雙殺、失誤等實際下一狀態差異由轉移核處理，不以結果名稱暗示固定跑者推進。

### 機率模型

- 母體：一軍例行賽、已完成且可完整辨識打席邊界與結果的 2018–前一完整季資料。
- 模型：分層 Dirichlet-multinomial empirical Bayes。聯盟結果率為先驗；打者面與投手面各依有效 PA 自動 shrink；直接投打對戰只在樣本足夠時作第三層修正。
- 合成在 centered log-ratio 空間進行：`clr(hitter) + clr(pitcher_allowed) - clr(league)`，直接對戰層再加入相對於前述組合的 shrinkage correction，最後 softmax 正規化。這等價於在 composition 上加入打者與投手偏移，避免原始機率直接相乘後失真；所有 pseudo-count／prior strength 只由訓練 fold 決定。
- 截止日：正式 artifact 只使用前一完整季以前資料；真實打席 deep-link 選擇 `trained_through < game_date` 的最新 artifact，禁止看見該場或未來結果。任選情境回傳 artifact 的 `trained_through`；若未來要混入本季 running counts，另開資料物化卡，不在 API request 時掃全史重 fit。
- 最低樣本不以硬切換製造跳變；API 回傳 hitter／pitcher／direct PA、shrinkage weight 與 `low_sample`。直接對戰層預設需至少 20 PA 才能產生可見影響，最終門檻以訓練集敏感度分析固定。

### 狀態轉移

每筆歷史打席重建：

`(half, bases_before, outs_before, score_diff_before, result) → (runs_delta, bases_after, outs_after, inning_ended)`

- 轉移核以 `result + bases_before + outs_before` 分桶；樣本不足時依序退化為 `result + outs`、`result`，並回傳使用層級與樣本數。
- 每個 outcome 可對應多個實際 next-state；以經驗分布逐一呼叫 `wp_state()`，不能把一壘安打、出局或雙殺簡化成單一 deterministic state。
- 若打席結束半局，轉為下一半局空壘 0 出局；9 局後免打下半、再見與 12 局和局沿用 `winprob.py` 規則。
- 結果加權整場勝率：`Σ P(outcome) × Σ P(next_state | outcome,state) × WP(next_state)`。
- 額外回傳每結果的 `delta_wp`，但不模擬再下一位打者、牛棚或完整陣容。

### 驗證與 API

- 資料稽核：逐年 games／PA 數、可分類率、可重建 next-state 率、未知詞彙表；任一年分類率或狀態重建率低於 99% 即 fail-closed。
- 機率驗證：按賽季走查，回報 multiclass LogLoss、Brier、各類 reliability bins；比較聯盟常數率與僅打者／僅投手模型。
- 轉移驗證：對留出季逐打席重播；比較預測 next-state 分布，並驗證加權 WP 對實際下一狀態 WP 的 MAE／Brier。
- `GET /api/v1/outcome/plate-appearance`：接受 hitter、pitcher、inning、half、score、bases、outs 與可選 cutoff。
- `GET /api/v1/outcome/plate-appearance/from-game`：接受 `year+kind_code+game_sno+main_event_no`，由 DB 解析投打者與打席前狀態；無法唯一定位或資料不完整時回明確 error，不猜測。
- 新離線 CLI：`cpbl-train-pa-sim`，為各驗證／服務 cutoff 建立 empirical-Bayes counts、轉移核與 metadata artifact；API 只載入 artifact 與查詢指定打席，不在 request 內訓練。

## 實作切片

1. 先做唯讀資料稽核與 PA snapshot builder，產出覆蓋率報告。
2. 建立賽前固定模型的 nested walk-forward backtest，確認候選訊號與上線閘門。
3. 建立打席分類、分層機率與 leakage-safe cutoff 測試。
4. 建立經驗轉移核，對人工列舉與歷史留出打席驗證狀態轉移。
5. 接兩組唯讀 API、route snapshot 與契約測試。
6. 跑 `uv run ruff check`、`uv run pytest`；LightGBM 對照與正式回測在容器內執行。
7. 由非 GPT 家族模型或人審獨立重跑資料稽核、走查與狀態轉移實測；通過後才可交 UX 卡。

## 邊界

- 必做：所有 fit／fill／calibration／signal selection 僅看該 fold 訓練資料；缺資料 fail-closed；輸出資料截止日與不確定性。
- 需另行核可：新增 migration、增加第三方 ML 套件、變更 `wp_state()` 規則、移除舊 API。
- 禁止：完整陣容／牛棚／後續打席模擬、賭盤比較、宣稱擊敗市場、用 Monte Carlo 包裝未經校準的輸入。

## 完成條件

- 賽前模型通過 baseline、跨季穩定性與校準閘門，或明確產出「不上線」結論。
- 打席結果機率與狀態轉移通過走查、覆蓋率與 leakage 測試。
- API 完整揭露 signal／sample／cutoff／uncertainty，且舊 API 無破壞性變更。
- 跨模型家族或人審完成統計與狀態轉移獨立實測。

## 待核可決策

1. `OTHER_REACH` 是否保留獨立結果，或併入 `BIP_OUT` 但改名為 `OTHER_BIP`。
2. 固定賽前模型是否接受「Brier、LogLoss 優於 baseline，但 Accuracy 持平」上線；本規格建議接受，因勝率產品優先評估機率品質。
3. 本卡是否只交後端模型/API；`/predict` 與首頁視覺重製留給 UX-OUTCOME-HOME。本文建議切開，維持紅線模型與 UI 審核獨立。
