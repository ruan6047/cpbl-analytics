# GAME-RECAP-WP-STRENGTH1 場中 WP 戰力感知先驗〔T4；🔴統計〕

- 需求：ruan6047（2026-07-26 會話確認走 VAL1 §7 路徑 2）　規劃：**GPT-5.6@Codex（L4；2026-07-26 完成規劃並凍結本卡，需求方已核可 sign-off）**　分支：依認領時 worktree 慣例
- 執行：**Claude Opus 5@Claude Code**（分支 `ai/opus-5/GAME-RECAP-WP-STRENGTH1` @ `.claude/worktrees/game-recap-wp-strength1-execution`；source `13e5f23`）　查核：待指派（**建議 L4；須跨家族或人工，且 ≠ 執行；重跑留出季與統計紅線**）
- Initiative：INIT-GAME-RECAP　spec 基線：v1.3
- DB：`db_scope: read`（研究階段唯讀；先驗參數 artifact 落檔案，物化與 `model_versions` 寫入屬 WP-API1 或其子卡——同 CAL1 慣例）
- 部署：否　環境：—　PR：—　Merge SHA：—
- 範圍：**僅 A 一軍例行、核心資料自 2018 起**。依資料能力分 `≤2017`／`2018–2025`／`≥2026` 三期（見下）；C 需種子／讓一勝感知另卡（VAL1 §7.3），D/E 維持 unsupported
- Discovery：`GAME-RECAP-WP-VAL1` ✅（偏差結構已量化）＋`GAME-RECAP-WP-CAL1` 🏁（事後校準 No-Go，機制見其報告 §5）＋[`GAME-RECAP-WP-STRENGTH1_RESEARCH`](../research/GAME-RECAP-WP-STRENGTH1_RESEARCH.md) ✅（國內外研究與 CPBL 可移植性）
- Plan review：Google Gemini 3.6 Flash（跨家族）[`APPROVE`](../research/GAME-RECAP-WP-STRENGTH1_PLAN_REVIEW.md)（C1–C20 PASS；P0–P2=0、P3=1）。此輪只查規劃矛盾，不取代未來 implementation review
- Design：Design Gate N/A；純統計模型層，不改 public API 或 UI
- current-state：🔍待查核（iteration 1）；交付 [`GAME-RECAP-WP-STRENGTH1_RESULTS`](../research/GAME-RECAP-WP-STRENGTH1_RESULTS.md) → **A scope unsupported（No-Go）**：硬門檻「融合後不得劣於同代 base」在 2023／2025 兩季失敗，根因為八項凍結賽前特徵在時間外幾乎不含增量資訊。`GAME-RECAP-WP-API1` A 範圍維持阻塞。分支與 worktree 保留供查核者進駐。

## 背景與目標

WP-VAL1 證實 A scope 時間外 S 型偏差（低分箱 +4.2~+6.0pt／高分箱 −4.3pt，99% game-cluster CI 排除 0）。兩端成因不同：

- **高分箱（領先方低估）是結構性的**：現實中領先方不成比例地是較強隊或由較強先發投手出賽；中性隊伍假設的局面 DP 看不到此資訊。in-sample 亦有 −2.8pt 顯著偏差，事後校準無法治本。
- **低分箱（落後方高估）主因主場優勢漂移**：2023+ base 的早局帶已自行吸收大部分漂移；CAL1 的全域中心下修雖修平池化分箱，卻使 1–3 局帶 |dev| 由 0.1pt 惡化至 2.6pt。

本卡目標是在既有局面 WP 之上加入**僅由賽前可知資訊形成的隊伍戰力／先發投手先驗**，消除兩端偏差，使 A scope 通過 WP-VAL1 v2 與本卡加嚴的逐局帶門檻，才可解除 `GAME-RECAP-WP-API1` 的 A 範圍阻塞。

**排除路線（勿重走）**：校準窗變體（recency 窗／衰減加權／逐局帶條件化校準）。CAL1 §7 已將其列為低勝率路線，本卡不得以此替代戰力感知設計。

## 三期資料策略與分卡邊界

