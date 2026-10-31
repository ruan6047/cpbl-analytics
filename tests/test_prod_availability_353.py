"""#353 WP4：正式站可用性哨兵／探針（``scripts/prod_availability.py``）。零網路：curl 與時鐘都是假的。"""

from __future__ import annotations

import importlib.util
import os
import re
import signal
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
_spec = importlib.util.spec_from_file_location("prod_availability", ROOT / "scripts" / "prod_availability.py")
pa = importlib.util.module_from_spec(_spec)
sys.modules["prod_availability"] = pa
_spec.loader.exec_module(pa)

PING = "https://hc-ping.example.invalid/0000-secret-uuid"


def S(label: str, code: str, seconds: float, at: float = 1_000_000.0) -> pa.Sample:
    return pa.Sample(at, label, code, seconds)


# --------------------------------------------------------------------------- 判定


def test_all_good_is_ok() -> None:
    v = pa.judge([S("info", "200", 0.2), S("watch", "200", 4.999)])
    assert v["ok"] is True and v["samples"] == 2 and v["slowest_seconds"] == 4.999


@pytest.mark.parametrize("bad", [S("info", "000", 10.0), S("watch", "200", 5.0), S("recap-wp", "200", 7.2)])
def test_any_000_or_ge5s_fails(bad) -> None:
    assert pa.judge([S("info", "200", 0.1), bad])["ok"] is False


def test_zero_samples_fails_closed() -> None:
    v = pa.judge([])
    assert v["ok"] is False and v["samples"] == 0


def test_non2xx_under_5s_is_not_a_failure_but_is_reported() -> None:
    """規劃 §6：WP2 逾時後回的 5xx 不算驗收失敗，但筆數必須列出。"""
    v = pa.judge([S("recap-wp", "500", 2.1), S("info", "200", 0.1)])
    assert v["ok"] is True and v["non2xx"] == 1


def test_probe_judges_only_api_info() -> None:
    v = pa.judge([S("health", "000", 10.0), S("info", "200", 0.3)], labels={"info"})
    assert v["ok"] is True and v["samples"] == 1


def test_summary_has_no_url_or_secret() -> None:
    text = pa.summary_text("sentinel", pa.judge([S("info", "000", 10.0)]))
    assert "FAIL" in text and "http000=1" in text
    for leak in ("http://", "https://", "ruan-ruan", "hc-ping", "@"):
        assert leak not in text


# --------------------------------------------------------------------------- 哨兵迴圈


class FakeClock:
    def __init__(self) -> None:
        self.t = 0.0

    def now(self) -> float:
        return self.t

    def sleep(self, dt: float) -> None:
        self.t += dt


def _sampler(clock: FakeClock, calls: list):
    def sample(base, label, path):
        calls.append((clock.t, label, path))
        return pa.Sample(clock.t, label, "200", 0.1)
    return sample


def test_sentinel_hits_d1_endpoints_every_15s_and_runs_tail_after_stop(tmp_path: Path) -> None:
    clock, calls = FakeClock(), []
    stop = tmp_path / "stop"
    real_sleep = clock.sleep

    def sleep(dt):
        real_sleep(dt)
        if clock.t >= 60 and not stop.exists():
            stop.touch()   # 第 4 步在 t=60 結束

    samples = pa.run_sentinel(base_url="http://x", stop_file=stop, sample=_sampler(clock, calls),
                              now=clock.now, sleep=sleep)
    labels = {label for _, label, _ in calls}
    assert labels == {"info", "watch", "recap-wp"}
    ticks = sorted({round(t) for t, _, _ in calls})
    assert all(b - a >= 15 for a, b in zip(ticks, ticks[1:], strict=False)), ticks
    assert ticks[-1] >= 60 + 120 - 15, "停止訊號後仍須量滿 120 秒"
    assert clock.t >= 60 + 120 and clock.t < 60 + 120 + 16
    assert len(samples) == len(calls)


