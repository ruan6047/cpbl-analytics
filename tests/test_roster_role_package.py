"""#316 JSON輸入的語意集合與來源邊界。"""

import copy

import pytest
from test_roster_roles_v2 import provenance

from cpbl.ingest.run_roster import _official_text
from cpbl.rosters.parser import parse
from cpbl.rosters.role_package import parse_package


def package():
    teams = []
    for n, code in enumerate(("ACN011", "ADD011"), 1):
        roster = parse(_official_text(2026, "E", code)[0])
        members = []
        for entry in roster.entries:
            roles = ["先發", "長中繼"] if entry.position == "投手" else ["主力"]
            members.append({"player_id": entry.explicit_id, "announced_name": entry.name,
                            "official_position": entry.position, "tactical_roles": roles,
                            "role_provenance": provenance(roles)})
        teams.append({"team_code": code, "roster_id": f"00000000-0000-0000-0000-{n:012d}",
                      "membership_hash": "c" * 64, "source_hash": "d" * 64,
                      "expected_latest_revision": 1, "expected_latest_hash": "e" * 64,
                      "members": members})
    approval = {k: v for k, v in provenance(["先發"]).items() if k != "roles"}
    return {"format": "roster-roles/v2", "year": 2026, "kind_code": "E",
            "approval": approval, "teams": teams}


def test_full_two_team_package():
    result = parse_package(package())
    assert len(result["teams"]) == 2
    assert all(len(t["members"]) == 32 for t in result["teams"])
    assert all(len(t["revision_hash"]) == 64 for t in result["teams"])


@pytest.mark.parametrize("change", [
    lambda p: p["teams"].pop(),
    lambda p: p["teams"][0]["members"].pop(),
    lambda p: p["teams"][0]["members"][0].update(tactical_roles=["長中繼", "先發"]),
    lambda p: p["teams"][0].update(expected_latest_revision=0),
    lambda p: p["approval"].update(approval_table_sha256="f" * 64),
    lambda p: p["teams"][0]["members"][1].update(player_id=p["teams"][0]["members"][0]["player_id"]),
    lambda p: p["teams"][1].update(team_code=p["teams"][0]["team_code"]),
])
def test_package_rejects_incomplete_noncanonical_conflicting_input(change):
    p = copy.deepcopy(package())
    change(p)
    with pytest.raises(ValueError):
        parse_package(p)
