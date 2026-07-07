-- 048: 打者/投手 RE24（Phase B）
-- livelog 逐打席轉移 × run_expectancy 矩陣。打席中途跑壘異動（盜壘/暴投）歸跑者不歸打者；
-- 被跑壘出局截斷的打席碎片（action_name 空）不歸打者。詳 models/sabr.py build_re24。

CREATE TABLE IF NOT EXISTS cpbl.batter_re24 (
    year        integer NOT NULL,
    kind_code   text    NOT NULL DEFAULT 'A',
    player_id   text    NOT NULL,
    pa          integer NOT NULL,
    re24        numeric(7,2) NOT NULL,
    PRIMARY KEY (year, kind_code, player_id)
);

CREATE TABLE IF NOT EXISTS cpbl.pitcher_re24 (
    year        integer NOT NULL,
    kind_code   text    NOT NULL DEFAULT 'A',
    player_id   text    NOT NULL,
    bf          integer NOT NULL,
    re24        numeric(7,2) NOT NULL,  -- 打者觀點值：負=壓制（投手好）
    PRIMARY KEY (year, kind_code, player_id)
);
