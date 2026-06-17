-- 逐球 TrackMan 追蹤資料（stats.cpbl 每球一筆）。自投手頁解析（每球以投手視角唯一）。
-- pitch_cnt 為該場該投手累積投球數，(game, pitcher, pitch_cnt) 唯一。
CREATE TABLE IF NOT EXISTS cpbl.pitch_tracking (
    year              smallint NOT NULL,
    kind_code         text     NOT NULL,
    game_sno          int      NOT NULL,
    pitcher_acnt      text     NOT NULL,
    pitch_cnt         int      NOT NULL,
    pitcher_name      text,
    hitter_acnt       text,
    hitter_name       text,
    inning_seq        int,
    ball_cnt          int,
    strike_cnt        int,
    out_cnt           int,
    batting_order     int,
    content           text,
    pitch_call        text,    -- StrikeCalled/BallCalled/StrikeSwinging/InPlay…
    auto_pitch_type   text,    -- 系統判定球種
    tagged_pitch_type text,    -- 人工標記球種
    rel_speed         real,    -- 球速 km/h
    spin_rate         real,    -- 轉速 rpm
    rel_side          real,    -- 放球點水平
    rel_height        real,    -- 放球點高度
    extension         real,    -- 延伸
    zone_speed        real,    -- 進壘速度
    plate_loc_side    real,    -- 進壘點水平
    plate_loc_height  real,    -- 進壘點高度
    hit_exit_speed    real,    -- 擊球初速 km/h
    hit_launch_angle  real,    -- 擊球仰角
    hit_direction     real,    -- 擊球方向
    hit_distance      real,    -- 落點距離
    hit_hang_time     real,    -- 滯空時間
    PRIMARY KEY (year, kind_code, game_sno, pitcher_acnt, pitch_cnt)
);

CREATE INDEX IF NOT EXISTS idx_pitch_pitcher ON cpbl.pitch_tracking (pitcher_acnt, year);
CREATE INDEX IF NOT EXISTS idx_pitch_hitter ON cpbl.pitch_tracking (hitter_acnt, year);
CREATE INDEX IF NOT EXISTS idx_pitch_type ON cpbl.pitch_tracking (auto_pitch_type);
