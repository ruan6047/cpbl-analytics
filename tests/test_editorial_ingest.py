from __future__ import annotations

from pathlib import Path

import pytest

from cpbl.ingest.editorial import HEADERS, EditorialSourceError, validate_sheet

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
