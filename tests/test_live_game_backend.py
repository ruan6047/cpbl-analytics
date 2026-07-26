from __future__ import annotations

from datetime import UTC, datetime

from cpbl.ingest.live_game_worker import build_snapshot

T0 = datetime(2026, 7, 28, 17, 0, tzinfo=UTC)


def _team(name: str, *, score: int = 0, hitters: list[dict] | None = None,
          pitchers: list[dict] | None = None) -> dict:
    return {
        "Team": {"Code": name[:3], "Name": name},
        "Score": score,
        "Hitters": hitters or [],
        "Pitchers": pitchers or [],
        "InningScore": [],
    }


def _game(status: str, *, away: dict | None = None, home: dict | None = None,
          livelog: list[dict] | None = None) -> dict:
    return {
        "GameId": "2026-A-226",
        "GameSno": 226,
        "KindCode": "A",
        "GameStatus": status,
        "PreExeDate": "2026-07-28T18:35:00",
        "InningSeq": 1,
        "VisitingHomeType": 1,
        "Visiting": away or _team("味全龍"),
        "Home": home or _team("富邦悍將"),
        "LiveLog": livelog or [],
    }


def _starter(acnt: str, name: str) -> dict:
    return {"PitcherAcnt": acnt, "PitcherName": name, "RoleType": "先發"}


def _hitter(lineup: int, name: str) -> dict:
    return {
        "HitterAcnt": f"h{lineup}",
        "HitterName": name,
        "Lineup": lineup,
        "DefendStation": "CF",
    }


def test_scheduled_empty_payload_does_not_infer_announcements_from_clock() -> None:
    snapshot = build_snapshot(_game("SCHEDULED"), fetched_at=T0)

    assert snapshot["phase"] == "scheduled"
    assert snapshot["away"]["probable_pitcher"]["availability"] == "not_announced"
    assert snapshot["home"]["lineup"]["availability"] == "not_announced"
    assert snapshot["tracking_availability"] == "not_announced"


def test_probable_pitcher_and_lineup_are_independent_per_team() -> None:
    away = _team(
        "味全龍",
        pitchers=[_starter("p1", "伍鐸")],
        hitters=[_hitter(i, f"客隊打者{i}") for i in range(1, 10)],
    )
    home = _team("富邦悍將", hitters=[_hitter(1, "主隊第一棒")])

    snapshot = build_snapshot(_game("SCHEDULED", away=away, home=home), fetched_at=T0)

    assert snapshot["phase"] == "lineup_announced"
    assert snapshot["away"]["probable_pitcher"] == {
        "availability": "announced",
        "player_id": "p1",
        "name": "伍鐸",
        "first_observed_at": T0.isoformat(),
    }
    assert snapshot["away"]["lineup"]["availability"] == "announced"
    assert len(snapshot["away"]["lineup"]["items"]) == 9
    assert snapshot["home"]["probable_pitcher"]["availability"] == "not_announced"
    assert snapshot["home"]["lineup"]["availability"] == "partial"


def test_start_zero_zero_is_live_and_zero_trackman_is_pending_not_no_equipment() -> None:
    livelog = [{
        "PitchCnt": 1,
        "PitcherAcnt": "p1",
        "HitterAcnt": "h1",
        "Content": "好球沒揮棒。",
        "Trackman": None,
    }]

    snapshot = build_snapshot(_game("START", livelog=livelog), fetched_at=T0)

    assert snapshot["phase"] == "live"
    assert snapshot["away"]["score"] == 0
    assert snapshot["home"]["score"] == 0
    assert snapshot["event_count"] == 1
    assert snapshot["tracking_availability"] == "pending"


def test_finished_trackman_is_available_and_unknown_status_fails_closed() -> None:
    tracked = [{
        "PitchCnt": 1,
        "PitcherAcnt": "p1",
        "Trackman": {"Pitch": {"Release": {"RelSpeed": 150.0}}},
    }]
    finished = build_snapshot(_game("FINISHED", livelog=tracked), fetched_at=T0)
    unknown = build_snapshot(_game("SUSPENDED"), fetched_at=T0)

    assert finished["phase"] == "final"
    assert finished["tracking_availability"] == "available"
    assert unknown["phase"] == "unknown"
    assert unknown["raw_status"] == "SUSPENDED"


def test_first_observed_time_survives_later_snapshots() -> None:
    away = _team("味全龍", pitchers=[_starter("p1", "伍鐸")])
    first = build_snapshot(_game("SCHEDULED", away=away), fetched_at=T0)
    later = build_snapshot(
        _game("SCHEDULED", away=away),
        fetched_at=datetime(2026, 7, 28, 17, 10, tzinfo=UTC),
        previous=first,
    )

    assert later["away"]["probable_pitcher"]["first_observed_at"] == T0.isoformat()
    assert later["source"]["fetched_at"] != T0.isoformat()