| 時期 | 現有資料能力 | 本卡用途 | 明確限制／後續 |
|---|---|---|---|
| **≤2017** | `batting_seasons`／`pitching_seasons` 逐年球員與 team_id 彙總；沒有 canonical PA、逐場 `games`／gamelog 或逐隊勝敗表可供同口徑重建 | 只允許 2017 球員／球隊投打率作 2018 冷啟動 prior；`prior_winpct_diff` 因無 2017 逐隊勝敗仍回中性 0；不納入 game-level fit、選型或 WP 驗證 | 不為追求長歷史另造低粒度假樣本；若未來取得逐場資料再另卡 Discovery |
| **2018–2025** | A 例行逐場、逐打席與 pitching/batting gamelog 完整；可在每場結果套用前重建 season-to-date 隊伍、先發與牛棚指標 | **核心訓練與歷史 walk-forward 母體**；所有可上線特徵都必須在此期可重建 | 沒有官方 2026 進階站的歷史 TrackMan leaderboard；只能用逐場 box 可追溯計數衍生 |
| **≥2026** | 上述核心資料持續存在；另有官方 `advanced_stats`、逐球 TrackMan、球種／擊球品質。本機 DB 與官方公開 UI 目前只可核對 2026，且本機 TrackMan coverage 非完整；缺場機制尚未完成查核 | **2026 是最重要的最終 holdout／當季產品證據**；核心模型照樣消費截至賽前的當季 running state | 官方 advanced／TrackMan 只做 shadow／前瞻蒐集，不參與本卡選型或 Go；另拆 `GAME-RECAP-WP-STRENGTH-ADV1` 規劃，待有時間快照、缺場機制分析與下一留出期再判定 |

成本裁定：本卡不補 `≤2017` 逐場資料，也不承擔 2026 advanced snapshot pipeline；先交付 2018+ 可完整回測的核心模型，並在報告排序上以 2026 當季結果為首、2023–2025 作穩定性反證。**2026 較有產品意義不等於可用 2026 結果挑模型**：它仍是鎖箱 holdout，否則會重犯 CAL1 的選型洩漏。

## 規劃定案：logit 空間先驗融合

### 候選比較與決策

| 候選 | 樣本／侵入性 | 統計風險 | 定案 |
|---|---|---|---|
| **logit 空間先驗融合** | 保留既有 48-state pooled `run_dist`，新增 2018+ 低維度賽前模型與融合層；可直接復用 `winprob_val`／`winprob_cal` 的 wf、metrics、bootstrap | 須預註冊先驗、season-running 收縮與 `w(t)`，並防止賽前特徵洩漏 | **採用**：連續、資料效率高、可讓 2026 當季資料在賽前逐場更新 |
| 戰力條件化 `run_dist` | 3/5 分箱在 `MIN_STATE_N=30` 下格數可行（附錄 A），不是因樣本量淘汰 | 每個狀態的 7 類得分機率被再切薄；硬分箱造成邊界不連續，戰力尺度或分箱一變即須重估整組分布 | 可行但不選；若主方案 No-Go，不得在本卡事後切換，須另卡預註冊 |
| 第三案 | 未提出 | 沒有證據足以勝過上述兩案 | 不開啟 |

### 融合形式與不變量

對驗證季 `Y`、比賽 `g`、canonical PA 賽前狀態 `s`：

```text
p0(g)       = sigmoid(beta0 + beta · x_pre(g))
p_base0(Y)  = 同一個 Y 代 base run_dist／ruleset 在「1 局上、0 出局、空壘、0:0」的主隊 WP
t(s)        = clamp(((inning - 1) * 6 + half_offset * 3 + outs) / 54, 0, 1)
               half_offset：上半=0、下半=1
w_gamma(t)  = (1 - t) ** gamma
WP_adj      = sigmoid(logit_clip(WP_situ) + w_gamma(t) *
                      (logit_clip(p0) - logit_clip(p_base0)))
```

- `logit_clip` 固定 `eps=1e-6`，只供數值計算；已終場／再見的 canonical 端點直接回 0/1，不經 clip 與融合。
- `p_base0` 必須由**同一代 base 解算器的開場狀態**取得，不得以跨代經驗主場勝率代替。於 `t=0` 時 `WP_adj=p0`；這可避免錯把 base 已含的主場優勢重複相加。
- `gamma>0`，故 `w(t)` 隨 regulation outs 單調遞減；9 局完成與 10+ 局固定為 0。固定 `(p0,t)` 時，`WP_adj` 對 `WP_situ` 嚴格單調且值域在 [0,1]。
- 此卡只建立與驗證離線融合層；不得修改 `winprob.py`、public API、前端或 production artifact。

## 先驗模型預註冊

### 目標、模型與特徵

