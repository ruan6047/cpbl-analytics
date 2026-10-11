"""消費 #237 已交的正式母體；沒有正式交付不可用年度 roster 偷換。"""

from __future__ import annotations


def adapt(records: list[dict], season: int, kind: str, team: str) -> dict:
    matches = [r for r in records if r.get("year") == season and r.get("round") == kind
               and r.get("team_code") == team]
    if len(matches) != 1:
        return {"year": season, "round": kind, "team_code": team, "complete": False,
                "roster_version": None, "source_url": None, "published_at": None,
                "observed_at": None, "members": [], "unresolved_members": [],
                "status": "unverified"}
    record = matches[0]
    members = record.get("members", [])
    unresolved = [r for r in members if not r.get("player_id") or r.get("role") not in ("batting", "pitching")]
    complete = bool(record.get("complete") and record.get("official") and record.get("source_url")
                    and record.get("roster_version") and record.get("observed_at") and members and not unresolved)
    return {**record, "complete": complete, "unresolved_members": unresolved,
            "status": "verified" if complete else "incomplete"}
