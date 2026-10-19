"""#332 P3：worker 原位就緒證據。不連真 Redis／官網；socket 用 /tmp 短路徑。"""
from __future__ import annotations

import json
import os
import shutil
import socket
import tempfile
import threading
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from cpbl.ingest.live_game_worker import LiveGameWorker, StatsLiveSource
from cpbl.ingest.live_worker_readiness import (
    LATEST_FILE,
    SOCKET_FILE,
    LiveWorkerReadiness,
    digest,
    redis_key,
)
from cpbl.readiness import check_worker, main

T0 = datetime(2026, 7, 28, 17, 0, tzinfo=UTC)  # 台北 07-29 01:00；7 月單一分區


def _team(code: str, score: int | None = 0) -> dict:
    return {"Team": {"Code": code, "Name": code}, "Score": score, "Hitters": [],
            "Pitchers": [], "InningScore": []}


def _game(game_id: str = "2026-A-226", status: str = "START", *, livelog=None,
          starts_at: str = "2026-07-28T18:35:00", score: int | None = 0) -> dict:
    year, kind, sno = game_id.split("-")
    raw = {"GameId": game_id, "GameSno": int(sno), "KindCode": kind, "GameStatus": status,
           "PreExeDate": starts_at, "InningSeq": 1, "VisitingHomeType": 1,
           "Visiting": _team("AAA", score), "Home": _team("BBB", score)}
    if livelog is not None:
        raw["LiveLog"] = livelog
    return raw


def _row(game_id: str, starts_at: str = "2026-07-28T18:35:00") -> dict:
    year, kind, sno = game_id.split("-")
    return {"GameId": game_id, "GameSno": int(sno), "KindCode": kind,
            "PreExeDate": starts_at}


class Cache:
    def __init__(self, *, lock=True, killed=False, corrupt_write=False) -> None:
        self.lock, self.killed, self.corrupt_write = lock, killed, corrupt_write
        self.items: dict[tuple, dict] = {}
        self.errors: list = []

    def acquire_lock(self):
        return self.lock

    def is_killed(self):
        return self.killed

    def release_lock(self):
        pass

    def get_snapshot(self, year, kind, sno):
        value = self.items.get((year, kind, sno))
        return deepcopy(value) if value is not None else None

    def set_snapshot(self, snapshot):
        year, kind, sno = snapshot["game_id"].split("-")
        stored = deepcopy(snapshot)
        if self.corrupt_write:
            stored["home"]["score"] = 99
        self.items[(int(year), kind, int(sno))] = stored

    def record_source_error(self, year, kind, sno, *, observed_at, error_type):
        self.errors.append((year, kind, sno, error_type))


class Redis:
    def __init__(self, *, fail_set=False) -> None:
        self.values: dict[str, str] = {}
        self.fail_set = fail_set

    def set(self, key, value, *, ex=None, nx=False):
        if self.fail_set:
            raise ConnectionError("down")
        self.values[key] = value
        return True

    def get(self, key):
        return self.values.get(key)

    def close(self):
        pass


@pytest.fixture
def evidence_dir():
    # macOS AF_UNIX 路徑上限 104 bytes：pytest tmp_path 太長。
    path = Path(tempfile.mkdtemp(prefix="c332-", dir="/tmp")) / "ev"
    yield path
    shutil.rmtree(path.parent, ignore_errors=True)


def _source(schedule: dict, games: dict, calls: list | None = None) -> StatsLiveSource:
    def handler(request: httpx.Request) -> httpx.Response:
        if calls is not None:
            calls.append(str(request.url))
        if request.url.path.endswith("/games/schedule"):
            key = (request.url.params["kindCode"], int(request.url.params["month"]))
            payload = schedule.get(key, {"Data": {"Games": []}})
            if isinstance(payload, Exception):
                raise payload
            return httpx.Response(200, json=payload)
        game_id = request.url.path.rsplit("/", 1)[1]
        value = games[game_id]
        if isinstance(value, Exception):
            raise value
        return httpx.Response(200, json={"Data": {"Game": value}})

    return StatsLiveSource(client=httpx.Client(transport=httpx.MockTransport(handler)))