- 目標 `y` 採主隊勝=1、敗=0、和局=0.5，與 WP 的「勝 + 0.5×和」語意一致；不得直接使用 `game_features.home_win`（和局為 NULL），須由唯讀 `games` 比分依同一規則建立標籤。
- 模型固定為含未懲罰 intercept 的 L2 正則化邏輯斯迴歸 [L2-regularized logistic regression]；最小化 `sum(binomial NLL) + lambda/2 * ||beta||²`。以決定性 Newton／等價凸優化求解，不使用隨機抽樣。
- 和局軟標籤 `y=0.5` 不得直接傳給只接受離散類別 target 的分類器 API。實作可用兩筆 `sample_weight=0.5` 的 `y=0/1` 等價拆分，或自訂上述凸目標；須以測試證明兩者 loss、梯度與預測等價，且不因拆列改變 game weighting。
- 連續特徵只以該次 fit 窗的 mean/std 標準化；零變異欄係數固定 0。補值、聯盟均值與收縮統計亦只能來自 fit 窗。
- 特徵方向皆定義為「正值有利主隊」，清單凍結如下；執行不得臨時增刪：

| key | 定義與賽前可得性 |
|---|---|
| `prior_winpct_diff` | 主隊−客隊上季最終勝率；新隊／缺值各以 0.5 |
| `winrate_diff` | 本季截至該場**套用結果前**的主隊−客隊勝率 |
| `run_margin_diff` | `runs_scored_diff - runs_allowed_diff`，皆為本季截至該場前的場均 running state |
| `rest_days_diff` | 主隊−客隊賽前休息天數，沿用上限 7 天與任一隊季內首戰→0 的既有慣例 |
| `starter_kbb_adv` | 主隊−客隊先發的 `(SO−BB)/PA`；由該場前 gamelog running count 對前一季／fit-window 聯盟率收縮 |
| `starter_recorded_strike_share_adv` | 主隊−客隊先發的 `strike_cnt/pitch_cnt`；只累積該場前投球，採同一收縮規則。此為 box/gamelog 記錄好球占比，不得稱為官方 TrackMan 好球帶率 `zone%` |
| `starter_fip_proxy_adv` | 客隊−主隊先發的 `(13×HR + 3×(BB+HBP) − 2×SO) / IP`，其中 `IP = inning_pitched_cnt + inning_pitched_div3/3`；低者較強，故反向定義為正值有利主隊 |
| `bullpen_kbb_adv` | 主隊−客隊非先發投手的 `(SO−BB)/PA`；由 `role_type != '先發'` 且該場前的 team running count 建立 |

特徵資料來源限 `cpbl.game_features` 中已於賽前更新的 running／prior 欄位、`cpbl.games` 的賽前先發 ID，以及 `cpbl.pitching_gamelog` 的逐場原始計數；2018 首季冷啟動才可讀 `cpbl.pitching_seasons(year=2017)`／fit-window 聯盟率作 prior。pitching gamelog 在 2018–2026 A 完成場為 100% game coverage；先發列中 5,098/5,102（99.92%）同時有正投球數、好球數與 PA，可 fail closed 補值而不必丟棄整場。

所有 rate 採同一**預註冊部分池化近似**：`shrunk_rate = (current_num + kappa * prior_rate) / (current_den + kappa)`；它受 empirical-Bayes 小樣本研究啟發，但本卡未由資料估計完整階層分布，不得冒稱完整 empirical-Bayes fit。`prior_rate` 先取該球員／球隊前一季同口徑值，缺值才退到 fit-window 聯盟率。FIP proxy 的四個事件計數以同一 `kappa` 對應的 prior event rates 收縮後再組合，禁止直接平均 rate。此設計讓當季資料隨分母增加自然取得更高權重，而不是永遠被前一季 ERA 主導；外部 MLB 的 stabilization 常數不得直接代入，`kappa` 仍只由 inner season 選定。

**不得直接使用現有 `game_features.starter_era_diff`、`starter_whip_diff`、`starter_k9_diff`**：`features/outcome.py` 目前以 `(starter_id, year)` 讀同季彙總，對歷史賽前模型會看見該季後續資料。也不得使用同季最終 standing、同場比分／PA 結果、賽後修訂名單、`pitching_current` 全季快照，或目前只有 2026 累計值的 `advanced_stats` 回填 2026 已賽場次。

