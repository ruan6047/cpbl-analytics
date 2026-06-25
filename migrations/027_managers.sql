-- 歷任總教練（資料源：中文維基百科各球隊條目「歷任/按總教練分」表格）。
-- 維基為人工編修、覆蓋不均（部分球隊條目無此表）；資料一次性抓取 + 手動刷新（不掛 cron），
-- 故標 source 與 needs_review 提醒可能需人工複查。team_code = franchise 代碼（對齊 team_dim）。
CREATE TABLE IF NOT EXISTS cpbl.managers (
    team_code     TEXT NOT NULL,             -- franchise 代碼（6碼，如 ACN011）
    era_name      TEXT NOT NULL,             -- 維基「時期」欄（兄弟象 / 中信兄弟…）
    name          TEXT NOT NULL,
    from_year     INT  NOT NULL,
    to_year       INT,
    g             INT,
    w             INT,
    l             INT,
    t             INT,
    win_pct       DOUBLE PRECISION,
    postseason    INT,                        -- 季後賽進入次數
    championships INT,                        -- 年度總冠軍數
    source        TEXT NOT NULL DEFAULT 'wikipedia',
    needs_review  BOOLEAN NOT NULL DEFAULT true,
    PRIMARY KEY (team_code, era_name, name, from_year)
);
CREATE INDEX IF NOT EXISTS idx_managers_team ON cpbl.managers (team_code);
