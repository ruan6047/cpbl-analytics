"""PostgreSQL 連線（psycopg3 connection pool）與 migration runner。"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import psycopg
from psycopg_pool import ConnectionPool

from cpbl.config import settings

_pool: ConnectionPool | None = None

# psycopg_pool 的借池等待預設值；非 API 行程（migrate、訓練、ingest CLI）一律維持它。
DEFAULT_POOL_TIMEOUT_SECONDS = 30.0
_pool_timeout: float = DEFAULT_POOL_TIMEOUT_SECONDS
# API 行程專用的 session 逾時（statement_timeout_ms, lock_timeout_ms）；None＝不設（#353 WP2）。
_api_session: tuple[int, int] | None = None

# 業務日期一律台北。中職**不可能在其他時區比賽**（全史 1990–2026 共 28 個球場全在台灣），
# 所以「今天」只有一個意思。在此之前 session timezone 是 UTC——那不是有人選的，是預設值
# 漏進來的，於是每個呼叫點各自決定日界（DATA-TZ-BOUNDARY-SUCCESSION1）。
#
# ⚠️ 這裡設的是 **per-session**，不是 server-wide：`prod_pg` 是主站 PersonalWebsite 與
# cpbl 共用的單一 `alpha_db`，`ALTER DATABASE/SYSTEM SET timezone` 會波及主站。
#
# ⚠️ 瞬間值不受影響：`timestamptz` 存的是絕對瞬間，session timezone 只改**顯示**與
# `CURRENT_DATE`／`now()::date` 這類日界推導，不會位移任何已存的值。
#
# ⛔ **不變量：借用者不得改動 session timezone。** 借出的連線可以自由開交易、`SET LOCAL`
#    其他 GUC，但**不得** `SET TIME ZONE` / `SET timezone`——那會污染整條連線而不只是
#    這一次借用。實測（2026-08-21，`min_size=1`／`max_size=8` 的實際 pool）：借用者
#    `SET TIME ZONE 'UTC'` 後歸還，同一個 backend PID 再被借出時 `current_setting('TimeZone')`
#    **仍是 UTC**——`configure` 只在**建立連線時**跑一次，psycopg_pool **不會**在 checkout
#    重跑它，也沒有 reset callback 把它撥回來。觀測到的序列（PID 隨機分派）：
#        initial (pid A) Asia/Taipei → borrower (pid B) SET UTC → 下次借到 A 是 Asia/Taipei
#        → 再下次借到 B 仍是 **UTC**
#    也就是說污染會**存活到行程結束**，而且因為輪到哪條連線是隨機的，症狀是**間歇性**的
#    ——那是最難查的形狀。
#    目前 `src/` 與 `tests/` 內除本函式外沒有任何 `SET TIME ZONE` 路徑（DATA-TZ-BOUNDARY-
#    SUCCESSION1 查核者 2026-08-21 獨立實測），故本卡**只留不變量、不加機制**。⚠️ 若日後
#    新增任何會改 session GUC 的消費者，這條不變量就不夠了，屆時需要 pool 的 reset
#    callback 或 checkout 時驗證，而不是靠這段註解。
SESSION_TIMEZONE = "Asia/Taipei"


def _configure(c: psycopg.Connection) -> None:
    """每條新連線都明示 session timezone。

    ⚠️ **刻意用 `configure` 而不是 `options=-c timezone=…`／連線字串參數**：實測
    （2026-08-21）`PGTZ` 環境變數會**蓋掉** startup packet 裡的 `-c timezone=`——
    ``PGTZ=UTC`` 下 ``options="-c timezone=Asia/Taipei"`` 仍得到 ``SHOW timezone = UTC``。
    也就是說寫進連線字串仍然是「靠環境變數」，只是換個方向被靠。`configure` 在連線建立
    **之後**執行 `SET`，是唯一贏得過 env 的位置——這是正確性的前提，不是偏好，所以不能
    留給環境。回歸釘在 ``tests/test_tz_boundary.py``。

    ⚠️ **這裡是 `configure` 不是 `reset`**：它**只在建立連線時跑一次**，借用／歸還都不會
    重跑。因此借用者若自行改了 session timezone，這個函式救不回來——見上方
    :data:`SESSION_TIMEZONE` 的不變量說明。
    """
    c.execute(f"SET TIME ZONE '{SESSION_TIMEZONE}'")
    if _api_session is not None:
        statement_ms, lock_ms = _api_session
        # 值已在 configure_api_timeouts 驗為非負 int，才內插（SET 不吃參數化）。
        c.execute(f"SET statement_timeout = {statement_ms:d}")
        c.execute(f"SET lock_timeout = {lock_ms:d}")
    c.commit()  # configure 回傳前必須結束交易，否則 pool 會丟棄該連線（INTRANS）


def _migrations_dir() -> Path:
    """找 migrations 目錄。容器內套件裝在 site-packages，無法用相對原始碼路徑，
    故依序嘗試：env 指定 → 原始碼布局（dev）→ 容器 /app/migrations → cwd。"""
    candidates = [
        Path(os.environ["CPBL_MIGRATIONS_DIR"]) if os.getenv("CPBL_MIGRATIONS_DIR") else None,
        Path(__file__).resolve().parents[2] / "migrations",  # dev: src/cpbl/db.py → repo 根
        Path("/app/migrations"),                              # 生產容器
        Path.cwd() / "migrations",
    ]
    for c in candidates:
        if c and c.is_dir() and any(c.glob("*.sql")):
            return c
    raise RuntimeError("找不到 migrations 目錄（設 CPBL_MIGRATIONS_DIR 或確認 *.sql 存在）")


def configure_api_timeouts(
    *, pool_timeout_s: float, statement_timeout_ms: int, lock_timeout_ms: int
) -> None:
    """只給 API 行程（``cpbl.api.main`` 的 lifespan）呼叫：借池逾時＋session 逾時（#353 WP2）。

    為什麼：每日鏈 PA 同步持 ACCESS EXCLUSIVE 時，等鎖的讀取會把 8 條連線全占住，其他請求
    （含 ``/api/info``）在借池處排隊到 psycopg_pool 預設 30 秒——外部看來就是無回應（研究 2）。
    逾時讓卡住的請求在數秒內以錯誤結束、連線歸還，而不是整池陪葬。

    ⛔ **作用域是行程**：``migrate()``、``cpbl-train*``、ingest CLI 是各自的行程、從不經過
    API lifespan，合法地會跑超過 statement_timeout，所以本函式不得在 import 時或 CLI 路徑呼叫
    （碼面守衛：``tests/test_api_db_timeouts_353.py``）。``0`` 依 PostgreSQL 語意＝不設限。

    ⚠️ 只對**之後建立**的連線生效（``_configure`` 只在建立連線時跑）：若池已存在就先關掉，
    下一次 :func:`pool` 以新設定重建。仍遵守 :data:`SESSION_TIMEZONE` 的不變量——這裡只加
    逾時，不動時區。
    """
    global _pool, _pool_timeout, _api_session
    if not pool_timeout_s > 0:
        raise ValueError(f"pool_timeout_s 必須 > 0：{pool_timeout_s!r}")
    for name, value in (("statement_timeout_ms", statement_timeout_ms),
                        ("lock_timeout_ms", lock_timeout_ms)):
        if not isinstance(value, int) or value < 0:
            raise ValueError(f"{name} 必須是非負整數（毫秒）：{value!r}")
    if _pool is not None:
        _pool.close()
        _pool = None
    _pool_timeout = float(pool_timeout_s)
    _api_session = (statement_timeout_ms, lock_timeout_ms)


def pool() -> ConnectionPool:
    """惰性建立全域連線池。"""
    global _pool
    if _pool is None:
        _pool = ConnectionPool(
            settings.database_url, min_size=1, max_size=8, open=True, configure=_configure,
            timeout=_pool_timeout,
        )
    return _pool


@contextmanager
def conn() -> Iterator[psycopg.Connection]:
    """從池取一條連線；離開時自動 commit / rollback。"""
    with pool().connection() as c:
        yield c


def migrate() -> list[str]:
    """依序套用 migrations/*.sql（冪等；皆為 IF NOT EXISTS）。"""
    applied: list[str] = []
    files = sorted(_migrations_dir().glob("*.sql"))
    with conn() as c:
        for f in files:
            c.execute(f.read_text(encoding="utf-8"))  # type: ignore[arg-type]
            applied.append(f.name)
    return applied
