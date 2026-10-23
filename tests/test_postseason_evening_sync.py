"""#268 WP3：`refresh-cpbl-prod.sh` 的 POSTSEASON_RESULTS_ONLY 分支與 `postseason-evening.sh` 編排。

一律跑**副本／symlink 到假 repo**＋假 `ssh`／`docker`／`uv`／`curl`／`python3`／`launchctl`，
`VPS` 指向 `.invalid`、`LOCAL_DB` 不存在——零 DB、零網路、零真實排程（沿用
`tests/test_prod_sync_revision_seq.py` 的 harness）。證明的是：

* 晚間分支**只碰三表＋異動訊號表**（games／game_schedule_status_revisions／game_source_revisions／
  official_change_signals；訊號表為 #268 B1 需求方裁定 6142744045），不同步 074 公告表、不 TRUNCATE、
  不 migration、不 build-features、不訓練、不寫 prod refresh 標記；
* 備份走**獨立 BACKUP_DIR**（不輪替掉 10:10 的 7 份），且未明示時拒跑；
* 編排腳本：無事件不取鎖、不連 www；鎖被佔一律 exit 75 且不刪鎖；同步失敗即 halt 並 bootout；
  三表沒變（或 www 失敗）但訊號表待同步時，仍走同一條已驗證備份→同步路徑（僅訊號變動）。
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from tests.test_prod_sync_revision_seq import (
    FAKE_LOCAL_SEQ,
    FAKE_PROD_MAX,
    _build_harness,
    _run_refresh,
)

ROOT = Path(__file__).resolve().parents[1]
REFRESH = ROOT / "scripts" / "refresh-cpbl-prod.sh"
EVENING = ROOT / "scripts" / "postseason-evening.sh"
THREE_TABLES = ("games", "game_schedule_status_revisions", "game_source_revisions")
SIGNALS_TABLE = "official_change_signals"


# =========================================================== refresh-cpbl-prod.sh 分支

def _run_results_only(tmp_path: Path, **env_overrides: str):
    harness = _build_harness(tmp_path)
    if env_overrides.pop("STUB_VERIFY_FAIL", None):
        # verify_refresh_info.py 由假 python3 執行；改成讀完 stdin 後以 3（對帳不等）結束。
        py = harness["bin"] / "python3"
        py.write_text("#!/bin/sh\ncat > /dev/null\nexit 3\n", encoding="utf-8")
        py.chmod(0o755)
    backup_log = tmp_path / "backup-env.txt"
    stub = harness["repo"] / "scripts" / "backup-prod-db.sh"
    stub.unlink()
    stub.write_text(
        "#!/bin/sh\n"
        f"printf 'BACKUP_DIR=%s\\nBACKUP_KEEP=%s\\nUMASK=%s\\n' \"$BACKUP_DIR\" \"$BACKUP_KEEP\" \"$(umask)\" > {backup_log}\n"
        "echo /fixture/evening-backup.sql.gz\n", encoding="utf-8")
    stub.chmod(0o755)
    (tmp_path / "tmp").mkdir(exist_ok=True)
    env = {
        "PATH": f"{harness['bin']}:/usr/bin:/bin",
        "HOME": str(tmp_path / "home"),
        "TMPDIR": str(tmp_path / "tmp"),
        "STUB_LOG_DIR": str(harness["log"]),
        "STUB_HELPER_DIR": str(harness["helpers"]),
        "STUB_LOCAL_SEQ": json.dumps(FAKE_LOCAL_SEQ),
        "STUB_PROD_MAX": json.dumps(FAKE_PROD_MAX),
        "VPS": "stub@harness.invalid",
        "LOCAL_DB": "stub-nonexistent-container",
        "DEPLOY_PATH": "/nonexistent/stub-deploy",
        "API_INFO_URL": "http://127.0.0.1:1/api/info",
        "POSTSEASON_RESULTS_ONLY": "1",
        "SKIP_SCRAPE": "1",
        "BACKUP_DIR": str(tmp_path / "evening-backups"),
        "BACKUP_KEEP": "3",
        **env_overrides,
    }
    env = {k: v for k, v in env.items() if v is not None}
    result = subprocess.run(["/bin/bash", str(harness["repo"] / "scripts" / REFRESH.name)],
                            env=env, text=True, capture_output=True, stdin=subprocess.DEVNULL,
                            check=False)

    def calls(kind: str) -> list[dict]:
        d = harness["log"] / kind
        return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(d.glob("*.json"))] if d.is_dir() else []

    return result, calls, backup_log


def test_results_only_touches_exactly_the_three_tables_plus_signals_and_nothing_else(tmp_path: Path):
    result, calls, backup_log = _run_results_only(tmp_path)
    assert result.returncode == 0, result.stderr

    payloads = [c["stdin"] for c in calls("ssh") if c["stdin"]]
    synced = sorted({m for p in payloads for m in re.findall(r"^INSERT INTO cpbl\.(\w+) ", p, re.M)})
    assert synced == sorted((*THREE_TABLES, SIGNALS_TABLE))
    (signals,) = [p for p in payloads if f"INSERT INTO cpbl.{SIGNALS_TABLE} " in p]
    assert "ON CONFLICT (year,kind_code,game_sno,field) DO UPDATE SET" in signals
    assert "official_value=EXCLUDED.official_value" in signals and "resolved_at=EXCLUDED.resolved_at" in signals
    assert "DELETE" not in signals, "本機只 resolve 不刪列；同步只 upsert"
    joined = "\n".join(payloads) + "\n".join(" ".join(c["argv"]) for c in calls("ssh"))
    for forbidden in ("game_lineup_announcement_revisions", "TRUNCATE", "refresh_log",
                      "db.migrate", "cpbl-train", "game_features"):
        assert forbidden not in joined, forbidden
    # 假 uv 會把非 completion 的呼叫原樣印到 stdout：有 build-features／訓練就看得到。
    assert "cpbl-build-features" not in result.stdout and "cpbl-train" not in result.stdout
    assert "BACKUP_DIR=" + str(tmp_path / "evening-backups") in backup_log.read_text()
    assert "BACKUP_KEEP=3" in backup_log.read_text()
    assert "UMASK=" in backup_log.read_text(), "備份已被呼叫；0600 由 producer 自身保證（見下一條）"
    assert "季後晚間：完成" in result.stdout
    assert "寫入 production refresh 成功標記" not in result.stdout


def test_backup_created_under_owner_only_umask_is_0600(tmp_path: Path):
    """合成：真 backup-prod-db.sh（假 ssh、低門檻）不論呼叫端 umask 077 或 022 → 目錄 0700、檔案 0600。
    producer 自身 umask 077 是唯一責任層（需求方裁定 6138860627），晚間分支不再另設 umask。"""
    import stat

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    (fake_bin / "ssh").write_text("#!/bin/sh\nprintf '%s\\n' 'CREATE TABLE cpbl.games(id int);'\n", encoding="utf-8")
    (fake_bin / "ssh").chmod(0o755)
    script = ROOT / "scripts" / "backup-prod-db.sh"

    def run(mask: str, backup_dir: Path) -> Path:
        env = {"PATH": f"{fake_bin}:/usr/bin:/bin", "HOME": str(tmp_path / "home"),
               "BACKUP_DIR": str(backup_dir), "BACKUP_MIN_TABLES": "1", "BACKUP_MIN_BYTES": "1",
               "VPS": "stub@harness.invalid", "DEPLOY_PATH": "/nonexistent/stub-deploy"}
        out = subprocess.run(["/bin/bash", "-c", f'umask {mask}; exec /bin/bash "$0"', str(script)],
                             env=env, text=True, capture_output=True, check=True)
        return Path(out.stdout.strip())

    evening = run("077", tmp_path / "evening")
    assert stat.S_IMODE(evening.stat().st_mode) == 0o600
    assert stat.S_IMODE(evening.parent.stat().st_mode) == 0o700
    normal = run("022", tmp_path / "normal")
    assert stat.S_IMODE(normal.stat().st_mode) == 0o600, "呼叫端 umask 022 也不得產出 0644"


def test_results_only_refuses_shared_or_missing_backup_dir(tmp_path: Path):
    for i, bad in enumerate((None, "{HOME}/Library/Application Support/cpbl-analytics/backups")):
        home = tmp_path / f"r{i}" / "home"
        value = bad.replace("{HOME}", str(home)) if bad else None
        result, calls, _ = _run_results_only(tmp_path / f"r{i}", BACKUP_DIR=value)
        assert result.returncode == 64, result.stderr
        assert not calls("ssh"), "拒跑前不得碰 production"


def test_results_only_requires_skip_scrape_and_rejects_detail(tmp_path: Path):
    result, calls, _ = _run_results_only(tmp_path / "a", SKIP_SCRAPE=None)
    assert result.returncode == 64 and not calls("ssh")
    result, calls, _ = _run_results_only(tmp_path / "b", WITH_DETAIL="1")
    assert result.returncode == 64 and not calls("ssh")


def test_results_only_freshness_gate_is_identical_to_the_full_chain():
    """晚間分支的 freshness 基準與完整鏈逐字同源（同一支 helper、同一段 SQL）。"""
    text = REFRESH.read_text(encoding="utf-8")
    blocks = re.findall(
        r'COMPLETED_GAMES_SQL="\$\(uv run python -m cpbl\.completion --with-evidence\)"\n'
        r'\s*LOCAL_FRESHNESS="\$\(docker exec[^\n]*\n[^\n]*\n[^\n]*\n[^\n]*FROM cpbl\.games g"\)"', text)
    assert len(blocks) == 2
    norm = [re.sub(r"\s+", " ", b) for b in blocks]
    assert norm[0] == norm[1]


def test_full_chain_still_syncs_the_three_tables_once():
    text = REFRESH.read_text(encoding="utf-8")
    assert text.count("sync_table games ") == 1
    assert text.count("sync_revision_table game_schedule_status_revisions") == 1
    assert text.count(f"sync_table {SIGNALS_TABLE} ") == 1, "訊號表只在共用清單出現一次（兩鏈不各寫一份）"
    assert text.count("\nsync_postseason_results\n") == 1


def test_existing_daily_chain_also_syncs_the_signal_table_once(tmp_path: Path):
    """B1：既有每日鏈（SKIP_SCRAPE=1 WITH_DETAIL=1，同 scrape-daily.sh）在同一次已驗證備份後也帶上訊號表。"""
    result, calls = _run_refresh(tmp_path)
    assert result.returncode == 0, result.stderr
    hits = [c["stdin"] for c in calls if f"INSERT INTO cpbl.{SIGNALS_TABLE} AS tgt" in c["stdin"]]
    assert len(hits) == 1


# =========================================================== postseason-evening.sh 編排

_UV_STUB = """#!/bin/sh
mkdir -p "$STUB_CALLS"
printf '%s\\n' "$*" >> "$STUB_CALLS/uv.txt"
case "$*" in
  *" plan") echo "$STUB_PLAN" ;;
  *" scrape") echo "$STUB_SCRAPE" ;;
  *" sync-due") echo "${STUB_SYNC_DUE:-no}" ;;
  *"record-sync --code 0") echo synced ;;
  *"record-sync --code 68") echo blocked ;;
  *"record-sync --code "*) echo halted ;;
  *" finish") echo ok ;;
