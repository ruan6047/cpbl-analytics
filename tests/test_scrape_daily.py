import json
import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).parents[1]


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

    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_bin}:/usr/bin:/bin",
            "REFRESH_TRIGGER": trigger,
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
