-- GAME-RECAP-PA1-EXPAND1：canonical 打席 [plate appearance / PA] 物化基礎設施（additive expand）。
--
-- 契約基線：docs/design/GAME-RECAP-PA1_CONTRACT.md §「資料模型」/§「PA 狀態機與穩定 ID」/§「逐球 mapping 與 availability」。
-- 前置：GAME-RECAP-PA1-TAXONOMY1（merge c58dd75）版本化 transition taxonomy [taxonomy_version=1.0.0]；
--       消費檔 docs/design/pa_transition_taxonomy.v1.json。本 schema 必須能承載該 state machine 輸出。
--
-- 本卡邊界（紅線）：
--   * 只做 additive expand DDL；全部 IF NOT EXISTS，migrate() 每次全跑須冪等 [idempotent]。
--   * 不改寫既有 migration；不建 builder、不回填、不新增 API/前端（那是 BUILD1）。
--   * 不儲存 credentials；只保留來源 revision／parser／taxonomy version 留痕。
--
-- 與既有物件關係：
--   * 既有 cpbl.game_source_revisions（061，STATUS-EXPAND1）記錄逐來源 refresh 狀態，
--     無 sha256/parser_version/max_source_key，語意為「刷新可追溯」；
--     本卡的 game_recap_source_revisions 是 PA build 綁定的 immutable manifest（hash+parser+max key），
--     兩者刻意分離、不合併（契約明列 game_recap_ 前綴物件）。
--   * 不對 mutable 來源表（game_livelog / pitch_tracking）建硬 FK：來源可重爬替換，
--     provenance 一律經 source_revision 留痕（契約不變量 #2/#3）。
--
-- 關鍵設計決策（供跨家族查核者複核）：
--   * pa_id 為穩定 deterministic UUIDv5（seed = game key + start event + event_order_version），
--     跨 build 相同故「非唯一」，僅索引；PA 實體 FK 目標為代理鍵 pa_row_id（乾淨引用完整性）。
--   * game_recap_builds 以 partial unique index 保證每場至多一個 state='published'（current canonical；
--     reconciliation 須在同交易 demote 舊 build 再發布新 build → atomic swap，不 delete-and-reinsert）。
--   * game_pa_pitch_mappings 以 (source_revision_id + pitch local key) UNIQUE 保證
--     「同一版本每顆球至多綁定一個 PA」（契約紅燈：每顆球最多一個 PA）；pitch local key 對齊
--     pitch_tracking PK (year,kind_code,game_sno,pitcher_acnt,pitch_cnt)，該表逐球唯一，
--     與 game_livelog.pitch_cnt 的逐列非唯一（TAXONOMY 紅燈 D）是不同層級。

-- =====================================================================================
-- 1) 來源 revision manifest：每次成功抓取 livelog／tracking 的 immutable 指紋
-- =====================================================================================
CREATE TABLE IF NOT EXISTS cpbl.game_recap_source_revisions (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    year            smallint NOT NULL,
    kind_code       text     NOT NULL,
    game_sno        int      NOT NULL,
    source_kind     text     NOT NULL CHECK (source_kind IN ('livelog', 'tracking')),
    source_sha256   text     NOT NULL CHECK (source_sha256 ~* '^[0-9a-f]{64}$'),  -- 來源 payload 內容雜湊
    parser_version  text     NOT NULL,                                            -- 解析器版本留痕
    row_count       int      NOT NULL DEFAULT 0 CHECK (row_count >= 0),
    max_source_key  text,                     -- 該來源最大來源鍵（livelog=max main_event_no；tracking=max pitch key）
    fetched_at      timestamptz NOT NULL DEFAULT now(),
    -- 唯一鍵：game key + source kind + 內容 hash（同內容重抓 → 同一 manifest）
    UNIQUE (year, kind_code, game_sno, source_kind, source_sha256)
);

CREATE INDEX IF NOT EXISTS idx_game_recap_source_rev_latest
    ON cpbl.game_recap_source_revisions
       (year, kind_code, game_sno, source_kind, fetched_at DESC);

