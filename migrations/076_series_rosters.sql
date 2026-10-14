-- #284 S03：季後賽官方 32 人資格名單（本機 CLI 唯一 writer；生產只經 insert-only 同步）。
-- 純新增（expand），整檔冪等（cpbl.db.migrate() 每次全跑）。
--
-- 不變量（DB 層保證，不依賴呼叫端）：
--   1. 每 (year, kind_code, team_code) 至多一份名單（唯一鍵；競爭提交至多一個成功）。
--   2. 三表提交後不可變：UPDATE／DELETE／TRUNCATE 一律拒絕；sync_table 式
--      INSERT … ON CONFLICT DO UPDATE 落到既有列同樣被 BEFORE UPDATE 擋下。
--      ⛔ 例外修正須需求方裁定＋另卡顯式 DISABLE TRIGGER，不是 routine 路徑。
--   3. 每份名單恰 32 名會員、恰有角色版本 1；每個角色版本恰 32 列、同版同一 revision_hash、
--      版本號連續（延遲約束，交易提交時檢查；未滿 32 不能提交）。
-- 資格名單只表示官方登錄資格，⛔ 不含先發／當場登錄／可用性欄位。
-- kind_code／team_code 是 S02 契約核定前的最小介面假設（#284 T1 裁定 A）：不保存 series_id 與規則版本。

CREATE TABLE IF NOT EXISTS cpbl.series_roster (
    roster_id            UUID PRIMARY KEY,
    year                 SMALLINT NOT NULL CHECK (year BETWEEN 1990 AND 2100),
    kind_code            TEXT NOT NULL CHECK (kind_code IN ('E', 'C')),
    team_code            TEXT NOT NULL REFERENCES cpbl.team_dim (team_code),
    source_url           TEXT NOT NULL CHECK (btrim(source_url) <> ''),
    published_date       DATE NOT NULL,
    published_precision  TEXT NOT NULL CHECK (published_precision IN ('date')),
    observed_at          TIMESTAMPTZ NOT NULL,
    observation_basis    TEXT NOT NULL
                         CHECK (observation_basis IN ('cli_input', 'first_recorded_acquisition')),
    identity_verified_at TIMESTAMPTZ NOT NULL,
    input_origin         TEXT NOT NULL CHECK (input_origin IN ('pasted_text', 'official_population_v1')),
    raw_text             TEXT NOT NULL CHECK (btrim(raw_text) <> ''),
    hash_version         SMALLINT NOT NULL CHECK (hash_version = 1),
    membership_hash      TEXT NOT NULL CHECK (membership_hash ~ '^[0-9a-f]{64}$'),
    source_hash          TEXT NOT NULL CHECK (source_hash ~ '^[0-9a-f]{64}$'),
    import_check         JSONB NOT NULL,
    submitted_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (year, kind_code, team_code)
);

CREATE TABLE IF NOT EXISTS cpbl.series_roster_member (
    roster_id         UUID NOT NULL REFERENCES cpbl.series_roster (roster_id),
    player_id         TEXT NOT NULL CHECK (player_id ~ '^[0-9]{10}$'),
    official_position TEXT NOT NULL CHECK (official_position IN ('投手', '捕手', '內野手', '外野手')),
    announced_name    TEXT NOT NULL CHECK (btrim(announced_name) <> ''),
    PRIMARY KEY (roster_id, player_id)
);
CREATE INDEX IF NOT EXISTS idx_series_roster_member_player
    ON cpbl.series_roster_member (player_id);

CREATE TABLE IF NOT EXISTS cpbl.roster_annotation_revision (
    roster_id     UUID NOT NULL,
    revision      INTEGER NOT NULL CHECK (revision >= 1),
    player_id     TEXT NOT NULL,
    tactical_role TEXT NOT NULL CHECK (tactical_role IN
                  ('輪值', '終結', '勝利組', '長中繼', '主力', '代打', '守備', '待命', 'unclassified')),
    revision_hash TEXT NOT NULL CHECK (revision_hash ~ '^[0-9a-f]{64}$'),
    changed_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (roster_id, revision, player_id),
    FOREIGN KEY (roster_id, player_id)
        REFERENCES cpbl.series_roster_member (roster_id, player_id)
);

-- 2. 不可變守衛 ------------------------------------------------------------
CREATE OR REPLACE FUNCTION cpbl.reject_roster_mutation() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'cpbl.% 不可變：拒絕 %（名單提交後不得修改；例外修正須需求方裁定另卡處理）',
        TG_TABLE_NAME, TG_OP
        USING ERRCODE = 'restrict_violation';
END
$$;

CREATE OR REPLACE TRIGGER series_roster_immutable
    BEFORE UPDATE OR DELETE ON cpbl.series_roster
    FOR EACH ROW EXECUTE FUNCTION cpbl.reject_roster_mutation();
CREATE OR REPLACE TRIGGER series_roster_no_truncate
    BEFORE TRUNCATE ON cpbl.series_roster
    FOR EACH STATEMENT EXECUTE FUNCTION cpbl.reject_roster_mutation();