def test_interval_cannot_be_below_15s(tmp_path: Path) -> None:
    clock, calls = FakeClock(), []
    stop = tmp_path / "stop"
    stop.touch()
    pa.run_sentinel(base_url="http://x", stop_file=stop, interval=1, tail=40,
                    sample=_sampler(clock, calls), now=clock.now, sleep=clock.sleep)
    ticks = sorted({t for t, _, _ in calls})
    assert all(b - a >= 15 for a, b in zip(ticks, ticks[1:], strict=False)), ticks


def test_sentinel_stops_when_orphaned(tmp_path: Path) -> None:
    clock, calls = FakeClock(), []
    pa.run_sentinel(base_url="http://x", stop_file=tmp_path / "never", tail=0,
                    sample=_sampler(clock, calls), now=clock.now, sleep=clock.sleep,
                    parent_alive=lambda: clock.t < 30)
    assert clock.t < 60


def test_probe_sequence_first_then_five_info_every_10s() -> None:
    clock, calls = FakeClock(), []
    pa.run_probe(base_url="http://x", sample=_sampler(clock, calls), sleep=clock.sleep)
    assert [label for _, label, _ in calls] == ["health", "healthz", "info"] + ["info"] * 5
    assert [t for t, *_ in calls][3:] == [10.0, 20.0, 30.0, 40.0, 50.0]


# --------------------------------------------------------------------------- 通道


