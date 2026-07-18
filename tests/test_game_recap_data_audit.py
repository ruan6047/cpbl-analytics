from scripts.audit_game_recap_data import (
    audit_game_events,
    classify_tracking_availability,
    frontend_moment_groups,
    legacy_pa_starts,
    pitch_linkage_risks,
    render_report,
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
    assert len(starts["frontend"]) == 9
    assert "10" not in starts["frontend"]


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
    assert frontend_moment_groups(events) == [("1", "1"), ("3", "3")]


def test_frontend_moment_skips_a_pitching_change_inside_one_plate_appearance() -> None:
    events = [
        _event(1, "H1"),
        {**_event(2, None, change=True), "content": "更換投手"},
        _event(3, "H1", pitcher="P2"),
        _event(4, "H2", order=2, pitcher="P2"),
    ]

    assert frontend_moment_groups(events) == [("1", "3"), ("4", "4")]


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
        game_started=False, game_pitch_count=0, scope_tracked_games=0, venue_tracked_games=0
    ) == "not_expected_yet"
    assert classify_tracking_availability(
        game_started=True, game_pitch_count=0, scope_tracked_games=0, venue_tracked_games=0
    ) == "source_not_collected"
    assert classify_tracking_availability(
        game_started=True, game_pitch_count=0, scope_tracked_games=3, venue_tracked_games=0
    ) == "equipment_unobserved"
    assert classify_tracking_availability(
        game_started=True, game_pitch_count=0, scope_tracked_games=3, venue_tracked_games=3
    ) == "expected_missing"
    assert classify_tracking_availability(
        game_started=True, game_pitch_count=120, scope_tracked_games=3, venue_tracked_games=3
    ) == "available"


def test_game_audit_keeps_denominators_and_risk_flags_separate() -> None:
    events = [_event(i, f"H{i}", order=i) for i in range(1, 10)]
    events.extend(
        [
            _event(10, "H1", order=1),
            {**_event(11, None, change=True), "content": "更換投手"},
            {**_event(12, "H2", order=2), "action_name": ""},
        ]
    )

    result = audit_game_events(events, box_pa=11)

    assert result.box_pa == 11
    assert result.run_dist_pa == 9
    assert result.winprob_pa == 9
    assert result.frontend_pa == 9
    assert result.blank_action_rows == 11
    assert result.change_rows == 1
    assert result.pitching_change_rows == 1
    assert result.repeated_matchup_keys == 2


def test_report_is_an_obsidian_note_and_states_the_canonical_no_go() -> None:
    report = {
        "parameters": {"from_year": 2018, "to_year": 2026, "kinds": ["A"], "as_of": "2026-07-19"},
        "coverage_by_year_kind": [],
        "coverage_by_year_kind_venue": [],
        "pa_by_year_kind": [],
        "present_status_counts": [],
        "source_totals": {"scheduled_games": 1, "started_games": 1, "scoreboard_rows": 18, "livelog_rows": 300, "box_pa": 75, "tracking_pitches": 0},
        "tracking_classes": {},
        "tracking_linkage": {"pitches": 0, "unique_pitches": 0, "ambiguous_pitches": 0, "unmatched_pitches": 0, "samples": []},
        "actions": [],
        "edge_cases": {"zero_zero": [], "extra_inning": [], "tie": [], "delayed_or_retained": [], "mismatch": [], "grouping_risks": [], "blank_action": []},
        "refresh_rows": [],
        "relation_sizes": [],
        "elapsed_seconds": 0.1,
        "generated_at": "2026-07-19T02:00:00+08:00",
    }

    text = render_report(report)

    assert text.startswith("---\n")
    assert "[[GAME_RECAP_PRODUCT_SPEC]]" in text
    assert "[[GAME-RECAP-DATA1]]" in text
    assert "canonical PA：NO-GO" in text
    assert "## 覆蓋矩陣" in text
    assert "## canonical 資料契約" in text
    assert "## 物化決策" in text
    assert "候選物化列數：75" in text
