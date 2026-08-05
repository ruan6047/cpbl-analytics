"""CLI：抓維基百科歷任總教練 → cpbl.managers（一次性 + 手動刷新，不掛 cron）。

    uv run cpbl-scrape-managers
"""

from __future__ import annotations

import argparse
import logging

from cpbl.db import migrate
from cpbl.ingest._cli import cli_parser
from cpbl.ingest.cpbl_managers import scrape_managers


def _parser() -> argparse.ArgumentParser:
    return cli_parser("cpbl-scrape-managers", __doc__)


def main() -> None:
    _parser().parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
    migrate()
    result = scrape_managers()
    logging.getLogger("cpbl.managers").info(
        "完成：%d 隊 / %d 位總教練 %s", len(result), sum(result.values()), result)


if __name__ == "__main__":
    main()
