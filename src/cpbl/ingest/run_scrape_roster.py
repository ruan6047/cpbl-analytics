"""CLI：爬官方球隊登錄名單（官網 /team/index 的 TeamPlayersList）。

    uv run cpbl-scrape-roster          # 當年
    uv run cpbl-scrape-roster 2026     # 指定年

「現役選手」以此為準，而非出賽推導——登錄了但整季未出賽的選手，用 *_current（需有成績）
或 gamelog（需出賽）都會漏掉。注意官網此頁為**一軍登錄名單**，不含二軍。
"""

from __future__ import annotations

import logging
import sys
from datetime import date

from cpbl.db import migrate
from cpbl.ingest.cpbl_roster import scrape_roster


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
    year = int(sys.argv[1]) if len(sys.argv) >= 2 else date.today().year
    migrate()
    out = scrape_roster(year)
    logging.getLogger("cpbl.roster").info("done %d: %s", year, out)


if __name__ == "__main__":
    main()
