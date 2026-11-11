"""#448：未快取即時端點的「到達後合併」[post-arrival request coalescing]。

V2（兩倍請求量）重放裡，8 支⛔ 不裝快取的端點（``response_cache`` 模組說明的排除清單＋
``playoffs/overview``）在爆量時同一組路徑＋參數同時被算幾十次，把 8 條連線的池借光
（#442 V2：PoolTimeout 50／QueryCanceled 3）。本模組讓**同一鍵同時最多一個計算在跑**。

**刻意行為（需求方核定的新鮮度判準 F1，#448 規劃確認）**：

- 計算進行中抵達的請求，⛔ 不拿那一次計算的結果（那次的 DB／Redis 讀取在它抵達**前**就開始了）；
  它排進「下一批」，等這次結束後下一批才開始，並在開始時才讀資料。所以每個請求拿到的資料，
  讀取一定在該請求抵達之後才開始——API 層增加的資料延遲是 0。
- 一批算完就把結果交給該批所有成員然後丟掉，⛔ 不跨請求保留任何回應（沒有 TTL、沒有失效邏輯）；
  記憶體只有進行中的那一份。
- 鍵＝（模組, 函式, 解析後的全部參數）＝完整路徑＋query；不同鍵互不阻擋。
- 失敗不連坐：一批的計算拋出例外，或 ``HTTPException`` 狀態碼 ≥ 500，⛔ 不直接交給同批成員；
  每個成員各自重新排入下一批**一次**，第二次仍失敗才回錯。狀態碼 < 500（如 404）是正常結果，照常共用。

**⛔ 不得推出什麼**：

- 這⛔ 不是一般的單飛 [single-flight]（跟隨進行中的計算會拿到抵達前就開始讀的資料，最多舊一次計算時間，
  正是需求方否決的「增加數秒」）。⛔ 不要為了省等待把「加入進行中的那一批」加回來。
- 這⛔ 不是快取：⛔ 不要在這裡加 TTL 或保留最近結果；要快取的端點走 :mod:`cpbl.api.response_cache`，
  而這 8 支依 #442／#448 裁定不裝。
- 跟隨者的等待最多約「上一批剩餘時間＋下一批全程」；它佔著一條 anyio 工作執行緒在等（R3），
  ⛔ 不設等待逾時（逾時就會產生新的錯誤回應）。

接線：各 router 把端點本體搬進以 :func:`coalesced` 裝飾的內部函式（FastAPI 看到的端點函式本身不變，
所以路由、參數、OpenAPI 與 ``response_cache`` 的「未裝 @cached」守門都不變）；
``games/*/facts`` 只包 payload 計算，``Cache-Control`` 仍由每個請求依共用 payload 自己設。
"""

from __future__ import annotations

import functools
import inspect
import threading
from collections.abc import Callable, Hashable
from typing import Any

from fastapi import HTTPException

from cpbl.api.response_cache import _freeze, _resolved_kwargs


class _Batch:
    __slots__ = ("done", "ok", "value", "error")

    def __init__(self) -> None:
        self.done = threading.Event()
        self.ok = False
        self.value: Any = None
        self.error: BaseException | None = None


class _State:
    __slots__ = ("running", "pending")

    def __init__(self) -> None:
        self.running: _Batch | None = None   # 計算中的那一批（其成員都在計算開始前抵達）
        self.pending: _Batch | None = None   # 計算中抵達者組成的下一批（尚未開始讀資料）


class _Retry(Exception):
    """內部訊號：同批計算失敗，本請求重新排入下一批（每個請求最多一次）。"""


def _retryable(e: BaseException) -> bool:
    if isinstance(e, HTTPException):
        return e.status_code >= 500
    return True


class Coalescer:
    """執行緒安全的到達後合併器；同步端點在 anyio 工作執行緒中呼叫 :meth:`run`。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._states: dict[Hashable, _State] = {}

    def inflight_keys(self) -> int:
        with self._lock:
            return len(self._states)

    def run(self, key: Hashable, fn: Callable[[], Any]) -> Any:
        try:
            return self._run_once(key, fn)
        except _Retry:
            return self._run_once(key, fn, final=True)

    def _run_once(self, key: Hashable, fn: Callable[[], Any], *, final: bool = False) -> Any:
        prev: _Batch | None = None
        with self._lock:
            st = self._states.get(key)
            if st is None:
                st = self._states[key] = _State()
            if st.running is None:
                batch = st.running = _Batch()
                role = "lead"
            elif st.pending is None:
                prev, batch = st.running, _Batch()
                st.pending = batch
                role = "next"
            else:
                batch = st.pending
                role = "follow"
        if role == "next":
            # 等上一批結束；結束時上一批的領頭會把本批升為 running（成員名單在此刻封閉），
            # 之後才開始計算，所以本批每個成員都在讀取開始前抵達（F1）。
            assert prev is not None
            prev.done.wait()
            role = "lead"
        if role == "lead":
            return self._compute(key, st, batch, fn)
        batch.done.wait()
        if batch.ok:
            return batch.value
        assert batch.error is not None
        if _retryable(batch.error) and not final:
            raise _Retry
        raise batch.error

    def _compute(self, key: Hashable, st: _State, batch: _Batch, fn: Callable[[], Any]) -> Any:
        try:
            batch.value = fn()
            batch.ok = True
            return batch.value
        except BaseException as e:
            batch.error = e
            raise
        finally:
            with self._lock:
                if st.pending is not None:
                    st.running, st.pending = st.pending, None
                else:
                    st.running = None
                    self._states.pop(key, None)
            # 結果只由 batch 物件持有；成員取走後 batch 隨之釋放，⛔ 不留存。
            batch.done.set()


COALESCER = Coalescer()


def _key(wrapper: Callable[..., Any], args: tuple, kwargs: dict) -> tuple[Hashable, dict[str, Any]]:
    """（鍵, 解析後參數）：鍵＝（模組, 函式, 解析後的全部參數，含 ``Query(...)`` 預設值）。"""
    func, sig = wrapper.__wrapped__, wrapper.coalesce_sig  # type: ignore[attr-defined]
    kw = _resolved_kwargs(sig, args, kwargs)
    return (func.__module__, func.__qualname__, _freeze(kw)), kw


def coalesced(func: Callable[..., Any]) -> Callable[..., Any]:
    """把同步計算包上到達後合併。``wrapper.compute`` 是實際計算（預設＝原函式；測試可替換）。"""

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        key, kw = _key(wrapper, args, kwargs)
        return COALESCER.run(key, lambda: wrapper.compute(**kw))  # type: ignore[attr-defined]

    wrapper.coalesce_sig = inspect.signature(func, eval_str=True)  # type: ignore[attr-defined]
    wrapper.compute = func  # type: ignore[attr-defined]
    wrapper.coalesced = True  # type: ignore[attr-defined]
    return wrapper
