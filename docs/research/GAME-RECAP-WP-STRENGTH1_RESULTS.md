# GAME-RECAP-WP-STRENGTH1 場中 WP 戰力感知先驗 — 結果與 Go/No-Go

- 卡片：[`GAME-RECAP-WP-STRENGTH1`](../tasks/GAME-RECAP-WP-STRENGTH1.md)〔T4；🔴統計〕　scope：**A 一軍例行**
- 程式：[`src/cpbl/models/winprob_strength.py`](../../src/cpbl/models/winprob_strength.py)　測試：[`tests/test_winprob_strength.py`](../../tests/test_winprob_strength.py)
- 機器 artifact：[`game_recap_wp_strength1_metrics.json`](game_recap_wp_strength1_metrics.json)
- 前置：[`WP-VAL1`](GAME-RECAP-WP-VAL1_RESULTS.md)（全 scope unsupported）→ [`WP-CAL1`](GAME-RECAP-WP-CAL1_RESULTS.md)（事後校準 No-Go）→ 本卡（VAL1 §7 路徑 2）
- 全程唯讀 DB；未修改 `winprob.py`、`winprob_val.py`、`winprob_cal.py`、public API、前端或任何 production artifact。

---

## §0 裁決

<!-- generated:verdict start -->
> **A scope（局面 WP ＋ 戰力感知先驗融合）＝ unsupported（No-Go）。**
> `GAME-RECAP-WP-API1` 的 A 範圍**維持阻塞**。

| 硬門檻 | 結果 |
|---|---|
| 各驗證季 coverage ≥ 0.98（**含 effective coverage**） | ✅ 2023–2025 皆 **1.000000**；2026 **0.986301**（3 場尚無 published PA build） |
| 融合後 Brier 勝主場常數基準 | ✅ 四季皆勝（幅度 0.081–0.096） |
| **融合後 Brier 不得劣於同代未融合 base** | ❌ **2023（+0.000444）**；**2025（+0.001479）** 劣於 base |
| 池化十分位 n≥1000：\|dev\|≤0.03 或 99% CI 含 0 | ✅ 通過（**但見 §6 的重要但書**） |
| 池化局帶 n≥1000：\|dev\|≤0.03 或 99% CI 含 0 | ✅ 三帶 \|dev\| 皆 ≤0.73pt |
| 局帶相對 base 不得系統性惡化 | ✅ 最大惡化 +0.72pt（<1pt，未達揭露門檻） |
| 全部預註冊驗證季 2023–2026 皆執行 | ✅ |

**一句話結論**：融合層在**校準**上有微幅正向效果（池化 ECE 0.02257 → 0.02063，顯著偏差分箱 [7, 8] → []），但在**準確度**上與零無異——池化 Brier 差 **+0.000095（99% game-cluster CI [−0.001367, +0.001646]）**，四季中 2 季變差。根因不是融合式或實作，而是**八項凍結賽前特徵在時間外幾乎不含增量資訊**（§6）。
<!-- generated:verdict end -->

---

## §1 紅線逐條落地對照

