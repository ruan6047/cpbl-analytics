# ML-WP-VAL-RESAMPLE1：WP 評估取樣的打席前比分修正與結論重驗

- 卡：`ruan6047/cpbl-analytics#98`（T3，`db_scope=read`）
- 基準：`b853572e63565970c21f8521bc0448d1db1cc761`（`DATA-RECAP-WP-PRESTATE1` merge）
- 資料截止：`2026-08-07`（本機 DB；`--as-of 2026-08-07`）
- 全程唯讀，未寫任何 DB 表；未動 `web/`、`api/routers/`、`ingest/`。

---

## §0 結論（三選一：**需修正**）

**舊 VAL1／STRENGTH1 的方向性結論全部仍成立；需要修正的是逐項對外數字。**

- **VAL1 A scope**：`unsupported` 不變。S 型偏差不但沒被取樣污染撐出來，修正後**還略為放大**
  （低分箱 +5.3→+5.5pt、高分箱 −4.3→−4.5pt）。「校準有偏、辨別力為真」的定性結論
  （池化 Brier 0.153 vs 主場常數 0.245）在修正後**逐位不變**——`/methodology#key-plays`
  用來支撐「序數用法站得住」的那句話不受影響。
- **VAL1 C／E scope**：`unsupported` 不變，數字第三位小數內移動。
- **VAL1 D scope**：判定由 `unsupported` 翻成 `supported`——但**這不是取樣修正造成的**。
  今日資料 × 舊讀法的控制組**已經**翻成 `supported`（§3.3）。成因是母體增長 1,151→1,169 場
  後，唯一支撐 `unsupported` 的池化十分位 2 的 99% bootstrap CI 下界由 +0.0059 掉到 −0.0029。
  §5 的 seed 穩健度顯示該分箱的「顯著」本來就只有 7–8/12 個 seed 成立——**翻面是抽樣實現的
  隨機性，不是偏差變小**。標記**待人工判讀**，交需求方裁決（§7-D1）。
- **STRENGTH1**：`unsupported`（No-Go）**不翻轉**。失敗閘門（4c）、失敗季（2023／2025）、
  超參選擇（k／λ/γ）在三路對照下逐項相同（§4）。

---

## §1 病灶與修法

`winprob_val.load_eval_season()` 原本以 canonical `pre_state.away_score`／`home_score`
之差當「打席前局面分差」。但 livelog 的比分欄是**事件後**快照，而 `pre_state` 是把
**起始事件列**的比分欄原樣存下來——單一事件即結束的得分打席（首球全壘打等）起始列＝終結列，
存到的已是得分**後**的比分（`DATA-RECAP-WP-PRESTATE1`／#96）。

修法：改由 **`#96` 已落 main 的那支純函式** `cpbl.api.routers.recap.pre_scores_from_events()`
以 `start_event_no` 對回 `pa_facts.annotate_scores()` 的事件流取「事件之前」的 running 比分。
**沒有另刻第二份實作**——`tests/test_winprob_val.py::
test_pre_score_resolution_delegates_to_the_single_recap_implementation` 以 spy 釘住這條依賴：
若日後有人在 models 側自建解算，數值測試可能仍全綠，那支測試會紅。

解不出打席前比分的 `ready` 打席 **fail closed 排除**並計入
`pa_state_counts.ready_pre_score_unresolved`，不以受污染的 `pre_state` 值冒充。

### 1.1 分層債（**需求方裁決項**，見 §7-P1）

`pre_scores_from_events()` 住在 `api/routers/recap.py`，而 `models` 不得 import `api`；
更硬的是**模組層 import 會構成循環**：`winprob_val → recap → winprob_scorer → winprob_val`
（`winprob_scorer` 已 import `winprob_val` 的 `RuleSet`／`we_solver_rules`／`wp_state_rules`）。
本卡因此以**函式內延後 import** 取用該純函式——寧可留這個氣味，也不違反「同一條紅線只能有
一份實作」。乾淨解是把它上抽到 `models/`（`recap` 已有 `winprob_scorer` 的上抽前例，且 recap
可原樣 re-export 保持相容），但那要動 `src/cpbl/api/routers/recap.py`，不在本卡寫入集，
**未動、留待裁決**。

---

## §2 受影響打席母體（逐季，由指令輸出產生）

腳本：`docs/research/ML-WP-VAL-RESAMPLE1/census.py`　artifact：`population_census.json`

```
uv run python docs/research/ML-WP-VAL-RESAMPLE1/census.py
```

