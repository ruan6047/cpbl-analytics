"""#442 審核 r1b 的兩項 finding（不碰 DB）。

F1：有舊值時重算失敗也要套冷卻——冷卻期內回舊值、⛔ 不重跑失敗的 DB 工作。
F2：池忙就延後背景工作，⛔ 不因等待逾時而在池仍忙時照跑（PLAN v4 G4「延後重試、不搶連線」）。
"""

from __future__ import annotations

import threading
import time

from cpbl.api import pool_yield, response_cache
from cpbl.api.ttl_cache import SWRCache


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


# ---------------------------------------------------------------- F1
def test_f1_failure_with_old_value_is_cooled_down():
    clk = Clock()
    c = SWRCache(10, max_stale_s=1200, fail_cooldown_s=2, clock=clk)
    c.get("k", lambda: "old")
    clk.t += 1201  # 超過 max_stale → 同步重算
    calls = []

    def boom():
        calls.append(1)
        raise RuntimeError("QueryCanceled")

    for _ in range(4):
        assert c.get("k", boom) == "old"
    assert calls == [1], "冷卻期內不得重跑已失敗的計算"
    clk.t += 3  # 冷卻過後才再試
    assert c.get("k", lambda: "new") == "new"


def test_f1_background_refresh_skips_key_in_cooldown():
    clk = Clock()
    c = SWRCache(10, max_stale_s=1200, fail_cooldown_s=2, clock=clk)
    c.get("k", lambda: "old", pin=True)
    clk.t += 1201

    def boom():
        raise RuntimeError("x")

    assert c.get("k", boom) == "old"
    assert "k" not in c.due_keys(), "冷卻中的鍵不得被背景刷新者立刻重試"
    clk.t += 3
    assert "k" in c.due_keys()


# ---------------------------------------------------------------- F2
class _FastClock:
    """讓「已等待秒數」每次讀取前進 10 s（模擬長時間持續忙碌），sleep 不實際睡。"""

    def __init__(self):
        self.t = 0.0

    def monotonic(self):
        self.t += 10.0
        return self.t

    def sleep(self, _s):
        time.sleep(0.01)


def _busy_forever(monkeypatch):
    monkeypatch.setattr(pool_yield, "pool_busy", lambda: True)
    monkeypatch.setattr(pool_yield, "time", _FastClock())


def test_f2_refresher_never_refreshes_while_pool_stays_busy(monkeypatch):
    _busy_forever(monkeypatch)
    clk = Clock()
    cache = SWRCache(10, clock=clk)
    r = response_cache.Refresher(cache)
    monkeypatch.setattr(response_cache, "wait_until_idle", pool_yield.wait_until_idle)
    refreshed = []
    cache.get("a", lambda: refreshed.append(1) or 1, pin=True)
    clk.t += 9
    stop = threading.Event()
    threading.Timer(0.5, stop.set).start()
    r.run_once(stop)
    assert refreshed == [1], "池一直忙：只有最初那次計算，背景刷新不得執行"


def test_f2_info_background_refresh_never_runs_while_pool_stays_busy(monkeypatch):
    from cpbl.api.routers import info

    _busy_forever(monkeypatch)
    monkeypatch.setattr(info, "wait_until_idle", pool_yield.wait_until_idle)
    computes: list[float] = []
    monkeypatch.setattr(info, "_compute", lambda: computes.append(time.monotonic()) or info._Snapshot(
        time.time(), True, "running", {}))
    cache = info._CACHE
    try:
        cache.start(0.05)
        time.sleep(2.5)                     # 舊行為：約 1.5 s 後（等滿上限）就會重算
    finally:
        cache.stop()
    assert len(computes) == 1, "只有啟動預熱那一次；池一直忙時背景重算一律延後"


def test_f2_wait_until_idle_reports_idle_vs_stopped(monkeypatch):
    seq = iter([True, True, False])
    monkeypatch.setattr(pool_yield, "pool_busy", lambda: next(seq))
    assert pool_yield.wait_until_idle(poll_s=0.01) is True
    monkeypatch.setattr(pool_yield, "pool_busy", lambda: True)
    stop = threading.Event()
    threading.Timer(0.1, stop.set).start()
    assert pool_yield.wait_until_idle(stop, poll_s=0.01) is False
