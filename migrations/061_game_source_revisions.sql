-- GAME-RECAP-STATUS-EXPAND1：逐場、逐來源的可追溯 revision。
-- 只做 additive expand；歷史資料不猜測、不 backfill final。

CREATE TABLE IF NOT EXISTS cpbl.game_source_revisions (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    year            smallint NOT NULL,
    kind_code       text NOT NULL,
    game_sno        int NOT NULL,
    source          text NOT NULL
                    CHECK (source IN ('schedule', 'scoreboard', 'livelog', 'advanced')),
    source_version  text NOT NULL,
    outcome         text NOT NULL
                    CHECK (outcome IN ('available', 'missing', 'error')),
    row_count       int NOT NULL DEFAULT 0 CHECK (row_count >= 0),
    error_code      text,
    detail          jsonb NOT NULL DEFAULT '{}'::jsonb,
    fetched_at      timestamptz NOT NULL DEFAULT now(),
    last_seen_at    timestamptz NOT NULL DEFAULT now(),
    seen_count      int NOT NULL DEFAULT 1 CHECK (seen_count > 0),
    UNIQUE (year, kind_code, game_sno, source, source_version)
);

CREATE INDEX IF NOT EXISTS idx_game_source_revisions_latest
    ON cpbl.game_source_revisions
       (year, kind_code, game_sno, source, last_seen_at DESC);

CREATE TABLE IF NOT EXISTS cpbl.game_schedule_status_revisions (
    id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    year                smallint NOT NULL,
    kind_code           text NOT NULL,
    game_season_code    text NOT NULL DEFAULT '',
    game_sno            int NOT NULL,
    raw_present_status  int,
    raw_game_result     text,
    raw_game_date       date,
    raw_pre_exe_date    date,
    payload_hash        text NOT NULL,
    raw_payload         jsonb NOT NULL,
    fetched_at          timestamptz NOT NULL DEFAULT now(),
    last_seen_at        timestamptz NOT NULL DEFAULT now(),
    seen_count          int NOT NULL DEFAULT 1 CHECK (seen_count > 0),
    UNIQUE (year, kind_code, game_season_code, game_sno, payload_hash)
);

CREATE INDEX IF NOT EXISTS idx_game_schedule_status_revisions_latest
    ON cpbl.game_schedule_status_revisions
       (year, kind_code, game_sno, last_seen_at DESC);
