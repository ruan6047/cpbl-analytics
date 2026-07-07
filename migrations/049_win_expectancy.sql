-- 049: 逐打席勝率（WP）打底
-- run_dist：半局剩餘得分「分布」P(k | 上/下半局,壘位,出局)——上/下分開估，
--           主場優勢（主隊下半局得分較強）從資料自然浮現，不做人工參數
-- win_expectancy：半局邊界勝率表（由 run_dist DP 倒推；12 局和局、9 局後走查規則）
-- 全部自算（REBAS 僅對照）；詳 models/winprob.py

CREATE TABLE IF NOT EXISTS cpbl.run_dist (
    span        text    NOT NULL,
    kind_code   text    NOT NULL DEFAULT 'A',
    side        text    NOT NULL,              -- '1'=上半局(客隊進攻) '2'=下半局(主隊進攻)
    bases       text    NOT NULL,
    outs        integer NOT NULL,
    k           integer NOT NULL,              -- 再得 k 分（6=6+）
    p           numeric(7,5) NOT NULL,
    samples     integer NOT NULL,              -- 該 (side,bases,outs) 狀態總樣本
    PRIMARY KEY (span, kind_code, side, bases, outs, k)
);

CREATE TABLE IF NOT EXISTS cpbl.win_expectancy (
    span        text    NOT NULL,
    kind_code   text    NOT NULL DEFAULT 'A',
    inning      integer NOT NULL,              -- 1..12
    half        text    NOT NULL,              -- '1'=上半局開始前 '2'=下半局開始前
    diff        integer NOT NULL,              -- 主隊視角分差（clip ±15）
    p_win       numeric(7,5) NOT NULL,         -- 主隊勝
    p_tie       numeric(7,5) NOT NULL,         -- 12 局和
    PRIMARY KEY (span, kind_code, inning, half, diff)
);
