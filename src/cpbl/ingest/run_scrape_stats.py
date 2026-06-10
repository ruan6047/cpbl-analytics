"""CLI：爬本季投手成績（ERA + 進階指標 + 名字）。

    uv run cpbl-scrape-stats            # 預設當年
    uv run cpbl-scrape-stats 2025 2026  # 指定區間
"""

from __future__ import annotations

import logging
import sys
from datetime import date

from cpbl.db import migrate
from cpbl.ingest.cpbl_stats import scrape_all


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
    args = sys.argv[1:]
    this_year = date.today().year
    start = int(args[0]) if len(args) >= 1 else this_year
    end = int(args[1]) if len(args) >= 2 else start
    migrate()
    totals = scrape_all(start, end, this_year)
    logging.getLogger("cpbl.stats").info("done: %s", totals)


if __name__ == "__main__":
    main()
