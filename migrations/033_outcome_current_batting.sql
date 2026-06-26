-- 賽事預測新增「當季到此」團隊打擊細項（僅 2018+ 有逐打席 → 更早年份為 NULL，
-- train_model 對選定特徵丟 NULL 列自動限縮訓練年限）。
ALTER TABLE cpbl.game_features ADD COLUMN IF NOT EXISTS team_ops_now_diff double precision;
ALTER TABLE cpbl.game_features ADD COLUMN IF NOT EXISTS team_avg_now_diff double precision;
