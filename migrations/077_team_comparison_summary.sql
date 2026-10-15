-- #287 S06：季後賽第 2 區「全年 A／兩隊 A 對戰」背景摘要（本機離線 builder 唯一 writer；
-- 生產只經 refresh-cpbl-prod.sh 的 TEAM_COMPARISON_ONLY／完整鏈 insert-only 同步）。
-- 純新增（expand），整檔冪等（cpbl.db.migrate() 每次全跑）。
--
-- 形狀：不可變 build ＋ 不可變計數列 ＋ 每 (year, kind) 一列 current 指標。
--   · build_id＝uuid5(固定 namespace, "{year}|{builder_version}|{source_hash}")，本機與生產同 ID。
--   · 列只存**原始計數**；率一律由讀端以計數現算（G11）。NULL＝未知，⛔ 不當 0（G06）。
--   · current 是唯一可 UPDATE 的表；切換與列寫入同交易，讀者只會看到舊版或新版。
-- 不變量（DB 層保證）：
--   1. build／row 寫入後不可變：UPDATE／DELETE／TRUNCATE 一律拒絕；誤把摘要表加進
--      sync_table（INSERT … ON CONFLICT DO UPDATE）會被 BEFORE UPDATE 擋下。
--      ⛔ 清理舊 build 屬另卡 contract 作業，須需求方裁定＋顯式 DISABLE TRIGGER。
--   2. current 只能指向同年的 build（複合 FK (build_id, year)）。
--   3. 沒有任何既有表參照本檔新表；新 FK 只指向本檔新表與 team_dim。

-- 1. build ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS cpbl.team_comparison_build (
    build_id          UUID PRIMARY KEY,
    year              SMALLINT NOT NULL CHECK (year BETWEEN 2018 AND 2100),
    kind_code         TEXT NOT NULL CHECK (kind_code = 'A'),
    builder_version   TEXT NOT NULL
        CHECK (builder_version ~ '^team-comparison-[0-9]+\.[0-9]+\.[0-9]+$'),
    source_hash       TEXT NOT NULL CHECK (source_hash ~ '^[0-9a-f]{64}$'),
    games_fingerprint TEXT NOT NULL CHECK (games_fingerprint ~ '^[0-9a-f]{64}$'),
    completed_games   INTEGER NOT NULL CHECK (completed_games >= 0),
    rows_digest       TEXT NOT NULL CHECK (rows_digest ~ '^[0-9a-f]{64}$'),
    coverage          JSONB NOT NULL,
    built_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (year, builder_version, source_hash),
    UNIQUE (build_id, year)
);

-- 2. 計數列 ------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS cpbl.team_comparison_row (
    build_id         UUID NOT NULL REFERENCES cpbl.team_comparison_build (build_id),
    scope            TEXT NOT NULL CHECK (scope IN ('season', 'head_to_head')),
    team_code        TEXT NOT NULL REFERENCES cpbl.team_dim (team_code),
    opponent_code    TEXT NOT NULL DEFAULT '',
    games            INTEGER NOT NULL CHECK (games >= 0),
    wins             INTEGER NOT NULL CHECK (wins >= 0),
    losses           INTEGER NOT NULL CHECK (losses >= 0),
    ties             INTEGER NOT NULL CHECK (ties >= 0),
    runs_for         INTEGER,
    runs_against     INTEGER,
    bat_pa           INTEGER,
    bat_ab           INTEGER,
    bat_h            INTEGER,
    bat_1b           INTEGER,
    bat_tb           INTEGER,
    bat_bb           INTEGER,
    bat_hbp          INTEGER,
    bat_sf           INTEGER,
    bat_sh           INTEGER,
    bat_so           INTEGER,
    bat_sb           INTEGER,
    bat_cs           INTEGER,
    pit_outs         INTEGER,
    pit_starter_outs INTEGER,
    pit_bf           INTEGER,
    pit_h            INTEGER,
    pit_hr           INTEGER,
    pit_bb           INTEGER,
    pit_hbp          INTEGER,
    pit_so           INTEGER,
    pit_er           INTEGER,
    streak_result    TEXT CHECK (streak_result IN ('W', 'L', 'T')),
    streak_len       INTEGER CHECK (streak_len >= 1),
    streak_through   TEXT,
    null_reasons     JSONB NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY (build_id, scope, team_code, opponent_code),
    CHECK (games = wins + losses + ties),
    CHECK ((scope = 'season' AND opponent_code = '')
        OR (scope = 'head_to_head' AND opponent_code <> '' AND opponent_code <> team_code)),
    CHECK ((streak_result IS NULL) = (streak_len IS NULL)),
    CHECK ((streak_result IS NULL) = (streak_through IS NULL))
);

-- 3. current 指標（每 (year, kind) 一列；唯一可 UPDATE 的表）------------------------
CREATE TABLE IF NOT EXISTS cpbl.team_comparison_current (
    year                SMALLINT NOT NULL,
    kind_code           TEXT NOT NULL CHECK (kind_code = 'A'),
    build_id            UUID NOT NULL,
    promoted_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    pending_source_hash TEXT CHECK (pending_source_hash ~ '^[0-9a-f]{64}$'),
    pending_since       TIMESTAMPTZ,
    PRIMARY KEY (year, kind_code),
    FOREIGN KEY (build_id, year) REFERENCES cpbl.team_comparison_build (build_id, year),
    CHECK ((pending_source_hash IS NULL) = (pending_since IS NULL))
);

-- 4. 不可變守衛（build／row）---------------------------------------------------------
CREATE OR REPLACE FUNCTION cpbl.reject_team_comparison_mutation() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'cpbl.% 不可變：拒絕 %（隊伍比較摘要 build 寫入後不得修改；舊版保留、改以新 build 切換 current）',
        TG_TABLE_NAME, TG_OP
        USING ERRCODE = 'restrict_violation';
END
$$;

CREATE OR REPLACE TRIGGER team_comparison_build_immutable
    BEFORE UPDATE OR DELETE ON cpbl.team_comparison_build
    FOR EACH ROW EXECUTE FUNCTION cpbl.reject_team_comparison_mutation();
CREATE OR REPLACE TRIGGER team_comparison_build_no_truncate
    BEFORE TRUNCATE ON cpbl.team_comparison_build
    FOR EACH STATEMENT EXECUTE FUNCTION cpbl.reject_team_comparison_mutation();
CREATE OR REPLACE TRIGGER team_comparison_row_immutable
    BEFORE UPDATE OR DELETE ON cpbl.team_comparison_row
    FOR EACH ROW EXECUTE FUNCTION cpbl.reject_team_comparison_mutation();
CREATE OR REPLACE TRIGGER team_comparison_row_no_truncate
    BEFORE TRUNCATE ON cpbl.team_comparison_row
    FOR EACH STATEMENT EXECUTE FUNCTION cpbl.reject_team_comparison_mutation();
