"""CLI：建賽果預測特徵表（cpbl.game_features）。

    uv run cpbl-build-features
"""

from __future__ import annotations

import logging

from cpbl.db import migrate
from cpbl.features.outcome import materialize


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
    log = logging.getLogger("cpbl.features")
    migrate()
    n = materialize()
    log.info("game_features materialized: %d rows", n)


if __name__ == "__main__":
    main()
