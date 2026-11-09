"""#442 PLAN v4 G1–G4：SWRCache、@cached 裝飾器、背景刷新者、池忙讓路（不碰 DB）。"""

from __future__ import annotations

import threading
import time

import pytest
from fastapi import Query

from cpbl.api import pool_yield, response_cache
from cpbl.api.ttl_cache import SWRCache


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


# ---------------------------------------------------------------- G1 單飛／TTL
def test_fresh_hit_computes_once():
    clk = Clock()
    c = SWRCache(10, clock=clk)
    calls = []
    assert c.get("k", lambda: calls.append(1) or "v") == "v"
    assert c.get("k", lambda: calls.append(1) or "v2") == "v"
    assert calls == [1]


def test_concurrent_same_key_single_flight():
    c = SWRCache(10)
    calls, gate, out = [], threading.Event(), []

    def slow():
        calls.append(1)
        gate.wait(2)
        return {"x": 1}

    ts = [threading.Thread(target=lambda: out.append(c.get("k", slow))) for _ in range(8)]
    for t in ts:
        t.start()
    time.sleep(0.2)
    gate.set()
    for t in ts:
        t.join(5)
    assert len(calls) == 1 and len(out) == 8 and all(o is out[0] for o in out)


# ---------------------------------------------------------------- G2 過期仍回舊值
def test_stale_returns_old_value_and_signals_refresh():
    clk = Clock()
    marked = []
    c = SWRCache(10, max_stale_s=100, clock=clk, on_stale=marked.append)
    c.get("k", lambda: "old")
    clk.t += 20
    assert c.get("k", lambda: pytest.fail("過期讀取不得同步重算")) == "old"
    assert marked == ["k"]


def test_beyond_max_stale_recomputes_synchronously():
    clk = Clock()
    c = SWRCache(10, max_stale_s=30, clock=clk)
    c.get("k", lambda: "old")
    clk.t += 31
    assert c.get("k", lambda: "new") == "new"


def test_refresh_key_and_due_keys():
    clk = Clock()
    c = SWRCache(10, max_stale_s=100, clock=clk, refresh_ahead=0.8)
    n = {"v": 0}

    def comp():
        n["v"] += 1
        return n["v"]

    c.get("pinned", comp, pin=True)
    c.get("read", comp)
    clk.t += 9  # 已過 0.8×TTL
    assert set(c.due_keys()) == {"pinned", "read"}
    assert c.refresh_key("pinned") is True
    assert c.get("pinned", comp) == 3
    clk.t += 200  # read 鍵久未讀 → 不再主動刷新；釘選鍵仍刷新
    assert c.due_keys() == ["pinned"]


# ---------------------------------------------------------------- G3 領頭者失敗
def test_leader_failure_with_old_value_returns_old_to_everyone():
    clk = Clock()
    c = SWRCache(10, max_stale_s=15, clock=clk)
    c.get("k", lambda: "old")
    clk.t += 16  # 超過 max_stale → 同步重算

    def boom():
        raise RuntimeError("timeout")

    assert c.get("k", boom) == "old"


def test_leader_failure_without_old_value_shared_and_cooled_down():
    clk = Clock()
    c = SWRCache(10, clock=clk, fail_cooldown_s=2)
    calls = []

    def boom():
        calls.append(1)
        raise RuntimeError("timeout")

    with pytest.raises(RuntimeError):
        c.get("k", boom)
    with pytest.raises(RuntimeError):  # 冷卻期內不重算
        c.get("k", boom)
    assert calls == [1]
    clk.t += 3
    assert c.get("k", lambda: "ok") == "ok"


def test_followers_do_not_recompute_on_leader_failure():
    c = SWRCache(10, fail_cooldown_s=5)
    calls, gate, errs = [], threading.Event(), []

    def slow_boom():
        calls.append(1)
        gate.wait(2)
        raise RuntimeError("x")

    def run():
        try:
            c.get("k", slow_boom)
        except RuntimeError as e:
            errs.append(e)

    ts = [threading.Thread(target=run) for _ in range(6)]
    for t in ts:
        t.start()
    time.sleep(0.2)
    gate.set()
    for t in ts:
        t.join(5)
    assert len(calls) == 1 and len(errs) == 6


# ---------------------------------------------------------------- @cached 裝飾器
def test_cached_decorator_key_resolves_query_defaults(monkeypatch):
    monkeypatch.setattr(response_cache, "CACHE", SWRCache(600))
    calls = []

    @response_cache.cached
    def ep(code: str, season: int = Query(2026), kind_code: str = Query("A")) -> dict:
        calls.append((code, season, kind_code))
        return {"code": code, "season": season}

    # FastAPI 以關鍵字傳全部參數；直接呼叫缺省時取 Query default → 兩者同鍵
    a = ep(code="AAA011", season=2026, kind_code="A")
    b = ep(code="AAA011")
    c = ep(code="ACN011", season=2026, kind_code="A")
    assert a is b and calls == [("AAA011", 2026, "A"), ("ACN011", 2026, "A")]
    assert c["code"] == "ACN011"
    assert ep.uncached(code="AAA011", season=2026, kind_code="A") == a  # 有無快取內容相同


