"""逐場來源 revision：只保存可觀測事實，不推導 public status。"""

from __future__ import annotations

import hashlib
import json
from datetime import date
from typing import Any

from cpbl.db import conn

_SECRET_PARTS = ("password", "secret", "token", "api_key", "apikey", "authorization")
_DETAIL_TEXT_LIMIT = 500


def canonical_source_version(payload: Any) -> str:
    """以 canonical JSON 建立穩定 SHA-256；key 順序不影響 revision。"""
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def sanitize_detail(value: Any) -> Any:
    """遞迴遮蔽敏感 key，並限制外部錯誤文字長度。"""
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            normalized = str(key).lower().replace("-", "_")
            out[str(key)] = (
                "[REDACTED]"
                if any(part in normalized for part in _SECRET_PARTS)
                else sanitize_detail(item)
            )
        return out
    if isinstance(value, list):
        return [sanitize_detail(item) for item in value[:50]]
    if isinstance(value, str):
        return value[:_DETAIL_TEXT_LIMIT]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)[:_DETAIL_TEXT_LIMIT]


def record_source_revision(
    *, year: int, kind_code: str, game_sno: int, source: str, outcome: str,
    row_count: int, payload: Any = None, source_version: str | None = None,
    error_code: str | None = None, detail: dict[str, Any] | None = None,
) -> None:
    """冪等寫入來源 revision；相同內容只更新 last_seen_at／seen_count。"""
    version = source_version or canonical_source_version({
        "payload": payload, "outcome": outcome, "error_code": error_code,
    })
    safe_detail = sanitize_detail(detail or {})
    with conn() as c:
        c.execute(
            """
            INSERT INTO cpbl.game_source_revisions
                (year, kind_code, game_sno, source, source_version, outcome,
                 row_count, error_code, detail)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
            ON CONFLICT (year, kind_code, game_sno, source, source_version) DO UPDATE SET
                last_seen_at = now(),
                seen_count = cpbl.game_source_revisions.seen_count + 1,
                outcome = EXCLUDED.outcome,
                row_count = EXCLUDED.row_count,
                error_code = EXCLUDED.error_code,
                detail = EXCLUDED.detail
            """,
            (year, kind_code, game_sno, source, version, outcome, row_count,
             error_code, json.dumps(safe_detail, ensure_ascii=False)),
        )


def _to_int(value: Any) -> int | None:
    try:
        return int(float(value)) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _to_date(value: Any) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10].replace("/", "-"))
    except ValueError:
        return None


def record_schedule_revisions(entries: list[dict[str, Any]]) -> int:
    """保存每一筆 raw schedule entry；同 payload 重跑只更新 last_seen_at。"""
    schedule_rows: list[tuple[Any, ...]] = []
    source_rows: list[tuple[Any, ...]] = []
    for entry in entries:
        year = _to_int(entry.get("Year"))
        sno = _to_int(entry.get("GameSno"))
        kind = entry.get("KindCode")
        if year is None or sno is None or not kind:
            continue
        season_code = str(entry.get("GameSeasonCode") or "")
        payload_hash = canonical_source_version(entry)
        safe_payload = sanitize_detail(entry)
        schedule_rows.append((
            year, kind, season_code, sno, _to_int(entry.get("PresentStatus")),
            str(entry.get("GameResult")) if entry.get("GameResult") not in (None, "") else None,
            _to_date(entry.get("GameDate")), _to_date(entry.get("PreExeDate")),
            payload_hash, json.dumps(safe_payload, ensure_ascii=False),
        ))
        source_rows.append((
            year, kind, sno, "schedule", payload_hash, "available", 1, None,
            json.dumps({"game_season_code": season_code, "raw_status_recorded": True},
                       ensure_ascii=False),
        ))
    if not schedule_rows:
        return 0
    with conn() as c:
        c.cursor().executemany(
            """
            INSERT INTO cpbl.game_schedule_status_revisions
                (year, kind_code, game_season_code, game_sno, raw_present_status,
                 raw_game_result, raw_game_date, raw_pre_exe_date, payload_hash, raw_payload)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
            ON CONFLICT (year, kind_code, game_season_code, game_sno, payload_hash) DO UPDATE SET
                last_seen_at = now(),
                seen_count = cpbl.game_schedule_status_revisions.seen_count + 1
            """,
            schedule_rows,
        )
        c.cursor().executemany(
            """
            INSERT INTO cpbl.game_source_revisions
                (year, kind_code, game_sno, source, source_version, outcome,
                 row_count, error_code, detail)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
            ON CONFLICT (year, kind_code, game_sno, source, source_version) DO UPDATE SET
                last_seen_at = now(),
                seen_count = cpbl.game_source_revisions.seen_count + 1
            """,
            source_rows,
        )
    return len(schedule_rows)
