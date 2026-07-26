"""stats.cpbl 單場資料的 canonical live snapshot 與集中式 polling worker。

本模組先把外部 payload 正規化成 fail-closed contract；網路、cache 與排程於後續 slice
接在同一 contract 上。官方 raw status 未觀測過時一律保留為 ``unknown``。
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

_STATUS_PHASE = {
    "START": "live",
    "FINISHED": "final",
    "POSTPONED": "postponed",
    "RESERVED": "reserved",
}


def _iso(value: datetime) -> str:
    return value.isoformat()


def _first_observed(previous: dict | None, key: str, identity: str | None,
                    fetched_at: datetime) -> str:
    old = (previous or {}).get(key) or {}
    if identity and old.get("player_id") == identity and old.get("first_observed_at"):
        return old["first_observed_at"]
    if identity is None and old.get("items") and old.get("first_observed_at"):
        return old["first_observed_at"]
    return _iso(fetched_at)


def _team_snapshot(raw: dict, fetched_at: datetime, previous: dict | None) -> dict:
    pitchers = raw.get("Pitchers") if isinstance(raw.get("Pitchers"), list) else []
    starter = next((p for p in pitchers if p.get("RoleType") == "先發"), None)
    pitcher_id = None if starter is None else starter.get("PitcherAcnt")
    if starter and pitcher_id:
        probable = {
            "availability": "announced",
            "player_id": pitcher_id,
            "name": starter.get("PitcherName"),
            "first_observed_at": _first_observed(
                previous, "probable_pitcher", str(pitcher_id), fetched_at,
            ),
        }
    else:
        probable = {
            "availability": "not_announced",
            "player_id": None,
            "name": None,
            "first_observed_at": None,
        }

    hitters = raw.get("Hitters") if isinstance(raw.get("Hitters"), list) else []
    items = [
        {
            "batting_order": h.get("Lineup"),
            "player_id": h.get("HitterAcnt"),
            "name": h.get("HitterName"),
            "position": h.get("DefendStation"),
        }
        for h in hitters
        if h.get("Lineup") is not None and h.get("HitterAcnt")
    ]
    items.sort(key=lambda row: int(row["batting_order"]))
    orders = {int(row["batting_order"]) for row in items}
    availability = "announced" if set(range(1, 10)) <= orders else (
        "partial" if items else "not_announced"
    )
    lineup_first = None
    if items:
        previous_lineup = (previous or {}).get("lineup") or {}
        lineup_first = previous_lineup.get("first_observed_at") or _iso(fetched_at)

    team = raw.get("Team") if isinstance(raw.get("Team"), dict) else {}
    return {
        "team": {"code": team.get("Code"), "name": team.get("Name")},
        "score": raw.get("Score"),
        "probable_pitcher": probable,
        "lineup": {
            "availability": availability,
            "items": items,
            "first_observed_at": lineup_first,
        },
        "inning_score": raw.get("InningScore") if isinstance(raw.get("InningScore"), list) else [],
        "hitters": hitters,
        "pitchers": pitchers,
    }


def _phase(raw_status: str, away: dict, home: dict) -> str:
    mapped = _STATUS_PHASE.get(raw_status)
    if mapped:
        return mapped
    if raw_status != "SCHEDULED":
        return "unknown"
    if any(side["lineup"]["availability"] != "not_announced" for side in (away, home)):
        return "lineup_announced"
    if any(side["probable_pitcher"]["availability"] == "announced" for side in (away, home)):
        return "probable_announced"
    return "scheduled"


def build_snapshot(raw_game: dict[str, Any], *, fetched_at: datetime,
                   previous: dict | None = None) -> dict[str, Any]:
    """把 stats ``Data.Game`` 轉為前後端共用的 canonical snapshot。"""
    raw_status = str(raw_game.get("GameStatus") or "")
    away = _team_snapshot(
        raw_game.get("Visiting") if isinstance(raw_game.get("Visiting"), dict) else {},
        fetched_at,
        (previous or {}).get("away"),
    )
    home = _team_snapshot(
        raw_game.get("Home") if isinstance(raw_game.get("Home"), dict) else {},
        fetched_at,
        (previous or {}).get("home"),
    )
    livelog = raw_game.get("LiveLog") if isinstance(raw_game.get("LiveLog"), list) else []
    tracked = sum(1 for event in livelog if event.get("Trackman"))
    phase = _phase(raw_status, away, home)
    if tracked:
        tracking = "available"
    elif phase in {"live", "final"}:
        tracking = "pending"
    elif phase in {"scheduled", "probable_announced", "lineup_announced"}:
        tracking = "not_announced"
    else:
        tracking = "unknown"

    canonical = json.dumps(raw_game, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {
        "game_id": raw_game.get("GameId"),
        "game_sno": raw_game.get("GameSno"),
        "kind_code": raw_game.get("KindCode"),
        "starts_at": raw_game.get("PreExeDate"),
        "phase": phase,
        "raw_status": raw_status or None,
        "inning": raw_game.get("InningSeq"),
        "half": raw_game.get("VisitingHomeType"),
        "away": away,
        "home": home,
        "livelog": livelog,
        "event_count": len(livelog),
        "tracking_count": tracked,
        "tracking_availability": tracking,
        "source": {
            "fetched_at": _iso(fetched_at),
            "version": hashlib.sha256(canonical.encode()).hexdigest(),
        },
    }
