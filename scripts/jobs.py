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
JOBS = (*WORKERS, "schedule-watchdog", "alert-watch")


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
def _environment():
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
        "CPBL_JOBS_MODE": "1", "PGAPPNAME": "cpbl-jobs",
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
            if key == "CPBL_JOBS_MODE" or key not in os.environ:
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
        self.lock = root / "locks" / ("refresh.lock" if job in WORKERS else job + ".lock")

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
    def locked(self):
        self.lock.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.lock.mkdir(mode=0o700)  # busy 即 75；不刪未知或舊 namespace 的 owner。
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


def _daily(run, args):
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
    code, _ = _invoke(run_refresh_recent.main, ["fast"] if args.fast else [], jobs=True)
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


def _weekly(run, args):
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
            else:
                from cpbl.ingest.cpbl_pitch_tracking import completed_game_snos, scrape_game_pitches
                snos = completed_game_snos(year, kind, None)
                result = scrape_game_pitches([(year, kind, sno) for sno in snos])
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


def _evening(run, args):
    """保留原晚間/先發/boxpa 狀態機，只把 Mac 同步交付換成同 DB 已提交證據。"""
    from cpbl.ingest import postseason_evening as evening

    def step(*argv):
        return _invoke(evening.main, list(argv), jobs=True)

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
        return code
    finish_code = 0
    try:
        code = _evening_active(run, evening, step, action)
    finally:
        finish_code, _ = step("finish")
    state = evening.load_state(evening.state_path())
    run.detail["halted"] = state.get("halted")
    errors = (state.get("last_run") or {}).get("errors") or state.get("signals_error")
    return code or finish_code or (69 if errors or state.get("halted") else 0)


def _evening_active(run, evening, step, action):
    outcome = "unchanged"
    partial = False
    if action == "scrape":
        code, outcome = step("scrape")
        if code:
            return code
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
        if act in ("detail", "tracking"):
            code, result = step("boxpa-" + act, "--games", keys)
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
    report = schedule_watch.evaluate_jobs(registry, CODE_ROOT, run.now,
                                          os.environ["CPBL_JOBS_API_URL"])
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

    alert_watch.run_once(CODE_ROOT, run.now, jobs=True,
                         config=alert_ping.load_config(use_environment=True), pinger=ping, armer=arm)
    state = alert_watch.load_json(run.root / "alert-watch/state.json")
    if not isinstance(state, dict) or state.get("observed_at") != run.now.isoformat():
        return 70
    return 1 if failures or state.get("evening_error") else 0


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
    evening = sub.add_parser("postseason-evening", allow_abbrev=False)
    evening.add_argument("--stage", choices=("all", "boxpa"), default="all")
    for name in ("weekly-box-revisions", "weekly-game-pitches"):
        weekly = sub.add_parser(name, allow_abbrev=False); weekly.add_argument("--year", type=int)
        if name == "weekly-box-revisions":
            weekly.add_argument("--days-back", type=int, default=30)
    sub.add_parser("schedule-watchdog", allow_abbrev=False); sub.add_parser("alert-watch", allow_abbrev=False)
    return parser


def main(argv=None):
    try:
        with contextlib.redirect_stderr(io.StringIO()):
            args = _parser().parse_args(argv)
    except SystemExit as error:
        if error.code:
            print(json.dumps({"error": "arguments", "exit_code": 64}))
        return 64 if error.code else 0
    if args.job in (*WORKERS, "alert-watch") and not os.environ.get("DATABASE_URL"):
        print(json.dumps({"job": args.job, "error": "explicit_database_required"})); return 64
    if args.job == "alert-watch" and not os.environ.get("REDIS_URL"):
        print(json.dumps({"job": args.job, "error": "redis_url_required"})); return 64
    if args.job in ("schedule-watchdog", "alert-watch") and not os.environ.get("CPBL_JOBS_API_URL"):
        print(json.dumps({"job": args.job, "error": "api_url_required"})); return 64
    code, run = 64, None
    try:
        with _environment() as (root, trigger):
            run = Run(args.job, root, trigger, datetime.now(TAIPEI))
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
                        with run.locked():
                            try:
                                run.record("running"); run.daily_ping("start")
                                if args.job == "scrape-daily":
                                    code = _daily(run, args)
                                elif args.job in ("weekly-box-revisions", "weekly-game-pitches"):
                                    code = _weekly(run, args)
                                elif args.job == "postseason-evening":
                                    code = _evening(run, args)
                                elif args.job == "schedule-watchdog":
                                    code = _watchdog(run, args)
                                else:
                                    code = _alert(run, args)
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
