-- 賽果預測特徵表（由 cpbl.games 派生，leakage-safe：每場特徵只用該場日期「之前」資訊）
-- home_win: 1=主勝 0=客勝 NULL=未開打或平手。completed=已打完（home_score+away_score>0）。

CREATE TABLE IF NOT EXISTS cpbl.game_features (
    year             INT  NOT NULL,
    kind_code        TEXT NOT NULL,
    game_season_code TEXT NOT NULL,
    game_sno         INT  NOT NULL,
    game_date        DATE,
    season           INT,
    home_team_code   TEXT,
    away_team_code   TEXT,
    home_team_name   TEXT,
    away_team_name   TEXT,
    home_win         INT,
    completed        BOOLEAN NOT NULL DEFAULT false,

    -- 候選特徵（全部為「主隊相對客隊」的差值，正值有利主隊）
    winrate_diff      DOUBLE PRECISION,   -- 季內至今勝率差
    h2h_home          DOUBLE PRECISION,   -- 主隊對該客隊歷史勝率（0.5=無交手史）
    starter_era_diff  DOUBLE PRECISION,   -- 客先發前季ERA - 主先發前季ERA
    home_field        DOUBLE PRECISION,   -- 常數 1.0（主場 bias）
    recent_form_diff  DOUBLE PRECISION,   -- 近10場勝率差
    run_diff_diff     DOUBLE PRECISION,   -- 季內場均得失分差

    PRIMARY KEY (year, kind_code, game_season_code, game_sno)
);

CREATE INDEX IF NOT EXISTS idx_game_features_completed ON cpbl.game_features (completed, season);
CREATE INDEX IF NOT EXISTS idx_game_features_date ON cpbl.game_features (game_date);
