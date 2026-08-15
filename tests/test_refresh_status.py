"""排程歷史寫入器 ＋ 週跑 wrapper 的行為守衛（OPS-SCHEDULE-FAILURE-BLIND1／#132）。

**為什麼週跑 wrapper 的測試放在這一檔**：它整個改動都是「往 `refresh_status.py` 擁有的
狀態／歷史面寫出可分辨的訊號」，而本卡的 resource-claims 只宣告 `tests/test_refresh_status.py`
與 `tests/test_schedule_watch.py` 兩個測試檔。放這裡是刻意的歸位，不是誤植。

**每個 case 同時斷言 exit code 與狀態檔內容**。Discovery §7 已指出：`lock 忙碌 → 寫
skipped 但 exit 0` 那條路徑之所以活到今天，正是因為既有覆蓋只斷言其中一項——狀態檔的
`result` 欄看得出 `skipped`，而 launchd 記到的 `LastExitStatus` 是 0，兩者完全不可分辨，
**而 launchd 正是 2026-08-10 那次失敗唯一被人看到的那個面**。

`scripts/scrape-daily.sh` 一個位元都沒改（不在本卡 resource-claims 內）。歷史改由
`refresh_status.py` 的 `start`／`finish` 自動 append，故 `tests/test_scrape_daily.py`
的 17 個既有 case 一行不改而全綠，就是每日鏈行為零變更的證明。
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
STATUS_HELPER = ROOT / "scripts" / "refresh_status.py"
WEEKLY_BOX = ROOT / "scripts" / "weekly-box-revisions.sh"
REGISTRY = ROOT / "scripts" / "schedule-registry.json"
SYSTEM_PYTHON = "/usr/bin/python3" if Path("/usr/bin/python3").exists() else sys.executable


def _executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def _run_helper(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [SYSTEM_PYTHON, str(STATUS_HELPER), *args],
        cwd=cwd, text=True, capture_output=True, check=False,
    )


def _history(repo: Path, label: str) -> list[dict]:
    path = repo / "logs" / "schedule-history" / f"{label}.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


# --------------------------------------------------------- refresh_status.py 歷史

def test_start_then_finish_leaves_running_then_terminal(tmp_path: Path) -> None:
    """至少兩列：起跑一列 running、結束一列終態。

    這兩列是「開跑後死掉」與「從未開跑」可分辨的**唯一**依據——現行設計只記錄結果、
    不記錄嘗試，於是缺席與崩潰在觀測上長得一模一樣。
    """
    common = [
        "--status", "logs/last-status.json",
        "--scheduled-status", "logs/last-launchd-status.json",
        "--trigger", "launchd", "--log", "logs/refresh-x.log",
        "--started-at", "2026-08-10T10:10:00+0800", "--sync-enabled", "1",
    ]
    assert _run_helper(tmp_path, "start", *common).returncode == 0
    records = _history(tmp_path, "com.cpbl.scrape-daily")
    assert [r["state"] for r in records] == ["running"]
    assert records[0]["finished_at"] is None

    assert _run_helper(
        tmp_path, "finish", *common,
        "--finished-at", "2026-08-10T11:50:37+0800",
        "--scrape-code", "1", "--sync-attempted", "0",
    ).returncode == 0
    records = _history(tmp_path, "com.cpbl.scrape-daily")
    assert [r["state"] for r in records] == ["running", "failed"]
    assert records[1]["exit_code"] == 1
    assert records[1]["failed_phase"] == "scrape"
    assert records[1]["trigger"] == "launchd"


def test_manual_runs_are_recorded_with_their_own_trigger(tmp_path: Path) -> None:
    """手動補跑必須留下 `trigger=manual`——偵測器只採計 launchd，否則手動救火會把
    壞掉的排程蓋成健康。"""
    _run_helper(
        tmp_path, "start",
        "--status", "logs/last-status.json",
        "--scheduled-status", "logs/last-launchd-status.json",
        "--trigger", "manual", "--log", "logs/x.log",
        "--started-at", "2026-08-10T19:00:00+0800", "--sync-enabled", "0",
    )
    assert [r["trigger"] for r in _history(tmp_path, "com.cpbl.scrape-daily")] == ["manual"]


def test_history_compacts_only_past_the_threshold(tmp_path: Path) -> None:
    """正常路徑是 O(1) append，超過門檻才付重寫成本，且只保留最後 HISTORY_KEEP 列。"""
    sys.path.insert(0, str(ROOT / "scripts"))
    try:
        import importlib.util

        spec = importlib.util.spec_from_file_location("_rs", STATUS_HELPER)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)

    history_dir = tmp_path / "hist"
    for index in range(module.HISTORY_COMPACT_AT):
        module.append_history(history_dir, "job", {"n": index, "started_at": "2026-08-01T00:00:00+0800"})
    path = module.history_path(history_dir, "job")
    assert len(path.read_text(encoding="utf-8").splitlines()) == module.HISTORY_COMPACT_AT

    module.append_history(history_dir, "job", {"n": -1, "started_at": "2026-08-01T00:00:00+0800"})
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == module.HISTORY_KEEP
    assert json.loads(lines[-1])["n"] == -1          # 最新的一列留下
    assert json.loads(lines[0])["n"] == module.HISTORY_COMPACT_AT + 1 - module.HISTORY_KEEP


def test_history_write_failure_warns_but_never_breaks_the_chain(tmp_path: Path) -> None:
    """觀測器不得把被觀測的鏈弄掛。缺失的代價由讀取端承擔（判 MISSING，fail closed）。"""
    blocked = tmp_path / "blocked"
    blocked.write_text("我是檔案不是目錄", encoding="utf-8")   # mkdir 必失敗
    result = _run_helper(
        tmp_path, "start",
        "--status", "logs/last-status.json",
        "--scheduled-status", "logs/last-launchd-status.json",
        "--trigger", "launchd", "--log", "logs/x.log",
        "--started-at", "2026-08-10T10:10:00+0800", "--sync-enabled", "1",
        "--history-dir", str(blocked / "sub"),
    )
    assert result.returncode == 0
    assert "WARN" in result.stderr
    assert (tmp_path / "logs" / "last-status.json").exists()   # 狀態檔照常寫


def test_default_history_label_matches_registry(tmp_path: Path) -> None:
    """`scrape-daily.sh` 不帶 `--history-label`（本卡不改那支），故預設值是隱性耦合。

    這個測試把它變成機器擋得住的東西：預設 label 一旦與登記表漂移，每日鏈的歷史就會
    寫到偵測器不看的檔名去，症狀是「排程明明跑了卻天天報 MISSING」。
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location("_rs", STATUS_HELPER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    daily = next(j for j in registry["jobs"] if j["label"] == module.DEFAULT_HISTORY_LABEL)
    assert daily["history_path"] == str(
        module.history_path(module.DEFAULT_HISTORY_DIR, module.DEFAULT_HISTORY_LABEL))


# ------------------------------------------------------- weekly-box-revisions.sh

def _run_weekly(
    tmp_path: Path,
    *,
    uv_exit: int = 0,
    docker_running: bool = True,
    lock_pid: int | None = None,
    lock_without_pid: bool = False,
    argv: list[str] | None = None,
    trigger_env: dict[str, str] | None = None,
) -> tuple[subprocess.CompletedProcess, dict, list[dict]]:
    repo = tmp_path / "repo"
    scripts = repo / "scripts"
    fake_bin = tmp_path / "bin"
    scripts.mkdir(parents=True, exist_ok=True)
    fake_bin.mkdir(exist_ok=True)
    shutil.copy2(WEEKLY_BOX, scripts / "weekly-box-revisions.sh")
    shutil.copy2(STATUS_HELPER, scripts / "refresh_status.py")

    docker_output = "cpbl-analytics-db-1\n" if docker_running else ""
    _executable(fake_bin / "docker", f"#!/bin/sh\nprintf '{docker_output}'\n")
    _executable(fake_bin / "uv", f"#!/bin/sh\nexit {uv_exit}\n")

    lock_dir = tmp_path / "refresh.lock"
    if lock_pid is not None or lock_without_pid:
        lock_dir.mkdir()
        if lock_pid is not None:
            (lock_dir / "pid").write_text(str(lock_pid), encoding="utf-8")

    env = os.environ.copy()
    env.update({"PATH": f"{fake_bin}:/usr/bin:/bin", "REFRESH_LOCK_DIR": str(lock_dir)})
    env.pop("XPC_SERVICE_NAME", None)
    env.update(trigger_env or {})
    result = subprocess.run(
        ["/bin/bash", str(scripts / "weekly-box-revisions.sh"), *(argv or [])],
        cwd=repo, env=env, text=True, capture_output=True, check=False,
    )
    status_path = repo / "logs" / "last-weekly-box-revisions.json"
    status = json.loads(status_path.read_text(encoding="utf-8")) if status_path.exists() else {}
    return result, status, _history(repo, "com.cpbl.weekly-box-revisions")


def test_lock_busy_is_no_longer_indistinguishable_from_success(tmp_path: Path) -> None:
    """本卡的核心回歸：舊版寫 `skipped` 卻 `exit 0`。

    ⚠️ **兩項一起斷言**才有意義。舊版在「狀態檔 result 欄」上是通得過的
    （`"skipped" != "ok"`），只有 exit code 那一面把「該跑沒跑」偽裝成成功。
    """
    result, status, history = _run_weekly(tmp_path, lock_pid=os.getpid())

    assert result.returncode == 75            # ← 舊版是 0，launchd 那面完全不可分辨
    assert status["result"] == "skipped"
    assert status["exit_code"] == 75          # ← 舊版是 0
    assert [r["state"] for r in history] == ["skipped"]
    assert history[0]["exit_code"] == 75


def test_lock_without_pid_is_not_reclaimed(tmp_path: Path) -> None:
    """另一個程序剛 mkdir、還沒寫 pid 的窗口——不可誤判成 stale 後刪掉別人的鎖。

    這條守則從 `scrape-daily.sh:48-52` 逐字沿用，是取鎖邏輯裡唯一「保守優於積極」的
    地方；連同 stale 回收一起搬過來時最容易被順手簡化掉。
    """
    result, status, _ = _run_weekly(tmp_path, lock_without_pid=True)

    assert result.returncode == 75
    assert status["result"] == "skipped"
    assert (tmp_path / "refresh.lock").exists()      # 鎖沒被搶走


def test_stale_lock_is_reclaimed_instead_of_skipping_forever(tmp_path: Path) -> None:
    """沒有回收，鎖目錄一旦被留下就是**永久跳過、永久沒訊號**——比失敗更難發現。"""
    dead_pid = 999_999                                # 不存在的 pid
    result, status, history = _run_weekly(tmp_path, lock_pid=dead_pid)

    assert result.returncode == 0
    assert status["result"] == "ok"
    assert "回收 stale lock" in result.stdout
    assert [r["state"] for r in history] == ["running", "succeeded"]


def test_success_records_running_then_succeeded(tmp_path: Path) -> None:
    result, status, history = _run_weekly(tmp_path)

    assert result.returncode == 0
    assert status["result"] == "ok" and status["exit_code"] == 0
    assert [r["state"] for r in history] == ["running", "succeeded"]


def test_scrape_failure_propagates_and_is_recorded(tmp_path: Path) -> None:
    result, status, history = _run_weekly(tmp_path, uv_exit=9)

    assert result.returncode == 9
    assert status["result"] == "failed" and status["exit_code"] == 9
    assert [r["state"] for r in history] == ["running", "failed"]
    assert history[-1]["exit_code"] == 9


def test_missing_local_database_is_a_failure_not_a_skip(tmp_path: Path) -> None:
    result, status, history = _run_weekly(tmp_path, docker_running=False)

    assert result.returncode == 127
    assert status["result"] == "failed"
    assert [r["state"] for r in history] == ["running", "failed"]


def test_launchd_trigger_is_detected_without_touching_the_plist(tmp_path: Path) -> None:
    """本檔的 plist 不在 #132 射程內（一個位元不改），故執行身分改用 launchd 自己
    設的 `XPC_SERVICE_NAME` 判定。"""
    _, _, history = _run_weekly(
        tmp_path / "as-launchd",
        trigger_env={"XPC_SERVICE_NAME": "com.cpbl.weekly-box-revisions"})
    assert {r["trigger"] for r in history} == {"launchd"}

    _, _, history = _run_weekly(tmp_path / "as-manual")
    assert {r["trigger"] for r in history} == {"manual"}


@pytest.mark.parametrize("flag", ["--help", "-h"])
def test_help_prints_usage_and_touches_nothing(tmp_path: Path, flag: str) -> None:
    """argv 守衛必須在任何副作用之前。本檔會開真實爬蟲並寫 DB——`--help` 被當成位置
    參數吞掉就是 DEV-CLI-HELP-GUARD1 那次事故（查核者想看用法，結果對官網開爬）。"""
    result, status, history = _run_weekly(tmp_path, argv=[flag])

    assert result.returncode == 0
    assert "在做什麼" in result.stdout and "會寫什麼" in result.stdout
    assert "怎麼呼叫" in result.stdout
    assert status == {} and history == []
    assert not (tmp_path / "repo" / "logs").exists()      # 連 logs/ 都沒建


def test_unknown_argument_exits_64_without_running(tmp_path: Path) -> None:
    result, status, history = _run_weekly(tmp_path, argv=["zzz-not-a-real-arg"])

    assert result.returncode == 64
    assert status == {} and history == []
    assert not (tmp_path / "repo" / "logs").exists()
