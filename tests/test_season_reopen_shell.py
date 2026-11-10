"""#392 WP2：``refresh-cpbl-prod.sh`` 的 ``SEASON_REOPEN_ONLY`` 單表模式（副本＋假樁，⛔ 不連 VPS）。

形狀沿用 ``tests/test_lineup_announcement_sync.py``：腳本複製進 tmp 假 repo，``ssh``／``docker``／``uv``／``curl``
換成留痕假樁，備份腳本換成假備份；``VPS`` 指向 ``.invalid`` 保留網域、``HOME`` 指向 tmp（fail-safe）。
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

SHIM = r"""#!/usr/bin/env python3
import json, os, pathlib, sys
name = pathlib.Path(sys.argv[0]).name
with open(os.environ["SR_CALLS"], "a") as f:
    f.write(json.dumps([name, *sys.argv[1:]]) + "\n")
if name == "uv":
    raise SystemExit(int(os.environ.get("SR_UV_RC", "0")))
if name == "ssh":
    raise SystemExit(int(os.environ.get("SR_SSH_RC", "0")))
raise SystemExit(99)
"""

BACKUP = """#!/bin/sh
printf '%s\\n' "[\\"backup-prod-db.sh\\", \\"$BACKUP_DIR\\"]" >> "$SR_CALLS"
[ "${SR_BACKUP_FAIL:-}" != "1" ] || exit 9
echo "$BACKUP_DIR/fixture-backup.sql.gz"
"""


def harness(tmp_path: Path, **extra: str) -> tuple[Path, dict, Path]:
    scripts = tmp_path / "repo" / "scripts"
    scripts.mkdir(parents=True)
    script = scripts / "refresh-cpbl-prod.sh"
    shutil.copy(ROOT / "scripts" / "refresh-cpbl-prod.sh", script)
    backup = scripts / "backup-prod-db.sh"
    backup.write_text(BACKUP)
    backup.chmod(0o755)
    bins = tmp_path / "bin"
    bins.mkdir()
    for name in ("docker", "ssh", "uv", "curl", "psql", "pg_dump"):
        (bins / name).write_text(SHIM)
        (bins / name).chmod(0o755)
    calls = tmp_path / "calls.jsonl"
    calls.touch()
    home = tmp_path / "home"
    home.mkdir()
    env = {
        **{k: v for k, v in os.environ.items() if k not in (
            "WITH_DETAIL", "LINEUP_ONLY", "ROSTER_ONLY", "POSTSEASON_RESULTS_ONLY", "POSTSEASON_BOXPA_ONLY",
            "TEAM_COMPARISON_ONLY", "DAILY_DAY_TYPE", "CPBL_MAC_RESCUE")},
        "PATH": str(bins) + os.pathsep + "/usr/bin:/bin",
        "HOME": str(home),
        "LOCAL_DB": "sr-fixture-db.invalid",
        "VPS": "sr-fixture.invalid",
        "DEPLOY_PATH": "/not-a-deploy-path",
        "API_INFO_URL": "https://sr-fixture.invalid/api/info",
        "SR_CALLS": str(calls),
        "SEASON_REOPEN_ONLY": "1",
        "SKIP_SCRAPE": "1",
        "SEASON_REOPEN_ACTION": "apply",
        "SEASON_REOPEN_ROWS": "major:2026,farm:2026",
        "BACKUP_DIR": str(tmp_path / "sr-backups"),
        **extra,
    }
    return script, env, calls


def run(script: Path, env: dict) -> subprocess.CompletedProcess:
    return subprocess.run(["bash", str(script)], env=env, capture_output=True, text=True, timeout=20,
                          stdin=subprocess.DEVNULL, check=False)


def actions(calls: Path) -> list[list[str]]:
    return [json.loads(line) for line in calls.read_text().splitlines()]


@pytest.mark.parametrize("action", ["apply", "revoke"])
def test_mode_runs_backup_then_migrate_then_single_table_write(tmp_path, action):
    script, env, calls = harness(tmp_path, SEASON_REOPEN_ACTION=action)
    result = run(script, env)
    assert result.returncode == 0, result.stderr
    got = actions(calls)
    assert [a[0] for a in got] == ["backup-prod-db.sh", "ssh", "uv"], got
    assert got[0][1] == os.path.realpath(env["BACKUP_DIR"])
    assert "prod_cpbl_api" in " ".join(got[1]) and "db.migrate()" in " ".join(got[1])
    uv = got[2][1:]
    assert uv[:5] == ["run", "python", "-m", "cpbl.season_reopen", "remote"]
    assert uv[uv.index("--action") + 1] == action
    assert uv[uv.index("--rows") + 1] == "major:2026,farm:2026"
    target = uv[uv.index("--target-psql") + 1]
    assert target.startswith("ssh -o BatchMode=yes sr-fixture.invalid ") and "docker exec -i prod_pg psql" in target
    text = json.dumps(got)
    for banned in ("game_features", "cpbl-train", "pg_dump", "sync_table", "cpbl.games", "curl"):
        assert banned not in text
    assert "freshness" not in result.stdout.lower()


@pytest.mark.parametrize("override", [
    {"SKIP_SCRAPE": ""},
    {"SEASON_REOPEN_ONLY": "yes"},
    {"WITH_DETAIL": "1"},
    {"LINEUP_ONLY": "1"},
    {"ROSTER_ONLY": "1"},
    {"POSTSEASON_RESULTS_ONLY": "1"},
    {"TEAM_COMPARISON_ONLY": "1"},
    {"DAILY_DAY_TYPE": "full"},
    {"SEASON_REOPEN_ACTION": ""},
    {"SEASON_REOPEN_ACTION": "drop"},
    {"SEASON_REOPEN_ROWS": ""},
    {"SEASON_REOPEN_ROWS": "major:26"},
    {"SEASON_REOPEN_ROWS": "major:2026,"},
    {"SEASON_REOPEN_ROWS": "major:2026;rm -rf /"},
    {"SEASON_REOPEN_ROWS": "major:2026,major:2025"},
    {"SEASON_REOPEN_ROWS": "major:2026,farm:2026,farm:2025"},
    {"BACKUP_DIR": ""},
    {"BACKUP_DIR": "relative/dir"},
], ids=lambda d: ",".join(f"{k}={v}" for k, v in d.items()))
def test_guards_refuse_with_64_before_any_side_effect(tmp_path, override):
    script, env, calls = harness(tmp_path, **override)
    result = run(script, env)
    assert result.returncode == 64, (result.returncode, result.stderr)
    assert actions(calls) == [], "守衛失敗時不得備份、不得 ssh、不得寫入"


def test_backup_dir_equal_to_daily_rotation_dir_is_refused(tmp_path):
    script, env, calls = harness(tmp_path)
    daily = Path(env["HOME"]) / "Library" / "Application Support" / "cpbl-analytics" / "backups"
    daily.mkdir(parents=True)
    env["BACKUP_DIR"] = str(daily) + "/."
    result = run(script, env)
    assert result.returncode == 64 and actions(calls) == []


def test_boxpa_combination_is_refused(tmp_path):
    """BOXPA 的互斥檢查在最前面且不認得本模式；同時設定時由本模式的守衛拒絕（仍是 64、零副作用）。"""
    script, env, calls = harness(tmp_path, POSTSEASON_BOXPA_ONLY="1")
    result = run(script, env)
    assert result.returncode == 64 and actions(calls) == []


def test_backup_failure_stops_before_migrate_and_write(tmp_path):
    script, env, calls = harness(tmp_path, SR_BACKUP_FAIL="1")
    result = run(script, env)
    assert result.returncode != 0
    assert [a[0] for a in actions(calls)] == ["backup-prod-db.sh"]


def test_migrate_failure_stops_before_write(tmp_path):
    script, env, calls = harness(tmp_path, SR_SSH_RC="255")
    result = run(script, env)
    assert result.returncode == 255
    assert [a[0] for a in actions(calls)] == ["backup-prod-db.sh", "ssh"]


@pytest.mark.parametrize("rc", [69, 71, 72])
def test_remote_step_exit_code_is_the_script_exit_code(tmp_path, rc):
    script, env, calls = harness(tmp_path, SR_UV_RC=str(rc))
    result = run(script, env)
    assert result.returncode == rc
    assert "正式站完成" not in result.stdout


def test_help_documents_the_mode(tmp_path):
    script, env, calls = harness(tmp_path)
    result = subprocess.run(["bash", str(script), "--help"], env=env, capture_output=True, text=True, timeout=10,
                            check=False)
    assert result.returncode == 0 and actions(calls) == []
    assert "SEASON_REOPEN_ONLY" in result.stdout and "SEASON_REOPEN_ROWS" in result.stdout
