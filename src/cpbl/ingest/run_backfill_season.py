"""CLI：以官方 teamscore 回填某年的 season-level 彙總（opendata 未涵蓋年份，如 2025）。

    uv run cpbl-backfill-season 2025
"""

from __future__ import annotations

import logging
import sys

from cpbl.db import migrate
from cpbl.ingest.cpbl_season_backfill import backfill_batting_season, backfill_pitching_season


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
    if len(sys.argv) < 2:
        print("用法：cpbl-backfill-season <YEAR>")
        sys.exit(1)
    year = int(sys.argv[1])
    migrate()
    b = backfill_batting_season(year)
    p = backfill_pitching_season(year)
    logging.getLogger("cpbl.seasonbf").info("done %d: batting=%d pitching=%d", year, b, p)


if __name__ == "__main__":
    main()
