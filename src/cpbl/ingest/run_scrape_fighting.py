"""CLI：爬本季登錄打者的「投打對決」(batter-vs-pitcher)。

範圍：一軍正式賽別（A 例行賽 / C 總冠軍賽 / E 季後挑戰賽），
年度 = 生涯累計(9999) + 指定年。

    uv run cpbl-scrape-fighting                 # 當年 + 9999、delay 1.2s
    uv run cpbl-scrape-fighting 2026            # 指定年 + 9999
    uv run cpbl-scrape-fighting 2026 2.0        # + 每請求間隔秒數
    uv run cpbl-scrape-fighting 2026 1.2 cur    # 第三參數 cur：只保留本季登錄一軍投手

資料量大（每打者數十請求），中途可安全中斷重跑（冪等 UPSERT）。
"""

from __future__ import annotations

import argparse
import logging
from datetime import date

from cpbl.db import migrate
from cpbl.ingest._cli import cli_parser
from cpbl.ingest.cpbl_fighting import YEAR_CAREER, _current_pitchers, scrape_matchups


def _parser() -> argparse.ArgumentParser:
    p = cli_parser("cpbl-scrape-fighting", __doc__)
    p.add_argument("year", nargs="?", type=int, help="年份（省略＝當年）；一律再加生涯 9999")
    p.add_argument("delay", nargs="?", type=float, default=1.2, help="每請求間隔秒數（預設 1.2）")
    p.add_argument("scope", nargs="?", choices=("cur",),
                   help="cur＝只保留本季登錄一軍投手（省略＝全部）")
    return p


def main() -> None:
    args = _parser().parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
    year = args.year if args.year is not None else date.today().year
    delay = args.delay
    pitcher_ids = _current_pitchers() if args.scope == "cur" else None

    migrate()
    total = scrape_matchups([YEAR_CAREER, year], delay=delay, pitcher_ids=pitcher_ids)
    logging.getLogger("cpbl.fighting").info("done: %d 對戰列 (years=[%d,%d])", total, YEAR_CAREER, year)


if __name__ == "__main__":
    main()