def _harness(evidence_dir, *, schedule, games, cache=None, redis=None, kinds=(),
             max_games=8, start=False):
    cache = cache or Cache()
    redis = redis or Redis()
    source = _source(schedule, games)
    observer = LiveWorkerReadiness(directory=evidence_dir, redis_client=redis,
                                   prefix="cpbl:live", cache=cache, max_games=max_games,
                                   clock=lambda: T0)
    if start:
        observer.start()
    source.payload_observer = observer.partition_payload
    worker = LiveGameWorker(cache=cache, fetch_schedule=source.fetch_schedule,
                            fetch_game=source.fetch_game, max_games_per_cycle=max_games,
                            postseason_kinds=kinds, readiness_observer=observer)
    return SimpleNamespace(cache=cache, redis=redis, source=source, observer=observer,
                           worker=worker)


def _cycle(h, now=T0, delay=600):
    h.observer.begin_attempt(now)
    try:
        result = h.worker.run_cycle(now)
    except Exception as exc:  # noqa: BLE001 — 與 run_live_game_worker 的程序邊界相同
        result = {"state": "error", "error_type": type(exc).__name__}
    h.observer.end_attempt(result, delay, now)
    return result, h.observer.snapshot_for("0" * 32)["m2"]


def _one_game(**changes):
    return {("A", 7): {"Data": {"Games": [_row("2026-A-226")]}}}, {"2026-A-226": _game(**changes)}


# ── 單輪分類 ───────────────────────────────────────────────────

def test_written_and_read_back_game_is_ready(evidence_dir):
    schedule, games = _one_game(livelog=[])
    result, summary = _cycle(_harness(evidence_dir, schedule=schedule, games=games))
    assert result["state"] == "ok"
    assert summary["result"] == "ready", summary["reasons"]
    assert summary["delivery"]["write_readback"] == 1
    assert summary["games"][0]["disposition"] == "write_readback"
    # 預告先發恆 not_announced、TrackMan pending：合法缺值只進來源可用度，不擋 ready。
    assert summary["source_availability"]["state"] == "partial"


def test_explicit_empty_partition_is_ready_with_zero_games(evidence_dir):
    _, summary = _cycle(_harness(evidence_dir, schedule={("A", 7): {"Data": {"Games": []}}},
                                 games={}))
    assert summary["result"] == "ready"
    assert summary["selected"] == []
    assert summary["partitions"][0]["row_count"] == 0


@pytest.mark.parametrize("payload", [{"Data": {"Games": None}}, {"Data": {}}, {},
                                     {"Data": {"Games": {}}}])
def test_null_or_missing_games_is_unknown_even_though_worker_sees_empty(evidence_dir, payload):
    h = _harness(evidence_dir, schedule={("A", 7): payload}, games={})
    result, summary = _cycle(h)
    assert result["state"] == "ok" and result["selected"] == 0  # 既有行為：壓成空
    assert summary["result"] == "unknown"
    assert "partition_games_not_list" in summary["reasons"]


def test_postseason_partition_failure_is_unknown_and_a_still_runs(evidence_dir):
    schedule, games = _one_game(livelog=[])
    schedule[("E", 7)] = httpx.ConnectError("boom")
    h = _harness(evidence_dir, schedule=schedule, games=games, kinds=("E", "C"))
    result, summary = _cycle(h)
    assert result["cached"] == 1
    assert summary["result"] == "unknown"
    assert "partition_fetch_failed" in summary["reasons"]
    assert {(p["kind"], p["month"]) for p in summary["partitions"]} == {
        ("A", 7), ("C", 7), ("E", 7)}


def test_a_partition_failure_is_cycle_error_not_ready(evidence_dir):
    h = _harness(evidence_dir, schedule={("A", 7): httpx.ConnectError("boom")}, games={})
    result, summary = _cycle(h)
    assert result["state"] == "error"
    assert summary["result"] == "not_ready"
    assert summary["reasons"] == ["worker_cycle_error"]


def test_single_game_source_failure_is_partial_not_ready(evidence_dir):
    schedule = {("A", 7): {"Data": {"Games": [_row("2026-A-226"), _row("2026-A-227")]}}}
    games = {"2026-A-226": _game(livelog=[]),
             "2026-A-227": httpx.ReadTimeout("slow")}
    _, summary = _cycle(_harness(evidence_dir, schedule=schedule, games=games))
    assert summary["result"] == "not_ready"
    assert summary["delivery"]["state"] == "partial"
    assert summary["delivery"]["failed"] == 1


