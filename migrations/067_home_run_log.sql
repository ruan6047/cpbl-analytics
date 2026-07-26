-- INGEST-RECORDS-HR1：官網 /stats/hr 逐轟里程碑（低頻 audit ingest）。
-- Natural key 經 DISCOVERY-CPBL-RECORDS1 的 1584 筆跨年／季後抽樣驗證；
-- migrate() 會重跑全部檔案，故 DDL 必須 additive、idempotent。
CREATE TABLE IF NOT EXISTS cpbl.home_run_log (
    year            smallint NOT NULL,
    kind_code       text NOT NULL,
    game_sno        int NOT NULL,
    inning          smallint NOT NULL,
    hitter_acnt     text NOT NULL,
    pitcher_acnt    text NOT NULL,
    game_date       date,
    venue           text,
    hitter_name     text,
    hitter_team_name text,
    pitcher_name    text,
    pitcher_team_name text,
    rbi             smallint,
    source_note     text,
    -- /stats/hr 僅以篩選結果揭露此二維度；未分類／來源缺欄時保留 NULL。
    home_run_type   smallint CHECK (home_run_type BETWEEN 1 AND 5),
    citizenship     smallint CHECK (citizenship IN (0, 1)),
    fetched_at      timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (year, kind_code, game_sno, inning, hitter_acnt, pitcher_acnt)
);
