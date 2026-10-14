"""#284 同步比對與 payload 的純函式檢查（不連 DB）。"""

from __future__ import annotations

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
        revs[n] = {"hash": [revision_hash(r.items())], "changed_at": ["t"], "roles": r}
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
