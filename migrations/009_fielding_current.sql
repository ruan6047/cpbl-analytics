-- 本季球員守備數據（來源：/team/teamscoreaction Position=03，逐隊全名單）
-- 一名球員可守多個位置 → PK 含 pos。

CREATE TABLE IF NOT EXISTS cpbl.fielding_current (
    year       INT  NOT NULL,
    player_id  TEXT NOT NULL,
    name       TEXT,
    team_code  TEXT,
    pos        TEXT NOT NULL,          -- 守備位置（中外野手 / 投手 …）
    g    INT,                          -- 出賽
    tc   INT,                          -- 守備機會
    po   INT,                          -- 刺殺
    a    INT,                          -- 助殺
    e    INT,                          -- 失誤
    dp   INT,                          -- 雙殺
    fpct NUMERIC(5,3),                 -- 守備率
    PRIMARY KEY (year, player_id, pos)
);

CREATE INDEX IF NOT EXISTS idx_fielding_current_pos ON cpbl.fielding_current (year, pos);