esac
"""

_SYNC_STUB = """#!/bin/sh
{
  printf 'POSTSEASON_RESULTS_ONLY=%s\\n' "${POSTSEASON_RESULTS_ONLY:-}"
  printf 'SKIP_SCRAPE=%s\\n' "${SKIP_SCRAPE:-}"
  printf 'WITH_DETAIL=%s\\n' "${WITH_DETAIL:-}"
  printf 'BACKUP_DIR=%s\\n' "${BACKUP_DIR:-}"
  printf 'BACKUP_KEEP=%s\\n' "${BACKUP_KEEP:-}"
  printf 'ARGC=%s\\n' "$#"
} > "$STUB_CALLS/sync.txt"
exit "${STUB_SYNC_EXIT:-0}"
"""


def _evening(tmp_path: Path, *, plan: str, scrape: str = "unchanged", sync_exit: int = 0,
             lock_pid: int | None = None, lock_kind: str | None = None, trigger: str = "manual",
             sync_due: str = "no"):
    repo, fake_bin, calls = tmp_path / "repo", tmp_path / "bin", tmp_path / "calls"
    (repo / "scripts").mkdir(parents=True)
    fake_bin.mkdir()
    shutil.copy2(EVENING, repo / "scripts" / EVENING.name)
    for name, body in (("uv", _UV_STUB),
                       ("launchctl", '#!/bin/sh\nmkdir -p "$STUB_CALLS"\nprintf \'%s\\n\' "$*" >> "$STUB_CALLS/launchctl.txt"\n')):
        (fake_bin / name).write_text(body, encoding="utf-8")
        (fake_bin / name).chmod(0o755)
    (repo / "scripts" / "refresh-cpbl-prod.sh").write_text(_SYNC_STUB, encoding="utf-8")
    lock = tmp_path / "lock"
    if lock_pid is not None:
        lock.mkdir()
        (lock / "pid").write_text(f"{lock_pid}\n")
        if lock_kind:
            (lock / "kind").write_text(f"{lock_kind}\n")
    env = {"PATH": f"{fake_bin}:/usr/bin:/bin", "HOME": str(tmp_path / "home"),
           "STUB_CALLS": str(calls), "STUB_PLAN": plan, "STUB_SCRAPE": scrape,
           "STUB_SYNC_EXIT": str(sync_exit), "STUB_SYNC_DUE": sync_due, "REFRESH_LOCK_DIR": str(lock),
           "REFRESH_TRIGGER": trigger,
           "POSTSEASON_BACKUP_DIR": str(tmp_path / "evening-backups")}
    result = subprocess.run(["/bin/bash", str(repo / "scripts" / EVENING.name)], cwd=repo, env=env,
                            text=True, capture_output=True, stdin=subprocess.DEVNULL, check=False)

    def read(name: str) -> str:
        p = calls / name
        return p.read_text(encoding="utf-8") if p.exists() else ""

    return result, read, lock


def test_no_event_takes_no_lock_and_never_reaches_www(tmp_path: Path):
    result, read, lock = _evening(tmp_path, plan="idle")
    assert result.returncode == 0
    assert "scrape" not in read("uv.txt") and "--group scrape" not in read("uv.txt")
    assert not read("sync.txt")
    assert not lock.exists()


def test_quiet_plan_takes_no_lock_and_skips_boxpa_precheck(tmp_path: Path):
    """#365 (b)：plan 回 quiet（今晚無排定場、無待辦）→ 連 boxpa-plan --dry（會連 DB）都不跑、不取鎖、exit 0。
    對照上一條：idle 時仍會跑 boxpa-plan --dry（box／PA 預檢），所以 quiet 早退是可觀察的差異。"""
    result, read, lock = _evening(tmp_path, plan="quiet")
    assert result.returncode == 0, result.stderr
    calls = read("uv.txt")
    assert "postseason_evening plan" in calls
    assert "boxpa-plan" not in calls and "finish" not in calls and "scrape" not in calls
    assert not read("sync.txt") and not lock.exists()
    idle, read_idle, _ = _evening(tmp_path / "idle", plan="idle")
    assert idle.returncode == 0 and "boxpa-plan --dry" in read_idle("uv.txt"), "負控：idle 仍做 box／PA 預檢"


def test_event_without_change_scrapes_once_and_does_not_sync(tmp_path: Path):
    result, read, lock = _evening(tmp_path, plan="scrape", scrape="unchanged")
    assert result.returncode == 0, result.stderr
    assert read("uv.txt").count("--group scrape python -m cpbl.ingest.postseason_evening scrape") == 1
    assert not read("sync.txt")
    assert not lock.exists(), "鎖必須真釋放"


def test_change_triggers_three_table_sync_with_independent_backup(tmp_path: Path):
    result, read, lock = _evening(tmp_path, plan="scrape", scrape="changed")
    assert result.returncode == 0, result.stderr
    sync = dict(line.split("=", 1) for line in read("sync.txt").splitlines())
    assert sync == {"POSTSEASON_RESULTS_ONLY": "1", "SKIP_SCRAPE": "1", "WITH_DETAIL": "",
                    "BACKUP_DIR": str(tmp_path / "evening-backups"), "BACKUP_KEEP": "3", "ARGC": "0"}
    assert "record-sync --code 0" in read("uv.txt") and read("uv.txt").rstrip().endswith("finish")
    assert not lock.exists()


def test_signal_only_change_after_unchanged_or_failed_www_still_syncs_once(tmp_path: Path):
    """B1：www 沒帶來三表變化（unchanged）或失敗（failed），但訊號表待同步 → 同一條已驗證備份→同步路徑。"""
    for scrape in ("unchanged", "failed"):
        result, read, lock = _evening(tmp_path / scrape, plan="scrape", scrape=scrape, sync_due="signals")
        assert result.returncode == 0, (scrape, result.stderr)
        sync = dict(line.split("=", 1) for line in read("sync.txt").splitlines())
        assert sync["POSTSEASON_RESULTS_ONLY"] == "1" and sync["SKIP_SCRAPE"] == "1"
        assert sync["BACKUP_DIR"] == str(tmp_path / scrape / "evening-backups"), "仍用晚間獨立已驗證備份"
        assert read("uv.txt").count("--group scrape python -m cpbl.ingest.postseason_evening scrape") == 1, "不重試 www"
        assert "record-sync --code 0" in read("uv.txt")
        assert not lock.exists(), "鎖必須真釋放"


def test_signal_only_sync_failure_still_halts_and_boots_out(tmp_path: Path):
    result, read, lock = _evening(tmp_path, plan="scrape", scrape="failed", sync_due="signals",
                                  sync_exit=67, trigger="launchd")
    assert result.returncode == 69
    assert re.search(r"^bootout gui/\d+/com\.cpbl\.postseason-evening$", read("launchctl.txt"), re.M)
    assert not lock.exists()


def test_pending_sync_syncs_without_scraping(tmp_path: Path):
    result, read, _ = _evening(tmp_path, plan="sync")
    assert result.returncode == 0
    assert " scrape" not in read("uv.txt")
    assert "POSTSEASON_RESULTS_ONLY=1" in read("sync.txt")


def test_busy_lock_exits_75_and_is_never_deleted(tmp_path: Path):
    for name, pid in (("live", os.getpid()), ("dead", 999_999)):
        result, read, lock = _evening(tmp_path / name, plan="scrape", lock_pid=pid)
        assert result.returncode == 75, (name, result.stderr)
        assert lock.is_dir() and (lock / "pid").read_text().strip() == str(pid), "不刪、不搶他人的鎖"
        assert " scrape" not in read("uv.txt").replace("plan", "")


def test_sync_failure_halts_and_boots_out_the_job(tmp_path: Path):
    result, read, lock = _evening(tmp_path, plan="scrape", scrape="changed", sync_exit=67,
                                  trigger="launchd")
    assert result.returncode == 69
    assert "record-sync --code 67" in read("uv.txt")
    assert re.search(r"^bootout gui/\d+/com\.cpbl\.postseason-evening$", read("launchctl.txt"), re.M)
    assert not lock.exists()


def test_reconcile_mismatch_stops_tonight_without_bootout(tmp_path: Path):
    """核定規劃：data-only 對帳不等＝記失敗並停止當晚，不是 halt／bootout。"""
    result, read, lock = _evening(tmp_path, plan="scrape", scrape="changed", sync_exit=68,
                                  trigger="launchd")
    assert result.returncode == 68
    assert "record-sync --code 68" in read("uv.txt")
    assert not read("launchctl.txt")
    assert not lock.exists()


def test_results_only_maps_reconcile_mismatch_to_68(tmp_path: Path):
    """refresh 分支：/api/info 對帳失敗回專屬 68（假 python3 讓 verify 失敗）。"""
    harness_tmp = tmp_path / "h"
    result, _, _ = _run_results_only(harness_tmp, STUB_VERIFY_FAIL="1")
    assert result.returncode == 68, result.stderr
    assert "對帳不等" in result.stderr


def test_manual_run_never_calls_launchctl(tmp_path: Path):
    result, read, _ = _evening(tmp_path, plan="scrape", scrape="changed", sync_exit=67)
    assert result.returncode == 69
    assert not read("launchctl.txt")


def test_plist_template_is_interval_driven_and_points_at_the_wrapper():
    import plistlib

    path = ROOT / "ops" / "launchd" / "com.cpbl.postseason-evening.plist"
    data = plistlib.loads(path.read_bytes())
    assert data["Label"] == "com.cpbl.postseason-evening"
    assert data["StartInterval"] == 300
    assert "StartCalendarInterval" not in data, "沒有鐘點截止，也不是固定時段"
    assert data["ProgramArguments"][0] == "/bin/bash"
    assert data["ProgramArguments"][1].endswith("scripts/postseason-evening.sh")
    assert data["EnvironmentVariables"]["REFRESH_TRIGGER"] == "launchd"
    assert data["RunAtLoad"] is False
    # 不得放在 scripts/：排程登記表（schedule_watch）尚不支援 StartInterval，
    # 放進去會讓 REGISTRY_INCOMPLETE／INVALID 擋下其他 job 的判定（見交付說明）。
    assert not list((ROOT / "scripts").glob("com.cpbl.postseason-evening*.plist"))


def test_evening_wrapper_has_no_clock_cutoff_literals():
    text = EVENING.read_text(encoding="utf-8") + (
        ROOT / "src" / "cpbl" / "ingest" / "postseason_evening.py").read_text(encoding="utf-8")
    for literal in ("23:30", "22:50", "23:55", "time(23", "time(22"):
        assert literal not in text, literal
