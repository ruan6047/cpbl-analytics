"""CLI：離線推算球種，寫回 pitch_tracking.pitch_type_pred。

    uv run cpbl-classify-pitches               # 本季一軍（A）
    uv run cpbl-classify-pitches 2026 D        # 2026 二軍
    uv run cpbl-classify-pitches 2025 A        # 指定年份

逐投手 GMM（BIC 選 k）+ 規則命名；樣本 < 150 退回 tagged 二元。見 models/pitch_type.py。
需先跑過補收軌跡的爬蟲（cpbl-scrape-pitches）才有 ivb/hb 特徵。純 sklearn，不需 LightGBM/容器。
"""

from __future__ import annotations

import datetime as _dt
import logging
import sys

from cpbl.db import migrate
from cpbl.models.pitch_type import classify


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
    year = _dt.date.today().year
    kind = "A"
    for a in sys.argv[1:]:
        if a.isdigit() and len(a) == 4:
            year = int(a)
        elif a in ("A", "C", "D", "E"):
            kind = a
    migrate()
    classify(year, kind)


if __name__ == "__main__":
    main()
