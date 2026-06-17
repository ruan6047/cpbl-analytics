-- 官方進階數據（stats.cpbl.com.tw，TrackMan/Statcast 風格）彙總 + 官方 PR 百分位。
-- 打者=進攻數值；投手=被打數值（PR 已依角色定向，皆「越高越好」）。
-- 來源為 Next.js RSC 內嵌資料，解析較脆弱；欄位對齊官方鍵（barrel% PR 官方鍵為 prlpPr）。
CREATE TABLE IF NOT EXISTS cpbl.advanced_stats (
    year         smallint NOT NULL,
    acnt         text     NOT NULL,
    role         text     NOT NULL,   -- batting / pitching
    pa           int,
    woba         real, woba_pr        int,
    ba           real, ba_pr          int,
    slg          real, slg_pr         int,
    iso          real, iso_pr         int,
    obp          real, obp_pr         int,
    brl          int,  brl_pr         int,   -- 出色擊球數 Barrels
    brlp         real, brlp_pr        int,   -- 出色擊球率 Barrel%
    ev           real, ev_pr          int,   -- 平均擊球初速 (km/h)
    max_ev       real, max_ev_pr      int,   -- 最高擊球初速
    hardhitp     real, hardhitp_pr    int,   -- 強擊球率
    kp           real, kp_pr          int,   -- 三振率
    bbp          real, bbp_pr         int,   -- 保送率
    whiffp       real, whiffp_pr      int,   -- 揮空率
    chasep       real, chasep_pr      int,   -- 追打率
    updated_at   timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (year, acnt, role)
);