同一支 `load_eval_season()` 各跑一次 `events`／`pre_state`，以 `(game_sno, pa_index)` 逐打席比對。

| scope | ready 打席（全期） | 分差改變 | 比例 | 解不出（fail closed） |
|---|---|---|---|---|
| A 2018–2026 | 197,974 | 3,054 | 1.5426% | 0 |
| C 2018–2025 | 3,294 | 42 | 1.2750% | 0 |
| D 2018–2026 | 128,832 | 2,195 | 1.7038% | 0 |
| E 2018–2025 | 1,302 | 20 | 1.5361% | 0 |
| **全期合計** | **331,402** | **5,311** | **1.6026%** | **0** |

（上表逐格取自 artifact 的 `by_scope`／`totals` 欄，非人工加總。）

逐季明細見 artifact。三件事值得記：

1. **2026/A 逐位重現派工包的量測**：ready 17,843、changed 223（1.2498%）、
   Δ 分布 `{-3:7, -2:23, -1:88, 0:17620, 1:81, 2:21, 3:2, 4:1}`——與 #96 的獨立量測完全一致。
2. **不得以單季推論全期**：受影響比例**逐年遞減**（A 2018 2.04% → A 2026 1.25%），
   只跑 2026 會低估歷史季的污染程度約四成。
3. **`ready_pre_score_unresolved` 全期為 0**：fail-closed 分支在真實資料上從未觸發
   （其行為由 `tests/test_winprob_val.py` 的合成 fixture 覆蓋，不是未測路徑）。
   因此 A/B 兩路的評分母體**完全相同**，Δ 指標可乾淨歸因於取樣修正本身。

Δdiff（新 − 舊）全期分布高度對稱：`{-4:13, -3:89, -2:475, -1:2096, 0:326091, 1:2086, 2:448, 3:88, 4:16}`。
負值＝主隊在該打席得分（舊讀法把這分算進了打席**前**），正值＝客隊得分。對稱性即
「主客得分打席數相當」，符合預期。

---

## §3 VAL1 重跑：三路對照

只有兩路是不夠的——canonical artifact 跑於 2026-07-2x，A 母體自那時起由 1,826 場長到 1,855 場。
加跑「今日資料 × 舊讀法」當控制組後，母體漂移與取樣修正才切得開：

- `canonical → pre_state` ＝ **母體漂移**（同一把尺、不同資料）
- `pre_state → events` ＝ **取樣修正**（同一批資料、不同尺）

腳本：`compare.py`　artifacts：`val1_metrics_events.json`／`val1_metrics_pre_state.json`／`val1_comparison.json`

```
uv run python -m cpbl.models.winprob_val --pre-score-source events    --out docs/research/ML-WP-VAL-RESAMPLE1/val1_metrics_events.json
uv run python -m cpbl.models.winprob_val --pre-score-source pre_state --out docs/research/ML-WP-VAL-RESAMPLE1/val1_metrics_pre_state.json
uv run python docs/research/ML-WP-VAL-RESAMPLE1/compare.py
```

### 3.1 A scope（一軍例行）——結論不變，偏差略為放大

| | verdict | n_games | n_pa | 池化 Brier | 主場基準 | ECE | 顯著分箱 |
|---|---|---|---|---|---|---|---|
| canonical | unsupported | 1,826 | 138,949 | 0.15314 | 0.245 | 0.02604 | 1,2,3,8,9 |
| 今日 × 舊讀法 | unsupported | 1,855 | 140,991 | 0.15317 | 0.24534 | 0.02639 | 1,2,3,8,9 |
| 今日 × 修正 | unsupported | 1,855 | 140,991 | **0.15330** | 0.24534 | 0.02681 | 1,2,3,**7**,8,9 |

池化十分位偏差（pred − actual，百分點，未捨入值見 artifact）：

| 十分位 | canonical | 今日×舊 | 今日×修正 | Δ取樣修正 |
|---|---|---|---|---|
| 1 | +4.21 | +4.23 | +4.24 | +0.01 |
| 2 | +5.34 | +5.41 | **+5.54** | +0.13 |
| 3 | +6.03 | +6.01 | **+6.12** | +0.11 |
| 7 | −3.45 | −3.52 | −3.65 | −0.13 |
| 8 | −4.32 | −4.41 | **−4.47** | −0.06 |
| 9 | −1.40 | −1.39 | −1.40 | −0.01 |

