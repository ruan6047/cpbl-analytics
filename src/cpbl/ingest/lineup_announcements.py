"""有限 stats Data.Game 公告投影與單表repository；沒有抓取、建表或cache替身。"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from datetime import UTC, datetime

from psycopg.rows import dict_row

from cpbl.db import conn

SOURCE_TYPE = "stats_datagame"
PROJECTION_VERSION = "stats_datagame_lineup_v2"
FIELDS = ("Lineup", "HitterAcnt", "HitterName", "DefendStation")


def canonical(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def identity(game_id: str) -> tuple[int, str, int]:
    match = re.fullmatch(r"(2026)-([EC])-([1-9][0-9]*)", game_id)
    if not match:
        raise ValueError("announcement identity outside 2026 E/C scope")
    return int(match[1]), match[2], int(match[3])


def integer(value) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, str) and re.fullmatch(r"[0-9]+", value):
        return int(value)
    return None


def _scalar(value):
    # 有限欄位也不能夾帶任意nested payload；型別不符仍保留unknown。
    return value if value is None or isinstance(value, (str, int, float, bool)) else None


def _team(value) -> dict:
    if not isinstance(value, Mapping):
        return {"Team": {"Code": None}, "Hitters": None}
    team = value.get("Team")
    code = _scalar(team.get("Code")) if isinstance(team, Mapping) else None
    hitters = value.get("Hitters")
    if isinstance(hitters, list):
        # 非Mapping row不解包猜欄位，僅保存四欄null，仍為unknown。
        rows = [{k: _scalar(r.get(k)) if isinstance(r, Mapping) else None for k in FIELDS} for r in hitters]
        # 穩定排序不修改原欄位值，重複／超過9人也原樣保留以供unknown判斷。
        rows.sort(
            key=lambda r: (
                integer(r.get("Lineup")) or 0,
                canonical(r.get("HitterAcnt")),
                canonical(r),
            )
        )
        hitters = rows
    elif isinstance(hitters, Mapping):
        hitters = {
            "unsupported_shape": "object",
            "projected_fields": {k: _scalar(hitters.get(k)) for k in FIELDS},
        }
    elif hitters is not None:
        hitters = {"unsupported_shape": "scalar"}
    return {"Team": {"Code": code}, "Hitters": hitters}


def project(game_id: str, raw: dict) -> dict:
    _, kind, sno = identity(game_id)
    if (
        not isinstance(raw, Mapping)
        or raw.get("GameId") != game_id
        or raw.get("KindCode") != kind
        or integer(raw.get("GameSno")) != sno
    ):
        raise ValueError("stats announcement source identity mismatch")
    return {
        "projection_version": PROJECTION_VERSION,
        **{k: _scalar(raw.get(k)) for k in ("GameId", "KindCode", "GameSno", "PreExeDate", "GameStatus")},
        "Visiting": _team(raw.get("Visiting")),
        "Home": _team(raw.get("Home")),
    }


def content_hash(projected: dict) -> str:
    return hashlib.sha256(
        canonical({k: v for k, v in projected.items() if k != "GameStatus"}).encode()
    ).hexdigest()


def _same(row: dict, projected: dict, version: str, status: str | None) -> bool:
    return (
        row["content_hash"] == version
        and row["raw_status"] == status
        and canonical(row["raw_payload"]) == canonical(projected)
    )


def observe(game_id: str, raw: dict, fetched_at: datetime) -> dict:
    """回應完成UTC觀測：同片段只last_seen，重現另片段；失敗由conn回滾。

    單writer租用及CLI明示local mode由操作者保證。沒有migrate或正式worker隱式寫入。
    """
    return observe_projected(game_id, project(game_id, raw), fetched_at)


def observe_projected(game_id: str, payload: dict, fetched_at: datetime) -> dict:
    """重播本機有限投影佇列；時間仍是原回應UTC，不取重播時鐘。"""
    year, kind, sno = identity(game_id)
    if set(payload) != {"projection_version", "GameId", "KindCode", "GameSno", "PreExeDate", "GameStatus", "Visiting", "Home"}:
        raise ValueError("announcement projected fields mismatch")
    if any(_scalar(payload[k]) != payload[k] for k in ("GameId", "KindCode", "GameSno", "PreExeDate", "GameStatus")):
        raise ValueError("announcement projected metadata fields mismatch")
    for side in ("Visiting", "Home"):
        team = payload[side]
        if not isinstance(team, Mapping) or set(team) != {"Team", "Hitters"} or not isinstance(team["Team"], Mapping) or set(team["Team"]) != {"Code"}:
            raise ValueError("announcement projected team fields mismatch")
        if _scalar(team["Team"]["Code"]) != team["Team"]["Code"]:
            raise ValueError("announcement projected team code mismatch")
        hitters = team["Hitters"]
        if isinstance(hitters, list):
            if any(not isinstance(r, Mapping) or set(r) != set(FIELDS) or any(_scalar(v) != v for v in r.values()) for r in hitters):
                raise ValueError("announcement projected hitter fields mismatch")
        elif hitters is not None:
            if not isinstance(hitters, Mapping):
                raise ValueError("announcement projected shape mismatch")
            expected = {"unsupported_shape", "projected_fields"} if hitters.get("unsupported_shape") == "object" else {"unsupported_shape"}
            if not isinstance(hitters, Mapping) or set(hitters) != expected or ("projected_fields" in hitters and (set(hitters["projected_fields"]) != set(FIELDS) or any(_scalar(v) != v for v in hitters["projected_fields"].values()))):
                raise ValueError("announcement projected shape mismatch")
    if payload["projection_version"] != PROJECTION_VERSION or payload["GameId"] != game_id or payload["KindCode"] != kind or integer(payload["GameSno"]) != sno:
        raise ValueError("announcement projected identity mismatch")
    if (
        not isinstance(fetched_at, datetime)
        or fetched_at.tzinfo is None
        or fetched_at.utcoffset() is None
    ):
        raise ValueError("announcement response timestamp must be timezone aware")
    fetched_at = fetched_at.astimezone(UTC)
    version = content_hash(payload)
    status = payload.get("GameStatus")
    status = status if isinstance(status, str) else None
    scope = (year, kind, sno, SOURCE_TYPE)
    with conn() as c, c.cursor(row_factory=dict_row) as cur:
        cur.execute("SET LOCAL statement_timeout = '5s'")
        cur.execute("SET LOCAL lock_timeout = '1s'")
        cur.execute(
            """SELECT * FROM cpbl.game_lineup_announcement_revisions
                       WHERE year=%s AND kind_code=%s AND game_sno=%s AND source_type=%s
                         AND fetched_at=%s""",
            (*scope, fetched_at),
        )
        existing = cur.fetchone()
        if existing is not None:
            if not _same(existing, payload, version, status):
                raise ValueError("announcement natural key evidence conflict")
            # 同鍵重送不是新取得，不能借今日時間改寫舊片段。
            return {
                "action": "replayed",
                "fetched_at": existing["fetched_at"],
                "content_hash": version,
            }
        cur.execute(
            """SELECT * FROM cpbl.game_lineup_announcement_revisions
                       WHERE year=%s AND kind_code=%s AND game_sno=%s AND source_type=%s
                       ORDER BY fetched_at DESC LIMIT 1""",
            scope,
        )
        latest = cur.fetchone()
        if latest is not None:
            if fetched_at < latest["last_seen_at"]:
                raise ValueError("announcement observation clock moved backwards")
            if _same(latest, payload, version, status):
                cur.execute(
                    """UPDATE cpbl.game_lineup_announcement_revisions
                               SET last_seen_at=GREATEST(last_seen_at,%s)
                               WHERE year=%s AND kind_code=%s AND game_sno=%s AND source_type=%s
                                 AND fetched_at=%s""",
                    (fetched_at, *scope, latest["fetched_at"]),
                )
                return {
                    "action": "seen",
                    "fetched_at": latest["fetched_at"],
                    "content_hash": version,
                }
            if fetched_at == latest["last_seen_at"]:
                raise ValueError("announcement timestamp has contradictory evidence")
        source_url = f"https://stats.cpbl.com.tw/api/proxy/v1/games/{game_id}"
        cur.execute(
            """INSERT INTO cpbl.game_lineup_announcement_revisions
                       (year,kind_code,game_sno,source_type,source_url,fetched_at,
                        content_hash,raw_status,raw_payload,last_seen_at)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s)""",
            (*scope, source_url, fetched_at, version, status, canonical(payload), fetched_at),
        )
        return {"action": "inserted", "fetched_at": fetched_at, "content_hash": version}
