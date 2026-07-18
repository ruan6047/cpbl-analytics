from scripts.audit_game_recap_data import (
    classify_tracking_availability,
    legacy_pa_starts,
    pitch_linkage_risks,
)


def _event(
    no: int,
    hitter: str | None,
    *,
    inning: int = 1,
    half: str = "1",
    order: int | None = 1,
    pitcher: str = "P1",
    change: bool = False,
) -> dict:
    return {
        "main_event_no": str(no),
        "inning_seq": inning,
        "visiting_home_type": half,
        "batting_order": order,
        "hitter_acnt": hitter,
        "pitcher_acnt": pitcher,
        "is_change_player": change,
    }


def test_legacy_run_dist_and_wp_collapse_a_lineup_turnover_in_one_half_inning() -> None:
    events = [_event(i, f"H{i}", order=i) for i in range(1, 10)]
    events.append(_event(10, "H1", order=1))

    starts = legacy_pa_starts(events)

    assert len(starts["run_dist"]) == 9
    assert len(starts["winprob"]) == 9
    assert len(starts["frontend"]) == 10
    assert starts["frontend"][-1] == "10"


def test_legacy_groupers_split_a_mid_plate_appearance_pinch_hitter() -> None:
    events = [
        _event(1, "H1", order=4),
        _event(2, None, order=4, change=True),
        _event(3, "PH1", order=4),
    ]

    starts = legacy_pa_starts(events)

    assert starts == {
        "run_dist": ["1", "3"],
        "winprob": ["1", "3"],
        "frontend": ["1", "3"],
    }


def test_pitch_triple_is_ambiguous_when_same_matchup_repeats_in_an_inning() -> None:
    pa_starts = [
        _event(1, "H1", order=1),
        _event(10, "H1", order=1),
        _event(20, "H2", order=2),
    ]

    risks = pitch_linkage_risks(pa_starts)

    assert risks.ambiguous_keys == 1
    assert risks.ambiguous_plate_appearances == 2
    assert risks.unique_keys == 1


def test_tracking_gap_distinguishes_unobserved_equipment_from_expected_missing() -> None:
    assert classify_tracking_availability(
        game_started=False, game_pitch_count=0, venue_tracked_games=0
    ) == "not_expected_yet"
    assert classify_tracking_availability(
        game_started=True, game_pitch_count=0, venue_tracked_games=0
    ) == "equipment_unobserved"
    assert classify_tracking_availability(
        game_started=True, game_pitch_count=0, venue_tracked_games=3
    ) == "expected_missing"
    assert classify_tracking_availability(
        game_started=True, game_pitch_count=120, venue_tracked_games=3
    ) == "available"
