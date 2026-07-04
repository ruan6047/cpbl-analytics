"""CLI：重建 sabermetrics 打底表（守備局數 + RE 矩陣；livelog 2018+ 推算）。

    uv run cpbl-build-sabr                # 守備局數 2018–今年(A) + RE 矩陣 2018–去年
    uv run cpbl-build-sabr 2026 2026      # 只重建指定年份守備局數（RE 不動）
"""

from __future__ import annotations

import datetime as _dt
import logging
import sys

from cpbl.db import migrate
from cpbl.models.sabr import build_fielding_innings, build_run_expectancy, build_traits

log = logging.getLogger("cpbl.sabr")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
    migrate()
    this_year = _dt.date.today().year
    if len(sys.argv) > 2:
        frm, to = int(sys.argv[1]), int(sys.argv[2])
        for y in range(frm, to + 1):
            build_fielding_innings(y)
            build_traits(y)
        return
    for y in range(2018, this_year + 1):
        build_fielding_innings(y)
        build_traits(y)
    build_run_expectancy(2018, this_year - 1)


if __name__ == "__main__":
    main()
