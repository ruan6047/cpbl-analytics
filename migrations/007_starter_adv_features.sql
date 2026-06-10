-- 先發投手進階變因：WHIP、K9（每9局三振）。訓練資料：2023-24 由 opendata 計算，
-- 2025+ 由 pitching_current。未達合格投手以聯盟平均墊檔。

ALTER TABLE cpbl.game_features ADD COLUMN IF NOT EXISTS starter_whip_diff DOUBLE PRECISION;
ALTER TABLE cpbl.game_features ADD COLUMN IF NOT EXISTS starter_k9_diff   DOUBLE PRECISION;
