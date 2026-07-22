# ML-FIELD-OAA-VAL1 守備指標升級：利用極座標落點還原 Spray Chart 與外野 OAA〔T4；🔴統計／ML 紅線〕

> **狀態 📥Backlog**：已由 CPBL 深層 API 結構研究正式註冊。待指派認領並進入 Plan。

- 需求：ruan6047　規劃：待指派　分支：—（認領後建立）
- 執行：待指派　查核：待指派（T4 紅線：須跨模型家族或人工複審）
- worktree：—（認領後建立）
- Initiative：`INIT-OFFICIAL-DATA1`　spec 基線：[`../research/OFFICIAL_DATA_GAP1_RESULTS.md`](../research/OFFICIAL_DATA_GAP1_RESULTS.md) §4
- DB：`db_scope: write`（實作階段：建立 OAA 計算與期望出局數表）　部署：否（實作後 ⏸未部署）　環境：—

## 背景

在之前的 `ML-FIELD-TZ1` 守備指標研究中，我們發現由於文字直播 LiveLog 缺乏物理座標，導致內野守備分析陷入致命的「分類洩漏 (Classification Leakage)」NO-GO 瓶頸。
但在本專案深層 API 研究中，我們發現在 API payload 內部已提供擊球落地的極座標參數：落地距離（`Distance`）與落地方位角（`Bearing`）。
這意味著我們可以藉此還原出擊球的二維平面座標 $(X, Y)$。結合 LiveLog 重建出的單場局守備陣容，本任務將驗證是否能實作一套真正的外野 OAA (Outs Above Average) 指標，徹底克服分類洩漏，為 Outcome 模型提供高精度的守備特徵。

## 目標

- **二維落點還原**：
  利用極座標轉換公式，將資料庫中的 `hit_landing_bearing` 與 `hit_landing_distance` 轉換為相對於本壘的二維平面座標 $(X, Y)$，繪製打者擊球分佈圖（Spray Chart）。
- **物理距離計算**：
  結合 `ML-FIELD-LINEUP1` 子卡重建的逐局外野守位與球場物理尺寸（`venue_dim` 中各球場左/中/右外野牆距與角度），計算當外野空中球產生時，負責該守區的守備球員與落點之間的物理移動距離。
- **OAA 指標驗證 (Go/No-Go)**：
  依據物理移動距離與球的滯空時間（`HangTime`），建立期望出局率模型（Logistic Regression / Random Forest）。
  計算球員的「超越期望出局數」(OAA)。
  驗證此指標的統計信度與穩定度，評估是否能通過 **T4 統計紅線** 以作為 Outcome 模型與前端球員頁的正式指標。

## 實作前提

1.  **資料前置**：
    本卡高度依賴 `INGEST-DEEP-TRACKMAN1` 補齊落地距離、方位角與官方落地信心，並依賴 `ML-FIELD-LINEUP1` 所進行的逐局守備陣容重建；`ML-FIELD-OF1` 是物理落點模型失敗時的結果分類 baseline，不是 lineup 前置。
2.  **不包含內野**：
    內野由於沒有雷達落地座標（內野球通常以擊中手套或地面為準，物理運動不同），仍維持既有 NO-GO 判定。

## 非目標

- **不開發前端 UI**：本卡僅負責模型驗證、OAA 指標產出與回測對帳，不涉及前端 UI 展示（UI 由後續 `UX-FIELD-OAA1` 處理）。

## Gate 與驗證

- **Design Gate**：
  本卡為後台統計與 ML 特徵卡，主要進行 OAA 回測穩定度驗證。需向需求方說明模型架構、滯空時間與移動距離的交互作用、以及與傳統守備率 (RF) 的相關性。
- **驗證方案（T4 紅線）**：
  *   **出局守恆**：各守位預期出局數與實際接殺數之差在全聯盟層級應 $\le \pm3\%$。
  *   **2026 feasibility**：先按球場、`LandingFlat.Confidence`、賽制與 availability 報 coverage，只驗證落點物理合理性、守恆與模型可識別性，不產出公開 OAA 排名。
  *   **跨年信度檢定延後**：現有 `pitch_tracking` 只有 2026，未證實 2025 可回填；沒有 2027 holdout 前不得宣稱跨年穩定或通過 OAA Go gate。
  *   **對帳測試**：隨機抽檢 10 個外野空中球案例，人工比對電視轉播畫面中的實際落點與公式還原的 $(X, Y)$ 座標是否物理合理。

## Log

- 2026-07-21 由 `ruan6047` 指示正式註冊為 📥Backlog。
- 2026-07-22 新資料影響修訂：Bearing 提升可行性，但單季限制仍在；跨年信度 gate 延至 2027，先做 2026 feasibility。
