"""CLI：抓官網年度獎項 → cpbl.player_awards（本機台灣 IP；一次性 + 手動刷新）。

    uv sync --group scrape && uv run cpbl-scrape-awards
"""

from __future__ import annotations

import logging

from cpbl.db import migrate
from cpbl.ingest.cpbl_awards import scrape_awards


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
    migrate()
    scrape_awards()


if __name__ == "__main__":
    main()
