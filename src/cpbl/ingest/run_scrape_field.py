"""CLI：爬官網 /field 球場規格 enrich venue_dim（一次性 + 手動刷新）。

    uv run cpbl-scrape-field              # 全部可對照球場（~12 頁）
    uv run cpbl-scrape-field 大巨蛋 天母   # 只爬指定球場（小量驗證）
"""

from __future__ import annotations

import logging
import sys

from cpbl.db import migrate
from cpbl.ingest.cpbl_field import scrape


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
    migrate()
    only = sys.argv[1:] or None
    out = scrape(only=only)
    logging.getLogger("cpbl.field").info("完成：%s", out)


if __name__ == "__main__":
    main()
