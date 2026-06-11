-- 打者補上計數型數據（teamscore 本來就有,之前只存了 rate stat）
ALTER TABLE cpbl.batting_current ADD COLUMN IF NOT EXISTS g    INT;  -- 出賽
ALTER TABLE cpbl.batting_current ADD COLUMN IF NOT EXISTS ab   INT;  -- 打數
ALTER TABLE cpbl.batting_current ADD COLUMN IF NOT EXISTS r    INT;  -- 得分
ALTER TABLE cpbl.batting_current ADD COLUMN IF NOT EXISTS h    INT;  -- 安打
ALTER TABLE cpbl.batting_current ADD COLUMN IF NOT EXISTS b2   INT;  -- 二安
ALTER TABLE cpbl.batting_current ADD COLUMN IF NOT EXISTS b3   INT;  -- 三安
ALTER TABLE cpbl.batting_current ADD COLUMN IF NOT EXISTS rbi  INT;  -- 打點
ALTER TABLE cpbl.batting_current ADD COLUMN IF NOT EXISTS bb   INT;  -- 四壞
ALTER TABLE cpbl.batting_current ADD COLUMN IF NOT EXISTS so   INT;  -- 三振
ALTER TABLE cpbl.batting_current ADD COLUMN IF NOT EXISTS sb   INT;  -- 盜壘
ALTER TABLE cpbl.batting_current ADD COLUMN IF NOT EXISTS cs   INT;  -- 盜壘刺
