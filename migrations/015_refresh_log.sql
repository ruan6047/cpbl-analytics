-- 資料刷新紀錄：每次近期賽事更新寫一列，記錄時間、區間、完成場次與各表更新數，
-- 供追蹤資料新鮮度與偵測缺漏（避免某天比賽結果沒抓到卻無感）。
CREATE TABLE IF NOT EXISTS cpbl.refresh_log (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    refreshed_at    timestamptz NOT NULL DEFAULT now(),
    scope           text NOT NULL,        -- 例：recent-games
    from_date       date,
    to_date         date,
    games_total     int,                  -- 區間內賽程總場次（含未開打）
    games_completed int,                  -- 區間內已完成場次（比分 > 0）
    detail          jsonb,                -- 各表更新列數等明細
    ok              boolean NOT NULL DEFAULT true,
    note            text                  -- 警示訊息（如某日有賽程卻無結果）
);

CREATE INDEX IF NOT EXISTS idx_refresh_log_at ON cpbl.refresh_log (refreshed_at DESC);
