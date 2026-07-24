"""GAME-RECAP-PA1-TAXONOMY1 純函式不變量測試（無 DB 依賴）。

覆蓋：island 分類 fail-closed 分區、taxonomy 自洽、客觀效果剖面計算、
矛盾偵測、island 邊界（同局重複打者/換投/換人附掛）、版本化 JSON 契約。
"""

from __future__ import annotations

from scripts.pa_transition_taxonomy import (
    EXPECTED_SIGNAL,
    TAXONOMY_VERSION,
    TERMINAL_TAXONOMY,
    _action_profiles,
    _classification_summary,
    _classify_island,
    _island_starts,
    _taxonomy_contradictions,
    build_taxonomy_json,
    render,
)


def _island(
    *,
    term_action: str,
    distinct_pitches: int = 4,
    rows: int = 4,
    scored: bool = False,
    batter_out: bool = False,
    hit: bool = False,
    walk_hbp: bool = False,
    reach_error: bool = False,
    term_ban: str = "",
    year: int = 2026,
    kind: str = "A",
    game: int = 1,
) -> dict:
    return {
        "year": year,
        "kind_code": kind,
        "game_sno": game,
        "isl_id": 1,
        "rows": rows,
        "distinct_pitches": distinct_pitches,
        "scored": scored,
        "batter_out": batter_out,
        "hit": hit,
        "walk_hbp": walk_hbp,
        "reach_error": reach_error,
        "term_action": term_action,
        "term_ban": term_ban,
        "term_content": "",
        "inning_seq": 1,
    }


# --- taxonomy 自洽 --------------------------------------------------------
def test_every_outcome_family_has_expected_signal() -> None:
    families = {e["outcome_family"] for e in TERMINAL_TAXONOMY.values()}
    for family in families:
        assert family in EXPECTED_SIGNAL, f"{family} 缺 EXPECTED_SIGNAL"


def test_tiebreak_is_the_only_non_pa_action() -> None:
    non_pa = [a for a, e in TERMINAL_TAXONOMY.items() if e["role"] == "non_pa"]
    assert non_pa == ["突破僵局上壘"]


# --- island 分類 fail-closed ---------------------------------------------
def test_completed_pa_for_registered_terminal_action() -> None:
    assert _classify_island(_island(term_action="三振")) == "completed_pa"
    assert _classify_island(_island(term_action="一壘安打")) == "completed_pa"


def test_no_pitch_award_is_still_completed_pa() -> None:
    # 故意四壞球可零投球；不得因無投球被誤判為 ghost。
    assert (
        _classify_island(_island(term_action="故意四壞球", distinct_pitches=0))
        == "completed_pa"
    )


def test_blank_action_with_pitches_is_truncated_fragment() -> None:
    assert (
        _classify_island(_island(term_action="", distinct_pitches=3))
        == "truncated_fragment"
    )


def test_blank_action_without_pitches_is_running_fragment() -> None:
    assert (
        _classify_island(_island(term_action="", distinct_pitches=0))
        == "non_pa_running_fragment"
    )


def test_tiebreak_runner_is_non_pa() -> None:
    assert (
        _classify_island(_island(term_action="突破僵局上壘", distinct_pitches=0))
        == "non_pa_tiebreak"
    )


def test_unregistered_action_fails_closed() -> None:
    assert _classify_island(_island(term_action="外星人降臨")) == "unknown_action"


# --- 客觀效果剖面 ---------------------------------------------------------
def test_action_profile_measures_observed_rates() -> None:
    islands = [
        _island(term_action="三振", batter_out=True, term_ban="三振"),
        _island(term_action="三振", batter_out=True, term_ban="三振"),
        _island(term_action="三振", batter_out=False, term_ban="三振"),
    ]
    profiles = _action_profiles(islands)
    prof = next(p for p in profiles if p.action_name == "三振")
    assert prof.islands == 3
    assert abs(prof.batter_out_rate - 2 / 3) < 1e-9
    assert prof.hit_rate == 0.0


def test_contradiction_detector_flags_mislabeled_out() -> None:
    # 指派 out 卻幾乎沒有 batter_out → 應被標記。
    islands = [_island(term_action="三振", batter_out=False) for _ in range(5)]
    profiles = _action_profiles(islands)
    flagged = _taxonomy_contradictions(profiles)
    assert any(f["action_name"] == "三振" for f in flagged)


