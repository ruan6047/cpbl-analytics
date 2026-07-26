# GAME-RECAP-WP-STRENGTH1 國內外研究依據與可移植性評估

- 卡：[`GAME-RECAP-WP-STRENGTH1`](../tasks/GAME-RECAP-WP-STRENGTH1.md)（T4 🔴統計；規劃 gate）
- 研究日：2026-07-26；同日以 Tavily advanced search＋query-focused extract 逐條重審
- 範圍：場中勝率 [win probability, WP]、賽前隊伍／先發戰力、季中小樣本收縮、CPBL 可用資料
- 定位：供設計預註冊與排除路線使用；不是系統性文獻回顧，也不以 MLB 係數直接代入 CPBL。Tavily `research pro` 未產出報告，故改以搜尋發現來源、再抽取原文；搜尋摘要本身不作證據

## 1. 結論

研究結果支持本卡採用「**中立局勢 WP + 賽前戰力先驗的 logit 空間融合**」，而不是把戰力硬切箱後重估整套 `run_dist`：

1. Baseball-Reference 與 FanGraphs 的勝率期望 [win expectancy, WE] 都明示其基準描述的是**平均球隊／平均球員**在指定局數、分差與壘包出局狀態下的歷史結果。這類局勢模型適合保留為低變異 base，但不是已納入當場球隊與先發強度的完整預測。
2. Yang & Swartz 的兩階段貝葉斯 MLB 模型明確把隊伍勝率、打擊、先發 ERA 與主場組成相對戰力。FiveThirtyEight 的官方封存資料字典則可核對季前投影、均值回歸、先發 rolling game score 與先發 rating adjustment 欄位。這只支持「賽前 team strength＋starter」的架構方向；舊方法頁目前已轉址，休息、旅行、精確換算常數與效果量無法由現行官方頁直接核對，不作本卡證據。
3. CPBL 實證研究顯示，攻守／戰績指標以「主客兩隊相對差」進入邏輯斯迴歸具有預測力，但有效因子會因球隊而異。故本卡保留低維度差值特徵與 L2 收縮，並以跨季 walk-forward 驗證，不宣稱一組係數可永久跨隊、跨規則沿用。
4. Brown 的季中**打擊率**研究顯示，在該資料與切分下，直接以目前打擊率預測未來通常最差，經驗貝葉斯 [empirical Bayes]／階層方法較佳。將此原理延伸至投手 K−BB／事件率是建模類比，不是該論文直接驗證；它不支持本卡任何固定 pseudo-count，收縮強度仍須只在內部訓練季選定。
5. 官方 CPBL 進階數據已定義 K%、BB%、揮空率、追打率、wOBA、擊球初速與 Barrel 等量測；公開排行榜與球員頁目前年度選項只顯示 2026，官方社群公告也記錄平台於 2026-05-04 上線試營運。這不證明聯盟底層不存在更早資料，但足以證明公開來源無法重建 2018–2025 的 pregame snapshots；故必須 fail closed，只作 2026 shadow。

## 2. 證據矩陣

