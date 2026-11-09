"""唯讀端點的行程內回應快取：裝飾器、背景刷新者、啟動預熱（#442 PLAN v4 G1／G2）。

快取機制本體在 :mod:`cpbl.api.ttl_cache`；本模組把它接到 FastAPI 端點上：

- :func:`cached`：裝在同步端點函式上。鍵＝（模組, 函式, 解析後的全部參數），等同「完整路徑＋query」
  （FastAPI 呼叫端點時一律以關鍵字傳入全部參數；缺省值取 ``Query(...)`` 的 default）。
- :class:`Refresher`：單一背景執行緒，**依序**重算到期鍵（一次只借 1 條連線），每次重算前
  :func:`cpbl.api.pool_yield.wait_until_idle` 讓路。
- :func:`start`／:func:`stop`：uvicorn lifespan 呼叫；預熱 fail-open（失敗只記 log，不擋啟動），
  沿用 ``info.start_cache`` 的作法。

**哪些端點可以裝**（G1；範圍由 #442 D1 的借池持有秒數量測決定，裝在哪裡就看各 router）：
唯讀、回應不隨比賽進行即時變動、前端也沒有要求即時的端點。⛔ 不裝的即時端點與理由：

- ``games/*/live``、``games/*/status``、``games/*/winprob``、``games/*/facts``、``games/*/milestones``、
  ``games/*/report``、``games/*/report-anchor``、``playoffs/watch``：賽中逐球／逐打席會變，前端 ``getLive``
  或輪詢（``poll_after_seconds``）。
- ``daily/summary``、``outcome/pregame``、``outcome/pregame/backtest``：帶賽前模型 serving 降級揭露，
  前端註明「no-store 是正確性需求」（web/src/lib/api.ts dailySummary／pregameBacktest），
  ``outcome/pregame`` 與 daily 共用 ``pregame_serving.serving_state()``。
- ``games/calendar``、``postseason-summary``：當季已公告季後時前端改走 no-store（#237 方案 A），
  快取會讓季後旅程重新出現舊新混用。
- ``/api/info``：已有自己的 60 s 快取與契約（info.py），不經這裡。

TTL＝資料新鮮度預算 600 s（需求方裁定，#442 PLAN v4 §9 第 2 項）：前端保留 600 s 快取時，
使用者看到的最大延遲約 1,200 s；前端 no-store 時約 600 s（G2 舊值最多再回到 :data:`MAX_STALE_S`）。
"""

from __future__ import annotations

import functools
import inspect
import logging
import threading
import time
from collections.abc import Callable, Hashable
from typing import Any

from fastapi.params import Param

from cpbl.api.pool_yield import wait_until_idle
from cpbl.api.ttl_cache import SWRCache

log = logging.getLogger("cpbl.api.cache")

TTL_S = 600.0
MAX_STALE_S = 1200.0
REFRESH_POLL_S = 2.0

CACHE = SWRCache(TTL_S, max_stale_s=MAX_STALE_S)


def _freeze(v: Any) -> Hashable:
    if isinstance(v, (list, tuple)):
        return tuple(_freeze(x) for x in v)
    if isinstance(v, dict):
        return tuple(sorted((k, _freeze(x)) for k, x in v.items()))
    return v


def _resolved_kwargs(sig: inspect.Signature, args: tuple, kwargs: dict) -> dict[str, Any]:
    bound = sig.bind_partial(*args, **kwargs)
    out: dict[str, Any] = {}
    for name, p in sig.parameters.items():
        if name in bound.arguments:
            out[name] = bound.arguments[name]
        elif isinstance(p.default, Param):
            out[name] = p.default.default
        elif p.default is not inspect.Parameter.empty:
            out[name] = p.default
    return out


def cached(func: Callable[..., Any]) -> Callable[..., Any]:
    """把同步端點包上回應快取。FastAPI 看到的簽名與原函式相同（已解析的註解，見 ``__signature__``）。"""
    sig = inspect.signature(func, eval_str=True)

    def _key_and_compute(args: tuple, kwargs: dict) -> tuple[Hashable, Callable[[], Any]]:
        kw = _resolved_kwargs(sig, args, kwargs)
        key = (func.__module__, func.__qualname__, _freeze(kw))
        return key, functools.partial(func, **kw)

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        key, compute = _key_and_compute(args, kwargs)
        return CACHE.get(key, compute)

    def warm(**kwargs: Any) -> Any:
        """預熱並釘選（背景刷新者會一直讓它保持新鮮）。"""
        key, compute = _key_and_compute((), kwargs)
        return CACHE.get(key, compute, pin=True)

    wrapper.__signature__ = sig  # type: ignore[attr-defined]
    wrapper.warm = warm  # type: ignore[attr-defined]
    wrapper.uncached = func  # type: ignore[attr-defined]
    return wrapper


class Refresher:
    """單一背景執行緒：依序重算到期鍵與過期被讀到的鍵；每次重算前在池忙時讓路。"""

    def __init__(self, cache: SWRCache) -> None:
        self._cache = cache
        self._stale: set[Hashable] = set()
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        cache.on_stale = self._mark

    def _mark(self, key: Hashable) -> None:
        with self._lock:
            self._stale.add(key)

    def _pending(self) -> list[Hashable]:
        with self._lock:
            keys, self._stale = list(self._stale), set()
        return list(dict.fromkeys(keys + self._cache.due_keys()))

    def run_once(self, stop: threading.Event | None = None) -> int:
        n = 0
        for key in self._pending():
            if stop is not None and stop.is_set():
                break
            if not wait_until_idle(stop):  # 池忙就延後；回 False＝關機，⛔ 不在池忙時照跑
                break
            n += bool(self._cache.refresh_key(key))
        return n

    def start(self, prewarm: Callable[[threading.Event], object] | None = None) -> None:
        self.stop()
        self._stop = threading.Event()
        stop = self._stop

        def loop() -> None:
            if prewarm is not None:
                prewarm(stop)
            while not stop.wait(REFRESH_POLL_S):
                try:
                    self.run_once(stop)
                except Exception:  # noqa: BLE001 — 背景執行緒不得死掉
                    log.exception("cache: 背景刷新迴圈例外")

        self._thread = threading.Thread(target=loop, name="cpbl-response-cache", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
        self._thread = None


REFRESHER = Refresher(CACHE)
PREWARM_DONE = threading.Event()


def run_prewarm(jobs: list[tuple[str, Callable[[], Any]]],
                stop: threading.Event | None = None) -> tuple[int, int, float]:
    """依序執行預熱；fail-open。回傳（成功數, 失敗數, 秒數）。``stop`` 被設就提前結束（關機）。"""
    t0 = time.monotonic()
    ok = fail = 0
    for name, job in jobs:
        if stop is not None and stop.is_set():
            break
        try:
            job()
            ok += 1
        except Exception as exc:  # noqa: BLE001 — 預熱失敗不擋啟動
            fail += 1
            log.warning("cache: 預熱失敗 %s err=%s", name, type(exc).__name__)
    secs = time.monotonic() - t0
    log.warning("cache: 預熱完成 ok=%d failed=%d secs=%.1f", ok, fail, secs)
    PREWARM_DONE.set()
    return ok, fail, secs


def start(jobs_factory: Callable[[], list[tuple[str, Callable[[], Any]]]] | None = None) -> None:
    PREWARM_DONE.clear()
    REFRESHER.start((lambda stop: run_prewarm(jobs_factory(), stop)) if jobs_factory else None)


def stop() -> None:
    REFRESHER.stop()
    CACHE.clear()
