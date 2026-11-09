"""#442 G1：選定唯讀端點同鍵只算一次、有無快取內容相同、即時端點不快取（不碰 DB）。"""

from __future__ import annotations

import inspect
import threading
import time
from contextlib import contextmanager

import pytest

from cpbl.api import response_cache
from cpbl.api import team_style as api_ts
from cpbl.api.routers import daily, games, outcome, standings, teams
from cpbl.api.ttl_cache import SWRCache


@pytest.fixture(autouse=True)
def _fresh_cache(monkeypatch):
    monkeypatch.setattr(response_cache, "CACHE", SWRCache(600))
    yield


class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._rows[0] if self._rows else None


@contextmanager
def _conn(rows=()):
    class _C:
        def execute(self, *_a, **_k):
            return _Rows(list(rows))

        def cursor(self):
            return self

    yield _C()


def test_upcoming_records_once_per_key(monkeypatch):
    calls = []
    monkeypatch.setattr(teams, "upcoming_records",
                        lambda code, season: calls.append((code, season)) or {"team": code})
    a = teams.team_upcoming_records(code="AAA011", season=2026)
    b = teams.team_upcoming_records(code="AAA011", season=2026)
    teams.team_upcoming_records(code="ACN011", season=2026)
    assert a == b == {"team": "AAA011"}
    assert calls == [("AAA011", 2026), ("ACN011", 2026)]


def test_special_records_concurrent_single_flight(monkeypatch):
    calls, gate = [], threading.Event()

    def slow(season, kind_code):
        calls.append(1)
        gate.wait(2)
        return {"AAA011": {"natural": [1, 0], "artificial": [0, 0]}}

    monkeypatch.setattr(teams.special_records, "team_situational", slow)
    monkeypatch.setattr(teams, "conn", lambda: _conn([("AAA011", "中信兄弟")]))
    out = []
    ts = [threading.Thread(target=lambda: out.append(teams.special_records_endpoint(season=2026, kind_code="A")))
          for _ in range(8)]
    for t in ts:
        t.start()
    time.sleep(0.2)
    gate.set()
    for t in ts:
        t.join(5)
    assert len(calls) == 1 and len(out) == 8
    assert out[0]["items"][0]["team_name"] == "中信兄弟"


def test_style_heavy_load_shared_across_teams(monkeypatch):
    loads = []
    monkeypatch.setattr(api_ts.ts, "load_team_games", lambda c: loads.append("g") or {})
    monkeypatch.setattr(api_ts.ts, "load_team_names", lambda c: {})
    monkeypatch.setattr(api_ts, "_in_progress_years", lambda c: set())
    monkeypatch.setattr(api_ts, "conn", lambda: _conn([]))
    for code in ("AAA011", "ACN011", "ADD011", "AEO011", "AJL011", "AKP011"):
        assert teams.team_style(code=code)["team"] == code
    assert loads == ["g"]


def test_team_split_cached_equals_uncached(monkeypatch):
    def metrics(cur, season, half):
        return {"AAA011": {"g": 10 if half is None else 5, "ops": 0.7}}

    monkeypatch.setattr(standings, "_team_scoped_metrics", metrics)
    monkeypatch.setattr(standings, "conn", lambda: _conn([]))
    uncached = standings.season_team_split.uncached(season=2026)
    assert standings.season_team_split(season=2026) == uncached
    assert standings.season_team_split(season=2026) is standings.season_team_split(season=2026)


@pytest.mark.parametrize("fn", [
    daily.daily_summary, games.game_milestones, outcome.outcome_pregame,
])
def test_live_endpoints_are_not_cached(fn):
    """排除清單（response_cache docstring）：即時／serving 揭露端點⛔ 不裝 @cached。"""
    assert not hasattr(fn, "uncached")
    assert inspect.unwrap(fn) is fn
