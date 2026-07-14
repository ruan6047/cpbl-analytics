-- TEAM-HIST1：隊史年表（twbsball「分類:職棒球隊年表」246 頁）補三個缺口。
--
-- 1) team_year_staff：歷年教練團。現有 coaches 只有 2026 現任、managers 只有歷任總教練，
--    1995 味全的中村典夫／成田幸洋這類歷年教練完全沒有。
--    **role 照抄原始欄位**（早期只有「總教練」與「教練」兩級；嚴禁腦補成助理教練／投手教練）。
-- 2) player_name_changes：歷年改名。`players` 無舊名欄位，現行改名靠每日 gamelog 事後同步，
--    歷史改名紀錄等於全失——這是唯一「無替代來源且影響生涯串接」的缺口。
-- 3) team_year_awards：逐年獲獎（分一軍／二軍）。player_awards 的二軍獎項為 0 筆。
-- 4) roster_moves：註冊／註銷／新進／離隊。player_transactions 只有 2026。
--
-- 來源為次級 wiki，故一律留 raw 原文並可標 needs_review；不覆蓋官網一手資料。
-- 兩種頁面格式：早期「*總教練：X」「*教　練：A、B」；近年「*教練團成員：」→
-- 「:*一軍教練團：黃甘霖（總教練）、高政華…」。level 僅近年格式有（早期為 NULL）。
CREATE TABLE IF NOT EXISTS cpbl.team_year_staff (
    year        smallint NOT NULL,
    team_code   text     NOT NULL,
    role        text     NOT NULL,          -- 原始欄位：總教練／教練／領隊／副領隊…
    name        text     NOT NULL,
    level       text     NOT NULL DEFAULT '', -- 一軍／二軍（早期頁面無此分層 → 空字串）
    note        text,                          -- 原文括號（如「下半季7月5日起代理總教練」）
    source      text     NOT NULL DEFAULT 'twbsball',
    updated_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (year, team_code, role, name, level)
);
CREATE INDEX IF NOT EXISTS idx_team_year_staff_name ON cpbl.team_year_staff (name);

CREATE TABLE IF NOT EXISTS cpbl.player_name_changes (
    year        smallint NOT NULL,
    team_code   text     NOT NULL,
    old_name    text     NOT NULL,
    new_name    text     NOT NULL,
    note        text,                        -- 原文括號（如「季後，10月26日」）
    source      text     NOT NULL DEFAULT 'twbsball',
    updated_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (year, team_code, old_name, new_name)
);
CREATE INDEX IF NOT EXISTS idx_name_changes_old ON cpbl.player_name_changes (old_name);
CREATE INDEX IF NOT EXISTS idx_name_changes_new ON cpbl.player_name_changes (new_name);

CREATE TABLE IF NOT EXISTS cpbl.team_year_awards (
    year        smallint NOT NULL,
    team_code   text     NOT NULL,
    level       text     NOT NULL,          -- 一軍／二軍
    name        text     NOT NULL,
    award_raw   text     NOT NULL,          -- 原文（獎項名稱未正規化，避免腦補）
    source      text     NOT NULL DEFAULT 'twbsball',
    updated_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (year, team_code, level, name, award_raw)
);

CREATE TABLE IF NOT EXISTS cpbl.roster_moves (
    year        smallint NOT NULL,
    team_code   text     NOT NULL,
    kind        text     NOT NULL,          -- 原始欄位：合約所屬轉註冊／註銷註冊／新進人員／離隊人員
    name        text     NOT NULL,
    detail      text,                        -- 原文括號（日期等）
    source      text     NOT NULL DEFAULT 'twbsball',
    updated_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (year, team_code, kind, name)
);
CREATE INDEX IF NOT EXISTS idx_roster_moves_name ON cpbl.roster_moves (name);
