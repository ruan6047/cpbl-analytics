-- #268 D1（需求方裁定 6142259348）：官方賽程異動訊號。
-- 季後晚間事件鏈以官方 stats 賽程偵測到「官方已異動（新場次／改期／改主客／改球場）、本站正式資料尚未反映」
-- 時記一列；同步對帳通過（或偵測不再成立）後寫 resolved_at。只是待更新訊號：不是賽程或完賽來源，
-- 不改 cpbl.games、不作完賽判準。只新增、冪等；不回填、不改既有表。
CREATE TABLE IF NOT EXISTS cpbl.official_change_signals (
    year SMALLINT NOT NULL,
    kind_code TEXT NOT NULL CHECK (kind_code IN ('E', 'C')),
    game_sno INTEGER NOT NULL CHECK (game_sno > 0),
    field TEXT NOT NULL CHECK (field IN ('game', 'date', 'teams', 'venue')),
    official_value TEXT,
    detected_at TIMESTAMPTZ NOT NULL,
    resolved_at TIMESTAMPTZ,
    PRIMARY KEY (year, kind_code, game_sno, field),
    CHECK (resolved_at IS NULL OR resolved_at >= detected_at)
);
CREATE INDEX IF NOT EXISTS idx_official_change_signals_unresolved
    ON cpbl.official_change_signals (year, kind_code, game_sno)
    WHERE resolved_at IS NULL;
