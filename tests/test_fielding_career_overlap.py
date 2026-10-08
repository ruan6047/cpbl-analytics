"""#236：季表與 current 同年度共存時，生涯守備只採一份。"""
import sqlite3
from contextlib import contextmanager

import pytest

from cpbl.api.routers import players


@pytest.fixture
def fielding_db(monkeypatch):
    db = sqlite3.connect(":memory:")
    db.execute("ATTACH DATABASE ':memory:' AS cpbl")
    columns = "year int, player_id text, pos text, g int, tc int, po int, a int, e int, dp int, tp int, pb int, cs int"
    db.execute(f"CREATE TABLE cpbl.fielding_seasons ({columns}, team_id text, sb int)")
    db.execute(f"CREATE TABLE cpbl.fielding_current ({columns}, team_code text, sba int, kind_code text)")

    class Cursor:
        def execute(self, query, params):
            self.cur = db.execute(query.replace("%s", "?"), params)

        def fetchall(self):
            return self.cur.fetchall()

    class Connection:
        def cursor(self):
            return Cursor()

    @contextmanager
    def connection():
        yield Connection()

    monkeypatch.setattr(players, "conn", connection)
    yield db
    db.close()


def season(db, year, team, games):
    db.execute("INSERT INTO cpbl.fielding_seasons VALUES (?, '0000000001', 'P', ?, ?, ?, 0, 0, 0, 0, 0, NULL, ?, NULL)", (year, games, games, games, team))


def current(db, year, games, kind="A"):
    db.execute("INSERT INTO cpbl.fielding_current VALUES (?, '0000000001', '投手', ?, ?, ?, 0, 0, 0, 0, 0, 3, 'AAA011', 7, ?)", (year, games, games, games, kind))


def totals():
    return players.player_fielding("0000000001", scope="career")["items"][0]


def test_current_year_replaces_overlapping_season_and_preserves_verified_cs(fielding_db):
    season(fielding_db, 2024, "AAA", 10)
    season(fielding_db, 2026, "AAA011", 26)
    current(fielding_db, 2026, 26)
    row = totals()
    assert (row["g"], row["tc"], row["cs"], row["sba"]) == (36, 36, 3, 7)


def test_no_current_keeps_all_teams_in_same_season(fielding_db):
    season(fielding_db, 2026, "AAA011", 20)
    season(fielding_db, 2026, "AJL011", 6)
    assert totals()["g"] == 26


def test_farm_current_does_not_hide_regular_season(fielding_db):
    season(fielding_db, 2026, "AAA011", 26)
    current(fielding_db, 2026, 9, kind="D")
    assert totals()["g"] == 26
