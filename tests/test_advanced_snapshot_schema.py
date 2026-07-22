from __future__ import annotations

import os
from pathlib import Path

import psycopg
import pytest

ROOT = Path(__file__).parents[1]
MIGRATION = ROOT / "migrations" / "062_advanced_snapshot_schema.sql"


def test_advanced_snapshot_migration_is_additive_and_rerunnable() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    upper = sql.upper()

    for table in (
        "cpbl.advanced_ingest_runs",
        "cpbl.advanced_snapshot_state",
        "cpbl.advanced_pitch_type_stats",
        "cpbl.advanced_league_summary",
    ):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in sql

    assert "ADD COLUMN IF NOT EXISTS source_run_id" in sql
    assert "ADD COLUMN IF NOT EXISTS last_seen_at" in sql
    assert "DROP TABLE" not in upper
    assert "DROP COLUMN" not in upper
    assert "TRUNCATE" not in upper
    assert "DELETE FROM" not in upper


@pytest.mark.skipif(
    not os.getenv("ADV_SCHEMA_TEST_DATABASE_URL"),
    reason="requires CARD_ID-isolated PostgreSQL",
)
def test_advanced_snapshot_schema_contract_and_rerun_preserve_existing_rows() -> None:
    database_url = os.environ["ADV_SCHEMA_TEST_DATABASE_URL"]
    assert database_url.rsplit("/", 1)[-1] == "cpbl_ingest_adv_expand1"
    migrations = sorted((ROOT / "migrations").glob("*.sql"))

    with psycopg.connect(database_url) as connection:
        connection.execute("DROP SCHEMA IF EXISTS cpbl CASCADE")
        for _ in range(2):
            for migration in migrations:
                connection.execute(migration.read_text(encoding="utf-8"))
        connection.execute(
            """
            INSERT INTO cpbl.advanced_stats (year, kind_code, acnt, role, metrics)
            VALUES (2099, 'A', '0000000001', 'batting', '{"woba": 0.3}'::jsonb)
            ON CONFLICT (year, kind_code, acnt, role) DO UPDATE
            SET metrics = EXCLUDED.metrics
            """
        )
        connection.commit()

        for _ in range(2):
            connection.execute(MIGRATION.read_text(encoding="utf-8"))
        connection.commit()

        row = connection.execute(
            """
            SELECT metrics, source_run_id, last_seen_at
            FROM cpbl.advanced_stats
            WHERE year = 2099 AND kind_code = 'A'
              AND acnt = '0000000001' AND role = 'batting'
            """
        ).fetchone()
        assert row == ({"woba": 0.3}, None, None)

        primary_keys = {
            record[0]: record[1]
            for record in connection.execute(
                """
                SELECT tc.table_name,
                       array_agg(kcu.column_name::text ORDER BY kcu.ordinal_position)
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu
                  ON tc.constraint_name = kcu.constraint_name
                 AND tc.constraint_schema = kcu.constraint_schema
                WHERE tc.constraint_schema = 'cpbl'
                  AND tc.constraint_type = 'PRIMARY KEY'
                  AND tc.table_name IN (
                    'advanced_pitch_type_stats', 'advanced_league_summary',
                    'advanced_snapshot_state'
                  )
                GROUP BY tc.table_name
                """
            )
        }
        assert primary_keys["advanced_pitch_type_stats"] == [
            "year", "kind_code", "role", "acnt", "pitch_type",
        ]
        assert primary_keys["advanced_league_summary"] == [
            "year", "kind_code", "category", "pitch_type",
        ]
        assert primary_keys["advanced_snapshot_state"] == [
            "year", "kind_code", "dataset", "role",
        ]

        indexes = {
            record[0]
            for record in connection.execute(
                """
                SELECT indexname
                FROM pg_indexes
                WHERE schemaname = 'cpbl'
                  AND tablename IN (
                    'advanced_ingest_runs', 'advanced_pitch_type_stats',
                    'advanced_league_summary'
                  )
                """
            )
        }
        assert {
            "idx_advanced_ingest_runs_scope",
            "idx_advanced_pitch_type_source_run",
            "idx_advanced_league_summary_source_run",
        } <= indexes

        run_id = connection.execute(
            """
            INSERT INTO cpbl.advanced_ingest_runs (
                year, kind_code, dataset, role, snapshot_scope, status,
                source_endpoint, source_fetched_at, observed_rows, accepted_rows
            ) VALUES (
                2026, 'A', 'pitch_type_stats', 'pitching', 'full', 'validated',
                '/leaderboards/pitch-tracking', '2026-07-22T09:00:00Z', 2, 2
            ) RETURNING id
            """
        ).fetchone()[0]
        with connection.cursor() as cursor:
            cursor.executemany(
                """
                INSERT INTO cpbl.advanced_pitch_type_stats (
                    year, kind_code, role, acnt, pitch_type, pitches, kph,
                    spin_rate, throws, source_run_id, source_fetched_at, last_seen_at
                ) VALUES (
                    2026, 'A', 'pitching', '0000007790', %s, %s, %s,
                    %s, 'R', %s, '2026-07-22T09:00:00Z', '2026-07-22T09:00:00Z'
                )
                """,
                [
                    ("breakingball", 758, 135.9062, 1977.5341, run_id),
                    ("fastball", 428, 146.3434, 2326.9341, run_id),
                ],
            )
        rows = connection.execute(
            """
            SELECT pitch_type, pitches
            FROM cpbl.advanced_pitch_type_stats
            WHERE year = 2026 AND kind_code = 'A' AND role = 'pitching'
              AND acnt = '0000007790'
            ORDER BY pitch_type
            """
        ).fetchall()
        assert rows == [("breakingball", 758), ("fastball", 428)]