def test_overflow_beyond_existing_limit_is_partial(evidence_dir):
    ids = [f"2026-A-{n}" for n in range(220, 223)]
    schedule = {("A", 7): {"Data": {"Games": [_row(i) for i in ids]}}}
    games = {i: _game(i, livelog=[]) for i in ids}
    _, summary = _cycle(_harness(evidence_dir, schedule=schedule, games=games, max_games=2))
    assert summary["overflow_count"] == 1
    assert summary["result"] == "not_ready"
    assert "delivery_partial" in summary["reasons"]


def test_readback_mismatch_is_failed(evidence_dir):
    schedule, games = _one_game(livelog=[])
    _, summary = _cycle(_harness(evidence_dir, schedule=schedule, games=games,
                                 cache=Cache(corrupt_write=True)))
    assert summary["games"][0]["reasons"] == ["readback_mismatch"]
    assert summary["result"] == "not_ready"


def test_live_game_with_malformed_or_absent_livelog_is_incomplete(evidence_dir):
    for livelog, reason in (("bad", "raw_livelog_malformed"), (None, "raw_livelog_absent")):
        schedule, games = _one_game(livelog=livelog)
        _, summary = _cycle(_harness(evidence_dir, schedule=schedule, games=games))
        assert summary["result"] == "unknown"
        assert reason in summary["reasons"]


def test_pregame_without_livelog_and_unannounced_lineup_is_legal(evidence_dir):
    schedule, games = _one_game(status="SCHEDULED", livelog=None, score=None)
    _, summary = _cycle(_harness(evidence_dir, schedule=schedule, games=games))
    assert summary["result"] == "ready", summary["reasons"]
    availability = summary["source_availability"]["games"][0]
    assert availability["lineup"] == {"away": "not_announced", "home": "not_announced"}


def test_unknown_official_status_is_not_complete(evidence_dir):
    schedule, games = _one_game(status="SUSPENDED_NEW", livelog=[])
    _, summary = _cycle(_harness(evidence_dir, schedule=schedule, games=games))
    assert summary["result"] == "unknown"
    assert "snapshot_phase_unknown" in summary["reasons"]


def test_valid_final_is_reused_without_rewrite_and_missing_final_score_is_unknown(evidence_dir):
    schedule, games = _one_game(status="FINISHED", livelog=[])
    h = _harness(evidence_dir, schedule=schedule, games=games)
    _cycle(h)
    before = deepcopy(h.cache.items)
    _, summary = _cycle(h)
    assert summary["games"][0]["disposition"] == "reused_final"
    assert summary["result"] == "ready"
    assert h.cache.items == before  # final 原版本／時點不被改寫
    h.cache.items[(2026, "A", 226)]["home"]["score"] = None
    _, summary = _cycle(h)
    assert summary["result"] == "unknown"
    assert "home_score_unknown" in summary["reasons"]


def test_detail_moved_out_of_window_is_terminal(evidence_dir):
    schedule = {("A", 7): {"Data": {"Games": [_row("2026-A-226")]}}}
    games = {"2026-A-226": _game(livelog=[], starts_at="2026-08-02T18:35:00")}
    h = _harness(evidence_dir, schedule=schedule, games=games)
    _, summary = _cycle(h)
    assert summary["games"][0]["disposition"] == "moved_out_of_window"
    assert summary["result"] == "ready"
    assert h.cache.items == {}


def test_partition_with_unidentifiable_rows_is_unknown(evidence_dir):
    schedule = {("A", 7): {"Data": {"Games": [{"GameId": "x"}, _row("2026-A-226")]}}}
    games = {"2026-A-226": _game(livelog=[])}
    _, summary = _cycle(_harness(evidence_dir, schedule=schedule, games=games))
    assert summary["result"] == "unknown"
    assert "partition_rows_invalid" in summary["reasons"]


@pytest.mark.parametrize("cache,reason", [(Cache(lock=False), "worker_locked"),
                                          (Cache(killed=True), "worker_killed")])
def test_locked_or_killed_is_not_ready(evidence_dir, cache, reason):
    _, summary = _cycle(_harness(evidence_dir, schedule={}, games={}, cache=cache))
    assert summary["result"] == "not_ready"
    assert summary["reasons"] == [reason]


def test_new_failure_is_not_masked_by_previous_success(evidence_dir):
    schedule, games = _one_game(livelog=[])
    h = _harness(evidence_dir, schedule=schedule, games=games)
    _, first = _cycle(h)
    assert first["result"] == "ready"
    h.cache.lock = False
    _, second = _cycle(h)
    assert second["attempt"] == first["attempt"] + 1
    assert second["result"] == "not_ready"


