import hashlib
import json
from importlib import import_module

import pytest

from cpbl.reports import population


def records(year=2026, kind="E"):
    return import_module("cpbl.reports.official_population").load(year, kind)


def fixture_record():
    return {
        "year": 2026,
        "round": "E",
        "team_code": "ACN011",
        "official": True,
        "complete": True,
        "source_url": "https://www.cpbl.com.tw/fixture",
        "roster_version": "fixture-v1",
        "observed_at": "2026-10-11T17:33:07.351Z",
        "announced_total": 2,
        "members": [
            {"player_id": "0000000001", "role": "pitching", "name": "甲"},
            {"player_id": "0000000002", "role": "batting", "name": "乙"},
        ],
    }


@pytest.mark.parametrize("damage", ["duplicate", "short", "name", "id"])
def test_population_does_not_claim_complete_when_identity_or_total_is_invalid(damage):
    record = fixture_record()
    if damage == "duplicate":
        record["members"][1]["player_id"] = "0000000001"
    if damage == "short":
        record["members"].pop()
    if damage == "name":
        record["members"][0]["name"] = ""
    if damage == "id":
        record["members"][0]["player_id"] = "1"
    assert not population.adapt([record], 2026, "E", "ACN011")["complete"]


def test_official_population_keeps_64_names_roles_ids_and_time_precision():
    actual = records()
    assert [r["team_code"] for r in actual] == ["ACN011", "ADD011"]
    assert all(len(r["members"]) == r["announced_total"] == 32 for r in actual)
    people = [m for r in actual for m in r["members"]]
    assert len({m["player_id"] for m in people}) == 64
    for r in actual:
        assert r["published_date"] == "2026-10-08" and r["published_precision"] == "date"
        assert r["published_at"] is None and r["raw_fetch_start_at"] is None
        assert r["observed_at"] == "2026-10-11T17:33:07.351Z"
        assert r["identity_verified_at"] == "2026-10-11T18:56:05.097767+00:00"
        assert population.adapt(actual, 2026, "E", r["team_code"])["complete"]
    byname = {m["name"]: m for m in people}
    assert byname["勝騎士"]["player_id"] == "0000005604"
    assert byname["喬登"]["player_id"] == "0000007778"
    assert byname["髙塩將樹"]["player_id"] == "0000006818"
    assert byname["林志綱"]["official_role"] == "外野手"
    for r, expected in zip(actual, [(15, 3, 8, 6), (15, 3, 9, 5)], strict=True):
        assert (
            tuple(
                sum(m["official_role"] == role for m in r["members"])
                for role in ("投手", "捕手", "內野手", "外野手")
            )
            == expected
        )


def test_source_is_round_specific_and_returns_independent_records():
    for year, kind in [(2025, "E"), (2026, "C"), (2027, "E")]:
        assert records(year, kind) == []
    first = records()
    first[0]["members"].clear()
    assert len(records()[0]["members"]) == 32


def test_observed_difference_is_preserved_and_does_not_fake_complete_population():
    record = population.adapt([fixture_record()], 2026, "E", "ACN011")
    observed = [
        {"team_code": "ACN011", "player_id": "0000000001"},
        {"team_code": "ACN011", "player_id": "0000000003"},
        {"team_code": "ADD011", "player_id": "0000000004"},
    ]
    actual = population.reconcile(record, observed)
    assert actual["registration_complete"] is True
    assert actual["complete"] is False and actual["status"] == "conflict"
    assert actual["observed_outside_population"] == ["0000000003"]
    assert len(actual["members"]) == 2 and record["complete"] is True
    assert population.reconcile(record, observed[:1])["complete"] is True
    unknown = population.adapt([], 2026, "C", "ACN011")
    assert population.reconcile(unknown, observed)["observed_outside_population"] == []


def test_all_64_data_match_the_fixed_qualified_handoff_fingerprint():
    actual = records()
    meta = {
        k: actual[0][k]
        for k in (
            "year",
            "round",
            "source_url",
            "published_date",
            "published_precision",
            "published_at",
            "observed_at",
            "observation_basis",
            "raw_fetch_start_at",
        )
    }
    meta["members_by_team"] = {r["team_code"]: r["members"] for r in actual}
    fingerprint = hashlib.sha256(
        json.dumps(meta, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    # 正式64人handoff的canonical映射hash，不由本測試樣例選擇ID。
    assert fingerprint == "808cbc0c03a1da7c4c543d06a5e4d1982ad27cfa28f3164ce856888871ef75b0"
    assert all(r["roster_version"] == fingerprint for r in actual)


def test_partial_source_metadata_remains_unknown_and_never_claims_verified():
    record = fixture_record()
    del record["observed_at"]
    adapted = population.adapt([record], 2026, "E", "ACN011")
    assert adapted["complete"] is False
    source = population.provenance([adapted])[0]
    assert source["observed_at"] is None and source["coverage_status"] == "incomplete"
