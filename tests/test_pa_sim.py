from __future__ import annotations

from datetime import date

import pytest

from cpbl.models.pa_sim import (
    GameState,
    PAAudit,
    PAEvent,
    PASnapshot,
    Transition,
    assert_audit_coverage,
    audit_pa_events,
    build_pa_snapshots,
    classify_action,
    events_from_rows,
    fit_empirical_bayes,
    fit_transition_kernel,
    load_pa_artifact,
    predict_outcomes,
    resolve_pa_event_no,
    save_pa_artifact,
    simulate_plate_appearance,
    train_pa_artifact,
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


def test_events_from_rows_skips_change_player_but_keeps_score_progression():
    rows = [
        {
            "event_no": 1, "inning": 7, "half": "2", "hitter": "replaced",
            "pitcher": "old-pitcher", "first_base": None, "second_base": None,
            "third_base": None, "outs": 2, "post_away": 3, "post_home": 2,
            "action": "一滾", "is_change_player": True,
        },
        {
            "event_no": 2, "inning": 7, "half": "2", "hitter": "pinch-hitter",
            "pitcher": "new-pitcher", "first_base": None, "second_base": None,
            "third_base": None, "outs": 0, "post_away": 3, "post_home": 2,
            "action": "一滾", "is_change_player": False,
        },
    ]

    events = events_from_rows(rows)

    assert len(events) == 1
    assert events[0].hitter == "pinch-hitter"
    assert (events[0].away_score, events[0].home_score) == (3, 2)


def test_resolve_pa_event_no_maps_change_announcement_to_next_real_pa():
    rows = [
        {"event_no": 1000, "inning": 7, "half": "2", "hitter": "replaced",
         "pitcher": "old", "is_change_player": True},
        {"event_no": 2000, "inning": 7, "half": "2", "hitter": "pinch",
         "pitcher": "new", "is_change_player": True},
        {"event_no": 3000, "inning": 7, "half": "2", "hitter": "pinch",
         "pitcher": "new", "is_change_player": False},
    ]

    assert resolve_pa_event_no(rows, 1000) == 3000
    assert resolve_pa_event_no(rows, 3000) == 3000
    assert resolve_pa_event_no(rows, 9999) is None


def test_audit_counts_missing_action_and_invalid_state_as_unrebuilt():
    events = [
        PAEvent(1, 1, "1", "h1", "p1", "___", 2, 0, 0, "一滾"),
        PAEvent(2, 1, "1", "h2", "p1", "___", 1, 0, 0, "一安"),
        PAEvent(3, 1, "1", "h3", "p1", "1__", 1, 0, 0, None),
    ]

    audit = audit_pa_events(events, final_score=(0, 0))

    assert audit.total_pa == 3
    assert audit.classified_pa == 2
    assert audit.rebuilt_pa == 1
    assert audit.missing_action_pa == 1
    assert audit.state_errors == {"outs_regressed": 1}


def test_build_pa_snapshots_uses_first_known_out_count_after_control_event():
    rows = [
        {"event_no": 1, "inning": 4, "half": "2", "hitter": "h1", "pitcher": "p",
         "first_base": None, "second_base": None, "third_base": None, "outs": 1,
         "post_away": 0, "post_home": 0, "action": "一安"},
        {"event_no": 2, "inning": 4, "half": "2", "hitter": "h2", "pitcher": "p",
         "first_base": "runner", "second_base": None, "third_base": None, "outs": None,
         "post_away": 0, "post_home": 0, "action": "游滾"},
        {"event_no": 3, "inning": 4, "half": "2", "hitter": "h2", "pitcher": "p",
         "first_base": "runner", "second_base": None, "third_base": None, "outs": 1,
         "post_away": 0, "post_home": 0, "action": "游滾"},
        {"event_no": 4, "inning": 4, "half": "2", "hitter": "h3", "pitcher": "p",
         "first_base": "runner2", "second_base": None, "third_base": None, "outs": 1,
         "post_away": 0, "post_home": 0, "action": "四壞"},
    ]

    audit = audit_pa_events(events_from_rows(rows), final_score=(0, 0))

    assert audit.rebuilt_pa == 3
    assert audit.state_errors == {}


def test_audit_rejects_full_bases_walk_without_forced_advance():
    events = [
        PAEvent(1, 2, "2", "h1", "p", "123", 0, 1, 0, "四壞"),
        PAEvent(2, 2, "2", "h2", "p", "123", 0, 1, 0, "內飛"),
    ]

    audit = audit_pa_events(events, final_score=(1, 0))

    assert audit.rebuilt_pa == 1
    assert audit.state_errors == {"forced_advance_missing": 1}


def test_assert_audit_coverage_checks_box_plate_appearance_reconciliation():
    audits = {2025: PAAudit(100, 100, 100, {}, box_pa=98)}

    with pytest.raises(RuntimeError, match="box_delta=2.041%"):
        assert_audit_coverage(audits, minimum=0.99)


def test_snapshot_carries_game_metadata_for_time_cutoff():
    events = [
        PAEvent(1, 1, "1", "h1", "p1", "___", 0, 0, 0, "一安",
                year=2025, game_sno=7, game_date=date(2025, 4, 1)),
        PAEvent(2, 1, "1", "h2", "p1", "1__", 0, 0, 0, None,
                year=2025, game_sno=7, game_date=date(2025, 4, 1)),
    ]

    snapshot = build_pa_snapshots(events)[0]

    assert snapshot.year == 2025
    assert snapshot.game_sno == 7
    assert snapshot.game_date == date(2025, 4, 1)


def test_assert_audit_coverage_fails_closed_below_threshold():
    audits = {2025: PAAudit(100, 98, 98, {"未知": 2})}

    with pytest.raises(RuntimeError, match="2025.*classification=98.000%.*rebuild=98.000%"):
        assert_audit_coverage(audits, minimum=0.99)


def _snapshot(result: str, hitter: str = "h1", pitcher: str = "p1") -> PASnapshot:
    before = GameState(1, "1", "___", 0, 0, 0)
    after = GameState(1, "1", "___", 1, 0, 0)
    return PASnapshot(1, hitter, pitcher, result, before, after, 0, False, False, year=2024)


def test_empirical_bayes_probabilities_are_mutually_exclusive_and_normalized():
    model = fit_empirical_bayes([
        _snapshot("K"), _snapshot("K"), _snapshot("HR"),
        _snapshot("1B", "h2", "p2"), _snapshot("BIP_OUT", "h2", "p2"),
    ], hitter_strength=2, pitcher_strength=2, direct_strength=3)

    probabilities = predict_outcomes(model, "h1", "p1")

    assert set(probabilities) == {"K", "BB_HBP", "1B", "XBH", "HR", "BIP_OUT", "OTHER_REACH"}
    assert sum(probabilities.values()) == pytest.approx(1.0)
    assert all(probability > 0 for probability in probabilities.values())


def test_empirical_bayes_unseen_players_fall_back_to_league_distribution():
    model = fit_empirical_bayes([_snapshot("K"), _snapshot("HR", "h2", "p2")])

    assert predict_outcomes(model, "rookie", "new-pitcher") == pytest.approx(model.league)


def test_transition_kernel_uses_exact_state_then_falls_back():
    snapshots = [
        PASnapshot(1, "h", "p", "1B", GameState(1, "1", "___", 0, 0, 0),
                   GameState(1, "1", "1__", 0, 0, 0), 0, False, False),
        PASnapshot(2, "h", "p", "1B", GameState(1, "1", "12_", 1, 0, 0),
                   GameState(1, "1", "123", 1, 0, 0), 0, False, False),
    ]
    kernel = fit_transition_kernel(snapshots)

    exact, exact_level, exact_n = kernel.distribution("1B", "___", 0)
    fallback, fallback_level, fallback_n = kernel.distribution("1B", "_2_", 0)

    assert exact_level == "result+bases+outs"
    assert exact_n == 1
    assert exact == [(Transition(0, "1__", 0, False), 1.0)]
    assert fallback_level == "result+outs"
    assert fallback_n == 1
    assert sum(probability for _, probability in fallback) == pytest.approx(1.0)


def test_simulate_plate_appearance_walkoff_does_not_call_future_wp():
    training = [
        PASnapshot(1, "h", "p", "HR", GameState(9, "2", "___", 1, 2, 2),
                   GameState(9, "2", "___", 1, 2, 3), 1, False, False),
    ]
    for index, outcome in enumerate(("K", "BB_HBP", "1B", "XBH", "BIP_OUT", "OTHER_REACH"), 2):
        training.append(PASnapshot(
            index, "h", "p", outcome, GameState(9, "2", "___", 1, 2, 2),
            GameState(9, "2", "___", 2, 2, 2), 0, False, False,
        ))
    model = fit_empirical_bayes(training)
    kernel = fit_transition_kernel(training)

    result = simulate_plate_appearance(
        model, kernel, "h1", "p1", GameState(9, "2", "___", 1, 2, 2),
        lambda _: 0.25,
    )

    assert result["outcomes"]["HR"]["win_probability"] == 1.0
    assert 0.0 <= result["weighted_win_probability"] <= 1.0


def test_pa_artifact_round_trip_preserves_metadata_and_probabilities(tmp_path):
    training = [_snapshot(outcome) for outcome in (
        "K", "BB_HBP", "1B", "XBH", "HR", "BIP_OUT", "OTHER_REACH",
    )]
    artifact = train_pa_artifact(training, trained_through=2024, strengths=(10, 20, 30))
    path = tmp_path / "pa-sim.joblib"

    save_pa_artifact(artifact, path)
    restored = load_pa_artifact(path)

    assert restored["trained_through"] == 2024
    assert restored["strengths"] == (10, 20, 30)
    assert predict_outcomes(restored["model"], "h1", "p1") == pytest.approx(
        predict_outcomes(artifact["model"], "h1", "p1")
    )