# ── 不改變 worker 行為 ─────────────────────────────────────────

class _Exploding:
    def __getattr__(self, name):
        if name == "mark_fault":
            return lambda *_: None
        def boom(*args):
            raise RuntimeError(name)
        return boom


def test_observer_hooks_do_not_change_cycle_result_or_writes():
    schedule = {("A", 7): {"Data": {"Games": [_row("2026-A-226"), _row("2026-A-227")]}},
                ("E", 7): {"Data": {"Games": None}}}
    games = {"2026-A-226": _game(livelog=[]), "2026-A-227": httpx.ReadTimeout("slow")}
    outputs = []
    for observer in (None, _Exploding()):
        cache = Cache()
        source = _source(schedule, games)
        source.payload_observer = observer.partition_payload if observer else None
        worker = LiveGameWorker(cache=cache, fetch_schedule=source.fetch_schedule,
                                fetch_game=source.fetch_game, postseason_kinds=("E",),
                                readiness_observer=observer)
        outputs.append((worker.run_cycle(T0), cache.items, cache.errors))
    assert outputs[0] == outputs[1]


def test_observer_fault_makes_cycle_unknown(evidence_dir):
    schedule, games = _one_game(livelog=[])
    h = _harness(evidence_dir, schedule=schedule, games=games)
    h.observer.cache = None  # 讀回元件故障
    _, summary = _cycle(h)
    assert summary["result"] == "not_ready"  # 讀回失敗＝本場交付未證實
    assert summary["games"][0]["reasons"] == ["readback_error:AttributeError"]


def test_m1_is_updated_before_cycle_io(evidence_dir):
    seen = []
    schedule = {("A", 7): {"Data": {"Games": []}}}
    h = _harness(evidence_dir, schedule=schedule, games={})
    original = h.source.fetch_schedule

    def spy(year, month, kind="A"):
        seen.append(h.observer.snapshot_for("0" * 32)["m1"]["attempt"])
        return original(year, month, kind)

    h.worker.fetch_schedule = spy
    _cycle(h)
    _cycle(h)
    assert seen == [1, 2]


# ── 持久化、socket 與讀取端 ─────────────────────────────────────

def _settings(evidence_dir, **changes):
    values = dict(live_game_worker_enabled=True, redis_url="redis://x/0",
                  live_worker_readiness_dir=evidence_dir, live_game_cache_prefix="cpbl:live")
    values.update(changes)
    return SimpleNamespace(**values)


def _read(h, evidence_dir, now=T0, **kwargs):
    kwargs.setdefault("sleep", lambda _: None)
    return check_worker(_settings(evidence_dir), redis_factory=lambda _: h.redis,
                        clock=lambda: now, **kwargs)


def test_persisted_evidence_is_private_bounded_and_matches_memory(evidence_dir):
    schedule, games = _one_game(livelog=[])
    h = _harness(evidence_dir, schedule=schedule, games=games, start=True)
    try:
        _, summary = _cycle(h)
        latest = evidence_dir / LATEST_FILE
        assert oct(os.stat(evidence_dir).st_mode & 0o777) == "0o700"
        assert oct(os.stat(latest).st_mode & 0o777) == "0o600"
        assert oct(os.stat(evidence_dir / SOCKET_FILE).st_mode & 0o777) == "0o600"
        assert latest.stat().st_size <= 65_536 + 1024
        stored = json.loads(latest.read_bytes())
        assert stored["digest"] == digest(summary)
        credential = json.loads(h.redis.values[redis_key("cpbl:live", h.observer.instance)])
        assert credential["attempt"] == summary["attempt"]
        report = _read(h, evidence_dir)
        assert report["result"] == "ready", report["reasons"]
        assert report["worker"]["evidence"] == {"file": "match", "redis": "match"}
    finally:
        h.observer.close()
    assert not (evidence_dir / SOCKET_FILE).exists()


def test_both_persistent_writes_failing_is_unknown_not_old_success(evidence_dir):
    schedule, games = _one_game(livelog=[])
    h = _harness(evidence_dir, schedule=schedule, games=games, start=True)
    slept = []
    try:
        _cycle(h)
        assert _read(h, evidence_dir)["result"] == "ready"
        # 第二輪：本機檔與 Redis 都寫不進去；記憶體 M2 比兩處持久紀錄新。
        h.redis.fail_set = True
        os.chmod(evidence_dir, 0o500)
        try:
            h.cache.lock = False
            _cycle(h)
        finally:
            os.chmod(evidence_dir, 0o700)
        report = _read(h, evidence_dir, sleep=slept.append)
        assert report["result"] == "unknown"
        assert report["reasons"] == ["evidence_persist_stale"]
        assert slept == [2.0]  # 只重讀一次
    finally:
        h.observer.close()


