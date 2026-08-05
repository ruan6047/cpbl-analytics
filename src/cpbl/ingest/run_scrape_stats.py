"""CLI：爬本季投手成績（ERA + 進階指標 + 名字）。

    uv run cpbl-scrape-stats            # 預設當年
    uv run cpbl-scrape-stats 2025 2026  # 指定區間
"""

from __future__ import annotations

import argparse
import logging
from datetime import date

from cpbl.db import migrate
from cpbl.ingest._cli import cli_parser
from cpbl.ingest.cpbl_stats import scrape_all


def _parser() -> argparse.ArgumentParser:
    p = cli_parser("cpbl-scrape-stats", __doc__)
    p.add_argument("start_year", nargs="?", type=int, help="起始年（省略＝當年）")
    p.add_argument("end_year", nargs="?", type=int, help="結束年（省略＝同起始年）")
    return p


def main() -> None:
    args = _parser().parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
    this_year = date.today().year
    start = args.start_year if args.start_year is not None else this_year
    end = args.end_year if args.end_year is not None else start
    migrate()
    totals = scrape_all(start, end, this_year)
    logging.getLogger("cpbl.stats").info("done: %s", totals)


if __name__ == "__main__":
    main()
