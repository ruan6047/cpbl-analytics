-- 球種細分：pitch_tracking 補軌跡導出特徵 + 推算球種。
-- 來源 logs API Trackman.Pitch.Flight.PolyFit.PitchTrajectory（二次多項式係數）+ Location.ZoneTime。
-- IVB/HB 由軌跡加速度導出（見 docs/PITCH_TYPE_PLAN.md §2）；pitch_type_pred 為離線 GMM 分類結果。
-- 冪等：全部 IF NOT EXISTS。

ALTER TABLE cpbl.pitch_tracking ADD COLUMN IF NOT EXISTS traj_accel_y real;    -- 2·Y[2]（垂直加速度含重力，m/s²）
ALTER TABLE cpbl.pitch_tracking ADD COLUMN IF NOT EXISTS traj_accel_z real;    -- 2·Z[2]（水平加速度，m/s²）
ALTER TABLE cpbl.pitch_tracking ADD COLUMN IF NOT EXISTS zone_time   real;     -- 出手到本壘飛行秒數
ALTER TABLE cpbl.pitch_tracking ADD COLUMN IF NOT EXISTS ivb_cm      real;     -- 誘導垂直位移（cm，正=上飄）
ALTER TABLE cpbl.pitch_tracking ADD COLUMN IF NOT EXISTS hb_cm       real;     -- 水平位移（cm，未翻轉左右手）
ALTER TABLE cpbl.pitch_tracking ADD COLUMN IF NOT EXISTS pitch_type_pred text; -- 推算球種（離線分類）
