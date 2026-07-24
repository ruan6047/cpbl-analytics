"""CLI：以「單場 API」為單位抓逐球 TrackMan（INGEST-GAME-TM-REFACTOR1）。

一場一請求打 `/api/proxy/v1/games/{year}-{kind}-{sno}`，解析 LiveLog 逐球並冪等 UPSERT。
與逐投手 logs 版（cpbl-scrape-pitches）共用同一 pure parser 與入庫欄位，可互為冪等來源。

    uv run cpbl-scrape-game-pitches                 # 本季一軍全部已完成場（A）
    uv run cpbl-scrape-game-pitches 2026 D          # 2026 二軍全部已完成場
    uv run cpbl-scrape-game-pitches 2026 A 7        # 一軍近 7 天已完成場（增量）
    uv run cpbl-scrape-game-pitches 2026 A 99 100   # 指定 game_sno（99、100）

kind：A 一軍例行 / C 一軍季後 / D 二軍 / E 二軍季後。

⚠️ 此 CLI 為 Gate 1-2 的單場路徑手動入口；現行每日 refresh 仍走逐投手 logs（唯一正式
writer），本 CLI 不改動該路徑。
"""

from __future__ import annotations

import datetime as _dt
import logging
import sys

from cpbl.db import migrate
from cpbl.ingest.cpbl_pitch_tracking import completed_game_snos, scrape_game_pitches


def _parse_args(argv: list[str]) -> tuple[int, str, list[int], int | None]:
    """回傳 (year, kind, explicit_snos, since_days)。

    第 3 個以後的數字：若只有一個且介於 1..60 視為 since_days（增量窗口）；否則全視為
    明確 game_sno 清單。無數字＝整季全部已完成場。
    """
    year = _dt.date.today().year
    kind = "A"
    nums: list[int] = []
    for a in argv:
        if a in ("A", "C", "D", "E"):
            kind = a
        elif a.isdigit() and len(a) == 4:
            year = int(a)
        elif a.isdigit():
            nums.append(int(a))
    if len(nums) == 1 and 1 <= nums[0] <= 60:
        return year, kind, [], nums[0]
    return year, kind, nums, None


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
    year, kind, snos, since_days = _parse_args(sys.argv[1:])
    migrate()
    log = logging.getLogger("cpbl.pitch")
    if not snos:
        snos = completed_game_snos(year, kind, since_days)
    games = [(year, kind, s) for s in snos]
    log.info("單場逐球：%d 場（year=%d kind=%s%s）…", len(games), year, kind,
             f" 近{since_days}天" if since_days else "")
    out = scrape_game_pitches(games)
    log.info("done: %s", out)


if __name__ == "__main__":
    main()
