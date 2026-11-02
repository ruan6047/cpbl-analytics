"""``cpbl.db.migrate`` 的套用記錄：跳過已記錄、內容變了重跑並告警、force 全量、DROP SCHEMA 後重來。

跑在 ``CPBL_ISOLATED_TEST_DSN`` 指的拋棄式庫（未設即 skip；CI 由 Postgres service 提供，xdist 下 conftest
已按 worker 拆庫）。結束時 ``DROP SCHEMA cpbl CASCADE`` 還原成空庫，與其他隔離測試檔的前提一致。
"""

from __future__ import annotations

import logging
import os

import psycopg
import pytest
from psycopg_pool import ConnectionPool

from cpbl import db


@pytest.fixture
def isolated_db(monkeypatch):
    dsn = os.environ.get("CPBL_ISOLATED_TEST_DSN")
    if not dsn:
        pytest.skip("未設 CPBL_ISOLATED_TEST_DSN（自行擁有的隔離 Postgres）")
    with psycopg.connect(dsn, autocommit=True) as c:
        if c.execute("SELECT to_regclass('cpbl.games')").fetchone()[0] is not None:
            pytest.fail("隔離庫已有 cpbl.games：拒絕在疑似真實資料庫上跑 migration")
    pool = ConnectionPool(dsn, min_size=0, max_size=2, open=True, configure=db._configure)
    monkeypatch.setattr(db, "_pool", pool)
    monkeypatch.delenv("CPBL_MIGRATE_FORCE", raising=False)
    try:
        yield dsn
    finally:
        pool.close()
        with psycopg.connect(dsn, autocommit=True) as c:
            c.execute("DROP SCHEMA IF EXISTS cpbl CASCADE")


def _recorded(dsn: str) -> dict[str, str]:
    with psycopg.connect(dsn) as c:
        return dict(c.execute("SELECT filename, checksum FROM cpbl.schema_migrations").fetchall())


def test_first_run_applies_everything_then_skips(isolated_db: str) -> None:
    files = sorted(p.name for p in db._migrations_dir().glob("*.sql"))
    first = db.migrate()
    assert first == files, "空庫第一次必須照序全跑"
    assert set(_recorded(isolated_db)) == set(files)
    second = db.migrate()
    assert second == [], "全部已記錄且內容未變 → 一支都不重跑"


def test_changed_checksum_reruns_that_file_with_a_warning(
    isolated_db: str, caplog: pytest.LogCaptureFixture
) -> None:
    db.migrate()
    with psycopg.connect(isolated_db, autocommit=True) as c:
        c.execute("UPDATE cpbl.schema_migrations SET checksum = 'stale' WHERE filename = '001_init.sql'")
    with caplog.at_level(logging.WARNING, logger="cpbl.db"):
        rerun = db.migrate()
    assert rerun == ["001_init.sql"]
    assert any("001_init.sql" in rec.getMessage() for rec in caplog.records)
    assert _recorded(isolated_db)["001_init.sql"] != "stale"


def test_force_reruns_all_and_is_idempotent(isolated_db: str, monkeypatch) -> None:
    files = db.migrate()
    assert db.migrate(force=True) == files, "force 全量重跑：冪等檔重跑無害，記錄更新"
    monkeypatch.setenv("CPBL_MIGRATE_FORCE", "1")
    assert db.migrate() == files, "環境變數 CPBL_MIGRATE_FORCE=1 等同 force"
    monkeypatch.delenv("CPBL_MIGRATE_FORCE")
    assert db.migrate() == []


def test_dropping_the_schema_also_forgets_the_records(isolated_db: str) -> None:
    files = db.migrate()
    with psycopg.connect(isolated_db, autocommit=True) as c:
        c.execute("DROP SCHEMA cpbl CASCADE")
    assert db.migrate() == files, "記錄表與 schema 同生共滅：schema 重來，記錄也重來"
