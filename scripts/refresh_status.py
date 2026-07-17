#!/usr/bin/env python3
"""Write and inspect machine-readable daily refresh status files."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import Any

EXIT_NOT_TRIGGERED = 2
EXIT_SCRAPE_FAILED = 3
EXIT_SYNC_FAILED = 4
EXIT_INVALID_STATUS = 5
EXIT_RUNNING = 6


def _bool(value: str) -> bool:
    if value == "1":
        return True
    if value == "0":
        return False
    raise argparse.ArgumentTypeError("boolean must be 0 or 1")


def _tail(log_path: Path, line_count: int = 20) -> str:
    try:
        return "".join(log_path.read_text(encoding="utf-8", errors="replace").splitlines(True)[-line_count:])
    except FileNotFoundError:
        return ""


def _write_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        delete=False,
    ) as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        temp_path = Path(handle.name)
    os.replace(temp_path, path)


def _write_status(args: argparse.Namespace, payload: dict[str, Any]) -> None:
    _write_atomic(args.status, payload)
    if args.trigger == "launchd":
        _write_atomic(args.scheduled_status, payload)


def _base_payload(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "started_at": args.started_at,
        "finished_at": None,
        "trigger": args.trigger,
        "state": "running",
        "ok": None,
        "exit_code": None,
        "failed_phase": None,
        "args": args.refresh_args,
        "log": str(args.log),
        "scrape_ok": None,
        "scrape_exit_code": None,
        "sync_enabled": args.sync_enabled,
        "sync_attempted": False,
        "sync_ok": None,
        "sync_exit_code": None,
        "tail": _tail(args.log),
    }


def command_start(args: argparse.Namespace) -> int:
    _write_status(args, _base_payload(args))
    return 0


def command_finish(args: argparse.Namespace) -> int:
    payload = _base_payload(args)
    scrape_ok = args.scrape_code == 0
    sync_ok = args.sync_code == 0 if args.sync_attempted else None
    failed_phase = None
    exit_code = 0
    if not scrape_ok:
        failed_phase = "scrape"
        exit_code = args.scrape_code
    elif args.sync_attempted and not sync_ok:
        failed_phase = "sync"
        exit_code = args.sync_code

    payload.update(
        {
            "finished_at": args.finished_at,
            "state": "succeeded" if failed_phase is None else "failed",
            "ok": failed_phase is None,
            "exit_code": exit_code,
            "failed_phase": failed_phase,
            "scrape_ok": scrape_ok,
            "scrape_exit_code": args.scrape_code,
            "sync_attempted": args.sync_attempted,
            "sync_ok": sync_ok,
            "sync_exit_code": args.sync_code if args.sync_attempted else None,
            "tail": _tail(args.log),
        }
    )
    _write_status(args, payload)
    return 0


def _expected_schedule_date(now: datetime, deadline: time) -> object:
    if now.timetz().replace(tzinfo=None) >= deadline:
        return now.date()
    return (now - timedelta(days=1)).date()


def _parse_timestamp(value: str) -> datetime:
    """Parse ISO timestamps on Python 3.9, including basic UTC offsets such as +0800."""
    if len(value) >= 5 and value[-5] in "+-" and value[-3] != ":":
        value = f"{value[:-2]}:{value[-2:]}"
    return datetime.fromisoformat(value)


def command_check(args: argparse.Namespace) -> int:
    path = args.scheduled_status if args.scheduled else args.status
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        print(f"NOT_TRIGGERED status_missing path={path}")
        return EXIT_NOT_TRIGGERED
    except (json.JSONDecodeError, OSError) as error:
        print(f"INVALID_STATUS path={path} error={error}")
        return EXIT_INVALID_STATUS

    if args.scheduled:
        try:
            now = _parse_timestamp(args.now) if args.now else datetime.now().astimezone()
            started_at = _parse_timestamp(payload["started_at"])
            deadline = time.fromisoformat(args.deadline)
        except (KeyError, TypeError, ValueError) as error:
            print(f"INVALID_STATUS path={path} error={error}")
            return EXIT_INVALID_STATUS
        expected_date = _expected_schedule_date(now, deadline)
        if payload.get("trigger") != "launchd" or started_at.date() < expected_date:
            print(
                "NOT_TRIGGERED "
                f"expected_date={expected_date} last_started_at={payload.get('started_at')}"
            )
            return EXIT_NOT_TRIGGERED

    state = payload.get("state")
    if state == "running":
        print(f"RUNNING trigger={payload.get('trigger')} started_at={payload.get('started_at')}")
        return EXIT_RUNNING
    if state == "succeeded" and payload.get("ok") is True:
        print(f"OK trigger={payload.get('trigger')} finished_at={payload.get('finished_at')}")
        return 0
    if state == "failed" and payload.get("failed_phase") == "scrape":
        print(f"SCRAPE_FAILED exit_code={payload.get('exit_code')} log={payload.get('log')}")
        return EXIT_SCRAPE_FAILED
    if state == "failed" and payload.get("failed_phase") == "sync":
        print(f"SYNC_FAILED exit_code={payload.get('exit_code')} log={payload.get('log')}")
        return EXIT_SYNC_FAILED
    print(f"INVALID_STATUS path={path} state={state}")
    return EXIT_INVALID_STATUS


def _add_write_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--status", type=Path, required=True)
    parser.add_argument("--scheduled-status", type=Path, required=True)
    parser.add_argument("--trigger", choices=("manual", "launchd"), required=True)
    parser.add_argument("--args", dest="refresh_args", default="")
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--started-at", required=True)
    parser.add_argument("--sync-enabled", type=_bool, required=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    start = subparsers.add_parser("start")
    _add_write_arguments(start)
    start.set_defaults(handler=command_start)

    finish = subparsers.add_parser("finish")
    _add_write_arguments(finish)
    finish.add_argument("--finished-at", required=True)
    finish.add_argument("--scrape-code", type=int, required=True)
    finish.add_argument("--sync-attempted", type=_bool, required=True)
    finish.add_argument("--sync-code", type=int)
    finish.set_defaults(handler=command_finish)

    check = subparsers.add_parser("check")
    check.add_argument("--status", type=Path, default=Path("logs/last-status.json"))
    check.add_argument(
        "--scheduled-status",
        type=Path,
        default=Path("logs/last-launchd-status.json"),
    )
    check.add_argument("--scheduled", action="store_true")
    check.add_argument("--deadline", default="11:00")
    check.add_argument("--now", help="ISO timestamp override for deterministic checks")
    check.set_defaults(handler=command_check)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "finish" and args.sync_attempted and args.sync_code is None:
        raise SystemExit("--sync-code is required when --sync-attempted=1")
    return args.handler(args)


if __name__ == "__main__":
    sys.exit(main())
