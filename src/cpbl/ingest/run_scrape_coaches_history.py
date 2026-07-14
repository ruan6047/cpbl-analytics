"""CLI 入口：爬取 TwBsBall 歷年教練與總教練經歷並入庫。

    uv run cpbl-scrape-coaches-history
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
    args = parser.parse_args()

    log.info("Starting TwBsBall coach history scraper...")
    st = run(throttle=args.throttle, limit=args.limit)
    log.info("Done. Scraper stats: %s", st)


if __name__ == "__main__":
    main()
