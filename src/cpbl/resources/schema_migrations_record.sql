-- 記下一支 migration 已套用（參數：filename, checksum）。見 schema_migrations_ddl.sql 的說明。
INSERT INTO cpbl.schema_migrations (filename, checksum, applied_at)
VALUES (%s, %s, now())
ON CONFLICT (filename) DO UPDATE SET checksum = EXCLUDED.checksum, applied_at = now();
