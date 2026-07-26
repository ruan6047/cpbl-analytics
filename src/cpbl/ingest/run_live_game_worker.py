"""集中式 stats live worker；預設關閉，需 ``LIVE_GAME_WORKER_ENABLED=true``。"""

from __future__ import annotations

import logging
import random
import signal
import time
from datetime import UTC, datetime

import redis

from cpbl.config import settings
from cpbl.ingest.live_game_worker import (
    LiveGameWorker,
    RedisLiveGameCache,
    StatsLiveSource,
    next_delay_seconds,
)

log = logging.getLogger("cpbl.liveworker")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
    if not settings.live_game_worker_enabled:
        log.info("live worker disabled（LIVE_GAME_WORKER_ENABLED=false）")
        return
    if not settings.redis_url:
        raise RuntimeError("live worker enabled 但 REDIS_URL 未設定")

    redis_client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
    cache = RedisLiveGameCache(
        redis_client,
        prefix=settings.live_game_cache_prefix,
        snapshot_ttl_seconds=settings.live_game_snapshot_ttl_seconds,
        lock_ttl_seconds=settings.live_game_lock_ttl_seconds,
    )
    source = StatsLiveSource()
    worker = LiveGameWorker(
        cache=cache,
        fetch_schedule=source.fetch_schedule,
        fetch_game=source.fetch_game,
        max_games_per_cycle=settings.live_game_max_games_per_cycle,
    )
    stopping = False

    def _stop(_signum, _frame) -> None:
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    failures = 0
    try:
        while not stopping:
            try:
                result = worker.run_cycle(datetime.now(UTC))
            except Exception as exc:  # noqa: BLE001 — process boundary，記錄後退避
                failures += 1
                result = {"state": "error", "error_type": type(exc).__name__}
                log.exception("live cycle failed")
            else:
                failures = 0 if result.get("state") == "ok" else failures
                log.info("live cycle %s", result)
            delay = next_delay_seconds(
                result,
                failures=failures,
                jitter=lambda: random.uniform(0.9, 1.1),
            )
            for _ in range(delay):
                if stopping:
                    break
                time.sleep(1)
    finally:
        source.close()
        redis_client.close()


if __name__ == "__main__":
    main()
