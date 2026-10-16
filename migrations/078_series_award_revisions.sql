-- #288 S07 WP-AWARDS：官方系列獎項窄表（本機離線 CLI `cpbl-import-series-awards` 唯一 writer；
-- 生產只經 refresh-cpbl-prod.sh 的 sync_table 同步）。純新增（expand），整檔冪等（cpbl.db.migrate() 每次全跑）。
--
-- 形狀：每次查核官方公布頁＝一個 revision（append-only）；讀端只取每系列最新 revision。
--   · status=published：官方已公布，得主列在 series_award_winner（共同得主＝同 award_seq 多個 ordinal，⛔ 壓成單一 ID）。
--   · status=not_published：本站查核時官方尚未公布（≠ 本站未取得；「未取得」＝沒有任何 revision）。
-- 不變量（DB 層保證）：
--   1. 兩表寫入後不可變：UPDATE／DELETE／TRUNCATE 一律拒絕。sync_table 只對「值不同」的既有列 UPDATE，
--      故同內容重送是 no-op；若本機與生產同鍵不同值，同步會被觸發器擋下並大聲失敗。
--      ⛔ 例外修正須需求方裁定＋另卡顯式 DISABLE TRIGGER。
--   2. 得主列只能掛在 status=published 的 revision（插入時檢查）。
--   3. 「published 至少一位得主」不在 DB 層強制：sync_table 逐表各自一個交易，revision 會先於得主寫入；
--      由匯入 CLI 在同一交易內保證，讀端遇到 0 位得主的 published 一律當「本站尚未取得」（fail closed）。
--   4. 來源只收官方站 https（www.cpbl.com.tw／cpbl.com.tw／stats.cpbl.com.tw）。
--   5. 沒有任何既有表參照本檔新表；新 FK 只指向本檔新表與 team_dim。⛔ 不讀寫 029 player_awards／058 team_year_awards。

-- 1. revision ----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS cpbl.series_award_revision (
    year          SMALLINT NOT NULL CHECK (year BETWEEN 1990 AND 2100),
    kind_code     TEXT NOT NULL CHECK (kind_code IN ('E', 'C')),
    revision      INTEGER NOT NULL CHECK (revision >= 1),
    status        TEXT NOT NULL CHECK (status IN ('published', 'not_published')),
    source_url    TEXT NOT NULL
        CHECK (source_url ~ '^https://(www\.|stats\.)?cpbl\.com\.tw(/[^[:space:]\\]*)?$'),
    source_sha256 TEXT NOT NULL CHECK (source_sha256 ~ '^[0-9a-f]{64}$'),
    checked_at    TIMESTAMPTZ NOT NULL,
    imported_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (year, kind_code, revision)
);

-- 2. 得主 --------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS cpbl.series_award_winner (
    year        SMALLINT NOT NULL,
    kind_code   TEXT NOT NULL,
    revision    INTEGER NOT NULL,
    award_seq   SMALLINT NOT NULL CHECK (award_seq >= 1),     -- 官方公布的獎項順序
    ordinal     SMALLINT NOT NULL CHECK (ordinal >= 1),       -- 同一獎項內的得主順序（共同得主）
    award_name  TEXT NOT NULL CHECK (btrim(award_name) <> ''),  -- 官方完整名稱
    award_type  TEXT NOT NULL CHECK (award_type IN ('series_mvp', 'other')),
    player_id   TEXT CHECK (player_id ~ '^[0-9]{10}$'),       -- 可為 NULL（官方名單對不到本站 ID 時不猜）
    winner_name TEXT NOT NULL CHECK (btrim(winner_name) <> ''),  -- 官方公布的姓名（顯示以此為準）
    team_code   TEXT REFERENCES cpbl.team_dim (team_code),
    PRIMARY KEY (year, kind_code, revision, award_seq, ordinal),
    FOREIGN KEY (year, kind_code, revision) REFERENCES cpbl.series_award_revision (year, kind_code, revision)
);

-- 3. 不可變守衛 ----------------------------------------------------------------------
CREATE OR REPLACE FUNCTION cpbl.reject_series_award_mutation() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'cpbl.% 不可變：拒絕 %（官方系列獎項以新 revision 追加；例外修正須需求方裁定另卡處理）',
        TG_TABLE_NAME, TG_OP
        USING ERRCODE = 'restrict_violation';
END
$$;

CREATE OR REPLACE TRIGGER series_award_revision_immutable
    BEFORE UPDATE OR DELETE ON cpbl.series_award_revision
    FOR EACH ROW EXECUTE FUNCTION cpbl.reject_series_award_mutation();
CREATE OR REPLACE TRIGGER series_award_revision_no_truncate
    BEFORE TRUNCATE ON cpbl.series_award_revision
    FOR EACH STATEMENT EXECUTE FUNCTION cpbl.reject_series_award_mutation();
CREATE OR REPLACE TRIGGER series_award_winner_immutable
    BEFORE UPDATE OR DELETE ON cpbl.series_award_winner
    FOR EACH ROW EXECUTE FUNCTION cpbl.reject_series_award_mutation();
CREATE OR REPLACE TRIGGER series_award_winner_no_truncate
    BEFORE TRUNCATE ON cpbl.series_award_winner
    FOR EACH STATEMENT EXECUTE FUNCTION cpbl.reject_series_award_mutation();

-- 4. 得主只能掛在 published revision ----------------------------------------------------
CREATE OR REPLACE FUNCTION cpbl.check_series_award_winner_published() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM cpbl.series_award_revision r
        WHERE r.year = NEW.year AND r.kind_code = NEW.kind_code AND r.revision = NEW.revision
          AND r.status = 'published'
    ) THEN
        RAISE EXCEPTION 'cpbl.series_award_winner：revision %/%/% 不是 published，不能有得主',
            NEW.year, NEW.kind_code, NEW.revision
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END
$$;

CREATE OR REPLACE TRIGGER series_award_winner_requires_published
    BEFORE INSERT ON cpbl.series_award_winner
    FOR EACH ROW EXECUTE FUNCTION cpbl.check_series_award_winner_published();
