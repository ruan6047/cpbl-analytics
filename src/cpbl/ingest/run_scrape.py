"""CLI：爬官網逐場賽程/結果。

    uv run cpbl-scrape-games            # 預設抓當年（一軍例行賽）
    uv run cpbl-scrape-games 2020 2024  # 指定年份區間
"""

from __future__ import annotations

import logging
import sys
from datetime import date

from cpbl.db import migrate
from cpbl.ingest.cpbl_site import scrape_games


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
    log = logging.getLogger("cpbl.scrape")

    args = sys.argv[1:]
    this_year = date.today().year
    start = int(args[0]) if len(args) >= 1 else this_year
    end = int(args[1]) if len(args) >= 2 else start

    migrate()
    log.info("scraping games %s–%s …", start, end)
    totals = scrape_games(start, end)
    log.info("done. totals: %s (sum=%d)", totals, sum(totals.values()))


if __name__ == "__main__":
    main()
