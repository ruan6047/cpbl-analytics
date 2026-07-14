-- 歷年教練職務史（資料源：台灣棒球維基館 twbsball 個人經歷節）。
-- 資料一次性抓取 + 手動刷新（不掛 cron），標 source 與 needs_review 提醒可能需人工複查。
CREATE TABLE IF NOT EXISTS cpbl.coach_history (
    id             SERIAL PRIMARY KEY,
    player_id      TEXT REFERENCES cpbl.players(id),
    name           TEXT NOT NULL,
    raw_text       TEXT NOT NULL,
    phase          TEXT NOT NULL,
    league         TEXT,
    team_raw       TEXT,
    team_code      TEXT,
    pos            TEXT,
    from_year      INT,
    to_year        INT,
    needs_review   BOOLEAN NOT NULL DEFAULT false,
    source         TEXT NOT NULL DEFAULT 'twbsball',
    updated_at     TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_coach_history_name ON cpbl.coach_history (name);
CREATE INDEX IF NOT EXISTS idx_coach_history_player ON cpbl.coach_history (player_id);