2026 advanced shadow 可揭露 `whiff%`、`chase%`、HardHit%、Barrel%、球速／轉速與上述核心指標的相關性、coverage 與方向，但不得加入本卡 prior、超參選型或 Go/No-Go。若要讓它可上線，後續卡至少須保存 as-of snapshot 或由逐球資料重建 pregame running state，並以 2027 或預註冊的前瞻期間作真正留出驗證。

外部研究只提供候選的**結構合理性**，不預先宣稱任一欄位在 CPBL 有增量預測力：Yang & Swartz 是 2001 MLB、Brown 直接研究的是打擊率、FanGraphs 的 K−BB/FIP 為實務方法來源，CPBL 期刊則只涵蓋中職 30 年四隊個別模型。`rest_days_diff`、recorded strike share、FIP proxy 與 bullpen K−BB 的效用一律由預註冊 inner／holdout 指標決定，不得把文獻或搜尋摘要當驗收證據。

### 選型、超參數與融合權重

固定候選集合：

- `lambda ∈ {0.1, 1, 10, 100}`；intercept 不懲罰。
- `kappa ∈ {50, 100, 200}` PA-equivalent；共同控制 starter／bullpen rate 的前一季收縮強度，不得各指標另調。
- `gamma ∈ {0.5, 1, 2}`；皆保證 `w(0)=1`、`w(1)=0`。

對每個驗證季 `Y ∈ {2023, 2024, 2025, 2026}`，逐季執行以下**事先固定**程序：

1. 內部 fit 窗為 A 例行 `2018..Y-2`，內部前向選型季固定為 `Y-1`。每個 `(kappa, lambda)` 只在 fit 窗建立收縮特徵並擬合先驗，以 `Y-1` 的逐場 Brier 選最低者；未捨入差 `<1e-5` 時依序比較逐場 log-loss、再取較大的 `lambda`、最後取較大的 `kappa`（較強收縮）。
2. 以選定 `(kappa, lambda)` 對 `Y-1` 產生 p0；同時以 `2018..Y-2` base run_dist 對 `Y-1` PA 產生 `WP_situ`。每個 `gamma` 的融合結果以 `Y-1` 逐 PA Brier 選最低者；差 `<1e-5` 時比較 ECE，再同分依固定順序 `gamma=1 → 2 → 0.5`（先取線性衰減）。
3. `kappa/lambda/gamma` 鎖定後，先驗模型才以相同設定重 fit `2018..Y-1`，base run_dist 亦使用 `2018..Y-1`；兩者只評估 `Y`。不得查看 `Y` 結果後改模型族、特徵、候選網格、tie-break 或 `w(t)`。

因此最早驗證季 2023 的 inner fit／selection／final fit 分別為 2018–2021／2022／2018–2022；之後逐年向前滾動。各季驗證輸出來自不同代、但程序相同的模型，池化時必同時保留逐季列，不能把池化樣本誤稱為同分布。

研究診斷另固定輸出三組消融：`team-only`（前四項）、`team+starter`（前四項＋三項 starter）、`full`（八項，另加 bullpen）。消融只回答資料來源的增量資訊與共線風險，**full 是唯一驗收候選**；不得因驗證季消融結果較佳而切換上線模型或重做選型。FiveThirtyEight 官方封存資料只用來佐證 team rating＋starter 的架構類比；舊方法頁目前無法核對的休息／旅行常數與任何效果量均不作證據，更不得帶入 CPBL。

## 紅線（違反即退回）

