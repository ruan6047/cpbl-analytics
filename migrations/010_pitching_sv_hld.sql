-- 投手補救援成功 / 中繼成功（teamscore 本就有）
ALTER TABLE cpbl.pitching_current ADD COLUMN IF NOT EXISTS sv  INT;  -- 救援成功
ALTER TABLE cpbl.pitching_current ADD COLUMN IF NOT EXISTS hld INT;  -- 中繼成功
