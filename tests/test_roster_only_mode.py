"""#284 E19：refresh-cpbl-prod.sh ROSTER_ONLY=1 的 mock harness；假 ssh／docker／uv／backup，絕不連真生產。

ROSTER_SCRIPT 指向要驗的 refresh-cpbl-prod.sh（預設 repo 內那支）。
"""
from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
SCRIPT = Path(os.environ.get("ROSTER_SCRIPT", ROOT / "scripts/refresh-cpbl-prod.sh"))

SHIM = r"""#!/usr/bin/env python3
import json,os,pathlib,sys
name=pathlib.Path(sys.argv[0]).name
with open(os.environ["R_CALLS"],"a") as f:f.write(json.dumps([name,*sys.argv[1:]])+"\n")
mode=os.environ.get("R_MODE","insert")
if name=="uv" and sys.argv[1:4]==["run","python","-m"] and sys.argv[4]=="cpbl.rosters.sync":
    action=sys.argv[5]
    if action=="plan":
        if mode=="reject": print("✗ 內容不同",file=sys.stderr); raise SystemExit(70)
        if mode=="notable": raise SystemExit(69)
        print("ROSTER_SYNC_PLAN="+("no-change" if mode=="nochange" else "insert-pending"))
    elif action=="apply":
        print("ROSTER_SYNC_PLAN=insert-pending"); print("ROSTER_SYNC_RECONCILE=ok")
    else: raise SystemExit(99)
else: raise SystemExit(99)
"""


def harness(tmp_path, mode="insert", **extra):
    scripts = tmp_path / "repo/scripts"
    scripts.mkdir(parents=True)
    script = scripts / "refresh-cpbl-prod.sh"
    shutil.copy(SCRIPT, script)
    calls = tmp_path / "calls.jsonl"
    backup = scripts / "backup-prod-db.sh"
    backup.write_text('#!/bin/sh\necho "[\\"backup\\",\\"$BACKUP_DIR\\",\\"$BACKUP_KEEP\\"]" >> "$R_CALLS"\n'
                      '[ "${R_BACKUP_FAIL:-}" != 1 ] || exit 9\necho /fixture-backup.sql.gz\n')
    backup.chmod(0o755)
    bins = tmp_path / "bin"
    bins.mkdir()
    for name in ["docker", "ssh", "uv", "curl"]:
        (bins / name).write_text(SHIM)
        (bins / name).chmod(0o755)
    env = {**os.environ, "PATH": f"{bins}{os.pathsep}{os.environ['PATH']}",
           "LOCAL_DB": "r-fixture-db.invalid", "VPS": "r-fixture.invalid",
           "DEPLOY_PATH": "/not-a-deploy-path", "API_INFO_URL": "https://r-fixture.invalid/info",
           "ROSTER_ONLY": "1", "SKIP_SCRAPE": "1", "BACKUP_DIR": str(tmp_path / "roster-backups"),
           "R_CALLS": str(calls), "R_MODE": mode, **extra}
    r = subprocess.run(["bash", str(script)], env=env, capture_output=True, text=True, timeout=20)
    actions = [json.loads(ln) for ln in calls.read_text().splitlines()] if calls.exists() else []
    return r, actions


def _sync_calls(actions):
    return [a for a in actions if a[0] == "uv"]


def test_insert_pending_backs_up_then_applies_only_roster_sync(tmp_path):
    r, actions = harness(tmp_path)
    assert r.returncode == 0, r.stderr
    assert [a[0] for a in actions] == ["uv", "backup", "uv"]
    assert [a[5] for a in _sync_calls(actions)] == ["plan", "apply"]
    assert actions[1][1].endswith("roster-backups") and actions[1][2] == "3"
    flat = json.dumps(actions, ensure_ascii=False)
    for banned in ("cpbl-scrape", "cpbl-build-features", "cpbl-train", "migrate", "sync_table",
                   "pg_dump", "refresh-marker", "game_features"):
        assert banned not in flat
    plan = _sync_calls(actions)[0]
    local = plan[plan.index("--local-psql") + 1]
    target = plan[plan.index("--target-psql") + 1]
    assert local == "docker exec -i r-fixture-db.invalid psql -U cpbl -d cpbl"
    argv = shlex.split(target)
    assert argv[:4] == ["ssh", "-o", "BatchMode=yes", "r-fixture.invalid"]
    assert argv[4] == ('cd /not-a-deploy-path && set -a && . ./.env && docker exec -i prod_pg '
                       'psql -U "$DB_USER" -d "$DB_NAME"')


def test_no_change_skips_backup_and_write(tmp_path):
    r, actions = harness(tmp_path, mode="nochange")
    assert r.returncode == 0 and "無變更" in r.stdout
    assert [a[0] for a in actions] == ["uv"] and actions[0][5] == "plan"


@pytest.mark.parametrize(("mode", "code"), [("reject", 70), ("notable", 69)])
def test_reject_or_missing_table_stops_before_backup(tmp_path, mode, code):
    r, actions = harness(tmp_path, mode=mode)
    assert r.returncode == code
    assert [a[0] for a in actions] == ["uv"]


def test_backup_failure_stops_before_write(tmp_path):
    r, actions = harness(tmp_path, R_BACKUP_FAIL="1")
    assert r.returncode != 0
    assert [a[0] for a in actions] == ["uv", "backup"]


@pytest.mark.parametrize("extra", [
    {"SKIP_SCRAPE": ""}, {"ROSTER_ONLY": "yes"}, {"WITH_DETAIL": "1"}, {"LINEUP_ONLY": "1"},
    {"POSTSEASON_RESULTS_ONLY": "1"}, {"BACKUP_DIR": ""},
])
def test_guards_exit_64_without_side_effects(tmp_path, extra):
    r, actions = harness(tmp_path, **extra)
    assert r.returncode == 64, (extra, r.stdout, r.stderr)
    assert actions == []


def test_default_backup_dir_rejected(tmp_path):
    r, actions = harness(tmp_path, BACKUP_DIR=f"{os.environ['HOME']}/Library/Application Support/cpbl-analytics/backups")
    assert r.returncode == 64 and actions == []
