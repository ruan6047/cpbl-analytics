-- DATA-EDITORIAL1: append-only editorial content revisions and ingest audit log.
-- Sheet row deletion is intentionally not a withdrawal. Editors must append a
-- newer revision with status=withdrawn so removal remains attributable.

CREATE TABLE IF NOT EXISTS cpbl.editorial_ingest_runs (
    run_id UUID PRIMARY KEY,
    source_kind TEXT NOT NULL CHECK (source_kind IN ('google_sheets', 'csv_fixture')),
    source_ref TEXT NOT NULL,
    source_range TEXT,
    source_digest CHAR(64) NOT NULL CHECK (source_digest ~ '^[0-9a-f]{64}$'),
    status TEXT NOT NULL CHECK (status IN ('accepted', 'rejected')),
    total_rows INTEGER NOT NULL CHECK (total_rows >= 0),
    accepted_rows INTEGER NOT NULL DEFAULT 0 CHECK (accepted_rows >= 0),
    unchanged_rows INTEGER NOT NULL DEFAULT 0 CHECK (unchanged_rows >= 0),
    rejected_rows INTEGER NOT NULL DEFAULT 0 CHECK (rejected_rows >= 0),
    error_report JSONB NOT NULL DEFAULT '[]'::jsonb,
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ NOT NULL,
    CHECK (jsonb_typeof(error_report) = 'array'),
    CHECK (completed_at >= started_at),
    CHECK (
        (status = 'accepted' AND rejected_rows = 0 AND error_report = '[]'::jsonb
            AND total_rows = accepted_rows + unchanged_rows)
        OR
        (status = 'rejected' AND accepted_rows = 0 AND unchanged_rows = 0
            AND rejected_rows > 0 AND jsonb_array_length(error_report) > 0)
    )
);

CREATE TABLE IF NOT EXISTS cpbl.editorial_content_revisions (
    content_id TEXT NOT NULL CHECK (content_id ~ '^[a-z0-9][a-z0-9_-]{2,99}$'),
    source_updated_at TIMESTAMPTZ NOT NULL,
    ingest_run_id UUID NOT NULL REFERENCES cpbl.editorial_ingest_runs(run_id),
    source_row_number INTEGER NOT NULL CHECK (source_row_number >= 2),
    content_type TEXT NOT NULL
        CHECK (content_type IN ('cheering_culture', 'theme_day', 'seasonal_banner')),
    status TEXT NOT NULL CHECK (status IN ('active', 'withdrawn')),
    team_code TEXT CHECK (team_code IS NULL OR length(team_code) <= 20),
    title TEXT NOT NULL CHECK (length(btrim(title)) BETWEEN 1 AND 120),
    summary TEXT NOT NULL CHECK (length(btrim(summary)) BETWEEN 1 AND 300),
    body_markdown TEXT NOT NULL DEFAULT '' CHECK (length(body_markdown) <= 20000),
    source_url TEXT NOT NULL CHECK (source_url ~ '^https://'),
    source_label TEXT NOT NULL CHECK (length(btrim(source_label)) BETWEEN 1 AND 120),
    valid_from DATE NOT NULL,
    valid_until DATE NOT NULL,
    updated_by TEXT NOT NULL CHECK (length(btrim(updated_by)) BETWEEN 1 AND 120),
    withdrawal_reason TEXT,
    content_hash CHAR(64) NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (content_id, source_updated_at),
    CHECK (valid_until >= valid_from),
    CHECK (
        (status = 'active' AND withdrawal_reason IS NULL)
        OR
        (status = 'withdrawn' AND withdrawal_reason IS NOT NULL
            AND length(btrim(withdrawal_reason)) BETWEEN 1 AND 300)
    )
);

CREATE INDEX IF NOT EXISTS idx_editorial_revisions_run
    ON cpbl.editorial_content_revisions (ingest_run_id);

CREATE INDEX IF NOT EXISTS idx_editorial_revisions_current
    ON cpbl.editorial_content_revisions (content_id, source_updated_at DESC);

DO $$
BEGIN
    IF to_regclass('cpbl.editorial_content_current') IS NULL THEN
        EXECUTE $view$
            CREATE VIEW cpbl.editorial_content_current AS
            SELECT DISTINCT ON (content_id)
                content_id,
                content_type,
                status,
                team_code,
                title,
                summary,
                body_markdown,
                source_url,
                source_label,
                valid_from,
                valid_until,
                updated_by,
                withdrawal_reason,
                source_updated_at,
                ingest_run_id,
                ingested_at
            FROM cpbl.editorial_content_revisions
            ORDER BY content_id, source_updated_at DESC
        $view$;
    END IF;
END
$$;
