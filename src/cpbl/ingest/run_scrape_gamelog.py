"""CLI：回填本季每場賽況（逐局比分 + 逐打席事件流）。

    uv run cpbl-scrape-gamelog            # 本季所有已完成場次
    uv run cpbl-scrape-gamelog 2026       # 指定年份

冪等 UPSERT，可重跑。
"""

from __future__ import annotations

import logging
import sys
from datetime import date

from cpbl.db import migrate
from cpbl.ingest.cpbl_gamelog import completed_snos, scrape_gamelogs


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
    year = int(sys.argv[1]) if len(sys.argv) >= 2 else date.today().year
    migrate()
    snos = completed_snos(year)
    logging.getLogger("cpbl.gamelog").info("回填 %d 場已完成賽事的賽況 …", len(snos))
    out = scrape_gamelogs(year, snos)
    logging.getLogger("cpbl.gamelog").info("done: %s", out)


if __name__ == "__main__":
    main()
