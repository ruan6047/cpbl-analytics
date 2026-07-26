"""home_run_log additive migration guard。"""


from pathlib import Path

_MIGRATION = Path(__file__).parents[1] / "migrations" / "067_home_run_log.sql"


def test_home_run_log_migration_is_additive_and_idempotent() -> None:
    sql = _MIGRATION.read_text(encoding="utf-8")
    upper = sql.upper()

    assert "CREATE TABLE IF NOT EXISTS cpbl.home_run_log" in sql
    assert "PRIMARY KEY (year, kind_code, game_sno, inning, hitter_acnt, pitcher_acnt)" in sql
    assert "DROP TABLE" not in upper
    assert "DROP COLUMN" not in upper


def test_home_run_log_retains_official_audit_dimensions() -> None:
    sql = _MIGRATION.read_text(encoding="utf-8")

    for column in ("home_run_type", "citizenship", "hitter_name", "pitcher_name", "source_note"):
        assert column in sql
