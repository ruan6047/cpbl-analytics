-- GAME-RECAP-PA1-FIX1：逐球映射唯一鍵改為 per-build 範圍。
--
-- migration 066 的 UNIQUE (source_revision_id, year, kind_code, game_sno,
-- pitcher_acnt, pitch_cnt) 隱含假設「同一 tracking revision 只會有一個 build 寫映射」。
-- 該假設在 BUILD1 時代成立（同來源重跑＝noop），但 FIX1 的 builder 升級發布路徑會
-- 對**同一個 tracking revision** 建新 build（舊 build 轉 superseded、其映射列保留供
-- 稽核）→ 新映射與舊映射同鍵，268 場（2026 有 TrackMan 的場次）全庫重建時撞唯一鍵。
-- 這是 BUILD1 的潛在缺陷：晚到 livelog 的 reconciliation build 同樣會撞，只是從未
-- 被觸發（原始回填一次到位、每日 refresh 不跑 PA build、rehearsal 合成場無逐球）。
--
-- 契約「每顆球至多綁定一個 PA」的正確範圍是**單一 build 之內**：
-- 消費端只讀 published build（每場恰一個，partial unique index 保證），故
-- per-build 唯一 ⇒ published 視圖下每球仍至多一個 PA，語意不變；
-- superseded／reconciliation build 的映射保留稽核不受影響。
--
-- 冪等（migrate() 每次全跑）。不加 build_id FK：pa_row_id 已有 FK cascade，
-- build 刪除時映射隨 PA 列連動，重複 FK 徒增鎖競爭。

ALTER TABLE cpbl.game_pa_pitch_mappings
    ADD COLUMN IF NOT EXISTS build_id uuid;

UPDATE cpbl.game_pa_pitch_mappings m
   SET build_id = pa.build_id
  FROM cpbl.game_plate_appearances pa
 WHERE pa.pa_row_id = m.pa_row_id AND m.build_id IS NULL;

ALTER TABLE cpbl.game_pa_pitch_mappings
    DROP CONSTRAINT IF EXISTS game_pa_pitch_mappings_source_revision_id_year_kind_code_ga_key;

CREATE UNIQUE INDEX IF NOT EXISTS game_pa_pitch_mappings_build_pitch_key
    ON cpbl.game_pa_pitch_mappings (build_id, pitcher_acnt, pitch_cnt);

COMMENT ON COLUMN cpbl.game_pa_pitch_mappings.build_id IS
    '所屬 build（與 pa_row_id 的 build 一致）；唯一鍵範圍＝per-build，'
    '「每球至多一 PA」由每場單一 published build 保證於消費視圖';
