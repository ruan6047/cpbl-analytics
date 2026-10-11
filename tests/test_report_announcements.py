from datetime import UTC, datetime, timedelta
from importlib import import_module

import pytest

from cpbl.ingest.lineup_announcements import content_hash, project

T0 = datetime(2026, 10, 12, 0, 0, tzinfo=UTC)
TARGET = {
    "year": 2026,
    "kind_code": "E",
    "game_sno": 4,
    "away_team_code": "ACN011",
    "home_team_code": "ADD011",
}
POSITIONS = ["C", "1B", "2B", "3B", "SS", "LF", "CF", "RF", "DH"]


def row(minute=0, status="SCHEDULED", damage=None):
    def team(code, offset):
        return {
            "Team": {"Code": code},
            "Hitters": [
                {
                    "Lineup": i,
                    "HitterAcnt": str(offset + i).zfill(10),
                    "HitterName": f"打者{offset + i}",
                    "DefendStation": pos,
                }
                for i, pos in enumerate(POSITIONS, 1)
            ],
        }

    raw = {
        "GameId": "2026-E-4",
        "GameSno": 4,
        "KindCode": "E",
        "PreExeDate": "2026-10-12T17:05:00",
        "GameStatus": status,
        "Visiting": team("ACN011", 0),
        "Home": team("ADD011", 10),
    }
    if damage:
        damage(raw)
    payload = project("2026-E-4", raw)
    return {
        "year": 2026,
        "kind_code": "E",
        "game_sno": 4,
        "source_type": "stats_datagame",
        "source_url": "https://stats.cpbl.com.tw/api/proxy/v1/games/2026-E-4",
        "raw_status": status,
        "raw_payload": payload,
        "content_hash": content_hash(payload),
        "fetched_at": T0 + timedelta(minutes=minute),
        "last_seen_at": T0 + timedelta(minutes=minute),
    }


def select(rows, schedules=None):
    return import_module("cpbl.reports.announcements").select(rows, schedules or [], TARGET)


def test_scheduled_same_version_is_independent_per_team_without_fabricating_main_n():
    r = row(damage=lambda raw: raw["Home"]["Hitters"].pop())
    actual = select([r])
    assert actual["status"] == "partial" and actual["source_type"] == "stats_datagame"
    assert actual["team_evidence"]["ACN011"]["status"] == "announced"
    assert actual["team_evidence"]["ADD011"]["status"] == "unverified"
    assert len(actual["items"]) == 9 and "is_play_ball" not in actual.get("pregame_evidence", {})
    assert actual["observed_at"] == r["fetched_at"].isoformat()


def test_first_started_boundary_keeps_real_pregame_fragment_after_late_results():
    initial = row(0)
    changed = row(
        1, damage=lambda raw: raw["Visiting"]["Hitters"][0].update(HitterAcnt="0000000077")
    )
    started = row(2, "START")
    late = row(3)
    final = row(4, "FINISHED")
    actual = select([initial, changed, started, late, final])
    assert actual["source_version"] == changed["content_hash"]
    assert actual["observed_at"] == changed["fetched_at"].isoformat()
    assert (
        actual["team_evidence"]["ACN011"]["first_started_at"] == started["fetched_at"].isoformat()
    )
    assert actual == select(
        [
            {**r, "last_seen_at": T0 + timedelta(days=10)}
            for r in [initial, changed, started, late, final]
        ]
    )


def test_unknown_partial_or_withdrawn_latest_fragment_does_not_fall_back_to_older_full():
    for latest in [
        row(1, damage=lambda raw: raw["Visiting"]["Hitters"].clear()),
        row(1, None),
        row(1, "POSTPONED"),
    ]:
        actual = select([row(0), latest])
        assert actual["team_evidence"]["ACN011"]["status"] == "unverified"
        assert not any(i["team_code"] == "ACN011" for i in actual["items"])


def test_first_content_and_first_status_do_not_replace_selected_scheduled_segment_time():
    unknown = row(0, None)
    scheduled = row(1)
    changed = row(
        2, damage=lambda raw: raw["Visiting"]["Hitters"][0].update(HitterAcnt="0000000077")
    )
    reappeared = row(3)
    actual = select([unknown, scheduled, changed, reappeared])
    evidence = actual["team_evidence"]["ACN011"]
    assert evidence["fetched_at"] == reappeared["fetched_at"].isoformat()
    assert evidence["first_content_at"] == unknown["fetched_at"].isoformat()
    assert evidence["first_status_at"] == scheduled["fetched_at"].isoformat()
    assert actual["observed_at"] == reappeared["fetched_at"].isoformat()


@pytest.mark.parametrize(
    "damage",
    [
        lambda raw: raw["Visiting"]["Hitters"][0].update(HitterAcnt="bad"),
        lambda raw: raw["Visiting"]["Hitters"][0].update(
            HitterAcnt=raw["Visiting"]["Hitters"][1]["HitterAcnt"]
        ),
        lambda raw: raw["Visiting"]["Hitters"][0].update(Lineup=2),
        lambda raw: raw["Visiting"]["Hitters"][0].update(DefendStation="RF(CF)"),
        lambda raw: raw["Visiting"]["Hitters"][0].update(DefendStation="(PR)(DH)"),
        lambda raw: raw["Visiting"]["Team"].update(Code="unknown"),
    ],
)
def test_ambiguous_ids_orders_positions_or_target_team_never_announce(damage):
    actual = select([row(damage=damage)])
    assert actual["team_evidence"]["ACN011"]["status"] == "unverified"


def test_main_first_start_and_stats_reserved_are_both_started_evidence_not_postponed():
    main = {
        "year": 2026,
        "kind_code": "E",
        "game_sno": 4,
        "is_play_ball": "Y",
        "raw_game_result": "",
        "fetched_at": T0 + timedelta(seconds=30),
        "payload_hash": "main-v",
    }
    actual = select([row(0), row(1)], [main])
    assert actual["source_version"] == row(0)["content_hash"]
    assert select([row(1), row(0, "RESERVED")])["status"] == "unverified"
    assert select([row(0, "POSTPONED"), row(1)])["status"] == "announced"


def test_untrusted_clock_or_corrupt_source_evidence_stays_unknown():
    for bad in [{**row(), "fetched_at": T0.replace(tzinfo=None)}, {**row(), "content_hash": "bad"}]:
        assert select([bad])["status"] == "unverified"
    main = {
        "year": 2026,
        "kind_code": "E",
        "game_sno": 4,
        "is_play_ball": "Y",
        "fetched_at": T0.replace(tzinfo=None),
    }
    assert select([row()], [main])["status"] == "unverified"


def test_unknown_latest_version_still_changes_context_material_and_keeps_started_boundary():
    module = import_module("cpbl.reports.announcements")
    unknown1 = row(1, None)
    unknown2 = row(
        2, None, damage=lambda raw: raw["Home"]["Hitters"][0].update(HitterAcnt="0000000077")
    )
    before = module.context_materials([unknown1], [], [TARGET])
    after = module.context_materials([unknown1, unknown2], [], [TARGET])
    assert before != after and after[0]["lineup"]["status"] == "unverified"
    started = row(0, "START")
    assert (
        select([started, row(1)])["team_evidence"]["ACN011"]["first_started_at"] == T0.isoformat()
    )


def test_later_result_or_started_observation_does_not_change_selected_material():
    module = import_module("cpbl.reports.announcements")
    baseline = [row(0), row(1, "START")]
    later = [*baseline, row(2, "FINISHED"), row(3)]
    assert module.context_materials(baseline, [], [TARGET]) == module.context_materials(
        later, [], [TARGET]
    )
