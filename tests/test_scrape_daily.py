import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).parents[1]
SYSTEM_PYTHON = "/usr/bin/python3" if Path("/usr/bin/python3").exists() else sys.executable


def _executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def _run_daily(
    tmp_path: Path,
    *,
    uv_exit: int = 0,
    sync_exit: int = 0,
    docker_running: bool = True,
    trigger: str = "manual",
    active_lock_pid: int | None = None,
) -> tuple[subprocess.CompletedProcess[str], dict[str, object]]:
    repo = tmp_path / "repo"
    scripts = repo / "scripts"
    fake_bin = tmp_path / "bin"
    scripts.mkdir(parents=True)
    fake_bin.mkdir()
    shutil.copy2(ROOT / "scripts" / "scrape-daily.sh", scripts / "scrape-daily.sh")
    status_helper = ROOT / "scripts" / "refresh_status.py"
    if status_helper.exists():
        shutil.copy2(status_helper, scripts / "refresh_status.py")

    docker_output = "cpbl-analytics-db-1\n" if docker_running else ""
    _executable(fake_bin / "docker", f"#!/bin/sh\nprintf '{docker_output}'\n")
    _executable(fake_bin / "uv", f"#!/bin/sh\nexit {uv_exit}\n")
    _executable(scripts / "refresh-cpbl-prod.sh", f"#!/bin/sh\nexit {sync_exit}\n")

    lock_dir = tmp_path / "refresh.lock"
    if active_lock_pid is not None:
        lock_dir.mkdir()
        (lock_dir / "pid").write_text(str(active_lock_pid), encoding="utf-8")

    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_bin}:/usr/bin:/bin",
            "REFRESH_TRIGGER": trigger,
            "REFRESH_LOCK_DIR": str(lock_dir),
            "SYNC_PROD": "1",
        }
    )
    result = subprocess.run(
        ["/bin/bash", str(scripts / "scrape-daily.sh")],
        cwd=repo,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    status_path = repo / "logs" / "last-status.json"
    status = json.loads(status_path.read_text(encoding="utf-8")) if status_path.exists() else {}
    return result, status


def test_sync_failure_is_reported_as_overall_failure(tmp_path: Path) -> None:
    result, status = _run_daily(tmp_path, sync_exit=17)

    assert result.returncode == 17
    assert status["ok"] is False
    assert status["state"] == "failed"
    assert status["failed_phase"] == "sync"
    assert status["scrape_ok"] is True
    assert status["sync_attempted"] is True
    assert status["sync_ok"] is False


def test_scrape_failure_skips_sync_and_preserves_exit_code(tmp_path: Path) -> None:
    result, status = _run_daily(tmp_path, uv_exit=9)

    assert result.returncode == 9
    assert status["failed_phase"] == "scrape"
    assert status["scrape_ok"] is False
    assert status["sync_attempted"] is False
    assert status["sync_ok"] is None


def test_success_records_launchd_trigger_and_both_phases(tmp_path: Path) -> None:
    result, status = _run_daily(tmp_path, trigger="launchd")

    assert result.returncode == 0
    assert status["ok"] is True
    assert status["state"] == "succeeded"
    assert status["trigger"] == "launchd"
    assert status["failed_phase"] is None
    assert status["scrape_ok"] is True
    assert status["sync_ok"] is True
    assert (tmp_path / "repo" / "logs" / "last-launchd-status.json").exists()


def test_missing_local_database_is_a_scrape_failure(tmp_path: Path) -> None:
    result, status = _run_daily(tmp_path, docker_running=False)

    assert result.returncode == 127
    assert status["failed_phase"] == "scrape"
    assert status["scrape_ok"] is False
    assert status["sync_attempted"] is False


def test_checker_distinguishes_missing_schedule_from_latest_manual_success(tmp_path: Path) -> None:
    result, _ = _run_daily(tmp_path, trigger="manual")
    helper = tmp_path / "repo" / "scripts" / "refresh_status.py"

    check = subprocess.run(
        ["python3", str(helper), "check", "--scheduled"],
        cwd=tmp_path / "repo",
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert check.returncode == 2
    assert check.stdout.startswith("NOT_TRIGGERED")


def test_checker_returns_distinct_exit_code_for_sync_failure(tmp_path: Path) -> None:
    result, _ = _run_daily(tmp_path, sync_exit=17)
    helper = tmp_path / "repo" / "scripts" / "refresh_status.py"

    check = subprocess.run(
        ["python3", str(helper), "check"],
        cwd=tmp_path / "repo",
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 17
    assert check.returncode == 4
    assert check.stdout.startswith("SYNC_FAILED")


def _check_scheduled(
    repo: Path,
    *,
    now: datetime,
    deadline: str = "11:00",
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            SYSTEM_PYTHON,
            str(repo / "scripts" / "refresh_status.py"),
            "check",
            "--scheduled",
            "--now",
            now.isoformat(),
            "--deadline",
            deadline,
        ],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )


def _status_started_at(status: dict[str, object]) -> datetime:
    value = str(status["started_at"])
    if len(value) >= 5 and value[-5] in "+-" and value[-3] != ":":
        value = f"{value[:-2]}:{value[-2:]}"
    return datetime.fromisoformat(value)


def test_scheduled_checker_accepts_success_written_by_launchd_flow(tmp_path: Path) -> None:
    _, status = _run_daily(tmp_path, trigger="launchd")
    started_at = _status_started_at(status)

    check = _check_scheduled(
        tmp_path / "repo",
        now=started_at.replace(hour=12, minute=0, second=0),
    )

    assert check.returncode == 0, check.stderr or check.stdout
    assert check.stdout.startswith("OK")


def test_scheduled_checker_reports_running_state(tmp_path: Path) -> None:
    _, status = _run_daily(tmp_path, trigger="launchd")
    repo = tmp_path / "repo"
    scheduled_path = repo / "logs" / "last-launchd-status.json"
    status.update({"state": "running", "ok": None, "finished_at": None})
    scheduled_path.write_text(json.dumps(status), encoding="utf-8")
    started_at = _status_started_at(status)

    check = _check_scheduled(repo, now=started_at.replace(hour=12, minute=0, second=0))

    assert check.returncode == 6
    assert check.stdout.startswith("RUNNING")


def test_scheduled_checker_reports_stale_running_after_timeout(tmp_path: Path) -> None:
    _, status = _run_daily(tmp_path, trigger="launchd")
    repo = tmp_path / "repo"
    scheduled_path = repo / "logs" / "last-launchd-status.json"
    status.update({"state": "running", "ok": None, "finished_at": None})
    scheduled_path.write_text(json.dumps(status), encoding="utf-8")
    started_at = _status_started_at(status)

    check = _check_scheduled(repo, now=started_at + timedelta(hours=13))

    assert check.returncode == 7
    assert check.stdout.startswith("STALE_RUNNING")


def test_scheduled_checker_reports_scrape_failure(tmp_path: Path) -> None:
    _, status = _run_daily(tmp_path, trigger="launchd", uv_exit=9)
    started_at = _status_started_at(status)

    check = _check_scheduled(
        tmp_path / "repo",
        now=started_at.replace(hour=12, minute=0, second=0),
    )

    assert check.returncode == 3
    assert check.stdout.startswith("SCRAPE_FAILED")


def test_scheduled_checker_reports_sync_failure(tmp_path: Path) -> None:
    _, status = _run_daily(tmp_path, trigger="launchd", sync_exit=17)
    started_at = _status_started_at(status)

    check = _check_scheduled(
        tmp_path / "repo",
        now=started_at.replace(hour=12, minute=0, second=0),
    )

    assert check.returncode == 4
    assert check.stdout.startswith("SYNC_FAILED")


def test_scheduled_checker_detects_expired_run_after_deadline(tmp_path: Path) -> None:
    _, status = _run_daily(tmp_path, trigger="launchd")
    started_at = _status_started_at(status)

    check = _check_scheduled(
        tmp_path / "repo",
        now=started_at + timedelta(days=1, hours=12 - started_at.hour),
    )

    assert check.returncode == 2
    assert check.stdout.startswith("NOT_TRIGGERED")


def test_scheduled_checker_honors_custom_deadline(tmp_path: Path) -> None:
    _, status = _run_daily(tmp_path, trigger="launchd")
    started_at = _status_started_at(status)

    check = _check_scheduled(
        tmp_path / "repo",
        now=started_at.replace(hour=12, minute=0, second=0),
        deadline="13:00",
    )

    assert check.returncode == 0


def test_active_refresh_lock_blocks_second_crawler_without_overwriting_status(tmp_path: Path) -> None:
    result, status = _run_daily(tmp_path, active_lock_pid=os.getpid())

    assert result.returncode == 75
    assert status == {}
    assert "already running" in result.stderr


def test_lock_without_pid_is_not_reclaimed_during_owner_startup(tmp_path: Path) -> None:
    lock_dir = tmp_path / "refresh.lock"
    lock_dir.mkdir()

    result, status = _run_daily(tmp_path)

    assert result.returncode == 75
    assert status == {}
    assert "lock unavailable" in result.stderr


def test_stale_refresh_lock_is_reclaimed(tmp_path: Path) -> None:
    result, status = _run_daily(tmp_path, active_lock_pid=999_999)

    assert result.returncode == 0
    assert status["state"] == "succeeded"


def test_sync_sql_error_propagates_to_daily_failed_phase(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    scripts = repo / "scripts"
    fake_bin = tmp_path / "bin"
    scripts.mkdir(parents=True)
    fake_bin.mkdir()
    for script_name in (
        "scrape-daily.sh",
        "refresh_status.py",
        "refresh-cpbl-prod.sh",
        "backup-cpbl-prod.sh",
        "verify_refresh_info.py",
    ):
        shutil.copy2(ROOT / "scripts" / script_name, scripts / script_name)

    _executable(
        fake_bin / "docker",
        """#!/bin/bash
if [ "$1" = "ps" ]; then
  echo cpbl-analytics-db-1
elif [[ "$*" == *" psql "* ]]; then
  echo '2026-07-16|3'
elif [[ "$*" == *" pg_dump "* ]]; then
  printf '%s\n' 'COPY cpbl.games (id) FROM stdin;' '1' '\\.'
fi
""",
    )
    _executable(fake_bin / "uv", "#!/bin/sh\nexit 0\n")
    _executable(
        fake_bin / "ssh",
        """#!/bin/bash
if [[ "$*" == *"pg_dump"* ]]; then
  echo 'CREATE SCHEMA cpbl;'
  exit 0
fi
if [[ "$*" == *"--single-transaction"* ]]; then
  cat >/dev/null
  echo 'ERROR: injected sync SQL failure' >&2
  if [[ "$*" == *"ON_ERROR_STOP"* ]]; then
    exit 42
  fi
fi
exit 0
""",
    )
    now = datetime.now().astimezone().isoformat()
    _executable(
        fake_bin / "curl",
        "#!/bin/sh\n"
        f"echo '{json.dumps({'status': 'running', 'metrics': {'last_refresh': now, 'last_game_date': '2026-07-16', 'season_games_completed': 3}})}'\n",
    )

    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_bin}:/usr/bin:/bin",
            "REFRESH_LOCK_DIR": str(tmp_path / "refresh.lock"),
            "REFRESH_TRIGGER": "manual",
            "BACKUP_DIR": str(tmp_path / "backups"),
            "SYNC_PROD": "1",
        }
    )
    result = subprocess.run(
        ["/bin/bash", str(scripts / "scrape-daily.sh")],
        cwd=repo,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    status = json.loads((repo / "logs" / "last-status.json").read_text(encoding="utf-8"))

    assert result.returncode == 42
    assert status["state"] == "failed"
    assert status["failed_phase"] == "sync"
    assert status["sync_exit_code"] == 42