1. **時間分離與擬合對象**：驗證季 Y 的 base 與最終先驗參數只 fit 2018..Y−1 的訓練賽果；超參／融合選型只能看「fit `2018..Y−2` 後對 `Y−1` 產生」的 out-of-time 預測。兩種擬合對象須在 artifact 分開標記，禁止用 Y、對 Y 的 in-sample 預測或跨代池化誤差反向調參。〔canonical #1 #2〕
2. **特徵洩漏**：僅可使用上節八項賽前特徵；season running state 必須在套用該場結果前計算。現有同季完整 starter／advanced snapshot 明確禁用；前一季資料、聯盟 prior、分子與分母均須有測試證明只含 `game_date` 前事件。〔canonical #3〕
3. **選型洩漏**：模型族、特徵、`kappa/lambda/gamma` 網格、目標、tie-break、融合式與門檻已在本卡凍結；不得以 2023–2026 任一目標季表現挑選或事後改動。2026 advanced shadow 不得進候選集合。若設計須變更，停止本卡並由需求方決定是否另卡。〔canonical #4 #5〕
4. **WP-VAL1 v2 門檻只可加嚴**：任一驗證季 coverage `<0.98`、`WP_adj` Brier 未勝該季 leakage-safe 主場常數基準、或 `WP_adj` Brier 劣於同代未融合 base，皆硬性失敗；池化十分位 `n≥1000` 若 `|pred-actual|>0.03` 且 99% game-cluster CI 排除 0，亦硬性失敗。全部判定使用未捨入值。〔canonical #4 #6〕
5. **逐局帶是硬性判定，不是附表**：池化 1–3／4–6／7–9 各帶 `n≥1000` 若 `|dev|>0.03` 且 99% game-cluster CI 排除 0即失敗；相對同代 base，任一帶 `|dev|` 惡化 `>2pt`，或至少兩帶各惡化 `>1pt`，亦失敗（沿用 CAL1 已預註冊門檻）。10+ 僅揭露，不作支持或否決證據。〔canonical #4 #7〕
6. **語意與數值合約**：固定 `(p0,t)` 時 `WP_adj` 對 `WP_situ` 單調、值域 [0,1]；開場等於 p0；終場／再見端點為 0/1；`w(t)` 不增且 9 局完成後為 0。任何一項破壞即退回，不得以總體指標補償。
7. **基準、時期與小樣本**：逐季及池化須並排未融合 base、CAL1 歷史判定與主場常數；報告先列 2026 鎖箱結果，再列 2023–2025 與池化。先驗 p0、≤2017 prior 與 2026 advanced shadow 的指標只作診斷。分箱 `n<1000`、10+ 局帶與其他未預註冊子群只能揭露，不可作 Go 證據。〔canonical #6 #7〕
8. **可重現**：DB 全程唯讀，bootstrap seed 固定 `20260725`；全跑與單季／部分重跑均須支援 `--out` 指向 scratch，禁止覆寫 canonical artifact。查核者至少重跑一個留出季並核對 window、分母、feature-year audit 與 artifact。〔canonical #8〕

   > **2026-07-27 需求方明確 sign-off 的紅線放寬**（原文：「降為『漂移偵測』並 sign-off」）：
   > 本條原要求「部分重跑**可逐位重現**」。經 iteration 1–3 查核實證，對持續入庫的 DB 達成真正
   > 逐位重現需要凍結 `games`／`game_features`／PA build／gamelog 的**輸入快照**——成本明顯超出
   > 本卡（研究性 No-Go 判定）的價值。**本卡的可重現性要求降為：相同 `--as-of` ＋ 相同 DB 狀態下
   > 輸出逐位相同，且母體／輸入若已漂移必須可被偵測並 fail loudly，不得靜默產出不同數字。**
   > 放寬僅限本卡；未來若 WP 相關產出要上線（非研究結論），須回到完整快照要求或另訂。
   > 此放寬由需求方裁定，非執行者自行改義（iteration 3 查核 F1 明確要求此 sign-off）。
   >
   > **仍須修正的具體缺陷（不因放寬而免除）**：`build_season_pack()` 仍呼叫使用 `CURRENT_DATE` 的
   > `load_eval_season()`，使 `coverage`／`n_irregular_games`／`pa_state_counts` 來自當下全表；
   > `advanced_shadow()` 不吃 as-of 卻被標 `data_as_of`（應改標 `observed_at` 並排除逐位比對）；
   > fingerprint 應涵蓋實際模型輸入與 published build identity，且不符時 fail loudly；
   > 報告 §9 的重現指令須帶 `--as-of`。

## 驗收條件

