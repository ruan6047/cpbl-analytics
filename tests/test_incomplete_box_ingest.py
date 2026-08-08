"""未完成保留賽不得被每日鏈當作完成場。"""

from __future__ import annotations

from contextlib import contextmanager

import pytest

from cpbl.ingest import run_check_coverage as coverage
from cpbl.ingest import run_refresh_recent as refresh


class _Cursor:
    def __init__(self, rows: list[tuple] | None = None) -> None:
        self.rows = rows or []
        self.sql = ""
        self.description = []

    def execute(self, sql: str, params=None):  # noqa: ANN001
        self.sql = sql
        return self

    def fetchall(self) -> list[tuple]:
        return self.rows


def _conn(cursor: _Cursor):
    class Connection:
        def execute(self, sql: str, params=None):  # noqa: ANN001
            return cursor.execute(sql, params)

    @contextmanager
    def factory():
        yield Connection()

    return factory


@pytest.mark.parametrize(
    ("query", "args"),
    [
        (refresh._missing_gamelog_snos, (2026, "D")),
        (refresh._lagging_pitch_games, (2026, "D")),
    ],
)
def test_refresh_queries_exclude_future_scored_games(query, args, monkeypatch) -> None:
    cursor = _Cursor()
    monkeypatch.setattr(refresh, "conn", _conn(cursor))

    query(*args)

    assert "game_date <= CURRENT_DATE" in cursor.sql
    assert "home_score + away_score > 0" in cursor.sql


def test_coverage_completed_flag_excludes_future_scored_games(monkeypatch) -> None:
    cursor = _Cursor()
    monkeypatch.setattr(coverage, "conn", _conn(cursor))

    coverage._rows(2026, "D")

    assert "game_date <= CURRENT_DATE" in cursor.sql
    assert "home_score + away_score > 0" in cursor.sql
