-- 生涯分項錨定基底 [career anchor base]：Phase 2 停爬生涯 apart 後，
-- 生涯(9999) = base(官方生涯−官方本季，同刻相減=純歷史) + 本季重算。
-- base 由 cpbl-anchor-career 一次寫入；跨年 roll（base += 上季終值）亦寫此表。
-- 欄位=主表計數欄（rate 由合併後重算，不存）；index/note 照官方原列搬（含
-- 局數13+的空名列），PK 與主表對齊（少 year 維度）。

CREATE TABLE IF NOT EXISTS cpbl.batting_splits_career_base (
    kind_code        text NOT NULL,
    acnt             text NOT NULL,
    item_group_code  text NOT NULL,
    item_index       int  NOT NULL,
    item_name        text NOT NULL,
    item_note        text,
    plate_appearances int NOT NULL DEFAULT 0,
    at_bats          int NOT NULL DEFAULT 0,
    hits             int NOT NULL DEFAULT 0,
    rbi              int NOT NULL DEFAULT 0,
    singles          int NOT NULL DEFAULT 0,
    doubles          int NOT NULL DEFAULT 0,
    triples          int NOT NULL DEFAULT 0,
    home_runs        int NOT NULL DEFAULT 0,
    total_bases      int NOT NULL DEFAULT 0,
    sac_hit          int NOT NULL DEFAULT 0,
    sac_fly          int NOT NULL DEFAULT 0,
    bb               int NOT NULL DEFAULT 0,
    ibb              int NOT NULL DEFAULT 0,
    hbp              int NOT NULL DEFAULT 0,
    so               int NOT NULL DEFAULT 0,
    ground_outs      int NOT NULL DEFAULT 0,
    fly_outs         int NOT NULL DEFAULT 0,
    anchored_at      timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (kind_code, acnt, item_group_code, item_index, item_name)
);

CREATE TABLE IF NOT EXISTS cpbl.pitching_splits_career_base (
    kind_code        text NOT NULL,
    acnt             text NOT NULL,
    item_group_code  text NOT NULL,
    item_index       int  NOT NULL,
    item_name        text NOT NULL,
    item_note        text,
    wins             int NOT NULL DEFAULT 0,
    loses            int NOT NULL DEFAULT 0,
    starts           int NOT NULL DEFAULT 0,
    complete_games   int NOT NULL DEFAULT 0,
    shutouts         int NOT NULL DEFAULT 0,
    save_ok          int NOT NULL DEFAULT 0,
    inning_pitched_div3 int NOT NULL DEFAULT 0,  -- 出局數（可加總；cnt/div3 寫回時再拆）
    plate_appearances int NOT NULL DEFAULT 0,
    pitch_cnt        int NOT NULL DEFAULT 0,
    strikes          int NOT NULL DEFAULT 0,
    balls            int NOT NULL DEFAULT 0,
    hits             int NOT NULL DEFAULT 0,
    home_runs        int NOT NULL DEFAULT 0,
    sac_hit          int NOT NULL DEFAULT 0,
    sac_fly          int NOT NULL DEFAULT 0,
    bb               int NOT NULL DEFAULT 0,
    ibb              int NOT NULL DEFAULT 0,
    hbp              int NOT NULL DEFAULT 0,
    so               int NOT NULL DEFAULT 0,
    wild_pitch       int NOT NULL DEFAULT 0,
    balk             int NOT NULL DEFAULT 0,
    runs             int NOT NULL DEFAULT 0,
    earned_runs      int NOT NULL DEFAULT 0,
    anchored_at      timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (kind_code, acnt, item_group_code, item_index, item_name)
);

CREATE INDEX IF NOT EXISTS idx_bscb_acnt ON cpbl.batting_splits_career_base (acnt);
CREATE INDEX IF NOT EXISTS idx_pscb_acnt ON cpbl.pitching_splits_career_base (acnt);
