-- #357 B1：livelog 同一事件號多筆時，主列以外的同號列存這裡（附加表）。
--
-- 背景：016 為 `game_livelog` 註明「main_event_no：場內事件序（唯一）」——這個前提**不成立**。
-- www `getlive` 的 LiveLogJson 每場最後一個事件號下，實際打席／事件之後會再跟一筆同號的
-- 「比賽結束」或「主審裁定比賽結束」標記（2026 全 608 場皆此形狀，#357 研究 2）。
-- `game_livelog` 主鍵不變（一號一列＝主列：原文第一筆非結束標記列），其餘同號列寫進本表，
-- 鍵加上 `dup_seq`（該列在原文同號組中的位置，0 起算；主列佔用的位置不出現在本表）。
-- ⛔ 不改 016；⛔ 不得從主表沒有標記列推出「該場原文沒有結束標記」——標記在本表。
--
-- 寫入：`cpbl_gamelog._write_livelog` 每場先刪後寫、與主表 UPSERT 同一交易。
-- 讀取：`/api/v1/games/{sno}/live` 依 (main_event_no::bigint, dup_seq) 合併兩表。
-- 同步：`scripts/refresh-cpbl-prod.sh` 整表 TRUNCATE＋全量重灌（本機衍生、正式站無獨立 writer）。

CREATE TABLE IF NOT EXISTS cpbl.game_livelog_extra (
    year                smallint NOT NULL,
    kind_code           text     NOT NULL,
    game_sno            int      NOT NULL,
    main_event_no       text     NOT NULL,
    dup_seq             int      NOT NULL,  -- 原文同號組內位置（0 起算）
    pkno                text,               -- 原文 Pkno（只供追溯，不入鍵：2018–2025 唯一性未證）
    inning_seq          int,
    visiting_home_type  text,
    batting_order       int,
    out_cnt             int,
    ball_cnt            int,
    strike_cnt          int,
    pitch_cnt           int,
    content             text,
    action_name         text,
    batting_action_name text,
    defend_station_code text,
    hitter_acnt         text,
    hitter_name         text,
    pitcher_acnt        text,
    pitcher_name        text,
    catcher_acnt        text,
    catcher_name        text,
    first_base          text,
    second_base         text,
    third_base          text,
    is_strike           boolean,
    is_ball             boolean,
    is_score            boolean,
    is_change_player    boolean,
    is_special_event    boolean,
    visiting_score      int,
    home_score          int,
    PRIMARY KEY (year, kind_code, game_sno, main_event_no, dup_seq)
);
