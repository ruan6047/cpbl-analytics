"""#236 R-1：執行實際讀取 SQL，驗證年度留存後的來源邊界與守位聚合。"""
import json
import sqlite3

import pytest

from cpbl.api import matchups, team_records
from cpbl.api.routers.ability import _bat_ability_sql


@pytest.fixture
def sql_db():
    db = sqlite3.connect(":memory:")
    db.execute("ATTACH DATABASE ':memory:' AS cpbl")
    db.create_function("trunc", 1, lambda n: int(n))
    db.executescript("""
        CREATE TABLE cpbl.players(id TEXT, name TEXT);
        CREATE TABLE cpbl.batting_seasons(player_id TEXT, year INT, team_id TEXT,
            ab INT, h INT, b2 INT, b3 INT, hr INT, bb INT, ibb INT, hbp INT, sf INT,
            rbi INT, r INT, sb INT);
        CREATE TABLE cpbl.batting_current AS SELECT * FROM cpbl.batting_seasons WHERE 0;
        CREATE TABLE cpbl.pitching_seasons(player_id TEXT, year INT, team_id TEXT,
            bf INT, h INT, hr INT, bb INT, ibb INT, hbp INT, so INT, ip REAL,
            w INT, sv INT, hld INT);
        CREATE TABLE cpbl.pitching_current(player_id TEXT, year INT, pa INT,
            h INT, hr INT, bb INT, ibb INT, hbp INT);
        CREATE TABLE cpbl.fielding_seasons(player_id TEXT, year INT, team_id TEXT,
            pos TEXT, g INT, po REAL, a REAL, cs REAL, sb REAL);
    """)
    yield db
    db.close()


class FranchiseCursor:
    def __init__(self, db):
        self.db = db

    def execute(self, sql, params):
        sql = sql.replace("= ANY(%s)", "IN (SELECT value FROM json_each(?))")
        sql = sql.replace("%s", "?")
        self.result = self.db.execute(sql, (json.dumps(params[0]), *params[1:]))

    def fetchall(self):
        return self.result.fetchall()


def test_franchise_prior_excludes_retained_current_and_future_seasons(sql_db):
    sql_db.executemany("INSERT INTO cpbl.batting_seasons VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", [
        ("p", 2025, "AAA1", 100, 20, 0, 0, 1, 0, 0, 0, 0, 10, 10, 1),
        ("p", 2025, "AAA2", 50, 10, 0, 0, 1, 0, 0, 0, 0, 5, 5, 1),
        ("p", 2026, "AAA1", 100, 99, 0, 0, 1, 0, 0, 0, 0, 10, 10, 1),
        ("p", 2027, "AAA1", 100, 88, 0, 0, 1, 0, 0, 0, 0, 10, 10, 1),
        ("p", 2025, "BBB1", 100, 77, 0, 0, 1, 0, 0, 0, 0, 10, 10, 1),
    ])
    prior = team_records._franchise_batting_totals(FranchiseCursor(sql_db), ["AAA"])
    assert prior["p"]["h"] == 30
    current = team_records._merge_current_season(
        prior, [{"player_id": "p", "name": "球員"}], {"p": {"h": 9}}, ["h"])
    assert current["p"]["h"] == 39


def test_franchise_pitching_prior_keeps_multiteam_outs_once(sql_db):
    sql_db.executemany("INSERT INTO cpbl.pitching_seasons VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", [
        ("p", 2025, "AAA1", 30, 0, 0, 0, 0, 0, 10, 3.1, 1, 1, 2),
        ("p", 2025, "AAA2", 30, 0, 0, 0, 0, 0, 20, 2.2, 2, 2, 3),
        ("p", 2026, "AAA1", 30, 0, 0, 0, 0, 0, 99, 90.0, 9, 9, 9),
    ])
    prior = team_records._franchise_pitching_totals(FranchiseCursor(sql_db), ["AAA"])
    assert prior["p"] == {"name": "p", "so": 30, "ip": 6, "w": 3, "sv_hld": 8}


@pytest.mark.parametrize("role", ["batting", "pitching"])
def test_official_matchup_pool_prefers_complete_season_and_keeps_current_fallback(sql_db, role):
    if role == "batting":
        sql = matchups._BATTING_OFFICIAL_SQL
        sql_db.execute("INSERT INTO cpbl.batting_seasons(player_id,year,team_id,ab,h) VALUES ('p',2025,'AAA',50,5)")
        sql_db.execute("INSERT INTO cpbl.batting_current(player_id,year,ab,h) VALUES ('p',2026,100,20)")
        sql_db.execute("INSERT INTO cpbl.batting_current(player_id,year,ab,h) VALUES ('old',2025,777,77)")
        retain = "INSERT INTO cpbl.batting_seasons(player_id,year,team_id,ab,h) VALUES ('p',2026,'AAA',100,20)"
    else:
        sql = matchups._PITCHING_OFFICIAL_SQL
        sql_db.execute("INSERT INTO cpbl.pitching_seasons(player_id,year,team_id,bf,h) VALUES ('p',2025,'AAA',50,5)")
        sql_db.execute("INSERT INTO cpbl.pitching_current(player_id,year,pa,h) VALUES ('p',2026,100,20)")
        retain = "INSERT INTO cpbl.pitching_seasons(player_id,year,team_id,bf,h) VALUES ('p',2026,'AAA',100,20)"
    sql = sql.replace("%(lo)s", ":lo").replace("%(hi)s", ":hi")
    before = sql_db.execute(sql, {"lo": 2026, "hi": 2026}).fetchall()
    assert [(r[0], r[1], r[2]) for r in before] == [("p", 100, 20)]
    sql_db.execute(retain)
    # current 中有未留存球員也不能混入完整年度母體。
    if role == "batting":
        sql_db.execute("INSERT INTO cpbl.batting_current(player_id,year,ab,h) VALUES ('extra',2026,10,2)")
    else:
        sql_db.execute("INSERT INTO cpbl.pitching_current(player_id,year,pa,h) VALUES ('extra',2026,10,2)")
    after = sql_db.execute(sql, {"lo": 2026, "hi": 2026}).fetchall()
    assert after == before
    career = sql_db.execute(sql, {"lo": 1990, "hi": 2026}).fetchall()
    assert [(r[0], r[1], r[2]) for r in career] == [("p", 150, 25)]


