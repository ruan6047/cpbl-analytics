-- Sabermetrics 打底（皆由 livelog 2018+ 推算，cpbl-build-sabr 重建）：
-- 1) fielding_innings：每人每守位守備出局數（首打席守位觀測 + 更換事件時間線重建；
--    投捕以逐事件 pitcher/catcher_acnt 精算）。outs/3 = 守備局數 → RF/9、SBA/9 等分母。
-- 2) run_expectancy：壘位×出局數 → 半局剩餘得分期望 [RE24]。排除未打滿三出局的半局
--    （再見/裁定截斷會低估）。span 供分期（如 '2018-2025'）。
CREATE TABLE IF NOT EXISTS cpbl.fielding_innings (
    year       int  NOT NULL,
    kind_code  text NOT NULL,
    player_id  text NOT NULL,
    pos        text NOT NULL,          -- C/1B/2B/3B/SS/LF/CF/RF/P
    outs       int  NOT NULL,          -- 在位時流逝的守備出局數
    games      int  NOT NULL,          -- 該守位出賽場數
    PRIMARY KEY (year, kind_code, player_id, pos)
);
CREATE INDEX IF NOT EXISTS idx_fielding_innings_player ON cpbl.fielding_innings (player_id);

CREATE TABLE IF NOT EXISTS cpbl.run_expectancy (
    span       text NOT NULL,          -- 統計期間，如 '2018-2025'
    kind_code  text NOT NULL,
    bases      text NOT NULL,          -- '___'/'1__'/'_2_'/'12_'/…（一二三壘有人與否）
    outs       int  NOT NULL,          -- 0/1/2
    re         double precision NOT NULL,
    samples    int  NOT NULL,
    PRIMARY KEY (span, kind_code, bases, outs)
);
