"""#358 WP2'：每日鏈的外部心跳 ping 掛在 `refresh_status.py` 的 start／finish。

為什麼掛這裡而不是 `scrape-daily.sh`（規劃 2 §2、§4.1）：鏈檔是共同主 PM 點名的共享檔，
`refresh_status.py` 只被它的 start／finish 呼叫，掛在這裡就不必改鏈檔。

每個 case 都用**真實子行程**跑系統 Python（launchd 用的那支），並對本機 127.0.0.1 上的
假服務送 ping——⛔ 不觸外網、不呼叫任何告警服務。驗收 6（6429229525）的四類 fail-open
（逾時、斷網、服務錯誤、金鑰缺席）各一個 case，**同時**斷言 rc、狀態檔與歷史列不變。
"""

from __future__ import annotations

import http.server
import json
import shutil
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
STATUS_HELPER = ROOT / "scripts" / "refresh_status.py"
PING_MODULE = ROOT / "scripts" / "alert_ping.py"
SYSTEM_PYTHON = "/usr/bin/python3" if Path("/usr/bin/python3").exists() else sys.executable
FAKE_KEY = "pk-synthetic-daily-0000"
STARTED = "2026-10-22T10:14:35+0800"


class _Server:
    """127.0.0.1 上的假 healthchecks：記錄路徑，依 mode 回 200／500 或故意不回應。"""

    def __init__(self, mode: str = "ok") -> None:
        self.mode = mode
        self.paths: list[str] = []
        outer = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def _serve(self) -> None:
                outer.paths.append(self.path)
                length = int(self.headers.get("Content-Length") or 0)
                if length:
                    self.rfile.read(length)
                if outer.mode == "hang":
                    time.sleep(2.0)
                    return
                code = 500 if outer.mode == "error" else 200
                self.send_response(code)
                self.send_header("Content-Length", "2")
                self.end_headers()
                self.wfile.write(b"OK")

            do_GET = do_POST = _serve

            def log_message(self, *args) -> None:  # noqa: ANN002
                return None

        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.httpd.daemon_threads = True
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def close(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()


@pytest.fixture
def server():
    created: list[_Server] = []

    def make(mode: str = "ok") -> _Server:
        srv = _Server(mode)
        created.append(srv)
        return srv

    yield make
    for srv in created:
        srv.close()


def _closed_port_base() -> str:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()  # 關掉之後這個埠沒人聽＝connection refused
    return f"http://127.0.0.1:{port}"


def _repo(tmp_path: Path, *, base: str | None, key: str | None = FAKE_KEY,
          timeout: str = "0.5", with_module: bool = True) -> Path:
    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    shutil.copy2(STATUS_HELPER, repo / "scripts" / "refresh_status.py")
    if with_module:
        shutil.copy2(PING_MODULE, repo / "scripts" / "alert_ping.py")
    lines = ["DATABASE_URL=postgresql://cpbl:cpbl@localhost:5433/cpbl"]
    if key is not None:
        lines.append(f"CPBL_HC_PING_KEY={key}")
    if base is not None:
        lines.append(f"CPBL_HC_PING_BASE={base}")
    lines.append(f"CPBL_HC_TIMEOUT_SECONDS={timeout}")
    (repo / ".env").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return repo


def _common(trigger: str = "launchd") -> list[str]:
    return ["--status", "logs/last-status.json",
            "--scheduled-status", "logs/last-launchd-status.json",
            "--trigger", trigger, "--log", "logs/refresh-x.log",
            "--started-at", STARTED, "--sync-enabled", "1"]


def _run(repo: Path, *args: str, extra_env: dict | None = None) -> subprocess.CompletedProcess:
    env = {"PATH": "/usr/bin:/bin", "HOME": str(repo)}
    env.update(extra_env or {})
    return subprocess.run([SYSTEM_PYTHON, str(repo / "scripts" / "refresh_status.py"), *args],
                          cwd=repo, env=env, text=True, capture_output=True, check=False, timeout=60)


def _start(repo: Path, trigger: str = "launchd", **kw) -> subprocess.CompletedProcess:
    return _run(repo, "start", *_common(trigger), **kw)


def _finish(repo: Path, code: int = 0, trigger: str = "launchd", *more: str,
            **kw) -> subprocess.CompletedProcess:
    return _run(repo, "finish", *_common(trigger), "--finished-at", "2026-10-22T12:16:00+0800",
                "--scrape-code", str(code), "--sync-attempted", "0", *more, **kw)


def _history(repo: Path) -> list[dict]:
    path = repo / "logs" / "schedule-history" / "com.cpbl.scrape-daily.jsonl"
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x]


def _status(repo: Path) -> dict:
    return json.loads((repo / "logs" / "last-launchd-status.json").read_text(encoding="utf-8"))


# ------------------------------------------------------------------ 正常路徑

def test_launchd_daily_sends_start_then_exit_code_with_same_rid(tmp_path: Path, server) -> None:
    srv = server()
    repo = _repo(tmp_path, base=srv.base)
    assert _start(repo).returncode == 0
    assert _finish(repo, 0).returncode == 0
    assert len(srv.paths) == 2
    start, end = srv.paths
    assert start.startswith(f"/{FAKE_KEY}/daily/start?rid=")
    assert end.startswith(f"/{FAKE_KEY}/daily/0?rid=")
    assert start.split("rid=")[1] == end.split("rid=")[1]


