"""CLI：爬官方球隊戰績（含上下半季：和局/勝差/淘汰指數/H2H/主客場/連勝敗/近十場）。

    uv run cpbl-scrape-standings          # 當年
    uv run cpbl-scrape-standings 2025     # 指定年
"""

from __future__ import annotations

import argparse
import logging
from datetime import date

from cpbl.db import migrate
from cpbl.ingest._cli import cli_parser
from cpbl.ingest.cpbl_standings import scrape_standings


def _parser() -> argparse.ArgumentParser:
    p = cli_parser("cpbl-scrape-standings", __doc__)
    p.add_argument("year", nargs="?", type=int, help="年份（省略＝當年）")
    return p


def main() -> None:
    args = _parser().parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
    year = args.year if args.year is not None else date.today().year
    migrate()
    out = scrape_standings(year)
    logging.getLogger("cpbl.standings").info("done %d: %s", year, out)


if __name__ == "__main__":
    main()
