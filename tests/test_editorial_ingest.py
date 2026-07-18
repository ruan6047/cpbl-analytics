from __future__ import annotations

import os
from pathlib import Path

import psycopg
import pytest

from cpbl.ingest.editorial import (
    HEADERS,
    EditorialSourceError,
    ingest_sheet,
    validate_sheet,
)
from cpbl.ingest.run_ingest_editorial import run

MIGRATION = Path(__file__).parents[1] / "migrations" / "060_editorial_content.sql"
FIXTURE = Path(__file__).parent / "fixtures" / "editorial_content.csv"


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


def _row(**overrides: str) -> list[str]:
    values = {
        "content_id": "brothers-theme-day-2026",
        "content_type": "theme_day",
        "status": "active",
        "team_code": "B04",
        "title": "兄弟主題日",
        "summary": "可追溯的活動摘要",
        "body_markdown": "活動內容",
        "source_url": "https://example.com/events/2026",
        "source_label": "球團公告",
        "valid_from": "2026-07-20",
        "valid_until": "2026-07-21",
        "updated_by": "editor@example.com",
        "source_updated_at": "2026-07-19T01:00:00+08:00",
        "withdrawal_reason": "",
    }
    values.update(overrides)
    return [values[header] for header in HEADERS]


def test_validate_sheet_accepts_traced_active_content() -> None:
    result = validate_sheet([list(HEADERS), _row()])

    assert result.errors == ()
    assert result.total_rows == 1
    assert result.rows[0].content_id == "brothers-theme-day-2026"
    assert result.rows[0].source_updated_at.isoformat() == "2026-07-18T17:00:00+00:00"
    assert len(result.rows[0].content_hash) == 64


def test_validate_sheet_accepts_explicit_withdrawal() -> None:
    result = validate_sheet(
        [list(HEADERS), _row(status="withdrawn", withdrawal_reason="活動取消")]
    )

    assert result.errors == ()
    assert result.rows[0].status == "withdrawn"


@pytest.mark.parametrize(
    ("overrides", "error_field"),
    [
        ({"content_id": "BAD ID"}, "content_id"),
        ({"source_url": "http://example.com"}, "source_url"),
        ({"valid_until": "2026-07-19"}, "valid_until"),
        ({"source_updated_at": "2026-07-19T01:00:00"}, "source_updated_at"),
        ({"status": "withdrawn"}, "withdrawal_reason"),
        ({"withdrawal_reason": "不該出現"}, "withdrawal_reason"),
        ({"content_type": "cheering_culture", "team_code": ""}, "team_code"),
    ],
)
def test_validate_sheet_rejects_bad_rows(overrides: dict[str, str], error_field: str) -> None:
    result = validate_sheet([list(HEADERS), _row(**overrides)])

    assert error_field in {error.field for error in result.errors}
    assert result.rows == ()


def test_validate_sheet_rejects_header_drift_and_duplicate_ids() -> None:
    bad_header = validate_sheet([[*HEADERS[:-1], "removed"], _row()])
    duplicate = validate_sheet([list(HEADERS), _row(), _row(title="另一個標題")])

    assert bad_header.errors[0].code == "header_mismatch"
    assert [error.code for error in duplicate.errors] == ["duplicate", "duplicate"]


def test_source_error_does_not_include_remote_response_body(monkeypatch: pytest.MonkeyPatch) -> None:
    from cpbl.ingest import editorial

    class Credentials:
        token = "secret-token"

        def refresh(self, _request: object) -> None:
            return None

    monkeypatch.setattr(
        editorial.service_account.Credentials,
        "from_service_account_file",
        lambda *_args, **_kwargs: Credentials(),
    )
    response = editorial.httpx.Response(
        403,
        text="remote-secret-body",
        request=editorial.httpx.Request("GET", "https://sheets.googleapis.com"),
    )
    monkeypatch.setattr(editorial.httpx, "get", lambda *_args, **_kwargs: response)

    with pytest.raises(EditorialSourceError) as raised:
        editorial.fetch_google_sheet_values("a" * 30, "Editorial!A:N", Path("secret.json"))

    assert "HTTP 403" in str(raised.value)
    assert "remote-secret-body" not in str(raised.value)
    assert "secret-token" not in str(raised.value)


