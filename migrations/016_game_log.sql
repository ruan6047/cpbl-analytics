-- 每場賽況：逐局比分（scoreboard）+ 逐打席事件流（live log）。
-- 來源 box/getlive 的 ScoreboardJson / LiveLogJson。冪等 UPSERT。

-- 逐局比分（每隊每局）
CREATE TABLE IF NOT EXISTS cpbl.game_scoreboard (
    year               smallint NOT NULL,
    kind_code          text     NOT NULL,
    game_sno           int      NOT NULL,
    team_no            text     NOT NULL,
    inning_seq         int      NOT NULL,
    visiting_home_type text,                -- 1=客隊 2=主隊
    team_name          text,
    score_cnt          int,                 -- 該局得分
    hitting_cnt        int,                 -- 該局安打
    error_cnt          int,                 -- 該局失誤
    PRIMARY KEY (year, kind_code, game_sno, team_no, inning_seq)
);

-- 逐打席/逐事件（一筆＝一個事件，含即時局數/出局/球數/壘況/比分/中文描述）
CREATE TABLE IF NOT EXISTS cpbl.game_livelog (
    year                smallint NOT NULL,
    kind_code           text     NOT NULL,
    game_sno            int      NOT NULL,
    main_event_no       text     NOT NULL,  -- 場內事件序（唯一）
    inning_seq          int,
    visiting_home_type  text,               -- 1=上半(客) 2=下半(主)
    batting_order       int,
    out_cnt             int,
    ball_cnt            int,
    strike_cnt          int,
    pitch_cnt           int,
    content             text,               -- 中文事件描述
    action_name         text,
    batting_action_name text,
    defend_station_code text,
    hitter_acnt         text,
    hitter_name         text,
    pitcher_acnt        text,
    pitcher_name        text,
    catcher_acnt        text,
    catcher_name        text,
    first_base          text,               -- 壘上跑者（acnt 或空）
    second_base         text,
    third_base          text,
    is_strike           boolean,
    is_ball             boolean,
    is_score            boolean,
    is_change_player    boolean,
    is_special_event    boolean,
    visiting_score      int,                -- 該事件後即時比分
    home_score          int,
    PRIMARY KEY (year, kind_code, game_sno, main_event_no)
);

CREATE INDEX IF NOT EXISTS idx_scoreboard_game ON cpbl.game_scoreboard (year, kind_code, game_sno);
CREATE INDEX IF NOT EXISTS idx_livelog_game ON cpbl.game_livelog (year, kind_code, game_sno, inning_seq);
