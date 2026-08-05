"""CLI：爬現役球團教練團（官網 /team/index）。

    uv run cpbl-scrape-coaches          # 當年
    uv run cpbl-scrape-coaches 2026     # 指定年
"""

from __future__ import annotations

import argparse
import logging
from datetime import date

from cpbl.db import migrate
from cpbl.ingest._cli import cli_parser
from cpbl.ingest.cpbl_coaches import scrape_coaches


def _parser() -> argparse.ArgumentParser:
    p = cli_parser("cpbl-scrape-coaches", __doc__)
    p.add_argument("year", nargs="?", type=int, help="年份（省略＝當年）")
    return p


def main() -> None:
    args = _parser().parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
    year = args.year if args.year is not None else date.today().year
    migrate()
    out = scrape_coaches(year)
    logging.getLogger("cpbl.coaches").info("done %d: %s", year, out)


if __name__ == "__main__":
    main()