-- =====================================================================================
-- 2) build：每次物化 PA 的紀錄；綁定 livelog／tracking revision + builder/taxonomy version
--    API 僅讀 state='published'（契約不變量 #5）。
-- =====================================================================================
CREATE TABLE IF NOT EXISTS cpbl.game_recap_builds (
    build_id             uuid PRIMARY KEY,     -- builder 供給（非 deterministic；每 build 一個）
    year                 smallint NOT NULL,
    kind_code            text     NOT NULL,
    game_sno             int      NOT NULL,
    livelog_revision_id  bigint   NOT NULL REFERENCES cpbl.game_recap_source_revisions (id),
    tracking_revision_id bigint   REFERENCES cpbl.game_recap_source_revisions (id),  -- 可為 NULL：無逐球來源
    builder_version      text     NOT NULL,
    taxonomy_version     text     NOT NULL,    -- builder 必須 pin（TAXONOMY §9）
    state                text     NOT NULL DEFAULT 'building'
                         CHECK (state IN ('building', 'published', 'superseded',
                                          'reconciliation_required', 'failed')),
    validation_summary   jsonb    NOT NULL DEFAULT '{}'::jsonb,  -- 每 scope：box/candidate/ready/unreliable/mapped/failed…
    built_at             timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_game_recap_builds_game
    ON cpbl.game_recap_builds (year, kind_code, game_sno, built_at DESC);

-- 每場至多一個已發布 build（current canonical）
CREATE UNIQUE INDEX IF NOT EXISTS uq_game_recap_builds_one_published
    ON cpbl.game_recap_builds (year, kind_code, game_sno)
    WHERE state = 'published';

-- =====================================================================================
-- 3) 物化 PA：per-build 快照。pa_id 為跨 build 穩定身分（索引、非唯一）。
--    state != 'ready' 不可供 WP／精確逐球 UI 使用（契約）。
--    state 對應 TAXONOMY island_classes：
--      ready        ← completed_pa 且終結可信
--      unreliable   ← unknown_action / uncaught_third_strike 未由計數確認
--      truncated    ← truncated_fragment（空 action 有投球）
--      non_pa       ← non_pa_tiebreak / non_pa_running_fragment（context，不進 PA 分母）
--      reconciliation_required ← 跨 revision 成員/身分/終點改變，待對帳
-- =====================================================================================
CREATE TABLE IF NOT EXISTS cpbl.game_plate_appearances (
    pa_row_id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,  -- 代理鍵：events/mappings FK 目標
    pa_id                 uuid     NOT NULL,   -- 穩定 deterministic UUIDv5（跨 build 相同）
    build_id              uuid     NOT NULL REFERENCES cpbl.game_recap_builds (build_id) ON DELETE CASCADE,
    year                  smallint NOT NULL,
    kind_code             text     NOT NULL,
    game_sno              int      NOT NULL,
    pa_index              int      NOT NULL CHECK (pa_index >= 0),  -- 場內 PA 全序（0-based）
    start_event_no        text     NOT NULL,   -- game_livelog.main_event_no（PA 起始事件）
    end_event_no          text,                -- 終結事件；truncated/unreliable 可 NULL
    event_order_version   text     NOT NULL,   -- 事件全序版本（UUIDv5 seed 一部分）
    hitter_acnt           text,                -- 打者（island 內固定）
    start_pitcher_acnt    text,                -- 打席起始投手
    end_pitcher_acnt      text,                -- 打席終結投手（打席中換投時不同）
    pre_state             jsonb    NOT NULL DEFAULT '{}'::jsonb,  -- 套用該 PA 前 out/壘況/比分
    post_state            jsonb    NOT NULL DEFAULT '{}'::jsonb,  -- 套用該 PA 後
    result_action         text,                -- 終結 action_name（taxonomy pa_terminal）；unreliable/truncated 可 NULL
    outcome_family        text,                -- taxonomy 指派家族（pinned taxonomy_version 下）
    state                 text     NOT NULL
                          CHECK (state IN ('ready', 'unreliable', 'truncated',
                                           'non_pa', 'reconciliation_required')),
    tracking_availability text     CHECK (tracking_availability IN
                                          ('available', 'advanced_pending', 'no_equipment',
                                           'source_missing', 'mapping_failed', 'source_error')),
    reconciliation_reason text,                -- 機器可讀對帳/降級原因
    built_at              timestamptz NOT NULL DEFAULT now(),
    -- 唯一鍵：game key + build + pa_index
    UNIQUE (year, kind_code, game_sno, build_id, pa_index)
);

