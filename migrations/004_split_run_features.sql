-- 賽果預測改版：把「場均得失分差」拆成可分別檢視的得分 / 失分兩項
-- （使用者要在對戰卡上分開看「平均得分」與「平均失分(防禦)」）。
-- 舊欄位 run_diff_diff 保留不刪，僅停用。

ALTER TABLE cpbl.game_features ADD COLUMN IF NOT EXISTS runs_scored_diff  DOUBLE PRECISION;
ALTER TABLE cpbl.game_features ADD COLUMN IF NOT EXISTS runs_allowed_diff DOUBLE PRECISION;
