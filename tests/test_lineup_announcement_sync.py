"""LINEUP_ONLY純mock受保護入口；假ssh/backup/DB，絕不連真production。"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
COLUMNS = "year, kind_code, game_sno, source_type, source_url, fetched_at, content_hash, raw_status, raw_payload, last_seen_at"
DUMP = (
    f"-- fixture-only\nCOPY cpbl.game_lineup_announcement_revisions ({COLUMNS}) FROM stdin;\n\\.\n"
)


def harness(tmp_path, dump=DUMP):
    scripts = tmp_path / "repo/scripts"
    scripts.mkdir(parents=True)
    script = scripts / "refresh-cpbl-prod.sh"
    shutil.copy(ROOT / "scripts/refresh-cpbl-prod.sh", script)
    backup = scripts / "backup-prod-db.sh"
    backup.write_text(
        '#!/bin/sh\n[ "${A8_BACKUP_FAIL:-}" != "1" ] || exit 9\necho /fixture-backup.sql.gz\n'
    )
    backup.chmod(0o755)
    bins = tmp_path / "bin"
    bins.mkdir()
    calls = tmp_path / "calls.jsonl"
    payloads = tmp_path / "payload.sql"
    fixture = tmp_path / "fixture.dump"
    fixture.write_text(dump)
    shim = r"""#!/usr/bin/env python3
import json,os,pathlib,sys
name=pathlib.Path(sys.argv[0]).name
with open(os.environ["A8_CALLS"],"a") as f:f.write(json.dumps([name,*sys.argv[1:]])+"\n")
if name=="docker":
    if "pg_dump" in sys.argv:print(pathlib.Path(os.environ["A8_DUMP"]).read_text(),end="")
    else:raise SystemExit(99)
elif name=="ssh":
    text=sys.stdin.read()
    if text:pathlib.Path(os.environ["A8_PAYLOAD"]).write_text(text)
else:raise SystemExit(99)
"""
    for name in ["docker", "ssh", "uv", "curl"]:
        path = bins / name
        path.write_text(shim)
        path.chmod(0o755)
    env = {
        **os.environ,
        "PATH": str(bins) + os.pathsep + os.environ["PATH"],
        "LOCAL_DB": "a8-fixture-db.invalid",
        "VPS": "a8-fixture.invalid",
        "DEPLOY_PATH": "/not-a-deploy-path",
        "API_INFO_URL": "https://a8-fixture.invalid/info",
        "LINEUP_ONLY": "1",
        "SKIP_SCRAPE": "1",
        "A8_CALLS": str(calls),
        "A8_DUMP": str(fixture),
        "A8_PAYLOAD": str(payloads),
    }
    return script, env, calls, payloads


def test_lineup_only_excludes_general_sync_features_training_and_freshness(tmp_path):
    script, env, calls, payload = harness(tmp_path)
    result = subprocess.run(
        ["bash", str(script)], env=env, capture_output=True, text=True, timeout=10
    )
    assert result.returncode == 0, result.stderr
    actions = [json.loads(l) for l in calls.read_text().splitlines()]
    assert {a[0] for a in actions} <= {"docker", "ssh"}
    assert all("game_features" not in str(a) and "cpbl-train" not in str(a) for a in actions)
    sql = payload.read_text()
    assert "_lineup_stg" in sql and "game_lineup_announcement_revisions" in sql
    assert "GREATEST" in sql and "RAISE EXCEPTION" in sql
    assert "fetched_at=EXCLUDED" not in sql and "DELETE FROM" not in sql
    assert "cpbl.games" not in sql and "freshness" not in result.stdout.lower()


@pytest.mark.parametrize(
    "bad_dump",
    [
        DUMP + "SELECT pg_catalog.setval('bad',99,true);\n",
        DUMP.replace("cpbl.game_lineup_announcement_revisions", "cpbl.games"),
    ],
)
def test_unsafe_dump_is_stopped_before_any_remote_write(tmp_path, bad_dump):
    script, env, calls, payload = harness(tmp_path, bad_dump)
    result = subprocess.run(
        ["bash", str(script)], env=env, capture_output=True, text=True, timeout=10
    )
    assert result.returncode == 67
    actions = [json.loads(l) for l in calls.read_text().splitlines()]
    assert all(a[0] != "ssh" for a in actions) and not payload.exists()


def test_backup_failure_stops_migration_and_sync(tmp_path):
    script, env, calls, payload = harness(tmp_path)
    env["A8_BACKUP_FAIL"] = "1"
    result = subprocess.run(
        ["bash", str(script)], env=env, capture_output=True, text=True, timeout=10
    )
    assert result.returncode != 0
    actions = [json.loads(l) for l in calls.read_text().splitlines()]
    assert all(a[0] != "ssh" for a in actions) and not payload.exists()
