-- 選手特性（livelog 2018+ 推算，cpbl-build-sabr 順帶重建）：
-- 打席耗球 P/PA、滾飛比 GO/FO、兩好球後表現、進壘方向傾向（拉/中/推需 join players.bats）。
-- PA 切界＝連續同打者 island（見記憶 livelog-data-semantics）；方向由結果字彙守位字首推得。
CREATE TABLE IF NOT EXISTS cpbl.batter_traits (
    year          int  NOT NULL,
    kind_code     text NOT NULL,
    player_id     text NOT NULL,
    pa            int  NOT NULL,           -- 打席數（island 法）
    p_pa          double precision,        -- 平均耗球
    go            int, fo int,             -- 滾地/飛球出局型態（結果字彙 滾/飛）
    dir_left      int, dir_center int, dir_right int,  -- 擊球方向（三游左/中/一二右）
    two_strike_pa int,                     -- 陷入兩好球的打席
    two_strike_k  int,                     -- 其中被三振
    two_strike_hit int,                    -- 其中敲安（含全壘打）
    PRIMARY KEY (year, kind_code, player_id)
);
CREATE TABLE IF NOT EXISTS cpbl.pitcher_traits (
    year          int  NOT NULL,
    kind_code     text NOT NULL,
    player_id     text NOT NULL,
    bf            int  NOT NULL,           -- 面對打席
    p_pa          double precision,        -- 每打席耗球
    go            int, fo int,             -- 製造滾地/飛球
    two_strike_pa int, two_strike_k int,   -- 兩好球後解決能力
    PRIMARY KEY (year, kind_code, player_id)
);
