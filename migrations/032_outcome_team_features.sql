-- 賽事預測新增「上季團隊」打擊/投手特徵（全史可算）。leakage-safe（用 season-1 彙總）。
ALTER TABLE cpbl.game_features ADD COLUMN IF NOT EXISTS prior_team_ops_diff  double precision;
ALTER TABLE cpbl.game_features ADD COLUMN IF NOT EXISTS prior_team_slg_diff  double precision;
ALTER TABLE cpbl.game_features ADD COLUMN IF NOT EXISTS prior_team_era_diff  double precision;
ALTER TABLE cpbl.game_features ADD COLUMN IF NOT EXISTS prior_team_whip_diff double precision;
