-- INGEST-ADV-RECONCILE1：進階快照讀路徑收斂（read gating）。
-- additive／冪等；不 DROP、不 TRUNCATE、不改既有列。晉升機制與資料修復在 ingest 層。
--
-- gating 語意（advanced_stats scope=(year,kind_code,'player_stats',role)）：
--   一列可見 iff
--     (該 scope 尚無 promoted pointer) AND source_run_id IS NULL   -- reconcile 前的 legacy 未管理列
--     OR (該 scope 有 pointer) AND source_run_id = pointer.current_run_id
--   → 晉升前行為不變；晉升後只讀最後成功的完整快照，半晉升／污染殘列不外露。

CREATE INDEX IF NOT EXISTS idx_advanced_stats_scope_run
    ON cpbl.advanced_stats (year, kind_code, role, source_run_id);

-- advanced_flat 欄位與 038 完全相同（CREATE OR REPLACE 需同名同序），僅在 WHERE 疊加 gating。
-- 拆出球種維度後 velo_avg/velo_max/spin_avg/spin_max 於新快照為 NULL（來源已移入
-- advanced_pitch_type_stats）；欄位保留以維持 view 形狀穩定。
CREATE OR REPLACE VIEW cpbl.advanced_flat AS
SELECT
  a.year, a.acnt, a.role,
  (a.metrics->>'pa')::int            AS pa,
  (a.metrics->>'woba')::numeric      AS woba,
  (a.metrics->>'ba')::numeric        AS ba,
  (a.metrics->>'obp')::numeric       AS obp,
  (a.metrics->>'slg')::numeric       AS slg,
  (a.metrics->>'iso')::numeric       AS iso,
  (a.metrics->>'bbp')::numeric       AS bb_pct,
  (a.metrics->>'kp')::numeric        AS k_pct,
  (a.metrics->>'chasep')::numeric    AS chase_pct,
  (a.metrics->>'whiffp')::numeric    AS whiff_pct,
  (a.metrics->>'ev')::numeric        AS ev_avg,
  (a.metrics->>'evMax')::numeric     AS ev_max,
  (a.metrics->>'ev50Th')::numeric    AS ev_50th,
  (a.metrics->>'ev90Th')::numeric    AS ev_90th,
  (a.metrics->>'maxEv')::numeric     AS max_ev,
  (a.metrics->>'hardHitp')::numeric  AS hardhit_pct,
  (a.metrics->>'hardHit')::int       AS hardhit_cnt,
  (a.metrics->>'barrels')::int       AS barrels,
  (a.metrics->>'brlp')::numeric      AS barrel_pct,
  (a.metrics->>'brlsBbEp')::numeric  AS barrels_per_bbe,
  (a.metrics->>'brlsPAp')::numeric   AS barrels_per_pa,
  (a.metrics->>'laAvg')::numeric     AS la_avg,
  (a.metrics->>'distanceAvgHr')::numeric AS dist_avg_hr,
  (a.metrics->>'distanceMax')::numeric   AS dist_max,
  (a.metrics->>'bbe')::int           AS bbe,
  (a.metrics->>'gbp')::numeric       AS gb_pct,
  (a.metrics->>'fbp')::numeric       AS fb_pct,
  (a.metrics->>'ldp')::numeric       AS ld_pct,
  (a.metrics->>'airp')::numeric      AS air_pct,
  (a.metrics->>'pup')::numeric       AS popup_pct,
  (a.metrics->>'pullp')::numeric     AS pull_pct,
  (a.metrics->>'straightp')::numeric AS center_pct,
  (a.metrics->>'oppop')::numeric     AS oppo_pct,
  (a.metrics->>'kph')::numeric       AS velo_avg,
  (a.metrics->>'kphMax')::numeric    AS velo_max,
  (a.metrics->>'spinRate')::numeric  AS spin_avg,
  (a.metrics->>'spinRateMax')::numeric AS spin_max,
  a.metrics
FROM cpbl.advanced_stats a
WHERE a.kind_code = 'A'
  AND (
    (NOT EXISTS (SELECT 1 FROM cpbl.advanced_snapshot_state s
                 WHERE s.year = a.year AND s.kind_code = a.kind_code
                   AND s.dataset = 'player_stats' AND s.role = a.role)
     AND a.source_run_id IS NULL)
    OR EXISTS (SELECT 1 FROM cpbl.advanced_snapshot_state s
               WHERE s.year = a.year AND s.kind_code = a.kind_code
                 AND s.dataset = 'player_stats' AND s.role = a.role
                 AND s.current_run_id = a.source_run_id)
  );
