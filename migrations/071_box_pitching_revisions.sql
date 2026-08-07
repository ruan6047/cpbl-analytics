-- DATA-BOX-REVISION-SNAPSHOT1：官方 box 逐場逐投手 append-only 快照。
--
-- 背景：cpbl.pitching_gamelog 只存最新一次 UPSERT 後的值，無版本歷史。
-- ML-PITCHER-ER-REBUILD1（#107）發現「官方賽後修正判決」與「我方 livelog 漏記」
-- 在單一快照上預測完全相同的觀測、永遠分不開。本表從上線日起，每次抓 box 都
-- 存一份逐投手快照（內容雜湊去重、append-only），讓「賽後被改過幾次/改了什麼」
-- 從不可證偽變成可量測。
--
-- 粒度：逐投手列（非整場一個 blob）。理由：pitching_gamelog 的自然鍵就是
-- (year, kind_code, game_sno, pitcher_acnt)；逐投手雜湊去重可以精準指出「哪個
-- 投手的哪次抓取變了」，而不會因同場其他投手列不變動的重複抓取誤判整場都變了。
--
-- 只做 additive；不改動既有表（pitching_gamelog / game_source_revisions）。
CREATE TABLE IF NOT EXISTS cpbl.box_pitching_revisions (
    id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    year                smallint NOT NULL,
    kind_code           text     NOT NULL,
    game_sno            int      NOT NULL,
    pitcher_acnt        text     NOT NULL,
    -- 驗收條件點名的三個欄位：局數（兩種官方表示法）+ 失分 + 自責分。
    inning_pitched_cnt  int,
    inning_pitched_div3 int,
    runs                int,
    earned_runs         int,
    -- 內容雜湊：對該投手當次抓到的完整 PitchingJson 列做 canonical hash（與
    -- game_source_revisions.canonical_source_version 同一手法），確保「內容
    -- 未變不新增列」且能回答「改了什麼」（raw_payload 存完整內容，不只雜湊）。
    content_hash        text     NOT NULL,
    raw_payload         jsonb    NOT NULL,
    fetched_at          timestamptz NOT NULL DEFAULT now(),
    last_seen_at        timestamptz NOT NULL DEFAULT now(),
    seen_count          int      NOT NULL DEFAULT 1 CHECK (seen_count > 0),
    UNIQUE (year, kind_code, game_sno, pitcher_acnt, content_hash)
);

-- 熱路徑：某場某投手的完整版本歷史（依抓取時間排序）。
CREATE INDEX IF NOT EXISTS idx_box_pitching_revisions_pitcher
    ON cpbl.box_pitching_revisions
       (year, kind_code, game_sno, pitcher_acnt, fetched_at);

COMMENT ON TABLE cpbl.box_pitching_revisions IS
    'DATA-BOX-REVISION-SNAPSHOT1：官方 box 逐場逐投手 append-only 快照（內容雜湊去重）。'
    '只從上線日起累積；2018-2026 既有歷史場次無回溯快照，不能回答「這些場過去被改過嗎」。';
