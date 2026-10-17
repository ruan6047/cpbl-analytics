"""#316 第3/4區多重角色同源與相鄰負荷。"""

import copy
from datetime import date

import pytest
from test_playoffs_roster_reader import AWAY, HOME, NOW, inputs, members, roster
from test_roster_roles_v2 import provenance

from cpbl.playoffs.roster_reader import compute_roster
from cpbl.playoffs.watch_reader import _pitcher
from cpbl.playoffs.watch_rules import DayCoverage
from cpbl.rosters.canonical import role_fields


def multi_member(roles, position="投手"):
    return {"player_id": "0000000001", "announced_name": "球員", "official_position": position,
            "tactical_role": "unclassified", "role_format_version": 2,
            "tactical_roles": roles, "role_provenance": provenance(roles)}


def test_roster_v2_keeps_all_roles_and_no_scalar_primary():
    r = roster()
    r["members"] = [multi_member(["先發", "長中繼"])]
    out = compute_roster(inputs({AWAY: r, HOME: roster()}), now=NOW)
    m = members(out)["0000000001"]
    assert m["tactical_role"] is None and m["tactical_roles"] == ["先發", "長中繼"]
    assert m["role_format_version"] == 2
    changed = copy.deepcopy(r)
    changed["members"][0]["role_provenance"]["roles"]["先發"]["original_evidence"] += "補充"
    other = compute_roster(inputs({AWAY: changed, HOME: roster()}), now=NOW)
    assert other["context_version"] == out["context_version"]
    assert other["roster_version"] != out["roster_version"]


@pytest.mark.parametrize("roles,visible,level", [(["先發"], False, "starter_exempt"),
    (["先發", "長中繼"], True, "low"), (["中繼"], True, "low"), (["拆彈組"], True, "low")])
def test_watch_full_roles_default_relief_and_actual_load(roles, visible, level):
    from datetime import timedelta
    d = date(2026, 10, 17)
    coverage = {d-timedelta(days=k): DayCoverage(d-timedelta(days=k), True) for k in range(4)}
    out = _pitcher(multi_member(roles), [], coverage, d)
    assert out["tactical_roles"] == roles
    assert out["tactical_role"] is None
    assert out["default_visible"] is visible and out["load"]["level"] == level


def test_unknown_format_never_silently_becomes_no_roles():
    with pytest.raises(ValueError, match="未知角色格式"):
        role_fields({"role_format_version": 3, "tactical_role": "終結"})


def test_legacy_role_is_preserved_without_relabel():
    assert role_fields({"tactical_role": "守備"}) == {
        "role_format_version": 1, "tactical_role": "守備", "tactical_roles": ["守備"], "role_provenance": None}