| 來源 | 類型與母體 | 可採用的發現 | 對本卡的具體影響 |
|---|---|---|---|
| [Baseball-Reference：Win Probability Added 說明](https://www.baseball-reference.com/about/wpa.shtml) | MLB 歷史 WE 方法說明 | WE 以平均主隊在局數、分差、壘包與出局狀態下的結果估計；不是 matchup-specific forecast | 保留 `run_dist`／DP 作中立局勢 base；戰力另由賽前 prior 注入，避免假稱 base 已含球隊實力 |
| [FanGraphs：Win Expectancy](https://library.fangraphs.com/misc/we/) | MLB 歷史 WE 方法說明 | WE 是長期歷史平均，實際打者／投手組合會改變真實勝率 | 支持連續融合，而不是把平均球員 WE 當成完整即時預測 |
| [Yang & Swartz (2004), A Two-Stage Bayesian Model for Predicting Winners in Major League Baseball](https://jds-online.org/journal/JDS/article/1117/info) | 同行評審論文；MLB | 以過去隊伍表現、打擊、先發與主場建立賽前勝率，且允許因素隨時間變化 | 先驗必須含隊伍 running strength 與先發；係數須逐季向前重 fit，不假設永久平穩 |
| [FiveThirtyEight 官方資料 README](https://github.com/fivethirtyeight/data/blob/master/mlb-elo/README.md)／[資料欄位文件](https://fivethirtyeightdata.github.io/fivethirtyeightdata/reference/mlb_elo.html) | MLB rating 封存資料與字典 | 可核對季前 projections、跨季均值回歸、starter rolling game score／adjustment 及含 starter 的 pregame probability；舊[方法頁](https://fivethirtyeight.com/methodology/how-our-mlb-predictions-work/)現已無法抽取原文 | 只支持 team prior＋starter 的架構類比；**不再以該來源替 `rest_days_diff`、旅行、任何常數或改善幅度背書** |
| [Brown (2008), In-season prediction of batting averages](https://arxiv.org/abs/0803.3697) | 同行評審統計研究；MLB 打者／投手的打擊率季中預測 | 在論文切分中，直接用目前平均的 naive predictor 整體最差；不同同質子群的最佳 shrinkage 方法不同 | 支持「小樣本率值應測試收縮」的原理，不直接證明投手 K−BB/FIP、前季 prior 或 `kappa` 網格有效 |
| [Hirotsu & Wright (2003), A Markov Chain Approach to Optimal Pinch Hitting Strategies](https://www.jstage.jst.go.jp/article/jorsj/46/3/46_KJ00000757413/_article/-char/en) | 同行評審論文；非同質球員 Markov chain | 特定兩隊陣容、分差與決策模型需解超過一百萬條聯立方程，可計算 lineup-specific WP 與代打策略 | 證明 player-conditioned state model 可行且可能高維；「本卡不選」仍是結合 CPBL 格數實測後的工程／資料效率裁定，不是該論文的比較結論 |
| [FanGraphs：Pitching Rate Stats](https://library.fangraphs.com/pitching/rate-stats/) | MLB sabermetrics 方法說明 | K%／BB% 以面對打者數為分母，比以投球局數比較投手更直接；仍受球季／聯盟環境影響 | K−BB 使用 PA/BF 分母並逐季標準化；禁止把 MLB 聯盟基準直接當 CPBL prior |
| [以攻守表現與競賽制度預測中華職棒比賽勝負](https://www.airitilibrary.com/Article/Detail/19925530-202012-202102040005-202102040005-41-51) | 國內期刊；CPBL 第 30 年度 | 主客隊攻守、賽程與戰績的相對指標可進邏輯斯模型，但有效指標依球隊而異 | 全部 feature 定義成主隊相對客隊；以 pooled L2 模型控制維度，另揭露逐季漂移，不事後依單隊挑特徵 |
| [CPBL 官方進階數據指標介紹](https://stats.cpbl.com.tw/news/1vrRUWdz8zWv6bWMz0xiazeJUJl8q1c2lxg_uAg122hc)／[官方榜單](https://stats.cpbl.com.tw/rankings)／[官方上線公告](https://www.instagram.com/p/DX6ZjAJHxLh/) | CPBL 官方定義、公開 UI 與公告 | 指標定義可核對；排行榜公開年度目前僅 2026，平台於 2026-05-04 上線試營運 | 只能證明「公開可核對資料不足以做歷史 as-of 回測」，不能反推聯盟底層完全沒有 2025 或更早 TrackMan 資料 |

## 3. Tavily 來源重審：主張狀態

| 主張 | 狀態 | 查核結論 |
|---|---|---|
| 傳統 WE 是平均球隊／平均球員基準 | **已驗證** | Baseball-Reference 與 FanGraphs 原文明示；可支持 neutral base 與 matchup prior 分層 |
| Yang & Swartz 使用隊伍勝率、打擊、先發與主場 | **已驗證但限縮** | 原文採 2001 MLB，重點含季中 division／final-season prediction；沒有驗證 CPBL、場中逐 PA 校準或本卡融合式 |
| FiveThirtyEight 使用 preseason strength 與 starter adjustment | **已驗證** | 官方 GitHub README／欄位字典可核對 |
| FiveThirtyEight 的休息、旅行常數及 starter 帶來約 1pt accuracy 改善 | **不作證據** | 舊官方方法頁現已轉址；只找到二手學位論文轉述，未保留於卡面定案依據 |
| Brown 支持 shrinkage | **已驗證但限縮** | 支持 batting-average 小樣本借力，不支持投手事件率的固定 `kappa`；本卡只能把它當方法原理 |
| K%／BB% 以 BF/PA 為分母、FIP 使用 HR/BB/HBP/K | **定義已驗證；CPBL 增益未驗證** | FanGraphs 是實務方法來源而非本卡母體實證；只能列為預註冊候選，效用須由 inner／holdout 指標決定 |
| CPBL 研究支持相對對戰指標 | **已驗證但不可外推** | 研究是中職 30 年（2019）四隊個別模型；三隊有有效指標、統一模型失敗，不能證明 pooled 2018–2026 係數穩定 |
| 官方 advanced 歷史只有 2026 | **改寫為可證明範圍** | 公開 UI 只暴露 2026且平台 2026 上線；不能宣稱底層資料絕對不存在，只能判定目前不可作歷史 as-of 回測 |
| strength-conditioned Markov／run model 一定較差 | **未被文獻證明** | 文獻只證明可行且高維；不選理由來自本卡 CPBL 格數實測、連續性與維護成本 |

## 4. 對三期資料策略的裁定

| 時期 | 研究上合理的用途 | 不可做的推論 |
|---|---|---|
| **≤2017** | 逐年彙總只作 2018 冷啟動 prior；若缺可對齊分母則退回 fit-window 聯盟率 | 不以 season aggregate 偽造逐場 running features，也不和 2018+ game-level 樣本混成同一驗證母體 |
| **2018–2025** | 以逐場 gamelog 建立賽前可重建的 team／starter／bullpen running rates；作核心訓練與歷史 walk-forward | 不以同季最終 ERA、standing 或賽後修訂快照回填歷史賽前特徵 |
| **≥2026** | 核心 box/gamelog 特徵照常逐場更新；2026 是報告首要鎖箱 holdout。官方進階數據只做 coverage、相關性與方向 shadow | 不因當季資料較有產品意義，就使用 2026 結果選模型或將只有 2026 的 leaderboard 值填到較早比賽 |

這個切法同時滿足「當季最有決策價值」與「當季不能兼任選型資料」：2018–2025 提供可重建與可比較的訓練證據，2026 提供目前產品環境下的時間外證據。

## 5. 研究轉成的預註冊限制

1. **架構**：採 `logit(WP_situ) + w(t) × (logit(p0) − logit(p_base0))`；`p_base0` 必須是同代 base 的開場值。這是把平均隊伍 WE 與 matchup prior 分工，不是事後校準。
2. **特徵語意**：`pitching_gamelog.strike_cnt / pitch_cnt` 僅能稱為「記錄好球占比 [recorded strike share]」，不能稱為官方「好球帶率 [zone rate]」。後者是球位／好球帶定義，需要 TrackMan 或官方欄位。
3. **收縮**：卡面公式是預註冊的部分池化近似，不宣稱已由資料估計完整經驗 Bayes 超參數。`kappa` 候選只可在 Y−1 inner season 選定；不得引用 MLB 所謂 stabilization point 直接鎖死。
4. **相對特徵**：隊伍與投手指標皆定義為主隊相對客隊，並保留 L2 正則化；不依驗證季或個別球隊結果事後做 stepwise selection。
5. **診斷消融 [ablation]**：固定輸出 `team-only`、`team+starter`、`full(+bullpen)` 三組 inner／holdout 指標，用來判讀額外資料來源是否真的提供增量資訊；**full 仍是唯一預註冊驗收候選**，消融結果不得用來在驗證季後切換模型。
6. **外部常數隔離**：FiveThirtyEight 的官方封存資料只支持 team rating＋starter 的架構參考；休息／旅行與數值效果量不作證據。CPBL 的係數、標準化統計、`lambda/kappa/gamma` 全部依卡面訓練窗口估計。
7. **2026 advanced 閘門**：未來 ADV1 至少要有 as-of snapshot／逐球 pregame reconstruction、coverage policy、缺場機制分析及下一個前瞻留出期；未滿足前不得宣稱 advanced 特徵改善 WP。

## 6. 排除與保留風險

- **不重開校準窗變體**：上述來源支持加入賽前結構資訊，沒有推翻 CAL1 對 recency／衰減事後校準的 No-Go。
- **不選條件化 `run_dist`**：不是文獻證明效果較差，而是高維狀態會把有限 CPBL 樣本再切薄，且維護成本高；本卡附錄 A 已另完成實際格數可行性檢查。
- **不把官方 advanced 等同可回測資料**：指標存在不代表歷史 as-of snapshot 存在。2026 的資料豐富度只能提升前瞻研究價值，不能修補 2018–2025 的時間序列缺口。
- **剩餘模型風險**：隊伍 strength 與 starter／bullpen 指標可能共線；L2 可控制方差但不能證明因果。故驗收仍以 Brier、校準分箱與逐局帶硬門檻判斷，不以係數符號或單一 accuracy 放行。

## 7. 規劃決議

研究未形成需要改走第三案的新證據。卡面主設計維持 logit 先驗融合，但作三項收斂：

- 將 `starter_strike_rate_adv` 更名為 `starter_recorded_strike_share_adv`，避免與官方 zone% 混淆。
- 將收縮公式精確描述為「部分池化近似」，不冒稱完整 empirical-Bayes fit。
- 驗證報告新增三層固定消融，只作來源增量診斷，不改變 full model 的預註冊 Go/No-Go 身分。
