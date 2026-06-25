"""CLI：爬現役球團教練團（官網 /team/index）。

    uv run cpbl-scrape-coaches          # 當年
    uv run cpbl-scrape-coaches 2026     # 指定年
"""

from __future__ import annotations

import logging
import sys
from datetime import date

from cpbl.db import migrate
from cpbl.ingest.cpbl_coaches import scrape_coaches


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
    year = int(sys.argv[1]) if len(sys.argv) >= 2 else date.today().year
    migrate()
    out = scrape_coaches(year)
    logging.getLogger("cpbl.coaches").info("done %d: %s", year, out)


if __name__ == "__main__":
    main()
