# ML-UMP1 研究規格：好球帶判決差異的預期狀態影響

> 狀態：Approved（ruan6047，2026-07-15）
> 卡片：`ML-UMP1`
> 規劃：GPT-5@Codex
> 日期：2026-07-15

## 0. 決策摘要

本研究可以執行，但原需求中的「裁判誤判」必須降級為「固定好球帶代理 [fixed strike-zone proxy] 與實際判決的差異」；目前資料不足以建立逐打者規則好球帶真值 [ground truth]，更不能把差異稱為已證實的誤判。

原因有二：

1. CPBL 規則的垂直好球帶取決於擊球員準備揮擊時的正常姿態；`pitch_tracking` 沒有逐球 `sz_top`／`sz_bot` 或姿態資料。現有 `Z_BOT=0.423`、`Z_TOP=1.077` 只是固定代理帶，不是規則真值。
2. 既有 `RE24` 只包含壘況×出局。called ball 與 called strike 在非終結球上都不改變壘況或出局，直接相減無法衡量球數差異。研究必須建立球數×壘況×出局的狀態價值 [state value]，而非直接復用 `cpbl.run_expectancy`。

研究的主要產出是可重現的狀態價值估計、資料品質報告與敏感度分析；未通過統計紅線查核前，不新增 API、資料表、公開排行榜或 UI。

## 1. 目標與研究問題

### 1.1 目標

對 2026 年一軍例行賽、具有 TrackMan 位置資料的未揮棒球，估計「實際 ball／strike 判決」相對於「固定代理帶所指示的判決」造成的聯盟平均預期狀態差異，並按單場、攻守球隊與主審做描述性聚合。

回答四個問題：

1. 某顆判決差異，在該球之前的球數、壘況、出局、局數與比分下，預期得分差多少？
2. 若勝率模型通過獨立驗證，該差異對主隊勝率的狀態價值差多少？
3. 加入球數與比賽情境後，與「差異顆數」及「離代理帶距離」兩個 baseline 相比，聚合結論如何改變？
4. 結論是否對代理帶邊界、場地覆蓋、單場抽樣及價值模型估計誤差穩健？

### 1.2 成功定義

- 可以從歷史 livelog 建立無資料洩漏的球數感知 [count-aware] 狀態價值，並在 2025 留出集優於不含球數的基準 [count-agnostic baseline]。
- 2026 TrackMan called pitches 與 livelog 的唯一連結率及合法球數率皆至少 99.5%。
- 每顆輸出都可由 pre-call state、兩個反事實轉移與狀態價值重算，不依賴黑箱的「直接影響分數」。
- 聚合結果同時附樣本數、場次、TrackMan 覆蓋率、95% 區間與代理帶敏感度。
- 任何公開文字只描述「好球帶判決差異的預期狀態價值」，不描述為實際得失分、實際勝負改寫或裁判真實誤判；技術契約仍須揭露使用固定代理帶。

### 1.3 非目標

- 不建立逐打者規則好球帶真值。
- 不宣稱識別出裁判的因果效果、能力或偏誤。
- 不把後續實際發生的得分歸因給單一判決。
- 不評估揮棒球、界外球、觸身球、故意四壞或未捕第三好球的裁判正確性。
- 不在本卡修改現有 `/umpires`、球員頁、賽況頁或公開 API。
- 不把捕手 framing、投手控球、打者姿態或 TrackMan 場地選擇偏差誤算成主審效果。

## 2. 權威定義與方法依據

