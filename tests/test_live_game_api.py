from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

from cpbl.api import live_cache
from cpbl.api.routers import games
from cpbl.ingest.live_game_worker import build_snapshot

NOW = datetime(2026, 7, 28, 10, 0, tzinfo=UTC)


def _raw(status: str = "START") -> dict:
    return {
        "GameId": "2026-A-226",
        "GameSno": 226,
        "KindCode": "A",
        "GameStatus": status,
        "PreExeDate": "2026-07-28T18:35:00",
        "Visiting": {"Team": {"Code": "AAA", "Name": "味全龍"}, "Score": 0},
        "Home": {"Team": {"Code": "AJL", "Name": "富邦悍將"}, "Score": 0},
        "LiveLog": [],
    }


def test_public_snapshot_marks_live_data_stale_without_discarding_last_known_good() -> None:
    snapshot = build_snapshot(_raw(), fetched_at=NOW - timedelta(seconds=46))

    public = live_cache.public_snapshot(snapshot, now=NOW, live_stale_after_seconds=45)

    assert public["phase"] == "live"
    assert public["freshness"] == "stale"
    assert public["stale_after_seconds"] == 45
    assert public["poll_after_seconds"] == 12
    assert public["away"]["score"] == 0


def test_final_snapshot_does_not_age_into_stale() -> None:
    snapshot = build_snapshot(_raw("FINISHED"), fetched_at=NOW - timedelta(days=1))

    public = live_cache.public_snapshot(snapshot, now=NOW, live_stale_after_seconds=45)

    assert public["phase"] == "final"
    assert public["freshness"] == "final"
    assert public["stale_after_seconds"] is None
    assert public["poll_after_seconds"] is None


def test_public_snapshot_exposes_source_error_separately_from_age() -> None:
    snapshot = build_snapshot(_raw(), fetched_at=NOW - timedelta(seconds=5))
    snapshot["source"]["last_error_at"] = (NOW - timedelta(seconds=1)).isoformat()
    snapshot["source"]["last_error_type"] = "ReadTimeout"

    public = live_cache.public_snapshot(snapshot, now=NOW, live_stale_after_seconds=45)

    assert public["freshness"] == "fresh"
    assert public["source_status"] == "error"
    assert public["source"]["last_error_type"] == "ReadTimeout"


class _Cursor:
    description: list = []

    def execute(self, *_args, **_kwargs):
        return self

    def fetchall(self):
        return []


class _Connection:
    def cursor(self):
        return _Cursor()


@contextmanager
def _empty_conn():
    yield _Connection()


def test_status_endpoint_adds_cache_phase_without_rewriting_db_official_status(monkeypatch) -> None:
    snapshot = build_snapshot(_raw(), fetched_at=NOW)
    monkeypatch.setattr(games, "conn", _empty_conn)
    monkeypatch.setattr(games, "get_public_live_snapshot", lambda *_: snapshot)

    body = games.game_status(226, season=2026, kind_code="A")

    assert body["official_game_status"]["status"] == "unknown"
    assert body["canonical_phase"] == "live"
    assert body["live_snapshot"]["raw_status"] == "START"


def test_status_snapshot_drops_heavy_arrays_but_keeps_state_and_counts() -> None:
    raw = _raw()
    raw["LiveLog"] = [{"PitchCnt": i} for i in range(1, 4)]
    raw["Visiting"]["Hitters"] = [{
        "Lineup": 1, "HitterAcnt": "h1", "HitterName": "客隊第一棒", "DefendStation": "CF",
    }]
    raw["Visiting"]["Pitchers"] = [{"PitcherAcnt": "p1"}]
    full = live_cache.public_snapshot(
        build_snapshot(raw, fetched_at=NOW), now=NOW, live_stale_after_seconds=45,
    )

    slim = live_cache.status_snapshot(full)

    assert "livelog" not in slim
    assert "hitters" not in slim["away"] and "pitchers" not in slim["away"]
    assert slim["event_count"] == 3
    assert slim["away"]["lineup"]["availability"] == "partial"
    assert slim["freshness"] == full["freshness"]
    # /live 端保留全量，status_snapshot 不得改動原 snapshot
    assert full["livelog"] and full["away"]["hitters"]


def test_cache_failure_degrades_to_none(monkeypatch) -> None:
    class Broken:
        def get_snapshot(self, *_args):
            raise OSError("redis unavailable")

    monkeypatch.setattr(live_cache, "_cache", lambda: Broken())

    assert live_cache.get_public_live_snapshot(2026, "A", 226, now=NOW) is None