| # | 紅線 | 落地位置 | 驗證 |
|---|---|---|---|
| 1 | 時間分離與擬合對象 | `nested_windows(Y)` 是唯一窗口定義處：inner fit `2018..Y−2` → 選型季 `Y−1` → final fit `2018..Y−1` → 只評 `Y`。`build_season_pack` 另 `assert span_end <= s−1` | `test_nested_windows_strictly_separated`（4 季參數化）、`test_nested_windows_reject_too_early` |
| 2 | 特徵洩漏 | 前四項取 `game_features` 已於賽前寫入的 running／prior 欄；先發／牛棚由 `pitching_gamelog` 逐場原始計數在**快照之後才套用本場**重建。`starter_era_diff/whip/k9`、同季 standing、`pitching_current`、`advanced_stats` 全未進模型 | `test_running_state_excludes_the_game_itself`、`test_season_boundary_resets_running_state_but_keeps_prior`、`test_cold_start_prior_reads_only_2017_seasons_table` |
| 3 | 選型洩漏 | 模型族、八特徵、`kappa/lambda/gamma` 網格、tie-break、融合式、門檻全部寫死為模組常數；選型只讀 `Y−1` | `test_feature_keys_frozen`、`test_grids_and_ablations_frozen`、`test_prior_tiebreak_order`、`test_gamma_tiebreak_prefers_linear_decay` |
| 4 | v2 門檻只可加嚴 | 直接 import `winprob_val.THRESHOLDS`，未複製也未改寫；本卡只新增 `STRENGTH_THRESHOLDS`。**判定一律用未捨入值**（`raw_brier`／`band_stats`），非 `metrics()` 的 5 位捨入值 | `test_v2_thresholds_not_relaxed`、`test_verdict_*` 共 9 個門檻測試 |
| 5 | 逐局帶是硬性判定 | `strength_verdict` 同時檢「絕對偏差＋99% CI」與「相對同代 base 惡化」兩組門檻，數值沿用 CAL1 預註冊值 | `test_verdict_hard_fails_on_significant_band_deviation`、`..._single_band_worsening_over_2pt`、`..._two_bands_worsening_over_1pt`、`test_verdict_small_band_not_a_gate` |
| 6 | 語意與數值合約 | `fuse()`：`WP_situ ∈ {0,1}` 直接短路不經 clip；`w(t)=(1−t)^γ` 由 regulation outs 決定、10 局起恆 0；固定 `(p0,t)` 時嚴格單調 | `test_fuse_opening_anchor_equals_p0`、`..._strictly_monotone_in_wp_situ`、`..._range_and_canonical_endpoints`、`..._zero_weight_is_identity`、`test_weight_decreasing_with_fixed_endpoints` |
| 7 | 基準、時期與小樣本 | 逐季／池化並排 base、CAL1、主場常數（§4）；2026 首列；p0、≤2017 prior、advanced shadow 只列診斷；10+ 帶與 n<1000 分箱只揭露 | §4／§7；`test_verdict_small_band_not_a_gate` |
| 8 | 可重現（**經需求方 2026-07-27 sign-off 放寬為漂移偵測**） | DB 全程唯讀（只有 `SELECT`）；seed 固定 `20260725`；`--as-of` 界定完成場母體並貫穿 season metadata；`population_fingerprint` 涵蓋完成場內容／實際模型輸入／published build identity，`--expect-fingerprint` 不符即中止；部分重跑**強制**寫入 `不得作 Go 證據` 的硬性理由 | `test_partial_rerun_cannot_be_go_evidence`、`test_season_metadata_ignores_games_after_as_of`、`test_fingerprint_covers_scores_builds_and_model_inputs`、`test_fingerprint_tracks_actual_model_inputs`、`test_fingerprint_diff_names_the_drifted_key`；§9 |

---

## §2 母體、資料來源與降級帳

> 本節起，凡帶數字的表格與句子皆由 `scripts/strength1_report_tables.py` 自 canonical artifact
> 產生（標記為 `<!-- generated:… -->` 的區塊），`tests/test_strength1_report_sync.py` 釘住同步。
> **人工謄寫數字後宣稱已對帳，在本卡連續三輪失敗**（iteration 1／2／3），故改為結構保證。

<!-- generated:population start -->
**賽前母體**：A 一軍例行 **2,554 場**（完成場且 `game_date ≤ data_as_of`；本次 `data_as_of = 2026-07-27`），含 **40 場和局**（標籤 `y=0.5`）。

| 年 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 場數 | 239 | 240 | 240 | 299 | 300 | 298 | 360 | 359 | 219 |

本次 2026 輸入指紋：`n_completed=219`、`sno_md5=992a324eb00ca9d65c98c0aa2f649bed`、`games_md5=6a46603396e7035484d5d3c2a5c1b04b`、`model_inputs_md5=ef34553f7675cb7c6d56d24e5b250a59`；全域 `model_inputs_md5=32c3931b2f28529cf456904b5c5db144`。
<!-- generated:population end -->

> ⚠️ **進行中賽季的母體會隨入庫漂移**：`--as-of` 只鎖 `game_date` 界限，鎖不住入庫狀態。iteration 2 查核實測——同一個 `--as-of 2026-07-26` 在不同時點重跑得到 216 vs 219 場（那 3 場日期早在界限內，只是比分後來才入庫）。artifact 因此另存三層 `population_fingerprint`（完成場 sno／比分內容／**實際進入模型的 GameRow**／驗證季 published build identity），重跑時以 `--expect-fingerprint` 比對，不符即中止（紅線 8 的漂移偵測，經需求方 2026-07-27 sign-off 放寬自「逐位重現」）。

