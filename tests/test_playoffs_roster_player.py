"""#286 S05 WP4：抽屜按需詳情（player_detail_in_txn）——context_version 同源、名單外 404、層級決定走勢賽別。

以 monkeypatch 隔離 DB：S02 context、名單、能力卡、走勢都換成記錄呼叫的假函式。
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from cpbl.api.routers import ability, trend
from cpbl.playoffs import roster_reader as rr

NOW = datetime(2026, 10, 16, 2, 0, tzinfo=UTC)
CTX = {"context_version": "ctx-v9", "series": {"C": {"series_id": {"teams": ["AAA011", "ACN011"]}}}}


class _Cur:
    def __init__(self, rows):
        self.rows, self.description = rows, [("pid",), ("kind_code",), ("g",)]

    def execute(self, sql, params=None):
        self.params = params

    def fetchall(self):
        return self.rows


@pytest.fixture
def patched(monkeypatch):
    calls = {}
    monkeypatch.setattr(rr, "read_context", lambda cur, year, now, live_reader=None: CTX)
    monkeypatch.setattr(rr, "read_rosters", lambda cur, year, series, teams: {
        "AAA011": {"members": [{"player_id": "0000000001", "announced_name": "甲", "official_position": "投手",
                                "tactical_role": "unclassified"}]},
        "ACN011": None})
    monkeypatch.setattr(ability, "_ability_card",
                        lambda cur, pid, role, scope, year: {"available": True, "role": role, "scope": scope})

    def fake_trend(cur, pid, role, season, kind):
        calls["trend"] = (pid, role, season, kind)
        return {"player_id": pid, "role": role, "items": [], "roll": 15}

    monkeypatch.setattr(trend, "trend_items", fake_trend)
    return calls


def test_detail_carries_same_context_version_and_role(patched):
    out = rr.player_detail_in_txn(_Cur([("0000000001", "A", 30)]), 2026, "C", "0000000001", now=NOW)
    assert out["contract"] == "playoffs-roster-player/v1"
    assert out["context_version"] == "ctx-v9"
    assert out["player"]["role"] == "pitching" and out["player"]["tactical_role"] is None
    assert out["player"]["level"] == "A" and out["team_code"] == "AAA011"
    assert out["ability"]["season"]["scope"] == "season" and out["ability"]["career"]["scope"] == "career"
    assert patched["trend"] == ("0000000001", "pitching", 2026, "A")


def test_farm_only_uses_farm_trend_and_none_has_no_trend(patched):
    out = rr.player_detail_in_txn(_Cur([("0000000001", "D", 12)]), 2026, "C", "0000000001", now=NOW)
    assert out["player"]["level"] == "D" and patched["trend"][3] == "D"
    patched.clear()
    out = rr.player_detail_in_txn(_Cur([]), 2026, "C", "0000000001", now=NOW)
    assert out["player"]["level"] == "none" and out["trend"] is None and "trend" not in patched


def test_not_in_roster_raises(patched):
    with pytest.raises(rr.NotInRoster):
        rr.player_detail_in_txn(_Cur([]), 2026, "C", "0000000002", now=NOW)
