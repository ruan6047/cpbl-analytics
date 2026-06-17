"""CLI：回填本季登錄選手的官方進階數據（stats.cpbl.com.tw 彙總 + 官方 PR）。

    uv run cpbl-scrape-advanced            # 本季全名單
    uv run cpbl-scrape-advanced 1.5        # 指定每請求間隔秒數

冪等 UPSERT。RSC 解析較脆弱，個別失敗會略過不中斷。
"""

from __future__ import annotations

import logging
import sys
from datetime import date

from cpbl.db import migrate
from cpbl.ingest.cpbl_advanced import current_players, scrape_advanced


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
    delay = float(sys.argv[1]) if len(sys.argv) >= 2 else 1.0
    year = date.today().year
    migrate()
    players = current_players()
    logging.getLogger("cpbl.advanced").info("回填 %d 位選手官方進階數據 …", len(players))
    n = scrape_advanced(year, players, delay=delay)
    logging.getLogger("cpbl.advanced").info("done: %d 筆", n)


if __name__ == "__main__":
    main()
