#!/usr/bin/env python3
# LIFECYCLE: standing · 六個既有工作的 Linux 執行適配，不負責排程或取源清單協議。
"""#393 Linux jobs：沿原業務入口直寫同一 DB；排程生命週期由主站承接。"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import logging
import os
import signal
import stat
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
CODE_ROOT = HERE.parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
import alert_ping  # noqa: E402
import alert_watch  # noqa: E402
import refresh_status  # noqa: E402
import schedule_watch  # noqa: E402

TAIPEI = ZoneInfo("Asia/Taipei")
WORKERS = ("scrape-daily", "postseason-evening", "weekly-box-revisions", "weekly-game-pitches")
SCOPED_PUBLISHERS = (
    "weekly-pitches-only", "weekly-box-only", "daily-sabr-only", "daily-pitch-labels-only",
    "daily-current-only", "non-a-results-only", "daily-advanced-only", "daily-pa-only",
)
WRITERS = (*WORKERS, "features-only", "team-comparison-only", "evening-boxpa-only", "evening-inbox-dispatch", *SCOPED_PUBLISHERS)
JOBS = (*WRITERS, "schedule-watchdog", "alert-watch")
DATABASE_ENV = ("DATABASE_URL", "CPBL393_DATABASE_URL", "CPBL_FEATURE_PI_DATABASE_URL", "PGHOST",
                "PGHOSTADDR", "PGPORT", "PGUSER", "PGDATABASE", "PGPASSWORD", "PGPASSFILE",
                "PGSERVICE", "PGSERVICEFILE", "PGOPTIONS")


class Interrupted(BaseException):
    def __init__(self, code):
        self.code = code


def _invoke(main, argv, **kwargs):
    """只適配既有 Python CLI；輸出留在本次私有 log，不用 rc0 推定業務結果。"""
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        try:
            value = main(argv, **kwargs)
            code = int(value or 0)
        except SystemExit as exc:
            code = exc.code if type(exc.code) is int else (0 if exc.code is None else 1)
    output = stream.getvalue()
    print(output, end="")
    return code, output.strip()


@contextlib.contextmanager
def _environment(*, pi_handoff=False):
    root = Path(os.environ.get("CPBL_JOBS_STATE_DIR", ""))
    # 沿原相對 logs/data/artifacts 口徑；主站把私有 state volume 掛到 /app/logs。
    if not root.is_absolute() or root != CODE_ROOT / "logs" or root.is_symlink():
        raise ValueError("state_mount_must_be_code_root_logs")
    if os.path.lexists(CODE_ROOT / ".env"):
        raise ValueError("jobs_requires_protected_environment")
    trigger = os.environ.get("REFRESH_TRIGGER", "manual")
    if trigger not in ("manual", "jobs"):
        raise ValueError("invalid_jobs_trigger")
    defaults = {
        "CPBL_JOBS_MODE": "0" if pi_handoff else "1",
        "CPBL_JOBS_PI_HANDOFF": "1" if pi_handoff else "0", "PGAPPNAME": "cpbl-jobs",
        "POSTSEASON_STATE": str(root / "postseason-evening-state.json"),
        "POSTSEASON_STATUS": str(root / "last-postseason-evening.json"),
        "POSTSEASON_TODAY_SCHEDULE": str(root / "daily-schedule-today.json"),
        "POSTSEASON_STARTER_FLAG": str(root / "postseason-starter-checkpoints.enabled"),
        "POSTSEASON_STARTER_WATCH_FLAG": str(root / "starter-watch.enabled"),
        "POSTSEASON_STARTER_WATCH_ALERT": str(root / "starter-watch-alert.json"),
    }
    previous = {key: os.environ.get(key)
                for key in (*defaults, "DAILY_DAY_TYPE", "DAILY_CLOSED_LEAGUES")}
    cwd, mask = Path.cwd(), os.umask(0o077)
    try:
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        info = root.stat()
        if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
            raise ValueError("private_state_owner_or_mode")
        for key, value in defaults.items():
            if key in ("CPBL_JOBS_MODE", "CPBL_JOBS_PI_HANDOFF") or key not in os.environ:
                os.environ[key] = value
        os.chdir(CODE_ROOT)
        yield root, trigger
    finally:
        os.chdir(cwd)
        os.umask(mask)
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


class Run:
    """原 history schema/ping helper 的具名工作執行上下文，沒有自動重試/調度。"""

    def __init__(self, job, root, trigger, now):
        self.job, self.root, self.trigger, self.now = job, root, trigger, now
        self.label = "com.cpbl." + job
        self.started = now.isoformat()
        self.skipped = False
        self.detail = {}
        self.log = root / "jobs" / f"{job}-{now.strftime('%Y%m%d-%H%M%S-%f')}.log"
        self.lock = root / "locks" / ("refresh.lock" if job in WRITERS else job + ".lock")
        self.retain_lock = False

    def record(self, state, code=None):
        record = refresh_status._history_record(
            self.label, state, self.trigger, self.started,
            finished_at=datetime.now(TAIPEI).isoformat() if state != "running" else None,
            exit_code=code, failed_phase=self.detail.get("failed_phase"), log=str(self.log),
            note="intentional skip" if self.skipped else None,
        )
        if self.skipped and not code:
            record["skipped"] = True
        if not refresh_status.append_history(self.root / "schedule-history", self.label, record):
            raise OSError("history_write_failed")
        suffix = "" if self.trigger == "jobs" else "-manual"
        payload = {**record, "ok": None if state == "running" else code == 0,
                   "result": "running" if state == "running" else (
                       "ok" if code == 0 else "skipped" if code == 75 else "failed"), **self.detail}
        refresh_status._write_atomic(self.root / "jobs" / f"{self.job}{suffix}.json", payload)
        if self.job == "scrape-daily":
            refresh_status._write_atomic(self.root / "last-status.json", payload)
        elif self.job in ("weekly-box-revisions", "weekly-game-pitches"):
            name = ("last-weekly-box-revisions.json" if self.job == "weekly-box-revisions"
                    else "last-weekly-pitches.json")
            refresh_status._write_atomic(self.root / name, payload)

    @contextlib.contextmanager
    def locked(self, *, wait_seconds=0):
        self.lock.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        deadline = time.monotonic() + wait_seconds
        while True:
            try:
                self.lock.mkdir(mode=0o700)
                break
            except FileExistsError:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise  # busy 即 75；不刪未知或舊 namespace 的 owner。
                time.sleep(min(1, remaining))
        identity = self.lock.stat()
        pid = str(os.getpid())
        owned = False
        try:
            (self.lock / "pid").write_text(pid)
            (self.lock / "kind").write_text(self.label)
            owned = True
            yield
        finally:
            current = self.lock.stat()
            if (current.st_dev, current.st_ino) != (identity.st_dev, identity.st_ino):
                raise RuntimeError("lock_inode_changed")
            if owned and ((self.lock / "pid").read_text() != pid
                    or (self.lock / "kind").read_text() != self.label):
                raise RuntimeError("lock_owner_changed")
            if not self.retain_lock:
                (self.lock / "pid").unlink(missing_ok=True); (self.lock / "kind").unlink(missing_ok=True)
                self.lock.rmdir()

    def daily_ping(self, signal_value):
        if self.job == "scrape-daily" and self.trigger == "jobs":
            try:
                alert_ping.ping(alert_ping.load_config(use_environment=True), alert_ping.CHECK_DAILY,
                                signal_value, rid=alert_ping.run_id(self.started),
                                body=f"jobs scrape-daily signal={signal_value}")
            except Exception:
                logging.warning("daily ping failed")  # #358 fail-open；不用 key/log tail 當訊息。


def _features_only(run, *, verify_only, include_games=False):
    from cpbl.features.handoff import read_incoming_response

    result = {"job": run.job}
    acquired = False
    try:
        with run.locked():
            acquired = True
            manifest, rows, schedule = read_incoming_response(
                Path(os.environ["CPBL_JOBS_INBOX_ROOT"]),
                os.environ["CPBL_FEATURE_SOURCE_ID"],
                run.now.date(), include_games=include_games,
            )
            result.update(run_id=manifest["run_id"], result_sha256=manifest["result_sha256"],
                          response_sha256=manifest["response_sha256"])
            state = "verified" if verify_only else "published"
            receipts = run.root / f"features-{state}"
            if receipts.is_symlink():
                raise ValueError("feature_receipt_directory")
            receipts.mkdir(mode=0o700, exist_ok=True)
            receipt = receipts / f'{manifest["run_id"]}.json'
            if receipt.is_symlink():
                raise ValueError("feature_receipt_path")
            if receipt.exists():
                if not receipt.is_file() or json.loads(receipt.read_bytes()) != manifest:
                    raise ValueError("conflicting_feature_receipt")
                state = f"already_{state}"
            else:
                if datetime.now(TAIPEI).date() != run.now.date():
                    raise ValueError("feature_publication_crossed_midnight")
                if not verify_only:
                    from cpbl.db import conn
                    from cpbl.features.handoff import publish

                    try:
                        with conn() as connection:
                            # Keep the writer fence until the transaction and its receipt are confirmed.
                            run.retain_lock = True
                            if include_games:
                                publish(connection, rows, schedule=schedule)
                            else:
                                publish(connection, rows)
                    finally:
                        _close_pool(run)
                    if run.detail.get("close_failed"):
                        raise RuntimeError("feature_connection_exit_unknown")
                refresh_status._write_atomic(receipt, manifest)
                run.retain_lock = False
        code = 0
        result.update(state=state, row_count=manifest["row_count"])
    except Exception as exc:
        code = 75 if isinstance(exc, FileExistsError) and not acquired else 1
        result.update(state="busy" if code == 75 else "failed", error=type(exc).__name__,
                      lock_retained=run.retain_lock)
    print(json.dumps({**result, "exit_code": code}, sort_keys=True))
    return code


def _team_comparison_only(run, args):
    from cpbl.db import conn
    from cpbl.playoffs.team_comparison import handoff, sync

    result = {"job": run.job}
    acquired = False
    try:
        if args.wait_lock < 0:
            raise ValueError("invalid_summary_lock_wait")
        manifest, source = handoff.read_incoming(
            Path(os.environ["CPBL_JOBS_INBOX_ROOT"]), os.environ["CPBL_FEATURE_SOURCE_ID"], run.now.date(),
        )
        result.update(run_id=manifest["run_id"], snapshot_sha256=manifest["snapshot_sha256"])
        with run.locked(wait_seconds=args.wait_lock):
            acquired = True
            if datetime.now(TAIPEI).date() != run.now.date():
                raise ValueError("summary_publish_crossed_midnight")
            receipts = run.root / "team-comparison-published"
            if receipts.is_symlink():
                raise ValueError("summary_receipt_directory")
            receipts.mkdir(mode=0o700, exist_ok=True)
            receipt = receipts / f'{manifest["run_id"]}.json'
            if receipt.is_symlink():
                raise ValueError("summary_receipt_path")
            if receipt.exists():
                if not receipt.is_file() or json.loads(receipt.read_bytes()) != manifest:
                    raise ValueError("summary_conflicting_receipt")
                result.update(state="already_published")
            else:
                try:
                    with conn() as connection:
                        run.retain_lock = True
                        plan = handoff.publish(connection, source)
                except sync.SyncError as exc:
                    if exc.code in (sync.EXIT_REJECT, sync.EXIT_NO_TABLE):
                        run.retain_lock = False
                    raise
                finally:
                    _close_pool(run)
                if run.detail.get("close_failed"):
                    raise RuntimeError("summary_connection_exit_unknown")
                refresh_status._write_atomic(receipt, manifest)
                run.retain_lock = False
                result.update(state="published", plan=plan, reconciled=True)
        code = 0
    except Exception as exc:
        code = 75 if isinstance(exc, FileExistsError) and not acquired else 1
        result.update(state="busy" if code == 75 else "failed", error=type(exc).__name__,
                      lock_retained=run.retain_lock)
    print(json.dumps({**result, "exit_code": code}, sort_keys=True))
    return code


def _scoped_publish(run, args):
    from cpbl.db import conn
    from cpbl.ingest import (
        advanced_handoff,
        daily_current_handoff,
        daily_derived_handoff,
        daily_pa_handoff,
        weekly_box_handoff,
        weekly_pitches_handoff,
    )

    handlers = {
        "weekly-pitches-only": ("weekly-pitches", weekly_pitches_handoff.read_incoming, weekly_pitches_handoff.publish),
        "weekly-box-only": ("weekly-box", weekly_box_handoff.read_incoming, weekly_box_handoff.publish),
        "daily-sabr-only": ("daily-sabr", daily_derived_handoff.read_incoming, daily_derived_handoff.publish),
        "daily-pa-only": ("daily-pa", daily_pa_handoff.read_incoming, daily_pa_handoff.publish),
        "daily-pitch-labels-only": (
            "daily-pitch-labels", daily_derived_handoff.read_labels, daily_derived_handoff.publish_label_batch,
        ),
        "daily-current-only": ("daily-current", daily_current_handoff.read_current, daily_current_handoff.publish),
        "non-a-results-only": ("non-a-results", daily_current_handoff.read_results, daily_current_handoff.publish),
        "daily-advanced-only": ("daily-advanced", advanced_handoff.read_incoming, advanced_handoff.publish),
    }
    namespace, read_incoming, publish = handlers[run.job]

    result = {"job": run.job}
    acquired = False
    try:
        if args.wait_lock < 0:
            raise ValueError("invalid_scoped_lock_wait")
        manifest, rows = read_incoming(
            Path(os.environ["CPBL_JOBS_INBOX_ROOT"]), os.environ["CPBL_FEATURE_SOURCE_ID"], run.now.date(),
        )
        result.update(run_id=manifest["run_id"], snapshot_sha256=manifest["snapshot_sha256"])
        with run.locked(wait_seconds=args.wait_lock):
            acquired = True
            if datetime.now(TAIPEI).date() != run.now.date():
                raise ValueError("scoped_publish_crossed_midnight")
            receipts = run.root / f"{namespace}-published"
            if receipts.is_symlink():
                raise ValueError("scoped_receipt_directory")
            receipts.mkdir(mode=0o700, exist_ok=True)
            receipt = receipts / f'{manifest["run_id"]}.json'
            if receipt.is_symlink():
                raise ValueError("scoped_receipt_path")
            if receipt.exists():
                if not receipt.is_file():
                    raise ValueError("scoped_conflicting_receipt")
                prior = json.loads(receipt.read_bytes())
                if prior != manifest and prior.get("request") != manifest:
                    raise ValueError("scoped_conflicting_receipt")
                result.update(state="already_published")
            else:
                try:
                    with conn() as connection:
                        run.retain_lock = True
                        counts = publish(connection, rows)
                finally:
                    _close_pool(run)
                if run.detail.get("close_failed"):
                    raise RuntimeError("scoped_connection_exit_unknown")
                state = "published" if any(counts.values()) else "no_observations"
                refresh_status._write_atomic(receipt, {
                    "version": 1, "request": manifest, "state": state, "rows": counts,
                    "committed_at": datetime.now(TAIPEI).isoformat(),
                })
                run.retain_lock = False
                result.update(state=state, rows=counts, reconciled=True)
        code = 0
    except Exception as exc:
        code = 75 if isinstance(exc, FileExistsError) and not acquired else 1
        result.update(state="busy" if code == 75 else "failed", error=type(exc).__name__,
                      lock_retained=run.retain_lock)
    print(json.dumps({**result, "exit_code": code}, sort_keys=True))
    return code



def _evening_boxpa_only(run, args):
    from cpbl.db import conn
    from cpbl.ingest import boxpa_sync, evening_handoff, evening_results_handoff

    result = {"job": run.job, "batch_id": args.batch_id}
    acquired = False
    try:
        source = os.environ["CPBL_FEATURE_SOURCE_ID"]
        response, keys, snapshot = evening_handoff.read_incoming(
            Path(os.environ["CPBL_JOBS_INBOX_ROOT"]), source, run.now.date(), args.batch_id,
        )
        results = response["parts"] in evening_results_handoff.PARTS
        receipts = run.root / "evening-boxpa-published"
        receipt = evening_handoff.receipt_path(receipts, source, args.batch_id)
        with run.locked():
            acquired = True
            if datetime.now(TAIPEI).date() != run.now.date():
                raise ValueError("evening_publish_crossed_midnight")
            receipt.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            if os.path.lexists(receipt):
                old = evening_handoff.read_receipt(receipts, source, args.batch_id)
                if old["response_sha256"] != response["response_sha256"]:
                    raise ValueError("evening_receipt_conflict")
                result.update(state="already_published")
            else:
                field_plans = None
                if results:
                    from cpbl.features.handoff import _need

                    _need(isinstance(snapshot, dict) and set(snapshot) == {"columns", "data", "fields", "assessment"}
                          and isinstance(snapshot["assessment"], dict)
                          and set(snapshot["assessment"]) == {"batch_id", "response_sha256"},
                          "evening_results_assessment_required")
                    reference = snapshot["assessment"]
                    binding, _, field_plans = evening_handoff.result_binding(source, reference["batch_id"], run.now)
                    _need(binding["response_sha256"] == reference["response_sha256"]
                          and set(response["parts"]) <= set(binding["parts"])
                          and {key.text for key in keys} <= field_plans.keys(),
                          "evening_results_assessment_identity")
                attempt = receipt.with_suffix(".attempt")
                try:
                    with conn() as connection:
                        if not results:
                            evening_handoff.require_final(connection, keys)
                        with attempt.open("x") as handle:
                            handle.write(response["response_sha256"] + "\n")
                            handle.flush()
                            os.fsync(handle.fileno())
                        evening_handoff.sync_directory(receipt.parent)
                        run.retain_lock = True
                        if results:
                            manifest = evening_results_handoff.publish(
                                connection, keys, response["parts"], snapshot, field_plans=field_plans,
                            )
                        else:
                            manifest = evening_handoff.publish(connection, keys, response["parts"], snapshot)
                finally:
                    _close_pool(run)
                if run.detail.get("close_failed"):
                    raise RuntimeError("evening_connection_exit_unknown")
                evening_handoff.write_receipt(receipt, response, manifest, datetime.now(TAIPEI))
                run.retain_lock = False
                result.update(state="published" if manifest["delivery_mode"] == "committed" else "reused_existing")
        code = 0
    except boxpa_sync.SyncError as exc:
        code = exc.code
        result.update(state="waiting" if code == boxpa_sync.EXIT_NOT_FINAL else "failed",
                      lock_retained=run.retain_lock)
    except Exception as exc:
        code = 75 if isinstance(exc, FileExistsError) and not acquired else 1
        result.update(state="busy" if code == 75 else "failed", error=type(exc).__name__,
                      lock_retained=run.retain_lock)
    print(json.dumps({**result, "exit_code": code}, sort_keys=True))
    return code


def _evening_inbox_dispatch(run, args):
    from cpbl.ingest import boxpa_sync, evening_handoff

    result = {"job": run.job, "finished": [], "waiting": [], "unattempted": []}
    try:
        if args.limit < 1:
            raise ValueError("evening_dispatch_limit")
        queue = evening_handoff.pending_batches(
            Path(os.environ["CPBL_JOBS_INBOX_ROOT"]), run.root / "evening-boxpa-published",
            os.environ["CPBL_FEATURE_SOURCE_ID"], run.now,
        )
    except evening_handoff.DispatchBlocked as exc:
        print(json.dumps({**result, "exit_code": 1, "stopped_at": exc.batch_id, "reason": str(exc)}, sort_keys=True))
        return 1
    except (OSError, TypeError, KeyError, ValueError) as exc:
        print(json.dumps({**result, "exit_code": 1, "error": type(exc).__name__}, sort_keys=True))
        return 1

    code = 0
    for index, name in enumerate(queue[:args.limit]):
        code = _evening_boxpa_only(run, argparse.Namespace(batch_id=name))
        if code == boxpa_sync.EXIT_NOT_FINAL:
            result["waiting"].append(name)
            code = 0
        elif code:
            result["unattempted"] = queue[index + 1:]
            result["stopped_at"] = name
            break
        else:
            result["finished"].append(name)
    else:
        result["unattempted"] = queue[args.limit:]
    print(json.dumps({**result, "exit_code": code}, sort_keys=True))
    return code


def _daily(run, args, *, pi_batch=None):
    """解除原 daily 的 uv/本機容器/同步/自動訓練依賴，沿用既有日型與業務步驟。"""
    from cpbl.features import run_build_features
    from cpbl.ingest import daily_gate, run_build_team_comparison, run_refresh_recent

    day_type, closed = "full", ""
    marker = run.root / "daily-sync-marker.json"
    today_file = run.root / "daily-schedule-today.json"
    if os.environ.get("DAILY_FORCE_FULL") != "1":
        code, output = _invoke(daily_gate.main, ["decide", "--history",
                              str(run.root / "schedule-history" / (run.label + ".jsonl")),
                              "--sync-marker", str(marker), "--today-file", str(today_file),
                              "--started-at", run.started])
        values = dict(line.split("=", 1) for line in output.splitlines() if "=" in line)
        if code == 0 and values.get("DAY_TYPE") in ("full", "light", "sync_only", "skip"):
            day_type, closed = values["DAY_TYPE"], values.get("CLOSED_LEAGUES", "")
        else:
            today_file.unlink(missing_ok=True)  # 沿原失敗退 full，不沿舊賽程檔。
    run.detail.update(day_type=day_type, closed_leagues=closed)
    if day_type == "skip":
        run.skipped = True
        return 0
    os.environ["DAILY_DAY_TYPE"], os.environ["DAILY_CLOSED_LEAGUES"] = day_type, closed
    delivery = {"on_handoff": pi_batch.daily_written} if pi_batch is not None else {}
    code, _ = _invoke(run_refresh_recent.main, ["fast"] if args.fast else [], jobs=True, **delivery)
    run.detail["refresh_exit_code"] = code
    if day_type != "sync_only":
        _invoke(daily_gate.main, ["today-schedule", "--out", str(today_file),
                                "--day-type", day_type, "--stage", "after_scrape"])
    if code not in (0, 69):
        return code
    team_code, _ = _invoke(run_build_team_comparison.main,
                           ["--year", str(run.now.year), "--record-failure"])
    run.detail["team_comparison_exit_code"] = team_code
    feature_code, _ = _invoke(run_build_features.main, ["--jobs"])
    run.detail["features_exit_code"] = feature_code
    overall = code or feature_code or (69 if team_code else 0)
    if pi_batch is not None:
        return overall
    # 原 recent 及 prod-sync 使用同一個已審寫入函式；不是再同步到另一顆 DB。
    day = run.now.date()
    counts = run_refresh_recent._recent_counts(day.year, [day - timedelta(days=1), day])
    run_refresh_recent._log_refresh("prod-sync", day - timedelta(days=1), day,
                                   sum(row[1] for row in counts), sum(row[2] for row in counts),
                                   {"mode": "jobs", **run.detail}, overall == 0,
                                   None if overall == 0 else "jobs step failed")
    if overall == 0:
        _invoke(daily_gate.main, ["mark-synced", "--sync-marker", str(marker)])
    return overall


def _closed():
    from cpbl import season_close
    return season_close.closed_leagues(season_close.league_closure())


def _weekly(run, args, *, pitch_sink=None, box_sink=None):
    """解除兩支週跑的 uv/Docker 前置；同一組原選場/爬寫函式，不做 migrate。"""
    closed, code = _closed(), 0
    year = run.now.year if args.year is None else args.year
    run.detail["year"] = year
    for kind, league in (("A", "major"), ("D", "farm")):
        if league in closed:
            continue
        try:
            if run.job == "weekly-box-revisions":
                from cpbl.ingest.cpbl_gamelog import completed_snos_within_days, scrape_gamelogs
                snos = completed_snos_within_days(year, kind, args.days_back)
                result = scrape_gamelogs(year, snos, kind, delay=1.2)
                if box_sink is not None and snos and result["games"] == len(snos) and not result["failed"]:
                    box_sink(year, kind, snos)
            else:
                from cpbl.ingest.cpbl_pitch_tracking import completed_game_snos, scrape_game_pitches
                snos = completed_game_snos(year, kind, None)
                options = {"on_game_written": pitch_sink} if pitch_sink is not None else {}
                result = scrape_game_pitches([(year, kind, sno) for sno in snos], **options)
                if result.get("games", 0) + result.get("skipped_frozen", 0) != len(snos):
                    code = 69  # 原函式容錯跳場，不把未完成的整輪記成成功。
        except Exception:
            logging.exception("weekly step failed")
            code = 69
            continue
        print("done:", result)  # 保留既有 J3 log 計數口徑；只到私有 log。
        if result.get("errors"):
            code = 69
    run.skipped = len(closed) == 2
    return code


def _direct_boxpa(keys, parts):
    """同一正式 DB 的已提交資料，沿原 reconcile 建證據；不複製資料、不造 delivered。"""
    from cpbl.db import conn
    from cpbl.ingest import boxpa_sync

    class Reader:
        def __init__(self, cursor):
            self.cursor = cursor

        def read(self, sql):
            return [["" if v is None else str(v) for v in row]
                    for row in self.cursor.execute(sql).fetchall()]

    parsed = boxpa_sync.parse_games(keys)
    with conn() as connection:
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        reader = Reader(connection.cursor())
        published = boxpa_sync.published_builds(reader, parsed)
        manifest = boxpa_sync.reconcile(reader, reader, parsed,
                                        published if "pa" in parts.split(",") else (), parts.split(","))
    manifest["delivery_mode"] = "direct"
    return manifest


def _evening(run, args, *, pi_batch=None):
    """保留原晚間/先發/boxpa 狀態機，只把 Mac 同步交付換成同 DB 已提交證據。"""
    from cpbl.ingest import postseason_evening as evening

    def step(*argv):
        return _invoke(evening.main, list(argv), jobs=True)

    if pi_batch is not None:
        from pi_evening_handoff import poll
        from pi_night_results import before_worker

        receipt_status = poll(pi_batch)
        if receipt_status != "idle":
            return 0 if receipt_status in ("recorded", "waiting") else 69
        if args.stage == "all":
            result = before_worker(pi_batch, step)
            if result is not None:
                return result

    code, action = step("plan") if args.stage == "all" else (0, "idle")
    if code:
        return code
    if action == "quiet":
        run.skipped = True
        return 0
    if action == "halted":
        run.detail["halted"] = evening.load_state(evening.state_path()).get("halted")
        return 69
    code, pre = step("boxpa-plan", "--dry")
    if code:
        return code
    if action in ("idle", "halted") and not pre.startswith(("detail", "sync", "tracking", "build")):
        # plan 可能已寫訊號失敗；boxpa-only 沒跑 plan，不結算前輪的 signals_error。
        state = evening.load_state(evening.state_path())
        if args.stage == "all" and state.get("signals_error"):
            return 69
        if pi_batch is None or not pi_batch.night_results or not state.get("signals_dirty"):
            return code
    finish_code = 0
    try:
        code = (_evening_active(run, evening, step, action, pi_batch=pi_batch)
                if pi_batch is not None else _evening_active(run, evening, step, action))
    finally:
        finish_code, _ = step("finish")
    state = evening.load_state(evening.state_path())
    run.detail["halted"] = state.get("halted")
    errors = (state.get("last_run") or {}).get("errors") or state.get("signals_error")
    return code or finish_code or (69 if errors or state.get("halted") else 0)


def _evening_active(run, evening, step, action, *, pi_batch=None):
    outcome = "unchanged"
    partial = False
    if pi_batch is not None and pi_batch.night_results and action in ("scrape", "idle"):
        from pi_night_source import acquire

        outcome = acquire(pi_batch, schedules=action == "scrape")
    elif action == "scrape":
        code, outcome = step("scrape")
        if code:
            return code
    if pi_batch is not None and pi_batch.night_results:
        from pi_night_results import after_worker

        result = after_worker(pi_batch, expected=action == "sync" or outcome == "changed")
        if result is not None:
            return result
    if action == "sync" or outcome == "changed":
        code, delivered = step("record-sync", "--code", "0")
        if code or delivered != "synced":
            return code or 69
    code, plan = step("boxpa-plan")
    if code:
        return code
    fields = plan.split()
    if fields and fields[0] in ("detail", "tracking", "build", "sync"):
        act, keys = fields[0], fields[1]
        if pi_batch is not None and act in ("detail", "tracking"):
            from pi_evening_handoff import source_decision

            decision, selected = source_decision(pi_batch, keys, act)
            run.detail["evening_handoff"] = decision
            if not selected:
                return 0 if decision["state"] == "reused_existing" else 69
            keys = ",".join(selected)
        if pi_batch is not None and act == "sync":
            from pi_evening_handoff import send

            return send(pi_batch, keys, fields[2])
        if act in ("detail", "tracking"):
            www_only = ("--www-only",) if pi_batch is not None and act == "detail" else ()
            code, result = step("boxpa-" + act, "--games", keys, *www_only)
            if code:
                return code
            partial = result == "failed"
        code, result = step("boxpa-prepare", "--games", keys)
        if code:
            return code
        try:
            prepared = json.loads(result)
        except ValueError:
            return 69
        partial = partial or bool(prepared.get("error") or prepared.get("errors"))
        # PA 失敗不擋既有 box 交付；保留 partial，最終不可被 rc0/完成收據吞掉。
        code, plan = step("boxpa-plan")
        fields = plan.split()
        if code:
            return code
        if fields and fields[0] == "sync":
            _, keys, parts = fields
            if pi_batch is not None:
                from pi_evening_handoff import send

                return send(pi_batch, keys, parts)
            started = time.monotonic()
            try:
                manifest = _direct_boxpa(keys, parts)
            except Exception:
                logging.exception("direct reconcile failed")
                state = evening.load_state(evening.state_path())
                evening.boxpa_record_sync(state, datetime.now(TAIPEI), keys.split(","), 74,
                                          None, time.monotonic() - started, parts.split(","))
                evening.save_json(evening.state_path(), state)
                return 74
            mpath = run.root / "postseason-direct-manifest.json"
            evening.save_json(mpath, manifest)
            rc = 0 if manifest.get("ok") else 68
            code, result = step("boxpa-record", "--games", keys, "--parts", parts,
                                "--manifest", str(mpath), "--code", str(rc),
                                "--elapsed", str(time.monotonic() - started))
            if code or result == "halted":
                return code or 69
            if rc:
                return rc
    return 69 if outcome == "failed" or partial else 0


def _watchdog(run, args):
    """沿原週期判定讀 jobs history，移除 launchd/plist/桌面通知依賴。"""
    registry = json.loads((HERE / "schedule-registry.json").read_text())
    all_receipts = getattr(args, "handoff_receipts", False)
    feature_source = os.environ.get("CPBL_FEATURE_SOURCE_ID", "") if args.feature_receipts or all_receipts else None
    kwargs = {"feature_source": feature_source}
    if all_receipts:
        inbox = os.environ.get("CPBL_JOBS_INBOX_ROOT", "")
        kwargs["handoff_inbox"] = Path(inbox) if inbox else Path(".")
    report = schedule_watch.evaluate_jobs(registry, CODE_ROOT, run.now, os.environ["CPBL_JOBS_API_URL"], **kwargs)
    refresh_status._write_atomic(run.root / "schedule-watchdog/last-run.json", report)
    path = run.root / "schedule-alert.json"
    if report["exit_code"]:
        refresh_status._write_atomic(path, report)
    else:
        path.unlink(missing_ok=True)
    return int(report["exit_code"])


def _alert(run, args):
    """重用原四 check/兩次確認/晚間武裝，Linux 只讀服務健康，不控制容器。"""
    failures = []

    def ping(*argv, **kwargs):
        result = alert_ping.ping(*argv, **kwargs)
        if not result.ok:
            failures.append(True)
        return result

    def arm(*argv, **kwargs):
        result = alert_ping.arm_schedule(*argv, **kwargs)
        if not result.ok:
            failures.append(True)
        return result

    alert_watch.run_once(CODE_ROOT, run.now, jobs=True, only="services" if args.services_only else None,
                         config=alert_ping.load_config(use_environment=True), pinger=ping, armer=arm)
    state = alert_watch.load_json(run.root / "alert-watch/state.json")
    if not isinstance(state, dict) or state.get("observed_at") != run.now.isoformat():
        return 70
    return 1 if failures or (not args.services_only and state.get("evening_error")) else 0


def _close_pool(run):
    db = sys.modules.get("cpbl.db")
    if db is not None and db._pool is not None:
        try:
            db._pool.close()
            db._pool = None
        except Exception:
            logging.exception("jobs pool close failed")
            run.detail["close_failed"] = True


def _parser():
    parser = argparse.ArgumentParser(prog="jobs.py", description=__doc__, allow_abbrev=False)
    sub = parser.add_subparsers(dest="job", required=True)
    daily = sub.add_parser("scrape-daily", allow_abbrev=False); daily.add_argument("--fast", action="store_true")
    daily.add_argument("--pi-handoff", type=float, metavar="SEND_TIMEOUT")
    features = sub.add_parser("features-only", allow_abbrev=False)
    features.add_argument("--verify-only", action="store_true")
    features.add_argument("--include-games", action="store_true")
    summary = sub.add_parser("team-comparison-only", allow_abbrev=False)
    summary.add_argument("--wait-lock", type=int, default=0)
    for name in SCOPED_PUBLISHERS:
        scoped = sub.add_parser(name, allow_abbrev=False)
        scoped.add_argument("--wait-lock", type=int, default=0)
    receiver = sub.add_parser("evening-boxpa-only", allow_abbrev=False)
    receiver.add_argument("--batch-id", required=True)
    dispatch = sub.add_parser("evening-inbox-dispatch", allow_abbrev=False)
    dispatch.add_argument("--limit", required=True, type=int)
    evening = sub.add_parser("postseason-evening", allow_abbrev=False)
    evening.add_argument("--stage", choices=("all", "boxpa"), default="all")
    evening.add_argument("--pi-handoff", type=float, metavar="SEND_TIMEOUT")
    for name in ("weekly-box-revisions", "weekly-game-pitches"):
        weekly = sub.add_parser(name, allow_abbrev=False); weekly.add_argument("--year", type=int)
        weekly.add_argument("--pi-handoff", type=float, metavar="SEND_TIMEOUT")
        if name == "weekly-box-revisions":
            weekly.add_argument("--days-back", type=int, default=30)
    watchdog = sub.add_parser("schedule-watchdog", allow_abbrev=False)
    watchdog.add_argument("--feature-receipts", action="store_true")
    watchdog.add_argument("--handoff-receipts", action="store_true")
    alert = sub.add_parser("alert-watch", allow_abbrev=False)
    alert.add_argument("--services-only", action="store_true")
    return parser


def main(argv=None):
    try:
        with contextlib.redirect_stderr(io.StringIO()):
            args = _parser().parse_args(argv)
    except SystemExit as error:
        if error.code:
            print(json.dumps({"error": "arguments", "exit_code": 64}))
        return 64 if error.code else 0
    verify_only = args.job == "features-only" and args.verify_only
    if verify_only and any(name in os.environ for name in DATABASE_ENV):
        print(json.dumps({"job": args.job, "error": "verify_requires_no_database_environment", "exit_code": 64}))
        return 64
    if not verify_only and args.job in (*WRITERS, "alert-watch") and not os.environ.get("DATABASE_URL"):
        print(json.dumps({"job": args.job, "error": "explicit_database_required"})); return 64
    if args.job == "alert-watch" and not os.environ.get("REDIS_URL"):
        print(json.dumps({"job": args.job, "error": "redis_url_required"})); return 64
    if args.job in ("schedule-watchdog", "alert-watch") and not os.environ.get("CPBL_JOBS_API_URL"):
        print(json.dumps({"job": args.job, "error": "api_url_required"})); return 64
    code, run = 64, None
    pi_timeout = getattr(args, "pi_handoff", None)
    try:
        environment = _environment(pi_handoff=True) if pi_timeout is not None else _environment()
        with environment as (root, trigger):
            run = Run("features-verify" if verify_only else args.job, root, trigger, datetime.now(TAIPEI))
            if args.job == "features-only":
                return _features_only(run, verify_only=verify_only, include_games=args.include_games)
            if args.job == "team-comparison-only":
                return _team_comparison_only(run, args)
            if args.job == "evening-boxpa-only":
                return _evening_boxpa_only(run, args)
            if args.job == "evening-inbox-dispatch":
                return _evening_inbox_dispatch(run, args)
            if args.job in SCOPED_PUBLISHERS:
                return _scoped_publish(run, args)

            from cpbl.ingest._job_source import job_source

            run.log.parent.mkdir(parents=True, exist_ok=True)
            with run.log.open("a") as log, contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
                logger = logging.getLogger(); old_handlers, old_level = logger.handlers[:], logger.level
                logger.handlers = [logging.StreamHandler(log)]; logger.setLevel(logging.INFO)
                handlers = {s: signal.getsignal(s) for s in (signal.SIGINT, signal.SIGTERM)}
                try:
                    def interrupted(number, frame):
                        raise Interrupted(128 + number)
                    for sig in handlers:
                        signal.signal(sig, interrupted)
                    try:
                        with run.locked(), job_source(run.job, run.root) as source:
                            try:
                                batch = None
                                if pi_timeout is not None:
                                    from pi_job_handoff import PiJobHandoff

                                    batch = PiJobHandoff(run, pi_timeout)
                                run.record("running")
                                if batch is None:
                                    run.daily_ping("start")
                                if args.job == "scrape-daily":
                                    code = _daily(run, args, pi_batch=batch) if batch is not None else _daily(run, args)
                                elif args.job in ("weekly-box-revisions", "weekly-game-pitches"):
                                    code = (_weekly(run, args, pitch_sink=batch.pitch_written, box_sink=batch.box_written)
                                            if batch is not None else _weekly(run, args))
                                elif args.job == "postseason-evening":
                                    code = (_evening(run, args, pi_batch=batch)
                                            if batch is not None else _evening(run, args))
                                elif args.job == "schedule-watchdog":
                                    code = _watchdog(run, args)
                                else:
                                    code = _alert(run, args)
                                if source.failed and code == 0:
                                    code = 69  # 原葉函式可容錯；供給失敗不可因上層吞錯記成功。
                                if batch is not None and code == 0 and not run.skipped and args.job != "postseason-evening":
                                    run.detail["pi_handoff"] = batch.send()
                            finally:
                                _close_pool(run)
                    except FileExistsError:
                        code = 75
                    except Interrupted as error:
                        code = error.code
                    except Exception as error:
                        logging.exception("jobs step failed")
                        run.detail["failed_phase"] = type(error).__name__; code = 1
                    if run.detail.get("close_failed") and code == 0:
                        code = 1
                    run.record("succeeded" if code == 0 else ("skipped" if code == 75 else "failed"), code)
                    if pi_timeout is None:
                        run.daily_ping(code)
                finally:
                    for sig, handler in handlers.items():
                        signal.signal(sig, handler)
                    logger.handlers, logger.level = old_handlers, old_level
    except (OSError, ValueError) as error:
        code = 70 if run else 64
        print(json.dumps({"job": args.job, "error": type(error).__name__, "exit_code": code}))
        return code
    print(json.dumps({"job": args.job, "mode": "jobs", "exit_code": code,
                      "state": "succeeded" if code == 0 else "skipped" if code == 75 else "failed"}))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