<!-- generated:source_tiers start -->
**先發／牛棚 rate 的資訊來源層級**：逐場逐側計數，兩項各 5,108 側＝2,554 場 × 2 側。

| 指標 | 當季自身（own） | 前一季（prior） | fit 窗聯盟率（league） |
|---|---:|---:|---:|
| 先發 | 4,702（92.1%） | 252（4.9%） | 154（3.0%） |
| 牛棚 | 5,062（99.1%） | 39（0.8%） | 7（0.1%） |
<!-- generated:source_tiers end -->

降級全部落在「季初首戰」與「無前一季紀錄的新投手」，是 fail-closed 的預期行為而非缺陷。
**已知降級**：2018 的先發 prior 來自 `pitching_seasons(2017)`，該表無好球數 → 好球率 prior 只能退聯盟率
（`test_cold_start_prior_without_strike_falls_back_to_league` 鎖定此語意）；2018 的牛棚 prior 因 2017 無逐場
gamelog 而一律退聯盟率。兩者皆只影響 2018 的訓練列，不影響任何驗證季的評分。

<!-- generated:coverage_ledger start -->
**排除帳**：四個驗證季的 `excluded_pa_no_pregame_features` **皆為 0**；`coverage_raw` 與 `effective_coverage` 2023–2025 皆 **1.000000**、2026 為 **0.986301**（219 完成場中 216 場有 published PA build）。
<!-- generated:coverage_ledger end -->

（WP-CAL1 當時 2026 為 0.9722 而硬性失敗的 canonical PA build 缺口已由需求方補跑修復，
治本卡為 [`INGEST-PA-DAILY1`](../tasks/INGEST-PA-DAILY1.md)。上述三個欄位與 `coverage`、
`n_irregular_games`、`pa_state_counts` 自 iteration 4 起一律由 `--as-of` 母體重算——原本取自
`load_eval_season()`，該函式以 `CURRENT_DATE` 為界，會讓標著舊 `data_as_of` 的 artifact 混進當下
全表的內容（iteration 3 查核 F1）。實測：`--as-of 2026-06-30` 得 177 完成場、coverage 1.000000、
`n_irregular_games=17`；修正前這三格會回報 7/27 的 219／0.986301／19。）

**kappa 的分母換算**：卡面固定 `kappa` 為 PA-equivalent 且「不得各指標另調」。好球率的分母是投球數、
FIP proxy 的分母是局數，故以 fit 窗聯盟的 `分母/PA` 比換算等效 kappa（`pitch_per_pa ≈ 3.78`、
`ip_per_pa ≈ 0.228`）。這不是各指標另調——仍是**單一** kappa，只是換算到各自分母的尺度；
若照字面把 kappa 直接加到 IP 分母，`kappa=100` 會等於 100 局，先發整季約 150 局，當季資料將永遠被
前一季主導，與卡面「當季資料隨分母增加自然取得更高權重」的明文設計意圖相反。
合約由 `test_kappa_converted_to_each_denominator` 鎖定。

---

## §3 選型證據（只讀 inner season）

每個驗證季 `Y` 的 `(kappa, lambda)` 只以「fit `2018..Y−2` → 對 `Y−1` 的 out-of-time 逐場 Brier」選定，
`gamma` 再以同代 base 融合後的 `Y−1` 逐 PA Brier 選定。掃描順序固定為 kappa 升冪 → lambda 升冪，
故 epsilon 比較完全決定性。

<!-- generated:selection start -->
| 驗證季 Y | inner fit | 選型季 Y−1 | 選定 κ | 選定 λ | 選定 γ | 選型季逐場 Brier | 選型季融合 vs 未融合 |
|---|---|---|---:|---:|---:|---:|---|
| 2023 | 2018–2021 | 2022 | 50 | 100 | 1 | 0.239064 | 0.146455 < 0.147401（改善） |
| 2024 | 2018–2022 | 2023 | 200 | 100 | 2 | 0.242378 | 0.147634 > 0.147453（**惡化**） |
| 2025 | 2018–2023 | 2024 | 100 | 0.1 | 0.5 | 0.241558 | 0.151582 < 0.153876（改善） |
| 2026 | 2018–2024 | 2025 | 200 | 100 | 2 | 0.246487 | 0.154420 < 0.154478（改善） |
<!-- generated:selection end -->

