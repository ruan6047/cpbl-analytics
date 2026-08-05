"""CLI：爬本季登錄選手的「對戰各隊成績」+「分項成績」。

對戰各隊：本季 2026 A 例行賽（官網無生涯/季後）。
分項成績：本季 2026(A) + 生涯 9999(A/C/E)。

    uv run cpbl-scrape-detail               # 全部，delay 1.2s
    uv run cpbl-scrape-detail 2.0           # 指定每請求間隔秒數
    uv run cpbl-scrape-detail 1.2 pitchers  # 只跑投手（續跑）
    uv run cpbl-scrape-detail 1.2 batters   # 只跑打者

冪等 UPSERT，中途中斷可重跑。
"""

from __future__ import annotations

import argparse
import logging

from cpbl.db import migrate
from cpbl.ingest._cli import cli_parser
from cpbl.ingest.cpbl_player_detail import scrape


def _parser() -> argparse.ArgumentParser:
    p = cli_parser("cpbl-scrape-detail", __doc__)
    p.add_argument("delay", nargs="?", type=float, default=1.2, help="每請求間隔秒數（預設 1.2）")
    p.add_argument("group", nargs="?", choices=("batters", "pitchers"),
                   help="只跑打者或投手（省略＝兩者都跑）")
    return p


def main() -> None:
    args = _parser().parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
    delay = args.delay
    groups = (args.group,) if args.group else ("batters", "pitchers")
    migrate()
    out = scrape(delay=delay, groups=groups)
    logging.getLogger("cpbl.detail").info("done: %s", out)


if __name__ == "__main__":
    main()