- [ ] 新增獨立 `models/winprob_strength.py`（或同責任名稱）消費 `winprob_val`／`winprob_cal` 公開 helper；不得修改兩個既有 harness、`winprob.py` 或任何 production path。全程唯讀 DB，artifact 與報告落 `docs/research/`。
- [ ] 離線合約測試覆蓋：三期 routing、八項特徵、逐場分子／分母只含該場前事件、`kappa` 收縮與缺值 fallback、和局 `y=0.5` 的加權拆分／自訂 loss 等價且 game weighting 不變、嵌套窗口、選型只讀 inner season、決定性 tie-break、`w(t)` 單調／端點、開場 anchor、[0,1] 與固定狀態單調性。
- [ ] 嵌套 walk-forward 報告逐季 2023–2026＋池化：**先列 2026 當季鎖箱結果**，再列歷史穩定性；包含樣本／coverage／窗口、先驗參數與標準化統計、`kappa/lambda/gamma` 選型證據、p0 診斷、Brier／ECE／十分位 99% game-cluster CI、逐局帶 99% CI 與排除帳；base／CAL1／主場常數三方並排，並附預註冊 `team-only`／`team+starter`／`full` 消融（僅診斷，full 才判定）。另附 2026 advanced shadow coverage／相關性，明標不進判定。
- [ ] A scope 逐條執行上述硬門檻；**全數通過才可解除 WP-API1 A 阻塞，任一失敗即 No-Go**，不得以「接近門檻」、平均改善或事後改候選放行。2026 為進行中賽季時須標示資料截止日與完成場數，且季末重跑仍為上線前必要證據。
- [ ] `uv run ruff check`＋`uv run pytest` 全綠；完整命令與 `--out` scratch 部分重跑可逐位重現。跨家族／人工查核者重跑至少一個留出季。

## 執行順序與查核 checkpoint

1. **資料與先驗層（M）**：唯讀建立三期 router 與八項 pregame feature rows，逐場累積 starter／bullpen 原始計數、`kappa` 收縮、年份／日期 audit、L2 logistic fit 與 inner selection；若任何特徵無法證明賽前可得即 fail closed，不得換用同季快照。
2. **融合與嵌套評估（M）**：實作 opening anchor、`w_gamma(t)`、逐季 refit／holdout 與逐局帶 bootstrap；復用既有 wf scoring，不另造寬鬆 metrics。
3. **報告與 Go/No-Go（S）**：固定 seed 全跑，提交 JSON artifact＋人讀報告，逐條列硬門檻與 No-Go/Go 證據。
4. **查核 checkpoint**：跨家族／人工 reviewer 以 `--out` scratch 重跑至少一季，核對 feature-year audit、inner/final window、分母、門檻與 artifact；任一紅線違反即退回。

## 依賴、交付與範圍估算

- 依賴：無阻塞（PA1 canonical、`winprob_val`／`winprob_cal` harness、`game_features` 皆已 merge）。
- 後續：通過 → 解除 `GAME-RECAP-WP-API1`（A scope），WP-API1 只消費版本化的「base WP + 2018+ core strength prior fusion」；`UX-WP-DISCLOSURE1` 文案另卡修訂。2026 advanced／TrackMan extension 另走 `GAME-RECAP-WP-STRENGTH-ADV1` 規劃，不因本卡 Go 自動獲准。未通過 → A 維持 unsupported；不得在本卡轉做條件化 run_dist 或校準窗變體。
- 預估範圍：**M–L，核實後維持 core、拆出 advanced extension**。本卡預期 1 個模型模組＋1 個測試模組＋JSON artifact／研究報告；新增 gamelog running 特徵但不新增 DB writer。先驗與融合仍共同嵌套選型，不拆；官方 2026 advanced snapshot／TrackMan 因資料來源、缺場治理與前瞻驗證是獨立子系統，拆成後續卡，避免本卡爆成 XL。
- 禁止：public API、前端、`winprob.py` 生產路徑、migration、DB 寫入、爬蟲／refresh、LIVE-GAME-BACKEND1 或其他 session 的 lease 資源。

## 附錄 A：條件化 run_dist 樣本量可行性（唯讀估算）

2026-07-26 於本機 DB 唯讀估算：A 例行 2018–2025 共 2,335 場，沿用 `winprob_val.iter_half_pa_records()` 得 171,663 筆狀態紀錄；以賽前 `prior_winpct_diff` 作戰力代理，依各訓練窗 game-level quantile 切 3／5 箱（分位切點同值一律以 `bisect_right` 歸右箱），再以既有 `MIN_STATE_N=30` 判定 48 states × bins。`可用觀測` 指落在 n≥30 格內的紀錄比例。

| 訓練窗 | 分箱 | 可用格／總格 | 所有分箱皆可用的 state／48 | 可用觀測 |
|---|---:|---:|---:|---:|
| 2018–2022 | 3 | 140/144 | 46/48 | 99.90% |
| 2018–2022 | 5 | 225/240 | 44/48 | 99.70% |
| 2018–2023 | 3 | 143/144 | 47/48 | 99.98% |
| 2018–2023 | 5 | 228/240 | 45/48 | 99.78% |
| 2018–2024 | 3 | 144/144 | 48/48 | 100.00% |
| 2018–2024 | 5 | 234/240 | 46/48 | 99.90% |
| 2018–2025 | 3 | 144/144 | 48/48 | 100.00% |
| 2018–2025 | 5 | 238/240 | 47/48 | 99.97% |

