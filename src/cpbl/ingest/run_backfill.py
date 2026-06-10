"""CLI 入口：套用 migration + 從 cpbl-opendata 回填。

    uv run cpbl-backfill
"""

from __future__ import annotations

import logging

from cpbl.db import migrate
from cpbl.ingest.opendata import backfill


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
    log = logging.getLogger("cpbl.backfill")

    log.info("applying migrations…")
    applied = migrate()
    log.info("migrations applied: %s", applied)

    log.info("backfilling from cpbl-opendata…")
    totals = backfill()
    log.info("done. totals: %s", totals)


if __name__ == "__main__":
    main()
