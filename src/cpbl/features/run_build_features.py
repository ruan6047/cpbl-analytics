"""CLI：建賽果預測特徵表（cpbl.game_features）。

    uv run cpbl-build-features
    python -m cpbl.features.run_build_features --jobs  # 已備 schema，只建特徵
"""

from __future__ import annotations

import argparse
import json
import logging
import os

from cpbl.ingest._cli import cli_parser


def _parser() -> argparse.ArgumentParser:
    parser = cli_parser("cpbl-build-features", __doc__)
    parser.add_argument("--jobs", action="store_true", help="明確 DB 環境，只建特徵、不 migrate 或訓練")
    return parser


def _jobs() -> int:
    result = {"scope": "game_features", "ok": False, "stage": "environment",
              "row_count": None, "errors": []}
    db = None
    pool_log = logging.getLogger("psycopg.pool")
    disabled = pool_log.disabled
    pool_log.disabled = True  # 連線錯誤不回顯 DSN；只輸出固定階段與計數。
    try:
        # 在 import config/DB 之前拒絕 cwd/.env，不沿用 Mac 的隱式設定或預設 DSN。
        if os.path.lexists(".env") or not os.environ.get("DATABASE_URL"):
            raise ValueError("explicit_environment_required")
        from cpbl import db
        from cpbl.config import settings
        from cpbl.features.outcome import materialize

        if settings.database_url != os.environ["DATABASE_URL"]:
            raise ValueError("cached_environment_mismatch")
        result["stage"] = "feature_build"
        count = materialize()
        # 原函式契約是 int；帶 errors 的其他回傳型別不能被當成單步成功。
        if type(count) is not int or count < 0:
            raise ValueError("invalid_feature_result")
        result.update(ok=True, stage="complete", row_count=count)
    except Exception:
        result["errors"].append(result["stage"])
    finally:
        try:
            if db is not None and db._pool is not None:
                db._pool.close()
                db._pool = None
        except Exception:
            result.update(ok=False, stage="close_pool")
            result["errors"].append("close_pool")
        pool_log.disabled = disabled
    print(json.dumps(result))
    return 0 if result["ok"] and not result["errors"] else 1


def main(argv: list[str] | None = None) -> int:
    if _parser().parse_args(argv).jobs:
        return _jobs()
    from cpbl.db import migrate
    from cpbl.features.outcome import materialize

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
    log = logging.getLogger("cpbl.features")
    migrate()
    n = materialize()
    log.info("game_features materialized: %d rows", n)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
