"""CLI for validated Google Sheets editorial ingest."""

from __future__ import annotations

import argparse
import csv
import json
import os
from dataclasses import asdict
from pathlib import Path

from cpbl.db import conn, migrate
from cpbl.ingest.editorial import (
    EditorialSourceError,
    fetch_google_sheet_values,
    ingest_sheet,
    read_csv_values,
    validate_sheet,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate and ingest editorial content")
    source = parser.add_mutually_exclusive_group(required=False)
    source.add_argument("--csv", type=Path, help="staging/rehearsal fixture only")
    source.add_argument("--spreadsheet-id", default=os.getenv("EDITORIAL_SPREADSHEET_ID"))
    parser.add_argument("--range", dest="range_name", default=os.getenv("EDITORIAL_SHEET_RANGE"))
    parser.add_argument(
        "--credentials-file",
        type=Path,
        default=os.getenv("GOOGLE_APPLICATION_CREDENTIALS"),
    )
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--report", type=Path, help="write a credential-free JSON report")
    return parser


def run(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.csv is not None:
            values = read_csv_values(args.csv)
            source_kind = "csv_fixture"
            source_ref = f"csv_fixture:{args.csv.name}"
            source_range = None
        else:
            if not args.spreadsheet_id or not args.range_name or not args.credentials_file:
                raise EditorialSourceError(
                    "Google Sheets 來源需 spreadsheet id、range 與 credentials file"
                )
            values = fetch_google_sheet_values(
                args.spreadsheet_id, args.range_name, args.credentials_file
            )
            source_kind = "google_sheets"
            source_ref = f"google_sheets:{args.spreadsheet_id}"
            source_range = args.range_name
    except (EditorialSourceError, OSError, csv.Error):
        output = {"status": "source_error", "errors": [{"code": "source_error"}]}
        _emit(output, args.report)
        return 2

    if args.validate_only:
        validated = validate_sheet(values)
        output = {
            "status": "valid" if not validated.errors else "rejected",
            "total_rows": validated.total_rows,
            "errors": [asdict(error) for error in validated.errors],
            "source_digest": validated.source_digest,
        }
        _emit(output, args.report)
        return 0 if not validated.errors else 2

    migrate()
    with conn() as connection:
        report = ingest_sheet(
            connection,
            values,
            source_kind=source_kind,
            source_ref=source_ref,
            source_range=source_range,
        )
    output = report.as_dict()
    _emit(output, args.report)
    return 0 if report.status == "accepted" else 2


def _emit(output: dict[str, object], report_path: Path | None) -> None:
    rendered = json.dumps(output, ensure_ascii=False, indent=2, default=str)
    print(rendered)
    if report_path is not None:
        report_path.write_text(rendered + "\n", encoding="utf-8")


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
