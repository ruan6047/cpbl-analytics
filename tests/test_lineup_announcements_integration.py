"""Opt-in 僅新租用cpbl238_a8；全套pytest不借共享DB做公告寫入。"""

from __future__ import annotations

import os
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit

import pytest
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from test_lineup_announcements import raw_game

from cpbl import db
from cpbl.ingest.lineup_announcements import observe
from cpbl.ingest.live_game_worker import LiveGameWorker, RedisLiveGameCache
from cpbl.reports.announcements import select
from cpbl.reports.readers import lineup_revisions

T0 = datetime(2026, 10, 12, 8, 30, tzinfo=UTC)


@pytest.fixture
def isolated_pool(monkeypatch):
    dsn = os.environ.get("CPBL238_A8_TEST_DSN")
    if not dsn:
        pytest.skip("A8 dedicated DB lease/DSN not provided")
    details = conninfo_to_dict(dsn)
    if (details.get("host"), details.get("port"), details.get("dbname"), details.get("user")) != (
        "127.0.0.1",
        "15438",
        "cpbl238_a8",
        "cpbl",
    ):
        pytest.fail("A8 test DSN outside dedicated resource", pytrace=False)

    def configure(c):
        db._configure(c)
        c.execute("SET statement_timeout='5s'")
        c.execute("SET lock_timeout='1s'")
        c.commit()

    with ConnectionPool(
        dsn,
        min_size=0,
        max_size=1,
        timeout=3,
        reconnect_timeout=0,
        kwargs={"connect_timeout": 3},
        configure=configure,
    ) as pool:
        monkeypatch.setattr(db, "_pool", pool)
        with db.conn() as c:
            assert c.execute("SELECT current_database(),current_user").fetchone() == (
                "cpbl238_a8",
                "cpbl",
            )
            assert (
                c.execute(
                    "SELECT count(*) FROM information_schema.tables WHERE table_schema='cpbl'"
                ).fetchone()[0]
                == 1
            )
        yield pool
    assert pool.closed


def game(sno=4, status="SCHEDULED"):
    raw = raw_game(status)
    raw.update(GameId=f"2026-E-{sno}", GameSno=sno)
    return raw


def rows(sno):
    with db.conn() as c, c.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "SELECT * FROM cpbl.game_lineup_announcement_revisions WHERE year=%s AND kind_code=%s AND game_sno=%s ORDER BY fetched_at",
            (2026, "E", sno),
        )
        return cur.fetchall()


def test_real_revision_reappearance_and_historical_reader_pin(isolated_pool):
    v1 = game()
    v2 = deepcopy(v1)
    v2["Visiting"]["Hitters"][0]["HitterAcnt"] = "0000000099"
    sequence = [v1, v1, v2, v1, game(status="START"), v2]
    for minute, raw in enumerate(sequence):
        observe("2026-E-4", raw, T0 + timedelta(minutes=minute))
    actual = rows(4)
    assert len(actual) == 5
    assert actual[0]["fetched_at"] == T0 and actual[0]["last_seen_at"] == T0 + timedelta(minutes=1)
    assert actual[2]["content_hash"] == actual[0]["content_hash"]
    assert actual[3]["raw_status"] == "START"
    target = {
        "year": 2026,
        "kind_code": "E",
        "game_sno": 4,
        "away_team_code": "ACN011",
        "home_team_code": "ADD011",
    }
    with db.conn() as c, c.cursor() as cur:
        read = lineup_revisions(cur, 2026, [target])
    picked = select(read, [], target)
    assert picked["status"] == "announced"
    assert picked["observed_at"] == (T0 + timedelta(minutes=3)).isoformat()
    assert picked["team_evidence"]["ACN011"]["first_content_at"] == T0.isoformat()
    assert (
        picked["team_evidence"]["ACN011"]["first_started_at"]
        == (T0 + timedelta(minutes=4)).isoformat()
    )


def test_real_natural_key_conflict_and_clock_rollback_preserve_old_evidence(isolated_pool):
    v1 = game(5)
    observe("2026-E-5", v1, T0)
    observe("2026-E-5", v1, T0 + timedelta(minutes=2))
    before = rows(5)
    changed = game(5, "START")
    with pytest.raises(ValueError, match="conflict"):
        observe("2026-E-5", changed, T0)
    with pytest.raises(ValueError, match="backwards"):
        observe("2026-E-5", changed, T0 + timedelta(minutes=1))
    assert rows(5) == before
    assert observe("2026-E-5", v1, T0)["action"] == "replayed"
    assert rows(5) == before


def test_real_redis_fake_source_sink_preserves_cache_and_releases_owner_lock(isolated_pool):
    import redis

    url = os.environ.get("REDIS_URL", "")
    parsed = urlsplit(url)
    if (
        parsed.scheme != "redis"
        or parsed.hostname != "127.0.0.1"
        or parsed.port != 16389
        or parsed.path not in ("", "/0")
    ):
        pytest.fail("A8 Redis outside dedicated resource", pytrace=False)
    prefix = "cpbl238:a8:test"
    client = redis.Redis.from_url(
        url, decode_responses=True, socket_timeout=2, socket_connect_timeout=2
    )
    try:
        assert client.ping()
        cache = RedisLiveGameCache(
            client, prefix=prefix, snapshot_ttl_seconds=60, lock_ttl_seconds=30
        )
        raw = game(6)
        worker = LiveGameWorker(
            cache=cache,
            fetch_schedule=lambda year, month, kind="A": [raw] if kind == "E" else [],
            fetch_game=lambda _: raw,
            postseason_kinds=("E",),
            observation_sink=observe,
            observation_clock=lambda: T0,
        )
        result = worker.run_cycle(T0)
        assert result["announcement_observed"] == 1 and not result["announcement_errors"]
        assert result["cached"] == 1 and cache.get_snapshot(2026, "E", 6)["game_id"] == "2026-E-6"
        assert len(rows(6)) == 1
        keys = list(client.scan_iter(match=f"{prefix}:*"))
        assert not any("lock" in key for key in keys)
    finally:
        # 只有已租用測试prefix；不FLUSH、不清其他worker key。
        keys = list(client.scan_iter(match=f"{prefix}:*"))
        if keys:
            client.delete(*keys)
        client.close()