結論：最早窗並非全格充分（3 箱缺 4 格、5 箱缺 15 格），但 99.70% 以上觀測落在可用格，若設 pooled fallback 則具工程可行性，**不能僅以樣本量淘汰**。然而 `n=30` 仍要估 7 類剩餘得分機率，且硬分箱犧牲連續性與資料效率。故本卡選 logit 融合；此表只回答 feasibility，不得當作條件化方案已通過校準或可事後切換的證據。

## Log

- 2026-07-26 依 ruan6047 指示整理開卡（CAL1 No-Go 結案後續；需求方確認走 VAL1 §7 路徑 2）。卡面初稿由執行過 VAL1/CAL1 的 Fable 5 依兩份已跨家族 APPROVE 報告擬定；Coordinator register 併同 commit。
- 2026-07-26 GPT-5.6@Codex（L4）完成規劃並凍結卡面，待需求方核可：候選定案為 **L2 正則化賽前先驗＋logit opening-anchor 融合**；條件化 run_dist 經 DB 唯讀估算在 3/5 分箱下需少量 pooled fallback，故非樣本淘汰，而因資料效率、硬分箱不連續與侵入性較高未選。預註冊 2018..Y−2→Y−1 inner selection、2018..Y−1→Y validation（Y=2023..2026）、固定六特徵、lambda/gamma 網格與 tie-break；明確排除同季完整 starter 欄位的歷史洩漏。WP-VAL1 v2 門檻未放寬，另將逐局帶絕對偏差＋相對 base 惡化納入硬性判定；M–L 維持、不拆卡。spec 基線核對父卡 `INIT-GAME-RECAP` 仍為 v1.3。規劃 gate 已完成但 lifecycle 仍為 💡需求，核可前不可 claim。
- 2026-07-26 需求方要求依資料價值拆為 `≤2017`／`2018–2025`／`≥2026`，並優先當季資料。規劃修訂後再次凍結：`≤2017` 因無逐場母體，只供 2018 冷啟動 rate prior；2018–2025 為可完整回測的 core；2026 為報告首要鎖箱 holdout，當季 running gamelog 可進 core，但僅 2026 的官方 advanced／TrackMan 只作 shadow，另拆 `GAME-RECAP-WP-STRENGTH-ADV1`。core 特徵由六項修訂為八項，改以逐場可重建的 starter K−BB%、好球率、FIP proxy 與 bullpen K−BB% 取代前一年 ERA／availability，新增共同 `kappa ∈ {50,100,200}` 收縮選型；DB 唯讀核對 pitching gamelog 2018–2026 完成場 coverage 100%、先發有效分母 5,098/5,102。紅線與 v2 門檻不放寬，scope 維持 M–L；lifecycle 仍為 💡需求，待需求方核可。
- 2026-07-26 依需求方要求補作國內外網站／論文研究，形成 [`GAME-RECAP-WP-STRENGTH1_RESEARCH`](../research/GAME-RECAP-WP-STRENGTH1_RESEARCH.md) 附錄。研究支持「平均隊伍局勢 WE 與 matchup-specific 賽前 prior 分層後融合」、相對差值特徵、將 starter 納入先驗的架構類比與季中 rate 收縮原理；沒有足以改走第三案的證據。為避免過度宣稱，將 `starter_strike_rate_adv` 精確更名為 `starter_recorded_strike_share_adv`（非官方 zone%），收縮公式改稱部分池化近似，並凍結 `team-only`／`team+starter`／`full` 三層消融作診斷；full 仍是唯一驗收候選。MLB Elo／休息／先發常數不得搬用，2026 advanced 仍只作 shadow。紅線、窗口與 spec v1.3 均未放寬或改動；卡面再次凍結，待需求方核可。
- 2026-07-26 需求方啟用 Tavily 後要求重查以避免無效數據幻覺。逐條抽取原文後修正證據等級：Baseball-Reference／FanGraphs 平均隊伍 WE、Yang & Swartz covariates、Brown shrinkage 原理、CPBL 第 30 年研究摘要與官方進階指標定義均可核對；FiveThirtyEight 舊方法頁已轉址，僅官方 GitHub 封存資料能證明 preseason rating＋starter adjustment，故休息／旅行常數與效果量全部降為不作證據。另明確指出 Brown 未直接驗證投手 rate、CPBL 研究不可外推 pooled 跨季係數、公開 UI 只見 2026 不等於聯盟底層絕無歷史資料、Markov 論文也未證明條件化 run_dist 較差。主設計、窗口、紅線、M–L 與 spec v1.3 不變；卡面再次凍結，待需求方核可。
- 2026-07-26 需求方要求將凍結設計交其他 AI 做矛盾審核；新增 [`GAME-RECAP-WP-STRENGTH1_PLAN_REVIEW_REQUEST`](../research/GAME-RECAP-WP-STRENGTH1_PLAN_REVIEW_REQUEST.md)。文件固定 `APPROVE`／`REQUEST_CHANGES` 裁決、P0–P3 finding 格式與 C1–C20 必答檢查，特別要求核對 opening anchor、`w(t)`／延長賽、fractional tie label、跨 fold 季別重用、2018 cold-start prior、八特徵分母／方向、bullpen role、2026 鎖箱、full-only 消融、文獻外推、M–L 估算與 harness 復用。此文件不寫 lifecycle event、不代表規劃或實作已獲 APPROVE；卡面仍為 💡需求。
- 2026-07-26 Plan Gate review by Google Gemini 3.6 Flash（Google Gemini family，≠ GPT/Codex 規劃者；需求方轉錄）→ [`APPROVE`](../research/GAME-RECAP-WP-STRENGTH1_PLAN_REVIEW.md)：spec v1.3 PASS、C1–C20 全 PASS、P0–P2=0。唯一 F-01 P3 指出 scikit-learn 類分類器不接受 `y=0.5` continuous target；卡面已加入等價加權拆樣本／自訂凸 loss 與 game-weighting 合約測試，不改統計設計、窗口或門檻。另由規劃者唯讀核對 `migrations/001_init.sql`，確認 C7 所述 `pitching_seasons` 具 `ip/bf/np/hr/bb/ibb/hbp/so`。本 APPROVE 僅完成規劃矛盾查核，不取代 implementation T4 review；lifecycle 仍為 💡需求，待 ruan6047 sign-off 後由 Coordinator 轉 📥Backlog。
- 2026-07-26 ruan6047 需求方於會話明確回覆「核可」→ 最終規劃 sign-off 完成。卡面、研究附錄與跨家族 Plan Review 共同構成凍結基線；本規劃者不寫 lifecycle event，current-state 仍為 💡需求且不可 claim，待 Coordinator 依 canonical 流程落 event 後轉 📥Backlog。
- 2026-07-26 STATUS-003 落帳（GPT-5.6@Codex 依 ruan6047 明確授權代 Coordinator 寫 lifecycle）→ 📥Backlog 開放認領；卡面 current-state 由 Fable 5 同步對齊（本筆僅文字對齊，無狀態變更）。
- 2026-07-26 Claude Opus 5 依需求方派工 claim（CLAIM-004）並交付（HANDOFF-005，source `13e5f23`）→ **A scope unsupported（No-Go）**。硬門檻 4c「融合後 Brier 不得劣於同代未融合 base」在 2023（+0.000444）、2025（+0.001479）失敗；其餘門檻全通過（四季 coverage 1.0000、皆勝主場常數基準、池化十分位與逐局帶無顯著超界、局帶最大惡化 +0.72pt）。根因非融合式或實作，而是八項凍結賽前特徵在時間外幾乎不含增量資訊：p0 相對 leakage-safe 主場常數平均僅 −0.0009、四季兩季為負，池化融合前後 Brier 差 +0.000095（99% game-cluster CI 含 0）。新增 `--diagnostics` 四路對照證明管線可用（同窗 in-sample 一致優於常數 0.006–0.008），並實測佐證紅線 2：改用被禁用的同季彙總先發欄後四季一致出現 0.010–0.017 假性改善＝前視洩漏指紋。opening anchor 達成設計目的（逐局帶未惡化，未重蹈 CAL1 覆轍），但報告 §6.3 明文標註「池化顯著分箱 [7,8]→[] 是 CI 寬度擦邊、S 型偏差量級幾乎未變」以防誤讀。凍結紅線與門檻全程未放寬；分支與 worktree 保留供查核者進駐，執行者不自查不自 merge。
