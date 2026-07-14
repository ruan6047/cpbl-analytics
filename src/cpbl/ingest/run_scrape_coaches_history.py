"""CLI 入口：爬取 TwBsBall 個人經歷節（教練／球員）並入庫 cpbl.person_history。

    uv run cpbl-scrape-coaches-history                     # 教練＋歷任總教練
    uv run cpbl-scrape-coaches-history --scope players     # 現役（登錄名單∪出賽∪近三季）＋各榜前十
    uv run cpbl-scrape-coaches-history --scope all         # 全史球員（暱稱完整覆蓋，指標人物多為退休名將）
"""

from __future__ import annotations

import argparse
import logging

from cpbl.ingest.cpbl_coaches_history import run


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
    log = logging.getLogger("cpbl.scrape_coaches_history")

    parser = argparse.ArgumentParser(description="Scrape coach history from TwBsBall")
    parser.add_argument("--throttle", type=float, default=0.8, help="Throttle delay between API queries")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of coaches to query (for testing)")
    parser.add_argument("--scope", choices=("coaches", "players", "all", "persons", "staff"), default="coaches",
                        help="種子範圍：coaches｜players｜all")
    args = parser.parse_args()

    log.info("Starting TwBsBall coach history scraper...")
    st = run(throttle=args.throttle, limit=args.limit, scope=args.scope)
    log.info("Done. Scraper stats: %s", st)


if __name__ == "__main__":
    main()