CREATE OR REPLACE TRIGGER series_roster_member_immutable
    BEFORE UPDATE OR DELETE ON cpbl.series_roster_member
    FOR EACH ROW EXECUTE FUNCTION cpbl.reject_roster_mutation();
CREATE OR REPLACE TRIGGER series_roster_member_no_truncate
    BEFORE TRUNCATE ON cpbl.series_roster_member
    FOR EACH STATEMENT EXECUTE FUNCTION cpbl.reject_roster_mutation();
CREATE OR REPLACE TRIGGER roster_annotation_revision_immutable
    BEFORE UPDATE OR DELETE ON cpbl.roster_annotation_revision
    FOR EACH ROW EXECUTE FUNCTION cpbl.reject_roster_mutation();
CREATE OR REPLACE TRIGGER roster_annotation_revision_no_truncate
    BEFORE TRUNCATE ON cpbl.roster_annotation_revision
    FOR EACH STATEMENT EXECUTE FUNCTION cpbl.reject_roster_mutation();

-- 3. 延遲約束（交易提交時檢查）---------------------------------------------
-- 名單頭或會員有新增：該名單必須恰 32 名會員，且角色版本 1 恰 32 列。
-- 對既有名單事後補插會員（不是 UPDATE，不受 2 的守衛）同樣在提交時因人數 ≠ 32 被拒。
CREATE OR REPLACE FUNCTION cpbl.check_series_roster_complete() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    n_members integer;
    n_rev1    integer;
BEGIN
    IF NOT EXISTS (SELECT 1 FROM cpbl.series_roster WHERE roster_id = NEW.roster_id) THEN
        RETURN NULL;  -- 會員列的 FK 會另行擋下孤兒
    END IF;
    SELECT count(*) INTO n_members FROM cpbl.series_roster_member WHERE roster_id = NEW.roster_id;
    IF n_members <> 32 THEN
        RAISE EXCEPTION 'series_roster % 會員數 % ≠ 32：未滿或超過 32 人不能提交', NEW.roster_id, n_members
            USING ERRCODE = 'check_violation';
    END IF;
    SELECT count(*) INTO n_rev1 FROM cpbl.roster_annotation_revision
     WHERE roster_id = NEW.roster_id AND revision = 1;
    IF n_rev1 <> 32 THEN
        RAISE EXCEPTION 'series_roster % 角色版本 1 列數 % ≠ 32', NEW.roster_id, n_rev1
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NULL;
END
$$;

-- 角色版本有新增：該版恰 32 列、同一 revision_hash，且版本號連續（1 或前一版已存在）。
CREATE OR REPLACE FUNCTION cpbl.check_roster_revision_complete() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    n_rows   integer;
    n_hashes integer;
BEGIN
    SELECT count(*), count(DISTINCT revision_hash) INTO n_rows, n_hashes
      FROM cpbl.roster_annotation_revision
     WHERE roster_id = NEW.roster_id AND revision = NEW.revision;
    IF n_rows <> 32 OR n_hashes <> 1 THEN
        RAISE EXCEPTION 'roster % 角色版本 % 列數 %／雜湊數 %：每版須恰 32 列且同一 revision_hash',
            NEW.roster_id, NEW.revision, n_rows, n_hashes
            USING ERRCODE = 'check_violation';
    END IF;
    IF NEW.revision > 1 AND NOT EXISTS (
        SELECT 1 FROM cpbl.roster_annotation_revision
         WHERE roster_id = NEW.roster_id AND revision = NEW.revision - 1
    ) THEN
        RAISE EXCEPTION 'roster % 角色版本 % 不連續（缺版本 %）', NEW.roster_id, NEW.revision, NEW.revision - 1
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NULL;
END
$$;

-- CONSTRAINT TRIGGER 不支援 CREATE OR REPLACE（PG17 仍是），故以目錄查詢保冪等。
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger
                    WHERE tgrelid = 'cpbl.series_roster'::regclass
                      AND tgname = 'series_roster_complete') THEN
        CREATE CONSTRAINT TRIGGER series_roster_complete
            AFTER INSERT ON cpbl.series_roster
            DEFERRABLE INITIALLY DEFERRED
            FOR EACH ROW EXECUTE FUNCTION cpbl.check_series_roster_complete();
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_trigger
                    WHERE tgrelid = 'cpbl.series_roster_member'::regclass
                      AND tgname = 'series_roster_member_complete') THEN
        CREATE CONSTRAINT TRIGGER series_roster_member_complete
            AFTER INSERT ON cpbl.series_roster_member
            DEFERRABLE INITIALLY DEFERRED
            FOR EACH ROW EXECUTE FUNCTION cpbl.check_series_roster_complete();
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_trigger
                    WHERE tgrelid = 'cpbl.roster_annotation_revision'::regclass
                      AND tgname = 'roster_annotation_revision_complete') THEN
        CREATE CONSTRAINT TRIGGER roster_annotation_revision_complete
            AFTER INSERT ON cpbl.roster_annotation_revision
            DEFERRABLE INITIALLY DEFERRED
            FOR EACH ROW EXECUTE FUNCTION cpbl.check_roster_revision_complete();
    END IF;
END
$$;
