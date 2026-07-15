from __future__ import annotations

import pytest

from cpbl.models.pa_sim import (
    PAEvent,
    audit_pa_events,
    build_pa_snapshots,
    classify_action,
    events_from_rows,
)


@pytest.mark.parametrize(
    ("action", "expected"),
    [
        ("三振", "K"),
        ("不死三振", "K"),
        ("四壞", "BB_HBP"),
        ("死球", "BB_HBP"),
        ("一安", "1B"),
        ("二安", "XBH"),
        ("場三", "XBH"),
        ("全打", "HR"),
        ("雙殺", "BIP_OUT"),
        ("犧飛", "BIP_OUT"),
        ("游失", "OTHER_REACH"),
        ("野選", "OTHER_REACH"),
        ("礙打", "OTHER_REACH"),
    ],
)
def test_classify_action_returns_mutually_exclusive_outcomes(action: str, expected: str):
    assert classify_action(action) == expected


def test_classify_action_fails_closed_for_unknown_action():
    assert classify_action("未來新增詞彙") is None
    assert classify_action(None) is None


def test_build_pa_snapshots_uses_next_plate_appearance_as_post_state():
    events = [
        PAEvent(1, 1, "1", "h1", "p1", "___", 0, 0, 0, None),
        PAEvent(2, 1, "1", "h1", "p1", "___", 0, 0, 0, "一安"),
        PAEvent(3, 1, "1", "h2", "p1", "1__", 0, 0, 0, None),
        PAEvent(4, 1, "1", "h2", "p1", "1__", 0, 0, 0, "雙殺"),
        PAEvent(5, 1, "1", "h3", "p1", "___", 2, 0, 0, None),
    ]

    snapshots = build_pa_snapshots(events)

    assert snapshots[0].result == "1B"
    assert snapshots[0].before.bases == "___"
    assert snapshots[0].after.bases == "1__"
    assert snapshots[1].result == "BIP_OUT"
    assert snapshots[1].after.outs == 2


def test_build_pa_snapshots_marks_half_inning_transition():
    events = [
        PAEvent(1, 1, "1", "h1", "p1", "12_", 2, 0, 0, "一滾"),
        PAEvent(2, 1, "2", "h2", "p2", "___", 0, 0, 0, None),
    ]

    snapshot = build_pa_snapshots(events)[0]

    assert snapshot.inning_ended is True
    assert snapshot.after.inning == 1
    assert snapshot.after.half == "2"
    assert snapshot.after.bases == "___"
    assert snapshot.after.outs == 0


def test_build_pa_snapshots_does_not_guess_last_pa_without_post_state():
    events = [PAEvent(1, 9, "2", "h1", "p1", "___", 2, 3, 3, "全打")]

    assert build_pa_snapshots(events) == []


def test_build_pa_snapshots_uses_final_score_for_terminal_pa():
    events = [PAEvent(1, 9, "2", "h1", "p1", "___", 2, 3, 3, "全打")]

    snapshot = build_pa_snapshots(events, final_score=(3, 4))[0]

    assert snapshot.game_ended is True
    assert snapshot.runs_delta == 1
    assert snapshot.after.away_score == 3
    assert snapshot.after.home_score == 4


def test_audit_pa_events_reports_unknown_actions_and_rebuild_rate():
    events = [
        PAEvent(1, 1, "1", "h1", "p1", "___", 0, 0, 0, "一安"),
        PAEvent(2, 1, "1", "h2", "p1", "1__", 0, 0, 0, "未來新增詞彙"),
    ]

    audit = audit_pa_events(events, final_score=(0, 0))

    assert audit.total_pa == 2
    assert audit.classified_pa == 1
    assert audit.rebuilt_pa == 1
    assert audit.unknown_actions == {"未來新增詞彙": 1}
    assert audit.classification_rate == 0.5


def test_events_from_rows_converts_post_event_score_to_pre_event_score():
    rows = [
        {
            "event_no": 1, "inning": 1, "half": "1", "hitter": "h1", "pitcher": "p1",
            "first_base": None, "second_base": None, "third_base": None, "outs": 0,
            "post_away": 1, "post_home": 0, "action": "全打",
        },
        {
            "event_no": 2, "inning": 1, "half": "1", "hitter": "h2", "pitcher": "p1",
            "first_base": None, "second_base": None, "third_base": None, "outs": 0,
            "post_away": 1, "post_home": 0, "action": None,
        },
    ]

    events = events_from_rows(rows)

    assert (events[0].away_score, events[0].home_score) == (0, 0)
    assert (events[1].away_score, events[1].home_score) == (1, 0)
