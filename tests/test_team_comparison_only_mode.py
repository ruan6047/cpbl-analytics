"""#287 E13：refresh-cpbl-prod.sh TEAM_COMPARISON_ONLY=1 與完整鏈接線、scrape-daily.sh builder 步驟的 mock harness。

假 ssh／docker／uv／backup，絕不連真生產。TC_SCRIPT 可指向要驗的 refresh-cpbl-prod.sh（預設 repo 內那支）。
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
SCRIPT = Path(os.environ.get("TC_SCRIPT", ROOT / "scripts/refresh-cpbl-prod.sh"))
MODULE = "cpbl.playoffs.team_comparison.sync"

SHIM = r"""#!/usr/bin/env python3
import json,os,pathlib,sys
name=pathlib.Path(sys.argv[0]).name
with open(os.environ["R_CALLS"],"a") as f:f.write(json.dumps([name,*sys.argv[1:]])+"\n")
mode=os.environ.get("R_MODE","insert")
if name=="uv" and sys.argv[1:4]==["run","python","-m"] and sys.argv[4]=="cpbl.playoffs.team_comparison.sync":
    action=sys.argv[5]
    if action=="plan":
        if mode=="reject": print("✗ 內容衝突",file=sys.stderr); raise SystemExit(70)
        if mode=="notable": raise SystemExit(69)
        if mode=="drift": raise SystemExit(67)
        print("TEAM_COMPARISON_SYNC_PLAN="+("no-change" if mode=="nochange" else "insert-pending"))
    elif action=="apply":
        if mode=="applyfail": raise SystemExit(69)
        print("TEAM_COMPARISON_SYNC_PLAN=insert-pending"); print("TEAM_COMPARISON_SYNC_RECONCILE=ok")
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
           "LOCAL_DB": "tc-fixture-db.invalid", "VPS": "tc-fixture.invalid",
           "DEPLOY_PATH": "/not-a-deploy-path", "API_INFO_URL": "https://tc-fixture.invalid/info",
           "TEAM_COMPARISON_ONLY": "1", "SKIP_SCRAPE": "1", "BACKUP_DIR": str(tmp_path / "tc-backups"),
           "R_CALLS": str(calls), "R_MODE": mode, **extra}
    for k in ("ROSTER_ONLY", "LINEUP_ONLY", "POSTSEASON_RESULTS_ONLY", "WITH_DETAIL"):
        if k not in extra:
            env.pop(k, None)
    r = subprocess.run(["bash", str(script)], env=env, capture_output=True, text=True, timeout=20)
    actions = [json.loads(ln) for ln in calls.read_text().splitlines()] if calls.exists() else []
    return r, actions


def _sync_calls(actions):
    return [a for a in actions if a[0] == "uv"]


def test_insert_pending_backs_up_then_applies_only_summary_sync(tmp_path):
    r, actions = harness(tmp_path)
    assert r.returncode == 0, r.stderr
    assert [a[0] for a in actions] == ["uv", "backup", "uv"]
    assert [a[5] for a in _sync_calls(actions)] == ["plan", "apply"]
    assert all(a[4] == MODULE for a in _sync_calls(actions))
    assert actions[1][1].endswith("tc-backups") and actions[1][2] == "3"
    flat = json.dumps(actions, ensure_ascii=False)
    for banned in ("cpbl-scrape", "cpbl-build-features", "cpbl-train", "migrate", "sync_table",
                   "pg_dump", "refresh_log", "game_features", "cpbl.rosters.sync"):
        assert banned not in flat
    plan = _sync_calls(actions)[0]
    local = plan[plan.index("--local-psql") + 1]
    target = plan[plan.index("--target-psql") + 1]
    assert local == "docker exec -i tc-fixture-db.invalid psql -U cpbl -d cpbl"
    argv = shlex.split(target)
    assert argv[:4] == ["ssh", "-o", "BatchMode=yes", "tc-fixture.invalid"]
    assert argv[4] == ('cd /not-a-deploy-path && set -a && . ./.env && docker exec -i prod_pg '
                       'psql -U "$DB_USER" -d "$DB_NAME"')


