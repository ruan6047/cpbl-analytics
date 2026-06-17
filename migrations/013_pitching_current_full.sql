-- 補齊 pitching_current 至 teamscore 投手頁完整欄位集（原本只取 11 欄，缺自責分等）。
-- 對齊官網：完投/完封/打席/投球數/被安打/被全壘打/四壞/故四/死球/奪三振/暴投/犯規/
-- 失分/自責分/滾地出局/高飛出局/滾飛比。皆 IF NOT EXISTS（migrate 每次全跑須冪等）。
ALTER TABLE cpbl.pitching_current ADD COLUMN IF NOT EXISTS so   int;   -- 奪三振
ALTER TABLE cpbl.pitching_current ADD COLUMN IF NOT EXISTS cg   int;   -- 完投
ALTER TABLE cpbl.pitching_current ADD COLUMN IF NOT EXISTS sho  int;   -- 完封
ALTER TABLE cpbl.pitching_current ADD COLUMN IF NOT EXISTS pa   int;   -- 打席
ALTER TABLE cpbl.pitching_current ADD COLUMN IF NOT EXISTS np   int;   -- 投球數
ALTER TABLE cpbl.pitching_current ADD COLUMN IF NOT EXISTS h    int;   -- 被安打
ALTER TABLE cpbl.pitching_current ADD COLUMN IF NOT EXISTS hr   int;   -- 被全壘打
ALTER TABLE cpbl.pitching_current ADD COLUMN IF NOT EXISTS bb   int;   -- 四壞
ALTER TABLE cpbl.pitching_current ADD COLUMN IF NOT EXISTS ibb  int;   -- 故意四壞
ALTER TABLE cpbl.pitching_current ADD COLUMN IF NOT EXISTS hbp  int;   -- 死球
ALTER TABLE cpbl.pitching_current ADD COLUMN IF NOT EXISTS wp   int;   -- 暴投
ALTER TABLE cpbl.pitching_current ADD COLUMN IF NOT EXISTS bk   int;   -- 投手犯規
ALTER TABLE cpbl.pitching_current ADD COLUMN IF NOT EXISTS r    int;   -- 失分
ALTER TABLE cpbl.pitching_current ADD COLUMN IF NOT EXISTS er   int;   -- 自責分
ALTER TABLE cpbl.pitching_current ADD COLUMN IF NOT EXISTS go   int;   -- 滾地出局
ALTER TABLE cpbl.pitching_current ADD COLUMN IF NOT EXISTS ao   int;   -- 高飛出局
ALTER TABLE cpbl.pitching_current ADD COLUMN IF NOT EXISTS goao real;  -- 滾飛出局比
