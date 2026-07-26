# ML-OUTCOME-LEAK1 交付紀錄：先發特徵前視洩漏的量化與修正

> 卡面：[`docs/tasks/ML-OUTCOME-LEAK1.md`](../tasks/ML-OUTCOME-LEAK1.md)　執行分支：`ai/opus-5/ML-OUTCOME-LEAK1`
> 本檔是卡面統計最低限第 3 條要求的**一次性「修正前（含洩漏）vs 修正後」留痕**。
> 準確率下降是本卡目的：下降幅度即洩漏貢獻的量化。

---

## §1 修了什麼

`features/outcome.py` 的 `starter_era_diff`／`starter_whip_diff`／`starter_k9_diff`
原本以 `(starter_id, year)` 讀 `pitching_seasons`／`pitching_current` 的**同季彙總**——
歷史回測的模型因此在賽前看見該投手該季之後的表現（前視洩漏；實證見
[`GAME-RECAP-WP-STRENGTH1_RESULTS.md`](GAME-RECAP-WP-STRENGTH1_RESULTS.md) §6.2）。

改為**賽前 as-of**（機制參照 `models/winprob_strength.py` 已驗證的兩段式累積）：

1. **逐場 running state**：由 `pitching_gamelog`（kind A，2018+）依 `(game_date, game_sno)` 走查，
   **快照賽前 state 之後才套用本場計數**；每季歸零。
2. **前一季 prior 收縮**：`_shrink(num, den, prior_rate, κ) = (num + κ·prior) / (den + κ)`，
   κ = `STARTER_KAPPA_IP` = 30 IP（≈5 場先發）。**開跑前釘死、不隨回測數字調整。**
3. **兩層池化**：前一季率本身先向前一季聯盟率收縮，再當本季 running state 的 prior。
   少了這層，只投 1–2 局的前一季紀錄會產生 ±50 的 ERA 離群值（實測 sd 2.035 → 0.971）。
   這是分布穩定性的結構決策，與回測數字無關。
4. **fallback 順序**：前一季同口徑 → **前一季**聯盟率 → 全史首季的固定墊檔常數。
   2018 前無逐場 box，本季分母為 0 ⇒ 恰好退回前一季值，全史 9,808 列無 NULL、訓練母體不縮。
5. 一併修掉既有誤差：`pitching_seasons.ip` 是棒球記法（`.1` = 1/3 局），舊版 `_prior_era`
   直接把 `.1` 當 0.1 相除。新版走 `_ip_decimal()`。

**欄名沿用**（`starter_*_diff`），故 `models/outcome.py` 互動探索器、`models/outcome_gbm.py`、
`models/outcome_simple.py` 自動改讀新語意，無需改動；`FEATURE_DESC` tooltip 已同步改寫為
「開打前的本季至今…季初以上季成績按比例收縮墊檔」。

---

## §2 修正前後對照（同一份程式碼路徑，只換 `game_features`）

重現：`uv run cpbl-build-features` 後於容器內跑
`python scripts/outcome_leak_compare.py <out.json>`（只讀不寫 `model_versions`）。

### 2.1 `cpbl-train-outcome` 走查回測（test 2022–2026，pool n = 1,508）

| 模型 | 準確率（前） | 準確率（後） | Δ | Brier（前） | Brier（後） | Δ |
|---|---:|---:|---:|---:|---:|---:|
| **全押主場（基準）** | 0.5285 | 0.5285 | ±0 | 0.2494 | 0.2494 | ±0 |
| 全特徵邏輯回歸 | 0.6247 | **0.5524** | **−0.0723** | 0.2315 | 0.2463 | +0.0148 |
| LightGBM（全特徵） | 0.6160 | **0.5550** | **−0.0610** | 0.2327 | 0.2467 | +0.0140 |

修正後仍勝過全押主場（`beats_baseline = true`），但優勢從 ~9pt 降到 **~2.6pt**。
LogLoss：LightGBM 0.6578 → 0.6868，基準 0.6919。

### 2.2 互動探索器 `models/outcome.py`（test 2026，n = 213，基準 0.5211）

| 特徵組合 | 準確率（前） | 準確率（後） | Δ |
|---|---:|---:|---:|
| 主場 + 先發 ERA/WHIP/K9 | 0.6338 | **0.5634** | **−0.0704** |
| 主場 + 季內勝率 + 先發 ERA | 0.6338 | **0.5634** | **−0.0704** |
| 主場 + 季內勝率（**對照組：不含先發**） | 0.5634 | 0.5634 | **±0** |

第三列是關鍵對照：不含先發特徵的組合前後**完全相同**，證明變動被隔離在三個先發欄，
不是整條特徵管線位移。

### 2.3 洩漏貢獻的量化結論

單場勝負的真實賽前預測力，扣掉洩漏後只剩 **2.4–2.6pt**（相對全押主場）。
先前線上宣稱的 ~62% 中，約 **6–7 個百分點來自前視洩漏**。

---

## §3 `model_versions(task='outcome')` 新列

```
id         outcome-1785092639
task       outcome
algo       lightgbm-vs-logistic
trained_at 2026-07-26T19:03:59.334592+00:00
params     {"features": [19 項 real features], "test_seasons": [2022,2023,2024,2025,2026]}
cv_metrics {"best": "LightGBM（全特徵）", "beats_baseline": true,
            "n_train": 9185, "n_test": 1508, "home_rate_test": 0.5285,
            "models": [全押主場 .5285/.2494/.6919,
                       全特徵邏輯回歸 .5524/.2463/.6859,
                       LightGBM（全特徵） .5550/.2467/.6868], "importance": [...]}
```

