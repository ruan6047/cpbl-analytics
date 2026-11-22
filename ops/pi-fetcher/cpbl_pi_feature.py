"""Refresh a Pi-private database and optionally send its daily feature result.

The existing WWW sender and scheduler retain their original entrypoints.
"""

from __future__ import annotations

import argparse
import importlib.util
import io
import json
import math
import os
import re
import stat
import subprocess
import sys
import time
from contextlib import contextmanager, nullcontext, redirect_stderr, redirect_stdout
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

TAIPEI = ZoneInfo("Asia/Taipei")
SOURCE_BOX_TABLES = ("batting_gamelog", "pitching_gamelog")
EXIT_RESERVE_SECONDS = 10  # Same TERM/KILL wait budget as the original sender.

_spec = importlib.util.spec_from_file_location(
    "cpbl_feature_original_sender", Path(__file__).with_name("cpbl_pi_send.py")
)
sender = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sender)


def _publication_batch(run, *, notify=False, include_games=False):
    """The response is committed only after the result's final name exists."""
    if not re.fullmatch(r"[0-9a-f]{32}", run):
        raise ValueError("invalid_run_id")
    parent = f"/incoming/features/{run}"
    commands = (
        f"mkdir {parent}\n"
        f'put "result.json.gz" {parent}/.result.json.gz.upload\n'
        f"rename {parent}/.result.json.gz.upload {parent}/result.json.gz\n"
    )
    if include_games:
        commands += (
            f'put "schedule.json" {parent}/.schedule.json.upload\n'
            f"rename {parent}/.schedule.json.upload {parent}/schedule.json\n"
        )
    commands += (
        f'put "response.json" {parent}/.response.json.upload\n'
        f"rename {parent}/.response.json.upload {parent}/response.json\n"
    )
    if notify:
        commands += (
            f'put "notification.json" {parent}/.ready.upload\n'
            f"rename {parent}/.ready.upload /incoming/feature-notify/{run}.ready\n"
        )
    return commands.encode("ascii")


def _private_environment():
    from psycopg.conninfo import conninfo_to_dict

    dsn = os.environ.get("CPBL_FEATURE_PI_DATABASE_URL", "")
    params = conninfo_to_dict(dsn)
    host = params.get("host", "")
    port = params.get("port", "5432")
    if (not host.startswith("/") or "," in host
            or params.get("dbname") != "cpbl393_feature_bench"
            or set(params) - {"host", "port", "dbname", "user", "password", "connect_timeout"}
            or not re.fullmatch("[0-9]{1,5}", port) or not 1 <= int(port) <= 65535):
        raise ValueError("private_pi_socket_dsn_required")
    path = Path(host)
    if path.resolve(strict=True) != path:
        raise ValueError("private_pi_socket_path_required")
    sender._private(path, directory=True)
    info = (path / f".s.PGSQL.{port}").lstat()
    if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.getuid():
        raise ValueError("private_pi_socket_required")
    browser = {name: os.environ[name] for name in (
        "PLAYWRIGHT_BROWSERS_PATH", "XDG_CACHE_HOME", "XDG_CONFIG_HOME",
    ) if name in os.environ}
    return {
        **browser, "PATH": os.defpath, "LANG": "C.UTF-8", "TZ": "Asia/Taipei",
        "CPBL_FEATURE_PI_DATABASE_URL": dsn, "DATABASE_URL": dsn,
    }


def _replay_schedule(as_of, manifest, bundle, *, schedule_sink=None):
    from cpbl.ingest import run_replay_games

    sender._private(manifest)
    sender._private(bundle, directory=True)
    sender._private(bundle / "index.json")
    with (bundle / "index.json").open("rb") as stream:
        raw = stream.read(sender.fetch.MAX_INDEX_BYTES + 1)
    if len(raw) > sender.fetch.MAX_INDEX_BYTES:
        raise ValueError("schedule_bundle_size")
    finished = datetime.fromisoformat(json.loads(raw)["ended_at"])
    if (finished.utcoffset() is None or finished.astimezone(TAIPEI).date() != as_of
            or finished > datetime.now(UTC)):
        raise ValueError("schedule_bundle_day")
    output = io.StringIO()
    with redirect_stdout(output):
        rc = run_replay_games.main([
            "--year", str(as_of.year), "--kind", "A", "--manifest", str(manifest), "--bundle", str(bundle),
        ], **({"schedule_sink": schedule_sink} if schedule_sink is not None else {}))
    result = json.loads(output.getvalue())
    if (rc != 0 or result.get("ok") is not True or result.get("contract_passed") is not True
            or result.get("stage") != "complete" or not result.get("written_count")
            or result.get("index_sha256") != sender.fetch.digest(raw)):
        raise ValueError("schedule_replay_incomplete")


