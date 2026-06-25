"""CLI：抓維基百科歷任總教練 → cpbl.managers（一次性 + 手動刷新，不掛 cron）。

    uv run cpbl-scrape-managers
"""

from __future__ import annotations

import logging

from cpbl.db import migrate
from cpbl.ingest.cpbl_managers import scrape_managers


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
    migrate()
    result = scrape_managers()
    total = sum(result.values())
    logging.getLogger("cpbl.managers").info("完成：%d 隊 / %d 位總教練 %s", len(result), total, result)


if __name__ == "__main__":
    main()
