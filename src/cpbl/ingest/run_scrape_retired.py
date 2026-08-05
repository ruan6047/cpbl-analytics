"""CLI：抓維基各隊退休背號 → cpbl.retired_numbers（一次性 + 手動刷新，不掛 cron）。

    uv run cpbl-scrape-retired
"""

from __future__ import annotations

import argparse
import logging

from cpbl.db import migrate
from cpbl.ingest._cli import cli_parser
from cpbl.ingest.cpbl_retired import scrape_retired


def _parser() -> argparse.ArgumentParser:
    return cli_parser("cpbl-scrape-retired", __doc__)


def main() -> None:
    _parser().parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
    migrate()
    result = scrape_retired()
    logging.getLogger("cpbl.retired").info(
        "完成：%d 隊 / %d 個退休背號 %s", len(result), sum(result.values()), result)


if __name__ == "__main__":
    main()
