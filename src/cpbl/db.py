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

# 業務日期一律台北。中職**不可能在其他時區比賽**（全史 1990–2026 共 28 個球場全在台灣），
# 所以「今天」只有一個意思。在此之前 session timezone 是 UTC——那不是有人選的，是預設值
# 漏進來的，於是每個呼叫點各自決定日界（DATA-TZ-BOUNDARY-SUCCESSION1）。
#
# ⚠️ 這裡設的是 **per-session**，不是 server-wide：`prod_pg` 是主站 PersonalWebsite 與
# cpbl 共用的單一 `alpha_db`，`ALTER DATABASE/SYSTEM SET timezone` 會波及主站。
#
# ⚠️ 瞬間值不受影響：`timestamptz` 存的是絕對瞬間，session timezone 只改**顯示**與
# `CURRENT_DATE`／`now()::date` 這類日界推導，不會位移任何已存的值。
SESSION_TIMEZONE = "Asia/Taipei"


def _configure(c: psycopg.Connection) -> None:
    """每條新連線都明示 session timezone。

    ⚠️ **刻意用 `configure` 而不是 `options=-c timezone=…`／連線字串參數**：實測
    （2026-08-21）`PGTZ` 環境變數會**蓋掉** startup packet 裡的 `-c timezone=`——
    ``PGTZ=UTC`` 下 ``options="-c timezone=Asia/Taipei"`` 仍得到 ``SHOW timezone = UTC``。
    也就是說寫進連線字串仍然是「靠環境變數」，只是換個方向被靠。`configure` 在連線建立
    **之後**執行 `SET`，是唯一贏得過 env 的位置——這是正確性的前提，不是偏好，所以不能
    留給環境。回歸釘在 ``tests/test_tz_boundary.py``。
    """
    c.execute(f"SET TIME ZONE '{SESSION_TIMEZONE}'")
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


def pool() -> ConnectionPool:
    """惰性建立全域連線池。"""
    global _pool
    if _pool is None:
        _pool = ConnectionPool(
            settings.database_url, min_size=1, max_size=8, open=True, configure=_configure
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