class _SourceStopped(BaseException):
    """Exit the single-attempt operator run before the box fetcher's recovery path."""


@contextmanager
def _one_source_attempt():
    from cpbl.ingest import _browser

    old_backoffs = _browser._BACKOFF_MS
    new_context = _browser._Session._new_context
    post = _browser._Session.post

    def first_context(session):
        if getattr(session, "_ctx", None) is not None:
            raise _SourceStopped("browser_context_retry_disabled")
        return new_context(session)

    def first_post(session, *args, **kwargs):
        try:
            status, raw = post(session, *args, **kwargs)
        except Exception as exc:
            raise _SourceStopped("official_post_failed") from exc
        if status != 200:
            raise _SourceStopped("official_post_failed")
        return status, raw

    _browser._BACKOFF_MS = ()
    _browser._Session._new_context = first_context
    _browser._Session.post = first_post
    try:
        yield
    finally:
        _browser._BACKOFF_MS = old_backoffs
        _browser._Session._new_context = new_context
        _browser._Session.post = post


def _local_refresh(as_of, manifest, bundle, *, source_once=False, schedule_output=None):
    # The child repeats the socket check before importing any writer.
    env = _private_environment()
    if (os.path.lexists(".env") or os.environ.get("DATABASE_URL") != env["DATABASE_URL"]
            or as_of != datetime.now(TAIPEI).date()):
        raise ValueError("private_refresh_environment")
    from cpbl.ingest import cpbl_gamelog, cpbl_site, run_refresh_recent

    def capture(rows):
        _save(schedule_output.parent, schedule_output.name, rows)

    options = {"schedule_sink": capture} if schedule_output is not None else {}
    with _one_source_attempt() if source_once else nullcontext():
        if manifest is not None:
            _replay_schedule(as_of, manifest, bundle, **options)
        else:
            written = cpbl_site.scrape_games(as_of.year, as_of.year, "A", **options)
            if not written.get(as_of.year):
                raise ValueError("empty_schedule_refresh")

        days = [as_of - timedelta(days=1), as_of]
        games = sorted(set(run_refresh_recent._completed_snos(as_of.year, days, "A"))
                       | set(run_refresh_recent._missing_gamelog_snos(as_of.year, "A")))
        if games:
            result = cpbl_gamelog.scrape_gamelogs(as_of.year, games, "A")
            if (result.get("target") != len(games) or result.get("games") != len(games)
                    or result.get("failed")
                    or run_refresh_recent._detail_gaps(as_of.year, "A", games, SOURCE_BOX_TABLES)):
                raise ValueError("gamelog_refresh_incomplete")
    if as_of != datetime.now(TAIPEI).date():
        raise ValueError("refresh_crossed_taipei_midnight")


def _saved(path):
    if not os.path.lexists(path):
        return None
    sender._private(path)
    with path.open("rb") as stream:
        raw = stream.read(8193)
    if len(raw) > 8192:
        raise ValueError("local_state_too_large")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("invalid_local_state")
    return value


def _schedule_identity(manifest, bundle):
    if manifest is None:
        return None
    sender._private(manifest)
    sender._private(bundle, directory=True)
    fingerprints = []
    for path in (manifest, bundle / "index.json"):
        sender._private(path)
        with path.open("rb") as stream:
            raw = stream.read(sender.fetch.MAX_INDEX_BYTES + 1)
        if not 0 < len(raw) <= sender.fetch.MAX_INDEX_BYTES:
            raise ValueError("local_schedule_input_size")
        fingerprints.append({"path": str(path), "sha256": sender.fetch.digest(raw)})
    return fingerprints


def _save(out, filename, value):
    sender._state(out, filename, json.dumps(value, sort_keys=True, separators=(",", ":")))


def _read_result(handoff, directory, source_id, as_of, *, include_games=False):
    sender._private(directory.parent, directory=True)
    sender._private(directory, directory=True)
    for filename in ("response.json", "result.json.gz"):
        sender._private(directory / filename)
    receipt, _ = handoff.read_response(directory, source_id, as_of)
    if ("schedule_sha256" in receipt) != include_games:
        raise ValueError("schedule_mode_mismatch")
    if include_games:
        sender._private(directory / "schedule.json")
        handoff.read_schedule(directory, receipt, as_of)
    with (directory / "response.json").open("rb") as stream:
        raw = stream.read(handoff.MAX_MANIFEST + 1)
    if not 0 < len(raw) <= handoff.MAX_MANIFEST:
        raise ValueError("response_manifest_size")
    return receipt, sender.fetch.digest(raw)