兩點值得記錄：

1. **λ=100（網格最強正則）在四季中被選中三次**，且在 2023 的 12 格網格中，每個 kappa 下 Brier 都隨 lambda
   單調下降。這本身就是「賽前特徵幾乎沒有可轉移訊號」的直接證據——最佳模型接近常數模型。
2. **選型季的訊號與驗證季結果反向**：Y=2024 的選型季說融合會惡化，驗證季卻改善；Y=2025 的選型季說融合會
   改善，驗證季卻惡化。融合對 Brier 的作用在季間不可預測，這是後續判定的關鍵背景。

---

## §4 結果（2026 鎖箱 holdout 首列）

### 4.1 逐季（判定用未捨入值）

<!-- generated:seasons start -->
| 季 | base 模型窗 | n_PA | cov | **主場常數** | **CAL1（歷史）** | **base（未融合）** | **本卡 WP_adj** | Δ vs base | Δ 的 99% CI |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| **2026（鎖箱；資料截止 2026-07-27、完成場 219）** | 2018-2025 | 16,131 | 0.9863 | 0.247138 | 0.16725¹ | 0.166597 | **0.166368** | **−0.000230** | [−0.002341, +0.001766] |
| 2025 | 2018-2024 | 27,078 | 1.0000 | 0.248571 | 0.15357 | 0.154478 | **0.155958** | **+0.001479** ❌ | [−0.001809, +0.005377] |
| 2024 | 2018-2023 | 27,453 | 1.0000 | 0.248753 | 0.15335 | 0.153876 | **0.152505** | **−0.001372** | [−0.003265, +0.000130] |
| 2023 | 2018-2022 | 22,912 | 1.0000 | 0.241499 | 0.14792 | 0.147453 | **0.147897** | **+0.000444** ❌ | [−0.001560, +0.002625] |
<!-- generated:seasons end -->

¹ CAL1 欄是 WP-CAL1 的歷史值，**不在本卡 artifact 內**（腳本以常數帶入，見 `CAL1_BRIER`）；其 2026 是在 coverage 0.9722（缺 6 場）下計算，與本卡的 216/219 母體不完全可比，其餘年度可比。

**主場常數基準已改用未捨入值**：iteration 2 查核 F1a 指出 `winprob_val.home_rate_from_games()` 會先把 p 捨入 4 位，硬門檻 Brier 因而只是「對已捨入 p 的未捨入計算」；本卡改用自帶的 `home_rate_exact()`，故上表基準較 iteration 1 有第 6 位差異。

**四個 Δ 的 99% game-cluster CI 全部包含 0。** 兩個 ❌ 是硬門檻以點估計判定的結果，而點估計本身在雜訊尺度內。

### 4.2 池化 2023–2026

<!-- generated:pooled start -->
池化 2023–2026：n_PA = 93,574；n_games = 1,233。

| 模型 | Brier | ECE | 顯著偏差分箱（99% 叢集 CI 排除 0） |
|---|---:|---:|---|
| 主場常數基準 | 0.24665 | — | — |
| **base（未融合）** | **0.154671** | 0.02257 | **[7, 8]** |
| **WP_adj（本卡）** | **0.154766** | **0.02063** | **[]** |

池化 Brier 差 **+0.000095**，99% game-cluster CI **[−0.001367, +0.001646]**（`brier_delta_diagnostic`；診斷用，不進判定）。
<!-- generated:pooled end -->

### 4.3 池化逐局帶（硬性判定；未捨入）

<!-- generated:bands start -->
| 帶 | n | base dev | WP_adj dev | Δ\|dev\| | WP_adj 的 99% CI |
|---|---:|---:|---:|---:|---|
| 1-3 | 31,244 | −0.00003 | +0.00726 | **+0.72pt** | [−0.03025, +0.03376] |
| 4-6 | 31,771 | +0.00303 | +0.00588 | +0.28pt | [−0.02337, +0.02842] |
| 7-9 | 29,366 | −0.00059 | +0.00011 | −0.05pt | [−0.02284, +0.01687] |
| 10+（僅揭露） | 1,193 | −0.00028 | −0.00028 | +0.00pt | [−0.10834, +0.09311] |
<!-- generated:bands end -->

