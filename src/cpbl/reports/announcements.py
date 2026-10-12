"""有限公告歷史的純選版；不取數、不拼版、不以box或cache倒填。"""

from __future__ import annotations

import re
from datetime import UTC, datetime

from cpbl.api.between_games import _started_obs
from cpbl.ingest.lineup_announcements import PROJECTION_VERSION, SOURCE_TYPE, content_hash, integer

_STARTED = {"START", "FINISHED", "RESERVED"}
_FIELD_POSITIONS = {"C", "1B", "2B", "3B", "SS", "LF", "CF", "RF"}


def timestamp(value) -> datetime | None:
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        return None
    return value.astimezone(UTC)


def _blank(target: dict) -> dict:
    teams = [target.get("away_team_code"), target.get("home_team_code")]
    return {
        "status": "unverified",
        "items": [],
        "team_evidence": {team: {"status": "unverified"} for team in teams if team},
    }


def _scope(row: dict, target: dict) -> bool:
    return all(row.get(k) == target.get(k) for k in ("year", "kind_code", "game_sno"))


def _valid_revision(row: dict, target: dict) -> bool:
    raw = row.get("raw_payload")
    if not isinstance(raw, dict):
        return False
    game_id = f"{target['year']}-{target['kind_code']}-{target['game_sno']}"
    status = raw.get("GameStatus")
    status = status if isinstance(status, str) else None
    return (
        row.get("source_type") == SOURCE_TYPE
        and raw.get("projection_version") in ("stats_datagame_lineup_v1", PROJECTION_VERSION)
        and raw.get("GameId") == game_id
        and raw.get("KindCode") == target["kind_code"]
        and integer(raw.get("GameSno")) == target["game_sno"]
        and row.get("raw_status") == status
        and row.get("content_hash") == content_hash(raw)
        and timestamp(row.get("fetched_at")) is not None
    )


def _items(raw: dict, side: str, team: str) -> list[dict] | None:
    block = raw.get(side)
    if not isinstance(block, dict) or not isinstance(block.get("Team"), dict):
        return None
    if block["Team"].get("Code") != team:
        return None
    rows = block.get("Hitters")
    if not isinstance(rows, list) or len(rows) != 9 or any(not isinstance(r, dict) for r in rows):
        return None
    ids = [r.get("HitterAcnt") for r in rows]
    orders = [integer(r.get("Lineup")) for r in rows]
    positions = [r.get("DefendStation") for r in rows]
    if (
        any(not isinstance(pid, str) or not re.fullmatch(r"[0-9]{10}", pid) for pid in ids)
        or len(set(ids)) != 9
        or set(orders) != set(range(1, 10))
        or any(not isinstance(p, str) for p in positions)
        or len(set(positions)) != 9
        or not _FIELD_POSITIONS <= set(positions)
        or set(positions) - _FIELD_POSITIONS not in ({"DH"}, {"P"})
    ):
        return None
    return [
        {
            "player_id": r["HitterAcnt"],
            "team_code": team,
            "order": integer(r["Lineup"]),
            "pos": r["DefendStation"],
            "name": r.get("HitterName") if isinstance(r.get("HitterName"), str) else None,
        }
        for r in sorted(rows, key=lambda r: integer(r["Lineup"]))
    ]


def select(revisions: list[dict], schedules: list[dict], target: dict) -> dict:
    result = _blank(target)
    teams = [target.get("away_team_code"), target.get("home_team_code")]
    if not all(teams) or len(set(teams)) != 2:
        return result
    rows = [r for r in revisions if _scope(r, target)]
    if not rows or any(not _valid_revision(r, target) for r in rows):
        return result
    bounds = []
    for row in rows:
        if row["raw_status"] in _STARTED:
            bounds.append(
                {
                    "source_type": SOURCE_TYPE,
                    "source_version": row["content_hash"],
                    "raw_status": row["raw_status"],
                    "fetched_at": timestamp(row["fetched_at"]).isoformat(),
                }
            )
    for row in schedules:
        if _scope(row, target) and _started_obs(row):
            seen = timestamp(row.get("fetched_at"))
            if seen is None:
                return result  # 跨來源邊界時間未知，不能忽略它去取更晚公告。
            bounds.append(
                {
                    "source_type": "main_schedule",
                    "source_version": row.get("payload_hash"),
                    "fetched_at": seen.isoformat(),
                }
            )
    first_started = min((timestamp(b["fetched_at"]) for b in bounds), default=None)
    # 只pin真正決定最早界的原證；較晚完賽/START不得改寫歷史材料。
    bounds = [b for b in bounds if timestamp(b["fetched_at"]) == first_started]
    boundary = {
        "first_started_at": first_started.isoformat() if first_started is not None else None,
        "boundary_sources": sorted(bounds, key=lambda b: (b["fetched_at"], b["source_type"])),
    }
    result["team_evidence"] = {team: {**boundary, "status": "unverified"} for team in teams}
    eligible = [
        r for r in rows if first_started is None or timestamp(r["fetched_at"]) < first_started
    ]
    if not eligible:
        return result
    selected = max(eligible, key=lambda r: timestamp(r["fetched_at"]))
    observed = timestamp(selected["fetched_at"]).isoformat()
    same_content = [r for r in rows if r["content_hash"] == selected["content_hash"]]
    first_content = min(timestamp(r["fetched_at"]) for r in same_content).isoformat()
    first_status = min(
        timestamp(r["fetched_at"])
        for r in same_content
        if r["raw_status"] == selected["raw_status"]
        and r["raw_payload"].get("GameStatus") == selected["raw_payload"].get("GameStatus")
    ).isoformat()
    evidence = {
        "source_type": SOURCE_TYPE,
        "raw_status": selected["raw_status"],
        "source_version": selected["content_hash"],
        "fetched_at": observed,
        "observed_at": observed,
        "first_content_at": first_content,
        "first_status_at": first_status,
        **boundary,
    }
    result.update(
        source_type=SOURCE_TYPE,
        source_url=selected["source_url"],
        raw_status=selected["raw_status"],
        source_version=selected["content_hash"],
        observed_at=observed,
        pregame_evidence={"fetched_at": observed, "first_started_at": evidence["first_started_at"]},
    )
    # 未核status也必須pin這片段，不能跳過回取更舊的完整公告。
    if selected["raw_status"] != "SCHEDULED":
        result["team_evidence"] = {team: {**evidence, "status": "unverified"} for team in teams}
        return result
    for side, team in zip(("Visiting", "Home"), teams, strict=True):
        items = _items(selected["raw_payload"], side, team)
        result["team_evidence"][team] = {
            **evidence,
            "status": "announced" if items is not None else "unverified",
        }
        if items is not None:
            result["items"].extend(items)
    ready = sum(e["status"] == "announced" for e in result["team_evidence"].values())
    result["status"] = "announced" if ready == 2 else "partial" if ready else "unverified"
    return result


def context_materials(
    revisions: list[dict], schedules: list[dict], candidates: list[dict]
) -> list[dict]:
    """同一批reader材料供base/第二讀與輸出；不含last_seen/read_at。"""
    return [
        {
            "game_key": f"{r['year']}/{r['kind_code']}/{r['game_sno']}",
            "lineup": select(revisions, schedules, r),
        }
        for r in sorted(candidates, key=lambda r: (r["kind_code"], r["game_sno"]))
    ]
