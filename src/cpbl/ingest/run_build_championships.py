"""CLI：重建年度總冠軍成員表（不爬蟲，純由已入庫資料重建）。

    uv run cpbl-build-championships

冠軍隊源自逐年可追溯的 championships canonical dataset；球員／總教練由
season/gamelog/managers 補齊。每日增量爬蟲（run_refresh_recent）會一併重建。
"""

from __future__ import annotations

import argparse
import logging

from cpbl.db import migrate
from cpbl.ingest._cli import cli_parser
from cpbl.ingest.championships import build_championships


def _parser() -> argparse.ArgumentParser:
    return cli_parser("cpbl-build-championships", __doc__)


def main() -> None:
    _parser().parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
    migrate()
    out = build_championships()
    logging.getLogger("cpbl.champ").info("done: %s", out)


if __name__ == "__main__":
    main()
