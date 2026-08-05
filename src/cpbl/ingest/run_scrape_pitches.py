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

import argparse
import datetime as _dt
import logging

from cpbl.db import migrate
from cpbl.ingest._cli import KIND_CODES, cli_parser
from cpbl.ingest.cpbl_pitch_tracking import pitchers_by_kind, scrape_pitches


def _parser() -> argparse.ArgumentParser:
    p = cli_parser("cpbl-scrape-pitches", __doc__)
    p.add_argument("args", nargs="*", metavar="ARG",
                   help=f"YEAR（4 位數）／KIND（{'|'.join(KIND_CODES)}）／DELAY（秒）；順序無關，皆可省略")
    return p


def _parse_args(argv: list[str], parser: argparse.ArgumentParser | None = None) -> tuple[int, str, float]:
    year = _dt.date.today().year
    kind = "A"
    delay = 1.0
    for a in argv:
        if a.isdigit() and len(a) == 4:
            year = int(a)
        elif a in KIND_CODES:
            kind = a
        else:
            try:
                delay = float(a)
            except ValueError:
                # 舊版在此靜默略過——`--help` 就是這樣被吞掉後直接開爬的（DEV-CLI-HELP-GUARD1）。
                (parser or _parser()).error(
                    f"無法辨識的參數 {a!r}；可用：YEAR（4 位數）／KIND（{'|'.join(KIND_CODES)}）／DELAY（秒）")
    return year, kind, delay


def main() -> None:
    parser = _parser()
    year, kind, delay = _parse_args(parser.parse_args().args, parser)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
    migrate()
    pitchers = pitchers_by_kind(year, kind)  # 所有該 year/kind 出賽投手（A 亦不限現役，比照二軍）
    logging.getLogger("cpbl.pitch").info(
        "回填 %d 位投手逐球（year=%d kind=%s）…", len(pitchers), year, kind)
    out = scrape_pitches(pitchers, year, kind_code=kind, delay=delay)
    logging.getLogger("cpbl.pitch").info("done: %s", out)


if __name__ == "__main__":
    main()
