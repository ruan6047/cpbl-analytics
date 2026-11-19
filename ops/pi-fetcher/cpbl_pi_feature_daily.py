"""Own one private PostgreSQL lifetime for the daily feature-only service."""

from __future__ import annotations

import importlib.util
import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "cpbl_pi_feature_command", Path(__file__).with_name("cpbl_pi_feature.py")
)
feature = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(feature)


def _owned_settings():
    from psycopg.conninfo import conninfo_to_dict

    data = Path(os.environ["CPBL_FEATURE_PI_PGDATA"])
    for folder in (data, data.parent):
        feature.sender._private(folder, directory=True)
        if folder.resolve(strict=True) != folder:
            raise ValueError("private_pgdata_required")
    seed_path = data.parent / "seed.json"
    feature.sender._private(seed_path)
    seed = json.loads(seed_path.read_text())
    if seed.get("scope") != "seed_smoke_only" or data.name != "pgdata":
        raise ValueError("unrecognized_seed_cluster")
    socket = data.parent / "socket"
    feature.sender._private(socket, directory=True)
    dsn = conninfo_to_dict(os.environ["CPBL_FEATURE_PI_DATABASE_URL"])
    if (dsn.get("host") != str(socket) or dsn.get("port", "5432") != "5432"
            or dsn.get("dbname") != "cpbl393_feature_bench"
            or set(dsn) - {"host", "port", "dbname", "user", "password", "connect_timeout"}):
        raise ValueError("private_pi_socket_dsn_required")
    if os.path.lexists(data / "postmaster.pid") or os.path.lexists(socket / ".s.PGSQL.5432"):
        raise ValueError("private_postgres_already_present")
    return data, socket


def _stop(process):
    if process.poll() is None:
        process.send_signal(signal.SIGINT)
    try:
        return process.wait(timeout=17)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=5)
        return 78


def _interrupted(_signum, _frame):
    raise InterruptedError("feature_service_stopped")


def main():
    os.umask(0o077)
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, _interrupted)
    pg = None
    status = 78
    try:
        data, socket = _owned_settings()
        binaries = Path(os.environ["CPBL_FEATURE_PI_PG_BIN"])
        if not binaries.is_absolute():
            raise ValueError("absolute_pg_bin_required")
        # Keep the known one-run server settings and the private socket.
        argv = [binaries / "postgres", "-D", data, "-c", "listen_addresses=",
                "-c", f"unix_socket_directories={socket}", "-c", "unix_socket_permissions=0700",
                "-c", "shared_buffers=32MB", "-c", "work_mem=4MB", "-c", "maintenance_work_mem=32MB",
                "-c", "max_connections=8", "-c", "max_parallel_workers_per_gather=0"]
        pg = subprocess.Popen(argv, stdin=subprocess.DEVNULL, start_new_session=True)
        until = time.monotonic() + 40
        while pg.poll() is None and time.monotonic() < until:
            check = subprocess.run([binaries / "pg_isready", "-q", "-h", socket, "-p", "5432"],
                                   env={}, timeout=4, check=False)
            if check.returncode == 0:
                break
            time.sleep(1)
        else:
            raise ValueError("private_pg_not_ready")
        day = datetime.now(feature.TAIPEI).date().isoformat()
        command = [sys.executable, "-I", "-B", str(Path(feature.__file__)), "run",
                   "--out", os.environ["CPBL_FEATURE_PI_OUT"], "--source-id", "pi",
                   "--as-of", day, "--timeout", "650", "--source-once", "--send", "--notify"]
        status = subprocess.run(command, stdin=subprocess.DEVNULL, timeout=675, check=False).returncode
    except Exception as exc:
        print(json.dumps({"stage": "feature_only_service", "error_class": type(exc).__name__}), flush=True)
    finally:
        if pg is not None:
            for sig in (signal.SIGTERM, signal.SIGINT):
                signal.signal(sig, signal.SIG_IGN)
            rc = _stop(pg)
            clean = not (data / "postmaster.pid").exists() and not (socket / ".s.PGSQL.5432").exists()
            print(json.dumps({"stage": "owned_pg_exit", "native_rc": rc, "pidfile_socket_absent": clean}),
                  flush=True)
            if rc != 0 or not clean:
                status = 78
    return status


if __name__ == "__main__":
    raise SystemExit(main())
