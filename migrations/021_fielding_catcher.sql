-- 守備補欄：官網守備表（teamscore position=03）其實含 12 欄，原爬蟲只取 7 欄，
-- 丟棄了三殺/捕逸/盜壘阻殺(阻殺)/被盜成功。補進這些（捕手關鍵守備指標）。
ALTER TABLE cpbl.fielding_current ADD COLUMN IF NOT EXISTS tp  int;  -- 三殺 triple play
ALTER TABLE cpbl.fielding_current ADD COLUMN IF NOT EXISTS pb  int;  -- 捕逸 passed ball
ALTER TABLE cpbl.fielding_current ADD COLUMN IF NOT EXISTS cs  int;  -- 盜壘阻殺 caught stealing
ALTER TABLE cpbl.fielding_current ADD COLUMN IF NOT EXISTS sba int;  -- 被盜成功 stolen bases allowed
