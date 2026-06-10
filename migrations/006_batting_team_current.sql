-- 本季打者進階成績 + 團隊數據（來源：/stats/recordallaction Position=01；/standings/season）

CREATE TABLE IF NOT EXISTS cpbl.batting_current (
    year       INT  NOT NULL,
    player_id  TEXT NOT NULL,
    name       TEXT,
    team_code  TEXT,
    pa         INT,
    avg        NUMERIC(5,3),
    obp        NUMERIC(5,3),
    slg        NUMERIC(5,3),
    ops        NUMERIC(5,3),
    hr         INT,
    ops_plus   NUMERIC(7,2),
    k_pct      NUMERIC(5,2),
    bb_pct     NUMERIC(5,2),
    PRIMARY KEY (year, player_id)
);

CREATE TABLE IF NOT EXISTS cpbl.team_current (
    year       INT  NOT NULL,
    team_code  TEXT NOT NULL,
    name       TEXT,
    -- 團隊打擊
    bat_avg    NUMERIC(5,3),
    bat_obp    NUMERIC(5,3),
    bat_slg    NUMERIC(5,3),
    bat_ops    NUMERIC(5,3),
    bat_hr     INT,
    -- 團隊投手
    pit_era    NUMERIC(6,2),
    pit_whip   NUMERIC(5,2),
    PRIMARY KEY (year, team_code)
);
