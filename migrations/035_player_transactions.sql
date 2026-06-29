-- 球員異動（升降一/二軍）記錄，來源：官網 /player/trans（聯盟級事件 log，含 acnt）。
-- 用途：重建每位現役球員本季「一軍/二軍登錄天數」以判定主要層級。
-- 事件 log 無季初基準狀態，故天數重建會輔以出賽(gamelog A/D) fallback（見 api 計算）。
CREATE TABLE IF NOT EXISTS cpbl.player_transactions (
    year       INT  NOT NULL,
    acnt       TEXT NOT NULL,
    trans_date DATE NOT NULL,
    kind_code  TEXT NOT NULL,          -- 01 升一軍 / 02 降二軍（目前只存這兩種層級變動）
    name       TEXT,
    team_name  TEXT,
    reason     TEXT,                    -- 異動原因中文（升一軍/降二軍）
    updated_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (year, acnt, trans_date, kind_code)
);

CREATE INDEX IF NOT EXISTS idx_player_transactions_acnt ON cpbl.player_transactions (year, acnt, trans_date);
