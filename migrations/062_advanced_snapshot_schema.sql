-- INGEST-ADV-EXPAND1：進階排行榜球種／聯盟維度與完整快照 provenance。
-- 只做 additive expand；本 migration 不回填、不清資料、不切換既有 API read path。

CREATE TABLE IF NOT EXISTS cpbl.advanced_ingest_runs (
    id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    year                smallint NOT NULL,
    kind_code           text NOT NULL,
    dataset             text NOT NULL
                        CHECK (dataset IN (
                            'player_stats', 'pitch_type_stats', 'league_summary'
                        )),
    role                text NOT NULL DEFAULT '',
    snapshot_scope      text NOT NULL
                        CHECK (snapshot_scope IN ('full', 'partial')),
    status              text NOT NULL DEFAULT 'running'
                        CHECK (status IN (
                            'running', 'validated', 'rejected', 'promoted', 'failed'
                        )),
    source_endpoint     text NOT NULL,
    source_version      text,
    payload_hash        text,
    schema_hash         text,
    source_fetched_at   timestamptz NOT NULL,
    started_at          timestamptz NOT NULL DEFAULT now(),
    completed_at        timestamptz,
    observed_rows       int NOT NULL DEFAULT 0 CHECK (observed_rows >= 0),
    accepted_rows       int NOT NULL DEFAULT 0 CHECK (accepted_rows >= 0),
    empty_id_rows       int NOT NULL DEFAULT 0 CHECK (empty_id_rows >= 0),
    duplicate_key_rows  int NOT NULL DEFAULT 0 CHECK (duplicate_key_rows >= 0),
    error_report        jsonb NOT NULL DEFAULT '{}'::jsonb,
    provenance          jsonb NOT NULL DEFAULT '{}'::jsonb,
    CHECK (accepted_rows <= observed_rows),
    CHECK (completed_at IS NULL OR completed_at >= started_at)
);

CREATE INDEX IF NOT EXISTS idx_advanced_ingest_runs_scope
    ON cpbl.advanced_ingest_runs
       (year, kind_code, dataset, role, started_at DESC);

-- Reconcile 階段才會原子更新此 pointer；expand 階段保持空表。
CREATE TABLE IF NOT EXISTS cpbl.advanced_snapshot_state (
    year                smallint NOT NULL,
    kind_code           text NOT NULL,
    dataset             text NOT NULL
                        CHECK (dataset IN (
                            'player_stats', 'pitch_type_stats', 'league_summary'
                        )),
    role                text NOT NULL DEFAULT '',
    current_run_id      bigint NOT NULL REFERENCES cpbl.advanced_ingest_runs(id),
    row_count           int NOT NULL CHECK (row_count >= 0),
    source_fetched_at   timestamptz NOT NULL,
    promoted_at         timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (year, kind_code, dataset, role)
);

CREATE TABLE IF NOT EXISTS cpbl.advanced_pitch_type_stats (
    year                smallint NOT NULL,
    kind_code           text NOT NULL,
    role                text NOT NULL,
    acnt                text NOT NULL CHECK (acnt <> ''),
    pitch_type          text NOT NULL CHECK (pitch_type <> ''),
    pitches             int CHECK (pitches >= 0),
    kph                 real CHECK (kph >= 0),
    kph_max             real CHECK (kph_max >= 0),
    spin_rate           real CHECK (spin_rate >= 0),
    spin_rate_max       real CHECK (spin_rate_max >= 0),
    throws              text,
    source_run_id       bigint NOT NULL REFERENCES cpbl.advanced_ingest_runs(id),
    source_fetched_at   timestamptz NOT NULL,
    last_seen_at        timestamptz NOT NULL,
    source_payload      jsonb NOT NULL DEFAULT '{}'::jsonb,
    updated_at          timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (year, kind_code, role, acnt, pitch_type),
    CHECK (last_seen_at >= source_fetched_at)
);

CREATE INDEX IF NOT EXISTS idx_advanced_pitch_type_source_run
    ON cpbl.advanced_pitch_type_stats (source_run_id);

CREATE TABLE IF NOT EXISTS cpbl.advanced_league_summary (
    year                smallint NOT NULL,
    kind_code           text NOT NULL,
    category            text NOT NULL CHECK (category <> ''),
    pitch_type          text NOT NULL DEFAULT '',
    metrics             jsonb NOT NULL,
    source_run_id       bigint NOT NULL REFERENCES cpbl.advanced_ingest_runs(id),
    source_fetched_at   timestamptz NOT NULL,
    last_seen_at        timestamptz NOT NULL,
    source_payload      jsonb NOT NULL DEFAULT '{}'::jsonb,
    updated_at          timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (year, kind_code, category, pitch_type),
    CHECK (last_seen_at >= source_fetched_at)
);

CREATE INDEX IF NOT EXISTS idx_advanced_league_summary_source_run
    ON cpbl.advanced_league_summary (source_run_id);

-- 既有列不猜測 provenance；RECONCILE1 會在差異對帳後填入。
ALTER TABLE cpbl.advanced_stats
    ADD COLUMN IF NOT EXISTS source_run_id bigint
    REFERENCES cpbl.advanced_ingest_runs(id);
ALTER TABLE cpbl.advanced_stats
    ADD COLUMN IF NOT EXISTS source_fetched_at timestamptz;
ALTER TABLE cpbl.advanced_stats
    ADD COLUMN IF NOT EXISTS last_seen_at timestamptz;

CREATE INDEX IF NOT EXISTS idx_advanced_stats_source_run
    ON cpbl.advanced_stats (source_run_id);
