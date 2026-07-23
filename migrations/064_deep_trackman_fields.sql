-- INGEST-DEEP-TRACKMAN1：入庫深層 TrackMan 物理特徵（schema expand）。
-- 來源 logs API Trackman：Hit.LandingFlat.{Bearing,Confidence}、Hit.Launch.HitSpinRate、
-- Pitch.Flight.PolyFit.PitchTrajectory.{X,Y,Z}[0..2] 官方原始九係數。
--
-- 型別採 double precision（float8）而非 real：官方係數達 ~11 位有效數字
--（實例 X[0]=16.698916056），float4 僅 ~7 位會失真。紅線「原始值不可由衍生值反推、
--  九係數須原值保存」故不 round、以 float8 原值入庫；既有 traj_accel_y/z（=2·Y[2]/2·Z[2] round(4)）
--  與 ivb_cm/hb_cm 公式一律不動（非破壞性、純欄位擴充）。
-- 全部 NULL 容許：相容無 TrackMan 設備球場、無擊球（Hit=null）事件與歷史 opendata。
-- 冪等：全部 IF NOT EXISTS。

ALTER TABLE cpbl.pitch_tracking ADD COLUMN IF NOT EXISTS hit_landing_bearing    double precision; -- 落地方位角（度）
ALTER TABLE cpbl.pitch_tracking ADD COLUMN IF NOT EXISTS hit_landing_confidence text;             -- 官方落地品質標記 High/Medium/…
ALTER TABLE cpbl.pitch_tracking ADD COLUMN IF NOT EXISTS hit_spin_rate          double precision; -- 擊球自轉率（rpm）

ALTER TABLE cpbl.pitch_tracking ADD COLUMN IF NOT EXISTS traj_x0 double precision; -- 投球軌跡 X 軸多項式 t^0 係數（原值）
ALTER TABLE cpbl.pitch_tracking ADD COLUMN IF NOT EXISTS traj_x1 double precision; -- 投球軌跡 X 軸多項式 t^1 係數（原值）
ALTER TABLE cpbl.pitch_tracking ADD COLUMN IF NOT EXISTS traj_x2 double precision; -- 投球軌跡 X 軸多項式 t^2 係數（原值）
ALTER TABLE cpbl.pitch_tracking ADD COLUMN IF NOT EXISTS traj_y0 double precision; -- 投球軌跡 Y 軸多項式 t^0 係數（原值）
ALTER TABLE cpbl.pitch_tracking ADD COLUMN IF NOT EXISTS traj_y1 double precision; -- 投球軌跡 Y 軸多項式 t^1 係數（原值）
ALTER TABLE cpbl.pitch_tracking ADD COLUMN IF NOT EXISTS traj_y2 double precision; -- 投球軌跡 Y 軸多項式 t^2 係數（原值）
ALTER TABLE cpbl.pitch_tracking ADD COLUMN IF NOT EXISTS traj_z0 double precision; -- 投球軌跡 Z 軸多項式 t^0 係數（原值）
ALTER TABLE cpbl.pitch_tracking ADD COLUMN IF NOT EXISTS traj_z1 double precision; -- 投球軌跡 Z 軸多項式 t^1 係數（原值）
ALTER TABLE cpbl.pitch_tracking ADD COLUMN IF NOT EXISTS traj_z2 double precision; -- 投球軌跡 Z 軸多項式 t^2 係數（原值）
