"""CLI：爬官網球員異動（升一軍/降二軍）→ player_transactions。

    uv run cpbl-scrape-transactions             # 預設本季
    uv run cpbl-scrape-transactions 2025 2026   # 指定年度範圍 [start, end)

每日增量爬蟲會一併呼叫（見 run_refresh_recent）。官網反爬需 Playwright，只本機跑。
"""

from __future__ import annotations

import argparse
import logging
from datetime import date

from cpbl.db import migrate
from cpbl.ingest._cli import cli_parser
from cpbl.ingest.cpbl_transactions import scrape_transactions


def _parser() -> argparse.ArgumentParser:
    p = cli_parser("cpbl-scrape-transactions", __doc__)
    p.add_argument("start_year", nargs="?", type=int, help="起始年（含）；與 end_year 成對給")
    p.add_argument("end_year", nargs="?", type=int, help="結束年（不含）")
    return p


def main() -> None:
    parser = _parser()
    args = parser.parse_args()
    # 舊版只認「兩個都給」，單給一個會被靜默忽略而爬成當年——靜默吞參數是本卡要消滅的模式。
    if (args.start_year is None) != (args.end_year is None):
        parser.error("start_year 與 end_year 必須成對給定（範圍 [start, end)）")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
    if args.start_year is not None and args.end_year is not None:
        years = list(range(args.start_year, args.end_year))
    else:
        years = [date.today().year]
    migrate()
    out = scrape_transactions(years)
    logging.getLogger("cpbl.trans").info("done: %s", out)


if __name__ == "__main__":
    main()
