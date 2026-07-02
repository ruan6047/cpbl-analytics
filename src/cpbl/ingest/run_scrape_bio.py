"""CLI：爬選手 bio 細項（身高體重/初出場/學歷/出生地/選秀）寫回 players。

用法：
  cpbl-scrape-bio                # 本季登錄選手（現役，快速）
  cpbl-scrape-bio all            # players 全員（一次回填，可續跑）
  cpbl-scrape-bio all --skip-done  # 只補未抓過的（背景續跑）
"""

from __future__ import annotations

import logging
import sys

from cpbl.ingest.cpbl_player_bio import scrape


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s | %(message)s")
    args = sys.argv[1:]
    scope = "all" if "all" in args else "current"
    skip_done = "--skip-done" in args
    scrape(scope=scope, skip_done=skip_done)


if __name__ == "__main__":
    main()
