"""就緒訊號的純分類器；不修復、抓取或修改被觀察資料。"""
from __future__ import annotations

import re
from collections import Counter
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

_TAIPEI = ZoneInfo("Asia/Taipei")
_PHASES = {"scheduled", "probable_announced", "lineup_announced", "live", "final",
           "postponed", "reserved"}
_TERMINAL = {"write_readback", "reused_final", "moved_out_of_window"}


def instant(value: Any, *, local: bool = False) -> datetime | None:
    """來源開賽時間允許台北無時區格式；證據時間必須有時區。"""
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            if not local:
                return None
            parsed = parsed.replace(tzinfo=_TAIPEI)
        return parsed.astimezone(UTC)
    except (ValueError, OverflowError):
        return None


def identity(value: Any) -> tuple[int, str, int] | None:
    if not isinstance(value, str):
        return None
    match = re.fullmatch(r"([0-9]{4})-([AEC])-([1-9][0-9]*)", value)
    return (int(match[1]), match[2], int(match[3])) if match else None


def inspect_partition(payload: Any, *, year: int, month: int, kind: str) -> dict:
    data = payload.get("Data") if isinstance(payload, dict) else None
    games = data.get("Games") if isinstance(data, dict) else None
    result = {"year": year, "month": month, "kind": kind, "state": "unknown",
              "explicit_list": isinstance(games, list), "row_count": None,
              "invalid_identity_count": 0, "invalid_time_count": 0}
    if not isinstance(games, list):
        return result
    result["row_count"] = len(games)
    for item in games:
        row = item if isinstance(item, dict) else {}
        key = identity(row.get("GameId"))
        if (key is None or key[:2] != (year, kind)
                or row.get("KindCode", kind) != kind
                or ("GameSno" in row and (type(row["GameSno"]) is not int
                                         or row["GameSno"] != key[2]))):
            result["invalid_identity_count"] += 1
        if instant(row.get("PreExeDate"), local=True) is None:
            result["invalid_time_count"] += 1
    if not result["invalid_identity_count"] and not result["invalid_time_count"]:
        result["state"] = "complete"
    return result


def inspect_snapshot(value: Any, *, expected_id: str, now: datetime) -> dict:
    """必要欄位完整度；沒有來源 raw 時不宣稱已驗 raw→投影。"""
    if not isinstance(value, dict):
        return {"state": "unknown", "reasons": ["snapshot_missing"]}
    reasons = []
    key = identity(value.get("game_id"))
    if (key is None or value.get("game_id") != expected_id
            or value.get("kind_code") != key[1]
            or type(value.get("game_sno")) is not int or value.get("game_sno") != key[2]):
        reasons.append("snapshot_identity_unknown")
    if instant(value.get("starts_at"), local=True) is None:
        reasons.append("snapshot_time_unknown")
    phase = value.get("phase")
    if not isinstance(phase, str) or phase not in _PHASES:
        reasons.append("snapshot_phase_unknown")
    for side in ("away", "home"):
        team = value.get(side)
        team = team if isinstance(team, dict) else {}
        name = team.get("team")
        code = name.get("code") if isinstance(name, dict) else None
        if not isinstance(code, str) or not code.strip():
            reasons.append(f"{side}_identity_unknown")
        if phase in ("live", "final"):
            score = team.get("score")
            if type(score) is not int or score < 0:
                reasons.append(f"{side}_score_unknown")
    events = value.get("livelog")
    if (not isinstance(events, list) or any(not isinstance(row, dict) for row in events)
            or type(value.get("event_count")) is not int
            or value.get("event_count") != len(events)):
        reasons.append("snapshot_livelog_unknown")
    source = value.get("source")
    source = source if isinstance(source, dict) else {}
    version = source.get("version")
    fetched_at = instant(source.get("fetched_at"))
    if not isinstance(version, str) or re.fullmatch(r"[0-9a-f]{64}", version) is None:
        reasons.append("snapshot_version_unknown")
    if fetched_at is None or now.tzinfo is None or fetched_at > now:
        reasons.append("snapshot_fetched_at_unknown")
    return {"state": "unknown" if reasons else "complete", "reasons": reasons}


def reconcile_snapshot(expected: dict, actual: Any) -> bool:
    """精確比較既有投影；分離 source-error 附註不作版本差異。"""
    if not isinstance(actual, dict):
        return False

    def projection(value):
        source = value.get("source")
        if not isinstance(source, dict):
            return None
        return {**value, "source": {key: field for key, field in source.items()
                                   if key not in {"last_error_at", "last_error_type"}}}

    return projection(expected) is not None and projection(expected) == projection(actual)


