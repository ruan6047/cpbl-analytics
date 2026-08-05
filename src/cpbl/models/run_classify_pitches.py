"""CLI：離線推算球種，寫回 pitch_tracking.pitch_type_pred。

    uv run cpbl-classify-pitches               # 本季一軍（A）
    uv run cpbl-classify-pitches 2026 D        # 2026 二軍
    uv run cpbl-classify-pitches 2025 A        # 指定年份

逐投手 GMM（BIC 選 k）+ 規則命名；樣本 < 150 退回 tagged 二元。見 models/pitch_type.py。
需先跑過補收軌跡的爬蟲（cpbl-scrape-pitches）才有 ivb/hb 特徵。純 sklearn，不需 LightGBM/容器。
"""

from __future__ import annotations

import argparse
import datetime as _dt
import logging

from cpbl.db import migrate
from cpbl.ingest._cli import KIND_CODES, cli_parser
from cpbl.models.pitch_type import classify


def _parser() -> argparse.ArgumentParser:
    p = cli_parser("cpbl-classify-pitches", __doc__)
    p.add_argument("args", nargs="*", metavar="ARG",
                   help=f"YEAR（4 位數）／KIND（{'|'.join(KIND_CODES)}）；順序無關，皆可省略")
    return p


def _parse_args(argv: list[str], parser: argparse.ArgumentParser | None = None) -> tuple[int, str]:
    year = _dt.date.today().year
    kind = "A"
    for a in argv:
        if a.isdigit() and len(a) == 4:
            year = int(a)
        elif a in KIND_CODES:
            kind = a
        else:
            # 舊版在此靜默略過——`--help` 就是這樣被吞掉後直接開跑的（DEV-CLI-HELP-GUARD1）。
            (parser or _parser()).error(
                f"無法辨識的參數 {a!r}；可用：YEAR（4 位數）／KIND（{'|'.join(KIND_CODES)}）")
    return year, kind


def main() -> None:
    parser = _parser()
    year, kind = _parse_args(parser.parse_args().args, parser)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
    migrate()
    classify(year, kind)


if __name__ == "__main__":
    main()