def test_one_persistent_copy_suffices(evidence_dir):
    schedule, games = _one_game(livelog=[])
    h = _harness(evidence_dir, schedule=schedule, games=games, redis=Redis(fail_set=True),
                 start=True)
    try:
        _cycle(h)
        report = _read(h, evidence_dir)
        assert report["result"] == "ready"
        assert report["worker"]["evidence"] == {"file": "match", "redis": "missing"}
        assert report["worker"]["persist"]["redis"] == "error:ConnectionError"
    finally:
        h.observer.close()


def test_freshness_window_is_sleep_plus_60_seconds(evidence_dir):
    schedule, games = _one_game(livelog=[])
    h = _harness(evidence_dir, schedule=schedule, games=games, start=True)
    try:
        _cycle(h, delay=600)
        assert _read(h, evidence_dir, now=T0 + timedelta(seconds=660))["result"] == "ready"
        late = _read(h, evidence_dir, now=T0 + timedelta(seconds=661))
        assert (late["result"], late["reasons"]) == ("unknown", ["evidence_stale"])
    finally:
        h.observer.close()


def test_cycle_running_over_120_seconds_is_unknown(evidence_dir):
    schedule, games = _one_game(livelog=[])
    h = _harness(evidence_dir, schedule=schedule, games=games, start=True)
    try:
        _cycle(h, delay=3600)
        h.observer.begin_attempt(T0 + timedelta(seconds=10))
        running = _read(h, evidence_dir, now=T0 + timedelta(seconds=130))
        assert running["result"] == "ready" and running["worker"]["in_progress"] is True
        hung = _read(h, evidence_dir, now=T0 + timedelta(seconds=131))
        assert (hung["result"], hung["reasons"]) == ("unknown", ["cycle_timeout"])
    finally:
        h.observer.close()


def test_first_attempt_without_conclusion_is_unknown(evidence_dir):
    h = _harness(evidence_dir, schedule={}, games={}, start=True)
    try:
        h.observer.begin_attempt(T0)
        assert _read(h, evidence_dir)["reasons"] == ["no_completed_attempt"]
    finally:
        h.observer.close()


def test_stale_nonce_or_dead_worker_is_unknown(evidence_dir):
    schedule, games = _one_game(livelog=[])
    h = _harness(evidence_dir, schedule=schedule, games=games, start=True)
    try:
        _cycle(h)
        replay = json.dumps(h.observer.snapshot_for("f" * 32)).encode() + b"\n"
        report = _read(h, evidence_dir, ask=lambda path, nonce: replay)
        assert report["reasons"] == ["worker_nonce_mismatch"]
    finally:
        h.observer.close()
    # 程序結束後 socket 消失；本機檔與 Redis 舊成功都不能代替存活。
    report = _read(h, evidence_dir)
    assert (report["result"], report["reasons"]) == ("unknown", ["worker_socket_unavailable"])


def test_socket_rejects_anything_but_a_nonce(evidence_dir):
    h = _harness(evidence_dir, schedule={}, games={}, start=True)
    try:
        for request in (b'{"cmd":"kill"}\n', b"x" * 300 + b"\n", b'{"nonce":"ABC"}\n'):
            client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            client.settimeout(2)
            client.connect(str(evidence_dir / SOCKET_FILE))
            client.sendall(request)
            assert client.recv(10) == b""
            client.close()
    finally:
        h.observer.close()


def test_disabled_unsafe_dir_and_missing_redis(evidence_dir):
    assert check_worker(_settings(evidence_dir, live_game_worker_enabled=False))["reasons"] == [
        "worker_disabled"]
    assert check_worker(_settings(evidence_dir, redis_url=None))["result"] == "unknown"
    evidence_dir.mkdir(mode=0o755)
    os.chmod(evidence_dir, 0o755)
    report = check_worker(_settings(evidence_dir))
    assert (report["result"], report["reasons"]) == ("unknown", ["evidence_dir_unavailable"])


