"""CLI：回填逐球 TrackMan 追蹤資料（stats.cpbl logs API）。

    uv run cpbl-scrape-pitches                 # 本季一軍全出賽投手（A）
    uv run cpbl-scrape-pitches 2026 D          # 2026 二軍全出賽投手
    uv run cpbl-scrape-pitches 2026 A 1.5      # 指定每請求間隔秒數
    uv run cpbl-scrape-pitches 2025 E          # 二軍季後

kind：A 一軍例行 / C 一軍季後 / D 二軍 / E 二軍季後。一律用該 year/kind 有出賽的
投手（pitching_gamelog）——A 亦不限現役名單（比照二軍，避免下放/釋出者被漏）。
冪等 UPSERT；個別投手失敗略過不中斷。
"""

from __future__ import annotations

import datetime as _dt
import logging
import sys

from cpbl.db import migrate
from cpbl.ingest.cpbl_pitch_tracking import pitchers_by_kind, scrape_pitches


def _parse_args(argv: list[str]) -> tuple[int, str, float]:
    year = _dt.date.today().year
    kind = "A"
    delay = 1.0
    for a in argv:
        if a.isdigit() and len(a) == 4:
            year = int(a)
        elif a in ("A", "C", "D", "E"):
            kind = a
        else:
            try:
                delay = float(a)
            except ValueError:
                pass
    return year, kind, delay


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
    year, kind, delay = _parse_args(sys.argv[1:])
    migrate()
    pitchers = pitchers_by_kind(year, kind)  # 所有該 year/kind 出賽投手（A 亦不限現役，比照二軍）
    logging.getLogger("cpbl.pitch").info(
        "回填 %d 位投手逐球（year=%d kind=%s）…", len(pitchers), year, kind)
    out = scrape_pitches(pitchers, year, kind_code=kind, delay=delay)
    logging.getLogger("cpbl.pitch").info("done: %s", out)


if __name__ == "__main__":
    main()
