from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from datetime import UTC, datetime
from importlib import import_module

import pytest


def api():
    return import_module("cpbl.ingest.lineup_announcements")


def raw_game(status="SCHEDULED"):
    positions = ["C", "1B", "2B", "3B", "SS", "LF", "CF", "RF", "DH"]

    def team(code, offset):
        return {
            "Team": {"Code": code},
            "Score": 99,
            "Hitters": [
                {
                    "Lineup": n,
                    "HitterAcnt": str(offset + n).zfill(10),
                    "HitterName": f"打者{offset + n}",
                    "DefendStation": pos,
                    "Hits": 99,
                    "DOB": "not-projected",
                }
                for n, pos in enumerate(positions, 1)
            ],
        }

    return {
        "GameId": "2026-E-4",
        "GameSno": 4,
        "KindCode": "E",
        "PreExeDate": "2026-10-12T17:05:00",
        "GameStatus": status,
        "Visiting": team("ACN011", 0),
        "Home": team("ADD011", 10),
        "LiveLog": [{"secret_fixture": "not-projected"}],
    }


def test_projection_hash_excludes_status_scores_time_and_stats_but_keeps_lineup_version():
    source = api()
    raw = raw_game()
    projected = source.project("2026-E-4", raw)
    changed = deepcopy(raw)
    changed["GameStatus"] = "START"
    changed["Visiting"]["Score"] = 3
    changed["Visiting"]["Hitters"][0]["Hits"] = 7
    changed["LiveLog"] = []
    assert source.content_hash(projected) == source.content_hash(
        source.project("2026-E-4", changed)
    )
    assert projected["GameStatus"] == "SCHEDULED"
    assert "LiveLog" not in projected and "Score" not in projected["Visiting"]
    assert all(
        set(h) == {"Lineup", "HitterAcnt", "HitterName", "DefendStation"}
        for h in projected["Visiting"]["Hitters"]
    )
    changed["Visiting"]["Hitters"][0]["DefendStation"] = "RF(CF)"
    assert source.content_hash(projected) != source.content_hash(
        source.project("2026-E-4", changed)
    )


def test_projection_order_is_canonical_without_deduplicating_or_truncating():
    source = api()
    raw = raw_game()
    reversed_raw = deepcopy(raw)
    reversed_raw["Visiting"]["Hitters"].reverse()
    assert source.content_hash(source.project("2026-E-4", raw)) == source.content_hash(
        source.project("2026-E-4", reversed_raw)
    )
    raw["Visiting"]["Hitters"].append(deepcopy(raw["Visiting"]["Hitters"][0]))
    assert len(source.project("2026-E-4", raw)["Visiting"]["Hitters"]) == 10


@pytest.mark.parametrize("field,value", [("GameId", "2026-C-4"), ("KindCode", "C"), ("GameSno", 5)])
def test_wrong_source_identity_is_rejected(field, value):
    raw = raw_game()
    raw[field] = value
    with pytest.raises(ValueError):
        api().project("2026-E-4", raw)


@pytest.mark.parametrize("identity", ["2025-E-4", "2026-A-4", "2026-E-0"])
def test_persistence_scope_is_only_positive_2026_e_c_identity(identity):
    with pytest.raises(ValueError):
        api().project(identity, raw_game())


def test_unknown_status_and_partial_shape_are_kept_as_evidence_not_announced():
    raw = raw_game()
    raw.pop("GameStatus")
    raw["Home"]["Hitters"] = []
    projected = api().project("2026-E-4", raw)
    assert projected["GameStatus"] is None and projected["Home"]["Hitters"] == []
    assert "Pitchers" not in projected["Home"]


T0 = datetime(2026, 10, 12, 0, 0, tzinfo=UTC)
T1 = datetime(2026, 10, 12, 0, 1, tzinfo=UTC)
T2 = datetime(2026, 10, 12, 0, 2, tzinfo=UTC)


