"""#283 S02 WP2：T0–T5 與正交狀態純函式（注入時鐘；A02／A03 逐案）。

場次身分取自 2026 真實 C 列（兄弟／味全、C1 10/17…）；狀態事件為注入，標「真實事件未發生、未驗證」。
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from cpbl.playoffs import state as st

BRO, DRAGON = "ACN011", "AAA011"
DAY = date(2026, 10, 17)


def _g(sno, day, *, completed=False, official="scheduled", ended=None, observed=None, kind="C"):
    return {"year": 2026, "kind_code": kind, "game_sno": sno, "game_date": day, "completed": completed,
            "official_status": official, "ended_at": ended, "first_observed_final_at": observed}


def _series(status="pending", kind="C", decided_by=None):
    return {"kind_code": kind, "series_status": status, "decided_by_game_key": decided_by,
            "sides": [{"team_code": DRAGON}, {"team_code": BRO}]}


C_ROWS = [_g(1, date(2026, 10, 17)), _g(2, date(2026, 10, 18)), _g(3, date(2026, 10, 20))]
NOW = datetime.fromisoformat("2026-10-16T12:00:00+08:00")
K1, K2 = (2026, "C", 1), (2026, "C", 2)


def _layout(series=None, games=None, *, live=None, starters=None, rosters=None, now=NOW, pending=frozenset()):
    return st.series_layout(series or _series(), games or C_ROWS, live=live or {}, starters=starters or {},
                            rosters=rosters or {}, pending_keys=pending, taipei_day=now.date(), now=now)


def test_t0_warmup_without_rosters_or_starters():
    out = _layout()
    assert (out["layout_state"], out["target_game_key"]["game_sno"]) == ("T0", 1)
    assert out["section_order"] == [1, 2, 3, 4]


def test_t1_first_game_needs_both_rosters_and_both_starters():
    starters = {K1: {DRAGON: "announced", BRO: "announced"}}
    rosters = {DRAGON: "submitted", BRO: "submitted"}
    assert _layout(starters=starters, rosters=rosters)["layout_state"] == "T1"


def test_submitted_rosters_without_starters_is_not_t1():
    """A02：已提交名單但未公布先發 ⇒ 仍是 T0。"""
    out = _layout(rosters={DRAGON: "submitted", BRO: "submitted"})
    assert out["layout_state"] == "T0"


def test_single_side_starter_is_not_locked():
    """A02：單邊公告不得進 T3。"""
    assert _layout(starters={K1: {DRAGON: "announced", BRO: "missing"}})["layout_state"] == "T0"


def test_t3_both_starters_even_when_rosters_missing():
    out = _layout(starters={K1: {DRAGON: "announced", BRO: "changed"}})
    assert (out["layout_state"], out["layout_reason"]) == ("T3", "starters_announced")


def test_missing_rosters_but_live_is_t4():
    """A02：缺名單但 live ⇒ T4。"""
    out = _layout(live={K1: "live"}, now=datetime.fromisoformat("2026-10-17T18:00:00+08:00"))
    assert (out["layout_state"], out["target_status"]) == ("T4", "live")


def _after_g1(**kw):
    return [_g(1, DAY, completed=True, official="final", **kw), *C_ROWS[1:]]


def test_no_end_time_never_opens_window():
    """A02：無 ended_at 也無觀測 final ⇒ basis unknown、不開窗，直接場間 T2。"""
    out = _layout(_series("active"), _after_g1(), now=datetime.fromisoformat("2026-10-17T21:00:00+08:00"))
    assert out["layout_state"] == "T2" and out["window"]["basis"] == "unknown"


def test_observed_final_window_is_marked_observation_basis():
    obs = datetime.fromisoformat("2026-10-17T20:40:00+08:00")
    out = _layout(_series("active"), _after_g1(observed=obs), now=obs + timedelta(minutes=30))
    assert (out["layout_state"], out["layout_reason"]) == ("T4", "post_game_window_observed_final")
    assert out["window"]["basis"] == "observed_final" and out["target_game_key"]["game_sno"] == 1


@pytest.mark.parametrize(("minutes", "expected"), [(59, "T4"), (60, "T2"), (90, "T2")])
def test_trusted_ended_at_window_boundary(minutes, expected):
    end = datetime.fromisoformat("2026-10-17T20:30:00+08:00")
    out = _layout(_series("active"), _after_g1(ended=end, observed=end - timedelta(minutes=5)),
                  now=end + timedelta(minutes=minutes))
    assert out["layout_state"] == expected
    assert out["window"]["basis"] == "ended_at"


def test_next_game_live_beats_previous_window():
    end = datetime.fromisoformat("2026-10-17T20:30:00+08:00")
    out = _layout(_series("active"), _after_g1(ended=end), live={K2: "live"}, now=end + timedelta(minutes=10))
    assert (out["layout_reason"], out["target_game_key"]["game_sno"]) == ("live_observed", 2)


def test_t5_does_not_wait_for_window_or_pa():
    end = datetime.fromisoformat("2026-10-17T20:30:00+08:00")
    rows = [_g(1, DAY, completed=True, official="final", ended=end)]
    out = _layout(_series("decided", decided_by={"year": 2026, "kind_code": "C", "game_sno": 1}), rows,
                  now=end + timedelta(minutes=1))
    assert (out["layout_state"], out["summary_kind"]) == ("T5", "championship_summary")
    assert out["section_order"] == [1, 3, 4, 2]


def test_e_t5_is_advance_summary():
    rows = [_g(4, date(2026, 10, 12), completed=True, official="final", kind="E")]
    out = _layout(_series("decided", kind="E", decided_by={"year": 2026, "kind_code": "E", "game_sno": 4}), rows)
    assert out["summary_kind"] == "advance_summary"


def test_t2_without_next_db_row_has_null_target():
    """G02：下一場沒有 DB 列 ⇒ 安排待定、target null。"""
    out = _layout(_series("active"), [_g(1, DAY, completed=True, official="final")],
                  now=datetime.fromisoformat("2026-10-18T10:00:00+08:00"))
    assert (out["layout_state"], out["layout_reason"], out["target_game_key"]) == ("T2", "arrangement_pending", None)


# —— A03 賽程 ————————————————————————————————————————————————————————————————

def test_postponed_moves_date_but_keeps_identity_and_overlay():
    moved = [_g(1, date(2026, 10, 18), official="postponed"), *C_ROWS[1:]]
    out = _layout(games=moved, now=datetime.fromisoformat("2026-10-17T19:00:00+08:00"))
    assert out["target_game_key"] == {"year": 2026, "kind_code": "C", "game_sno": 1}
    assert "postponed" in out["overlays"]


def test_suspended_game_resumes_under_same_key():
    """保留比賽續賽：同一 key，不新增 G。"""
    out = _layout(games=[_g(1, DAY, official="reserved"), *C_ROWS[1:]], now=datetime.fromisoformat(
        "2026-10-17T22:00:00+08:00"))
    assert out["target_status"] == "suspended" and "suspended" in out["overlays"]
    assert out["target_game_key"]["game_sno"] == 1


def test_doubleheader_keeps_two_keys():
    rows = [_g(1, DAY, completed=True, official="final"), _g(2, DAY), *C_ROWS[2:]]
    out = _layout(_series("active"), rows, now=datetime.fromisoformat("2026-10-17T23:00:00+08:00"))
    assert out["target_game_key"]["game_sno"] == 2


def test_official_change_not_ingested_shows_pending_update():
    out = _layout(pending=frozenset({(2026, "C", 2)}))
    assert "pending_update" in out["overlays"]


@pytest.mark.parametrize(("official", "day_offset", "expected"), [
    ("final", -1, "unknown"),      # 官方 final 但正式未完賽 ⇒ 不是 final（G03）
    ("scheduled", -1, "scheduled"),
    ("unknown", 1, "scheduled"),
    ("unknown", 0, "unknown"),
])
def test_target_status_never_final_without_completed(official, day_offset, expected):
    today = date(2026, 10, 17)
    g = _g(1, today + timedelta(days=day_offset), official=official)
    assert st.target_status(g, live_phase=None, taipei_day=today) == expected
    assert st.target_status(g, live_phase="final", taipei_day=today) == expected   # 即時 final 也不是


def test_analysis_status_is_independent_of_decided():
    rows = [_g(1, DAY, completed=True), _g(2, DAY, completed=True)]
    assert st.analysis_status(rows, {}) == "pending"
    assert st.analysis_status(rows, {K1: "published"}) == "partial"
    assert st.analysis_status(rows, {K1: "published", K2: "published"}) == "ready"
    assert st.analysis_status(rows, {K1: "published", K2: "reconciling"}) == "reconciling"


def test_default_series_prefers_live_then_c_after_e_decided():
    e, c = _series("decided", kind="E"), _series("pending")
    assert st.default_series({"E": e, "C": c}, []) == "C"
    assert st.default_series({"E": _series("active", kind="E"), "C": {**c, "sides": [{"team_code": DRAGON},
                                                                                       {"team_code": None}]}}, []) == "E"
    assert st.default_series({"E": e, "C": c}, ["E"]) == "E"