def test_correct_labeling_has_no_contradiction() -> None:
    islands = [_island(term_action="一壘安打", hit=True) for _ in range(5)]
    assert _taxonomy_contradictions(_action_profiles(islands)) == []


# --- island 邊界（合成逐球事件） -----------------------------------------
def _ev(no: int, hitter: str | None, *, inning: int = 1, half: str = "1",
        pitcher: str = "P1", change: bool = False) -> dict:
    return {
        "main_event_no": str(no),
        "inning_seq": inning,
        "visiting_home_type": half,
        "hitter_acnt": hitter,
        "pitcher_acnt": pitcher,
        "is_change_player": change,
    }


def test_repeat_batter_same_inning_forms_two_islands() -> None:
    events = [
        _ev(1, "H1"), _ev(2, "H1"),
        _ev(3, "H2"),
        _ev(4, "H1"),  # 同局二度上場
    ]
    islands = _island_starts(events)
    hitters = [isl[0]["hitter_acnt"] for isl in islands]
    assert hitters == ["H1", "H2", "H1"]
    assert len(islands) == 3


def test_pitching_change_stays_one_island() -> None:
    events = [
        _ev(1, "H1", pitcher="P1"),
        {**_ev(2, None, change=True), "content": "更換投手"},
        _ev(3, "H1", pitcher="P2"),  # 換投後同打者
    ]
    islands = _island_starts(events)
    assert len(islands) == 1
    # 換人列附掛於同一 PA
    assert len(islands[0]) == 3


def test_change_row_never_seeds_new_island() -> None:
    events = [
        _ev(1, "H1"),
        {**_ev(2, None, change=True), "content": "更換守備"},
        _ev(3, "H1"),
    ]
    assert len(_island_starts(events)) == 1


# --- classification summary ----------------------------------------------
def test_classification_summary_counts_all_classes() -> None:
    islands = [
        _island(term_action="三振"),
        _island(term_action="", distinct_pitches=2),
        _island(term_action="突破僵局上壘", distinct_pitches=0),
        _island(term_action="外星人降臨"),
    ]
    summary = _classification_summary(islands)
    assert summary["per_class"]["completed_pa"] == 1
    assert summary["per_class"]["truncated_fragment"] == 1
    assert summary["per_class"]["non_pa_tiebreak"] == 1
    assert summary["per_class"]["unknown_action"] == 1
    assert len(summary["unknown_samples"]) == 1


# --- 版本化 JSON 契約 ------------------------------------------------------
def test_taxonomy_json_is_versioned_and_complete() -> None:
    report = {
        "profiles": _action_profiles([_island(term_action="三振", batter_out=True)]),
        "generated_at": "2026-07-24T00:00:00+08:00",
        "parameters": {"from_year": 2018, "to_year": 2026, "kinds": ["A"]},
    }
    doc = build_taxonomy_json(report)
    assert doc["taxonomy_version"] == TAXONOMY_VERSION
    assert {a["action_name"] for a in doc["actions"]} == set(TERMINAL_TAXONOMY)
    assert "island_rule" in doc and "fail_closed" in doc
    assert "unknown_action" in doc["fail_closed"]


def test_render_is_obsidian_note_with_redlight_sections() -> None:
    report = {
        "parameters": {"from_year": 2018, "to_year": 2026, "kinds": ["A"]},
        "taxonomy_version": TAXONOMY_VERSION,
        "island_total": 1,
        "profiles": _action_profiles([_island(term_action="三振", batter_out=True)]),
        "classification": {"per_class": {"completed_pa": 1}, "per_year_kind": {}, "unknown_samples": []},
        "contradictions": [],
        "redlight": {
            "repeat_batter": {"total_scopes": 0, "max_islands": 0, "samples": []},
            "pitching_change": {"total_pas": 0, "max_pitchers": 0, "samples": []},
            "legacy_delta": [],
            "pitch_multiplicity": {"distribution": [], "total_pitch_keys": 0, "multi_row_pitch_keys": 0},
        },
        "elapsed_seconds": 0.1,
        "generated_at": "2026-07-24T00:00:00+08:00",
    }
    text = render(report)
    assert text.startswith("---\n")
    assert "[[GAME-RECAP-PA1]]" in text
    assert "## 紅燈案例" in text
    assert "同局同打者二度上場" in text
    assert "打席中換投" in text
