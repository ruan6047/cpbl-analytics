-- 因雨延賽/保留比賽標記。getgamedatas 每個 sno 有多筆排程 entry(延期/保留歷程)：
-- GameResult 1=延賽(0-0 未開打改期) / 2=保留比賽(已開賽中止,擇期續賽)。爬蟲按 sno
-- 聚合：主記錄取完成場、delay_kind/orig_date 由歷程推導。供賽況頁備註。冪等。
ALTER TABLE cpbl.games ADD COLUMN IF NOT EXISTS delay_kind text;   -- '延賽' | '保留' | NULL
ALTER TABLE cpbl.games ADD COLUMN IF NOT EXISTS orig_date  date;   -- 延賽原定日 / 保留開賽日
