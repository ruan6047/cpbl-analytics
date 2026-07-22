# INGEST-DEEP-TRACKMAN1 數據管線優化：入庫深層 TrackMan 物理特徵〔T4；🔴資料正確性／schema 紅線〕

> **狀態 📥Backlog**：已由 CPBL 深層 API 結構研究正式註冊。待指派認領並進入 Plan。

- 需求：ruan6047　規劃：待指派　分支：—（認領後建立）
- 執行：待指派　查核：待指派
- worktree：—（認領後建立）
- Initiative：`INIT-OFFICIAL-DATA1`　spec 基線：[`../research/OFFICIAL_DATA_GAP1_RESULTS.md`](../research/OFFICIAL_DATA_GAP1_RESULTS.md) §3.3
- DB：`db_scope: schema`；`migration_phase=expand`（修改 `cpbl.pitch_tracking`）　部署：是　環境：production

## 背景

我們在對 `stats.cpbl.com.tw` 進階數據 API 的 JSON payload 研究中，發現其實體數據結構包含了多個被現有爬蟲 `cpbl_pitch_tracking.py` 忽略的深層欄位：
1.  **落地方位角 (`Hit.LandingFlat.Bearing`)**：與距離（`Distance`）結合可重建極座標，為二維落地點 (Spray Chart) 與 OAA 守備範圍特徵提供物理 Ground Truth。
2.  **落地信心 (`Hit.LandingFlat.Confidence`)**：官方 High／Medium 等品質標記；沒有它就無法對落點圖與守備模型做資料品質篩選。
3.  **擊球自轉率 (`Hit.Launch.HitSpinRate`)**：評估擊球飛行物理與擊球品質的重要指標。
4.  **投球 3D 多項式擬合參數 (`Pitch.Flight.PolyFit.PitchTrajectory`)**：包含了 X, Y, Z 軸的常數項 ($t^0$)、一次方項 ($t^1$) 與二次方項 ($t^2$) 的多項式係數。這是重構球路 3D 軌跡（3D Trajectory Reconstruction）、分析放球點一致性（Release Consistency）與隧道效應（Pitch Tunneling）的唯一金鑰。

## 目標

- **資料庫擴展**：
  在 `cpbl.pitch_tracking` 表中新增以下欄位：
  *   `hit_landing_bearing` (float) - 落地方位角
  *   `hit_landing_confidence` (text) - 官方落地品質標記
  *   `hit_spin_rate` (float) - 擊球自轉率
  *   `traj_x0, traj_x1, traj_x2` (float) - X軸多項式擬合係數
  *   `traj_y0, traj_y1, traj_y2` (float) - Y軸多項式擬合係數
  *   `traj_z0, traj_z1, traj_z2` (float) - Z軸多項式擬合係數
- **爬蟲解析升級**：
  修改 `cpbl_pitch_tracking.py` 內的 `_record` 與 `_COLS`，將上述欄位從 API payload 中正確抽離並 UPSERT 入庫。
- **歷史數據補正**：
  執行 2026 年（及可能的話 2025 年）歷史逐球數據的重爬與回填，以確保新特徵在歷史數據上的覆蓋率。

## 實作前提

1.  **向下相容性**：
    所有新欄位必須允許 `NULL` 值，以相容無 TrackMan 設備的球場、無擊球（Hit=null）的投球事件以及歷史 opendata 資料。
2.  **無破壞性變更**：
    不改動既有的 `ivb_cm` 與 `hb_cm` 的計算公式，僅做欄位擴充與純寫入。
3.  **原始值不可由衍生值反推**：
    `traj_accel_y/z` 已 round(4)，不能取代官方 `Y[2]`／`Z[2]`；九個係數須原值保存。

## 非目標

- **不重構爬蟲維度**：本卡不涉及將「投手維度」重構為「單場維度」（該工作由 `INGEST-GAME-TM-REFACTOR1` 處理）。
- **不開發軌跡重建或守備模型**：本卡僅負責將數據入庫，不涉及 ML 模型開發。

## Gate 與驗證

- **Plan Gate**：
  確認 Migration 檔案（如 `06X_add_deep_trackman_fields.sql`）對現有 localhost DB 容器重跑冪等性。
- **驗證方案**：
  *   執行 `pytest` 確保 API 抓取與 DB 寫入單元測試通過。
  *   隨機抽取一場 2026 年已完成場次，核對資料庫中該場投手的擊球轉速、落地方位角、以及 X/Y/Z 九個多項式係數是否與 stats 官方原始 JSON 一致。
- **T3 查核**：
  通過 `ruff check`，且完成 2026 增量回填後，新欄位的非空覆蓋率符合預期（有設備球場且有擊球的事件）。

## Log

- 2026-07-21 由 `ruan6047` 指示正式註冊為 📥Backlog。
- 2026-07-22 官網缺口稽核修訂：補 `LandingFlat.Confidence` 與完整九係數；納入 `INIT-OFFICIAL-DATA1`。
- 2026-07-22 流程勘誤：本卡包含 migration 且影響資料正確性，依 canonical 由 T3 升為 T4；production 回填另開 data-migration 卡或由明確 migrate phase 承接，不可混入 expand。