**判讀**：取樣污染**不是**偏差的來源，修正後偏差反而各方向加大 0.1pt 上下。這方向是可預期的
——舊讀法把得分打席的分差朝「得分方領先」偏移，等於把該打席的 WP 預測往實際賽果方向拉，
系統性地**低估**了模型的失準。

- 「低十分位高估 +4.2~+6.0pt」→ 應更新為 **+4.2~+6.1pt**（逐分箱 +4.2／+5.5／+6.1）。
- 「十分位 8 低估 −4.3pt」→ 應更新為 **−4.5pt**。
- 「99% game-cluster CI 全數排除 0」→ **仍成立**（分箱 1/2/3/8/9），且 §5 顯示 2/3/8 對 seed 完全穩健。
- 「池化 Brier 0.153 vs 主場常數基準 0.245」→ **逐位不變**（0.15330 vs 0.24534）。
- 十分位 7 在修正後首次跨進顯著——**不得當作新發現**，見 §5。

### 3.2 C／E scope（季後）——結論不變

| scope | | verdict | 池化 ECE | 關鍵數字 |
|---|---|---|---|---|
| C | canonical | unsupported | 0.10970 | 全期 25 場 |
| C | 今日×舊 | unsupported | 0.10922 | |
| C | 今日×修正 | unsupported | **0.11001** | |
| E | 已發布（FIX1 errata） | unsupported | 0.08536 | E2025 Brier 0.28886 vs 0.25289 |
| E | 今日×舊 | unsupported | 0.08539 | E2025 0.28741 vs 0.25301 |
| E | 今日×修正 | unsupported | **0.08548** | E2025 **0.28588** vs 0.25301 |

> ⚠️ E 的 canonical 比較基準**不能用** `docs/research/game_recap_wp_val1_metrics.json`：
> 該 artifact 是 **pre-FIX1** 版（E 仍借 D 分布、ruleset `cap15`，池化 ECE 0.10054），
> FIX1 修正後的正確值只存在於 `GAME-RECAP-WP-VAL1-FIX1_ERRATA.md` 的表格。
> 這是範圍外發現（§6-F1）。上表 E 的「已發布」列取自 errata。

### 3.3 D scope（二軍例行）——判定翻面，但**不是本卡造成的**

| | verdict | n_games | n_pa | 十分位 2 偏差 | 十分位 2 的 99% CI |
|---|---|---|---|---|---|
| canonical | **unsupported** | 1,151 | 87,948 | +4.71pt | [+0.0059, +0.0935] ← 排除 0 |
| 今日 × 舊讀法 | **supported** | 1,169 | 89,291 | +4.93pt | [−0.0029, +0.0937] ← 含 0 |
| 今日 × 修正 | **supported** | 1,169 | 89,291 | +4.90pt | [−0.0034, +0.0932] ← 含 0 |

點估計幾乎沒動（+4.71 → +4.93 → +4.90pt），翻面的是 **CI 下界**。取樣修正這一步
（舊 → 修正）**完全沒有改變判定**。因此：

> **D 的 `unsupported` 之所以不再重現，是母體增長 18 場後 bootstrap 重抽實現改變所致，
> 不是取樣修正、也不是偏差真的消失。**

§5 進一步顯示這個分箱的顯著性本來就是擲硬幣（7–8/12 個 seed）。**標記待人工判讀**，
不自行主張 D 應改標 `supported`。

---

## §4 STRENGTH1 重跑：No-Go 不翻轉

```
uv run python -m cpbl.models.winprob_strength --pre-score-source events    --as-of 2026-08-07 --out docs/research/ML-WP-VAL-RESAMPLE1/strength1_metrics_events.json
uv run python -m cpbl.models.winprob_strength --pre-score-source pre_state --as-of 2026-08-07 --out docs/research/ML-WP-VAL-RESAMPLE1/strength1_metrics_pre_state.json
```

| | verdict | 失敗閘門 | 池化 base Brier | 池化 adj Brier | n_pa |
|---|---|---|---|---|---|
| canonical（2026-07-27） | unsupported | 4c | 0.15467065 | 0.15476557 | 93,574 |
| 今日 × 舊讀法 | unsupported | 4c | 0.15454880 | 0.15457075 | 95,178 |
| 今日 × 修正 | unsupported | **4c** | 0.15469154 | 0.15471551 | 95,178 |

三路的硬性失敗理由**逐字相同**：`A2023 融合後 Brier 劣於同代未融合 base`、
`A2025 融合後 Brier 劣於同代未融合 base`。四季的超參選擇（k／λ／γ）在 A/B 之間
**完全一致**，coverage 皆 1.0。

