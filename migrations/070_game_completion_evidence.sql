-- DATA-TIE-REMEDY1：完成場的「外部證據」表（additive；不改 cpbl.games 既有欄）。
--
-- 為什麼需要外部證據：完成場判準原為 `home_score + away_score > 0`，一場真實的
-- 0:0 和局滿足 0+0=0 而被判為未完成（DATA-RULES-AUDIT1 候選 233，standings.tie
-- 1990–2024 逐年對帳 7/7 完全解釋）。此缺口自我隱蔽——爬蟲的目標場清單用同一判準，
-- 故該 5 場從未被抓，「無逐場資料」反過來讓人以為「這場沒打」。
--
-- 為什麼不能用自家欄位硬湊：`present_status = 1` 對「是否已完賽」毫無鑑別力
-- （全庫 13,480 場為 1，含 192 場未來日期）；實測會誤納 288 場 0:0 而其中僅 5 場為真。
-- 「有無逐場資料」同樣無效（5 場真和局本身也三表全空）。故判準**必須引入外部證據**。
--
-- migrate() 每次全跑，DDL 必須 additive、idempotent。
CREATE TABLE IF NOT EXISTS cpbl.game_completion_evidence (
    year            smallint NOT NULL,
    kind_code       text NOT NULL,
    game_sno        int NOT NULL,
    -- 證據種類；一場可有多種來源各一列（官方 box 取證／需求方核准）。
    --   'official_box_final'      官網 box 頁 game_detail 標記 final ＋ linescore 完整
    --   'requester_approved_tie'  需求方（領域知識）核准之 0:0 和局
    evidence_kind   text NOT NULL,
    source_url      text,
    -- 取證當下 HTML／payload 的 sha256，供覆核者比對存證檔未被竄改。
    payload_sha256  text,
    -- 官方記分板實際局數（雨裁和局如 2025/A/233 為 6；打滿延長如 2018/A/124 為 12）。
    -- 規章 §38：例行賽滿 5 局即可裁定和局，故此欄是「裁定和局是否成立」的關鍵事實。
    innings_played  smallint,
    approved_by     text,
    note            text,
    created_at      timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (year, kind_code, game_sno, evidence_kind)
);

-- 完成判準的熱路徑是「這場有沒有任一證據」，故以 (year, kind_code, game_sno) 建索引。
CREATE INDEX IF NOT EXISTS game_completion_evidence_game_idx
    ON cpbl.game_completion_evidence (year, kind_code, game_sno);

COMMENT ON TABLE cpbl.game_completion_evidence IS
    'DATA-TIE-REMEDY1：完成場外部證據。0:0 和局無法由比分自證，須以官方 box 或需求方核准佐證；無證據的 0:0 一律隔離為待判讀，不得預設納入完成場。';
