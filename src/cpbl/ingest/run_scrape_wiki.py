"""CLI：抓維基百科個人頁 infobox（所屬球隊／國際賽獎牌／獎項）→ cpbl.wiki_*。

目標＝現役 + 教練/總教練 + 歷史排行前段，以 name+birthday 比對到 players。
一次性 + 手動刷新（不掛 cron）。

    uv run cpbl-scrape-wiki            # 全部目標
    uv run cpbl-scrape-wiki 30         # 只跑前 30（測試用）
"""

from __future__ import annotations

import logging
import sys
from datetime import date

from cpbl.db import migrate
from cpbl.ingest.cpbl_wiki import run


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
    args = sys.argv[1:]
    limit = int(args[0]) if args else None
    migrate()
    st = run(year=date.today().year, limit=limit)
    logging.getLogger("cpbl.wiki").info("完成：%s", st)


if __name__ == "__main__":
    main()
