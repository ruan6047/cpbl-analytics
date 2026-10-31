import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
SYSTEM_PYTHON = "/usr/bin/python3" if Path("/usr/bin/python3").exists() else sys.executable


# #398 python3 樁：攔 prod_availability.py（記 argv、停止檔是否已預建、當下狀態檔內容），
# 其餘一律 exec 系統 python3。FAIL_STATUS_START=1 讓 refresh_status.py start 失敗（B6 exit 70）。
_PYTHON3_STUB = r"""#!/bin/sh
case "$1" in
  */prod_availability.py)
    n=$(ls "$SENTINEL_CALL_DIR" | grep -c '^call-')
    f="$SENTINEL_CALL_DIR/call-$n.txt"
    : > "$f"
    prev=""
    for a in "$@"; do
      printf '%s\n' "$a" >> "$f"
      if [ "$prev" = "--stop-file" ] && [ -e "$a" ]; then echo '#stop-file-present' >> "$f"; fi
      prev="$a"
    done
    if [ -f logs/last-status.json ]; then cp logs/last-status.json "$SENTINEL_CALL_DIR/status-at-call-$n.json"; fi
    if [ -n "${SENTINEL_STUB_TERM_PARENT:-}" ]; then kill -TERM "$PPID"; fi
    if [ -n "${SENTINEL_STUB_WAIT_STOP:-}" ]; then
      # 仿真哨兵：停止檔不出現就一直量（真哨兵是 6 小時保險絲）；收到 SIGTERM 記下並結束。
      stop=$(sed -n '/^--stop-file$/{n;p;}' "$f")
      trap 'echo "#terminated" >> "$f"; exit 0' TERM
      while [ ! -e "$stop" ]; do sleep 0.1; done
      echo '#stopped-by-file' >> "$f"
    fi
    exit "${SENTINEL_STUB_RC:-0}"
    ;;
  */refresh_status.py)
    if [ "$2" = start ] && [ -n "${FAIL_STATUS_START:-}" ]; then exit 1; fi
    ;;
esac
exec @SYSTEM_PYTHON@ "$@"
"""


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
    announcement_lock: bool = False,
    day_type: str | None = None,
    sync_body: str | None = None,
    sync_prod: str = "1",
    extra_env: dict[str, str] | None = None,
    uv_body: str | None = None,
    extra_bin: dict[str, str] | None = None,
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
    if uv_body is not None:
        _executable(fake_bin / "uv", uv_body)
    elif day_type is not None:
        # 日型判定樁：decide 印出指定日型；其餘 uv 呼叫照 uv_exit。
        _executable(
            fake_bin / "uv",
            "#!/bin/sh\n"
            f'case "$*" in *"daily_gate decide"*) printf \'DAY_TYPE={day_type}\\nREASON=test\\n\'; exit 0;; esac\n'
            f"exit {uv_exit}\n",
        )
    else:
        _executable(fake_bin / "uv", f"#!/bin/sh\nexit {uv_exit}\n")
    _executable(scripts / "refresh-cpbl-prod.sh", sync_body or f"#!/bin/sh\nexit {sync_exit}\n")
    # #398：每次執行都裝上 python3 樁。prod_availability.py 的呼叫只記錄、⛔ 不打任何端點；
    # 其餘（refresh_status.py）交回系統 python3。
    sentinel_calls = tmp_path / "sentinel-calls"
    sentinel_calls.mkdir()
    _executable(fake_bin / "python3", _PYTHON3_STUB.replace("@SYSTEM_PYTHON@", SYSTEM_PYTHON))
    (tmp_path / "tmp").mkdir()
    for name, body in (extra_bin or {}).items():
        _executable(fake_bin / name, body)

    lock_dir = tmp_path / "refresh.lock"
    if active_lock_pid is not None:
        lock_dir.mkdir()
        (lock_dir / "pid").write_text(str(active_lock_pid), encoding="utf-8")
        if announcement_lock:
            (lock_dir / "kind").write_text("lineup-announcements")
            _executable(fake_bin / "sleep", f"#!/bin/sh\nrm '{lock_dir}/pid' '{lock_dir}/kind'\nrmdir '{lock_dir}'\n")

    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_bin}:/usr/bin:/bin",
            "REFRESH_TRIGGER": trigger,
            "REFRESH_LOCK_DIR": str(lock_dir),
            "SYNC_PROD": sync_prod,
            "TMPDIR": str(tmp_path / "tmp"),
            "SENTINEL_CALL_DIR": str(sentinel_calls),
            # fail-safe：樁沒攔到也打不到正式站、送不出 ping。
            "API_INFO_URL": "http://127.0.0.1:9/api/info",
            **(extra_env or {}),
        }
    )
    env.pop("CPBL_AVAILABILITY_PING_URL", None)
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

    check = _check_scheduled(repo, now=started_at + timedelta(minutes=1))

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
        "backup-prod-db.sh",
        "verify_refresh_info.py",
    ):
        shutil.copy2(ROOT / "scripts" / script_name, scripts / script_name)

    _executable(
        fake_bin / "docker",
        """#!/bin/bash
if [ "$1" = "ps" ]; then
  echo cpbl-analytics-db-1
elif [[ "$*" == *information_schema.columns* ]]; then
  # sync_table 的欄位漂移守衛（2026-09-23）查本機 schema；回空＝守衛放行。本測試驗的是
  # SQL 錯誤沿 sync 相傳遞（exit 42），守衛本身見 tests/test_sync_table_column_guard.py。
  :
elif [[ "$*" == *" psql "* ]]; then
  echo '2026-07-16|3'
elif [[ "$*" == *" pg_dump "* && "$*" == *game_lineup_announcement_revisions* ]]; then
  printf '%s\\n' 'COPY cpbl.game_lineup_announcement_revisions (year, kind_code, game_sno, source_type, source_url, fetched_at, content_hash, raw_status, raw_payload, last_seen_at) FROM stdin;' '\\.'
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
  # 假 dump 需含 CREATE TABLE，否則會被 backup-prod-db.sh 的內容門檻擋在備份階段
  # （exit 66），本測試就走不到它要驗的 sync SQL 錯誤傳遞。
  echo 'CREATE SCHEMA cpbl;'
  echo 'CREATE TABLE cpbl.games (id integer);'
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
            # 本測試驗的是 SQL 錯誤沿著 sync 相傳遞（exit 42），不是備份內容門檻。
            # 假 dump 只有幾行，會撞到 backup-prod-db.sh 的正式門檻（90 表／100 MB）
            # 而在備份階段就以 65 中止，測試永遠走不到要驗的地方。
            "BACKUP_MIN_TABLES": "1",
            "BACKUP_MIN_BYTES": "1",
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


def test_natural_daily_queues_for_transient_announcement_owner_then_runs_entire_chain(tmp_path):
    result,status=_run_daily(tmp_path,trigger="launchd",active_lock_pid=os.getpid(),announcement_lock=True)
    assert result.returncode==0
    assert status["state"]=="succeeded" and status["scrape_ok"] and status["sync_ok"]
    assert status["trigger"]=="launchd"  # 合成wrapper證據，不當實際10:10自然run。


# ============================================ #398 非同步日的可用性補位（B1–B7）


def _sentinel_calls(tmp_path: Path) -> list[list[str]]:
    """python3 樁錄下的 prod_availability.py 呼叫（每次一個檔，依序號排序）。"""
    files = sorted((tmp_path / "sentinel-calls").glob("call-*.txt"), key=lambda p: int(p.stem.split("-")[1]))
    return [p.read_text(encoding="utf-8").splitlines() for p in files]


def _assert_one_fallback_with_existing_sentinel_args(tmp_path: Path) -> list[str]:
    calls = _sentinel_calls(tmp_path)
    assert len(calls) == 1, f"補位應剛好 1 次，實際 {len(calls)} 次：{calls}"
    argv = calls[0]
    repo = tmp_path / "repo"
    assert argv[0] == str(repo / "scripts" / "prod_availability.py")
    assert argv[1] == "sentinel", "必須是既有哨兵子命令（不是 probe、不是第二套判準）"
    assert argv[argv.index("--base-url") + 1] == "http://127.0.0.1:9", "base 由 API_INFO_URL 去掉 /api/info"
    assert argv[argv.index("--env-file") + 1] == str(repo / ".env")
    out = argv[argv.index("--out") + 1]
    assert out.startswith(str(repo / "logs" / "availability-sentinel-")) and out.endswith(".tsv")
    assert "#stop-file-present" in argv, "停止檔須預先建好（取樣一輪後再量 120 秒即判定）"
    assert not list((tmp_path / "tmp").glob("cpbl-daily-sentinel-*")), "停止檔與 marker 須清掉"
    return argv


def _assert_status_untouched_by_fallback(tmp_path: Path) -> None:
    """補位在狀態檔寫完之後才跑，且不改它：補位當下的內容＝最終內容。"""
    snapshot = tmp_path / "sentinel-calls" / "status-at-call-0.json"
    final = tmp_path / "repo" / "logs" / "last-status.json"
    assert snapshot.exists() and final.exists()
    assert json.loads(snapshot.read_text(encoding="utf-8")) == json.loads(final.read_text(encoding="utf-8"))
    assert json.loads(final.read_text(encoding="utf-8"))["state"] != "running", "補位須在 finish 寫完之後"


def _log_text(tmp_path: Path) -> str:
    return next((tmp_path / "repo" / "logs").glob("refresh-*.log")).read_text(encoding="utf-8")


# 補位本身成功或失敗（樁回 0／1）都不得改變離開碼與狀態檔。
_SENTINEL_RC = [{}, {"SENTINEL_STUB_RC": "1"}]
_SENTINEL_RC_IDS = ["sentinel-rc0", "sentinel-rc1"]


@pytest.mark.parametrize("extra", _SENTINEL_RC, ids=_SENTINEL_RC_IDS)
def test_b1_skip_day_runs_fallback_once_and_keeps_exit_code(tmp_path: Path, extra) -> None:
    result, status = _run_daily(tmp_path, trigger="launchd", day_type="skip", extra_env=extra)

    assert result.returncode == 0
    assert status["state"] == "succeeded" and status["skipped"] is True
    assert status["sync_attempted"] is False
    _assert_one_fallback_with_existing_sentinel_args(tmp_path)
    _assert_status_untouched_by_fallback(tmp_path)
    log = _log_text(tmp_path)
    assert "可用性補位" in log and "day_type=skip" in log


@pytest.mark.parametrize("extra", _SENTINEL_RC, ids=_SENTINEL_RC_IDS)
def test_b2_missing_local_database_runs_fallback_once(tmp_path: Path, extra) -> None:
    result, status = _run_daily(tmp_path, docker_running=False, extra_env=extra)

    assert result.returncode == 127
    assert status["failed_phase"] == "scrape" and status["sync_attempted"] is False
    _assert_one_fallback_with_existing_sentinel_args(tmp_path)
    _assert_status_untouched_by_fallback(tmp_path)


@pytest.mark.parametrize("extra", _SENTINEL_RC, ids=_SENTINEL_RC_IDS)
def test_b3_scrape_failure_runs_fallback_once(tmp_path: Path, extra) -> None:
    result, status = _run_daily(tmp_path, uv_exit=9, extra_env=extra)

    assert result.returncode == 9
    assert status["failed_phase"] == "scrape" and status["sync_attempted"] is False
    _assert_one_fallback_with_existing_sentinel_args(tmp_path)
    _assert_status_untouched_by_fallback(tmp_path)


@pytest.mark.parametrize("extra", _SENTINEL_RC, ids=_SENTINEL_RC_IDS)
def test_b4_sync_disabled_runs_fallback_once(tmp_path: Path, extra) -> None:
    result, status = _run_daily(tmp_path, sync_prod="0", extra_env=extra)

    assert result.returncode == 0
    assert status["state"] == "succeeded" and status["sync_attempted"] is False
    _assert_one_fallback_with_existing_sentinel_args(tmp_path)
    _assert_status_untouched_by_fallback(tmp_path)


@pytest.mark.parametrize("extra", _SENTINEL_RC, ids=_SENTINEL_RC_IDS)
def test_b5_sync_attempted_but_refresh_ended_before_sentinel_runs_fallback_once(tmp_path: Path, extra) -> None:
    """refresh 在啟動哨兵前結束（例：exit 65 取不到 freshness 基準）＝沒寫 marker ⇒ 要補。"""
    result, status = _run_daily(tmp_path, sync_exit=65, extra_env=extra)

    assert result.returncode == 65
    assert status["failed_phase"] == "sync" and status["sync_attempted"] is True
    assert status["sync_exit_code"] == 65
    _assert_one_fallback_with_existing_sentinel_args(tmp_path)
    _assert_status_untouched_by_fallback(tmp_path)


@pytest.mark.parametrize("extra", _SENTINEL_RC, ids=_SENTINEL_RC_IDS)
def test_b6_start_status_write_failure_runs_fallback_once(tmp_path: Path, extra) -> None:
    result, status = _run_daily(tmp_path, extra_env={"FAIL_STATUS_START": "1", **extra})

    assert result.returncode == 70
    assert status == {}, "start 失敗時本來就沒有狀態檔；補位不得補寫"
    _assert_one_fallback_with_existing_sentinel_args(tmp_path)
    log = _log_text(tmp_path)
    assert "無法寫入 refresh running 狀態" in log and "exit=70" in log


def test_b7_trapped_signal_runs_fallback_once_and_keeps_signal_exit_code(tmp_path: Path) -> None:
    """爬取中收到 SIGTERM（launchd 停止）：照原碼 143 離開，補位仍跑一次。"""
    uv = (
        "#!/bin/sh\n"
        'case "$*" in *cpbl-refresh-recent*) kill -TERM "$PPID";; esac\n'
        "exit 0\n"
    )
    result, status = _run_daily(tmp_path, trigger="launchd", uv_body=uv)

    assert result.returncode == 143
    assert status["state"] == "running", "訊號中斷時狀態檔本來就停在 running（不由補位改寫）"
    _assert_one_fallback_with_existing_sentinel_args(tmp_path)


def test_signal_during_fallback_still_releases_lock_and_keeps_exit_code(tmp_path: Path) -> None:
    """補位期間收到 SIGTERM：放鎖、照原碼離開（狀態檔在補位前已定案），不留 stale lock。"""
    result, status = _run_daily(tmp_path, day_type="skip", extra_env={"SENTINEL_STUB_TERM_PARENT": "1"})

    assert result.returncode == 0
    assert status["state"] == "succeeded"
    assert len(_sentinel_calls(tmp_path)) == 1
    assert not (tmp_path / "refresh.lock").exists(), "中斷補位不得留下 refresh lock"
    assert not list((tmp_path / "tmp").glob("cpbl-daily-sentinel-*")), "停止檔與 marker 須清掉"


_MARKING_REFRESH = '#!/bin/sh\n: > "$DAILY_SENTINEL_MARKER"\nexit {rc}\n'


@pytest.mark.parametrize("rc", [0, 17], ids=["sync-ok", "sync-failed-after-sentinel"])
def test_sync_day_with_marker_runs_no_fallback(tmp_path: Path, rc: int) -> None:
    """同步日：refresh 已啟動哨兵（寫了 marker）⇒ 補位 0 次，離開碼與狀態照舊（#398 驗收 3）。"""
    result, status = _run_daily(tmp_path, trigger="launchd", sync_body=_MARKING_REFRESH.format(rc=rc))

    assert result.returncode == rc
    assert status["sync_attempted"] is True and status["sync_ok"] is (rc == 0)
    assert _sentinel_calls(tmp_path) == []
    assert not list((tmp_path / "tmp").glob("cpbl-daily-sentinel-*")), "marker 用完須清掉"
    assert "可用性補位" not in _log_text(tmp_path)


def test_lock_contention_exit_does_not_run_fallback(tmp_path: Path) -> None:
    """75（取鎖失敗）屬「鏈本身沒執行」（#398 D1）：不補位，也不碰別人的 marker。"""
    result, _ = _run_daily(tmp_path, active_lock_pid=os.getpid())

    assert result.returncode == 75
    assert _sentinel_calls(tmp_path) == []


def test_fallback_has_no_success_path_of_its_own() -> None:
    """主風險（無條件送成功）：補位只呼叫既有 sentinel，自己不送 ping、不讀 ping URL、不判定。"""
    source = (ROOT / "scripts" / "scrape-daily.sh").read_text(encoding="utf-8")
    body = source.split("availability_fallback() {", 1)[1].split("\n}\n", 1)[0]
    assert body.count("prod_availability.py") == 1
    assert 'prod_availability.py" sentinel ' in body
    for forbidden in ("curl", "CPBL_AVAILABILITY_PING_URL", " probe", "/fail", "urllib"):
        assert forbidden not in body, forbidden
    trap_lines = [ln.strip() for ln in source.splitlines() if ln.strip().startswith("trap ") and "EXIT" in ln]
    assert trap_lines == ["trap on_exit EXIT"], trap_lines


# ------------------------------------------- #398 審核第 1 輪 F1：補位必須有界、停止檔要建得起來


def test_f1_unusable_tmpdir_moves_stop_file_to_logs_so_fallback_stays_short(tmp_path: Path) -> None:
    """TMPDIR 不存在：停止檔與 marker 改放 logs/，補位照樣預建停止檔（不會等 6 小時保險絲）。"""
    result, status = _run_daily(
        tmp_path, day_type="skip",
        extra_env={"TMPDIR": str(tmp_path / "no-such-tmp"), "SENTINEL_STUB_WAIT_STOP": "1"},
    )

    assert result.returncode == 0
    assert status["state"] == "succeeded"
    argv = _assert_one_fallback_with_existing_sentinel_args(tmp_path)
    assert argv[argv.index("--stop-file") + 1].startswith(str(tmp_path / "repo" / "logs" / "cpbl-daily-sentinel-stop."))
    assert "#stopped-by-file" in argv and "#terminated" not in argv
    assert not list((tmp_path / "repo" / "logs").glob("cpbl-daily-sentinel-*")), "logs/ 裡的停止檔與 marker 須清掉"
    assert not (tmp_path / "refresh.lock").exists()


def test_f1_stop_file_creation_failure_is_bounded_and_releases_lock(tmp_path: Path) -> None:
    """停止檔建不起來（審核 F1 的失效）：補位在上限內 SIGTERM 收尾、放鎖，離開碼與狀態不變。

    假 `touch` 只對停止檔失敗；python3 樁仿真真哨兵「停止檔不出現就一直量」。沒有上限時本測試會卡到
    pytest 逾時（真哨兵是 6 小時）。上限以 DAILY_SENTINEL_WAIT_MAX 縮成 2 秒。
    """
    import time

    started = time.monotonic()
    result, status = _run_daily(
        tmp_path, day_type="skip",
        extra_env={"SENTINEL_STUB_WAIT_STOP": "1", "DAILY_SENTINEL_WAIT_MAX": "2"},
        extra_bin={"touch": '#!/bin/sh\ncase "$*" in *cpbl-daily-sentinel-stop*) exit 1;; esac\n'
                            'exec /usr/bin/touch "$@"\n'},
    )
    elapsed = time.monotonic() - started

    assert elapsed < 30, f"補位沒有被上限收尾（{elapsed:.1f}s）"
    assert result.returncode == 0
    assert status["state"] == "succeeded" and status["skipped"] is True
    calls = _sentinel_calls(tmp_path)
    assert len(calls) == 1
    assert "#stop-file-present" not in calls[0], "前提：停止檔確實沒建起來"
    assert "#terminated" in calls[0], "逾時須送 SIGTERM（真哨兵據此以偵測器失敗告警）"
    _assert_status_untouched_by_fallback(tmp_path)
    assert not (tmp_path / "refresh.lock").exists(), "補位收尾後必須放鎖"
    log = _log_text(tmp_path)
    assert "停止檔建立失敗" in log and "已送 SIGTERM" in log


def test_f1_fallback_wait_bound_matches_refresh_sentinel_bound() -> None:
    """預設上限與 refresh 的 SENTINEL_WAIT_MAX 同值，且涵蓋 tail＋一輪取樣（不是隨手選的數字）。"""
    daily = (ROOT / "scripts" / "scrape-daily.sh").read_text(encoding="utf-8")
    refresh = (ROOT / "scripts" / "refresh-cpbl-prod.sh").read_text(encoding="utf-8")
    default = int(daily.split('FALLBACK_WAIT_MAX="${DAILY_SENTINEL_WAIT_MAX:-', 1)[1].split("}", 1)[0])
    assert default == int(refresh.split("SENTINEL_WAIT_MAX=", 1)[1].split("\n", 1)[0])
    assert default >= 120 + 3 * (10 + 5)


# ------------------------------------------- #398 審核第 1 輪 F2：marker 失敗路徑也只有一個哨兵


def _refresh_stub_with_real_sentinel_start() -> str:
    """假 refresh：逐字嵌入真 `start_availability_sentinel`，只呼叫它（uv 是只記錄的樁）。

    FORCE_MARKER_FAIL=1 把 refresh 這一側的 marker 路徑改到不存在的目錄＝模擬寫入失敗；每日鏈那一側
    看的仍是原路徑，所以組合起來就是審核 F2 的情境。
    """
    source = (ROOT / "scripts" / "refresh-cpbl-prod.sh").read_text(encoding="utf-8")
    start = source.index("start_availability_sentinel() {")
    func = source[start:source.index("\n}\n", start) + 3]
    return (
        "#!/bin/bash\nset -euo pipefail\n"
        'REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"\n'
        'API_INFO_URL="${API_INFO_URL:-https://cpbl.ruan-ruan.com/api/info}"\n'
        'SENTINEL_PID=""\nSENTINEL_STOP=""\n'
        f"{func}"
        'if [ -n "${FORCE_MARKER_FAIL:-}" ]; then DAILY_SENTINEL_MARKER="$DAILY_SENTINEL_MARKER.no-such-dir/x"; fi\n'
        'start_availability_sentinel || echo "start failed" >&2\n'
        '[ -z "$SENTINEL_PID" ] || wait "$SENTINEL_PID" || true\n'
        "exit 0\n"
    )


_RECORDING_UV = (
    "#!/bin/sh\n"
    'case "$*" in *prod_availability.py*)\n'
    '  n=$(ls "$SENTINEL_CALL_DIR" | grep -c \'^sync-\')\n'
    '  printf \'%s\\n\' "$@" > "$SENTINEL_CALL_DIR/sync-$n.txt";;\n'
    "esac\n"
    "exit 0\n"
)


@pytest.mark.parametrize(
    ("extra", "sync_launches", "fallback_launches"),
    [({}, 1, 0), ({"FORCE_MARKER_FAIL": "1"}, 0, 1)],
    ids=["marker-ok", "marker-write-fails"],
)
def test_f2_daily_chain_with_real_sentinel_start_launches_exactly_one(
    tmp_path: Path, extra, sync_launches: int, fallback_launches: int
) -> None:
    """組合：真每日鏈＋真 start_availability_sentinel。marker 成敗兩路都只啟動一個哨兵。"""
    result, status = _run_daily(
        tmp_path, trigger="launchd", uv_body=_RECORDING_UV,
        sync_body=_refresh_stub_with_real_sentinel_start(), extra_env=extra,
    )

    assert result.returncode == 0, result.stderr
    assert status["sync_attempted"] is True and status["sync_ok"] is True
    sync = list((tmp_path / "sentinel-calls").glob("sync-*.txt"))
    assert len(sync) == sync_launches
    assert len(_sentinel_calls(tmp_path)) == fallback_launches
    assert len(sync) + len(_sentinel_calls(tmp_path)) == 1, "同一次鏈執行只能有一個哨兵（驗收 3、D4）"
    if extra:
        assert "marker 寫入失敗" in _log_text(tmp_path)
    assert not list((tmp_path / "tmp").glob("cpbl-daily-sentinel-*"))
