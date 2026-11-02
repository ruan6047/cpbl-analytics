"""#413 CI 最小資料基底：載入器的目標守衛與 conftest 的標記閘門（不需 DB）。"""

from __future__ import annotations

import os
from types import SimpleNamespace

import ci_base
import pytest

from cpbl import db
from cpbl.config import Settings, settings
from tests import conftest

THROWAWAY = "postgresql://cpbl:cpbl@localhost:55413/cpbl_ci_base"


# ------------------------------------------------------------------ 載入器拒絕三種目標

@pytest.mark.parametrize("dsn", [
    Settings.model_fields["database_url"].default,          # 設定預設值＝本機 5433 主庫
    "postgresql://cpbl:cpbl@127.0.0.1:5433/cpbl",           # 同一台的另一種寫法
    "postgresql://other:pw@localhost:5433/cpbl?connect_timeout=3",
])
def test_refuses_the_settings_default_main_db(dsn, monkeypatch, tmp_path):
    monkeypatch.setattr(ci_base, "ROOT", tmp_path)          # 沒有 .env：只剩設定預設值這一條
    with pytest.raises(ci_base.Refused, match="主庫"):
        ci_base.refuse_target(dsn, games_rows=None)


def test_refuses_the_dotenv_main_db(monkeypatch, tmp_path):
    (tmp_path / ".env").write_text("FOO=1\nDATABASE_URL='postgresql://u:p@localhost:6011/realdata'\n",
                                   encoding="utf-8")
    monkeypatch.setattr(ci_base, "ROOT", tmp_path)
    with pytest.raises(ci_base.Refused, match="主庫"):
        ci_base.refuse_target("postgresql://x:y@127.0.0.1:6011/realdata", games_rows=None)
    ci_base.refuse_target("postgresql://x:y@127.0.0.1:6011/other", games_rows=0)   # 同埠不同庫照常


def test_refuses_a_target_whose_games_table_has_rows(monkeypatch, tmp_path):
    monkeypatch.setattr(ci_base, "ROOT", tmp_path)
    with pytest.raises(ci_base.Refused, match="已有 7 列"):
        ci_base.refuse_target(THROWAWAY, games_rows=7)
    ci_base.refuse_target(THROWAWAY, games_rows=0)          # 空的拋棄式庫才放行
    ci_base.refuse_target(THROWAWAY, games_rows=None)


def test_cli_load_exits_nonzero_before_touching_the_main_db(monkeypatch, tmp_path, capsys):
    """拒絕發生在連線之前：目標是主庫時 CLI 直接回 3，不會連上去。"""
    monkeypatch.setattr(ci_base, "ROOT", tmp_path)

    def _no_connect(*_a, **_k):
        raise AssertionError("拒絕前不得連線")

    monkeypatch.setattr("psycopg.connect", _no_connect)
    assert ci_base.main(["load", "--target-dsn", Settings.model_fields["database_url"].default]) == 3
    assert "REFUSED" in capsys.readouterr().err


# ------------------------------------------------------------------ conftest 標記閘門

def _config(worker: str | None) -> SimpleNamespace:
    return SimpleNamespace(workerinput={"workerid": worker} if worker else None)


@pytest.fixture
def _restore_gate(monkeypatch):
    monkeypatch.setattr(settings, "database_url", settings.database_url)
    monkeypatch.setattr(db, "_pool", db._pool)
    monkeypatch.setenv("DATABASE_URL", os.environ.get("DATABASE_URL", ""))
    monkeypatch.setattr(ci_base, "_ACTIVE", ci_base._ACTIVE)


@pytest.mark.parametrize("worker", [None, "gw3"])
def test_gate_without_marker_changes_nothing(worker, monkeypatch, _restore_gate):
    """沒有標記（本機正式庫、CI 舊形狀）：環境、settings、連線池都不動，也不複製。"""
    monkeypatch.setattr(conftest.ci_base, "marker_of", lambda dsn, **_: None)
    monkeypatch.setattr(conftest, "_clone_database", lambda *a: pytest.fail("不得複製"))
    before = (dict(os.environ), settings.database_url, db._pool)
    conftest._per_worker_ci_base(_config(worker))
    assert (dict(os.environ), settings.database_url, db._pool) == before
    assert ci_base.active() is False


def test_gate_with_marker_outside_xdist_only_flags_active(monkeypatch, _restore_gate):
    monkeypatch.setattr(conftest.ci_base, "marker_of", lambda dsn, **_: "cpbl-ci-base x")
    monkeypatch.setattr(conftest, "_clone_database", lambda *a: pytest.fail("單行程不複製"))
    before = (dict(os.environ), settings.database_url)
    conftest._per_worker_ci_base(_config(None))
    assert (dict(os.environ), settings.database_url) == before
    assert ci_base.active() is True


def test_gate_with_marker_in_worker_switches_to_its_own_clone(monkeypatch, _restore_gate):
    monkeypatch.setattr(settings, "database_url", THROWAWAY)
    monkeypatch.setattr(conftest.ci_base, "marker_of", lambda dsn, **_: "cpbl-ci-base x")
    calls, closed = [], []
    monkeypatch.setattr(conftest, "_clone_database", lambda *a: calls.append(a))
    # 替身池：⛔ 不能讓閘門關掉這個 worker 真正在用的全域池（monkeypatch 還原的會是一個已關閉的池，
    # 同 worker 之後的 DB 測試全數 PoolClosed）。
    monkeypatch.setattr(db, "_pool", SimpleNamespace(close=lambda: closed.append(True)))
    conftest._per_worker_ci_base(_config("gw2"))
    assert calls == [(THROWAWAY, "cpbl_ci_base", "cpbl_ci_base_gw2")]
    assert settings.database_url.endswith("/cpbl_ci_base_gw2") or "dbname=cpbl_ci_base_gw2" in settings.database_url
    assert os.environ["DATABASE_URL"] == settings.database_url
    assert closed == [True] and db._pool is None, "舊池（連著模板庫）要關掉，之後惰性重建到複本"
    assert ci_base.active() is True


# ------------------------------------------------------------------ 選取內容的紅線

def test_selection_never_includes_sentinel_keys():
    """哨兵年份 1900／2099 與 2018/D/110 由測試自行寫入，基底收進來就會撞。"""
    assert all(y not in (1900, 2099) for y, _k, _s, _w in ci_base.GAMES)
    assert (2018, "D", 110) not in {(y, k, s) for y, k, s, _w in ci_base.GAMES}
    games = next(t for t in ci_base.TABLES if t.name == "games")
    assert "1900" in games.where and "2099" in games.where


def test_committed_manifest_matches_its_files():
    """repo 內的基底自洽：每個 CSV 的 sha256／位元組數與 manifest 一致，總量不超過上限。"""
    manifest = ci_base.read_manifest()
    total = 0
    for entry in manifest["tables"]:
        data = (ci_base.FIXTURE_DIR / entry["file"]).read_bytes()
        assert len(data) == entry["bytes"] and ci_base._sha256(data) == entry["sha256"], entry["file"]
        total += len(data)
    total += (ci_base.FIXTURE_DIR / ci_base.MANIFEST).stat().st_size
    assert total <= ci_base.SIZE_LIMIT_BYTES
    assert {p.name for p in ci_base.FIXTURE_DIR.iterdir()} == \
        {ci_base.MANIFEST, *(e["file"] for e in manifest["tables"])}
