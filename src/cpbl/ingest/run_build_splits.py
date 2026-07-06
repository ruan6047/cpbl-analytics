"""CLI：重算本季分項（splits + vs各隊）寫回四張官方表，取代本季 apart/vs-team 爬蟲。

    uv run cpbl-build-splits [year] [kinds]     # 預設 今年 A,D

來源：{batting,pitching}_gamelog（T1 場次級）+ game_livelog（T2 打席級）。
生涯（year=9999）分項仍走爬蟲（Phase 2 改 anchor+accrual）。
語意規則與驗證紀錄見 splits_calc docstring 與記憶 splits-recompute-semantics。
"""

from __future__ import annotations

import logging
import sys
from datetime import date

from cpbl.ingest.splits_calc import build_career, build_splits


def main() -> None:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s | %(message)s")
    year = int(sys.argv[1]) if len(sys.argv) > 1 else date.today().year
    kinds = tuple(sys.argv[2].split(",")) if len(sys.argv) > 2 else ("A", "D")
    log = logging.getLogger("cpbl.splits")
    summary = build_splits(year, kinds)
    log.info("build_splits year=%s %s", year, summary)
    career = build_career(year, kinds)   # 生涯 = base + 本季（見 anchor_career）
    log.info("build_career %s", career)


if __name__ == "__main__":
    main()
