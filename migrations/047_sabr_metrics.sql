-- 047: 可靠度優先的進階指標（Phase A）
-- team_der：球隊守備效率（官方投球總計，純算術，1990+）
-- batter_wsb：打者盜壘得分價值（官方 SB/CS + 在地 run 係數，1990+）
-- catcher_runs：捕手接捕時失分（livelog 推算，2018+；RA/9 分母用 fielding_innings 的 C outs）
-- sabr_run_values：wSB 等指標的在地係數（含樣本數，供前端揭露方法）

CREATE TABLE IF NOT EXISTS cpbl.team_der (
    year        integer NOT NULL,
    team_id     text    NOT NULL,
    bf          integer,
    h           integer,
    hr          integer,
    bb          integer,
    hbp         integer,
    so          integer,
    der         numeric(5,4),
    PRIMARY KEY (year, team_id)
);

CREATE TABLE IF NOT EXISTS cpbl.batter_wsb (
    year        integer NOT NULL,
    player_id   text    NOT NULL,
    sb          integer,
    cs          integer,
    opp         integer,          -- 上壘機會 1B+BB-IBB+HBP（IBB 缺值年代視為 0）
    wsb         numeric(6,2),
    PRIMARY KEY (year, player_id)
);

CREATE TABLE IF NOT EXISTS cpbl.catcher_runs (
    year        integer NOT NULL,
    kind_code   text    NOT NULL DEFAULT 'A',
    player_id   text    NOT NULL,
    runs        integer NOT NULL,  -- 接捕時失分（含非自責，RA 非 ERA）
    games       integer,
    PRIMARY KEY (year, kind_code, player_id)
);

CREATE TABLE IF NOT EXISTS cpbl.sabr_run_values (
    span        text    NOT NULL,  -- 例 '2018-2025'
    kind_code   text    NOT NULL DEFAULT 'A',
    metric      text    NOT NULL,  -- 'run_sb' / 'run_cs'
    value       numeric(6,4) NOT NULL,
    samples     integer,
    PRIMARY KEY (span, kind_code, metric)
);
