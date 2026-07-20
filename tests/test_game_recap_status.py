from __future__ import annotations

from datetime import UTC, date, datetime

from cpbl.api.routers.games import _build_game_status

_OBSERVED_AT = datetime(2026, 7, 20, 1, 0, tzinfo=UTC)


def _schedule(present_status: int, game_result: str, game_date: date) -> dict:
    return {
        "raw_present_status": present_status,
        "raw_game_result": game_result,
        "raw_game_date": game_date,
        "raw_pre_exe_date": game_date,
        "last_seen_at": _OBSERVED_AT,
    }


def _source(source: str, outcome: str, *, complete: bool | None = None) -> dict:
    detail = {} if complete is None else {"game_level_complete": complete}
    return {
        "source": source,
        "outcome": outcome,
        "row_count": 1 if outcome == "available" else 0,
        "error_code": "http_428" if outcome == "error" else None,
        "detail": detail,
        "fetched_at": _OBSERVED_AT,
        "last_seen_at": _OBSERVED_AT,
    }


def test_official_status_uses_raw_schedule_vocabulary_not_score() -> None:
    final_zero_zero = _build_game_status(
        [_schedule(1, "0", date(2026, 7, 19))],
        {},
    )
    scheduled = _build_game_status(
        [_schedule(1, "", date(2026, 9, 22))],
        {},
    )
    postponed = _build_game_status(
        [_schedule(0, "1", date(2026, 4, 4))],
        {},
    )

    assert final_zero_zero["official_game_status"]["status"] == "final"
    assert scheduled["official_game_status"]["status"] == "scheduled"
    assert postponed["official_game_status"]["status"] == "postponed"


def test_rescheduled_game_prefers_active_official_entry() -> None:
    result = _build_game_status(
        [
            _schedule(0, "1", date(2026, 4, 4)),
            _schedule(1, "0", date(2026, 4, 10)),
        ],
        {},
    )

    assert result["official_game_status"]["status"] == "final"


def test_unobserved_cancel_and_held_game_fail_closed() -> None:
    held = _build_game_status([_schedule(0, "2", date(2026, 6, 7))], {})
    unobserved = _build_game_status([_schedule(0, "3", date(2026, 6, 8))], {})

    assert held["official_game_status"]["status"] == "unknown"
    assert unobserved["official_game_status"]["status"] == "unknown"


def test_final_scoreboard_without_livelog_is_pending_refresh() -> None:
    result = _build_game_status(
        [_schedule(1, "0", date(2026, 7, 19))],
        {
            "scoreboard": _source("scoreboard", "available"),
            "livelog": _source("livelog", "missing"),
        },
    )

    assert result["play_by_play_availability"]["status"] == "pending_refresh"


def test_successful_empty_sources_are_source_missing() -> None:
    result = _build_game_status(
        [_schedule(1, "0", date(2026, 7, 19))],
        {
            "scoreboard": _source("scoreboard", "missing"),
            "livelog": _source("livelog", "missing"),
        },
    )

    assert result["play_by_play_availability"]["status"] == "source_missing"


def test_livelog_error_is_not_collapsed_into_missing() -> None:
    result = _build_game_status(
        [_schedule(1, "0", date(2026, 7, 19))],
        {"livelog": _source("livelog", "error")},
    )

    assert result["play_by_play_availability"]["status"] == "source_error"


def test_scheduled_and_postponed_games_are_not_applicable() -> None:
    scheduled = _build_game_status(
        [_schedule(1, "", date(2026, 9, 22))],
        {},
    )
    postponed = _build_game_status(
        [_schedule(0, "1", date(2026, 4, 4))],
        {},
    )

    assert scheduled["play_by_play_availability"]["status"] == "not_applicable"
    assert postponed["play_by_play_availability"]["status"] == "not_applicable"


def test_advanced_freshness_requires_game_level_completion_evidence() -> None:
    aggregate_only = _build_game_status(
        [_schedule(1, "0", date(2026, 7, 19))],
        {"advanced": _source("advanced", "available", complete=False)},
    )
    late = _build_game_status(
        [_schedule(1, "0", date(2026, 7, 19))],
        {"advanced": _source("advanced", "missing", complete=False)},
    )
    failed = _build_game_status(
        [_schedule(1, "0", date(2026, 7, 19))],
        {"advanced": _source("advanced", "error", complete=False)},
    )

    assert aggregate_only["advanced_freshness"]["status"] == "unknown"
    assert late["advanced_freshness"]["status"] == "pending"
    assert failed["advanced_freshness"]["status"] == "source_error"
