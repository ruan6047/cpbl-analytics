-- 進階數據加軍別：stats.cpbl 的 /api/proxy/v1/leaderboards/* 支援 gameKind=A/D、
-- searchType=batter/pitcher。先前只抓一軍打者(SSR)。加 kind_code 以存二軍 + 投手 rich 進階。
-- 冪等：欄位 IF NOT EXISTS；PK DROP IF EXISTS + ADD 重建（每次 migrate 全跑亦安全）。

ALTER TABLE cpbl.advanced_stats ADD COLUMN IF NOT EXISTS kind_code text NOT NULL DEFAULT 'A';

ALTER TABLE cpbl.advanced_stats DROP CONSTRAINT IF EXISTS advanced_stats_pkey;
ALTER TABLE cpbl.advanced_stats ADD CONSTRAINT advanced_stats_pkey
    PRIMARY KEY (year, kind_code, acnt, role);

-- advanced_flat 維持一軍語意：欄位與 023 完全相同（不新增 kind_code 欄，否則 023 的
-- CREATE OR REPLACE 每次 migrate 會因無法砍欄而失敗），僅加 WHERE kind_code='A' 過濾二軍。
-- 二軍/季後進階分析請直接查 advanced_stats（有 kind_code 欄）。
CREATE OR REPLACE VIEW cpbl.advanced_flat AS
SELECT
  year, acnt, role,
  (metrics->>'pa')::int            AS pa,
  (metrics->>'woba')::numeric      AS woba,
  (metrics->>'ba')::numeric        AS ba,
  (metrics->>'obp')::numeric       AS obp,
  (metrics->>'slg')::numeric       AS slg,
  (metrics->>'iso')::numeric       AS iso,
  (metrics->>'bbp')::numeric       AS bb_pct,
  (metrics->>'kp')::numeric        AS k_pct,
  (metrics->>'chasep')::numeric    AS chase_pct,
  (metrics->>'whiffp')::numeric    AS whiff_pct,
  (metrics->>'ev')::numeric        AS ev_avg,
  (metrics->>'evMax')::numeric     AS ev_max,
  (metrics->>'ev50Th')::numeric    AS ev_50th,
  (metrics->>'ev90Th')::numeric    AS ev_90th,
  (metrics->>'maxEv')::numeric     AS max_ev,
  (metrics->>'hardHitp')::numeric  AS hardhit_pct,
  (metrics->>'hardHit')::int       AS hardhit_cnt,
  (metrics->>'barrels')::int       AS barrels,
  (metrics->>'brlp')::numeric      AS barrel_pct,
  (metrics->>'brlsBbEp')::numeric  AS barrels_per_bbe,
  (metrics->>'brlsPAp')::numeric   AS barrels_per_pa,
  (metrics->>'laAvg')::numeric     AS la_avg,
  (metrics->>'distanceAvgHr')::numeric AS dist_avg_hr,
  (metrics->>'distanceMax')::numeric   AS dist_max,
  (metrics->>'bbe')::int           AS bbe,
  (metrics->>'gbp')::numeric       AS gb_pct,
  (metrics->>'fbp')::numeric       AS fb_pct,
  (metrics->>'ldp')::numeric       AS ld_pct,
  (metrics->>'airp')::numeric      AS air_pct,
  (metrics->>'pup')::numeric       AS popup_pct,
  (metrics->>'pullp')::numeric     AS pull_pct,
  (metrics->>'straightp')::numeric AS center_pct,
  (metrics->>'oppop')::numeric     AS oppo_pct,
  (metrics->>'kph')::numeric       AS velo_avg,
  (metrics->>'kphMax')::numeric    AS velo_max,
  (metrics->>'spinRate')::numeric  AS spin_avg,
  (metrics->>'spinRateMax')::numeric AS spin_max,
  metrics
FROM cpbl.advanced_stats WHERE kind_code = 'A';
