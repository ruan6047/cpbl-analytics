from __future__ import annotations

from cpbl.models.umpire_impact_data import LINKED_CALLED_CTE, TrackingAudit


def _norm(sql: str) -> str:
    return " ".join(sql.split())


def test_linker_uses_full_state_and_call_flag_without_arbitrary_row_selection() -> None:
    sql = _norm(LINKED_CALLED_CTE)

    for field in (
        "pitcher_acnt",
        "hitter_acnt",
        "inning_seq",
        "batting_order",
        "pitch_cnt",
        "ball_cnt",
        "strike_cnt",
        "out_cnt",
    ):
        assert f"l.{field} = t.{field}" in sql
    assert "t.pitch_call = 'BallCalled' AND l.is_ball" in sql
    assert "t.pitch_call = 'StrikeCalled' AND l.is_strike" in sql
    assert "row_number()" not in sql.lower()


def test_tracking_audit_fails_closed_at_spec_thresholds() -> None:
    passing = TrackingAudit(
        total_called=24_270,
        located_called=24_270,
        unique_linked=24_195,
        valid_post_count=24_226,
        linked_missing_context=0,
    )
    low_link = TrackingAudit(1_000, 1_000, 994, 1_000, 0)
    low_count = TrackingAudit(1_000, 1_000, 1_000, 994, 0)
    missing_context = TrackingAudit(1_000, 1_000, 1_000, 1_000, 1)

    assert passing.passes
    assert not low_link.passes
    assert not low_count.passes
    assert not missing_context.passes
    assert passing.link_rate == 24_195 / 24_270
    assert passing.valid_count_rate == 24_226 / 24_270


def test_tracking_audit_fails_when_no_called_pitches_exist() -> None:
    audit = TrackingAudit(0, 0, 0, 0, 0)

    assert audit.link_rate == 0.0
    assert audit.valid_count_rate == 0.0
    assert not audit.passes
