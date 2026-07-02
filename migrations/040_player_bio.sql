-- 球員 bio 細項(官網 person 頁 inline HTML：身高體重/初出場/學歷/出生地/選秀順位)。
-- 現有 players 已有 name/handedness/bats/throws/birthday/country/full_name。冪等 IF NOT EXISTS。
ALTER TABLE cpbl.players ADD COLUMN IF NOT EXISTS height_cm  int;
ALTER TABLE cpbl.players ADD COLUMN IF NOT EXISTS weight_kg  int;
ALTER TABLE cpbl.players ADD COLUMN IF NOT EXISTS debut      text;   -- 初出場(日期或說明)
ALTER TABLE cpbl.players ADD COLUMN IF NOT EXISTS education  text;   -- 學歷
ALTER TABLE cpbl.players ADD COLUMN IF NOT EXISTS birthplace text;   -- 出生地
ALTER TABLE cpbl.players ADD COLUMN IF NOT EXISTS draft      text;   -- 選秀順位
ALTER TABLE cpbl.players ADD COLUMN IF NOT EXISTS bio_updated_at timestamptz;
