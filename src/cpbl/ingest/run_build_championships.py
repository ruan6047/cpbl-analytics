"""CLI：重建年度總冠軍成員表（不爬蟲，純由已入庫 games/season/gamelog/managers 推導）。

    uv run cpbl-build-championships

冠軍隊源自官網 games(kind_code='C')；每日增量爬蟲（run_refresh_recent）會一併重建。
"""

from __future__ import annotations

import logging

from cpbl.db import migrate
from cpbl.ingest.championships import build_championships


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
    migrate()
    out = build_championships()
    logging.getLogger("cpbl.champ").info("done: %s", out)


if __name__ == "__main__":
    main()
