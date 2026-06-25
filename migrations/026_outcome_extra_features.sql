-- 賽事預測新增 leakage-safe 特徵（全史 kind A 重建後可用）：
--   rest_days_diff   ：主隊休息天數 − 客隊休息天數（距上一場；季內第一場視為 0 差）。
--                      捕捉輪值/疲勞；先發連投、長假後手感皆反映於此。
--   prior_winpct_diff：主隊上季最終勝率 − 客隊上季最終勝率（無上季資料 → 0.5）。
--                      修正季初冷啟動：開季前幾場 winrate_diff 幾乎全 0.5，缺乏鑑別力。
-- 兩者皆只用「該場日期之前 / 前一季」資訊，無資料洩漏。

ALTER TABLE cpbl.game_features ADD COLUMN IF NOT EXISTS rest_days_diff    DOUBLE PRECISION;
ALTER TABLE cpbl.game_features ADD COLUMN IF NOT EXISTS prior_winpct_diff DOUBLE PRECISION;
