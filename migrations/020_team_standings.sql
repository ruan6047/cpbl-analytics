-- 官方球隊戰績（standings/seasonaction）。含和局、勝差、淘汰指數、對戰各隊(H2H)、
-- 主客場戰績、連勝連敗、近十場；分上半季(1)/下半季(2)/全年(0)。
CREATE TABLE IF NOT EXISTS cpbl.team_standings (
    year         smallint NOT NULL,
    kind_code    text     NOT NULL,
    season_code  smallint NOT NULL,   -- 0=全年 1=上半季 2=下半季
    team_code    text     NOT NULL,
    team_name    text,
    rank         int,
    g            int,
    w            int,
    t            int,
    l            int,
    win_pct      real,
    gb           real,                 -- 勝差（領先隊為 0）
    elim         text,                 -- 淘汰指數（原樣）
    home_record  text,                 -- 主場 勝-和-敗
    away_record  text,                 -- 客場 勝-和-敗
    streak       text,                 -- 連勝/連敗（如 勝3 / 敗2）
    last10       text,                 -- 近十場 勝-和-敗
    h2h          jsonb,                -- 對戰各隊 {team_code: "勝-和-敗"}
    updated_at   timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (year, kind_code, season_code, team_code)
);
