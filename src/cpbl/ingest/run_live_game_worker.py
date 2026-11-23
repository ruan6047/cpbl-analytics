"""集中式 stats live worker；預設關閉，需 ``LIVE_GAME_WORKER_ENABLED=true``。"""

from __future__ import annotations

import argparse
import json
import logging
import os
import random
import signal
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

import redis

from cpbl.config import parse_postseason_kinds, settings
from cpbl.ingest.live_game_worker import (
    LiveGameWorker,
    RedisLiveGameCache,
    StatsLiveSource,
    next_delay_seconds,
)

log = logging.getLogger("cpbl.liveworker")


def bind_evening_inputs(now: datetime):
    """Opt-in, once per already successful live worker cycle, with no new DB or HTTP."""
    if os.environ.get("CPBL_EVENING_ASSESSMENT_AUTO_BIND") != "1":
        return []
    from cpbl.ingest.evening_assessment_binder import run_from_environment

    return run_from_environment(
        now, limit=int(os.environ["CPBL_EVENING_BIND_LIMIT"]),
        max_age=int(os.environ["CPBL_EVENING_BIND_MAX_OBSERVATION_AGE"]),
        ttl=int(os.environ["CPBL_EVENING_BIND_TTL"]),
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="CPBL centralized live game worker")
    parser.add_argument("--once", action="store_true", help="執行一個 cycle 後輸出 JSON 並結束")
    parser.add_argument(
        "--persist-announcements", action="store_true",
        help="明示在已租用local DB保存2026 E/C公告版本；預設不寫DB",
    )
    parser.add_argument("--sync-announcements", action="store_true",
                        help="本機常設owner：有限投影佇列＋既有LINEUP_ONLY保護同步；須persist")
    args = parser.parse_args(argv)
    owner = None
    if args.sync_announcements:
        address = urlsplit(settings.database_url)
        redis_address = urlsplit(settings.redis_url or "")
        if not {"database_url", "redis_url"} <= getattr(settings, "model_fields_set", set()) or set(parse_postseason_kinds(settings.live_game_postseason_kinds)) != {"E", "C"} or not args.persist_announcements or address.hostname not in ("127.0.0.1", "localhost") or address.port != 5433 or address.path != "/cpbl" or redis_address.hostname not in ("127.0.0.1", "localhost") or redis_address.port != 16379:
            raise ValueError("announcement sync requires explicitly configured local DB5433/Redis16379 and persist mode")
        from cpbl.ingest.announcement_owner import AnnouncementOwner
        owner = AnnouncementOwner(Path(__file__).resolve().parents[3])
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
    if not settings.live_game_worker_enabled:
        log.info("live worker disabled（LIVE_GAME_WORKER_ENABLED=false）")
        return
    if not settings.redis_url:
        raise RuntimeError("live worker enabled 但 REDIS_URL 未設定")
    # 先解析再開任何連線：值打錯要在啟動時炸開（#237；預設空＝A-only）。
    postseason_kinds = parse_postseason_kinds(settings.live_game_postseason_kinds)

    redis_client = redis.Redis.from_url(
        settings.redis_url,
        decode_responses=True,
        socket_connect_timeout=2.0,
        socket_timeout=2.0,
    )
    cache = RedisLiveGameCache(
        redis_client,
        prefix=settings.live_game_cache_prefix,
        snapshot_ttl_seconds=settings.live_game_snapshot_ttl_seconds,
        lock_ttl_seconds=settings.live_game_lock_ttl_seconds,
    )
    source = StatsLiveSource()
    observation_sink = None
    if args.persist_announcements:
        from cpbl.ingest.lineup_announcements import observe

        observation_sink = owner.observe if owner else observe
    readiness = None
    if not args.once:
        # #332：常駐模式才有就緒證據（--once 輸出與退出碼維持原樣）。
        from cpbl.ingest.live_worker_readiness import LiveWorkerReadiness

        readiness = LiveWorkerReadiness(
            directory=settings.live_worker_readiness_dir,
            redis_client=redis_client,
            prefix=settings.live_game_cache_prefix,
            cache=cache,
            max_games=settings.live_game_max_games_per_cycle,
        )
        readiness.start()
        source.payload_observer = readiness.partition_payload
    facts_root = os.environ.get("CPBL_EVENING_TRUSTED_FACTS_ROOT")
    if facts_root:
        from cpbl.ingest.evening_official_facts import final_score_writer, writer

        source.trusted_schedule_observer = writer(Path(facts_root))
        source.trusted_game_observer = final_score_writer(Path(facts_root))
    worker = LiveGameWorker(
        cache=cache,
        fetch_schedule=source.fetch_schedule,
        fetch_game=source.fetch_game,
        max_games_per_cycle=settings.live_game_max_games_per_cycle,
        postseason_kinds=postseason_kinds,
        observation_sink=observation_sink,
        readiness_observer=readiness,
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
            if readiness:
                readiness.begin_attempt(datetime.now(UTC))
            try:
                result = worker.run_cycle(datetime.now(UTC))
            except Exception as exc:  # noqa: BLE001 — process boundary，記錄後退避
                failures += 1
                result = {"state": "error", "error_type": type(exc).__name__}
                log.exception("live cycle failed")
            else:
                failures = 0 if result.get("state") == "ok" else failures
                log.info("live cycle %s", result)
                if result.get("state") == "ok":
                    try:
                        bindings = bind_evening_inputs(datetime.now(UTC))
                        if bindings:
                            log.info("evening independent assessment binding %s", bindings)
                    except (KeyError, OSError, ValueError) as exc:
                        log.warning("evening assessment binding unavailable (%s)", type(exc).__name__)
            if owner:
                result["announcement_sync"] = owner.after_cycle()
                log.info("announcement owner %s", result["announcement_sync"])
            if args.once:
                print(json.dumps(result, ensure_ascii=False, sort_keys=True))
                if args.persist_announcements and (
                    result.get("announcement_errors") or result.get("state") != "ok"
                    or owner and result["announcement_sync"]["state"] not in ("idle", "synced")
                ):
                    raise SystemExit(1)
                return
            delay = next_delay_seconds(
                result,
                failures=failures,
                jitter=lambda: random.uniform(0.9, 1.1),
            )
            if readiness:
                readiness.end_attempt(result, delay, datetime.now(UTC))
            for _ in range(delay):
                if stopping:
                    break
                time.sleep(1)
    finally:
        if readiness:
            readiness.close()
        try:
            source.close()
        finally:
            try:
                redis_client.close()
            finally:
                if args.persist_announcements:
                    from cpbl import db

                    if db._pool is not None:
                        db._pool.close()


if __name__ == "__main__":
    main()
