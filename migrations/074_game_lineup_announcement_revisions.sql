-- #238 finite announcement evidence only; no report background snapshots or backfill.
CREATE TABLE IF NOT EXISTS cpbl.game_lineup_announcement_revisions (
    year SMALLINT NOT NULL,
    kind_code TEXT NOT NULL CHECK (kind_code IN ('E', 'C')),
    game_sno INTEGER NOT NULL CHECK (game_sno > 0),
    source_type TEXT NOT NULL CHECK (source_type = 'stats_datagame'),
    source_url TEXT NOT NULL,
    fetched_at TIMESTAMPTZ NOT NULL,
    content_hash TEXT NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
    raw_status TEXT,
    raw_payload JSONB NOT NULL,
    last_seen_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (year, kind_code, game_sno, source_type, fetched_at),
    CHECK (last_seen_at >= fetched_at)
);
CREATE INDEX IF NOT EXISTS idx_lineup_announcement_latest
    ON cpbl.game_lineup_announcement_revisions
       (year, kind_code, game_sno, source_type, fetched_at DESC);
CREATE INDEX IF NOT EXISTS idx_lineup_announcement_content_status_first
    ON cpbl.game_lineup_announcement_revisions
       (year, kind_code, game_sno, source_type, content_hash, raw_status, fetched_at);
