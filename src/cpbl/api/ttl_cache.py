"""API 行程內的唯讀回應快取：TTL＋同鍵單飛＋過期仍回舊值（#442 PLAN v4 G1–G3）。

為什麼有這個模組：正式站 1 CPU、池 8 條。多個頁面同時 SSR（球隊頁每頁扇出約 15 支 API、6 隊同時）
時，同一個季級鍵在 3 秒內被重複算 7–8 次、各隊逐隊端點同時各算一次，借池需求遠超池容量，
重語句被拉長到 statement_timeout（QueryCanceled），輕端點借池等不到 1 s（PoolTimeout）（#442 R3／R4）。
本模組讓**爆量當下需要碰 DB 的工作量**降到池容量以下：

- **G1 單飛**：同一個鍵同時只有一個呼叫者（領頭者）真的算，其餘等它的結果。
- **G2 過期仍回舊值**：過了 TTL 先回舊值，同時交給背景刷新者依序重算（一次只借 1 條連線，
  池忙時讓路，見 :mod:`cpbl.api.pool_yield`）；背景刷新者也會在到期前主動重算「釘選鍵」
  （啟動預熱的鍵）與近期被讀過的鍵，所以穩態下爆量遇到的是暖快取。
- **G3 領頭者失敗**：有舊值就回舊值（例外只記 log，不交給等待者）；沒有舊值時等待者收到同一個
  例外、⛔ 不各自重算（避免重工作量翻倍），並在 :attr:`fail_cooldown_s` 內對同一個鍵直接回同一個
  例外，不在爆量裡反覆重算。

界線（⛔ 不得推出的事）：

- 作用域是**單一 uvicorn 行程**的記憶體；⛔ 不跨行程、不寫 DB、不碰 ``cpbl.db`` 的共用池與
  ``config.py`` 的共用預設（#353 裁定，``tests/test_api_db_timeouts_353.py`` 守門）。
- 只用在**唯讀、回應不隨比賽進行即時變動**的端點；即時端點的排除清單與理由在
  :mod:`cpbl.api.response_cache`。
- TTL＝資料新鮮度預算（需求方裁定 600 s，#442 PLAN v4 §9 第 2 項）。舊值最多回到
  :attr:`max_stale_s`；超過就同步重算（⛔ 不無限期回舊值）。唯一例外是 G3：重算失敗時，
  有任何舊值都先回舊值，因為「舊資料」比「500」好。
- 回傳的是**同一個物件**（不複製）；呼叫端⛔ 不得就地修改快取值。
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable, Hashable
from typing import Any

log = logging.getLogger("cpbl.api.cache")


class _Flight:
    __slots__ = ("done", "error", "value")

    def __init__(self) -> None:
        self.done = threading.Event()
        self.value: Any = None
        self.error: BaseException | None = None


class _Entry:
    __slots__ = ("computed_at", "compute", "last_read", "pinned", "value")

    def __init__(self, value: Any, computed_at: float, compute: Callable[[], Any],
                 last_read: float, pinned: bool) -> None:
        self.value = value
        self.computed_at = computed_at
        self.compute = compute
        self.last_read = last_read
        self.pinned = pinned


class SWRCache:
    """執行緒安全的 TTL＋單飛＋過期仍回舊值快取。背景刷新交給 :meth:`refresh_due`／:meth:`refresh_key`。"""

    def __init__(self, ttl_s: float, *, max_stale_s: float | None = None,
                 fail_cooldown_s: float = 2.0, wait_timeout_s: float = 30.0,
                 maxsize: int = 4096, refresh_ahead: float = 0.8,
                 clock: Callable[[], float] = time.monotonic,
                 on_stale: Callable[[Hashable], None] | None = None) -> None:
        if not ttl_s > 0:
            raise ValueError(f"ttl_s 必須 > 0：{ttl_s!r}")
        self.ttl_s = float(ttl_s)
        self.max_stale_s = float(max_stale_s if max_stale_s is not None else 2 * ttl_s)
        self.fail_cooldown_s = float(fail_cooldown_s)
        self._wait = wait_timeout_s
        self._maxsize = maxsize
        self._ahead = refresh_ahead
        self._clock = clock
        self._lock = threading.Lock()
        self._data: dict[Hashable, _Entry] = {}
        self._inflight: dict[Hashable, _Flight] = {}
        self._failed: dict[Hashable, tuple[float, BaseException]] = {}
        # 過期但仍回舊值時呼叫（背景刷新者據此排程）；None＝不排程（測試或無背景刷新者）。
        self.on_stale = on_stale

    # ------------------------------------------------------------------ 讀取路徑
    def get(self, key: Hashable, compute: Callable[[], Any], *, pin: bool = False) -> Any:
        now = self._clock()
        stale_hit = False
        with self._lock:
            e = self._data.get(key)
            if e is not None:
                e.last_read = now
                e.compute = compute
                e.pinned = e.pinned or pin
                age = now - e.computed_at
                if age < self.ttl_s:
                    return e.value
                if age < self.max_stale_s:
                    stale_hit = True
                    value = e.value
            if not stale_hit:
                failed = self._failed.get(key)
                if failed is not None and now < failed[0]:
                    raise failed[1]
                flight = self._inflight.get(key)
                leader = flight is None
                if leader:
                    flight = self._inflight[key] = _Flight()
        if stale_hit:
            if self.on_stale is not None:
                self.on_stale(key)
            return value
        assert flight is not None
        if not leader:
            if not flight.done.wait(self._wait):
                raise TimeoutError(f"等待同鍵計算逾時（{self._wait}s）：{key!r}")
            if flight.error is not None:
                raise flight.error
            return flight.value
        return self._lead(key, compute, flight, pin)

    def _lead(self, key: Hashable, compute: Callable[[], Any], flight: _Flight, pin: bool) -> Any:
        try:
            value = compute()
        except Exception as exc:
            with self._lock:
                old = self._data.get(key)
                self._inflight.pop(key, None)
                if old is not None:
                    flight.value = old.value
                else:
                    flight.error = exc
                    self._failed[key] = (self._clock() + self.fail_cooldown_s, exc)
            flight.done.set()
            if old is not None:
                log.warning("cache: 重算失敗，回舊值 key=%r err=%s", key, type(exc).__name__)
                return old.value
            raise
        self._store(key, value, compute, pin)
        with self._lock:
            self._inflight.pop(key, None)
        flight.value = value
        flight.done.set()
        return value

    def _store(self, key: Hashable, value: Any, compute: Callable[[], Any], pin: bool) -> None:
        with self._lock:
            now = self._clock()
            old = self._data.get(key)
            self._data[key] = _Entry(value, now, compute, now if old is None else old.last_read,
                                     pin or (old is not None and old.pinned))
            self._failed.pop(key, None)
            if len(self._data) > self._maxsize:
                victims = sorted((k for k, v in self._data.items() if not v.pinned),
                                 key=lambda k: self._data[k].last_read)
                for k in victims[: len(self._data) - self._maxsize]:
                    del self._data[k]

    # ------------------------------------------------------------------ 背景刷新
    def due_keys(self) -> list[Hashable]:
        """應該主動重算的鍵：已過 ``refresh_ahead×TTL``，且是釘選鍵或在最近一個 max_stale 內被讀過。"""
        now = self._clock()
        with self._lock:
            return [k for k, e in self._data.items()
                    if now - e.computed_at >= self._ahead * self.ttl_s
                    and (e.pinned or now - e.last_read < self.max_stale_s)
                    and k not in self._inflight]

    def refresh_key(self, key: Hashable) -> bool:
        """背景重算一個鍵；失敗保留舊值並回 False。與讀取路徑共用單飛（同鍵已在算就略過）。"""
        with self._lock:
            e = self._data.get(key)
            if e is None or key in self._inflight:
                return False
            flight = self._inflight[key] = _Flight()
            compute, pin, before = e.compute, e.pinned, e.computed_at
        try:
            self._lead(key, compute, flight, pin)
        except Exception:  # noqa: BLE001 — 背景路徑只記 log（_lead 已記錄並保留舊值）
            return False
        with self._lock:
            now_e = self._data.get(key)
            return now_e is not None and now_e.computed_at != before

    def clear(self) -> None:
        with self._lock:
            self._data.clear()
            self._failed.clear()

    def __len__(self) -> int:
        return len(self._data)
