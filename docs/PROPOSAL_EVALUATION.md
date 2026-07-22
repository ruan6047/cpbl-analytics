# 中職進階數據分析平台 (CPBL Analytics)
## 未來功能提案可行性評估報告 (Proposal Feasibility & Evaluation Report)

本評估報告針對提升 **CPBL Analytics** 分析深度與用戶體驗的四項先進功能進行技術與可行性評估。各項提案均旨在橋接目前中職數據與大聯盟級別（Statcast/Savant, Pitcher List）的數據洞察力。

---

## 📋 提案總覽與評估矩陣 (Executive Summary)

| 提案名稱 | 數據成熟度 | 開發時數 (估) | 視覺衝擊力 | 數據洞察力 | 綜合推薦指數 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **A. 百分位數氣泡卡** | 🟢 100% 已備 | 12 小時 (低) | 🚀 極高 | 📈 中高 | **9.5 / 10** (優先推薦) |
| **B. 2D 放球與位移圖** | 🟢 100% 已備 | 16 小時 (低) | 🚀 極高 | 📈 高 | **9.0 / 10** (優先推薦) |
| **C. 中職 Stuff+ 指數** | 🟡 70% 需訓練 | 40+ 小時 (高) | 📊 中 | 🧠 極高 | **7.5 / 10** (核心研發) |
| **D. H2H 對戰模擬器 v2** | 🟡 60% 需建模 | 60+ 小時 (高) | 📊 中高 | 🧠 極高 | **6.5 / 10** (中長期計畫) |

---

## 🔍 各項提案可行性深度評估

### 提案 A：中職選手百分位數氣泡卡 (Percentile Player Cards)
> **目標**：仿照 Baseball Savant，在選手個人頁頂部以一排紅（強）到藍（弱）的百分位數氣泡（0–99 PR 值）展示多維度特徵，實現 5 秒判讀球員相對實力。

*   **1. 數據源與需求**：
    *   **打者指標**：`wrc_plus`、`whiff_rate`（揮空率）、`bb_rate`（保送率）、`k_rate`（三振率）、`gb_rate`（滾球率）、`avg_exit_velo`（平均擊球速度，若有 TrackMan）、`barrel_rate`（擊球桶心率）。
    *   **投手指標**：`fip`、`whiff_rate`、`k_rate`、`bb_rate`、`zone_rate`（好球帶率）、`chase_rate`（追打壞球率）。
*   **2. 後端實現 (FastAPI)**：
    *   使用 SQL 視窗函數 `PERCENT_RANK() OVER (PARTITION BY season ORDER BY metric)` 計算每個選手相較當季所有合格（或滿足最低 PA/BF 門檻）選手的 PR 值。
    *   快取機制：此數據按天或每週更新即可，應利用 Redis / FastAPI Cache 進行快取，避免每次載入選手頁都全量計算。
*   **3. 前端 UI/UX 設計 (Next.js)**：
    *   設計客製化氣泡組件 `PercentileBubble`，內部封裝 `PR_GRADIENT` 色值（100 = 鮮紅 `#ff2a2a`、50 = 灰 `#e2e8f0`、0 = 鮮藍 `#3b82f6`）。
    *   支援暗色模式：調整背景光暈，確保高對比度且文字易讀。
*   **4. 風險與痛點**：
    *   *合格樣本數門檻*：若不設定最低打席/面對打席門檻，會導致樣本極少的替補選手霸佔 99 PR 或 0 PR。必須定義 `min_pa = season_games * 3.1` (打者) 與 `min_bf = season_games * 1.0` (投手)。
*   **5. ROI 評估**：**極高**。開發時間極短，但能立即帶來大聯盟級的官網視覺震撼度。

---

### 提案 B：TrackMan 放球點與球路軌跡 2D 分布圖 (Release & Movement Maps)
> **目標**：在球員頁呈現投手的放球點分布（X: `rel_side`, Y: `rel_height`），用以分析出手重複性 (Consistency) 與球路隱蔽性 (Tunnelling)。

*   **1. 數據源與需求**：
    *   `pitch_tracking` 庫中的物理測量欄位：`rel_side_cm`、`rel_height_cm`、`extension_m`、`pitch_type_pred_v2`（細分球種）。
*   **2. 後端實現 (FastAPI)**：
    *   新增端點 `/players/{id}/release-point`，回傳當季該投手所有投球的出手點坐標與球種。
    *   為了防範巨量資料傳輸，前端僅請求當季的隨機抽樣 500 顆球，或直接由後端回傳各球種的「95% 信心區間橢圓 (Confidence Ellipse)」坐標與中心點，而非全量散點。