<!-- generated:cal1_contrast start -->
三個例行帶皆遠低於 0.03 上限、CI 皆含 0。**對照 CAL1**：事後校準（定案的 isotonic）當時把 1-3 帶從 −0.10pt 惡化到 −2.41pt，超過 2pt 硬性上限。
<!-- generated:cal1_contrast end -->
**opening anchor 設計確實達成了它的目的**——本卡沒有重蹈 CAL1 「全域中心下修破壞早局帶」的覆轍。

---

## §5 逐條硬門檻對照

<!-- generated:hard_gates start -->
| 條 | 門檻 | 判定 | 證據 |
|---|---|---|---|
| 4a | 任一季 coverage 或 effective coverage < 0.98 | ✅ 通過 | 2023 1.000000／1.000000；2024 1.000000／1.000000；2025 1.000000／1.000000；2026 0.986301／0.986301（coverage／effective） |
| 4b | 任一季 Brier 未勝主場常數基準 | ✅ 通過 | 最小優勢 0.0808（2026）、最大 0.0962（2024） |
| 4c | **任一季 Brier 劣於同代未融合 base** | ❌ **失敗** ×2 | A2023 融合後 Brier 0.147897 劣於同代未融合 base 0.147453；A2025 融合後 Brier 0.155958 劣於同代未融合 base 0.154478 |
| 4d | 池化十分位 n≥1000 且 \|dev\|>0.03 且 99% CI 排除 0 | ✅ 通過 | 無分箱同時顯著且 |dev| 超限 |
| 5a | 池化局帶 n≥1000 且 \|dev\|>0.03 且 99% CI 排除 0 | ✅ 通過 | 1-3 +0.00726；4-6 +0.00588；7-9 +0.00011 |
| 5b | 單帶 \|dev\| 惡化 >2pt，或 ≥2 帶各惡化 >1pt | ✅ 通過 | 1-3 +0.72pt；4-6 +0.28pt；7-9 -0.05pt |
| 8 | 全部預註冊驗證季皆執行 | ✅ 通過 | 2023–2026（4 季） |

**任一硬門檻失敗即 No-Go**。本次失敗 1 條（4c） → **No-Go**。
<!-- generated:hard_gates end -->

---

## §6 失敗機制（本卡的主要研究貢獻）

### 6.1 先驗 p0 在時間外幾乎不含增量資訊

<!-- generated:p0_diagnostics start -->
| 驗證季 | p0 逐場 Brier | leakage-safe 主場常數 | Δ | p0 值域 |
|---|---:|---:|---:|---|
| 2026 | 0.245492 | 0.245940 | −0.000448 | [0.414, 0.656] |
| 2025 | 0.248801 | 0.247375 | **+0.001426** | [0.383, 0.717] |
| 2024 | 0.242802 | 0.247965 | −0.005163 | [0.271, 0.673] |
| 2023 | 0.242734 | 0.241801 | **+0.000933** | [0.410, 0.653] |

四季平均 Δ ≈ −0.0008，2 季為正。
<!-- generated:p0_diagnostics end -->

### 6.2 這不是實作不足——管線在有訊號時抓得到

`--diagnostics` 的四路對照（固定 κ=100、λ=100，不參與任何選型）：

<!-- generated:prior_signal_diagnostics start -->
| Y | ① 同窗 in-sample | ② 時間外（本卡用法） | ③ 主場常數 | ④ `game_features` starter 欄 | ⑤ 後半季時間外 | ⑥ 後半季常數 |
|---|---:|---:|---:|---:|---:|---:|
| 2023 | 0.239013 | 0.242537 | 0.241801 | 0.241970 | 0.241442 | 0.240327 |
| 2024 | 0.239561 | 0.242650 | 0.247965 | 0.240356 | 0.240874 | 0.246285 |
| 2025 | 0.239856 | 0.246693 | 0.247375 | 0.244834 | 0.247856 | 0.249358 |
| 2026 | 0.240880 | 0.245267 | 0.245940 | 0.246447 | 0.249206 | 0.251628 |
<!-- generated:prior_signal_diagnostics end -->

兩項讀法：

1. **① < ③ 一致成立**（約 −0.006～−0.008）：同一組特徵在同窗內確實被擬合出訊號，
   **邏輯斯迴歸、標準化、收縮與融合管線本身可用**。是這個訊號不跨季轉移。
