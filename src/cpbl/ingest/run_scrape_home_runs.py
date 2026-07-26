"""低頻執行 /stats/hr 逐轟 audit ingest（只限本機白天）。"""

from __future__ import annotations

import argparse
import logging

from cpbl.db import migrate
from cpbl.ingest.cpbl_home_runs import KIND_CODES, scrape_home_runs


def main() -> None:
    parser = argparse.ArgumentParser(description="低頻回填官網 /stats/hr 逐轟資料")
    parser.add_argument("start_year", type=int)
    parser.add_argument("end_year", type=int)
    parser.add_argument("--kinds", default="A", help="逗號分隔賽別，預設 A；all=官方全部已知賽別")
    args = parser.parse_args()
    kinds = KIND_CODES if args.kinds.lower() == "all" else tuple(
        code.strip().upper() for code in args.kinds.split(",") if code.strip()
    )
    invalid = set(kinds) - set(KIND_CODES)
    if args.end_year < args.start_year or not kinds or invalid:
        parser.error(f"年份或賽別無效；可用賽別：{','.join(KIND_CODES)}")

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
    migrate()
    totals = scrape_home_runs(args.start_year, args.end_year, kinds)
    logging.getLogger("cpbl.home_runs").info("done: %s", totals)


if __name__ == "__main__":
    main()
