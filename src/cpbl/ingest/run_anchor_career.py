"""CLI：錨定生涯分項基底（一次性/重錨用）。

    uv run cpbl-anchor-career <season> <backup_csv_dir>

base = 表中官方生涯(9999) − 備份 CSV 的官方本季（Phase 1 覆蓋前 dump）。
兩者出自官方 apart 頁同刻同 transaction → 相減零錯位（滯後互相抵消）。

跨年 roll（下一季開季前執行，純 DB、無需爬）：
    UPDATE base SET 各欄 += 上季終值（主表 year=上季 的重算列），
    之後 build_career 的 season 參數改為新年度。屆時實作 roll 子命令即可；
    或重爬一次全量生涯+本季再重錨（可吸收官方季後修正，較推薦）。
"""

from __future__ import annotations

import argparse
import logging

from cpbl.ingest._cli import cli_parser
from cpbl.ingest.splits_calc import anchor_career


def _parser() -> argparse.ArgumentParser:
    p = cli_parser("cpbl-anchor-career", __doc__)
    p.add_argument("season", type=int, help="錨定基準球季")
    p.add_argument("backup_csv_dir", help="Phase 1 覆蓋前 dump 的官方本季 CSV 目錄")
    return p


def main() -> None:
    args = _parser().parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s | %(message)s")
    season, csv_dir = args.season, args.backup_csv_dir
    summary = anchor_career(season, csv_dir)
    logging.getLogger("cpbl.splits").info("anchor_career season=%s %s", season, summary)


if __name__ == "__main__":
    main()
