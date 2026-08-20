"""CLI：爬官方球隊戰績（含上下半季：和局/勝差/淘汰指數/H2H/主客場/連勝敗/近十場）。

    uv run cpbl-scrape-standings          # 當年（唯一會成功的用法）
    uv run cpbl-scrape-standings 2025     # 指定年 → 預期以對帳失敗告終，見下

⚠️ **官網忽略 `Year` 參數恆回當季**，所以指定舊年份幾乎必定拿到當季數字。爬蟲會在寫入前
以本地 `cpbl.games` 對帳（見 `cpbl_standings.check_year_consistency`），對不上就**拒寫並以
非 0 退出碼結束**——這支 CLI 對非當季年份預期是失敗的，那是正確行為不是壞掉。
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date

from cpbl.db import migrate
from cpbl.ingest._cli import cli_parser
from cpbl.ingest.cpbl_standings import StandingsYearMismatch, scrape_standings


def _parser() -> argparse.ArgumentParser:
    p = cli_parser("cpbl-scrape-standings", __doc__)
    p.add_argument("year", nargs="?", type=int, help="年份（省略＝當年）")
    return p


def main() -> None:
    args = _parser().parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
    year = args.year if args.year is not None else date.today().year
    log = logging.getLogger("cpbl.standings")
    migrate()
    try:
        out = scrape_standings(year)
    except StandingsYearMismatch as e:
        # 硬失敗：資料沒有寫進去，退出碼必須讓呼叫端（scrape-daily.sh／人）看得出來。
        log.error("年份對帳失敗，未寫入任何資料：%s", e)
        sys.exit(1)
    log.info("done %d: %s", year, out)


if __name__ == "__main__":
    main()
