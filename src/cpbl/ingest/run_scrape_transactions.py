"""CLI：爬官網球員異動（升一軍/降二軍）→ player_transactions。

    uv run cpbl-scrape-transactions             # 預設本季
    uv run cpbl-scrape-transactions 2025 2026   # 指定年度範圍 [start, end)

每日增量爬蟲會一併呼叫（見 run_refresh_recent）。官網反爬需 Playwright，只本機跑。
"""

from __future__ import annotations

import logging
import sys
from datetime import date

from cpbl.db import migrate
from cpbl.ingest.cpbl_transactions import scrape_transactions


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
    if len(sys.argv) >= 3:
        years = list(range(int(sys.argv[1]), int(sys.argv[2])))
    else:
        years = [date.today().year]
    migrate()
    out = scrape_transactions(years)
    logging.getLogger("cpbl.trans").info("done: %s", out)


if __name__ == "__main__":
    main()
