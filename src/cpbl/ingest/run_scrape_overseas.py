"""CLI：抓淡江棒球維基旅外列表 → cpbl.overseas（一次性 + 手動刷新，不掛 cron）。

    uv run cpbl-scrape-overseas
"""

from __future__ import annotations

import logging

from cpbl.db import migrate
from cpbl.ingest.cpbl_overseas import scrape_overseas


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
    migrate()
    scrape_overseas()


if __name__ == "__main__":
    main()