`GET /api/v1/outcome/backtest` 已回傳此列（本機實測）。`/predict` 舊路由已退場並轉址至
`/methodology#pregame`，該頁 benchmark 面板即以此端點驅動；離線 fallback 快照文案同步改為
1,508 場／55.2%／55.5%／52.9%，並註明舊 62.8%／61.3% 含洩漏。

---

## §4 ⚠️ 卡面前提不完整：受影響的不只 benchmark 面板

卡面稱「`/predict` 面板…是目前唯一『已知錯誤仍在線上展示』的宣稱」。實測**不成立**：
上線的固定語意群賽前模型 `outcome_simple`（`/methodology#pregame` 的主展示、`pregame` 卡片
點機率的來源）四個訊號之一就是 `starter_era_diff`，同樣吃到這個洩漏。

同一支比較腳本（test 2021–2025，n = 1,585）：

| 模型 | 準確率（前） | 準確率（後） | Brier（前） | Brier（後） |
|---|---:|---:|---:|---:|
| home_baseline | 0.5281 | 0.5281 | 0.24937 | 0.24937 |
| full_logistic | 0.6114 | 0.5464 | 0.23654 | 0.25067 |
| lightgbm | 0.6132 | 0.5489 | 0.23579 | 0.24775 |
| **fixed_semantic（上線模型）** | **0.6126** | **0.5584** | **0.23203** | **0.24496** |

部署閘門：**7/7 通過 → 6/7（`calibration_slope` 1.054 → 1.374，超出 [0.8, 1.2]）**，
`deployable: true → false`。配對週區塊 bootstrap 的 Brier 差 95% 區間
[−0.0229, −0.0121] → [−0.0068, −0.0019]（仍全負，但效果量掉到約 1/4）；
勝過基準的測試季 5/5 → 4/5。

**本卡未重跑／未持久化 `outcome_simple`**，理由：

- 卡面 DB scope 明列 `model_versions(task='outcome')`，未含 `outcome_simple`；
- 重跑會把一個**已上線且已過閘門**的模型翻成「未達可部署標準」，且
  `run_train_outcome_simple.main()` 在閘門失敗時**不更新 serving artifact**
  → 會出現「指標已修正、serving 仍是洩漏訓練的 artifact」的半套狀態。這是產品裁定，不是執行者裁定。

**部署前的硬性相依（阻塞）**：`scripts/refresh-cpbl-prod.sh` 會在本機
`cpbl-build-features` 後把 `game_features` 鏡像到 production，並在 VPS 重跑
`cpbl-train-outcome`——但**不會**重跑 `cpbl-train-outcome-simple`。因此本分支一旦上線並跑過
一次 refresh，production 的 `outcome_simple` serving artifact（係數與 scaler 皆 fit 於洩漏特徵）
會被餵入修正後的特徵分布，屬 serving 端的分布錯配，不只是展示不一致。
**合併／部署前必須先由需求方裁定 `outcome_simple` 的處置**（重訓並接受閘門失敗、改選訊號、
或暫時退場）。建議另開卡。

---

## §5 賽前可得性的離線證明

`tests/test_outcome_starter_features.py`（4 passed；風格比照 `tests/test_winprob_strength.py`
的 running-state 合約測試，以 fake cursor 離線驗證）：

| 測試 | 關鍵斷言 |
|---|---|
| `test_starter_running_state_excludes_the_game_itself_and_future_games` | 主隊先發第 1 場被打爆、第 2 場完美。第 1 場三欄 `== approx(0.0)`（雙方皆無本季分母 → 同一聯盟率）；第 2 場等於「只用第 1 場」獨立重算的值，且 `starter_era_diff > 0`。洩漏版兩場會看到同一個整季 ERA ⇒ 第一條斷言必然失敗。 |
| `test_season_boundary_resets_running_state_and_prior_is_previous_year_only` | 2020 開季首戰當季分母歸零，值恰等於「以 2019 總量為 prior」的封閉解；2019 首戰仍為 0。 |
| `test_shrink_falls_back_to_prior_then_league_and_yields_to_current_season` | 無當季無前一季 → 恰為前一季聯盟率；當季分母遞增時 ERA 單調趨近當季自身率。 |
| `test_ip_notation_converts_thirds_not_decimals` | `140.1 → 140⅓`、`140.2 → 140⅔`。 |

`materialize()` 全史重建 9,808 列（completed 9,647）；`starter_era_diff`
mean −0.0029、sd 0.9707、值域 [−4.72, +4.02]。

---

## §6 未盡事項

1. **`outcome_simple` 的處置**（§4）——部署前阻塞項，需需求方裁定。
2. **`models/matchup.py` 的對戰卡**仍用 `pitching_current` 的當季彙總顯示先發 ERA/WHIP/K9。
   對**未開打**場次而言那是賽前可得值、無洩漏，但與訓練分布（收縮後 sd 0.97）不同尺度，
   `z = (值 − mean) / std` 會被高估。本卡未動（卡面 scope 只含探索器）；若要一致化，
   應讓 matchup 改用同一支 `_starter_rates`。
3. 時間切分協定未動（既有 walk-forward），κ 未調參，未新增或移除任何特徵。
4. 未同步 production DB、未部署（依卡面紅線）。`scripts/refresh_status.py check` 語意不受影響：
   本卡未改 refresh 腳本或其 exit code，`cpbl-build-features` 仍是 refresh 流程中的同一步。