2. **⑤ vs ⑥ 只有微幅優勢且 2023 仍為負**：把樣本限縮到雙方皆已打 ≥40 場之後，
   時間外優勢仍只有 −0.001～−0.002。所以「季初 running state 太吵」不是主要解釋。

#### ⚠️ 第 ④ 欄的可重現性更正（iteration 1 查核 F2）

本報告初版的第 ④ 欄記為 0.231690／0.230744／0.231072／0.229086，並據此宣稱
「四季一致改善 0.010–0.017＝前視洩漏的典型指紋」。**該數字現已無法重現**，成因如下：

第 ④ 欄讀 `cpbl.game_features` 的 `starter_era_diff`／`whip`／`k9`。撰寫當時該三欄由
`features/outcome.py` 以 `(starter_id, year)` 讀**同季彙總**（即卡面紅線 2 禁用的洩漏欄），
對照因而成立；**[`ML-OUTCOME-LEAK1`](ML-OUTCOME-LEAK1_RESULTS.md)（merge `5a683d1`）已將該三欄
改為 leakage-safe 的賽前 as-of 值**，故此對照在該 merge 之後不再產生假性改善。上表已更新為
當前可重現值。佐證此診斷的關鍵事實：**重跑後只有第 ④ 欄改變，①②③⑤⑥ 六欄逐位不變**——
唯一變動的正是讀取那張被修改資料表的欄位。

**這是本卡的一項方法論缺陷，不是資料問題**：依賴可變 DB 狀態的診斷不構成可重現證據；
artifact 未快照輸入即無法自證。後續若要保留此類對照，須將輸入快照納入 artifact。

**洩漏本身的存在不受影響**，且已由不依賴本 harness 的三項獨立證據確立
（見 [`ML-OUTCOME-LEAK1_RESULTS.md`](ML-OUTCOME-LEAK1_RESULTS.md) 及其查核紀錄）：

- **變異測試**：把 `_starter_rates` 改回同季彙總語意後，該卡的 running-state 合約測試由綠轉紅。
- **DB 層反證**：同季內同一組先發重複對戰的 256 組中，`starter_era_diff` 全部有變異、0 組相同；
  洩漏版（同季彙總）該值必為常數。
- **同一程式碼路徑前後對照**：走查回測準確率 0.6160 → 0.5550，且不含先發特徵的對照組前後 **±0**。

因此原先「`outcome_gbm.py` 的 ~62% 含洩漏、不可當作賽前預測力已足夠的證據」這項延伸判讀
**仍然成立**，但其證據來源應改引 `ML-OUTCOME-LEAK1`，而非本表。

### 6.3 為什麼 S 型偏差沒有被治好

卡面的治本假說是「高分箱（領先方）低估是結構性的：現實中領先方不成比例地是較強隊」。
池化十分位顯示這個假說**方向正確但幅度遠遠不足**：

<!-- generated:deciles start -->
| 分箱 | n | base dev | WP_adj dev | 改善 |
|---|---:|---:|---:|---:|
| 0 | 10,554 | +0.00289 | +0.00192 | +0.10pt |
| 1 | 5,867 | +0.03591 | +0.03348 | +0.24pt |
| 2 | 6,168 | +0.04029 | +0.04150 | −0.12pt（惡化） |
| 3 | 6,906 | +0.04404 | +0.04682 | −0.28pt（惡化） |
| 4 | 8,953 | +0.01884 | +0.01045 | +0.84pt |
| 5 | 21,364 | +0.00617 | +0.01510 | −0.89pt（惡化） |
| 6 | 8,468 | −0.03106 | −0.00738 | +2.37pt |
| 7 | 6,891 | −0.04909 | −0.04376 | +0.53pt |
| 8 | 6,664 | −0.04154 | −0.03186 | +0.97pt |
| 9 | 11,739 | −0.01179 | −0.01225 | −0.05pt（惡化） |
<!-- generated:deciles end -->

高分箱確實往正確方向移動，但只走了 0.5–1.0pt，原始偏差是 4–5pt；低分箱反而略微惡化。

**因此 §0 表中「池化十分位 ✅ 通過」必須加但書**：它通過**不是因為偏差被修好**，
而是因為 99% game-cluster CI 夠寬——bin 7 的 CI 上界只從 −0.0043 移到 +0.0005 就跨過 0，
是不折不扣的擦邊。把「顯著分箱 [7,8] → []」當成「S 型偏差已解決」會是嚴重誤讀。
**S 型偏差依然存在，量級幾乎未變。**

