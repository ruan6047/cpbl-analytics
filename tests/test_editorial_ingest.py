from __future__ import annotations

from pathlib import Path

MIGRATION = Path(__file__).parents[1] / "migrations" / "060_editorial_content.sql"


def test_editorial_migration_is_additive_and_rerunnable() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS cpbl.editorial_ingest_runs" in sql
    assert "CREATE TABLE IF NOT EXISTS cpbl.editorial_content_revisions" in sql
    assert sql.count("CREATE INDEX IF NOT EXISTS") == 2
    assert "to_regclass('cpbl.editorial_content_current') IS NULL" in sql
    assert "DROP TABLE" not in sql
    assert "DROP COLUMN" not in sql


def test_editorial_migration_keeps_explicit_withdrawal_and_audit_fields() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")

    for field in (
        "source_url",
        "valid_from",
        "valid_until",
        "updated_by",
        "status",
        "withdrawal_reason",
        "source_updated_at",
        "ingest_run_id",
        "error_report",
    ):
        assert field in sql

    assert "status IN ('active', 'withdrawn')" in sql
    assert "status = 'withdrawn'" in sql
