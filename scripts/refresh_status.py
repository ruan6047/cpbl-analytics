#!/usr/bin/env python3
# LIFECYCLE: standing · 常設工具——這就是給你跑的；不要刪
"""Write and inspect machine-readable daily refresh status files.

兩種產物，語意不同，不要混用：

1. `logs/last-*.json`（`start`／`finish` 寫）——**最近一次**執行的完整快照，供人／AI
   接手診斷。只留一次，隔日的成功會把前一日的失敗覆寫掉。
2. `logs/schedule-history/<label>.jsonl`（本檔新增）——**append-only 歷史**，每次執行
   至少兩列（起跑 `running` ＋ 結束終態）。`scripts/schedule_watch.py` 靠它回頭判定
   「上一個應該完成的週期」跑了沒、跑成怎樣。

為什麼要第二種（OPS-SCHEDULE-FAILURE-BLIND1，#132）：2026-08-10 每日鏈失敗，隔日
08-11 的成功把 `last-launchd-status.json` 覆寫成 `succeeded`，於是任何只讀「最近一次」
的偵測器都會回報一切正常——那次失敗三天後才被人碰巧翻到。**缺席與失敗都只能從
「預期的節奏」反推，而節奏需要歷史。**

⚠️ 歷史紀錄**不含週期歸屬**（cycle）。cadence 的唯一事實來源是
`scripts/schedule-registry.json` ＋ plist，寫入端不複製一份會漂移的排程知識；週期歸屬
由讀取端（`schedule_watch.py`）依登記表計算。

⚠️ 歷史寫入失敗只警告不中斷：讓觀測器把被觀測的鏈弄掛是本末倒置。缺失的代價由
讀取端承擔——`schedule_watch.py` 對「該有紀錄而沒有」一律判 MISSING（fail closed）。
"""

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
EXIT_STALE_RUNNING = 7

HISTORY_SCHEMA_VERSION = 1
DEFAULT_HISTORY_DIR = Path("logs/schedule-history")
# `scrape-daily.sh` 不帶 `--history-label`（本卡不改那支，見 #132 資源宣告），故
# start／finish 的預設 label 就是每日鏈。與登記表的漂移由
# `tests/test_refresh_status.py::test_default_history_label_matches_registry` 擋住。
DEFAULT_HISTORY_LABEL = "com.cpbl.scrape-daily"
# 每 job 保留最近 400 列（日跑 2 列／次 ≈ 半年，週跑 ≈ 3.8 年），超過 500 列才壓實。
# 正常路徑是 O(1) append；400/500 是「涵蓋一次長假到整季回顧」的取捨，不是量測結果。
HISTORY_KEEP = 400
HISTORY_COMPACT_AT = 500
HISTORY_STATES = ("running", "succeeded", "failed", "skipped")


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


def history_path(history_dir: Path, label: str) -> Path:
    return history_dir / f"{label}.jsonl"


def _compact_history(path: Path) -> None:
    """超過 HISTORY_COMPACT_AT 列才重寫，保留最後 HISTORY_KEEP 列。

    壓實是唯一需要原子性的一步（`os.replace`）；正常 append 走 O_APPEND 單次 write，
    單列 < 1KB，不假設任何原子性保證——讀取端對無法解析的列跳過並計數。
    """
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines(True)
    except OSError:
        return
    if len(lines) <= HISTORY_COMPACT_AT:
        return
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False
    ) as handle:
        handle.writelines(lines[-HISTORY_KEEP:])
        temp_path = Path(handle.name)
    os.replace(temp_path, path)


def append_history(history_dir: Path, label: str, record: dict[str, Any]) -> bool:
    """Append 一列歷史。回傳是否成功——失敗只警告，絕不中斷呼叫端的排程鏈。"""
    path = history_path(history_dir, label)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
        _compact_history(path)
        return True
    except OSError as error:  # 觀測器不得把被觀測的鏈弄掛；讀取端會判 MISSING
        print(f"WARN 無法寫入排程歷史 path={path} error={error}", file=sys.stderr)
        return False