def test_failed_finish_sends_the_failing_exit_code(tmp_path: Path, server) -> None:
    srv = server()
    repo = _repo(tmp_path, base=srv.base)
    assert _finish(repo, 127).returncode == 0
    assert srv.paths[0].startswith(f"/{FAKE_KEY}/daily/127?rid=")
    assert _status(repo)["exit_code"] == 127


def test_skip_day_counts_as_success(tmp_path: Path, server) -> None:
    """#364 甲型略過日照樣寫 succeeded，所以 daily check 全年可用（規劃 2 §2）。"""
    srv = server()
    repo = _repo(tmp_path, base=srv.base)
    assert _finish(repo, 0, "launchd", "--day-type", "skip", "--skipped", "1",
                   "--skip-reason", "無賽日").returncode == 0
    assert srv.paths[0].startswith(f"/{FAKE_KEY}/daily/0?rid=")


def test_manual_trigger_sends_nothing(tmp_path: Path, server) -> None:
    srv = server()
    repo = _repo(tmp_path, base=srv.base)
    assert _start(repo, "manual").returncode == 0
    assert _finish(repo, 0, "manual").returncode == 0
    assert srv.paths == []


def test_other_history_label_sends_nothing(tmp_path: Path, server) -> None:
    srv = server()
    repo = _repo(tmp_path, base=srv.base)
    result = _run(repo, "start", *_common(), "--history-label", "com.cpbl.weekly-box-revisions")
    assert result.returncode == 0
    assert srv.paths == []


def test_slug_override_routes_to_test_check(tmp_path: Path, server) -> None:
    """故障注入（規劃 2 §7）：以環境改道到 TEST check，正式 daily 不受影響。"""
    srv = server()
    repo = _repo(tmp_path, base=srv.base)
    assert _start(repo, extra_env={"CPBL_ALERT_SLUG_OVERRIDE": "test"}).returncode == 0
    assert srv.paths[0].startswith(f"/{FAKE_KEY}/test/start?rid=")


# ------------------------------------------------- 驗收 6：fail-open 四類

def _assert_chain_unaffected(repo: Path, start: subprocess.CompletedProcess,
                             finish: subprocess.CompletedProcess) -> None:
    assert start.returncode == 0 and finish.returncode == 0
    status = _status(repo)
    assert status["state"] == "failed" and status["exit_code"] == 9
    assert status["failed_phase"] == "scrape"
    assert json.loads((repo / "logs" / "last-status.json").read_text(encoding="utf-8")) == status
    assert [r["state"] for r in _history(repo)] == ["running", "failed"]
    assert FAKE_KEY not in start.stderr + finish.stderr + start.stdout + finish.stdout


def test_fail_open_on_timeout(tmp_path: Path, server) -> None:
    srv = server("hang")
    repo = _repo(tmp_path, base=srv.base, timeout="0.3")
    start, finish = _start(repo), _finish(repo, 9)
    _assert_chain_unaffected(repo, start, finish)
    assert "failed" in finish.stderr


def test_fail_open_on_connection_refused(tmp_path: Path) -> None:
    repo = _repo(tmp_path, base=_closed_port_base())
    start, finish = _start(repo), _finish(repo, 9)
    _assert_chain_unaffected(repo, start, finish)
    assert "failed" in start.stderr


def test_fail_open_on_http_error(tmp_path: Path, server) -> None:
    srv = server("error")
    repo = _repo(tmp_path, base=srv.base)
    start, finish = _start(repo), _finish(repo, 9)
    _assert_chain_unaffected(repo, start, finish)
    assert len(srv.paths) == 6  # start、finish 各重試到上限 3 次
    assert "http=500" in finish.stderr


def test_fail_open_on_missing_key(tmp_path: Path, server) -> None:
    srv = server()
    repo = _repo(tmp_path, base=srv.base, key=None)
    start, finish = _start(repo), _finish(repo, 9)
    _assert_chain_unaffected(repo, start, finish)
    assert srv.paths == []
    assert "未設定" in start.stderr


def test_fail_open_when_ping_module_is_missing(tmp_path: Path, server) -> None:
    srv = server()
    repo = _repo(tmp_path, base=srv.base, with_module=False)
    start, finish = _start(repo), _finish(repo, 9)
    _assert_chain_unaffected(repo, start, finish)
    assert "WARN" in start.stderr and srv.paths == []


# ------------------------------------------------- 登記表 alert 段與實作一致

def test_registry_daily_alert_matches_cadence_and_module() -> None:
    """門檻 11:00＝cron 10:10＋grace 50（裁定 6348735853 第 4 項）；check 名與模組常數一致。"""
    import importlib.util

    spec = importlib.util.spec_from_file_location("_ap_for_registry", PING_MODULE)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    registry = json.loads((ROOT / "scripts" / "schedule-registry.json").read_text(encoding="utf-8"))
    job = next(j for j in registry["jobs"] if j["label"] == "com.cpbl.scrape-daily")
    alert, cadence = job["alert"], job["cadence"]
    assert alert["check"] == module.CHECK_DAILY
    assert alert["schedule"] == f"{cadence['minute']} {cadence['hour']} * * *"
    minutes = cadence["hour"] * 60 + cadence["minute"] + alert["grace_minutes"]
    assert alert["deadline"] == f"{minutes // 60:02d}:{minutes % 60:02d}" == "11:00"
