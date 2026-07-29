-- GAME-RECAP-PA1-FIX1：打席中途代打換人後，「誰被記錄」與「誰打完」不是同一人。
--
-- 原 schema 註解假設 hitter_acnt 是「打者（island 內固定）」——該前提在 FIX1 修正
-- island 切分後不成立：一個打席可跨兩位打者（代打接替）。記錄規則 9.15(b)：
--   擊球員於第 2 好球後退出、替代者以三振完成打擊 → 記最初擊球員；
--   替代者以其他結果完成打擊（含四壞球）→ 記該替代擊球員。
-- 兩種語意都有消費端（賽況頁要顯示打完的人、統計要用記錄歸屬），故比照投手側
-- start_pitcher_acnt / end_pitcher_acnt 的既有先例分成兩欄：
--   hitter_acnt      = 依 9.15(b) 的**記錄歸屬**打者
--   end_hitter_acnt  = 實際**完成該打席**的打者（無代打時與 hitter_acnt 相同）
--
-- 冪等（migrate() 每次全跑）。既有列的 end_hitter_acnt 為 NULL，待重建 build 後填入。

ALTER TABLE cpbl.game_plate_appearances
    ADD COLUMN IF NOT EXISTS end_hitter_acnt text;

COMMENT ON COLUMN cpbl.game_plate_appearances.hitter_acnt IS
    '記錄歸屬打者（記錄規則 9.15(b)）；代打中途接替時未必等於完成打席者';
COMMENT ON COLUMN cpbl.game_plate_appearances.end_hitter_acnt IS
    '實際完成該打席的打者；無代打接替時與 hitter_acnt 相同';
