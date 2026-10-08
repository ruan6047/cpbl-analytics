"""#237：季後摘要逐場帶官方場號 `game_sno`（不連 DB）。

前端要從系列卡連回原場，連結必須是 `/games/{game_sno}?kind=&year=`；舊的 `game_no` 是系列內
完成順序，與官方場號不一定相同（例如中間有延賽或場號不連續），不能拿來組連結。"""
from datetime import date

from cpbl.api.routers import standings


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class _Conn:
    def __init__(self, rows):
        self.rows = rows
        self.calls: list[tuple] = []

    def execute(self, sql, params):
        self.calls.append((sql, params))
        return _Result(self.rows)


class _Ctx:
    def __init__(self, c):
        self.c = c

    def __enter__(self):
        return self.c

    def __exit__(self, *exc):
        return False


def _patch(monkeypatch, rows):
    c = _Conn(rows)
    monkeypatch.setattr(standings, "conn", lambda: _Ctx(c))
    return c


# (kind, home_code, home_name, away_code, away_name, home_score, away_score, game_date, game_sno)
_LION, _BRO = ("ADD011", "統一7-ELEVEn獅"), ("ACN011", "中信兄弟")


def test_games_carry_official_game_sno(monkeypatch):
    # 場號刻意不從 1 連號：game_no 是完成順序、game_sno 是官方編號，兩者必須分開。
    rows = [
        ("E", *_BRO, *_LION, 2, 5, date(2026, 10, 9), 1),
        ("E", *_LION, *_BRO, 4, 3, date(2026, 10, 10), 2),
        ("E", *_BRO, *_LION, 1, 0, date(2026, 10, 12), 4),
    ]
    c = _patch(monkeypatch, rows)

    resp = standings.postseason_summary(season=2026, kind_code="A")

    sql, params = c.calls[0]
    assert "game_sno" in sql
    assert params == (2026, ["E", "C"])
    (series,) = resp["series"]
    assert series["kind_code"] == "E"
    assert [g["game_no"] for g in series["games"]] == [1, 2, 3]
    assert [g["game_sno"] for g in series["games"]] == [1, 2, 4]
    assert series["games"][0] == {
        "game_no": 1, "game_sno": 1, "date": "2026-10-09",
        "home_code": "ACN011", "home_name": "中信兄弟", "home_score": 2,
        "away_code": "ADD011", "away_name": "統一7-ELEVEn獅", "away_score": 5,
    }


def test_existing_fields_unchanged(monkeypatch):
    # 新增欄位不改既有語意：系列大比分只計實際比賽勝場（規則讓勝由前端依公告另列）。
    rows = [
        ("E", *_BRO, *_LION, 2, 5, date(2026, 10, 9), 1),
        ("E", *_LION, *_BRO, 4, 3, date(2026, 10, 10), 2),
    ]
    _patch(monkeypatch, rows)

    (series,) = standings.postseason_summary(season=2026, kind_code="A")["series"]

    assert (series["team1_code"], series["team1_wins"]) == ("ADD011", 2)
    assert (series["team2_code"], series["team2_wins"]) == ("ACN011", 0)
    assert series["kind_name"] == "季後挑戰賽"


def test_farm_kind_queries_f_only(monkeypatch):
    c = _patch(monkeypatch, [])

    assert standings.postseason_summary(season=2025, kind_code="D") == {"season": 2025, "series": []}
    assert c.calls[0][1] == (2025, ["F"])
