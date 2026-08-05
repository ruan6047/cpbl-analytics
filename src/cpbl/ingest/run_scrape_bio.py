"""CLI：爬選手 bio 細項（身高體重/初出場/學歷/出生地/選秀）寫回 players。

用法：
  cpbl-scrape-bio                # 本季登錄選手（現役，快速）
  cpbl-scrape-bio all            # players 全員（一次回填，可續跑）
  cpbl-scrape-bio all --skip-done  # 只補未抓過的（背景續跑）
"""

from __future__ import annotations

import argparse
import logging

from cpbl.ingest._cli import cli_parser
from cpbl.ingest.cpbl_player_bio import scrape


def _parser() -> argparse.ArgumentParser:
    p = cli_parser("cpbl-scrape-bio", __doc__)
    p.add_argument("scope", nargs="?", choices=("current", "all"), default="current",
                   help="current＝本季登錄選手（預設）；all＝players 全員")
    p.add_argument("--skip-done", action="store_true", help="只補未抓過的（背景續跑）")
    return p


def main() -> None:
    args = _parser().parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s | %(message)s")
    scrape(scope=args.scope, skip_done=args.skip_done)


if __name__ == "__main__":
    main()
