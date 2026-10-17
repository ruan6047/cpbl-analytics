"""#316 多重角色不可變版本的純契約測試。"""

import copy

import pytest

from cpbl.rosters.canonical import revision_hash, revision_hash_v2, validate_roles_v2


def provenance(roles):
    return {
        "approval_table_sha256": "a" * 64,
        "approval_manifest_sha256": "b" * 64,
        "approval_url": "https://github.com/ruan6047/cpbl-analytics/issues/316#issuecomment-6229024703",
        "roles": {r: {"origin": "research", "source_ids": ["S1"],
                      "original_basis": "原研究限制", "original_evidence": "實際用途"} for r in roles},
    }


def test_v1_golden_unchanged():
    assert revision_hash([("0000000002", "unclassified"), ("0000000001", "輪值")]) == (
        "6c47f4474e38af41b216b23d88d48a01779f56e6b9daa368714a11cc971fe9d6")


def test_v2_hash_has_no_primary_role_and_tracks_provenance():
    p = provenance(["先發", "長中繼"])
    rows = [("0000000001", ["先發", "長中繼"], p)]
    h = revision_hash_v2(rows)
    assert h == revision_hash_v2([("0000000001", ["長中繼", "先發"], p)])
    changed = copy.deepcopy(p)
    changed["roles"]["先發"]["origin"] = "human"
    assert h != revision_hash_v2([("0000000001", ["先發", "長中繼"], changed)])
    assert h != revision_hash([("0000000001", "unclassified")])


@pytest.mark.parametrize("roles", [[], ["先發", "先發"], ["輪值"], ["先發", None], ["工具人"]])
def test_v2_rejects_empty_duplicate_unknown_and_incompatible_roles(roles):
    with pytest.raises(ValueError):
        validate_roles_v2("投手", roles, provenance([r for r in roles if r]))


def test_v2_requires_exact_role_provenance():
    p = provenance(["先發"])
    assert validate_roles_v2("投手", ["先發"], p) == ("先發",)
    with pytest.raises(ValueError):
        validate_roles_v2("投手", ["先發", "長中繼"], p)
    p["approval_table_sha256"] = None
    with pytest.raises(ValueError):
        validate_roles_v2("投手", ["先發"], p)
