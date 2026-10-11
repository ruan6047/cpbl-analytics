from types import SimpleNamespace

import pytest

from cpbl import db
from cpbl.ingest import lineup_announcements
from cpbl.ingest import run_live_game_worker as cli


def setup_cli(monkeypatch, errors=None):
    seen = {"source_closed": False, "redis_closed": False, "pool_closed": False}

    class Source:
        def fetch_schedule(self, *args):
            raise AssertionError("real fetch forbidden")

        def fetch_game(self, *args):
            raise AssertionError("real fetch forbidden")

        def close(self):
            seen["source_closed"] = True

    class Redis:
        def close(self):
            seen["redis_closed"] = True

    class Pool:
        def close(self):
            seen["pool_closed"] = True

    class Worker:
        def __init__(self, **kwargs):
            seen["worker"] = kwargs

        def run_cycle(self, now):
            return {"state": "ok", "announcement_errors": errors or []}

    monkeypatch.setattr(cli.settings, "live_game_worker_enabled", True)
    monkeypatch.setattr(cli.settings, "redis_url", "redis://fixture.invalid/0")
    monkeypatch.setattr(cli.settings, "live_game_postseason_kinds", "E,C")
    monkeypatch.setattr(cli, "StatsLiveSource", Source)
    monkeypatch.setattr(cli.redis.Redis, "from_url", lambda *args, **kwargs: Redis())
    monkeypatch.setattr(cli, "RedisLiveGameCache", lambda *args, **kwargs: SimpleNamespace())
    monkeypatch.setattr(cli, "LiveGameWorker", Worker)
    monkeypatch.setattr(cli.signal, "signal", lambda *args: None)
    monkeypatch.setattr(db, "_pool", Pool())
    return seen


def test_default_cli_does_not_enable_persistence_or_touch_pool(monkeypatch):
    seen = setup_cli(monkeypatch)
    cli.main(["--once"])
    assert seen["worker"].get("observation_sink") is None and not seen["pool_closed"]
    assert seen["source_closed"] and seen["redis_closed"]


def test_explicit_local_persistence_injects_repository_and_closes_pool(monkeypatch):
    seen = setup_cli(monkeypatch)
    cli.main(["--once", "--persist-announcements"])
    assert seen["worker"]["observation_sink"] is lineup_announcements.observe
    assert seen["pool_closed"] and seen["source_closed"] and seen["redis_closed"]


def test_persistence_once_does_not_report_success_when_save_failed(monkeypatch):
    seen = setup_cli(monkeypatch, errors=[{"game_id": "2026-E-4", "error_type": "FixtureError"}])
    with pytest.raises(SystemExit) as exc:
        cli.main(["--once", "--persist-announcements"])
    assert exc.value.code == 1
    assert seen["pool_closed"] and seen["source_closed"] and seen["redis_closed"]


def test_persistence_help_exits_before_any_source_or_connection(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("side effect reached")

    monkeypatch.setattr(cli, "StatsLiveSource", forbidden)
    monkeypatch.setattr(cli.redis.Redis, "from_url", forbidden)
    with pytest.raises(SystemExit) as exc:
        cli.main(["--help"])
    assert exc.value.code == 0
