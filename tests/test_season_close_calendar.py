"""#391 審核 F1：二軍 F 月曆接上收官判定（``/api/v1/games/calendar`` 每列帶 ``not_needed``）。

樣本：2026 F1–F3＝官網原始回應（``tests/fixtures/getgamedatas_F_2026_raw.json``，真實）；
**F4 是構造的**未完成列（2026 實際不存在 F4），用來代表「二軍已先達 3 勝、官網仍殘留的未舉行場次」——
規劃 PLAN.md:89 所說「本季無，防未來」的那種列。⛔ 不聲稱 2026 有 F4。
"""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import date
from pathlib import Path

from fastapi.testclient import TestClient

from cpbl import season_close as sc
from cpbl.api.main import app
from cpbl.api.routers import games

RAW = json.loads((Path(__file__).resolve().parent / "fixtures" / "getgamedatas_F_2026_raw.json")
                 .read_text(encoding="utf-8"))
COLS = ["year", "kind_code", "game_sno", "game_date", "venue", "present_status",
        "away_team_name", "away_team_code", "away_score", "home_team_name", "home_team_code", "home_score",
        "win_pitcher", "lose_pitcher", "mvp", "home_starter", "away_starter",
        "attendance", "game_time", "delay_kind", "orig_date", "completed"]


def real_f() -> list[dict]:
    out = []
    for e in json.loads(json.loads(RAW["body"])["GameDatas"]):
        out.append({"year": 2026, "kind_code": "F", "game_sno": int(e["GameSno"]),
                    "game_date": date.fromisoformat(e["GameDate"][:10]), "venue": e["FieldAbbe"],
                    "present_status": int(e["PresentStatus"]),
                    "away_team_name": e["VisitingTeamName"], "away_team_code": e["VisitingTeamCode"],
                    "away_score": int(e["VisitingScore"]), "home_team_name": e["HomeTeamName"],
                    "home_team_code": e["HomeTeamCode"], "home_score": int(e["HomeScore"]),
                    "win_pitcher": None, "lose_pitcher": None, "mvp": None, "home_starter": None,
                    "away_starter": None, "attendance": None, "game_time": None, "delay_kind": None,
                    "orig_date": None, "completed": True})
    return out


def constructed_f4(rows: list[dict]) -> dict:
    """⚠️ 構造列：F3 之後的未舉行 F4（0:0、未完賽）。"""
    return {**rows[-1], "game_sno": 4, "game_date": date(2026, 10, 3), "away_score": 0, "home_score": 0,
            "away_team_code": rows[-1]["home_team_code"], "away_team_name": rows[-1]["home_team_name"],
            "home_team_code": rows[-1]["away_team_code"], "home_team_name": rows[-1]["away_team_name"],
            "completed": False}


def farm_closure(rows: list[dict]) -> sc.LeagueClosure:
    """真實判定函式（先達 3 勝）作用在同一批列上；決勝場 F3 官網 PresentStatus=1、GameResult='0'＝官方 final。"""
    games_ = [sc.FarmGame(2026, r["game_sno"], r["game_date"], r["away_team_code"], r["home_team_code"],
                          r["away_score"], r["home_score"], r["completed"], r["completed"]) for r in rows]
    return sc.tally_farm_series(2026, games_)


class _Cur:
    def __init__(self, rows):
        self.description = [(c,) for c in COLS]
        self._rows = [tuple(r[c] for c in COLS) for r in rows]

    def execute(self, sql, params=None):
        assert "FROM cpbl.games g" in sql

    def fetchall(self):
        return self._rows


class _Conn:
    def __init__(self, rows):
        self._cur = _Cur(rows)

    def cursor(self):
        return self._cur

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _calendar(monkeypatch, rows, closure) -> list[dict]:
    monkeypatch.setattr(games, "conn", lambda: _Conn(rows))
    monkeypatch.setattr(games, "_season_closure", lambda season: closure, raising=False)
    res = TestClient(app).get("/api/v1/games/calendar?season=2026&kind_code=D")
    assert res.status_code == 200
    return res.json()["items"]


def test_closed_farm_marks_constructed_f4_not_needed(monkeypatch):
    rows = real_f()
    rows.append(constructed_f4(rows))
    closure = farm_closure(rows)
    assert closure.closed and closure.not_needed_keys == frozenset({(2026, "F", 4)})
    items = _calendar(monkeypatch, rows, {"farm": closure})
    assert [(i["game_sno"], i["not_needed"]) for i in items] == [(1, False), (2, False), (3, False), (4, True)]


def test_calendar_without_closure_marks_nothing(monkeypatch):
    rows = real_f()
    rows.append(constructed_f4(rows))
    items = _calendar(monkeypatch, rows, None)
    assert [i["not_needed"] for i in items] == [False] * 4


def test_open_farm_does_not_mark_pending_games(monkeypatch):
    """二軍未收官（F3 尚未完賽＝2:0）時，F3／F4 都只是未完賽，不得標 not_needed。"""
    rows = real_f()
    rows[-1] = {**rows[-1], "completed": False, "away_score": 0, "home_score": 0}
    rows.append(constructed_f4(rows))
    closure = farm_closure(rows)
    assert not closure.closed
    items = _calendar(monkeypatch, rows, {"farm": replace(closure)})
    assert [i["not_needed"] for i in items] == [False] * 4
