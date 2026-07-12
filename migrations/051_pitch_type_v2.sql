-- 球種細分 v2（ML-PT2 Phase2）：MLB 標籤遷移命名，與 v1 (pitch_type_pred) 並存對照。
ALTER TABLE cpbl.pitch_tracking ADD COLUMN IF NOT EXISTS pitch_type_pred_v2 text;
