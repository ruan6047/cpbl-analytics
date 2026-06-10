-- 本季投手成績（來源：cpbl.com.tw POST /stats/recordallaction, Position=02）
-- 解決兩件事：(1) 先發投手 ID→名字（opendata 到 2024，缺新人）；(2) 本季 ERA 及進階指標。
-- 進階欄位（whip/k9/fip/era_plus）讓賽果預測的可選變因變多。

CREATE TABLE IF NOT EXISTS cpbl.pitching_current (
    year       INT  NOT NULL,
    player_id  TEXT NOT NULL,
    name       TEXT,
    team_code  TEXT,
    era        NUMERIC(6,2),
    ip         NUMERIC(6,1),
    g          INT,
    gs         INT,
    w          INT,
    l          INT,
    whip       NUMERIC(5,2),
    k9         NUMERIC(5,2),
    fip        NUMERIC(6,2),
    era_plus   NUMERIC(7,2),
    PRIMARY KEY (year, player_id)
);

CREATE INDEX IF NOT EXISTS idx_pitching_current_player ON cpbl.pitching_current (player_id);