def test_no_change_skips_backup_and_write(tmp_path):
    r, actions = harness(tmp_path, mode="nochange")
    assert r.returncode == 0 and "無變更" in r.stdout
    assert [a[0] for a in actions] == ["uv"] and actions[0][5] == "plan"


@pytest.mark.parametrize(("mode", "code"), [("reject", 70), ("notable", 69), ("drift", 67)])
def test_reject_missing_table_or_drift_stops_before_backup(tmp_path, mode, code):
    r, actions = harness(tmp_path, mode=mode)
    assert r.returncode == code
    assert [a[0] for a in actions] == ["uv"]


def test_backup_failure_stops_before_write(tmp_path):
    r, actions = harness(tmp_path, R_BACKUP_FAIL="1")
    assert r.returncode != 0
    assert [a[0] for a in actions] == ["uv", "backup"]


@pytest.mark.parametrize("extra", [
    {"SKIP_SCRAPE": ""}, {"TEAM_COMPARISON_ONLY": "yes"}, {"WITH_DETAIL": "1"}, {"LINEUP_ONLY": "1"},
    {"ROSTER_ONLY": "1"}, {"POSTSEASON_RESULTS_ONLY": "1"}, {"BACKUP_DIR": ""},
    {"BACKUP_DIR": "tc-backups"},
])
def test_guards_exit_64_without_side_effects(tmp_path, extra):
    r, actions = harness(tmp_path, **extra)
    assert r.returncode == 64, (extra, r.stdout, r.stderr)
    assert actions == []


@pytest.mark.parametrize("variant", ["{d}", "{d}/", "{d}/.", "{d}/../backups", "{link}"])
def test_equivalent_daily_backup_paths_rejected(tmp_path, variant):
    home = tmp_path / "home"
    daily = home / "Library/Application Support/cpbl-analytics/backups"
    daily.mkdir(parents=True)
    link = tmp_path / "alias-of-daily"
    link.symlink_to(daily)
    r, actions = harness(tmp_path, HOME=str(home), BACKUP_DIR=variant.format(d=daily, link=link))
    assert r.returncode == 64 and actions == []


def test_roster_only_still_runs_its_own_mode_when_team_comparison_unset(tmp_path):
    """負控：未設 TEAM_COMPARISON_ONLY 時不進本模式（ROSTER_ONLY 路徑呼叫的是名單模組）。"""
    r, actions = harness(tmp_path, TEAM_COMPARISON_ONLY="", ROSTER_ONLY="1")
    assert all(MODULE not in a for a in actions)


def test_help_mentions_mode_and_has_no_side_effects(tmp_path):
    bins = tmp_path / "bin"
    bins.mkdir()
    for name in ["docker", "ssh", "uv", "curl"]:
        (bins / name).write_text(SHIM)
        (bins / name).chmod(0o755)
    calls = tmp_path / "calls.jsonl"
    r = subprocess.run(["bash", str(SCRIPT), "--help"], capture_output=True, text=True, timeout=10,
                       env={**os.environ, "PATH": f"{bins}{os.pathsep}{os.environ['PATH']}",
                            "R_CALLS": str(calls), "TEAM_COMPARISON_ONLY": "1", "SKIP_SCRAPE": "1"})
    assert r.returncode == 0 and "TEAM_COMPARISON_ONLY" in r.stdout
    assert not calls.exists()


# ------------------------------------------------------------------ 完整鏈接線（靜態結構）