def test_cached_decorator_keeps_fastapi_signature():
    import inspect

    from cpbl.api.routers import teams

    sig = inspect.signature(teams.special_records_endpoint)
    assert list(sig.parameters) == ["season", "kind_code"]
    assert sig.parameters["season"].annotation is int


# ---------------------------------------------------------------- G4 池忙讓路
class _FakePool:
    def __init__(self, stats):
        self.stats = stats

    def get_stats(self):
        return dict(self.stats)


def test_pool_busy_reads_stats(monkeypatch):
    from cpbl import db

    monkeypatch.setattr(db, "_pool", None)
    assert pool_yield.pool_busy() is False  # 未建立池＝不忙、⛔ 不建立
    monkeypatch.setattr(db, "_pool", _FakePool({"requests_waiting": 2, "pool_size": 8,
                                                "pool_available": 0, "pool_max": 8}))
    assert pool_yield.pool_busy() is True
    monkeypatch.setattr(db, "_pool", _FakePool({"requests_waiting": 0, "pool_size": 8,
                                                "pool_available": 0, "pool_max": 8}))
    assert pool_yield.pool_busy() is True   # 滿池且無可用連線
    monkeypatch.setattr(db, "_pool", _FakePool({"requests_waiting": 0, "pool_size": 3,
                                                "pool_available": 0, "pool_max": 8}))
    assert pool_yield.pool_busy() is False  # 還能長新連線


def test_wait_until_idle_waits_then_proceeds(monkeypatch):
    seq = iter([True, True, False])
    monkeypatch.setattr(pool_yield, "pool_busy", lambda: next(seq))
    t0 = time.monotonic()
    assert pool_yield.wait_until_idle(poll_s=0.01) is True
    assert 0.015 <= time.monotonic() - t0 < 1


def test_wait_until_idle_has_no_time_cap(monkeypatch):
    """池一直忙就一直等（審核 r1b F2：撤除 30 s 上限）；只有 stop 能讓它回 False。"""
    monkeypatch.setattr(pool_yield, "pool_busy", lambda: True)
    stop = threading.Event()
    threading.Timer(0.3, stop.set).start()
    t0 = time.monotonic()
    assert pool_yield.wait_until_idle(stop, poll_s=0.01) is False
    assert time.monotonic() - t0 >= 0.29


def test_info_background_refresh_yields_when_pool_busy(monkeypatch):
    """/api/info 背景重算：池忙時先讓路（只改時機）；讓路結束才借連線重算。"""
    from cpbl import db
    from cpbl.api.routers import info

    busy_until = time.monotonic() + 0.6
    stats_busy = {"requests_waiting": 3, "pool_size": 8, "pool_available": 0, "pool_max": 8}
    stats_idle = {"requests_waiting": 0, "pool_size": 8, "pool_available": 4, "pool_max": 8}

    class _Pool:
        def get_stats(self):
            return dict(stats_busy if time.monotonic() < busy_until else stats_idle)

    monkeypatch.setattr(db, "_pool", _Pool())
    computes: list[float] = []
    monkeypatch.setattr(info, "_compute", lambda: computes.append(time.monotonic()) or info._Snapshot(
        time.time(), True, "running", {}))
    cache = info._CACHE                     # 背景重算寫回的是模組全域 _CACHE（_refresh），所以直接用它
    try:
        cache.start(0.05)                   # 啟動預熱算 1 次；之後每 0.05 s 背景重算
        time.sleep(1.8)
    finally:
        cache.stop()                        # stop 會清掉快照，不污染其他測試
    monkeypatch.setattr(db, "_pool", None)
    background = computes[1:]
    assert background, "應有背景重算"
    assert min(background) >= busy_until    # 池忙期間⛔ 不借連線重算


def test_refresher_runs_due_keys_after_yield(monkeypatch):
    clk = Clock()
    cache = SWRCache(10, clock=clk)
    r = response_cache.Refresher(cache)
    yields = []
    monkeypatch.setattr(response_cache, "wait_until_idle", lambda stop=None: yields.append(1) or True)
    n = {"v": 0}

    def comp():
        n["v"] += 1
        return n["v"]

    cache.get("a", comp, pin=True)
    cache.get("b", comp, pin=True)
    clk.t += 9
    assert r.run_once() == 2 and len(yields) == 2
