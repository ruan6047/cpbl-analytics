"""CLI：重建 sabermetrics 打底表 + Phase A 進階指標（livelog 2018+ 推算 / 官方計數）。

    uv run cpbl-build-sabr                # 全量：守備局數+traits+捕手失分 2018–今年(A)、
                                          # RE 矩陣+run 係數 2018–去年、team DER、wSB
    uv run cpbl-build-sabr 2026 2026      # 只重建指定年份的年度表（RE/係數/DER/wSB 不動）
"""

from __future__ import annotations

import argparse
import datetime as _dt
import logging

from cpbl.db import migrate
from cpbl.ingest._cli import cli_parser
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


def _parser() -> argparse.ArgumentParser:
    p = cli_parser("cpbl-build-sabr", __doc__)
    p.add_argument("from_year", nargs="?", type=int,
                   help="起始年（須與 to_year 成對給定；兩者都省略＝全量重建）")
    p.add_argument("to_year", nargs="?", type=int, help="結束年（含）")
    return p


def main() -> None:
    parser = _parser()
    args = parser.parse_args()
    # 舊版的判斷是 `len(sys.argv) > 2`：只給**一個**年份會被靜默忽略，落回全量重建——
    # 而全量重建除了該年的年度表，還會連 RE 矩陣／run 係數／team DER／wSB／勝率矩陣
    # 一起重算，遠重於使用者要求的事。docs/research/DATA-RULES-AUDIT1_REPORT.md 正是
    # 以 `cpbl-build-sabr <YEAR>` 單年形式記載，兩邊對不上。寧可炸掉也不要靜默做別的事。
    if (args.from_year is None) != (args.to_year is None):
        parser.error("from_year 與 to_year 必須成對給定（如 `cpbl-build-sabr 2026 2026`）；"
                     "只給一個年份在舊版會靜默改跑全量重建，語意不明故不再接受")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
    migrate()
    this_year = _dt.date.today().year
    if args.from_year is not None and args.to_year is not None:
        frm, to = args.from_year, args.to_year
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
