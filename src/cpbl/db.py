"""PostgreSQL 連線（psycopg3 connection pool）與 migration runner。"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import psycopg
from psycopg_pool import ConnectionPool

from cpbl.config import settings

_pool: ConnectionPool | None = None

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


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
    files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    with conn() as c:
        for f in files:
            c.execute(f.read_text(encoding="utf-8"))  # type: ignore[arg-type]
            applied.append(f.name)
    return applied
