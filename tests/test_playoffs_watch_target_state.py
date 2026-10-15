"""#289 審核第 3 輪：目標場狀態 × 有無投球紀錄（DATE-SHAPES.md §2 交叉清單 T01–T12）。

判準：未核定完賽的場次，只有「目標場、D 當天、scheduled／postponed、該隊沒有任何投球紀錄」可當有證據的 0；
其餘一律灰並附理由，已知球數照列（PLAN :63／:107／:126、PRD 211–213）。
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from cpbl.playoffs import watch_reader as wrd
from cpbl.playoffs.watch_reader import WatchInputs, compute_watch, day_coverage
from cpbl.playoffs.watch_rules import Appearance

D = date(2026, 10, 17)
NOW = datetime(2026, 10, 17, 2, 0, tzinfo=UTC)
AWAY, HOME = "ACN011", "AAA011"
TARGET = (2026, "C", 1)


def g(completed: bool, box: bool) -> dict:
    return {"year": 2026, "kind_code": "C", "game_sno": 1, "game_date": D, "orig_date": None, "delay_kind": None,
            "away_team_code": AWAY, "home_team_code": HOME, "completed": completed, "box_away": box, "box_home": box}


# (編號, target_status, completed, 該隊有投球紀錄, 期望理由, 期望即時)
CELLS = [
    ("T01", "scheduled", False, False, (), False),
    ("T02", "scheduled", False, True, ("target_box_unverified",), False),
    ("T03", "postponed", False, False, (), False),
    ("T04", "postponed", False, True, ("target_box_unverified",), False),
    ("T05", "live", False, False, ("live_unobserved",), True),
    ("T06", "live", False, True, ("live_unobserved",), True),
    ("T07", "suspended", False, False, ("game_not_final",), False),
    ("T08", "suspended", False, True, ("game_not_final",), False),
    ("T09", "unknown", False, False, ("schedule_unavailable",), False),
    ("T10", "unknown", False, True, ("schedule_unavailable",), False),
    ("T11", "final", True, True, (), False),
    ("T12", "final", True, False, ("box_missing",), False),
]


@pytest.mark.parametrize(("cell", "status", "completed", "box", "reasons", "live"), CELLS, ids=[c[0] for c in CELLS])
def test_target_state_cross(cell, status, completed, box, reasons, live):
    cov = day_coverage(AWAY, D, [g(completed, box)], target_key=TARGET, target_date=D, target_status=status)
    assert cov.reasons == reasons, cell
    assert cov.complete is (not reasons) and cov.live is live, cell


def _context(target_status: str) -> dict:
    return {
        "context_version": "c", "source_manifest": [], "as_of": {},
        "series": {"C": {"series_id": {"kind_code": "C"}}},
        "state": {"by_series": {"C": {"target_game_key": {"year": 2026, "kind_code": "C", "game_sno": 1}}}},
        "games": [{"game_key": {"year": 2026, "kind_code": "C", "game_sno": 1}, "game_date": D.isoformat(),
                   "away_team_code": AWAY, "home_team_code": HOME, "completed": False,
                   "target_status": target_status}],
        "teams": [],
    }


@pytest.mark.parametrize("status", ["scheduled", "postponed"])
def test_review3_probe_target_unfinished_with_stored_box(status):
    """審核探針 target_still_scheduled_with_partial_box／target_postponed_with_stored_box 改寫。

    目標場仍是 scheduled／postponed、未核定完賽，但已有該投手 30 球紀錄 ⇒ ⛔ high／complete=True；
    應灰（target_box_unverified）並列已知 30 球。
    """
    roster = {"roster_id": "r", "published_date": "2026-10-16", "source_url": None, "annotation_version": 1,
              "members": [{"player_id": "0000000001", "announced_name": "甲", "tactical_role": "終結"}]}
    app = Appearance(game_key=TARGET, date=D, date_trusted=True, pitch_cnt=30, outs=3, er=0)
    w = compute_watch(WatchInputs(year=2026, series="C", context=_context(status), rosters={AWAY: roster, HOME: None},
                                  window_games=[g(False, True)], appearances={"0000000001": [app]}), now=NOW)
    load = w["teams"][0]["pitchers"][0]["load"]
    assert load["level"] == "unknown" and load["complete"] is False and load["live"] is False
    assert load["metrics"]["P0"] == 30 and load["metrics"]["Q"] == 1
    assert [i["reasons"] for i in load["incomplete"]] == [["target_box_unverified"]]
    assert "target_box_unverified" in w["missing_reason"]


def test_reserve_game_interval_covers_middle_days():
    """未完賽保留賽 [10/15, 10/30]：區間內每天（含中間日、目標日）都不完整。"""
    res = {"year": 2026, "kind_code": "A", "game_sno": 274, "game_date": date(2026, 10, 30),
           "orig_date": date(2026, 10, 15), "delay_kind": "保留", "away_team_code": AWAY, "home_team_code": "AEO011",
           "completed": False, "box_away": False, "box_home": False}
    for k, expect in ((3, ()), (2, ("game_not_final",)), (1, ("game_not_final",)), (0, ("game_not_final",))):
        day = date.fromordinal(D.toordinal() - k)
        assert day_coverage(AWAY, day, [res], target_key=TARGET, target_date=D,
                            target_status="scheduled").reasons == expect, k
    assert wrd.farm_code(AWAY) == "ACN022"


# 非目標場（窗口內）：完賽 × 有無紀錄 × D 之前／D 當天（DATE-SHAPES.md §6.3 N01–N08）。
NT = [
    ("N01", True, True, 1, ()), ("N02", True, False, 1, ("box_missing",)),
    ("N03", False, False, 1, ("game_not_final",)), ("N04", False, True, 1, ("game_not_final",)),
    ("N05", True, True, 0, ()), ("N06", True, False, 0, ("box_missing",)),
    ("N07", False, False, 0, ("game_not_final",)), ("N08", False, True, 0, ("game_not_final",)),
]


@pytest.mark.parametrize(("cell", "completed", "box", "offset", "reasons"), NT, ids=[c[0] for c in NT])
def test_non_target_cross(cell, completed, box, offset, reasons):
    day = date.fromordinal(D.toordinal() - offset)
    other = {**g(completed, box), "kind_code": "A", "game_sno": 300, "game_date": day}
    for status in ("scheduled", "postponed"):   # 非目標場不吃「賽前 0」，與目標場狀態無關
        cov = day_coverage(AWAY, day, [other], target_key=TARGET, target_date=D, target_status=status)
        assert cov.reasons == reasons, (cell, status)
