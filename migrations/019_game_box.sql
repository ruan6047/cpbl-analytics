-- 逐場球員 box score（每場每位選手的打擊/投球成績）。來源 box/getlive 的
-- BattingJson / PitchingJson（與 scoreboard/livelog 同一請求）。HitCnt=打數、HittingCnt=安打。
CREATE TABLE IF NOT EXISTS cpbl.batting_gamelog (
    year               smallint NOT NULL,
    kind_code          text     NOT NULL,
    game_sno           int      NOT NULL,
    hitter_acnt        text     NOT NULL,
    hitter_name        text,
    visiting_home_type text,
    uniform_no         text,
    role_type          text,    -- 先發 / 替補
    plate_appearances  int,
    at_bats            int,     -- HitCnt
    hits               int,     -- HittingCnt
    rbi                int,
    runs               int,
    singles            int,
    doubles            int,
    triples            int,
    home_runs          int,
    grand_slam         int,
    total_bases        int,
    gidp               int,
    sac_hit            int,
    sac_fly            int,
    bb                 int,
    ibb                int,
    hbp                int,
    so                 int,
    sb                 int,
    cs                 int,
    lob                int,
    errors             int,
    gw_rbi             int,
    is_mvp             boolean,
    PRIMARY KEY (year, kind_code, game_sno, hitter_acnt)
);

CREATE TABLE IF NOT EXISTS cpbl.pitching_gamelog (
    year                smallint NOT NULL,
    kind_code           text     NOT NULL,
    game_sno            int      NOT NULL,
    pitcher_acnt        text     NOT NULL,
    pitcher_name        text,
    visiting_home_type  text,
    uniform_no          text,
    role_type           text,
    game_result         text,    -- 勝/敗/中繼/救援…
    is_complete_game    boolean,
    is_shutout          boolean,
    inning_pitched_cnt  int,
    inning_pitched_div3 int,
    plate_appearances   int,
    pitch_cnt           int,
    strike_cnt          int,
    ball_cnt            int,
    hits                int,
    home_runs           int,
    sac_hit             int,
    sac_fly             int,
    bb                  int,
    ibb                 int,
    hbp                 int,
    so                  int,
    wild_pitch          int,
    balk                int,
    runs                int,
    earned_runs         int,
    relief_point        int,
    max_speed           real,    -- 該場最快球速 GameHigherSpeedPitch
    is_mvp              boolean,
    PRIMARY KEY (year, kind_code, game_sno, pitcher_acnt)
);

CREATE INDEX IF NOT EXISTS idx_bgl_hitter ON cpbl.batting_gamelog (hitter_acnt, year);
CREATE INDEX IF NOT EXISTS idx_pgl_pitcher ON cpbl.pitching_gamelog (pitcher_acnt, year);
