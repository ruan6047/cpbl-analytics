"""CLI：回填本季逐球 TrackMan 追蹤資料（自投手頁解析）。

    uv run cpbl-scrape-pitches            # 本季全投手
    uv run cpbl-scrape-pitches 1.5        # 指定每請求間隔秒數

冪等 UPSERT；個別投手失敗略過不中斷。
"""

from __future__ import annotations

import logging
import sys

from cpbl.db import migrate
from cpbl.ingest.cpbl_pitch_tracking import current_pitchers, scrape_pitches


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
    delay = float(sys.argv[1]) if len(sys.argv) >= 2 else 1.0
    migrate()
    pitchers = current_pitchers()
    logging.getLogger("cpbl.pitch").info("回填 %d 位投手的逐球資料 …", len(pitchers))
    out = scrape_pitches(pitchers, delay=delay)
    logging.getLogger("cpbl.pitch").info("done: %s", out)


if __name__ == "__main__":
    main()
