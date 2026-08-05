"""CLI：爬官網 /field 球場規格 enrich venue_dim（一次性 + 手動刷新）。

    uv run cpbl-scrape-field              # 全部可對照球場（~12 頁）
    uv run cpbl-scrape-field 大巨蛋 天母   # 只爬指定球場（小量驗證）
"""

from __future__ import annotations

import argparse
import logging

from cpbl.db import migrate
from cpbl.ingest._cli import cli_parser
from cpbl.ingest.cpbl_field import scrape


def _parser() -> argparse.ArgumentParser:
    p = cli_parser("cpbl-scrape-field", __doc__)
    p.add_argument("venues", nargs="*", metavar="VENUE",
                   help="只爬指定球場名（省略＝全部可對照球場）")
    return p


def main() -> None:
    args = _parser().parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
    migrate()
    only = args.venues or None
    out = scrape(only=only)
    logging.getLogger("cpbl.field").info("完成：%s", out)


if __name__ == "__main__":
    main()