def _run_native(command, cwd, env, deadline, payload=None):
    remaining = deadline - time.monotonic() - EXIT_RESERVE_SECONDS
    if remaining <= 0:
        raise ValueError("insufficient_native_exit_budget")
    child = subprocess.Popen(
        command, cwd=cwd, env=env, start_new_session=True,
        stdin=subprocess.PIPE if payload is not None else subprocess.DEVNULL,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    rc, timed_out = sender.fetch.wait_worker(child, remaining, payload)
    if type(rc) is not int:
        raise ValueError("native_exit_unknown")
    return {"native_rc": rc, "timed_out": timed_out, "native_wait": True}


def _stage(work, state, name, command, cwd, env, deadline, result, payload=None):
    """Persist the uncertain-start marker before crossing a process boundary."""
    state["phase"] = name + "_active"
    _save(work, "state.json", state)
    result["stage"] = name
    evidence = _run_native(command, cwd, env, deadline, payload)
    result[name] = evidence
    if name != "publish":
        state["phase"] = "local"
        _save(work, "state.json", state)
    if evidence["native_rc"] != 0 or evidence["timed_out"]:
        raise ValueError(name + "_native_failure")


def run(out, source_id, as_of, timeout, *, manifest=None, bundle=None, send=False,
        notify=False, source_once=False, include_games=False,
        identity_file=sender.IDENTITY_FILE, known_hosts=sender.KNOWN_HOSTS):
    """One daily Pi-owned feature run, with at most one local pre-publish reentry."""
    result = {"ok": False, "stage": "precheck"}
    try:
        from cpbl.features import handoff

        if (as_of != datetime.now(TAIPEI).date() or not math.isfinite(timeout)
                or timeout <= EXIT_RESERVE_SECONDS or (manifest is None) != (bundle is None)
                or (notify and not send) or (include_games and send and not notify)):
            raise ValueError("invalid_daily_feature_scope")
        deadline = time.monotonic() + timeout
        name = handoff.run_id(source_id, as_of)
        result["run_id"] = name
        out = out.absolute()
        if out.resolve(strict=True) != out:
            raise ValueError("canonical_private_root_required")
        sender._private(out, directory=True)
        if manifest is not None:
            manifest, bundle = manifest.absolute(), bundle.absolute()
        with sender._request_lock(out) as locked:
            if not locked:
                result["stage"] = "busy"
                return result
            work = out / name
            work.mkdir(mode=0o700, exist_ok=True)
            sender._private(work, directory=True)
            state = _saved(work / "state.json")
            if state is None:
                state = {"attempts": 0, "phase": "local"}
            if (not isinstance(state, dict) or type(state.get("attempts")) is not int
                    or not 0 <= state["attempts"] <= 2 or state.get("phase") not in (
                        "local", "refresh_active", "compute_active", "publish_active", "published",
                    )):
                raise ValueError("invalid_local_run_state")
            phase = state.get("phase")
            result["stage"] = phase
            directory = work / "result" / name
            if phase == "published":
                receipt, response_sha = _read_result(handoff, directory, source_id, as_of, include_games=include_games)
                if (receipt["result_sha256"], response_sha) != (
                        state.get("result_sha256"), state.get("response_sha256")):
                    raise ValueError("published_result_changed")
                if notify and state.get("notified") is not True:
                    raise ValueError("notification_not_proved")
                result.update(ok=True, stage="already_published", result_sha256=receipt["result_sha256"],
                              response_sha256=response_sha, notified=state.get("notified") is True)
                return result
            if phase != "local" or state["attempts"] >= 2:
                raise ValueError("unsafe_or_exhausted_reentry")

            raw_identity = _schedule_identity(manifest, bundle)
            if state["attempts"] and (state.get("raw_inputs") != raw_identity
                                      or state.get("source_once", False) != source_once
                                      or state.get("include_games", False) != include_games
                                      or (source_once and state.get("source_failed") is True)):
                raise ValueError("refresh_inputs_changed")
            freshness = work / "freshness.json"
            schedule = work / "schedule.json"
            result_root = work / "result"
            needs_refresh = _saved(freshness) is None
            needs_compute = not os.path.lexists(directory)
            env = _private_environment() if needs_refresh or needs_compute else None
            state.update(attempts=state["attempts"] + 1, raw_inputs=raw_identity, source_once=source_once,
                         include_games=include_games)
            _save(work, "state.json", state)
            if needs_refresh:
                command = [sys.executable, "-I", "-B", str(Path(__file__).resolve()),
                           "_refresh", as_of.isoformat()]
                if manifest is not None:
                    command.extend(["--manifest", str(manifest), "--bundle", str(bundle)])
                if include_games:
                    command.extend(["--schedule-output", str(schedule)])
                if source_once:
                    command.append("--source-once")
                try:
                    _stage(work, state, "refresh", command, work, env, deadline, result)
                except Exception:
                    if source_once:
                        state["source_failed"] = True
                        _save(work, "state.json", state)
                    raise
                if _schedule_identity(manifest, bundle) != raw_identity:
                    raise ValueError("refresh_inputs_changed")
                finished = datetime.now(UTC)
                if finished.astimezone(TAIPEI).date() != as_of:
                    raise ValueError("refresh_crossed_taipei_midnight")
                _save(work, freshness.name, {
                    "source_id": source_id, "as_of": as_of.isoformat(),
                    "finished_at": finished.isoformat(), "ok": True,
                })
            if needs_compute:
                command = [sys.executable, "-I", "-B", "-m", "cpbl.features.handoff", "compute",
                           str(freshness), str(result_root)]
                if include_games:
                    sender._private(schedule)
                    command.extend(["--schedule", str(schedule)])
                _stage(work, state, "compute", command, work, env, deadline, result)
            receipt, response_sha = _read_result(handoff, directory, source_id, as_of, include_games=include_games)
            if receipt["refresh_finished_at"] != _saved(freshness)["finished_at"]:
                raise ValueError("response_refresh_receipt_mismatch")
            sha = receipt["result_sha256"]
            if (state.get("result_sha256", sha), state.get("response_sha256", response_sha)) != (sha, response_sha):
                raise ValueError("local_result_changed")
            state.update(result_sha256=sha, response_sha256=response_sha)
            _save(work, "state.json", state)
            result.update(stage="local_ready", result_sha256=sha, response_sha256=response_sha,
                          input_sha256=receipt["input_sha256"],
                          row_count=receipt["row_count"])
            if send:
                result["stage"] = "authenticate"
                sender_auth = sender._authentication(identity_file, known_hosts)
                command = sender._sftp_command(*sender_auth, sender.USER)
                if notify:
                    _save(directory, "notification.json",
                          {"version": 1, "run_id": name, "response_sha256": response_sha})
                _stage(work, state, "publish", command, directory, {"LANG": "C", "LC_ALL": "C"},
                       deadline, result, _publication_batch(name, notify=notify, include_games=include_games))
                state.update(phase="published", notified=notify)
                _save(work, "state.json", state)
                result.update(stage="published", notified=notify)
            result["ok"] = True
    except Exception as exc:
        result["error_class"] = type(exc).__name__
    return result


def _raw_arguments(parser):
    parser.add_argument("--manifest", type=Path, help="Original local WWW schedule request")
    parser.add_argument("--bundle", type=Path, help="Its complete authentic same-day local bundle")
    parser.add_argument("--source-once", action="store_true",
                        help="No browser recovery or local source reentry after a source-stage failure")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(dest="command", required=True)
    daily = modes.add_parser("run")
    daily.add_argument("--out", type=Path, required=True)
    daily.add_argument("--source-id", required=True)
    daily.add_argument("--as-of", type=date.fromisoformat, required=True)
    daily.add_argument("--timeout", type=float, required=True, help="Total seconds including native exit")
    daily.add_argument("--send", action="store_true", help="Explicitly publish to the pinned private inbox")
    daily.add_argument("--notify", action="store_true", help="Commit the bound flat notification after both files")
    daily.add_argument("--include-games", action="store_true")
    _raw_arguments(daily)
    refresh = modes.add_parser("_refresh")
    refresh.add_argument("as_of", type=date.fromisoformat)
    refresh.add_argument("--schedule-output", type=Path)
    _raw_arguments(refresh)
    with redirect_stderr(io.StringIO()):
        try:
            args = parser.parse_args(argv)
        except SystemExit as exc:
            return int(exc.code or 0)
    if (args.manifest is None) != (args.bundle is None):
        return 78
    os.umask(0o077)
    if args.command == "_refresh":
        try:
            _local_refresh(args.as_of, args.manifest, args.bundle, source_once=args.source_once,
                           schedule_output=args.schedule_output)
            return 0
        except (Exception, _SourceStopped) as exc:
            print(json.dumps({"ok": False, "error_class": type(exc).__name__}))
            return 78
    result = run(args.out, args.source_id, args.as_of, args.timeout, manifest=args.manifest,
                 bundle=args.bundle, send=args.send, notify=args.notify, source_once=args.source_once,
                 include_games=args.include_games)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["ok"] else 78


if __name__ == "__main__":
    raise SystemExit(main())
