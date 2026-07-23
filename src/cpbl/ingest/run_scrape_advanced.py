"""CLI：全量抓本季官方進階 leaderboard 並原子晉升 current snapshot。

    uv run cpbl-scrape-advanced                 # 本季 一軍(A) 全量 full snapshot
    uv run cpbl-scrape-advanced 0.8             # 指定每請求間隔秒數
    uv run cpbl-scrape-advanced 0.5 A,D         # 指定軍別

全量 fetch → run manifest 驗證 → 單一 transaction 原子晉升（見 advanced_snapshot）。
daily partial refresh 走 cpbl-refresh-recent（scrape_advanced_result）。污染資料一次性修復
走 cpbl-reconcile-advanced。
"""

from __future__ import annotations

import logging
import sys
from datetime import date

from cpbl.db import migrate
from cpbl.ingest.cpbl_advanced import run_full_snapshot

log = logging.getLogger("cpbl.advanced")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
    delay = float(sys.argv[1]) if len(sys.argv) >= 2 else 0.5
    kinds = sys.argv[2].split(",") if len(sys.argv) >= 3 else ["A"]
    year = date.today().year
    migrate()
    for kind in kinds:
        log.info("full snapshot %s kind=%s …", year, kind)
        for o in run_full_snapshot(year, kind_code=kind, delay=delay):
            log.info("  kind=%s dataset=%s role=%s run=%s promoted=%s accepted=%d%s",
                     o.spec.kind_code, o.spec.dataset, o.spec.role or "-", o.run_id,
                     o.promoted, o.report.accepted_rows,
                     f" error={o.error}" if o.error else "")


if __name__ == "__main__":
    main()
