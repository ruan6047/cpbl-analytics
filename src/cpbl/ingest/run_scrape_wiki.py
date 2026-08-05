"""CLI：抓維基百科個人頁 infobox（所屬球隊／國際賽獎牌／獎項）→ cpbl.wiki_*。

目標＝現役 + 教練/總教練 + 歷史排行前段，以 name+birthday 比對到 players。
一次性 + 手動刷新（不掛 cron）。

    uv run cpbl-scrape-wiki            # 全部目標
    uv run cpbl-scrape-wiki 30         # 只跑前 30（測試用）
"""

from __future__ import annotations

import argparse
import logging
from datetime import date

from cpbl.db import migrate
from cpbl.ingest._cli import cli_parser
from cpbl.ingest.cpbl_wiki import run


def _parser() -> argparse.ArgumentParser:
    p = cli_parser("cpbl-scrape-wiki", __doc__)
    p.add_argument("limit", nargs="?", type=int, help="只跑前 N 個目標（測試用；省略＝全部）")
    return p


def main() -> None:
    args = _parser().parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
    migrate()
    st = run(year=date.today().year, limit=args.limit)
    logging.getLogger("cpbl.wiki").info("完成：%s", st)


if __name__ == "__main__":
    main()