def test_fixture_validate_only_is_credential_free(capsys: pytest.CaptureFixture[str]) -> None:
    assert run(["--csv", str(FIXTURE), "--validate-only"]) == 0

    output = capsys.readouterr().out
    assert '"status": "valid"' in output
    assert "fixture@example.com" not in output
    assert "測試內容" not in output


def test_invalid_csv_encoding_returns_sanitized_source_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    invalid = tmp_path / "invalid.csv"
    invalid.write_bytes(b"\xffprivate-cell")

    assert run(["--csv", str(invalid), "--validate-only"]) == 2
    output = capsys.readouterr().out
    assert '"code": "source_error"' in output
    assert "private-cell" not in output


@pytest.mark.skipif(
    not os.getenv("EDITORIAL_TEST_DATABASE_URL"),
    reason="requires CARD_ID-isolated PostgreSQL",
)
def test_ingest_is_idempotent_fail_closed_and_withdrawable() -> None:
    database_url = os.environ["EDITORIAL_TEST_DATABASE_URL"]
    assert database_url.rsplit("/", 1)[-1] == "cpbl_data_editorial1"
    content_id = "integration-theme-day-2026"
    run_ids = []
    base = [list(HEADERS), _row(content_id=content_id)]

    with psycopg.connect(database_url) as connection:
        try:
            first = ingest_sheet(
                connection, base, source_kind="csv_fixture", source_ref="integration"
            )
            run_ids.append(first.run_id)
            assert (first.status, first.accepted_rows, first.unchanged_rows) == ("accepted", 1, 0)

            rerun = ingest_sheet(
                connection, base, source_kind="csv_fixture", source_ref="integration"
            )
            run_ids.append(rerun.run_id)
            assert (rerun.status, rerun.accepted_rows, rerun.unchanged_rows) == (
                "accepted",
                0,
                1,
            )

            collision = ingest_sheet(
                connection,
                [list(HEADERS), _row(content_id=content_id, title="同時間不同內容")],
                source_kind="csv_fixture",
                source_ref="integration",
            )
            run_ids.append(collision.run_id)
            assert collision.status == "rejected"
            assert collision.errors[0].code == "version_conflict"

            withdrawal = ingest_sheet(
                connection,
                [
                    list(HEADERS),
                    _row(
                        content_id=content_id,
                        status="withdrawn",
                        withdrawal_reason="活動取消",
                        source_updated_at="2026-07-19T03:00:00+08:00",
                    ),
                ],
                source_kind="csv_fixture",
                source_ref="integration",
            )
            run_ids.append(withdrawal.run_id)
            assert withdrawal.status == "accepted"
            current = connection.execute(
                "SELECT status, withdrawal_reason FROM cpbl.editorial_content_current "
                "WHERE content_id = %s",
                (content_id,),
            ).fetchone()
            assert current == ("withdrawn", "活動取消")

            stale = ingest_sheet(
                connection, base, source_kind="csv_fixture", source_ref="integration"
            )
            run_ids.append(stale.run_id)
            assert stale.status == "rejected"
            assert stale.errors[0].code == "stale_version"

            invalid = ingest_sheet(
                connection,
                [list(HEADERS), _row(content_id=content_id, source_url="http://example.com")],
                source_kind="csv_fixture",
                source_ref="integration",
            )
            run_ids.append(invalid.run_id)
            assert invalid.status == "rejected"
            saved_errors = connection.execute(
                "SELECT error_report FROM cpbl.editorial_ingest_runs WHERE run_id = %s",
                (invalid.run_id,),
            ).fetchone()
            assert saved_errors is not None
            assert saved_errors[0][0]["code"] == "url"

            revisions = connection.execute(
                "SELECT count(*) FROM cpbl.editorial_content_revisions WHERE content_id = %s",
                (content_id,),
            ).fetchone()
            assert revisions == (2,)
        finally:
            connection.execute(
                "DELETE FROM cpbl.editorial_content_revisions WHERE content_id = %s", (content_id,)
            )
            connection.execute(
                "DELETE FROM cpbl.editorial_ingest_runs WHERE run_id = ANY(%s)", (run_ids,)
            )
