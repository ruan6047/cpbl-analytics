-- migrate() 的套用記錄表（cpbl.db.migrate）。放在 cpbl schema 內：隔離測試 DROP SCHEMA cpbl CASCADE 時
-- 它一起消失，下一次 migrate 自然全量重跑——schema 從零開始，記錄也從零開始。
-- 與 migrations/*.sql 一樣是 .sql 資源檔而不是 Python 字串：migrate() 執行的 SQL 一律來自 .sql 檔，
-- 也讓 scripts/script_inventory.py 的 W2 文字掃描不會因 cpbl/db.py 出現 CREATE／INSERT 字面，
-- 把所有只 import cpbl.db 取連線的唯讀腳本判成寫入。
CREATE SCHEMA IF NOT EXISTS cpbl;
CREATE TABLE IF NOT EXISTS cpbl.schema_migrations (
    filename   text PRIMARY KEY,
    checksum   text NOT NULL,
    applied_at timestamptz NOT NULL DEFAULT now()
);