def _history_record(
    label: str,
    state: str,
    trigger: str,
    started_at: str,
    finished_at: object = None,
    exit_code: object = None,
    failed_phase: object = None,
    log: object = None,
    note: object = None,
) -> dict[str, Any]:
    return {
        "schema_version": HISTORY_SCHEMA_VERSION,
        "label": label,
        "state": state,
        "trigger": trigger,
        "started_at": started_at,
        "finished_at": finished_at,
        "exit_code": exit_code,
        "failed_phase": failed_phase,
        "log": str(log) if log is not None else None,
        "note": note,
        "observed_at": datetime.now().astimezone().strftime("%Y-%m-%dT%H:%M:%S%z"),
    }


def _write_status(args: argparse.Namespace, payload: dict[str, Any]) -> None:
    _write_atomic(args.status, payload)
    if args.trigger == "launchd":
        _write_atomic(args.scheduled_status, payload)
    append_history(
        args.history_dir,
        args.history_label,
        _history_record(
            args.history_label,
            payload["state"],
            payload["trigger"],
            payload["started_at"],
            finished_at=payload["finished_at"],
            exit_code=payload["exit_code"],
            failed_phase=payload["failed_phase"],
            log=payload["log"],
        ),
    )


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

    state = payload.get("state")
    now = None
    started_at = None
    if args.scheduled or state == "running":
        try:
            now = _parse_timestamp(args.now) if args.now else datetime.now().astimezone()
            started_at = _parse_timestamp(payload["started_at"])
        except (KeyError, TypeError, ValueError) as error:
            print(f"INVALID_STATUS path={path} error={error}")
            return EXIT_INVALID_STATUS

    if state == "running" and now is not None and started_at is not None:
        age = now - started_at
        if age > timedelta(minutes=args.running_timeout_minutes):
            print(
                "STALE_RUNNING "
                f"trigger={payload.get('trigger')} started_at={payload.get('started_at')} age={age}"
            )
            return EXIT_STALE_RUNNING

    if args.scheduled and now is not None and started_at is not None:
        try:
            deadline = time.fromisoformat(args.deadline)
        except ValueError as error:
            print(f"INVALID_STATUS path={path} error={error}")
            return EXIT_INVALID_STATUS
        expected_date = _expected_schedule_date(now, deadline)
        if payload.get("trigger") != "launchd" or started_at.date() < expected_date:
            print(
                "NOT_TRIGGERED "
                f"expected_date={expected_date} last_started_at={payload.get('started_at')}"
            )
            return EXIT_NOT_TRIGGERED

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


def command_history_append(args: argparse.Namespace) -> int:
    """供 shell wrapper 呼叫的獨立歷史寫入口（`start`／`finish` 已自動寫，不需再叫）。"""
    ok = append_history(
        args.history_dir,
        args.history_label,
        _history_record(
            args.history_label,
            args.state,
            args.trigger,
            args.started_at,
            finished_at=args.finished_at,
            exit_code=args.exit_code,
            failed_phase=args.failed_phase,
            log=args.log,
            note=args.note,
        ),
    )
    return 0 if ok else 0  # 寫入失敗已警告；呼叫端的排程結果不因觀測失敗而改變


def _add_history_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--history-dir", type=Path, default=DEFAULT_HISTORY_DIR)
    parser.add_argument("--history-label", default=DEFAULT_HISTORY_LABEL)


def _add_write_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--status", type=Path, required=True)
    parser.add_argument("--scheduled-status", type=Path, required=True)
    parser.add_argument("--trigger", choices=("manual", "launchd"), required=True)
    parser.add_argument("--args", dest="refresh_args", default="")
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--started-at", required=True)
    parser.add_argument("--sync-enabled", type=_bool, required=True)
    _add_history_arguments(parser)


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
    check.add_argument("--running-timeout-minutes", type=int, default=180)
    check.add_argument("--now", help="ISO timestamp override for deterministic checks")
    check.set_defaults(handler=command_check)

    history = subparsers.add_parser("history-append")
    _add_history_arguments(history)
    history.add_argument("--state", choices=HISTORY_STATES, required=True)
    history.add_argument("--trigger", choices=("manual", "launchd"), required=True)
    history.add_argument("--started-at", required=True)
    history.add_argument("--finished-at")
    history.add_argument("--exit-code", type=int)
    history.add_argument("--failed-phase")
    history.add_argument("--log")
    history.add_argument("--note")
    history.set_defaults(handler=command_history_append)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "finish" and args.sync_attempted and args.sync_code is None:
        raise SystemExit("--sync-code is required when --sync-attempted=1")
    return args.handler(args)


if __name__ == "__main__":
    sys.exit(main())
