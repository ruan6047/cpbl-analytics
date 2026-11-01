"""每日 jobs 特徵邊界；替身不代表真 PG 或 VPS 已執行。"""

import json
import os
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from cpbl import db
from cpbl.config import settings
from cpbl.features import outcome, run_build_features
from cpbl.ingest import _browser
from cpbl.models import outcome_simple

ROOT = Path(__file__).parents[1]
UNREACHABLE = "postgresql://x:x@127.0.0.1:1/x"


@pytest.fixture
def compute(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATABASE_URL", UNREACHABLE)
    monkeypatch.setattr(settings, "database_url", UNREACHABLE)
    calls, forbidden_calls = [], []

    def forbidden(*args, **kwargs):
        forbidden_calls.append(True)
        raise AssertionError("不得連真 DB、啟動瀏覽器或子程序")

    def materialize():
        calls.append("features")
        return 7

    monkeypatch.setattr(db, "migrate", lambda: calls.append("migrate"))
    monkeypatch.setattr(outcome, "materialize", materialize)
    # base CLI 的 eager aliases 同樣隔離，讓 Red 只來自未提供 jobs 行為。
    for name, value in (("migrate", db.migrate), ("materialize", materialize)):
        if hasattr(run_build_features, name):
            monkeypatch.setattr(run_build_features, name, value)
    monkeypatch.setattr(db, "conn", forbidden)
    monkeypatch.setattr(db, "pool", forbidden)
    monkeypatch.setattr(outcome, "conn", forbidden)
    monkeypatch.setattr(_browser, "_Session", forbidden)
    monkeypatch.setattr(outcome_simple, "train_final_model", forbidden)
    monkeypatch.setattr(outcome_simple, "walk_forward_backtest", forbidden)
    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(db, "_pool", SimpleNamespace(close=lambda: calls.append("close")))
    yield calls
    assert not forbidden_calls


def invoke(monkeypatch, args):
    monkeypatch.setattr("sys.argv", ["cpbl-build-features", *args])
    return run_build_features.main()


def test_jobs_builds_features_without_migration_or_training(compute, monkeypatch, capsys):
    assert invoke(monkeypatch, ["--jobs"]) == 0
    assert compute == ["features", "close"]
    assert json.loads(capsys.readouterr().out) == {
        "scope": "game_features", "ok": True, "stage": "complete", "row_count": 7,
        "errors": [],
    }


@pytest.mark.parametrize("invalid", ["exception", "errors"])
def test_jobs_failure_is_nonzero_and_does_not_disclose_payload(
    compute, monkeypatch, capsys, invalid,
):
    def fail():
        compute.append("features")
        if invalid == "exception":
            raise RuntimeError("secret-dsn-and-row")
        return {"row_count": 7, "errors": ["secret-dsn-and-row"]}

    monkeypatch.setattr(outcome, "materialize", fail)
    assert invoke(monkeypatch, ["--jobs"]) == 1
    assert compute == ["features", "close"]
    captured = capsys.readouterr()
    result = json.loads(captured.out)
    assert not result["ok"] and result["errors"] and result["row_count"] is None
    assert "secret-dsn-and-row" not in captured.out + captured.err


@pytest.mark.parametrize("missing", ["env", "dotenv"])
def test_jobs_rejects_implicit_environment_before_build(compute, monkeypatch, capsys, missing):
    if missing == "env":
        monkeypatch.delenv("DATABASE_URL")
    else:
        Path(".env").write_text("DATABASE_URL=must-not-use\n")
    assert invoke(monkeypatch, ["--jobs"]) == 1
    assert not compute
    assert json.loads(capsys.readouterr().out)["stage"] == "environment"


def test_default_cli_retains_manual_migration_then_feature_build(compute, monkeypatch, capsys):
    invoke(monkeypatch, [])
    assert compute == ["migrate", "features"]
    assert not capsys.readouterr().out


@pytest.mark.parametrize("exit_code", [0, 69])
def test_daily_jobs_routes_before_mac_controls_and_preserves_exit(tmp_path, exit_code):
    repo, bin_dir = tmp_path / "repo", tmp_path / "bin"
    (repo / "scripts").mkdir(parents=True)
    bin_dir.mkdir()
    shutil.copy2(ROOT / "scripts/scrape-daily.sh", repo / "scripts/scrape-daily.sh")
    calls, forbidden = tmp_path / "calls", tmp_path / "forbidden"
    python = bin_dir / "python"
    python.write_text(
        '#!/bin/sh\nprintf "%s\\n" "$*" >> "$CALLS"\n'
        f"exit {exit_code}\n"
    )
    python.chmod(0o755)
    for name in ("uv", "docker", "launchctl", "pmset", "ssh", "curl", "python3", "date"):
        command = bin_dir / name
        command.write_text('#!/bin/sh\nprintf forbidden >> "$FORBIDDEN"\nexit 97\n')
        command.chmod(0o755)
    lock = tmp_path / "refresh.lock"
    result = subprocess.run(
        ["/bin/bash", str(repo / "scripts/scrape-daily.sh"), "--jobs-features"],
        cwd=tmp_path, env={**os.environ, "PATH": f"{bin_dir}:/usr/bin:/bin",
                           "DATABASE_URL": UNREACHABLE, "CALLS": str(calls),
                           "FORBIDDEN": str(forbidden), "REFRESH_LOCK_DIR": str(lock),
                           "REFRESH_TRIGGER": "not-a-mac-trigger"},
        text=True, capture_output=True, timeout=5,
    )
    assert result.returncode == exit_code
    assert calls.read_text().splitlines() == ["-m cpbl.features.run_build_features --jobs"]
    assert not forbidden.exists() and not lock.exists() and not (repo / "logs").exists()