def _body() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def test_full_chain_calls_summary_sync_after_gamelog_and_never_blocks():
    body = _body()
    detail = body[body.index('if [ -n "${WITH_DETAIL:-}" ]; then\n  sync_table batter_pitcher_matchups'):]
    # #293 把 box 七表的 sync_table 清單抽成 sync_box_<表>（完整鏈呼叫順序不變），這裡定位該呼叫。
    i_pit = detail.index("sync_box_pitching_gamelog")
    i_call = detail.index("if team_comparison_sync apply; then")
    assert i_pit < i_call < detail.index("sync_table batting_seasons")
    block = detail[i_call:detail.index("fi", i_call) + 2]
    assert "exit" not in block.replace("exit=$?", "")  # 失敗只記錄、不擋其他同步
    # 摘要三表 ⛔ 不進 sync_table 清單
    for t in ("team_comparison_build", "team_comparison_row", "team_comparison_current"):
        assert f"sync_table {t}" not in body


def test_team_comparison_mode_is_checked_before_roster_mode():
    body = _body()
    assert body.index('if [ -n "${TEAM_COMPARISON_ONLY:-}" ]; then') < body.index('if [ -n "${ROSTER_ONLY:-}" ]; then')


# ------------------------------------------------------------------ scrape-daily.sh builder 步驟


def _daily(tmp_path, *, scrape_exit=0, build_exit=0):
    repo = tmp_path / "repo"
    scripts = repo / "scripts"
    bins = tmp_path / "bin"
    scripts.mkdir(parents=True)
    bins.mkdir()
    shutil.copy2(ROOT / "scripts" / "scrape-daily.sh", scripts / "scrape-daily.sh")
    shutil.copy2(ROOT / "scripts" / "refresh_status.py", scripts / "refresh_status.py")
    calls = tmp_path / "calls.txt"
    (bins / "docker").write_text("#!/bin/sh\nprintf 'cpbl-analytics-db-1\\n'\n")
    (bins / "uv").write_text(
        f'#!/bin/sh\necho "uv $*" >> "{calls}"\n'
        f'case "$*" in *cpbl-build-team-comparison*) exit {build_exit};; *) exit {scrape_exit};; esac\n')
    (scripts / "refresh-cpbl-prod.sh").write_text(f'#!/bin/sh\necho "sync $SKIP_SCRAPE $WITH_DETAIL" >> "{calls}"\n')
    for f in (bins / "docker", bins / "uv", scripts / "refresh-cpbl-prod.sh"):
        f.chmod(0o755)
    env = {**os.environ, "PATH": f"{bins}:/usr/bin:/bin", "REFRESH_TRIGGER": "manual",
           "REFRESH_LOCK_DIR": str(tmp_path / "lock"), "SYNC_PROD": "1"}
    r = subprocess.run(["/bin/bash", str(scripts / "scrape-daily.sh")], cwd=repo, env=env, text=True,
                       capture_output=True, check=False)
    lines = calls.read_text().splitlines() if calls.exists() else []
    # #364：每日鏈另有日型閘門的 uv 呼叫（decide／today-schedule／mark-synced）。本檔只驗 builder 與
    # 爬取／同步的相對順序，故濾掉 daily_gate 呼叫；閘門本身由 tests/test_daily_gate.py 驗。
    lines = [ln for ln in lines if "cpbl.ingest.daily_gate" not in ln]
    return r, lines


@pytest.mark.parametrize("scrape_exit", [0, 69])
def test_daily_runs_builder_after_scrape_before_sync(tmp_path, scrape_exit):
    r, lines = _daily(tmp_path, scrape_exit=scrape_exit)
    assert r.returncode == scrape_exit, r.stdout
    assert [ln.split()[0] for ln in lines] == ["uv", "uv", "sync"]
    assert "cpbl-refresh-recent" in lines[0]
    assert "cpbl-build-team-comparison --year" in lines[1] and "--record-failure" in lines[1]


def test_daily_builder_failure_does_not_change_overall_or_block_sync(tmp_path):
    r, lines = _daily(tmp_path, build_exit=5)
    assert r.returncode == 0
    assert lines[-1].startswith("sync")
    assert "team-comparison build exit=5" in r.stdout


def test_daily_scrape_failure_skips_builder(tmp_path):
    r, lines = _daily(tmp_path, scrape_exit=2)
    assert r.returncode == 2
    assert not any("cpbl-build-team-comparison" in ln for ln in lines)