**結論：STRENGTH1 的 No-Go 不因取樣修正而翻轉。** 該卡「戰力先驗無法治本」的定案維持有效。

---

## §5 邊界分箱對 bootstrap seed 的穩健度（新增診斷）

VAL1 的硬性判定是「|dev| 超界 **且** 99% CI 排除 0」。CI 由固定 seed（20260725）的整場重抽算出。
本卡在兩處撞到「點估計沒動、CI 端點跨過 0」的邊界（A 十分位 7、D 十分位 2），故量了 12 個 seed。

腳本：`bin_stability.py`　artifact：`bin_stability.json`

| scope／分箱 | n | dev | 舊讀法顯著 seed 數 | 修正後顯著 seed 數 |
|---|---|---|---|---|
| A bin2 | 9,311 | +5.5pt | 12/12 | **12/12** |
| A bin3 | 10,381 | +6.1pt | 12/12 | **12/12** |
| A bin8 | 10,249 | −4.5pt | 12/12 | **12/12** |
| A bin7 | 10,508 | −3.6pt | 1/12 | **5/12** ← 邊界 |
| D bin1 | 6,345 | +2.3pt | 0/12 | 0/12 |
| D bin2 | 6,351 | +4.9pt | 8/12 | **7/12** ← 邊界 |
| D bin3 | 7,391 | +4.2pt | 0/12 | 0/12 |

**判讀**：

- VAL1 A scope 的核心宣稱（低分箱高估、十分位 8 低估）**對 seed 完全穩健**，12/12 成立。
- **A 十分位 7 的新「顯著」是雜訊**（5/12）——不得寫進對外文案當新發現。
- **D 十分位 2 的顯著性是擲硬幣**（7–8/12）。canonical 那次抽到成立的實現、今天抽到不成立的
  實現。「D 由 unsupported 翻 supported」因此**不是證據等級的變化**。
- 更一般的問題（範圍外，§6-F2）：`verdict_for()` 以**單一 seed 的 CI 是否含 0** 當硬性判定，
  在邊界分箱上等於讓判定吃 seed 的運氣。這是方法層缺陷，不在本卡修。

---

## §6 範圍外發現（只列出，不處置）

- **F1｜`docs/research/game_recap_wp_val1_metrics.json` 是 pre-FIX1 版**。E scope 仍是
  「借 D 分布、ruleset cap15、池化 ECE 0.10054」的缺陷版；FIX1 的修正只寫進 errata，
  artifact 從未重生成。任何人拿這份 artifact 當 E 的事實來源都會讀到已被推翻的數字。
- **F2｜Go/No-Go 對 bootstrap seed 敏感**（§5）。硬性判定用單一 seed 的 CI 含不含 0，
  邊界分箱的判定因此不可重現。可選修法：多 seed 取多數決、或改回報 CI 而非二元顯著。
  本卡不動 `verdict_for()`（會改變已發布卡的判定語意）。
- **F3｜對外文案裡的母體數字會持續漂移**。「1,826 場／138,949 打席」隨賽季進行每天變動，
  目前寫死在 `web/src/lib/methodology-content.ts`。要嘛標 as-of 日期，要嘛改由 artifact 供給。
- **F4｜`winprob_val` 與 `winprob_strength` 有第二處判準複製**：
  `_pa_state_counts_as_of()` 手抄了上游的 fail-closed 判準（本卡已同步更新並由既有 parity
  測試釘住）。這種「複製判準 + 測試釘住」的模式已經是第二次出現，長期應把 as-of 界限下推到
  `load_eval_season()` 本身。

---

## §7 待需求方裁決

### P1｜`pre_scores_from_events()` 是否上抽到 `models/`

現況是 models 以函式內延後 import 取用 api 層的純函式（§1.1），能跑、不重複實作，但分層是髒的。
乾淨解要動 `src/cpbl/api/routers/recap.py`（不在本卡寫入集，且無並行卡持有）。
建議：獨立小卡上抽到 `models/pa_facts.py`，`recap` re-export 保持相容。

### D1｜D scope 的 `wp_reliability` 要怎麼寫

`unsupported` 的唯一支撐（池化十分位 2 顯著超界）在今日資料上不再重現，但那是 bootstrap
實現的隨機性（§5：7–8/12 seed）。三個選項：
(a) 維持 `unsupported`，把理由改寫成「偏差 +4.9pt 幅度超界，顯著性隨重抽實現擺盪」；
(b) 依現行機械判定翻成 `supported`——**不建議**，等於讓對外可信度標籤吃 seed 的運氣；
(c) 先修 F2 的判定方法，再重跑定案。
**執行者不自行選擇。**

