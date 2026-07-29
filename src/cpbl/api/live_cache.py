"""API 的唯讀 live cache adapter；Redis 失效時退化為既有 PostgreSQL 回應。"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from functools import lru_cache

import redis

from cpbl.config import settings
from cpbl.ingest.live_game_worker import RedisLiveGameCache

log = logging.getLogger("cpbl.api.livecache")


@lru_cache(maxsize=1)
def _cache() -> RedisLiveGameCache | None:
    if not settings.redis_url:
        return None
    client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
    return RedisLiveGameCache(
        client,
        prefix=settings.live_game_cache_prefix,
        snapshot_ttl_seconds=settings.live_game_snapshot_ttl_seconds,
        lock_ttl_seconds=settings.live_game_lock_ttl_seconds,
    )


def public_snapshot(snapshot: dict, *, now: datetime,
                    live_stale_after_seconds: int) -> dict:
    """加上 freshness；final 是不可變快照，不因時間經過誤標 stale。"""
    result = dict(snapshot)
    result["source"] = dict(snapshot.get("source") or {})
    phase = result.get("phase")
    result["poll_after_seconds"] = 12 if phase == "live" else None
    if phase == "final":
        result["freshness"] = "final"
        result["stale_after_seconds"] = None
        return result

    stale_after = live_stale_after_seconds if phase == "live" else 1200
    fetched_raw = result["source"].get("fetched_at")
    try:
        fetched_at = datetime.fromisoformat(fetched_raw)
        if fetched_at.tzinfo is None:
            fetched_at = fetched_at.replace(tzinfo=UTC)
        age = max(0.0, (now - fetched_at).total_seconds())
    except (TypeError, ValueError):
        age = float("inf")
    result["freshness"] = "stale" if age > stale_after else "fresh"
    result["stale_after_seconds"] = stale_after
    return result


def get_public_live_snapshot(year: int, kind: str, sno: int,
                             *, now: datetime | None = None) -> dict | None:
    cache = _cache()
    if cache is None:
        return None
    try:
        snapshot = cache.get_snapshot(year, kind, sno)
    except (OSError, ValueError, redis.RedisError) as exc:
        log.warning("live cache unavailable: %s", type(exc).__name__)
        return None
    if snapshot is None:
        return None
    return public_snapshot(
        snapshot,
        now=now or datetime.now(UTC),
        live_stale_after_seconds=settings.live_game_stale_after_seconds,
    )
