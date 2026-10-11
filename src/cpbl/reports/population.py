"""官方完整母體的唯讀 adapter；年度 roster 只可佐證身份，不可偷換母體。"""

from __future__ import annotations

import re
from copy import deepcopy


def _valid_member(member: dict) -> bool:
    if not isinstance(member, dict):
        return False
    pid, name, role = member.get("player_id"), member.get("name"), member.get("role")
    official_role = member.get("official_role")
    return bool(isinstance(pid, str) and re.fullmatch(r"[0-9]{10}", pid)
                and isinstance(name, str) and name.strip() and role in ("batting", "pitching")
                and (official_role is None or (official_role in ("投手", "捕手", "內野手", "外野手")
                     and role == ("pitching" if official_role == "投手" else "batting"))))


def adapt(records: list[dict], season: int, kind: str, team: str) -> dict:
    matches = [r for r in records if r.get("year") == season and r.get("round") == kind
               and r.get("team_code") == team]
    if len(matches) != 1:
        return {"year": season, "round": kind, "team_code": team, "complete": False,
                "roster_version": None, "source_url": None, "published_at": None,
                "observed_at": None, "members": [], "unresolved_members": [],
                "status": "unverified"}
    record = deepcopy(matches[0])
    raw_members = record.get("members", [])
    members = raw_members if isinstance(raw_members, list) else []
    unresolved = [m for m in members if not _valid_member(m)]
    valid = [m for m in members if _valid_member(m)]
    ids = [m["player_id"] for m in valid]
    errors = []
    if not isinstance(raw_members, list):
        errors.append("invalid_members")
    if len(set(ids)) != len(ids):
        errors.append("duplicate_player_id")
    if record.get("announced_total") is not None and len(members) != record["announced_total"]:
        errors.append("announced_total_mismatch")
    complete = bool(record.get("complete") and record.get("official") and record.get("source_url")
                    and record.get("roster_version") and record.get("observed_at")
                    and members and not unresolved and not errors)
    return {**record, "complete": complete, "members": valid,
            "unresolved_members": unresolved, "validation_errors": errors,
            "status": "verified" if complete else "incomplete"}


def reconcile(record: dict, observed: list[dict]) -> dict:
    """保留正式會員與觀測差集；未核母體不能把所有觀測者判作名單外。"""
    result = deepcopy(record)
    result["registration_complete"] = bool(record["complete"])
    result["observed_outside_population"] = []
    if record["complete"]:
        registered = {m["player_id"] for m in record["members"]}
        extras = sorted({r["player_id"] for r in observed
                         if r["team_code"] == record["team_code"]} - registered)
        result["observed_outside_population"] = extras
        if extras:
            result["complete"] = False
            result["status"] = "conflict"
    return result


def provenance(rosters: list[dict]) -> list[dict]:
    """穩定來源 metadata，不含當次 read_at；同版本加入 context pin。"""
    return [{"source": "official_registration", "source_version": r["roster_version"],
             "scope": {"year": r["year"], "kind": r["round"], "team_code": r["team_code"]},
             "reference": r["source_url"], "published_at": r.get("published_at"),
             "published_date": r.get("published_date"), "published_precision": r.get("published_precision"),
             "observed_at": r.get("observed_at"), "observation_basis": r.get("observation_basis"),
             "identity_verified_at": r.get("identity_verified_at"),
             "fetched_at": None, "updated_at": None, "covered_game_keys": [],
             "coverage_status": r["status"], "cutoff_basis": "official_round_registration"}
            for r in sorted(rosters, key=lambda r: r["team_code"])
            if r.get("roster_version") and r.get("source_url")]
