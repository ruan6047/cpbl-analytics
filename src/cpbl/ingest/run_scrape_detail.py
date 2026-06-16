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

import logging
import sys

from cpbl.db import migrate
from cpbl.ingest.cpbl_player_detail import scrape


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
    delay = float(sys.argv[1]) if len(sys.argv) >= 2 else 1.2
    groups = (sys.argv[2],) if len(sys.argv) >= 3 else ("batters", "pitchers")
    migrate()
    out = scrape(delay=delay, groups=groups)
    logging.getLogger("cpbl.detail").info("done: %s", out)


if __name__ == "__main__":
    main()
