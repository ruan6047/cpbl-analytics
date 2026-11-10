-- #392：開季切回賽季中的手動工具——切回紀錄（軍, 被切回的球季）。
--
-- 寫入者只有 `cpbl.season_reopen`（需求方手動執行 `python -m cpbl.season_reopen apply|revoke`）：
--   本機以 psycopg 寫、正式站以 `scripts/refresh-cpbl-prod.sh` 的 SEASON_REOPEN_ONLY 單表模式寫（兩端各自單一
--   writer）。⛔ 不進每日鏈 sync_table 清單。
-- 讀取：`cpbl.season_close.league_closure` 只讀 revoked_at IS NULL 的列；該軍查詢球季＝當下最新球季＝紀錄球季、
--   且推導為已收官 ⇒ 視為未收官（override='reopened'）。新球季首場完賽後舊紀錄自然失效，不需清除。
-- 作廢（需求方裁定 #13 的撤銷）＝填 revoked_at，列保留成歷史；再次 apply 會清空 revoked_at、重記 reopened_at。

CREATE TABLE IF NOT EXISTS cpbl.season_reopen (
    league       text        NOT NULL CHECK (league IN ('major', 'farm')),
    season       int         NOT NULL CHECK (season BETWEEN 1990 AND 2100),
    reopened_at  timestamptz NOT NULL DEFAULT now(),
    revoked_at   timestamptz,
    note         text,
    PRIMARY KEY (league, season)
);
