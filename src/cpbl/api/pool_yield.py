"""背景工作在池忙時讓路（#442 PLAN v4 G4）。

``/api/info`` 的背景重算（每 60 s 借 1 條連線跑 14 個查詢）與回應快取的背景刷新，都和請求共用
同一個 8 條的池。爆量時它們再去搶連線，就是在輕端點已經排隊時再多占一條；``/api/info`` 若自己也
PoolTimeout，還會改成每 5 s 重試，形成正回饋（#442 PLAN v4 §0.2）。

本模組只**讀** ``pool().get_stats()``：有請求在等池（``requests_waiting > 0``）或沒有可用連線
（``pool_available == 0`` 且池已滿）就判定為忙，背景工作延後再試。

界線（⛔ 不得推出的事）：

- 只是 API 行程內的時機判斷；⛔ 不改 pool 設定、``/api/info`` 的 TTL 60 s 與回應契約。
- 等待有上限 :data:`MAX_YIELD_S`：池一直忙也不無限延後，到上限就照常執行（退化回沒有讓路的行為）。
- 池尚未建立時（行程剛啟動、測試）視為不忙；⛔ 不為了讀狀態而建立池。
"""

from __future__ import annotations

import threading
import time

MAX_YIELD_S = 30.0
POLL_S = 0.5


def pool_busy() -> bool:
    from cpbl import db

    p = db._pool  # 只讀既有的池；None＝尚未建立（⛔ 不呼叫 db.pool() 去建立）
    if p is None or getattr(p, "closed", False):
        return False  # 未開啟／已關閉的池不會借出連線，談不上「忙」（測試的不可達池即是未開啟）
    try:
        s = p.get_stats()
    except Exception:  # noqa: BLE001 — 讀不到狀態就當不忙，維持原行為
        return False
    if (s.get("requests_waiting") or 0) > 0:
        return True
    size, avail, mx = s.get("pool_size") or 0, s.get("pool_available") or 0, s.get("pool_max") or 0
    return avail == 0 and size >= mx > 0


def wait_until_idle(stop: threading.Event | None = None, *, max_wait_s: float = MAX_YIELD_S,
                    poll_s: float = POLL_S) -> float:
    """池忙就等，直到不忙、``stop`` 被設、或等滿 ``max_wait_s``；回傳實際等了幾秒。"""
    t0 = time.monotonic()
    while pool_busy():
        waited = time.monotonic() - t0
        if waited >= max_wait_s:
            break
        if stop is not None:
            if stop.wait(poll_s):
                break
        else:
            time.sleep(poll_s)
    return time.monotonic() - t0
