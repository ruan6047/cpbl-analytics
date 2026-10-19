"""純分類證據，不接資料庫、Redis 或官網。"""
from copy import deepcopy
from datetime import UTC, datetime, timedelta

import pytest

from cpbl.readiness_checks import (
    inspect_partition,
    inspect_snapshot,
    reconcile_snapshot,
    summarize_delivery,
)

NOW = datetime(2026, 10, 19, 10, tzinfo=UTC)


def snapshot():
    return {
        "game_id": "2026-E-1", "game_sno": 1, "kind_code": "E",
        "starts_at": "2026-10-19T18:35:00", "phase": "live",
        "away": {"team": {"code": "AAA"}, "score": 0},
        "home": {"team": {"code": "BBB"}, "score": 0},
        "livelog": [], "event_count": 0,
        "source": {"version": "a" * 64, "fetched_at": NOW.isoformat()},
    }


@pytest.mark.parametrize("payload", [{}, {"Data": None}, {"Data": {}},
    {"Data": {"Games": None}}, {"Data": {"Games": {}}},
    {"Data": {"Games": ""}}, None, []])
def test_missing_or_malformed_partition_is_unknown(payload):
    result = inspect_partition(payload, year=2026, month=10, kind="E")
    assert result["state"] == "unknown"
    assert result["explicit_list"] is False


def test_explicit_empty_partition_is_complete():
    result = inspect_partition({"Data": {"Games": []}}, year=2026, month=10, kind="E")
    assert result["state"] == "complete"
    assert result["row_count"] == 0


def test_partition_detects_identity_time_and_wrong_partition_without_mutation():
    rows = [
        {"GameId": "2026-E-1", "PreExeDate": "2026-10-19T18:35:00"},
        {"GameId": "2026-C-2", "PreExeDate": "2026-10-19T18:35:00"},
        {"GameId": "2026-E-3", "GameSno": 4, "PreExeDate": None},
        "invalid",
    ]
    payload = {"Data": {"Games": rows}}
    before = deepcopy(payload)
    result = inspect_partition(payload, year=2026, month=10, kind="E")
    assert result["state"] == "unknown"
    assert result["invalid_identity_count"] == 3
    assert result["invalid_time_count"] == 2
    assert payload == before


def test_zero_scores_and_optional_missing_values_are_valid():
    assert inspect_snapshot(snapshot(), expected_id="2026-E-1", now=NOW)["state"] == "complete"


@pytest.mark.parametrize("key,value", [("phase", "unknown"), ("game_sno", 2),
    ("starts_at", None), ("livelog", None), ("livelog", ["bad"]),
    ("source", {}), ("kind_code", "A")])
def test_required_snapshot_fields_cannot_be_inferred(key, value):
    value_snapshot = snapshot()
    value_snapshot[key] = value
    assert inspect_snapshot(value_snapshot, expected_id="2026-E-1", now=NOW)["state"] == "unknown"


@pytest.mark.parametrize("score", [None, -1, True, "0", 1.5])
def test_live_scores_must_be_nonnegative_integers(score):
    value = snapshot()
    value["home"]["score"] = score
    assert inspect_snapshot(value, expected_id="2026-E-1", now=NOW)["state"] == "unknown"


def test_future_source_timestamp_is_unknown():
    value = snapshot()
    value["source"]["fetched_at"] = (NOW + timedelta(seconds=1)).isoformat()
    assert inspect_snapshot(value, expected_id="2026-E-1", now=NOW)["state"] == "unknown"


def test_readback_ignores_separate_health_annotations_but_not_projection_changes():
    expected = snapshot()
    actual = deepcopy(expected)
    actual["source"]["last_error_type"] = "ReadTimeout"
    assert reconcile_snapshot(expected, actual)
    actual["home"]["score"] = 1
    assert not reconcile_snapshot(expected, actual)


def test_delivery_cannot_count_duplicates_or_missing_selected_as_complete():
    expected = ["2026-E-1", "2026-E-2"]
    assert summarize_delivery(expected, [
        {"game_id": "2026-E-1", "disposition": "write_readback"},
        {"game_id": "2026-E-1", "disposition": "reused_final"},
    ])["state"] == "unknown"


def test_delivery_accepts_only_the_three_verified_terminal_dispositions():
    expected = ["2026-E-1", "2026-E-2", "2026-E-3"]
    records = [{"game_id": game_id, "disposition": action} for game_id, action in zip(
        expected, ["write_readback", "reused_final", "moved_out_of_window"], strict=True)]
    assert summarize_delivery(expected, records)["state"] == "complete"
    records[-1]["disposition"] = "failed"
    assert summarize_delivery(expected, records)["state"] == "partial"
    assert summarize_delivery([], [], overflow_count=1)["state"] == "partial"
    assert summarize_delivery([], [])["state"] == "complete"
