-- 逐場逐投手官方旗標（stats.cpbl 單場 API `Data.Game.{Visiting,Home}.Pitchers[]`）。
--
-- 背景：救援失敗原本由 `cpbl.models.pitcher_decisions.blown()` 推算（其註解寫「官方無
-- 旗標」），2026-09-23 發現官方單場 API 逐投手帶 `IsSaveFail`。且官方判定與推算規則不同：
-- 2026-A-341 官方給 3 位救援失敗，其中 2 位是「中繼」角色，而推算只把救援失敗記給最後
-- 一任投手（中途接手者記中繼失敗）。`IsSaveOK` 與既有 `games.closer_id` 同源（近 20 場
-- 20/20 一致），一併收以便對帳。
--
-- 寫入者：`cpbl_pitch_tracking.scrape_game_pitches`（與逐球同一個請求，不多打 API）。
-- 官方值是字串 '0'／'1'；解析端轉成 boolean，其餘值存 NULL（不猜）。
--
-- 只做 additive；不改動既有表。
CREATE TABLE IF NOT EXISTS cpbl.pitching_game_flags (
    year              smallint    NOT NULL,
    kind_code         text        NOT NULL,
    game_sno          int         NOT NULL,
    pitcher_acnt      text        NOT NULL,
    is_save_ok        boolean,
    is_save_fail      boolean,
    role_type         text,
    relief_point      int,
    source_fetched_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (year, kind_code, game_sno, pitcher_acnt)
);