CREATE INDEX IF NOT EXISTS idx_game_pa_start_event
    ON cpbl.game_plate_appearances (year, kind_code, game_sno, start_event_no);

CREATE INDEX IF NOT EXISTS idx_game_pa_pa_id
    ON cpbl.game_plate_appearances (pa_id);

-- =====================================================================================
-- 4) PA 成員事件：保留全序與每事件 fingerprint（reconciliation 比對用）
-- =====================================================================================
CREATE TABLE IF NOT EXISTS cpbl.game_pa_events (
    id                bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    pa_row_id         bigint   NOT NULL REFERENCES cpbl.game_plate_appearances (pa_row_id) ON DELETE CASCADE,
    pa_id             uuid     NOT NULL,   -- 去正規化 stable id（便於對帳查詢；一致性由 builder 維持）
    year              smallint NOT NULL,
    kind_code         text     NOT NULL,
    game_sno          int      NOT NULL,
    event_no          text     NOT NULL,   -- game_livelog.main_event_no
    event_position    int      NOT NULL CHECK (event_position >= 0),  -- PA 內全序位置
    event_fingerprint text     NOT NULL,   -- 事件顯著欄位雜湊（晚到/修正比對）
    UNIQUE (pa_row_id, event_position),
    UNIQUE (pa_row_id, event_no)           -- 一事件於一 PA 內至多一次（防重複成員）
);

CREATE INDEX IF NOT EXISTS idx_game_pa_events_game_event
    ON cpbl.game_pa_events (year, kind_code, game_sno, event_no);

-- =====================================================================================
-- 5) 逐球 mapping：PA ↔ pitch_tracking 逐球（pitch local key）。
--    只在候選唯一且順序一致時標 mapped；否則 failed（契約，不傳空陣列假裝無球）。
-- =====================================================================================
CREATE TABLE IF NOT EXISTS cpbl.game_pa_pitch_mappings (
    id                 bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    pa_row_id          bigint   NOT NULL REFERENCES cpbl.game_plate_appearances (pa_row_id) ON DELETE CASCADE,
    pa_id              uuid     NOT NULL,
    source_revision_id bigint   NOT NULL REFERENCES cpbl.game_recap_source_revisions (id),  -- 對應 tracking revision
    year               smallint NOT NULL,
    kind_code          text     NOT NULL,
    game_sno           int      NOT NULL,
    pitcher_acnt       text     NOT NULL,   -- pitch local key（對齊 pitch_tracking PK）
    pitch_cnt          int      NOT NULL,
    pitch_position     int      NOT NULL CHECK (pitch_position >= 0),  -- PA 內逐球序（逐投手還原）
    mapping_state      text     NOT NULL CHECK (mapping_state IN ('mapped', 'failed')),
    mapping_reason     text,                -- 較細機器原因（ambiguous_candidate/order_regression/source_revision_mismatch…）
    -- 同一版本每顆球至多綁定一個 PA（契約紅燈：每顆球最多一個 PA）
    UNIQUE (source_revision_id, year, kind_code, game_sno, pitcher_acnt, pitch_cnt)
);

CREATE INDEX IF NOT EXISTS idx_game_pa_pitch_map_pa
    ON cpbl.game_pa_pitch_mappings (pa_row_id, pitch_position);
