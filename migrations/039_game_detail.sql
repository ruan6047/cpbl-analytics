-- 每場賽況細節：觀眾人數 + 裁判 + 比賽時長（官網 box 頁 HTML 的「比賽時間/觀眾人數」「裁判」區）。
-- 目前前端未用，先爬存備後續(觀眾趨勢/主審好球帶傾向等)。冪等 IF NOT EXISTS。
CREATE TABLE IF NOT EXISTS cpbl.game_detail (
    year              int  NOT NULL,
    kind_code         text NOT NULL,
    game_sno          int  NOT NULL,
    attendance        int,
    game_time         text,          -- 比賽時長 HH:MM
    head_umpire       text,          -- 主審
    first_umpire      text,          -- 一壘審
    second_umpire     text,          -- 二壘審
    third_umpire      text,          -- 三壘審
    left_umpire       text,          -- 左外野審(季後才有)
    right_umpire      text,          -- 右外野審(季後才有)
    updated_at        timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (year, kind_code, game_sno)
);