### 6.4 與 CAL1 的機制對照

<!-- generated:cal1_mechanism start -->
| | WP-CAL1（事後校準） | WP-STRENGTH1（戰力先驗） |
|---|---|---|
| 失敗形態 | 修正**有力但方向錯**：池化分箱修平了，卻把 1-3 局帶從 −0.10pt 破壞到 −2.41pt（定案的 isotonic，超過 2pt 硬性上限） | 修正**方向對但沒有力**：局帶完好無損（最大惡化僅 +0.72pt），但四季中 2 季 Brier 反而變差 |
| 根因 | 校準窗與驗證季分屬不同世代 base，學到的中心修正已過時（不具時間平穩性） | 賽前可得資訊在時間外幾乎不含增量預測力 |
| 共同教訓 | 內部窗指標會為有害／無效的層背書；**唯一防線是嵌套時間外驗證＋逐局帶硬門檻** | 同左 |
<!-- generated:cal1_mechanism end -->

CAL1 的教訓在本卡被制度化並生效：opening anchor 讓局帶完全沒有惡化（§4.3），
逐局帶硬門檻與「不得劣於同代 base」的門檻各自獨立生效——後者正是本次擋下 No-Go 的那一條。

---

## §7 診斷（不進判定）

### 7.1 預註冊消融（full 是唯一驗收候選）

融合後逐 PA Brier（低者佳）：

<!-- generated:ablation start -->
| 季 | team_only（4 項） | team+starter（7 項） | **full（8 項）** |
|---|---:|---:|---:|
| 2026 | 0.166765 | **0.166354** | 0.166368 |
| 2025 | **0.154671** | 0.155544 | 0.155958 |
| 2024 | 0.153332 | 0.152514 | **0.152505** |
| 2023 | **0.147645** | 0.147813 | 0.147897 |
<!-- generated:ablation end -->

三層排序在季間完全不穩定（各層在四季中各拿過最佳），再次符合「差異在雜訊尺度」的判讀。
依卡面紅線 3，**不得因某層在驗證季較佳而切換上線模型或重做選型**——full 仍是唯一驗收候選，
本卡的 No-Go 亦以 full 判定。

`winrate_diff` 在四季的標準化係數皆為**負**（−0.005 ~ −0.174），與直覺相反；
這是與 `run_margin_diff`（+0.112 ~ +0.286）的共線壓抑效應，在 λ=0.1 的 2025 最為誇張。
`starter_recorded_strike_share_adv` 係數在 ±0.03 內且四季變號 → 無可用訊號。
兩者都屬卡面預期的共線／弱訊號揭露，非缺陷。

### 7.2 2026 advanced／TrackMan shadow

**明確不進候選集合、超參選型或 Go/No-Go。**

<!-- generated:advanced_shadow start -->
> 本節不吃 `--as-of`，數字為 `observed_at = 2026-07-27T16:32:13+08:00` 的當下全表狀態；比對重跑輸出時須與 `generated_at` 一併排除。

| 項目 | 現況 | 不可用原因 |
|---|---|---|
| `advanced_stats` 2026 | 投手 331 列、打者 360 列 | **只有全季累計、無時間版本 → 歷史賽前狀態不可重建** |
| `pitch_tracking` 2026 A | 177/219 場（coverage 0.8082）、49,128 球 | 球場端設備缺場；缺場機制尚未查核 |

季末彙總相關性（37 位 PA≥100 的先發，只回答「概念是否對齊」）：`kbb~kp` **+0.416**、`strike_share~bbp` **-0.263**、`kbb~whiffp` **+0.259**、`strike_share~whiffp` **-0.179**。
<!-- generated:advanced_shadow end -->

`kbb ~ kp` 的中度正相關符合預期（同為三振傾向的兩種量度），但這是**季末對季末**的關係，
不構成任何賽前預測力證據。若要讓這些欄位可上線，後續卡至少須保存 as-of snapshot 或由逐球資料
重建 pregame running state，並以 2027 或預註冊的前瞻期間作真正留出驗證 → [`GAME-RECAP-WP-STRENGTH-ADV1`](../tasks/GAME-RECAP-WP-STRENGTH1.md)（尚未註冊）。

---

## §8 後續路徑（供需求方裁定，本卡不自行延伸）

