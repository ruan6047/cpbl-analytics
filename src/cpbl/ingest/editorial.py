"""Google Sheets editorial content validation and append-only ingest."""

from __future__ import annotations

import csv
import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlsplit

import httpx
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