1. [CPBL 2025 官方棒球規則](https://cpbl.com.tw/files/file_pool/1/0p065549820043528193/2025%E6%A3%92%E7%90%83%E8%A6%8F%E5%89%87%28%E5%AE%98%E7%B6%B2%E7%94%A8%29.pdf)定義垂直好球帶須依打者準備揮擊時的姿態決定。這直接否定固定公尺高度可作為逐球規則真值的前提。
2. Albert, *Using the Count to Measure Pitching Performance*（[DOI 10.2202/1559-0410.1279](https://doi.org/10.2202/1559-0410.1279)）指出球數會顯著改變打席後續價值，支持使用 count-aware valuation，而非單純 RE24。
3. Deshpande & Wyner, *A Hierarchical Bayesian Model of Pitch Framing*（[DOI 10.1515/jqas-2017-0027](https://doi.org/10.1515/jqas-2017-0027)）以位置、球數、投捕打與裁判情境估計 called-strike probability，並強調聚合價值具有顯著不確定性。本文採其「球數敏感價值＋不確定性不可省略」原則，但本卡不實作 catcher／umpire 因果效果模型。
4. Parsons et al., *Strike Three: Discrimination, Incentives, and Evaluation*（[AER DOI 10.1257/aer.101.4.1410](https://pubs.aeaweb.org/doi/10.1257/aer.101.4.1410)）顯示 called-strike 判決會受可觀測情境影響；未控制情境的裁判排行不可解讀為個人能力或偏誤。

## 3. 2026-07-15 資料可行性稽核

以下數字來自本機 `cpbl` schema 的唯讀 SQL 快照，研究實作時必須由正式 audit command 重算，不得硬編碼：

| 項目 | 實測 | 判定 |
|---|---:|---|
| 2026 A 組全部 TrackMan pitches | 45,759 | 僅作覆蓋母數 |
| `StrikeCalled`＋`BallCalled` | 24,270 | 研究初始母體 |
| 精確唯一連到 livelog | 24,195（99.69%） | 通過 99.5% gate |
| 合法 post-call 球數，可還原 pre-call | 24,226（99.82%） | 通過 99.5% gate |
| 已連結列缺 catcher／攻守方／比分 | 0 | 通過 |
| 固定代理帶與實際判決不同 | 2,695（11.10%） | 只代表 proxy disagreement |
| 其中代理帶外 called strike | 1,038 | 不稱「多判好球」真值 |
| 其中代理帶內 called ball | 1,657 | 不稱「漏判好球」真值 |
| 歷史 2018–2025 一軍 livelog pitch rows | 730,112／2,335 場 | 足以建立 count-aware baseline |
| 2026 有 called pitch 的一軍場次 | 165 | 場地覆蓋不完整 |
| 有樣本主審 | 18 人；每人 5–13 場、668–1,925 球 | 禁止硬排精確名次 |

場地選擇偏差已可觀察：例如嘉義市、花蓮為 0 場 TrackMan，大巨蛋 20 場完成賽中只有 6 場有 called-pitch tracking。研究必須以「逐場有無追蹤」計算 coverage，不得沿用固定的「某球場一定有／無設備」清單。

## 4. 資料契約

### 4.1 母體

納入：

- `year=2026`
- `kind_code='A'`
- `pitch_call IN ('StrikeCalled', 'BallCalled')`
- `plate_loc_side`、`plate_loc_height` 非 NULL
- 可唯一連到同場 livelog，並取得 pre-call state 所需欄位
- post-call 球數符合合法狀態

排除：

- 無 TrackMan 的場次與球；不得當作正確判決或零影響
- 二軍／季後賽
- 無法唯一連結或球數不合法的列；逐原因計數
- 被官方更正、比賽狀態不完整或無主審的場次

### 4.2 唯一連結鍵

TrackMan 與 livelog 以以下欄位等值連結：

```text
year, kind_code, game_sno,
pitcher_acnt, hitter_acnt, inning_seq, batting_order,
pitch_cnt, ball_cnt, strike_cnt, out_cnt,
call flag: BallCalled→is_ball / StrikeCalled→is_strike
```

要求每顆 TrackMan pitch 恰好命中一筆 livelog。零筆或多筆都進隔離區 [quarantine]，不以 `row_number()` 任意挑選。

### 4.3 球數語意

兩來源的 `ball_cnt`／`strike_cnt` 均為 post-call count：

```text
BallCalled:   pre = (ball_cnt - 1, strike_cnt)
StrikeCalled: pre = (ball_cnt, strike_cnt - 1)
```

合法 post-call：

- BallCalled：balls 1–4、strikes 0–2
- StrikeCalled：balls 0–3、strikes 1–3

四壞與三振是合法終結狀態，不得因出現 balls=4 或 strikes=3 被誤刪。

livelog 的壘況／出局是事件前快照，比分是事件後快照；pre-call 比分必須依 `main_event_no::bigint` 排序，以前一事件的 post-score 重建（首局從 0-0 開始），沿用 `models/sabr.py` 已驗證的快照語意。不得把同列 post-score 當成判決前比分。

### 4.4 代理好球帶

`fixed_zone_proxy_v1` 為現有 UI 契約：

```text
abs(plate_loc_side) <= 0.253m
0.423m <= plate_loc_height <= 1.077m
```

名稱與輸出必須包含 `proxy`。不可輸出 `correct=true/false` 作為研究 canonical 欄位；應輸出：

```text
observed_call: ball | strike
proxy_call: ball | strike
proxy_disagreement: bool
edge_distance_cm: signed distance to proxy boundary  # 帶內為正，帶外為負
zone_definition: fixed_zone_proxy_v1
```

現行 `umpires.py` 只排除「代理帶外且超過 50cm 的 called strike」，屬非對稱 outcome-dependent filter，研究不得沿用。除缺值與明確契約異常外，主要分析不依判決方向刪資料；現行 50cm 規則只能列為敏感度對照。

## 5. 估計量與符號

令 pre-call state：

```text
s = (batting_side, inning, score_diff_home,
     bases, outs, balls, strikes)
```

`T_B(s)` 與 `T_S(s)` 分別是把同一顆未揮棒球判為 ball／strike 後的狀態轉移，包含：

- 非終結球：只改球數
- 第四壞球：強迫進壘與可能的立即得分，下一打者 0-0
- 第三好球：增加一出局；三出局則半局結束

未捕第三好球等例外不在研究母體的標準反事實內；若 observed data 顯示例外事件，該球進 quarantine。

### 5.1 預期得分差

`V_R(s)` 是從狀態 `s` 到半局結束的聯盟平均剩餘得分期望。對同一 pre-call state：

```text
U_R(s, a) = immediate_runs(T_a) + V_R(T_a(s))
delta_runs_offense = U_R(s, observed_call) - U_R(s, proxy_call)
```

正值只表示該實際判決相對代理判決提高打擊方的聯盟平均狀態價值；不是該球之後實際多得的分數。

### 5.2 主隊勝率差（條件式產出）

`V_W(s)` 是主隊視角的聯盟平均勝率：

```text
delta_wp_home = V_W(T_observed(s)) - V_W(T_proxy(s))
```

只有第 7 節 WP gate 通過才產出。未通過時研究仍可只交付 run value，不得以 runs-to-wins 常數硬轉換。

### 5.3 聚合

每顆差異依打擊方／守備方與主審聚合：

- `sum_delta_runs_offense`
- `sum_delta_wp_home`（若通過）
- 每 100 called pitches 標準化值
- games、called pitches、proxy disagreements、tracked/completed games coverage
- game-cluster 95% interval
- zone-boundary sensitivity envelope

球隊欄位只可稱 `state_value_for/against`；禁用「實際得利」「被偷走幾勝」「裁判送分」。

## 6. 狀態價值模型

### 6.1 Count-aware remaining-run distribution

用 2018–2025 一軍 livelog 重建每個 pre-pitch state 的半局剩餘得分分布：

```text
P(K | batting_side, bases, outs, balls, strikes)
```

不直接使用現有 `K_CAP=6` 截斷期望值。新研究保留訓練資料觀察到的完整 `K` 支持集；若為儲存壓縮設 overflow bucket，必另存該 bucket 的條件平均，避免把 6+ 全當 6 分。

訓練母體排除未完成三出局的截斷半局（再見、裁定或資料不完整），避免系統性低估剩餘得分；排除數量必列入 waterfall。

稀疏 state 以 Dirichlet 部分池化 [partial pooling] 回縮到父分布：

```text
P_shrunk = (counts_state + alpha * P_parent) / (n_state + alpha)
parent = P(K | batting_side, bases, outs)
```

`alpha` 只用 2024 validation 選定；2025 test 不參與調參。若 count state 不足或違反結構性單調條件，逐級 backoff 到 parent，並記錄 backoff rate。

### 6.2 勝率

沿用 `models/winprob.py` 的半局邊界動態規劃 [dynamic programming] 與 CPBL 12 局和局規則，但場中剩餘得分分布改讀 count-aware distribution。不得直接復用目前不含球數的 `wp_state()` 來替 called pitch 定價。

### 6.3 結構性檢查

對打擊方而言，相同 pre-call state 下應滿足：

```text
U_R(s, Ball) >= U_R(s, Strike)
U_W_batting_team(s, Ball) >= U_W_batting_team(s, Strike)
```

任何有足夠樣本的 state 違反此條件，都視為估計器失效或需 backoff，不可把反號結果直接寫入報告。

## 7. 時間切分與驗證閘門

### 7.1 切分

| 用途 | 年度 |
|---|---|
| train | 2018–2023 |
| shrinkage tuning | 2024 |
| untouched test | 2025 |
| 最終重估、供 2026 scoring | 2018–2025 |

所有 state values 只能用 scoring 年度之前的資料。2026 實際比賽結果不得回灌 2026 pitch scoring。

### 7.2 Baselines

模型 baseline：

1. count-agnostic `P(K | side, bases, outs)`
2. 現有 `wp_state()`
3. 主場聯盟常數勝率（WP sanity baseline）

所有 baseline 必須用與候選模型完全相同的 train／tune 資料重建；禁止拿已看過 2025 的 production `run_dist`／`win_expectancy` 來評 2025 test。

產品指標 baseline：

1. proxy disagreement count／rate
2. `sum(abs(edge_distance_cm))`

### 7.3 Gate

在 2025 untouched test：

- remaining-run distribution 的 multinomial log loss 必須優於 count-agnostic baseline，且 expected-runs MAE 不得退化。
- WP 的 Brier 與 LogLoss 點估計皆不得差於現有 `wp_state()`；至少一項改善的 game-cluster bootstrap 95% interval 不得跨 0。
- 回報 calibration intercept、slope、十分位 reliability 與 ECE；不得只報 Accuracy。
- paired bootstrap 以 game 為抽樣單位，至少 2,000 replicates；不可把 pitch 當獨立樣本。
- 唯一連結率、合法球數率皆至少 99.5%，且所有 exclusion reason 有固定枚舉與數量。
- 結構性單調檢查通過；所有 backoff state 與比例可追溯。

WP gate 未過：只保留 run-value 研究，不產出 WP。Run-value gate 未過：整卡結論為 no-go，不進 API／UI。

## 8. 不確定性與敏感度

### 8.1 抽樣不確定性

- 以整場為 cluster bootstrap 單位，同時重建 value table 並重算聚合。
- 每位主審回報 2.5%、50%、97.5% 分位數，不做無區間精確排行。
- 不以「信賴區間重疊／不重疊」宣告兩位裁判顯著不同；若未建立預先指定的 pairwise test，不做顯著性敘述。

### 8.2 代理帶敏感度

固定代理帶不是 ground truth，因此必須對水平與垂直邊界做對稱擴張／收縮曲線：0、±1、±2、±3、±5cm。這些是 robustness scenarios，不是 TrackMan 測量誤差的信賴區間。

若某主審或球隊的影響方向在合理 scenario 間翻轉，標示 `zone_sensitive=true`，不得給方向性結論。

### 8.3 覆蓋敏感度

- leave-one-venue-out
- home／away、月份、主審樣本場次分布
- tracked games／completed games coverage
- 現行非對稱 50cm filter 僅作對照，不作主要結果

如果 leave-one-venue-out 會翻轉結論，標示 `coverage_sensitive=true`。

## 9. 研究輸出契約

### 9.1 每球 audit row

```text
year, kind_code, game_sno, pitch identity
umpire, batting_team, fielding_team, catcher_acnt
pre-call inning/half/score/bases/outs/balls/strikes
plate_loc_side, plate_loc_height, edge_distance_cm
observed_call, proxy_call, proxy_disagreement, zone_definition
run_value_ball, run_value_strike, delta_runs_offense
wp_ball, wp_strike, delta_wp_home  # nullable until WP gate passes
link_status, exclusion_reason, model_span, model_version
```

### 9.2 報告

產出 `docs/research/ML-UMP1_RESULTS.md`，至少包含：

- 資料 flow 與 exclusion waterfall
- test-set metrics／calibration／bootstrap intervals
- state value 表與四壞、三振、滿壘、兩出局等人工可驗算案例
- baseline 對照
- 主審／球隊描述性聚合與 coverage
- zone／venue sensitivity
- no-go 或可進下一階段的明確結論

研究 artifacts 放 `artifacts/`，不得 commit 大型逐球輸出或模型檔。

## 10. 預定專案結構與命令

本 spec 核可後才進實作；研究階段預定不新增 runtime dependency，使用既有 Python 3.12、NumPy、SciPy、scikit-learn、psycopg3。

```text
src/cpbl/models/umpire_impact.py        # state reconstruction、valuation、audit
src/cpbl/models/run_umpire_impact.py    # CLI；離線研究，API 不觸發
tests/test_umpire_impact.py             # state transition／單調／資料契約
tests/test_umpire_impact_integration.py # 本機 DB 可選 integration audit
docs/research/ML-UMP1_RESULTS.md         # 實測研究報告
```

預定命令：

```bash
uv run cpbl-research-umpire-impact audit --season 2026 --kind A
uv run cpbl-research-umpire-impact validate --train 2018:2023 --tune 2024 --test 2025
uv run cpbl-research-umpire-impact score --model-span 2018:2025 --season 2026 --kind A
uv run pytest tests/test_umpire_impact.py
uv run pytest tests/test_umpire_impact_integration.py -m integration
uv run ruff check
```

CLI 名稱與檔案是預定介面；核可 spec 前不視為既有功能。

## 11. 程式風格與測試策略

### 11.1 風格

- 純狀態轉移函式不得查 DB；SQL 載入與估計分層。
- SQL 全部參數化並走 `cpbl.db.conn()`。
- migration 若後續產品化才新增；不得修改既有 migration。
- 離線研究不由 API request 觸發。

示意介面：

```python
def transition_called_pitch(state: PitchState, call: Call) -> Transition:
    """回傳新狀態、立即得分與是否結束半局；不查 DB。"""
```

### 11.2 必測案例

- 0-0 ball／strike 的一般轉移
- 3-2 ball：空壘、壘上有人、滿壘強迫得分
- 0／1／2 出局的第三好球；兩出局時半局結束
- 主客攻擊方向與 `delta_wp_home` 正負號
- TrackMan post-call → pre-call 還原
- 零匹配／多匹配進 quarantine，禁止任挑一筆
- 2025 test 完全不參與 tuning
- count-aware → parent backoff
- 所有支持 state 的 ball value 不低於 strike value
- proxy 邊界擴張與收縮完全對稱
- exclusion 不得依 observed call 採不同規則

## 12. 邊界

### Always

- 每次 scoring 前重跑 audit gate。
- 先做時間切分驗證，再用 2018–2025 final refit。
- 所有聚合帶 coverage、樣本與區間。
- 研究報告保存 model span、資料快照時間與 git SHA。
- 紅線查核必由不同模型家族或人審，並重跑 DB audit 與 held-out validation。

### Ask first

- 新增 migration／canonical table。
- 新增 Python dependency 或改 Docker image。
- 新增 API、UI 或公開主審／球隊結論。
- 將 fixed proxy 替換成另一種 zone definition。
- 把描述性聚合升級成 umpire causal／ability model。

### Never

- 用固定垂直帶宣稱逐球規則真值。
- 把 expected state difference 稱為實際得分或實際勝負改寫。
- 用 2026 結果訓練後再回評同一批 2026 pitches。
- 把 pitches 當獨立 bootstrap 單位。
- 只報 Accuracy、單一排名或無區間累計值。
- 沿用 outcome-dependent asymmetric filter 當主要樣本。
- 模型未勝 baseline 或未通過跨家族實測查核就進 UI。

## 13. 實作拆分（spec 核可後）

- [ ] R0：資料 audit 與 deterministic linker
  - Acceptance：重現第 3 節 waterfall；唯一連結／合法球數 gate 可自動 fail。
  - Verify：本機 DB integration test＋quarantine 抽樣人工核對。
  - Files：model、CLI、unit test、integration test。
- [ ] R1：count-aware remaining-run distribution
  - Acceptance：時間切分、partial pooling、backoff、單調檢查完整；2025 run-value gate 通過。
  - Verify：held-out NLL／MAE＋2,000 次 game bootstrap。
  - Files：model、unit test、results report。
- [ ] R2：count-aware WP
  - Acceptance：Brier／LogLoss／calibration gate 通過；不通過即 no-ship WP。
  - Verify：與現有 `wp_state()` paired game-bootstrap 對照。
  - Files：model、unit test、results report。
- [ ] R3：2026 scoring 與敏感度
  - Acceptance：每球 audit、主審／球隊聚合、zone／venue sensitivity 全可重現。
  - Verify：人工驗算終結球案例＋總和恆等與 coverage 對帳。
  - Files：CLI、integration test、results report。
- [ ] R4：跨家族紅線查核
  - Acceptance：查核者獨立重跑 audit、validation、案例驗算；findings 清零。
  - Verify：查核紀錄與實測輸出進卡片 Log。
  - Files：不由查核者修改實作；缺陷退回原執行者。

## 14. 已核可決策

ruan6047 於 2026-07-15 核可以下四項：

1. 研究與未來產品文案改用「好球帶判決差異」，不使用「裁判誤判」作為 canonical 名稱；技術欄位仍保留 `proxy` 語意。
2. 本卡主要交付為 run value；WP 是通過獨立 gate 才附加的條件式輸出。
3. 研究階段只做離線報告，不新增 API／UI／production table。
4. fixed proxy v1 只為相容現有頁面，必須附邊界敏感度且不得當 ground truth。

## 15. ML-UMP2 增補：逐打者身高比例代理帶

> 狀態：Approved（ruan6047，2026-07-16）
> 卡片：`ML-UMP2`；執行：GPT-5@Codex；查核必須跨模型家族或人審。

### 15.1 定義與資料 gate

- canonical 名稱為 `height_scaled_proxy_v2`：`sz_top=0.535×身高`、`sz_bot=0.270×身高`，水平半寬沿用 0.253m。
- 這仍是站立身高比例代理，不是準備揮擊姿態的規則真值；文案不得使用「誤判」。
- `pitch_tracking.hitter_acnt` 必須精確連到 `players.id`；無球員列與 `height_cm IS NULL` 分開計數，不得 fallback 到 fixed v1。
- pitch-weighted coverage 與 distinct-hitter coverage 皆需 ≥99.5%，且評分後必須仍含 18 主審／6 隊；否則 fail closed，不產生方向性結論。

### 15.2 敏感度與主 gate

- v2 主情境及所有上下左右邊界對稱 ±1/2/3/5cm，每個 margin 都依各球打者身高重建帶。
- 主 gate 是零翻轉：18 主審與 6 隊在全 margins 中的符號翻轉數必須同時為 0；球隊任一 `for`／`against` 翻轉即計為該隊翻轉。
- 同時保留 fixed v1 全表對照、leave-one-venue-out、home/away、月份、既有非對稱 50cm filter；bootstrap 仍以 game 為 cluster、2,000 replicates。
- 球緣情境只是 secondary sensitivity：依官方球周長 22.9–23.5cm 取中點換算半徑，以球心到矩形帶的歐氏距離判定是否觸帶；不影響主 gate。

### 15.3 決策解讀

- 任一主審或球隊的 margin 方向翻轉：方向性產品繼續 no-go。
- 只有零翻轉 gate 通過，才能說「判決差異偏向 X 隊」；仍必須附區間與敏感度，且 API／UI 需另卡核可。
- state value 不是實際得失分、因果效果或「裁判送分」；描述性聚合不做精確排行。
