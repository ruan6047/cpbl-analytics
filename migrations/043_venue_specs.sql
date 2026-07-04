-- 球場規格 enrich（來源＝官網 /field/cont 各球場頁「場內資訊」，cpbl-scrape-field 一次性爬 + 手動刷新）。
-- 距離單位為官方頁面原始數字（實測大巨蛋 335/335/400 為呎）；park factor 特徵由 API/features 端換算。
ALTER TABLE cpbl.venue_dim ADD COLUMN IF NOT EXISTS address        text;
ALTER TABLE cpbl.venue_dim ADD COLUMN IF NOT EXISTS phone          text;
ALTER TABLE cpbl.venue_dim ADD COLUMN IF NOT EXISTS infield_seats  integer;
ALTER TABLE cpbl.venue_dim ADD COLUMN IF NOT EXISTS outfield_seats integer;
ALTER TABLE cpbl.venue_dim ADD COLUMN IF NOT EXISTS lf_dist        integer;   -- 左外野（呎）
ALTER TABLE cpbl.venue_dim ADD COLUMN IF NOT EXISTS cf_dist        integer;   -- 中外野（呎）
ALTER TABLE cpbl.venue_dim ADD COLUMN IF NOT EXISTS rf_dist        integer;   -- 右外野（呎）
ALTER TABLE cpbl.venue_dim ADD COLUMN IF NOT EXISTS big_screen     boolean;
ALTER TABLE cpbl.venue_dim ADD COLUMN IF NOT EXISTS field_sid      text;      -- 官網 /field/cont?SId=
