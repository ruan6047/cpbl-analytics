"""#353 WP2：API 讀端逾時只在 API 行程（uvicorn lifespan）生效。

背景（研究 2 事實）：每日鏈第 3 步 PA 同步持 ACCESS EXCLUSIVE 約 7 分 20 秒，API 連線池 8 條
全被等鎖的查詢占滿，連 ``/api/info`` 都等不到連線。WP2 讓一條卡住的路徑快速失敗、不拖垮整個池：
借池逾時、session ``statement_timeout``、session ``lock_timeout``。

⛔ ``migrate()``、``cpbl-train*``、ingest CLI 是不同行程、合法地會跑超過 4 秒，不得吃到這些值——
所以設定點是 ``cpbl.api.main`` 的 lifespan（只有 uvicorn 起 app 時才跑），不是 import 時。

本檔不需要 DB：以假連線記下 ``_configure`` 送出的 SQL、以 monkeypatch 隔離全域池。
鎖注入下池不耗盡的行為證據在拋棄式 DB 上跑（``~/.wf-evidence/cpbl-analytics/353/exec-1/``）。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from cpbl import db
from cpbl.config import settings


class _FakeConn:
    def __init__(self) -> None:
        self.sql: list[str] = []
        self.committed = False

    def execute(self, sql: str) -> None:
        self.sql.append(sql)

    def commit(self) -> None:
        self.committed = True


@pytest.fixture
def isolated_db_state(monkeypatch):
    """configure_api_timeouts 會改模組全域；monkeypatch 讓每個測試結束後還原。"""
    monkeypatch.setattr(db, "_pool", None)
    monkeypatch.setattr(db, "_api_session", None)
    monkeypatch.setattr(db, "_pool_timeout", db.DEFAULT_POOL_TIMEOUT_SECONDS)


def test_default_session_has_only_timezone(isolated_db_state) -> None:
    """未經 API lifespan（CLI、migrate、訓練）：連線只設時區，沒有任何逾時。"""
    c = _FakeConn()
    db._configure(c)
    assert c.sql == [f"SET TIME ZONE '{db.SESSION_TIMEZONE}'"]
    assert c.committed
    assert db._pool_timeout == 30.0, "非 API 行程的借池等待維持 psycopg_pool 預設 30s"


def test_api_timeouts_are_applied_to_new_connections(isolated_db_state) -> None:
    db.configure_api_timeouts(pool_timeout_s=3.0, statement_timeout_ms=4000, lock_timeout_ms=2000)
    c = _FakeConn()
    db._configure(c)
    assert c.sql == [
        f"SET TIME ZONE '{db.SESSION_TIMEZONE}'",
        "SET statement_timeout = 4000",
        "SET lock_timeout = 2000",
    ]
    assert c.committed, "configure 回傳前必須結束交易，否則 pool 會丟棄該連線"
    assert db._pool_timeout == 3.0


def test_configure_api_timeouts_discards_a_pool_created_before_it(isolated_db_state, monkeypatch):
    """已建立的池是用舊設定開的連線；必須關掉重建，否則逾時對既有連線不生效。"""
    closed: list[bool] = []

    class _Pool:
        def close(self) -> None:
            closed.append(True)

    monkeypatch.setattr(db, "_pool", _Pool())
    db.configure_api_timeouts(pool_timeout_s=3.0, statement_timeout_ms=4000, lock_timeout_ms=2000)
    assert closed == [True]
    assert db._pool is None


@pytest.mark.parametrize("bad", [
    {"pool_timeout_s": 0, "statement_timeout_ms": 4000, "lock_timeout_ms": 2000},
    {"pool_timeout_s": 3.0, "statement_timeout_ms": -1, "lock_timeout_ms": 2000},
    {"pool_timeout_s": 3.0, "statement_timeout_ms": 4000, "lock_timeout_ms": -5},
])
def test_configure_api_timeouts_rejects_invalid_values(isolated_db_state, bad) -> None:
    with pytest.raises(ValueError):
        db.configure_api_timeouts(**bad)


def test_pool_uses_configured_checkout_timeout(isolated_db_state, monkeypatch) -> None:
    seen: dict = {}

    class _Pool:
        def __init__(self, *args, **kwargs) -> None:
            seen.update(kwargs)

    monkeypatch.setattr(db, "ConnectionPool", _Pool)
    db.configure_api_timeouts(pool_timeout_s=3.0, statement_timeout_ms=4000, lock_timeout_ms=2000)
    db.pool()
    assert seen["timeout"] == 3.0
    assert seen["max_size"] == 8, "WP2 不加大池（規劃 §2.2）"


def test_api_lifespan_applies_settings_and_cli_import_does_not(monkeypatch) -> None:
    """只有 uvicorn 起 app（lifespan）才套逾時；單純 import app（測試、腳本）不套。"""
    calls: list[dict] = []
    monkeypatch.setattr(db, "configure_api_timeouts", lambda **kw: calls.append(kw))
    from cpbl.api import main
    from cpbl.api.routers import info

    monkeypatch.setattr(info, "start_cache", lambda: None, raising=False)
    monkeypatch.setattr(info, "stop_cache", lambda: None, raising=False)

    assert calls == [], "import cpbl.api.main 不得套 API 逾時"
    with TestClient(main.app):
        pass
    assert calls == [{
        "pool_timeout_s": settings.api_db_pool_timeout_seconds,
        "statement_timeout_ms": settings.api_db_statement_timeout_ms,
        "lock_timeout_ms": settings.api_db_lock_timeout_ms,
    }]


def test_migrate_and_cli_entrypoints_never_call_api_timeouts() -> None:
    """碼面守衛：設定點只在 API lifespan；migrate／訓練／ingest 不得呼叫。"""
    from pathlib import Path

    root = Path(__file__).parents[1] / "src" / "cpbl"
    callers = sorted(
        str(p.relative_to(root)) for p in root.rglob("*.py")
        if "configure_api_timeouts(" in p.read_text(encoding="utf-8") and p.name != "db.py"
    )
    assert callers == ["api/main.py"], callers


def test_default_worst_case_stays_under_the_5s_acceptance_bound() -> None:
    """單一請求最壞＝借池等待＋單一語句（lock 等待含在語句內）；必須 < 5s（#353 驗收）。"""
    worst = settings.api_db_pool_timeout_seconds + settings.api_db_statement_timeout_ms / 1000
    assert worst < 5.0, worst
    assert 0 < settings.api_db_lock_timeout_ms <= settings.api_db_statement_timeout_ms
