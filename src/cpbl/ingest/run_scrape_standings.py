"""CLI：爬官方球隊戰績（含上下半季：和局/勝差/淘汰指數/H2H/主客場/連勝敗/近十場）。

    uv run cpbl-scrape-standings          # 當年
    uv run cpbl-scrape-standings 2025     # 指定年
"""

from __future__ import annotations

import logging
import sys
from datetime import date

from cpbl.db import migrate
from cpbl.ingest.cpbl_standings import scrape_standings


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
    year = int(sys.argv[1]) if len(sys.argv) >= 2 else date.today().year
    migrate()
    out = scrape_standings(year)
    logging.getLogger("cpbl.standings").info("done %d: %s", year, out)


if __name__ == "__main__":
    main()
