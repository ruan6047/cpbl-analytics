-- INGEST-GAME-TM-REFACTOR1 Gate 3：隔離 shadow harness（不可寫 cpbl.pitch_tracking）。
-- 目的：以單場 API 路徑（Gate 1-2 既有 parse_pitches/_fetch_game_livelog，本卡不改）產出
-- 逐球資料寫入本檔獨立表，並與正式 cpbl.pitch_tracking（現行 logs 路徑 writer）逐日對帳，
-- 14 天觀測窗記錄未解差異。全部 IF NOT EXISTS（migrate() 每次全跑）。
--
-- 紅線：本檔四張表皆為觀測 artifact，任何情況下都不得被 refresh 正式路徑寫入或讀取；
-- 正式 pitch_tracking 的 schema／PK／writer 完全不受影響。

-- 每次觀測週期一列（run 粒度）：窗口參數、抓取/略過計數、對帳結果摘要。
CREATE TABLE IF NOT EXISTS cpbl.game_tm_shadow_runs (
    id                            bigserial PRIMARY KEY,
    started_at                    timestamptz NOT NULL DEFAULT now(),
    finished_at                   timestamptz,
    year                          smallint NOT NULL,
    kind_code                     text NOT NULL,
    window_days                   int NOT NULL,
    games_schedule_seen           int,   -- 窗口內賽程 shadow 觀測到的總場數（不分狀態）
    games_finished                int,   -- 官方 GameStatus=FINISHED 且落在窗口內
    games_fetched                 int,   -- 實際成功打單場 API 並寫入 shadow 逐球表的場數
    games_skipped_postponed       int,
    games_skipped_reserved        int,
    games_skipped_scheduled       int,
    games_skipped_unknown_status  int,
    requests_schedule             int,
    requests_game_api             int,
    diffs_found                   int,
    ok                            boolean,
    note                          text,
    summary                       jsonb
);

-- 賽程來源影子觀測（append-only）：保存原始 GameStatus／SkipTrackman 隨時間的快照，
-- 用來看清延期／保留賽的狀態演變（RESERVED→FINISHED、POSTPONED→…）。
CREATE TABLE IF NOT EXISTS cpbl.game_tm_shadow_schedule_obs (
    id             bigserial PRIMARY KEY,
    run_id         bigint NOT NULL REFERENCES cpbl.game_tm_shadow_runs(id),
    year           smallint NOT NULL,
    kind_code      text NOT NULL,
    game_sno       int NOT NULL,
    game_status    text NOT NULL,  -- FINISHED/SCHEDULED/POSTPONED/RESERVED/…（未知值原樣保存，不 fail-fast 丟資料）
    skip_trackman  boolean,        -- true=官方明確 skip；false 不得推論為 available（見 OFFICIAL_DATA_GAP1_RESULTS §3.4）
    pre_exe_date   timestamptz,
    visiting_score int,
    home_score     int,
    venue_abbe     text,
    observed_at    timestamptz NOT NULL DEFAULT now(),
    raw            jsonb NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_shadow_sched_game
    ON cpbl.game_tm_shadow_schedule_obs (year, kind_code, game_sno, observed_at DESC);

-- 隔離逐球 shadow 表：以單場 API 產出，欄位=cpbl_pitch_tracking._COLS 逐字保存為 jsonb row
-- （不重複硬編 44 欄型別、不與正式表耦合；比對在 Python 端用同一份 _COLS 還原）。
-- 【絕對不是】cpbl.pitch_tracking；正式 writer／查詢一律不觸碰本表。
CREATE TABLE IF NOT EXISTS cpbl.game_tm_shadow_pitch_tracking (
    year         smallint NOT NULL,
    kind_code    text     NOT NULL,
    game_sno     int      NOT NULL,
    pitcher_acnt text     NOT NULL,
    pitch_cnt    int      NOT NULL,
    row          jsonb    NOT NULL,
    run_id       bigint   NOT NULL REFERENCES cpbl.game_tm_shadow_runs(id),
    written_at   timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (year, kind_code, game_sno, pitcher_acnt, pitch_cnt)
);

-- 每次 run 的未解差異清單（append-only；「最近一次 run 的列」＝目前未解差異）。
CREATE TABLE IF NOT EXISTS cpbl.game_tm_shadow_diffs (
    id          bigserial PRIMARY KEY,
    run_id      bigint NOT NULL REFERENCES cpbl.game_tm_shadow_runs(id),
    year        smallint NOT NULL,
    kind_code   text NOT NULL,
    game_sno    int NOT NULL,
    diff_type   text NOT NULL,  -- schedule_status_mismatch / local_lag / only_shadow_pk / only_prod_pk / cell_mismatch / skip_trackman_anomaly / unknown_schedule_status
    detail      jsonb NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_shadow_diffs_run ON cpbl.game_tm_shadow_diffs (run_id);
