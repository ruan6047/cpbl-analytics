-- PLAYER-BIO：選手生涯歷程＋暱稱（twbsball 經歷節）。
--
-- 1) coach_history → person_history 改名：該表本來就存 phase='player' 的列，現在種子擴及
--    選手（現役∪近三季∪各榜前十），叫 coach_history 會誤導後人。純改名，欄位不動。
-- 2) players 補 nickname：官網 person 頁沒有暱稱，twbsball 有。結構化欄位「綽號別稱」可直接
--    採用；只寫在內文者（如林智勝「大師兄」）誤抓風險高，一律 needs_review 待人工複查。
DO $$
BEGIN
    IF to_regclass('cpbl.coach_history') IS NOT NULL
       AND to_regclass('cpbl.person_history') IS NULL THEN
        ALTER TABLE cpbl.coach_history RENAME TO person_history;
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS cpbl.person_history (
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
CREATE INDEX IF NOT EXISTS idx_person_history_name ON cpbl.person_history (name);
CREATE INDEX IF NOT EXISTS idx_person_history_player ON cpbl.person_history (player_id);

-- 相容 view：生產是「先套 migration、後換映像」，舊程式碼仍讀 coach_history。
-- 沒有這個 view，改名到部署完成之間教練頁會 500。部署穩定後可另開 migration 移除。
CREATE OR REPLACE VIEW cpbl.coach_history AS SELECT * FROM cpbl.person_history;

-- 暱稱以**人名**為主鍵，不掛在 players 上：指標性暱稱的持有者未必是中職球員——
-- 郭泰源（小郭）1985–97 效力日職西武、回台只當教練，`players` 根本沒有他，
-- 掛在 players 的欄位會讓他的暱稱無處可放。player_id 僅在能歸戶時附上。
CREATE TABLE IF NOT EXISTS cpbl.person_nickname (
    name          TEXT PRIMARY KEY,
    nickname      TEXT[] NOT NULL,
    player_id     TEXT REFERENCES cpbl.players(id),
    source        TEXT NOT NULL CHECK (source IN ('field', 'prose')),
    needs_review  BOOLEAN NOT NULL DEFAULT false,   -- prose 來源句型鬆散，易誤抓他人綽號
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_person_nickname_player ON cpbl.person_nickname (player_id);
