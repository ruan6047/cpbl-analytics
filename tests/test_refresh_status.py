"""排程歷史寫入器 ＋ 週跑 wrapper 的行為守衛（OPS-SCHEDULE-FAILURE-BLIND1／#132）。

`scripts/scrape-daily.sh` 一個位元都沒改（不在本卡 resource-claims 內）。歷史改由
`refresh_status.py` 的 `start`／`finish` 自動 append，故 `tests/test_scrape_daily.py`
的 17 個既有 case 一行不改而全綠，就是每日鏈行為零變更的證明。
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
STATUS_HELPER = ROOT / "scripts" / "refresh_status.py"
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
