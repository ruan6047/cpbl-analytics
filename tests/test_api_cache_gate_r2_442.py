"""#442 審核 r2 F1：失敗冷卻只在單一准入點判斷，所有觸發計算的入口都經過它（不碰 DB）。

入口清單（EXEC-442-v4 §13）：E1 同步讀取、E2 背景刷新（含已排入 _stale 佇列的鍵）、
E3 預熱（warm → get(pin=True)）、E4 跟隨者（不計算）。
"""

from __future__ import annotations

import threading
import time

import pytest
from fastapi import Query

from cpbl.api import response_cache
from cpbl.api.ttl_cache import SWRCache


class Clock:
    def __init__(self, t: float = 0.0):
        self.t = t

    def __call__(self):
        return self.t


def _boom_counter(calls):
    def boom():
        calls.append(1)
        raise RuntimeError("QueryCanceled")
    return boom


def test_reviewer_sequence_queued_key_respects_cooldown(monkeypatch):
    """審核者時間序：t=1199.9 排入背景佇列 → t=1200.1 前景失敗 → t=1200.2 背景輪次⛔ 不得再算。"""
    clk = Clock(0.0)
    cache = SWRCache(600, max_stale_s=1200, fail_cooldown_s=2, clock=clk)
    r = response_cache.Refresher(cache)
    monkeypatch.setattr(response_cache, "wait_until_idle", lambda stop=None: True)
    calls: list[int] = []
    cache.get("k", lambda: "old")
    clk.t = 1199.9
    assert cache.get("k", _boom_counter(calls)) == "old"   # 舊值未超過 max_stale → 回舊值並排入佇列
    clk.t = 1200.1
    assert cache.get("k", _boom_counter(calls)) == "old"   # 超過 max_stale → 前景重算失敗、開始冷卻
    assert calls == [1]
    clk.t = 1200.2
    r.run_once()                                           # 背景輪次：佇列裡的 k 在冷卻中
    assert calls == [1], "冷卻期內背景刷新不得再跑失敗的計算"
    clk.t = 1202.2
    cache._data["k"].compute = lambda: "new"               # 冷卻過後背景可以再試
    r._mark("k")
    r.run_once()
    assert cache.get("k", lambda: pytest.fail("不應同步重算")) == "new"


def test_e1_sync_get_respects_cooldown():
    clk = Clock(0.0)
    cache = SWRCache(10, max_stale_s=20, fail_cooldown_s=2, clock=clk)
    calls: list[int] = []
    with pytest.raises(RuntimeError):
        cache.get("cold", _boom_counter(calls))
    with pytest.raises(RuntimeError):
        cache.get("cold", _boom_counter(calls))           # 沒有舊值：回同一例外、不重算
    cache.get("warm", lambda: "old")
    clk.t = 25
    assert cache.get("warm", _boom_counter(calls)) == "old"
    assert cache.get("warm", _boom_counter(calls)) == "old"  # 有舊值：回舊值、不重算
    assert calls == [1, 1]


def test_e2_refresh_key_respects_cooldown_directly():
    clk = Clock(0.0)
    cache = SWRCache(10, max_stale_s=20, fail_cooldown_s=2, clock=clk)
    calls: list[int] = []
    cache.get("k", lambda: "old")
    clk.t = 25
    cache.get("k", _boom_counter(calls))                  # 失敗 → 冷卻
    cache._data["k"].compute = _boom_counter(calls)
    assert cache.refresh_key("k") is False                 # 直接呼叫背景入口：冷卻中不計算
    assert calls == [1]


def test_e3_prewarm_respects_cooldown(monkeypatch):
    clk = Clock(0.0)
    cache = SWRCache(600, fail_cooldown_s=2, clock=clk)
    monkeypatch.setattr(response_cache, "CACHE", cache)
    calls: list[int] = []

    @response_cache.cached
    def ep(season: int = Query(2026)) -> dict:
        calls.append(1)
        raise RuntimeError("down")

    ok, fail, _ = response_cache.run_prewarm([("a", lambda: ep.warm()), ("b", lambda: ep.warm())])
    assert (ok, fail) == (0, 2)
    assert calls == [1], "同鍵預熱第二次在冷卻期內不得重算"


def test_e4_followers_never_compute():
    cache = SWRCache(10, fail_cooldown_s=5)
    calls, gate, errs = [], threading.Event(), []

    def slow_boom():
        calls.append(1)
        gate.wait(2)
        raise RuntimeError("x")

    def run():
        try:
            cache.get("k", slow_boom)
        except RuntimeError as e:
            errs.append(e)

    ts = [threading.Thread(target=run) for _ in range(5)]
    for t in ts:
        t.start()
    time.sleep(0.2)
    gate.set()
    for t in ts:
        t.join(5)
    assert len(calls) == 1 and len(errs) == 5
