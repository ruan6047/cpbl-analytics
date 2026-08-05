"""CLI 入口：套用 migration + 從 cpbl-opendata 回填。

    uv run cpbl-backfill
"""

from __future__ import annotations

import argparse
import logging

from cpbl.db import migrate
from cpbl.ingest._cli import cli_parser
from cpbl.ingest.opendata import backfill


def _parser() -> argparse.ArgumentParser:
    return cli_parser("cpbl-backfill", __doc__)


def main() -> None:
    _parser().parse_args()
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
