"""Google Sheets editorial content validation and append-only ingest."""

from __future__ import annotations

import csv
import hashlib
import json
import re
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlsplit

import httpx
import psycopg
from google.auth.transport.requests import Request
from google.oauth2 import service_account

SHEETS_READONLY_SCOPE = "https://www.googleapis.com/auth/spreadsheets.readonly"
HEADERS = (
    "content_id",
    "content_type",
    "status",
    "team_code",
    "title",
    "summary",
    "body_markdown",
    "source_url",
    "source_label",
    "valid_from",
    "valid_until",
    "updated_by",
    "source_updated_at",
    "withdrawal_reason",
)
CONTENT_TYPES = frozenset({"cheering_culture", "theme_day", "seasonal_banner"})
STATUSES = frozenset({"active", "withdrawn"})
CONTENT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{2,99}$")
SHEET_ID_RE = re.compile(r"^[A-Za-z0-9_-]{20,200}$")
ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class EditorialSourceError(RuntimeError):
    """The source could not be read without exposing its response body."""


@dataclass(frozen=True)
class RowError:
    row: int
    field: str
    code: str
    message: str


@dataclass(frozen=True)
class EditorialRow:
    row_number: int
    content_id: str
    content_type: str
    status: str
    team_code: str | None
    title: str
    summary: str
    body_markdown: str
    source_url: str
    source_label: str
    valid_from: date
    valid_until: date
    updated_by: str
    source_updated_at: datetime
    withdrawal_reason: str | None
    content_hash: str


@dataclass(frozen=True)
class ValidatedSheet:
    rows: tuple[EditorialRow, ...]
    errors: tuple[RowError, ...]
    source_digest: str
    total_rows: int


@dataclass(frozen=True)
class IngestReport:
    run_id: uuid.UUID
    status: str
    total_rows: int
    accepted_rows: int
    unchanged_rows: int
    rejected_rows: int
    errors: tuple[RowError, ...]
    source_digest: str

    def as_dict(self) -> dict[str, Any]:
        output = asdict(self)
        output["run_id"] = str(self.run_id)
        return output