按「證據強度 ÷ 成本」排序：

1. **接受 A scope 短期無 WP 上線路徑**，維持 `WP-API1` 阻塞，並讓
   [`UX-WP-DISCLOSURE1`](../tasks/UX-WP-DISCLOSURE1.md) 依 §6.3 更新文案：
   S 型偏差**兩度嘗試（事後校準、戰力先驗）皆未修復**，量級維持 4–5pt。這是目前最誠實的產品狀態。
2. **先修「賽前預測力」本身，再談融合**：本卡證明瓶頸在 p0 而非融合層。
   任何後續嘗試都應先獨立通過「p0 逐場 Brier 在多個時間外季穩定勝過主場常數」這道前置關卡，
   通過後再接既有融合層（融合式與 anchor 已驗證無害）。候選方向：先發投手的多季階層模型、
   打線／守備的賽前可得代理、傷病與輪值資訊。**注意**：現行 `models/outcome_gbm.py` 報告的
   ~62% 走查準確率含 §6.2 所示的同季彙總洩漏欄位，不可作為「賽前預測力已足夠」的證據；
   建議另開卡以 leakage-safe 特徵重估該基線。
3. **條件化 run_dist**（卡面附錄 A 已證樣本可行）：本卡明文禁止事後切換，若要走須另卡預註冊。
4. **`GAME-RECAP-WP-STRENGTH-ADV1`**：僅在 2026+ advanced 有 as-of snapshot 或可由逐球重建
   pregame state 後才有意義，且須以前瞻期間驗證。

**排除路線（勿重走）**：校準窗變體（recency 窗／衰減加權／逐局帶條件化校準）已由 CAL1 §7 列為低勝率；
本卡另新增排除——**在 p0 未先通過前置關卡前，調整融合式（`w(t)` 形狀、anchor、gamma 網格）不會改變結論**，
因為 §4.2 顯示融合的整體效果量本身就與 0 不可區分。

---

## §9 重現

```bash
uv run ruff check && uv run pytest tests/test_winprob_strength.py tests/test_strength1_report_sync.py -q
uv run python -m cpbl.models.winprob_strength --as-of 2026-07-27   # 全跑 ~50s，寫 canonical artifact
uv run python scripts/strength1_report_tables.py                   # 由 artifact 重新產生本報告的數字區塊
```

**`--as-of` 不是選用的**：不給就取今日，完成場母體會隨入庫漂移，artifact 標的 `data_as_of`
與內容便對不上（iteration 3 查核 F1）。要與本報告的數字對照，一律帶 `--as-of 2026-07-27`。

部分重跑與診斷（**務必 `--out` 導向 scratch，不得覆寫已提交 artifact**）：

```bash
uv run python -m cpbl.models.winprob_strength --seasons 2026 --as-of 2026-07-27 --out /private/tmp/scratch.json
```

要確認輸入是否已漂移，帶 `--expect-fingerprint` 指向已提交 artifact；不符即中止並逐項列出差異
（紅線 8 的漂移偵測；經需求方 2026-07-27 sign-off 由「逐位重現」放寬而來）：

```bash
uv run python -m cpbl.models.winprob_strength --as-of 2026-07-27 \
  --expect-fingerprint docs/research/game_recap_wp_strength1_metrics.json \
  --out /private/tmp/scratch.json
```

```bash
uv run python -m cpbl.models.winprob_strength --diagnostics --as-of 2026-07-27
```

- 全程唯讀（模組內只有 `SELECT`）；bootstrap seed 固定 `20260725`。**相同 `--as-of` ＋相同輸入指紋
  下逐位一致**；輸入若已漂移，`--expect-fingerprint` 會擋下而不是靜默給出不同數字。
- `--seasons` 的部分重跑會在 `verdict.reasons` 強制寫入「不得作 Go 證據」，避免被誤引為結論。
- `advanced_shadow_2026` 不吃 `--as-of`（標 `observed_at`），**逐位比對時須與 `generated_at` 一併排除**。
- 查核建議：至少重跑一個留出季，核對 `windows`（inner/selection/final）、`population.source_tiers`、
  `final_league_rates`、`selection.prior_grid` 與 `coverage`／`excluded_pa_no_pregame_features`；
  並跑一次 `scripts/strength1_report_tables.py --check` 確認報告數字確實出自 artifact。
