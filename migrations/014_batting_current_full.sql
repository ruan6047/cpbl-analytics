-- 補齊 batting_current 至 teamscore 打者頁完整欄位：壘打數/雙殺/犧短/犧飛/故四/死球/
-- 滾飛出局。HBP/IBB/SF/TB 為 wOBA、BABIP 計算所需（原本未抓）。皆 IF NOT EXISTS（冪等）。
ALTER TABLE cpbl.batting_current ADD COLUMN IF NOT EXISTS tb   int;   -- 壘打數
ALTER TABLE cpbl.batting_current ADD COLUMN IF NOT EXISTS gidp int;   -- 雙殺打
ALTER TABLE cpbl.batting_current ADD COLUMN IF NOT EXISTS sh   int;   -- 犧短（犧牲觸擊）
ALTER TABLE cpbl.batting_current ADD COLUMN IF NOT EXISTS sf   int;   -- 犧飛（高飛犧牲打）
ALTER TABLE cpbl.batting_current ADD COLUMN IF NOT EXISTS ibb  int;   -- 故意四壞
ALTER TABLE cpbl.batting_current ADD COLUMN IF NOT EXISTS hbp  int;   -- 死球（觸身球）
ALTER TABLE cpbl.batting_current ADD COLUMN IF NOT EXISTS go   int;   -- 滾地出局
ALTER TABLE cpbl.batting_current ADD COLUMN IF NOT EXISTS ao   int;   -- 高飛出局
ALTER TABLE cpbl.batting_current ADD COLUMN IF NOT EXISTS goao real;  -- 滾飛出局比
