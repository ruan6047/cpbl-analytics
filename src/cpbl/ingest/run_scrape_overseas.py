"""CLI：抓淡江棒球維基旅外列表 → cpbl.overseas（一次性 + 手動刷新，不掛 cron）。

    uv run cpbl-scrape-overseas
"""

from __future__ import annotations

import argparse
import logging

from cpbl.db import migrate
from cpbl.ingest._cli import cli_parser
from cpbl.ingest.cpbl_overseas import scrape_overseas


def _parser() -> argparse.ArgumentParser:
    return cli_parser("cpbl-scrape-overseas", __doc__)


def main() -> None:
    _parser().parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
    migrate()
    scrape_overseas()


if __name__ == "__main__":
    main()