*   **3. 前端 UI/UX 設計 (Next.js)**：
    *   使用 Recharts 的 `ScatterChart` 或是手繪 SVG Canvas 繪製散點。
    *   背景輔助線：標註「聯盟平均放球框」與投手本人的「放球點質心 (Centroid)」。
    *   互動性：當鼠標 hover 特定球種分類時，高亮該球種的所有放球點，並隱藏其他球種。
*   **4. 風險與痛點**：
    *   *左投鏡像*：`rel_side` 會因為左/右投而正負反轉（左投出手點在三壘側，`rel_side` 應為負值；右投在一壘側，為正值）。繪製時需統一以投手視角或打者視角進行 X 軸鏡像，並清楚標示標記。
*   **5. ROI 評估**：**極高**。現有 TrackMan 數據庫 100% 覆蓋放球數據，是尚未被充分利用的黃金資料，視覺衝擊力極強。

---

### 提案 C：中職版球路品質指數 (CPBL Stuff+ / Pitch Quality Score)
> **目標**：不看被擊球結果，純粹根據球速、轉速、位移、放球點等物理特徵，評估投手單一球路的威脅性。

*   **1. 數據源與需求**：
    *   `rel_speed` (球速)、`ivb_cm` (垂直位移)、`hb_cm` (水平位移)、`spin_rate` (轉速)、`extension` (延伸量)、`throws` (投手左右手)。
    *   標籤（Label）：揮空 (Whiff)、被擊球初速與角度（預估 Run Value）。
*   **2. 後端實現 (Python Machine Learning)**：
    *   **第一步：計算 Expected Run Value (xRV)**。利用中職歷史數據（2020-2026），估算每個 pitch count 下，好/壞球、揮空、界外、各種擊球結果的期望分值變動。
    *   **第二步：模型訓練**。針對每一種主要球路（Fastball, Slider, Curveball, Changeup），以物理測量值為 X，xRV 為 Y，訓練隨機森林或 LightGBM。
    *   **第三步：標準化 (Stuff+)**。將預測的 xRV 標準化（聯盟平均 = 100，標準差 = 10）。110 代表比聯盟平均好一個標準差（具備強力的壓制力）。
