"""CLI：以官方 teamscore 回填某年的 season-level 彙總（opendata 未涵蓋年份，如 2025）。

    uv run cpbl-backfill-season 2025
"""

from __future__ import annotations

import argparse
import logging

from cpbl.db import migrate
from cpbl.ingest._cli import cli_parser
from cpbl.ingest.cpbl_season_backfill import backfill_batting_season, backfill_pitching_season


def _parser() -> argparse.ArgumentParser:
    p = cli_parser("cpbl-backfill-season", __doc__)
    p.add_argument("year", type=int, help="要回填的年份")
    return p


def main() -> None:
    args = _parser().parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
    year = args.year
    migrate()
    b = backfill_batting_season(year)
    p = backfill_pitching_season(year)
    logging.getLogger("cpbl.seasonbf").info("done %d: batting=%d pitching=%d", year, b, p)


if __name__ == "__main__":
    main()
