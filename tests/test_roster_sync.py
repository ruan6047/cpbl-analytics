"""#284 同步比對與 payload 的純函式檢查（不連 DB）。"""

from __future__ import annotations

import copy
import json
import re
import subprocess
import sys

import pytest

from cpbl.rosters import sync
from cpbl.rosters.canonical import membership_hash, revision_hash, source_hash


def bundle(source_url="https://example.invalid/a", roles=None, rid="r-1", revisions=1):
    members = {f"{i:010d}": {"official_position": "投手" if i < 16 else "外野手",
                             "announced_name": f"選手{i}"} for i in range(1, 33)}
    head = {
        "roster_id": rid, "year": 2026, "kind_code": "C", "team_code": "ACN011",
        "source_url": source_url, "published_date": "2026-10-16", "published_precision": "date",
        "observed_at": "2026-10-16T01:00:00+00:00", "observation_basis": "cli_input",
        "identity_verified_at": "2026-10-16T01:00:00+00:00", "input_origin": "pasted_text",
        "raw_text": "x", "hash_version": 1, "import_check": {"complete": True},
        "submitted_at": "2026-10-16T01:00:00+00:00",
        "membership_hash": membership_hash(2026, "C", "ACN011",
                                           [(m["official_position"], p) for p, m in members.items()]),
        "source_hash": source_hash(source_url, "2026-10-16", "date",
                                   [(p, m["announced_name"]) for p, m in members.items()]),
    }
    revs = {}
    for n in range(1, revisions + 1):
        r = {p: (roles or {}).get(p, "unclassified") if n > 1 else "unclassified" for p in members}
        revs[n] = {"hash": [revision_hash(r.items())],
                   "changed_at": ["2026-10-16T01:00:00+00:00"], "roles": r}
    return {(2026, "C", "ACN011"): {"head": head, "members": members, "revisions": revs}}


def test_plan_states():
    local = bundle()
    assert sync.self_check(local) == []
    assert sync.plan(local, {}).state == "insert-pending"
    assert sync.plan(local, bundle()).state == "no-change"
    two = bundle(revisions=2, roles={"0000000001": "輪值"})
    p = sync.plan(two, bundle())
    assert p.state == "insert-pending" and p.insert_revisions == [((2026, "C", "ACN011"), 2)]
    assert sync.plan(bundle(), two).state == "reject"                     # 目標多一版
    assert sync.plan(bundle(source_url="https://example.invalid/b"), bundle()).state == "reject"
    assert sync.plan({}, bundle()).state == "reject"                      # 目標有本機無
    assert sync.plan(bundle(rid="r-2"), bundle()).state == "reject"       # 同 scope 不同 roster_id


def test_self_check_detects_stored_hash_drift():
    b = bundle()
    b[(2026, "C", "ACN011")]["head"]["membership_hash"] = "0" * 64
    assert any("membership_hash" in p for p in sync.self_check(b))


def test_apply_script_is_insert_only_and_data_not_in_sql():
    b = bundle()
    script = sync.apply_script(sync.payload(b, sync.plan(b, {})))
    sql = "\n".join(ln for ln in script.splitlines() if not ln.startswith("{"))
    assert not re.search(r"\bUPDATE\b|\bDELETE\b|DO UPDATE|TRUNCATE", sql)
    assert "COPY _roster_sync_payload (doc) FROM STDIN;" in script
    data = next(ln for ln in script.splitlines() if ln.startswith("{"))
    assert json.loads(data.replace("\\\\", "\\"))["rosters"][0]["roster_id"] == "r-1"


def test_copy_escape_keeps_single_line():
    assert sync._copy_escape("a\nb\\c\td") == "a\\nb\\\\c\\td"


@pytest.mark.parametrize("flag", ["--help", "-h"])
def test_help_has_no_side_effects(flag):
    r = subprocess.run([sys.executable, "-m", "cpbl.rosters.sync", flag], capture_output=True,
                       text=True, timeout=30)
    assert r.returncode == 0 and "insert-only" in r.stdout


def test_missing_args_exit_nonzero():
    r = subprocess.run([sys.executable, "-m", "cpbl.rosters.sync", "plan"], capture_output=True,
                       text=True, timeout=30)
    assert r.returncode == 2


def test_scoped_plan_rejects_new_membership_and_ignores_other_scope():
    local = bundle(revisions=2)
    target = bundle()
    other = copy.deepcopy(bundle())
    extra = other.pop((2026, "C", "ACN011"))
    other[(2026, "E", "ADD011")] = extra
    local.update(other)
    scopes = ((2026, "C", "ACN011"),)
    p = sync.plan(local, target, scopes=scopes)
    assert p.insert_rosters == [] and p.insert_revisions == [((2026, "C", "ACN011"), 2)]
    assert sync.plan(local, {}, scopes=scopes).state == "reject"
    doc = sync.payload(local, p, scopes=scopes)
    assert not doc["rosters"] and not doc["members"]
    assert doc["scopes"] == [{"year": 2026, "kind_code": "C", "team_code": "ACN011"}]
    assert "ROSTER_SYNC_SCOPE" in sync.apply_script(doc)


def test_scope_cli_rejects_duplicates_and_unknown_kind():
    with pytest.raises(ValueError):
        sync.parse_scopes(["2026:C:ACN011", "2026:C:ACN011"])
    with pytest.raises(ValueError):
        sync.parse_scopes(["2026:A:ACN011", "2026:C:AAA011"])


def test_sync_v2_preserves_complete_roles_provenance_and_legacy_hash():
    from test_roster_roles_v2 import provenance

    from cpbl.rosters.canonical import revision_hash_v2
    local = bundle(revisions=2)
    rec = local[(2026, "C", "ACN011")]
    legacy_hash = rec["revisions"][1]["hash"][:]
    rev = rec["revisions"][2]
    rev["formats"] = [2]
    rev["details"] = {}
    for pid, member in rec["members"].items():
        roles = ["先發", "長中繼"] if member["official_position"] == "投手" else ["代打", "指定打擊"]
        rev["details"][pid] = {"role_format_version": 2, "tactical_roles": roles,
                               "role_provenance": provenance(roles)}
    rev["hash"] = [revision_hash_v2([(pid, d["tactical_roles"], d["role_provenance"])
                                    for pid, d in rev["details"].items()])]
    assert sync.self_check(local) == []
    doc = sync.payload(local, sync.plan(local, {}))
    restored = sync.normalize(doc)
    assert sync.self_check(restored) == []
    r = restored[(2026, "C", "ACN011")]["revisions"]
    assert r[1]["hash"] == legacy_hash and r[2]["details"] == rev["details"]
    r[2]["details"]["0000000001"]["role_format_version"] = 3
    # 每列格式也須一致，不能只信同版頭的formats。
    assert sync.self_check(restored)


def test_sync_dump_missing_new_columns_fails_closed():
    doc = sync.payload(bundle(), sync.plan(bundle(), {}))
    del doc["revisions"][0]["tactical_roles"]
    with pytest.raises(sync.SyncError) as exc:
        sync.normalize(doc)
    assert exc.value.code == 67


def test_scoped_reconcile_missing_scope_is_not_empty_success():
    with pytest.raises(sync.SyncError) as exc:
        sync._scoped({}, ((2026, "C", "ACN011"), (2026, "C", "AAA011")))
    assert exc.value.code == 71