def fielding_ctes():
    sql = _bat_ability_sql("career")
    start = sql.find("pos_source AS (")
    if start < 0:
        start = sql.index("pos_yr AS (")
    return sql[start:sql.index(", pos_pr AS (")].replace("::float", "")


def test_career_fielding_merges_chinese_and_historical_position_before_threshold(sql_db):
    sql_db.executemany("INSERT INTO cpbl.fielding_seasons VALUES (?,?,?,?,?,?,?,?,?)", [
        ("catcher", 2025, "AAA", "C", 10, 50, 2, 1, 3),
        ("catcher", 2026, "AAA", "捕手", 25, 100, 3, None, None),
        ("catcher", 2026, "BBB", "C", 5, 20, 1, 1, 3),
        ("peer", 2026, "AAA", "C", 40, 180, 3, 2, 2),
        ("catcher", 2026, "AAA", "1B", 31, 130, 3, None, None),
    ])
    rows = sql_db.execute("WITH " + fielding_ctes() + " SELECT player_id,pos,g,rf,(pos='C') FROM pos_rf ORDER BY player_id,pos").fetchall()
    catcher = [r for r in rows if r[0] == "catcher" and r[1] == "C"]
    assert len(catcher) == 1
    assert catcher[0][2] == 40  # 同年多隊、跨年語言與其他守位均完整保留。
    assert catcher[0][3] == pytest.approx(5 / 6)
    assert catcher[0][4] == 1
    assert any(r[:3] == ("catcher", "1B", 31) for r in rows)


@pytest.mark.parametrize("pos,zh", [("P", "投手"), ("C", "捕手"), ("1B", "一壘手"),
    ("2B", "二壘手"), ("3B", "三壘手"), ("SS", "游擊手"),
    ("LF", "左外野手"), ("CF", "中外野手"), ("RF", "右外野手")])
def test_career_fielding_uses_existing_nine_position_meaning(sql_db, pos, zh):
    sql_db.executemany("INSERT INTO cpbl.fielding_seasons VALUES (?,?,?,?,?,?,?,?,?)", [
        ("p", 2026, "AAA", pos, 20, 20, 1, None, None),
        ("p", 2026, "BBB", zh, 20, 20, 1, None, None),
    ])
    rows = sql_db.execute("WITH " + fielding_ctes() + " SELECT player_id,pos,g FROM pos_yr").fetchall()
    assert rows == [("p", pos, 40)]


def test_franchise_prior_uses_requested_season(sql_db):
    sql_db.executemany("INSERT INTO cpbl.batting_seasons(player_id,year,team_id,h) VALUES (?,?,?,?)", [
        ("p", 2024, "AAA", 10), ("p", 2025, "AAA", 20), ("p", 2026, "AAA", 30)])
    cur = FranchiseCursor(sql_db)
    assert team_records._franchise_batting_totals(cur, ["AAA"], 2025)["p"]["h"] == 10
    assert team_records._franchise_batting_totals(cur, ["AAA"], 2027)["p"]["h"] == 60


def test_upcoming_records_passes_requested_season_to_both_prior_queries(monkeypatch):
    from contextlib import nullcontext
    from types import SimpleNamespace

    monkeypatch.setattr(team_records, "conn", lambda: nullcontext(SimpleNamespace(cursor=lambda: None)))
    monkeypatch.setattr(team_records, "_roster", lambda *args: ([], []))
    monkeypatch.setattr(team_records, "_pitcher_near_by_player", lambda *args: {})
    for name in ("_batter_milestones", "_pitcher_milestones"):
        monkeypatch.setattr(team_records, name, lambda *args: [])
    seen = []

    def prior(cur, prefixes, season):
        seen.append(season)
        return {}

    for name in ("_franchise_batting_totals", "_franchise_pitching_totals"):
        monkeypatch.setattr(team_records, name, prior)
    for name in ("_franchise_current_season_batting", "_franchise_current_season_pitching"):
        monkeypatch.setattr(team_records, name, lambda *args: {})
    assert team_records.upcoming_records("AAA", 2025)["season"] == 2025
    assert seen == [2025, 2025]
