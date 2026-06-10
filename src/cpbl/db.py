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
        _pool = ConnectionPool(settings.database_url, min_size=1, max_size=8, open=True)
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