def read_csv_values(path: Path) -> list[list[str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return [list(row) for row in csv.reader(handle)]


def fetch_google_sheet_values(
    spreadsheet_id: str,
    range_name: str,
    credentials_file: Path,
) -> list[list[str]]:
    if not SHEET_ID_RE.fullmatch(spreadsheet_id):
        raise EditorialSourceError("spreadsheet_id 格式無效")
    if not range_name.strip() or len(range_name) > 200:
        raise EditorialSourceError("range 格式無效")

    try:
        credentials = service_account.Credentials.from_service_account_file(
            str(credentials_file), scopes=[SHEETS_READONLY_SCOPE]
        )
        credentials.refresh(Request())
    except Exception as exc:
        raise EditorialSourceError("Google Sheets 認證失敗") from exc
    encoded_range = quote(range_name, safe="")
    url = (
        f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}"
        f"/values/{encoded_range}"
    )
    try:
        response = httpx.get(
            url,
            headers={"Authorization": f"Bearer {credentials.token}"},
            params={"majorDimension": "ROWS", "valueRenderOption": "FORMATTED_VALUE"},
            timeout=30.0,
            follow_redirects=False,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        status = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
        suffix = f" (HTTP {status})" if status is not None else ""
        raise EditorialSourceError(f"Google Sheets 讀取失敗{suffix}") from exc

    try:
        payload = response.json()
    except ValueError as exc:
        raise EditorialSourceError("Google Sheets 回應格式無效") from exc
    if not isinstance(payload, dict):
        raise EditorialSourceError("Google Sheets 回應格式無效")
    values = payload.get("values", [])
    if not isinstance(values, list) or any(not isinstance(row, list) for row in values):
        raise EditorialSourceError("Google Sheets 回應格式無效")
    return [[str(cell) for cell in row] for row in values]


def validate_sheet(values: list[list[str]]) -> ValidatedSheet:
    digest = hashlib.sha256(
        json.dumps(values, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()
    if not values:
        error = RowError(1, "header", "missing_header", "缺少標題列")
        return ValidatedSheet((), (error,), digest, 0)

    headers = tuple(cell.strip() for cell in values[0])
    if headers != HEADERS:
        error = RowError(1, "header", "header_mismatch", "欄位名稱或順序不符合契約")
        return ValidatedSheet((), (error,), digest, max(len(values) - 1, 0))

    rows: list[EditorialRow] = []
    errors: list[RowError] = []
    content_rows: dict[str, list[int]] = {}
    total_rows = 0
    for row_number, raw in enumerate(values[1:], start=2):
        if not any(str(cell).strip() for cell in raw):
            continue
        total_rows += 1
        cells = [str(cell).strip() for cell in raw[: len(HEADERS)]]
        cells.extend([""] * (len(HEADERS) - len(cells)))
        if any(str(cell).strip() for cell in raw[len(HEADERS) :]):
            errors.append(
                RowError(row_number, "row", "unexpected_cell", "契約欄位外仍有資料")
            )
        parsed, row_errors = _parse_row(row_number, dict(zip(HEADERS, cells, strict=True)))
        errors.extend(row_errors)
        if parsed is not None:
            rows.append(parsed)
            content_rows.setdefault(parsed.content_id, []).append(row_number)

    for _content_id, row_numbers in content_rows.items():
        if len(row_numbers) > 1:
            for row_number in row_numbers:
                errors.append(
                    RowError(row_number, "content_id", "duplicate", "同批次 content_id 重複")
                )

    return ValidatedSheet(tuple(rows), tuple(errors), digest, total_rows)


def ingest_sheet(
    connection: psycopg.Connection,
    values: list[list[str]],
    *,
    source_kind: str,
    source_ref: str,
    source_range: str | None = None,
    now: datetime | None = None,
    run_id: uuid.UUID | None = None,
) -> IngestReport:
    if source_kind not in {"google_sheets", "csv_fixture"}:
        raise ValueError("unsupported source_kind")
    validated = validate_sheet(values)
    timestamp = (now or datetime.now(UTC)).astimezone(UTC)
    current_run_id = run_id or uuid.uuid4()
    if validated.errors:
        report = _rejected_report(current_run_id, validated, validated.errors)
        _insert_run(connection, report, source_kind, source_ref, source_range, timestamp)
        return report

    # Serializes all editorial writers even when the external scheduler lock fails.
    connection.execute("SELECT pg_advisory_xact_lock(%s)", (60_202_607_19,))
    latest = _latest_revisions(connection, validated.rows)
    conflicts: list[RowError] = []
    unchanged: set[str] = set()
    for row in validated.rows:
        existing = latest.get(row.content_id)
        if existing is None:
            continue
        existing_at, existing_hash = existing
        if existing_at > row.source_updated_at:
            conflicts.append(
                RowError(row.row_number, "source_updated_at", "stale_version", "資料庫已有較新版本")
            )
        elif existing_at == row.source_updated_at and existing_hash != row.content_hash:
            conflicts.append(
                RowError(
                    row.row_number,
                    "source_updated_at",
                    "version_conflict",
                    "同一版本時間的內容不一致",
                )
            )
        elif existing_at == row.source_updated_at:
            unchanged.add(row.content_id)

    if conflicts:
        report = _rejected_report(current_run_id, validated, tuple(conflicts))
        _insert_run(connection, report, source_kind, source_ref, source_range, timestamp)
        return report

    changed_rows = tuple(row for row in validated.rows if row.content_id not in unchanged)
    report = IngestReport(
        run_id=current_run_id,
        status="accepted",
        total_rows=validated.total_rows,
        accepted_rows=len(changed_rows),
        unchanged_rows=len(unchanged),
        rejected_rows=0,
        errors=(),
        source_digest=validated.source_digest,
    )
    _insert_run(connection, report, source_kind, source_ref, source_range, timestamp)
    if changed_rows:
        with connection.cursor() as cursor:
            cursor.executemany(
                """
                INSERT INTO cpbl.editorial_content_revisions (
                    content_id, source_updated_at, ingest_run_id, source_row_number,
                    content_type, status, team_code, title, summary, body_markdown,
                    source_url, source_label, valid_from, valid_until, updated_by,
                    withdrawal_reason, content_hash
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
                """,
                [
                    (
                        row.content_id,
                        row.source_updated_at,
                        current_run_id,
                        row.row_number,
                        row.content_type,
                        row.status,
                        row.team_code,
                        row.title,
                        row.summary,
                        row.body_markdown,
                        row.source_url,
                        row.source_label,
                        row.valid_from,
                        row.valid_until,
                        row.updated_by,
                        row.withdrawal_reason,
                        row.content_hash,
                    )
                    for row in changed_rows
                ],
            )
    return report


def _latest_revisions(
    connection: psycopg.Connection, rows: tuple[EditorialRow, ...]
) -> dict[str, tuple[datetime, str]]:
    if not rows:
        return {}
    result = connection.execute(
        """
        SELECT DISTINCT ON (content_id) content_id, source_updated_at, content_hash
        FROM cpbl.editorial_content_revisions
        WHERE content_id = ANY(%s)
        ORDER BY content_id, source_updated_at DESC
        """,
        ([row.content_id for row in rows],),
    ).fetchall()
    return {str(content_id): (source_updated_at, str(content_hash)) for content_id, source_updated_at, content_hash in result}


def _rejected_report(
    run_id: uuid.UUID,
    validated: ValidatedSheet,
    errors: tuple[RowError, ...],
) -> IngestReport:
    return IngestReport(
        run_id=run_id,
        status="rejected",
        total_rows=validated.total_rows,
        accepted_rows=0,
        unchanged_rows=0,
        rejected_rows=len({error.row for error in errors}),
        errors=errors,
        source_digest=validated.source_digest,
    )


def _insert_run(
    connection: psycopg.Connection,
    report: IngestReport,
    source_kind: str,
    source_ref: str,
    source_range: str | None,
    timestamp: datetime,
) -> None:
    connection.execute(
        """
        INSERT INTO cpbl.editorial_ingest_runs (
            run_id, source_kind, source_ref, source_range, source_digest, status,
            total_rows, accepted_rows, unchanged_rows, rejected_rows, error_report,
            started_at, completed_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s)
        """,
        (
            report.run_id,
            source_kind,
            source_ref,
            source_range,
            report.source_digest,
            report.status,
            report.total_rows,
            report.accepted_rows,
            report.unchanged_rows,
            report.rejected_rows,
            json.dumps(errors_as_dicts(report.errors), ensure_ascii=False),
            timestamp,
            timestamp,
        ),
    )


def _parse_row(row_number: int, data: dict[str, str]) -> tuple[EditorialRow | None, list[RowError]]:
    errors: list[RowError] = []

    def require(field: str, maximum: int) -> None:
        length = len(data[field])
        if length == 0 or length > maximum:
            errors.append(RowError(row_number, field, "length", f"必須為 1–{maximum} 字元"))

    require("title", 120)
    require("summary", 300)
    require("source_label", 120)
    require("updated_by", 120)
    if len(data["body_markdown"]) > 20_000:
        errors.append(RowError(row_number, "body_markdown", "length", "不得超過 20000 字元"))
    if len(data["team_code"]) > 20:
        errors.append(RowError(row_number, "team_code", "length", "不得超過 20 字元"))
    if data["content_type"] == "cheering_culture" and not data["team_code"]:
        errors.append(RowError(row_number, "team_code", "required", "應援文化必須指定球隊"))
    if not CONTENT_ID_RE.fullmatch(data["content_id"]):
        errors.append(RowError(row_number, "content_id", "format", "格式必須為小寫 slug"))
    if data["content_type"] not in CONTENT_TYPES:
        errors.append(RowError(row_number, "content_type", "enum", "不支援的內容類型"))
    if data["status"] not in STATUSES:
        errors.append(RowError(row_number, "status", "enum", "狀態必須為 active 或 withdrawn"))

    parsed_url = urlsplit(data["source_url"])
    if (
        parsed_url.scheme != "https"
        or not parsed_url.hostname
        or parsed_url.username
        or parsed_url.password
    ):
        errors.append(RowError(row_number, "source_url", "url", "必須為無帳密的 HTTPS URL"))

    valid_from = _parse_date(data["valid_from"], row_number, "valid_from", errors)
    valid_until = _parse_date(data["valid_until"], row_number, "valid_until", errors)
    updated_at = _parse_datetime(data["source_updated_at"], row_number, errors)
    if valid_from and valid_until and valid_until < valid_from:
        errors.append(RowError(row_number, "valid_until", "range", "不得早於 valid_from"))

    reason = data["withdrawal_reason"] or None
    if data["status"] == "active" and reason is not None:
        errors.append(RowError(row_number, "withdrawal_reason", "unexpected", "active 不得填撤回原因"))
    if data["status"] == "withdrawn" and (reason is None or len(reason) > 300):
        errors.append(RowError(row_number, "withdrawal_reason", "required", "withdrawn 必須填 1–300 字元原因"))
    if errors or valid_from is None or valid_until is None or updated_at is None:
        return None, errors

    canonical: dict[str, Any] = dict(data)
    canonical["valid_from"] = valid_from.isoformat()
    canonical["valid_until"] = valid_until.isoformat()
    canonical["source_updated_at"] = updated_at.isoformat()
    content_hash = hashlib.sha256(
        json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return (
        EditorialRow(
            row_number=row_number,
            content_id=data["content_id"],
            content_type=data["content_type"],
            status=data["status"],
            team_code=data["team_code"] or None,
            title=data["title"],
            summary=data["summary"],
            body_markdown=data["body_markdown"],
            source_url=data["source_url"],
            source_label=data["source_label"],
            valid_from=valid_from,
            valid_until=valid_until,
            updated_by=data["updated_by"],
            source_updated_at=updated_at,
            withdrawal_reason=reason,
            content_hash=content_hash,
        ),
        [],
    )


def _parse_date(value: str, row: int, field: str, errors: list[RowError]) -> date | None:
    try:
        if not ISO_DATE_RE.fullmatch(value):
            raise ValueError
        return date.fromisoformat(value)
    except ValueError:
        errors.append(RowError(row, field, "date", "必須為 YYYY-MM-DD"))
        return None


def _parse_datetime(value: str, row: int, errors: list[RowError]) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError
        return parsed.astimezone(UTC)
    except ValueError:
        errors.append(
            RowError(row, "source_updated_at", "datetime", "必須為含時區的 ISO 8601")
        )
        return None


def errors_as_dicts(errors: tuple[RowError, ...]) -> list[dict[str, Any]]:
    return [asdict(error) for error in errors]
