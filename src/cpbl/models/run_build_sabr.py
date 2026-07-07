"""CLI：重建 sabermetrics 打底表 + Phase A 進階指標（livelog 2018+ 推算 / 官方計數）。

    uv run cpbl-build-sabr                # 全量：守備局數+traits+捕手失分 2018–今年(A)、
                                          # RE 矩陣+run 係數 2018–去年、team DER、wSB
    uv run cpbl-build-sabr 2026 2026      # 只重建指定年份的年度表（RE/係數/DER/wSB 不動）
"""

from __future__ import annotations

import datetime as _dt
import logging
import sys

from cpbl.db import migrate
from cpbl.models.sabr import (
    build_catcher_runs,
    build_fielding_innings,
    build_run_expectancy,
    build_run_values,
    build_team_der,
    build_traits,
    build_wsb,
)

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
            build_catcher_runs(y)
        return
    for y in range(2018, this_year + 1):
        build_fielding_innings(y)
        build_traits(y)
        build_catcher_runs(y)
    build_run_expectancy(2018, this_year - 1)
    build_run_values(2018, this_year - 1)
    build_team_der()
    build_wsb(f"2018-{this_year - 1}")
    # 逐打席勝率打底（run_dist 分布 + WE 邊界 DP；校準驗證印在 log）
    from cpbl.models.winprob import build_run_dist, build_win_expectancy, validate_calibration
    build_run_dist(2018, this_year - 1)
    build_win_expectancy(f"2018-{this_year - 1}")
    validate_calibration(2018, this_year - 1, f"2018-{this_year - 1}")


if __name__ == "__main__":
    main()
