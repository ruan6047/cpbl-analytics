"""#181：戰績走勢依 season_code 篩半季；0 完全不篩，下半季自首場重新累計。"""
from contextlib import contextmanager
from datetime import date

import pytest

from cpbl.api.routers import standings


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class _FakeConn:
    def __init__(self, rows, calls):
        self._rows = rows
        self._calls = calls

    def execute(self, sql, params):
        self._calls.append((sql, params))
        return _Result(self._rows)


def _patch(monkeypatch, rows):
    calls: list = []

    @contextmanager
    def fake_conn():
        yield _FakeConn(rows, calls)

    monkeypatch.setattr(standings, "conn", fake_conn)
    return calls


@pytest.mark.parametrize("code", [1, 2])
def test_half_season_filters_by_season_code(monkeypatch, code):
    calls = _patch(monkeypatch, [])
    standings.standings_trend(season=2025, kind_code="A", season_code=code)
    sql, params = calls[0]
    assert "game_season_code=%s" in sql
    assert params == (2025, "A", str(code))


def test_full_season_does_not_filter(monkeypatch):
    calls = _patch(monkeypatch, [])
    standings.standings_trend(season=2006, kind_code="D", season_code=0)
    sql, params = calls[0]
    assert "game_season_code" not in sql
    assert params == (2006, "D")


def test_second_half_accumulates_from_zero(monkeypatch):
    # 只回下半季比賽時，首日點就是當天賽果本身，不帶入任何上半季累計。
    rows = [
        (date(2025, 7, 4), "AAA", "BBB", 5, 2, "甲", "乙"),
        (date(2025, 7, 5), "BBB", "AAA", 3, 1, "乙", "甲"),
    ]
    _patch(monkeypatch, rows)
    out = standings.standings_trend(season=2025, kind_code="A", season_code=2)
    assert out["points"][0] == {"date": "07-04", "AAA": 1, "BBB": -1}
    assert out["points"][1] == {"date": "07-05", "AAA": 0, "BBB": 0}