def existing_row(raw, fetched=T0, last=T0):
    projected = api().project("2026-E-4", raw)
    return {
        "fetched_at": fetched,
        "last_seen_at": last,
        "raw_status": raw.get("GameStatus"),
        "raw_payload": projected,
        "content_hash": api().content_hash(projected),
    }


def fake_connection(monkeypatch, responses):
    calls = []
    outcome = {"commit": False, "rollback": False}

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def execute(self, sql, params):
            calls.append((sql, params))

        def fetchone(self):
            return responses.pop(0)

    class Connection:
        def cursor(self, **kwargs):
            return Cursor()

    @contextmanager
    def connection():
        try:
            yield Connection()
        except Exception:
            outcome["rollback"] = True
            raise
        else:
            outcome["commit"] = True

    monkeypatch.setattr(api(), "conn", connection)
    return calls, outcome


def test_new_revision_uses_parameterized_source_only_insert(monkeypatch):
    calls, outcome = fake_connection(monkeypatch, [None, None])
    result = api().observe("2026-E-4", raw_game(), T0)
    assert result["action"] == "inserted" and result["fetched_at"] == T0
    assert outcome["commit"] and not outcome["rollback"]
    sql, params = calls[-1]
    assert "INSERT INTO cpbl.game_lineup_announcement_revisions" in sql and "%s::jsonb" in sql
    assert params[:4] == (2026, "E", 4, "stats_datagame") and params[5] == params[-1] == T0
    assert "DOB" not in params[-2] and "LiveLog" not in params[-2]


def test_same_content_status_only_updates_latest_last_seen(monkeypatch):
    calls, outcome = fake_connection(monkeypatch, [None, existing_row(raw_game())])
    result = api().observe("2026-E-4", raw_game(), T2)
    assert result["action"] == "seen" and result["fetched_at"] == T0
    assert "UPDATE" in calls[-1][0] and "GREATEST" in calls[-1][0]
    assert calls[-1][1][0] == T2 and calls[-1][1][-1] == T0
    assert not any("INSERT" in sql for sql, _ in calls) and outcome["commit"]


def test_reappeared_content_and_status_create_new_fragments(monkeypatch):
    changed = raw_game()
    changed["Visiting"]["Hitters"][0]["HitterAcnt"] = "0000000088"
    for previous, incoming in [(changed, raw_game()), (raw_game("START"), raw_game())]:
        calls, outcome = fake_connection(monkeypatch, [None, existing_row(previous, T1, T1)])
        result = api().observe("2026-E-4", incoming, T2)
        assert result["action"] == "inserted" and result["fetched_at"] == T2
        assert "INSERT" in calls[-1][0] and outcome["commit"]


def test_exact_natural_key_replay_does_not_borrow_today_clock(monkeypatch):
    calls, _ = fake_connection(monkeypatch, [existing_row(raw_game(), T0, T1)])
    result = api().observe("2026-E-4", raw_game(), T0)
    assert result["action"] == "replayed" and result["fetched_at"] == T0
    assert len(calls) == 1  # 沒有假新取得、沒有重寫舊片段時點。


def test_same_key_conflict_rolls_back_without_touching_old_evidence(monkeypatch):
    calls, outcome = fake_connection(monkeypatch, [existing_row(raw_game("START"))])
    with pytest.raises(ValueError, match="conflict"):
        api().observe("2026-E-4", raw_game(), T0)
    assert outcome["rollback"] and not outcome["commit"]
    assert len(calls) == 1


@pytest.mark.parametrize("now", [T0, T1])
def test_new_observation_backwards_or_same_time_contradiction_is_rejected(monkeypatch, now):
    calls, outcome = fake_connection(monkeypatch, [None, existing_row(raw_game("START"), T0, T1)])
    with pytest.raises(ValueError):
        api().observe("2026-E-4", raw_game(), now)
    assert outcome["rollback"] and len(calls) == 2


def test_naive_timestamp_stops_before_connection(monkeypatch):
    calls, _ = fake_connection(monkeypatch, [])
    with pytest.raises(ValueError, match="timezone"):
        api().observe("2026-E-4", raw_game(), T0.replace(tzinfo=None))
    assert calls == []
