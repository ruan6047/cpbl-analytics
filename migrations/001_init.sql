-- CPBL analytics — Phase 1 schema (season-level, 來源: cpbl-opendata)
-- 設計原則：season-level 為現階段真實來源；之後逐場爬蟲的 game-level 表
-- 再以相同 player_id / team_id 疊加，故此處所有 ID 與 opendata 對齊。

CREATE SCHEMA IF NOT EXISTS cpbl;

-- 球員主檔（players.csv）
CREATE TABLE IF NOT EXISTS cpbl.players (
    id          TEXT PRIMARY KEY,              -- opendata 10 碼 ID
    name        TEXT NOT NULL,
    handedness  TEXT,                          -- 原始字串，如 "右投右打"
    bats        TEXT,                          -- 解析：左打/右打/左右開弓
    throws      TEXT,                          -- 解析：左投/右投
    birthday    DATE,
    country     TEXT,
    full_name   TEXT
);

-- 球隊主檔（由 standings.csv 去重彙整；name/nickname 以最新年度為準）
CREATE TABLE IF NOT EXISTS cpbl.teams (
    team_id   TEXT PRIMARY KEY,                -- 新 ID，如 ACN
    old_id    TEXT,
    name      TEXT NOT NULL,
    nickname  TEXT
);

-- 逐年球隊戰績（standings.csv）
CREATE TABLE IF NOT EXISTS cpbl.standings (
    year     INT  NOT NULL,
    team_id  TEXT NOT NULL,
    old_id   TEXT,
    team     TEXT,
    nickname TEXT,
    win      INT,
    lose     INT,
    tie      INT,
    PRIMARY KEY (year, team_id)
);

-- 逐年打擊（battings/{year}.csv）。傳出可同年多隊 → PK 含 team_id
CREATE TABLE IF NOT EXISTS cpbl.batting_seasons (
    player_id TEXT NOT NULL,
    year      INT  NOT NULL,
    team_id   TEXT NOT NULL,
    team_name TEXT,
    g    INT, pa INT, ab INT, rbi INT, r INT, h INT,
    b1   INT, b2 INT, b3 INT, hr INT, tb INT,
    so   INT, sb INT, gidp INT, sh INT, sf INT,
    bb   INT, ibb INT, hbp INT, cs INT, go INT, fo INT,
    PRIMARY KEY (player_id, year, team_id)
);

-- 逐年投手（pitchings/{year}.csv）
CREATE TABLE IF NOT EXISTS cpbl.pitching_seasons (
    player_id TEXT NOT NULL,
    year      INT  NOT NULL,
    team_id   TEXT NOT NULL,
    team_name TEXT,
    g   INT, gs INT, gr INT, cg INT, sho INT, nbb INT,
    w   INT, l INT, sv INT, hld INT,
    ip  NUMERIC(5,1), bf INT, np INT,
    h   INT, hr INT, bb INT, ibb INT, hbp INT, so INT,
    wp  INT, bk INT, r INT, er INT, go INT, fo INT,
    PRIMARY KEY (player_id, year, team_id)
);

-- 逐年守備（fieldings/{year}.csv）。同球員同年可多守位 → PK 含 pos
CREATE TABLE IF NOT EXISTS cpbl.fielding_seasons (
    player_id TEXT NOT NULL,
    year      INT  NOT NULL,
    team_id   TEXT NOT NULL,
    team_name TEXT,
    pos  TEXT NOT NULL,
    g    INT, tc INT, po INT, a INT, e INT,
    dp   INT, tp INT, pb INT, cs INT, sb INT,
    PRIMARY KEY (player_id, year, team_id, pos)
);

-- ============ ML：成績預測 ============

-- 模型版本登錄
CREATE TABLE IF NOT EXISTS cpbl.model_versions (
    id          TEXT PRIMARY KEY,              -- 如 lgbm-batting-2026.06.10
    task        TEXT NOT NULL,                 -- batting_projection / pitching_projection
    algo        TEXT NOT NULL,                 -- marcel / lightgbm
    trained_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    params      JSONB,
    cv_metrics  JSONB                          -- 回測 MAE/RMSE per stat
);

-- 預測結果（actual 在對應賽季完成後回填，供回測與準確率展示）
CREATE TABLE IF NOT EXISTS cpbl.projections (
    player_id     TEXT NOT NULL,
    target_year   INT  NOT NULL,
    model_version TEXT NOT NULL REFERENCES cpbl.model_versions(id) ON DELETE CASCADE,
    stat          TEXT NOT NULL,               -- avg/obp/slg/ops/woba/hr...
    predicted     DOUBLE PRECISION,
    actual        DOUBLE PRECISION,
    PRIMARY KEY (player_id, target_year, model_version, stat)
);

CREATE INDEX IF NOT EXISTS idx_batting_seasons_year ON cpbl.batting_seasons (year);
CREATE INDEX IF NOT EXISTS idx_pitching_seasons_year ON cpbl.pitching_seasons (year);
CREATE INDEX IF NOT EXISTS idx_projections_target ON cpbl.projections (target_year, stat);