def test_observer_refuses_foreign_or_open_directory(evidence_dir):
    evidence_dir.mkdir(mode=0o755)
    os.chmod(evidence_dir, 0o755)
    h = _harness(evidence_dir, schedule={}, games={}, start=True)
    try:
        _cycle(h)
        assert not (evidence_dir / SOCKET_FILE).exists()
        assert not (evidence_dir / LATEST_FILE).exists()
        assert h.observer.snapshot_for("0" * 32)["persist"]["file"] == "unsafe_dir"
    finally:
        h.observer.close()


def test_cli_worker_exit_codes_follow_result(evidence_dir, capsys):
    report = check_worker(_settings(evidence_dir, live_game_worker_enabled=False))
    assert main(["--target", "worker"], runner=lambda _: (report, 1)) == 1
    assert json.loads(capsys.readouterr().out)["result"] == "not_ready"


def test_concurrent_reads_do_not_block_cycles(evidence_dir):
    schedule, games = _one_game(livelog=[])
    h = _harness(evidence_dir, schedule=schedule, games=games, start=True)
    stop = threading.Event()
    results = []

    def reader():
        while not stop.is_set():
            results.append(_read(h, evidence_dir)["result"])

    thread = threading.Thread(target=reader)
    try:
        _cycle(h)
        thread.start()
        for _ in range(5):
            h.cache.items.clear()
            _cycle(h)
        stop.set()
        thread.join(timeout=10)
        assert results and set(results) <= {"ready", "unknown"}
        assert _read(h, evidence_dir)["result"] == "ready"
    finally:
        stop.set()
        h.observer.close()


# ── run_live_game_worker 主迴圈接線（替身來源／Redis，不連官網）──────────

class _FakeSource:
    def __init__(self):
        self.payload_observer = None

    def fetch_schedule(self, year, month, kind_code="A"):
        payload = {"Data": {"Games": []}}
        if self.payload_observer is not None:
            self.payload_observer(kind_code, year, month, payload)
        return payload["Data"]["Games"]

    def fetch_game(self, game_id):
        raise AssertionError("no games expected")

    def close(self):
        pass


@pytest.fixture
def worker_main(monkeypatch, evidence_dir):
    import signal

    from cpbl.ingest import run_live_game_worker as module

    redis = Redis()
    redis.eval = lambda *args: 1
    monkeypatch.setattr(module, "StatsLiveSource", _FakeSource)
    monkeypatch.setattr(module.redis.Redis, "from_url", staticmethod(lambda *a, **k: redis))
    monkeypatch.setattr(module.settings, "live_game_worker_enabled", True)
    monkeypatch.setattr(module.settings, "redis_url", "redis://fake/0")
    monkeypatch.setattr(module.settings, "live_worker_readiness_dir", evidence_dir)
    monkeypatch.setattr(module.settings, "live_game_postseason_kinds", "")
    handlers = {sig: signal.getsignal(sig) for sig in (signal.SIGTERM, signal.SIGINT)}
    yield module, redis
    for sig, handler in handlers.items():
        signal.signal(sig, handler)


def test_daemon_loop_serves_evidence_while_sleeping_and_cleans_up(worker_main, evidence_dir,
                                                                  monkeypatch):
    import signal

    module, redis = worker_main
    seen = []

    def sleeping(_seconds):
        if not seen:
            seen.append(check_worker(_settings(evidence_dir),
                                     redis_factory=lambda _: redis, sleep=lambda _: None))
            os.kill(os.getpid(), signal.SIGTERM)  # 走既有 SIGTERM 停止路徑

    monkeypatch.setattr(module.time, "sleep", sleeping)
    module.main([])
    assert seen[0]["result"] == "ready", seen[0]["reasons"]
    assert seen[0]["worker"]["legacy_state"] == "ok"
    assert seen[0]["worker"]["evidence"] == {"file": "match", "redis": "match"}
    assert not (evidence_dir / SOCKET_FILE).exists()
    stopped = check_worker(_settings(evidence_dir), redis_factory=lambda _: redis)
    assert stopped["result"] == "unknown"  # 停止後不能以舊成功當就緒


def test_once_mode_output_and_evidence_unchanged(worker_main, evidence_dir, capsys):
    module, redis = worker_main
    module.main(["--once"])
    result = json.loads(capsys.readouterr().out)
    assert result["state"] == "ok" and "readiness" not in json.dumps(result)
    assert not evidence_dir.exists()
    assert not any(":readiness:" in key for key in redis.values)