def test_ping_url_prefers_env_then_env_file(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(f"OTHER=1\n{pa.PING_ENV}=\"{PING}\"\n", encoding="utf-8")
    assert pa.ping_url(str(env_file), environ={}) == PING
    assert pa.ping_url(str(env_file), environ={pa.PING_ENV: "https://other.invalid/x"}) == "https://other.invalid/x"
    assert pa.ping_url(str(tmp_path / "missing"), environ={}) is None


class _Resp:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_send_fail_goes_to_fail_endpoint_and_log_line_has_no_url() -> None:
    seen = []

    def opener(req, timeout):
        seen.append((req.full_url, req.data.decode(), timeout))
        return _Resp()

    line = pa.send(PING, False, "summary", opener=opener)
    assert seen == [(PING + "/fail", "summary", 10)]
    assert PING not in line and "secret" not in line
    pa.send(PING, True, "ok", opener=opener)
    assert seen[-1][0] == PING


def test_send_without_channel_or_on_error_never_raises() -> None:
    assert "未設定告警通道" in pa.send(None, False, "x")

    def boom(req, timeout):
        raise OSError("network down " + PING)

    line = pa.send(PING, False, "x", opener=boom)
    assert "失敗" in line and PING not in line


def test_main_always_exits_zero_even_if_the_detector_crashes(monkeypatch, tmp_path: Path, capsys) -> None:
    sent = []
    monkeypatch.setattr(pa, "run_probe", lambda **kw: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(pa, "send", lambda url, ok, body, **kw: sent.append((ok, body)) or "logged")
    assert pa.main(["probe", "--base-url", "http://127.0.0.1:1"]) == 0
    assert sent and sent[0][0] is False, "偵測器自身失敗也要告警（fail-closed）"


def test_main_sentinel_writes_tsv_and_alerts_on_failure(monkeypatch, tmp_path: Path) -> None:
    sent = []
    monkeypatch.setattr(pa, "run_sentinel", lambda **kw: [S("info", "000", 10.0)])
    monkeypatch.setattr(pa, "send", lambda url, ok, body, **kw: sent.append((ok, body)) or "logged")
    out = tmp_path / "logs" / "s.tsv"
    assert pa.main(["sentinel", "--stop-file", str(tmp_path / "stop"), "--out", str(out)]) == 0
    assert out.read_text().splitlines()[1].split("\t")[2:4] == ["info", "000"]
    assert sent == [(False, sent[0][1])] and "FAIL" in sent[0][1]


def test_recap_wp_endpoint_is_a_fixed_completed_game_path() -> None:
    paths = dict(pa.SENTINEL_ENDPOINTS)
    assert paths["info"] == "/api/info" and paths["watch"].startswith("/api/v1/playoffs/watch?") and "series=" in paths["watch"]
    assert paths["recap-wp"].startswith("/api/v1/games/") and "season=2026" in paths["recap-wp"]


# --------------------------------------------------------------------------- 審核 1 回歸




def _slow_sampler(clock: FakeClock, calls: list, seconds: float = 10.0):
    """每筆取樣耗時 ``seconds``（curl -m 10 卡滿）：一輪三筆就超過 15 秒間隔。"""
    def sample(base, label, path):
        clock.t += seconds
        calls.append((clock.t, label))
        return pa.Sample(clock.t, label, "000", seconds)
    return sample


@pytest.mark.parametrize("trigger", ["stop_file", "parent_gone", "max_seconds"])
def test_slow_requests_cannot_keep_the_sentinel_from_stopping(tmp_path: Path, trigger) -> None:
    """審核 1 第 1 項：三個請求各 10 秒時，停止條件仍須在每筆取樣後生效。"""
    clock, calls = FakeClock(), []
    stop = tmp_path / "stop"
    if trigger == "stop_file":
        stop.touch()
    pa.run_sentinel(base_url="http://x", stop_file=stop, tail=0,
                    max_seconds=1 if trigger == "max_seconds" else pa.SENTINEL_MAX_SECONDS,
                    sample=_slow_sampler(clock, calls), now=clock.now, sleep=clock.sleep,
                    parent_alive=(lambda: False) if trigger == "parent_gone" else (lambda: True))
    assert len(calls) == 1 and clock.t == 10.0, calls


def test_slow_requests_stop_within_tail_plus_one_round(tmp_path: Path) -> None:
    clock, calls = FakeClock(), []
    stop = tmp_path / "stop"
    stop.touch()
    pa.run_sentinel(base_url="http://x", stop_file=stop, tail=120, sample=_slow_sampler(clock, calls),
                    now=clock.now, sleep=clock.sleep)
    assert 120 <= clock.t <= 120 + 3 * (pa.CURL_MAX_TIME + 5)


def test_shell_wait_bound_covers_tail_plus_one_round() -> None:
    source = (ROOT / "scripts" / "refresh-cpbl-prod.sh").read_text(encoding="utf-8")
    bound = int(source.split("SENTINEL_WAIT_MAX=", 1)[1].split("\n", 1)[0])
    assert bound >= pa.SENTINEL_TAIL_SECONDS + 3 * (pa.CURL_MAX_TIME + 5)
    body = source.split("stop_availability_sentinel() {", 1)[1].split("\n}\n", 1)[0]
    assert 'kill "$SENTINEL_PID"' in body, "逾時須結束哨兵，不得無限等待"


def test_sigterm_turns_into_a_detector_failure_alert(monkeypatch, tmp_path: Path) -> None:
    import signal

    sent = []

    def fake_sentinel(**kw):
        signal.raise_signal(signal.SIGTERM)
        return []

    monkeypatch.setattr(pa, "run_sentinel", fake_sentinel)
    monkeypatch.setattr(pa, "send", lambda url, ok, body, **kw: sent.append((ok, body)) or "logged")
    previous = signal.getsignal(signal.SIGTERM)
    try:
        assert pa.main(["sentinel", "--stop-file", str(tmp_path / "s"), "--out", str(tmp_path / "o.tsv")]) == 0
    finally:
        signal.signal(signal.SIGTERM, previous)
    assert sent and sent[0][0] is False and "detector error" in sent[0][1]


def test_4xx_is_a_failure_but_5xx_under_5s_is_only_reported() -> None:
    assert pa.judge([S("watch", "422", 0.01)])["ok"] is False
    v = pa.judge([S("recap-wp", "503", 0.2)])
    assert v["ok"] is True and v["non2xx"] == 1 and v["n4xx"] == 0


def test_every_probe_path_passes_validation_and_reaches_its_reader(monkeypatch) -> None:
    """審核 1 第 2 項：以受審 app 驗每條探測路徑不是 422、且真的呼叫到讀取函式。"""
    from fastapi.testclient import TestClient

    from cpbl.api.main import app
    from cpbl.api.routers import info, recap
    from cpbl.playoffs import watch_reader

    hits: list[str] = []
    monkeypatch.setattr(watch_reader, "playoffs_watch", lambda *a, **k: hits.append("watch") or {})
    monkeypatch.setattr(recap, "_load_game_row", lambda *a: hits.append("recap-wp") or None)
    monkeypatch.setattr(recap, "_load_pa_rows", lambda *a: [])
    monkeypatch.setattr(info, "_compute", lambda: hits.append("info") or info._Snapshot(0.0, True, "running", {}))
    client = TestClient(app)
    for label, path in (*pa.SENTINEL_ENDPOINTS, ("info", "/api/info")):
        hits.clear()
        res = client.get(path)
        assert res.status_code != 422, (label, path, res.text)
        assert hits == [label], (label, path, hits)


# =========================================== #398 規劃 r2：真 prod_availability.py 收到 SIGTERM（T1–T3、T6）
#
# 共同條件：子程序以系統 python3（3.9，launchd 每日鏈實際用的那支）執行**未修改的** scripts/prod_availability.py；
# PATH 最前面放假 curl（Python 寫的，記下自己的 pid 後 sleep，再印 curl -w 格式）；告警收件端是本行程內
# 127.0.0.1 的 http.server。⛔ 不連外、不讀真 .env；每個子程序 start_new_session，結束時整個程序群組收尾。

SYSTEM_PYTHON = "/usr/bin/python3" if Path("/usr/bin/python3").exists() else sys.executable
SCRIPT = ROOT / "scripts" / "prod_availability.py"

_FAKE_CURL = f"""#!{SYSTEM_PYTHON}
import os, sys, time
from pathlib import Path
calls = Path(os.environ["FAKE_CURL_CALLS"])
calls.mkdir(parents=True, exist_ok=True)
(calls / ("%03d-%d" % (len(list(calls.iterdir())), os.getpid()))).write_text(sys.argv[-1])
time.sleep(float(os.environ.get("FAKE_CURL_SLEEP", "0")))
print("200 0.001 0.002 0.003", end="")
"""


class Receiver:
    """假告警收件端：記錄每筆 POST（路徑＋內容）。``hold`` 為真時，第一筆 POST 記下後等 ``release``。"""

    def __init__(self, *, hold: bool = False) -> None:
        self.posts: list[tuple[str, str]] = []
        self.got_post = threading.Event()
        self.release = threading.Event()
        if not hold:
            self.release.set()
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                body = self.rfile.read(int(self.headers.get("Content-Length") or 0)).decode("utf-8")
                outer.posts.append((self.path, body))
                outer.got_post.set()
                outer.release.wait(15)
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"OK")

            def log_message(self, *a):  # 安靜
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/ping-test"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self) -> None:
        self.release.set()
        self.server.shutdown()
        self.server.server_close()

    def fails(self) -> list[str]:
        return [b for p, b in self.posts if p.endswith("/fail")]

    def oks(self) -> list[str]:
        return [b for p, b in self.posts if not p.endswith("/fail")]


@pytest.fixture
def receiver():
    r = Receiver()
    yield r
    r.close()


def _sentinel_env(tmp_path: Path, receiver: Receiver, curl_sleep: float) -> dict[str, str]:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir(exist_ok=True)
    (fake_bin / "curl").write_text(_FAKE_CURL, encoding="utf-8")
    (fake_bin / "curl").chmod(0o755)
    return {
        "PATH": f"{fake_bin}:/usr/bin:/bin",
        "HOME": str(tmp_path),
        "FAKE_CURL_CALLS": str(tmp_path / "curl-calls"),
        "FAKE_CURL_SLEEP": str(curl_sleep),
        "CPBL_AVAILABILITY_PING_URL": receiver.url,
        "DATABASE_URL": "postgresql://nouser:nopw@127.0.0.1:9/none",
    }


def _start(cmd: list[str], env: dict[str, str]) -> subprocess.Popen:
    return subprocess.Popen(cmd, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            stdin=subprocess.DEVNULL, start_new_session=True)


def _finish(proc: subprocess.Popen, timeout: float) -> tuple[int, str, str, float]:
    started = time.monotonic()
    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        out, err = proc.communicate()
        pytest.fail(f"真哨兵收到 SIGTERM 後 {timeout}s 內沒有結束（訊號被吞？）\nstdout={out}\nstderr={err}")
    return proc.returncode, out, err, time.monotonic() - started


def _wait_for(pred, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while not pred():
        if time.monotonic() > deadline:
            pytest.fail("等待前提逾時")
        time.sleep(0.05)


def _curl_calls(tmp_path: Path) -> list[Path]:
    d = tmp_path / "curl-calls"
    return sorted(d.iterdir()) if d.is_dir() else []


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def _sentinel_cmd(tmp_path: Path) -> list[str]:
    # 停止檔刻意不存在：沒有 SIGTERM 時這支會一直量（真哨兵是 6 小時保險絲）。
    return [SYSTEM_PYTHON, str(SCRIPT), "sentinel", "--stop-file", str(tmp_path / "no-stop"),
            "--base-url", "http://127.0.0.1:9", "--out", str(tmp_path / "out.tsv")]


def _assert_single_detector_failure(receiver: Receiver, rc: int, out: str, err: str) -> None:
    assert rc == 0, err
    assert receiver.oks() == [], f"收到 SIGTERM 不得送成功：{receiver.posts}"
    assert len(receiver.fails()) == 1, receiver.posts
    assert "detector error SentinelTerminated" in receiver.fails()[0]
    assert out.count("已送告警（HTTP 200）") == 1, out
    assert receiver.url not in out + err, "log 不得含 ping URL"


def test_t1_sigterm_during_a_curl_sample_alerts_once_and_leaves_no_orphan_curl(tmp_path: Path, receiver) -> None:
    """F1-R2 的落點：訊號落在 curl_sample() 的 try 裡。修正前會被吞成 000 樣本、量測繼續。"""
    proc = _start(_sentinel_cmd(tmp_path), _sentinel_env(tmp_path, receiver, curl_sleep=8))
    _wait_for(lambda: len(_curl_calls(tmp_path)) >= 1)
    time.sleep(0.3)  # 假 curl 已在 sleep 8 中
    proc.send_signal(signal.SIGTERM)
    rc, out, err, elapsed = _finish(proc, timeout=15)

    assert elapsed < 10, f"收到 SIGTERM 後 {elapsed:.1f}s 才結束"
    _assert_single_detector_failure(receiver, rc, out, err)
    assert len(_curl_calls(tmp_path)) == 1, "收到訊號後不得再啟動下一筆取樣"
    curl_pid = int(_curl_calls(tmp_path)[0].name.split("-")[1])
    assert not _alive(curl_pid), "正在跑的 curl 必須被一起收掉，不得成為孤兒"


def test_t1b_second_sigterm_during_the_alert_does_not_interrupt_it(tmp_path: Path) -> None:
    """處理器第一次觸發就忽略後續 SIGTERM：告警送出途中再來一個訊號，告警照樣送完（每程序一個訊號）。"""
    receiver = Receiver(hold=True)
    try:
        proc = _start(_sentinel_cmd(tmp_path), _sentinel_env(tmp_path, receiver, curl_sleep=8))
        _wait_for(lambda: len(_curl_calls(tmp_path)) >= 1)
        time.sleep(0.3)
        proc.send_signal(signal.SIGTERM)
        assert receiver.got_post.wait(10), "第一個 SIGTERM 後沒有送出告警"
        proc.send_signal(signal.SIGTERM)  # 告警正在送（收件端還沒回應）
        time.sleep(0.5)
        receiver.release.set()
        rc, out, err, _ = _finish(proc, timeout=15)
        _assert_single_detector_failure(receiver, rc, out, err)
    finally:
        receiver.close()


def test_t2_sigterm_while_waiting_between_rounds_alerts_once(tmp_path: Path, receiver) -> None:
    """訊號落在兩輪取樣之間的 time.sleep(0.5) 等待中。"""
    proc = _start(_sentinel_cmd(tmp_path), _sentinel_env(tmp_path, receiver, curl_sleep=0))
    _wait_for(lambda: len(_curl_calls(tmp_path)) >= 3)
    time.sleep(1.5)  # 第一輪三筆已完成，下一輪在 15 秒後：此刻必在等待迴圈裡
    assert len(_curl_calls(tmp_path)) == 3
    proc.send_signal(signal.SIGTERM)
    rc, out, err, elapsed = _finish(proc, timeout=15)

    assert elapsed < 10
    _assert_single_detector_failure(receiver, rc, out, err)
    assert len(_curl_calls(tmp_path)) == 3


_SHORT_TAIL_RUNNER = """
import functools, importlib.util, sys
spec = importlib.util.spec_from_file_location("prod_availability", sys.argv[1])
pa = importlib.util.module_from_spec(spec); sys.modules["prod_availability"] = pa; spec.loader.exec_module(pa)
pa.run_sentinel = functools.partial(pa.run_sentinel, tail=0.2)   # 只縮短收尾量測，判定與送出照原碼
raise SystemExit(pa.main(sys.argv[2:]))
"""


def test_t3_sigterm_while_sending_the_result_is_ignored_single_signal(tmp_path: Path) -> None:
    """送出成功途中收到 SIGTERM：忽略它，只有一筆成功、沒有告警（驗收 3／D4）。"""
    receiver = Receiver(hold=True)
    try:
        (tmp_path / "stop").touch()
        cmd = [SYSTEM_PYTHON, "-c", _SHORT_TAIL_RUNNER, str(SCRIPT), "sentinel",
               "--stop-file", str(tmp_path / "stop"), "--base-url", "http://127.0.0.1:9",
               "--out", str(tmp_path / "out.tsv")]
        proc = _start(cmd, _sentinel_env(tmp_path, receiver, curl_sleep=0))
        assert receiver.got_post.wait(15), "沒有送出判定結果"
        proc.send_signal(signal.SIGTERM)  # 成功 ping 正在送（收件端還沒回應）
        time.sleep(0.5)
        receiver.release.set()
        rc, out, err, _ = _finish(proc, timeout=15)

        assert rc == 0, err
        assert len(receiver.oks()) == 1 and receiver.fails() == [], receiver.posts
        assert "sentinel OK" in receiver.oks()[0]
        assert "已送成功 ping（HTTP 200）" in out
    finally:
        receiver.close()


_ERROR_FIRST_RUNNER = """
import importlib.util, sys
spec = importlib.util.spec_from_file_location("prod_availability", sys.argv[1])
pa = importlib.util.module_from_spec(spec); sys.modules["prod_availability"] = pa; spec.loader.exec_module(pa)
def _boom(**kw):
    raise ValueError("injected detector error")   # 一般錯誤先發生（不是訊號）
pa.run_sentinel = _boom
raise SystemExit(pa.main(sys.argv[2:]))
"""


def test_t7_sigterm_during_the_alert_of_an_ordinary_error_does_not_drop_it(tmp_path: Path) -> None:
    """#398 審核第 3 輪 F3：一般錯誤先進失敗路徑（處理器尚未觸發），送告警途中第一次 SIGTERM——告警照樣送完。

    修正前：SIGTERM 在 send() 途中拋 SentinelTerminated，被內層 except 吞掉，rc 0 卻沒有任何送出結果。
    """
    receiver = Receiver(hold=True)
    try:
        cmd = [SYSTEM_PYTHON, "-c", _ERROR_FIRST_RUNNER, str(SCRIPT), "sentinel",
               "--stop-file", str(tmp_path / "no-stop"), "--base-url", "http://127.0.0.1:9",
               "--out", str(tmp_path / "out.tsv")]
        proc = _start(cmd, _sentinel_env(tmp_path, receiver, curl_sleep=0))
        assert receiver.got_post.wait(15), "一般錯誤後沒有送出告警"
        proc.send_signal(signal.SIGTERM)  # 告警正在送（收件端還沒回應）
        time.sleep(0.5)
        receiver.release.set()
        rc, out, err, _ = _finish(proc, timeout=15)

        assert rc == 0, err
        assert receiver.oks() == [] and len(receiver.fails()) == 1, receiver.posts
        assert "detector error ValueError" in receiver.fails()[0]
        assert out.count("已送告警（HTTP 200）") == 1, f"告警被 SIGTERM 中止：stdout={out!r} stderr={err!r}"
    finally:
        receiver.close()


def test_t1c_handler_ignores_further_sigterm_from_its_first_trigger(monkeypatch, tmp_path: Path) -> None:
    """處理器第一次觸發的當下就忽略後續 SIGTERM——在例外往外傳（subprocess 收尾等）期間、還沒進失敗路徑
    之前就已生效。失敗路徑開頭的忽略（F3）蓋不到這段窗口，所以這條直接在窗口內觀察（Md 變異用）。
    """
    seen = []

    def fake_sentinel(**kw):
        try:
            signal.raise_signal(signal.SIGTERM)
        except BaseException:
            seen.append(signal.getsignal(signal.SIGTERM))   # 例外剛離開處理器、尚未到 main 的失敗路徑
            raise
        return []

    monkeypatch.setattr(pa, "run_sentinel", fake_sentinel)
    monkeypatch.setattr(pa, "send", lambda *a, **k: "logged")
    assert pa.main(["sentinel", "--stop-file", str(tmp_path / "s"), "--out", str(tmp_path / "o.tsv")]) == 0
    assert seen == [signal.SIG_IGN], seen


def test_t6_daily_fallback_grace_is_at_least_the_send_timeout() -> None:
    """鏈端寬限 ≥ send() 的送出逾時（兩個值都從原始碼讀，不手打），且不超過規劃停止條件的 60 秒。"""
    import inspect

    send_timeout = int(re.search(r"timeout=(\d+)", inspect.getsource(pa.send)).group(1))
    daily = (ROOT / "scripts" / "scrape-daily.sh").read_text(encoding="utf-8")
    grace = int(re.search(r"^FALLBACK_KILL_GRACE=(\d+)$", daily, re.M).group(1))
    assert send_timeout <= grace <= 60
    assert grace >= send_timeout + pa.CURL_MAX_TIME, "規劃 r2 §2：送出逾時＋一輪 curl 收尾"


def test_sentinel_terminated_is_not_an_exception_subclass() -> None:
    """⛔ 改回 Exception 就會再被 curl_sample()／send() 的 except Exception 吞掉（F1-R2）。"""
    assert issubclass(pa.SentinelTerminated, BaseException)
    assert not issubclass(pa.SentinelTerminated, Exception)


def test_main_restores_the_previous_sigterm_handler(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(pa, "run_probe", lambda **kw: [])
    monkeypatch.setattr(pa, "send", lambda *a, **k: "logged")
    before = signal.getsignal(signal.SIGTERM)
    assert pa.main(["probe"]) == 0
    assert signal.getsignal(signal.SIGTERM) is before
