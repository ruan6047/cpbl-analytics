-- 逐場比賽（來源：cpbl.com.tw POST /schedule/getgamedatas）
-- 欄位對齊官網真實回傳。Acnt 類欄位即 opendata 的 10 碼 player_id，可 join cpbl.players。
-- 這是賽果預測 [game-outcome prediction] 的 game-level 基礎資料。

CREATE TABLE IF NOT EXISTS cpbl.games (
    year             INT  NOT NULL,
    kind_code        TEXT NOT NULL,            -- A=一軍例行賽…
    game_season_code TEXT NOT NULL,            -- 半季別
    game_sno         INT  NOT NULL,            -- 場次序號
    game_date        DATE,
    present_status   INT,                      -- 賽事狀態（官網 PresentStatus）
    venue            TEXT,

    home_team_code   TEXT,
    home_team_name   TEXT,
    away_team_code   TEXT,
    away_team_name   TEXT,
    home_score       INT,
    away_score       INT,

    home_starter_id  TEXT,                     -- HomePitcherAcnt
    away_starter_id  TEXT,                     -- VisitingPitcherAcnt
    winning_pitcher_id TEXT,
    losing_pitcher_id  TEXT,
    closer_id          TEXT,
    mvp_id             TEXT,

    PRIMARY KEY (year, kind_code, game_season_code, game_sno)
);

CREATE INDEX IF NOT EXISTS idx_games_date ON cpbl.games (game_date);
CREATE INDEX IF NOT EXISTS idx_games_teams ON cpbl.games (home_team_code, away_team_code);
