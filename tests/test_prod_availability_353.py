"""#353 WP4：正式站可用性哨兵／探針（``scripts/prod_availability.py``）。零網路：curl 與時鐘都是假的。"""

from __future__ import annotations

import importlib.util
import sys
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
