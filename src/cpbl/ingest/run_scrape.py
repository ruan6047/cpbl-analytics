"""CLI：爬官網逐場賽程/結果（一軍：例行賽 A + 總冠軍賽 C + 季後挑戰賽 E）。

    uv run cpbl-scrape-games            # 預設抓當年
    uv run cpbl-scrape-games 2020 2024  # 指定年份區間
"""

from __future__ import annotations

import logging
import sys
from datetime import date

from cpbl.db import migrate
from cpbl.ingest.cpbl_site import scrape_games

KINDS = ["A", "C", "E"]  # 一軍例行賽 / 總冠軍賽 / 季後挑戰賽


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
    log = logging.getLogger("cpbl.scrape")

    args = sys.argv[1:]
    this_year = date.today().year
    start = int(args[0]) if len(args) >= 1 else this_year
    end = int(args[1]) if len(args) >= 2 else start

    migrate()
    grand = 0
    for kind in KINDS:
        try:
            totals = scrape_games(start, end, kind)
            n = sum(totals.values())
            grand += n
            log.info("kind=%s %s–%s: %s", kind, start, end, totals)
        except Exception as e:  # noqa: BLE001 — 某賽別當年無資料時容錯
            log.warning("kind=%s 略過：%s", kind, e)
    log.info("done. 合計 %d 場", grand)


if __name__ == "__main__":
    main()