*   **3. 前端 UI/UX 設計 (Next.js)**：
    *   整合至 [players/[id]/movement](file:///Users/ruanruan/Dev/cpbl-analytics/web/src/app/players/[id]/page.tsx) 下的球路成績單。
    *   以極具辨識度的評分卡（如 Stuff+ 118 🔥 / Location+ 98 / Pitch+ 112）形式陳列於投手武器庫表中。
*   **4. 風險與痛點**：
    *   *樣本量限制*：中職球隊與投手基數較小，稀有球路（如 Sweeper、Sinker）在單一投手的樣本可能不足，模型容易過擬合。需要引入轉移學習（利用大聯盟數據預訓練，再以中職數據進行微調）。
*   **5. ROI 評估**：**中高**。雖然大腦分析價值極高，但機器學習模型的開發、調校與可解釋性門檻較高，需要獨立的機器學習研發週期。

---

### 提案 D：互動式 H2H 對戰模擬器 (Matchup Simulator v2)
> **目標**：讓用戶在網頁上自主選擇「投手 A」與「打者 B」，模擬在特定球數、壘包狀況下，打席的對戰勝率與機率分布。

*   **1. 數據源與需求**：
    *   投手的 Pitch Mix（球種比例）、各球種的揮空率、好球率、邊角控球能力。
    *   打者對各球路（速球系、橫向變化球、縱向變化球）的揮空率、追打壞球率、擊球初速分布。
*   **2. 後端實現 (FastAPI / PyTorch)**：
    *   使用蒙特卡羅模擬 (Monte Carlo Simulation) 或馬可夫鏈 (Markov Chain)，從 0-0 開始模擬打席。
    *   在每一個球數下，投手隨機抽樣其配球概率，打者則隨機抽樣其對該球種的決策概率（Swing/Take）與擊球結果機率。
    *   重複模擬 10,000 次，輸出該對戰的期望三振率、保送率、安打率及 wOBA。
*   **3. 前端 UI/UX 設計 (Next.js)**：
    *   雙欄式選手選取器，左側為投手，右側為打者。
    *   中央呈現動畫效果（如棒球飛入、虛擬好球帶）。
    *   以圓餅圖或柱狀圖實時更新「模擬對戰結果百分比」。
*   **4. 風險與痛點**：
    *   *對戰樣本稀疏性 (Sparsity)*：若投手 A 與打者 B 歷史上從未對決過，完全依賴兩者對聯盟平均的表現進行相乘，容易忽略特定的「手性相剋`」或「球路盲點」。
    *   *計算效能*：若每次請求都在線進行 10,000 次蒙特卡羅模擬，API 回應時間可能超過 2 秒。必須改為預先計算（離線跑好所有投打對決矩陣存入 Redis）或使用輕量級的常數公式推估。
*   **5. ROI 評估**：**中**。非常適合做為行銷、球迷互動或社群分享的爆點功能，但開發資源耗費極大。

---

## 📅 開發路線圖建議 (Development Roadmap)

考量到開發成本與視覺效果，建議採取**「漸進式交付」**策略：

### Phase 1：視覺特效與現成數據利用 (近期 - 1〜2 週)
- **優先實作：提案 A (百分位數氣泡卡) + 提案 B (放球點分布圖)**。
- 原因：這兩項提案的底層數據已經 100% 存在於目前的 PostgreSQL 資料庫中，不需要進行複雜的 ML 模型訓練。前端只需擴充 SVG/Recharts 和 CSS 特效即可上線，能快速在球迷社群中引爆話題。

### Phase 2：深度機器學習研發 (中期 - 1 個月)
- **實作：提案 C (中職 Stuff+ 指數)**。
- 利用 Python 獨立建立 ML 管線，並進行交叉驗證與特徵工程，產出投手的球路物理評分，並於後端增加 `stuff_plus` 欄位。

### Phase 3：球迷高互動模組 (遠期 - 下一季度)
- **實作：提案 D (對戰模擬器)**。
- 整合 Phase 1-2 的所有累積成果，打造旗艦級的互動預測工具。

---

## 🔎 附錄：複評勘誤與裁定（Fable-5@Claude Code，2026-07-12，ruan6047 核可）

| 案 | 裁定 | 勘誤/修正 |
|---|---|---|
| **A 氣泡卡** | ❌ **否決**（07-12 原型實測後 ruan6047 裁定：柱狀圖=數值+PR+長度+定義四合一，氣泡只剩 PR 圓圈＝資訊密度下降）| 非新建——既有三種 PR 呈現（能力值卡雷達/PercentileBar/官方進階 PR 區）之**整併+氣泡化**，工時低於報告估；hardcode 色（#ff2a2a/#3b82f6）違反 tokens 紅線 → 用既有 `prColor`/`PR_GRADIENT`；Redis 快取過度工程（本專案無 Redis，SQL window/物化足夠） |
| **B 出手點** | ✅ 併入 UX-7 | 位移半案（HB×IVB）07-12 已上線，僅剩出手點；欄名為 `rel_side`/`rel_height`（單位 m，非 `*_cm`）；信心橢圓改「出手一致性」數值（質心分散度）更省更可讀 |
| **C Stuff+** | 📥 ML-PT3，排 2026 季末 | **資料前提錯誤**：pitch_tracking 僅 2026 起（非 2020–2026），單季 ~69k 球樣本風險高一級 → 等全季收完再訓練；MLB 預訓練需逐球資料（非 leaderboard 聚合）；補紅線：**須贏過「whiff% 排名」baseline** 才採用；可重用 ML-PT2 特徵對齊管線與 sabr RE 矩陣 |
| **D 模擬器 v2** | 📥 ML-SIM1 簡易勝負＋單一打席；ML-SIM2 全場遠期 | ML-SIM1 取代 UX-10O，分兩模式：①固定、按語意群去重複訊號的簡易賽前勝負預測，取消自由勾選與手調權重；②單一打席互斥結果機率→情境狀態轉移→復用既有 `wp_state()` 加權整場勝率。完整陣容／牛棚／後續全打席個人化列 ML-SIM2，**遠期目標、暫時不做**。輸出須附基準、校準與不確定性，禁止用多個同義代理或蒙特卡羅包裝不可靠輸入 |

### 2026-07-22 官方資料源複查增補

- **B 出手點／軌跡**：`pitch_tracking` 並非 100% 場次覆蓋；只有設備／來源實際回傳 TrackMan
  的球可用。新確認的完整 X/Y/Z 九係數可支援 3D trajectory 與 tunneling 候選研究，但須先由
  `INGEST-DEEP-TRACKMAN1` 保存原始值，不能從 round 後的 acceleration 反推。
- **C Stuff+**：官方 `leaderboards/summary` 可提供聯盟年度球速／轉速與擊球品質 baseline，完整
  trajectory 可擴充候選特徵；這不改變「只有 2026」「無 active spin」「須勝過 whiff% baseline」三條紅線。
- **D 模擬器**：官方 player／league `fastball|breakingball` 可改善 coarse pitch-mix prior 與冷啟動，
  但只有兩類，不能冒充 `pitch_type_pred_v2` 細分球種，也不解除校準／全場陣容與牛棚限制。
- 完整證據與依賴矩陣見 [`research/OFFICIAL_DATA_GAP1_RESULTS.md`](research/OFFICIAL_DATA_GAP1_RESULTS.md)。