def summarize_delivery(selected: list[str], records: list[dict], *, overflow_count: int = 0) -> dict:
    counts = Counter(record.get("disposition") for record in records)
    record_ids = [record.get("game_id") for record in records]
    unresolved = (len(selected) != len(set(selected))
                  or Counter(record_ids) != Counter(selected)
                  or any(count > 1 for count in Counter(record_ids).values())
                  or any(action not in _TERMINAL | {"failed"} for action in counts))
    state = "complete"
    if overflow_count > 0 or counts["failed"]:
        state = "partial"
    elif unresolved:
        state = "unknown"
    return {"state": state, **{action: counts[action] for action in sorted(_TERMINAL)},
            "failed": counts["failed"], "unresolved": int(unresolved)}


_LEGAL_PREGAME = {"scheduled", "probable_announced", "lineup_announced", "postponed", "reserved"}


def inspect_raw_game(raw: Any, snapshot: Any) -> list[str]:
    """壓縮前的明細形狀：有值卻在投影遺失，或 LiveLog 形狀未知＝不完整。

    LiveLog 缺席／null 只在賽前類 phase 合法；live／final 缺席不能當成「零事件」。
    """
    if not isinstance(raw, dict) or not isinstance(snapshot, dict):
        return ["raw_game_unknown"]
    reasons = []
    events = raw.get("LiveLog")
    if events is None:
        if snapshot.get("phase") not in _LEGAL_PREGAME:
            reasons.append("raw_livelog_absent")
    elif not isinstance(events, list) or any(not isinstance(row, dict) for row in events):
        reasons.append("raw_livelog_malformed")
    elif snapshot.get("event_count") != len(events):
        reasons.append("livelog_projection_lost")
    for raw_side, side in (("Visiting", "away"), ("Home", "home")):
        team = raw.get(raw_side)
        if team is not None and not isinstance(team, dict):
            reasons.append(f"raw_{side}_malformed")
            continue
        code = ((team or {}).get("Team") or {}).get("Code") if isinstance(
            (team or {}).get("Team"), dict) else None
        projected = ((snapshot.get(side) or {}).get("team") or {}).get("code")
        if code is not None and code != projected:
            reasons.append(f"{side}_identity_projection_lost")
        score = (team or {}).get("Score")
        if score is not None and score != (snapshot.get(side) or {}).get("score"):
            reasons.append(f"{side}_score_projection_lost")
    return reasons


def source_availability(snapshot: Any) -> dict:
    """來源可用度（合法缺值）；與本輪交付 partial 分列，不影響 ready。"""
    if not isinstance(snapshot, dict):
        return {"state": "unknown"}
    value = {
        "lineup": {side: ((snapshot.get(side) or {}).get("lineup") or {}).get("availability")
                   for side in ("away", "home")},
        "probable": {side: ((snapshot.get(side) or {}).get("probable_pitcher") or {}).get(
            "availability") for side in ("away", "home")},
        "tracking": snapshot.get("tracking_availability"),
    }
    complete = (set(value["lineup"].values()) == {"announced"}
                and set(value["probable"].values()) == {"announced"}
                and value["tracking"] == "available")
    return {"state": "complete" if complete else "partial", **value}


_LEGACY_REASON = {"disabled": "worker_disabled", "killed": "worker_killed",
                  "locked": "worker_locked", "error": "worker_cycle_error"}


def classify_cycle(*, legacy_state: Any, partitions: list[dict], delivery: dict | None,
                   games: list[dict], faults: list[str]) -> tuple[str, list[str]]:
    """單輪結論：已知失敗＝not_ready、任何未知＝unknown；舊成功不參與本判定。"""
    failed: list[str] = []
    unknown: list[str] = [f"observer_fault:{name}" for name in faults]
    if legacy_state != "ok":
        failed.append(_LEGACY_REASON.get(legacy_state, "worker_state_unknown"))
        if legacy_state not in _LEGACY_REASON:
            unknown.append("worker_state_unknown")
            failed.pop()
    else:
        if not partitions:
            unknown.append("partitions_unobserved")
        for item in partitions:
            if item.get("state") != "complete":
                unknown.append(item.get("reason") or "partition_unknown")
        if delivery is None:
            unknown.append("delivery_unobserved")
        elif delivery.get("state") == "partial":
            failed.append("delivery_partial")
        elif delivery.get("state") != "complete":
            unknown.append("delivery_unknown")
        for game in games:
            unknown.extend(game.get("reasons") or [])
    if failed:
        return "not_ready", sorted(set(failed + unknown))
    if unknown:
        return "unknown", sorted(set(unknown))
    return "ready", []
