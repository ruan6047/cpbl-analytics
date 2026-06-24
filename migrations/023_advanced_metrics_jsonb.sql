-- 進階數據改彈性 schema：metrics jsonb 整包存官方所有進階指標（~60 欄）。
-- 官方未來開放更多指標時自動入庫、免 migration（見 ingest/cpbl_advanced.py 的 anchor 合併）。
-- 保留原 typed 欄位向後相容；分析/ML 走下方 advanced_flat view（typed、好算）。
ALTER TABLE cpbl.advanced_stats ADD COLUMN IF NOT EXISTS metrics jsonb;

-- jsonb containment / 存在性查詢用 GIN 索引
CREATE INDEX IF NOT EXISTS idx_advanced_metrics_gin ON cpbl.advanced_stats USING gin (metrics);

-- 攤平 view：把常用進階指標從 metrics 抽成 typed 欄，分析/ML 直接用、零資料重複。
-- 新增常用指標只要在此加一行（無資料 migration）；熱鍵範圍篩選再對 (metrics->>'key') 建表達式索引。
CREATE OR REPLACE VIEW cpbl.advanced_flat AS
SELECT
  year, acnt, role,
  (metrics->>'pa')::int            AS pa,
  -- 進階率
  (metrics->>'woba')::numeric      AS woba,
  (metrics->>'ba')::numeric        AS ba,
  (metrics->>'obp')::numeric       AS obp,
  (metrics->>'slg')::numeric       AS slg,
  (metrics->>'iso')::numeric       AS iso,
  (metrics->>'bbp')::numeric       AS bb_pct,
  (metrics->>'kp')::numeric        AS k_pct,
  (metrics->>'chasep')::numeric    AS chase_pct,
  (metrics->>'whiffp')::numeric    AS whiff_pct,
  -- 擊球品質
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
  -- 彈道分布
  (metrics->>'gbp')::numeric       AS gb_pct,
  (metrics->>'fbp')::numeric       AS fb_pct,
  (metrics->>'ldp')::numeric       AS ld_pct,
  (metrics->>'airp')::numeric      AS air_pct,
  (metrics->>'pup')::numeric       AS popup_pct,
  -- 拉打方向
  (metrics->>'pullp')::numeric     AS pull_pct,
  (metrics->>'straightp')::numeric AS center_pct,
  (metrics->>'oppop')::numeric     AS oppo_pct,
  -- 球質（投手）
  (metrics->>'kph')::numeric       AS velo_avg,
  (metrics->>'kphMax')::numeric    AS velo_max,
  (metrics->>'spinRate')::numeric  AS spin_avg,
  (metrics->>'spinRateMax')::numeric AS spin_max,
  metrics
FROM cpbl.advanced_stats;
