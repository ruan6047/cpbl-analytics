-- 天氣/致勝型態/後台觀眾數：來源＝box getlive 的 CurtGameDetailJson（每日 gamelog 爬取順帶，零額外請求）。
-- weather_desc 為官方全文（含降雨機率/溫度/風向風速/濕度），衍生欄位（溫度、降雨%）由 API 端解析。
-- winning_type 已驗證（2026 A 全季 182 場 100% 對應）：1=客勝 2=主勝 NULL=和局——
-- 非「致勝方式」，與比分冗餘，僅留作和局/勝負交叉驗證，前端不顯示。冪等 IF NOT EXISTS。
ALTER TABLE cpbl.game_detail ADD COLUMN IF NOT EXISTS weather_code text;
ALTER TABLE cpbl.game_detail ADD COLUMN IF NOT EXISTS weather_desc text;
ALTER TABLE cpbl.game_detail ADD COLUMN IF NOT EXISTS winning_type text;
ALTER TABLE cpbl.game_detail ADD COLUMN IF NOT EXISTS attendance_backend int;
