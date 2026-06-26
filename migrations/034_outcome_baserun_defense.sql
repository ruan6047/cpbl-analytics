-- 賽事預測：當季到此「壘間/守備」細項（淨盜壘/暴投/失誤，每場；僅 2018+ 有逐打席 → 更早 NULL）。
ALTER TABLE cpbl.game_features ADD COLUMN IF NOT EXISTS team_sb_now_diff  double precision;
ALTER TABLE cpbl.game_features ADD COLUMN IF NOT EXISTS team_wp_now_diff  double precision;
ALTER TABLE cpbl.game_features ADD COLUMN IF NOT EXISTS team_err_now_diff double precision;
