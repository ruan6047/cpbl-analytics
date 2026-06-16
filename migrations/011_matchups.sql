-- 投打對決 [batter-vs-pitcher matchup]：官網選手頁「投打對決」(/team/getfightingscore)。
-- 粒度為「打者 × 投手」逐人對戰彙總（非逐打席）；含進階球種比例 (Swing/Whiff/GB/LD/FB)。
-- 注意官網欄位語義：HitCnt=打數(AB)、HittingCnt=安打(H)（已實測 H/AB=Avg 驗證）。
CREATE TABLE IF NOT EXISTS cpbl.batter_pitcher_matchups (
    year                  smallint NOT NULL,
    kind_code             text     NOT NULL,
    hitter_acnt           text     NOT NULL,
    pitcher_acnt          text     NOT NULL,
    hitter_name           text,
    pitcher_name          text,
    hitter_team_no        text,
    pitcher_team_no       text,
    plate_appearances     int,
    at_bats               int,   -- HitCnt（打數）
    hits                  int,   -- HittingCnt（安打）
    rbi                   int,
    singles               int,
    doubles               int,
    triples               int,
    home_runs             int,
    total_bases           int,
    avg                   real,
    obp                   real,
    slg                   real,
    ops                   real,
    sac_hit               int,
    sac_fly               int,
    bb                    int,
    ibb                   int,
    hbp                   int,
    so                    int,
    ground_out            int,
    fly_out               int,
    goao                  real,
    strike_pct            real,
    ball_pct              real,
    swing_pct             real,
    first_pitch_swing_pct real,
    whiff_pct             real,
    gb_pct                real,
    ld_pct                real,
    fb_pct                real,
    updated_at            timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (year, kind_code, hitter_acnt, pitcher_acnt)
);

CREATE INDEX IF NOT EXISTS idx_matchups_pitcher ON cpbl.batter_pitcher_matchups (pitcher_acnt, year);
CREATE INDEX IF NOT EXISTS idx_matchups_hitter  ON cpbl.batter_pitcher_matchups (hitter_acnt, year);