### C1｜對外文案要改哪些字（**只列出，未改**）

| 位置 | 現行文字 | 修正後應為 | 成因 |
|---|---|---|---|
| `src/cpbl/api/routers/recap.py` `WP_RELIABILITY_SCOPES["A"].validation` | 「2021–2026 池化 1,826 場／138,949 打席」 | 1,855 場／140,991 打席（2026-08-07） | 母體漂移 |
| 同上 | 「低十分位…高估 +4.2~+6.0pt、十分位 8…低估 −4.3pt」 | +4.2~+6.1pt／−4.5pt | **取樣修正**＋漂移 |
| 同上 `["A"].known_bias` | 「極端分箱已知偏差 ±4–6pt；池化 Brier 0.153 vs 0.245」 | **不需改**（Brier 逐位不變、±4–6pt 仍涵蓋） | — |
| 同上 `["C"].validation` | 「代理池化 ECE 0.110 > 0.05、全期僅 25 場」 | 0.110（0.11001）、25 場 — **不需改** | — |
| 同上 `["D"].validation` | 「池化十分位 2 偏差 +4.7pt 顯著超界」 | 見 §7-D1，**待裁決** | 母體漂移＋seed |
| 同上 `["E"].validation` | 「池化 ECE 0.085 > 0.05、E2025 Brier 0.289 輸給主場常數基準 0.253」 | ECE 0.085（0.08548）不需改；E2025 Brier **0.286** vs 0.253 | 取樣修正＋漂移 |
| `web/src/lib/methodology-content.ts:92`（`winprob-validation`） | 「一軍例行賽池化共 1,826 場、138,949 個打席」 | 1,855 場／140,991 打席（2026-08-07） | 母體漂移 |
| `web/src/lib/methodology-content.ts:101` | 「十分位 1／2／3 被高估 +4.2／+5.3／+6.0…（十分位 8）被低估 −4.3」 | +4.2／**+5.5**／**+6.1**／**−4.5** | **取樣修正**＋漂移 |
| `web/src/lib/methodology-content.ts:99` | 「主場常數基準…池化 Brier 0.245」 | **不需改** | — |
| `web/src/lib/methodology-content.ts:131`（`key-plays`） | 「池化 Brier 0.153 對主場常數基準 0.245」 | **不需改**——#80 WPA 三階修訂所依據的「校準有偏、辨別力為真」在修正後逐位成立 | — |

> `web/` 與 `api/routers/recap.py` 皆不在本卡寫入集（`web/` 另由 #81 持有），一字未動。

---

## §8 驗證

```
uv run ruff check     # All checks passed!
uv run pytest         # 1428 passed, 10 skipped（基準 1422/10；+6 為本卡新增測試）
```

本卡新增測試（`tests/test_winprob_val.py`）：

- `test_eval_sample_uses_pre_pa_scores_not_the_polluted_snapshot` — 病灶最小重現（首球全壘打）
- `test_legacy_pre_state_source_reproduces_the_contaminated_diff` — 對照組必須仍能重現污染值
- `test_scores_between_plate_appearances_are_still_carried` — 打席**之間**得分（盜壘／暴投）不得被吃掉
- `test_unresolved_pre_score_fails_closed_and_is_counted` — fail closed 且獨立計數
- `test_pre_score_resolution_delegates_to_the_single_recap_implementation` — 釘住「只有一份實作」
- `test_unknown_pre_score_source_is_rejected` — 來源參數白名單

`tests/test_winprob_strength.py` 的兩支 as-of parity 測試已擴充涵蓋新的
`ready_pre_score_unresolved` 分支，維持「上游判準與 as-of 重算逐鍵相同」的釘子。

## §9 產物清單（皆可於交付 HEAD 重現）

| 檔案 | 內容 |
|---|---|
| `census.py` / `population_census.json` | 逐季受影響打席母體 |
| `compare.py` / `val1_comparison.json` | VAL1 三路對照（含未捨入 Δ） |
| `bin_stability.py` / `bin_stability.json` | 邊界分箱的 seed 穩健度 |
| `val1_metrics_events.json` / `val1_metrics_pre_state.json` | VAL1 兩路完整 artifact |
| `strength1_metrics_events.json` / `strength1_metrics_pre_state.json` | STRENGTH1 兩路完整 artifact |
