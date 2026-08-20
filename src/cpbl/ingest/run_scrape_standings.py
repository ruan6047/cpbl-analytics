"""CLI：爬官方球隊戰績（含上下半季：和局/勝差/淘汰指數/H2H/主客場/連勝敗/近十場）。

    uv run cpbl-scrape-standings          # 當年（唯一會成功的用法）
    uv run cpbl-scrape-standings 2025     # 指定年 → 預期以對帳失敗告終，見下

⚠️ **`/standings/seasonaction` 忽略 `Year` 參數恆回當季**，所以對它指定舊年份幾乎必定拿到
當季數字。爬蟲會在寫入前以本地 `cpbl.games` 對帳（見 `cpbl_standings.check_year_consistency`），
對不上就**拒寫並以非 0 退出碼結束**——這支 CLI 對非當季年份預期是失敗的，那是正確行為
不是壞掉。

    uv run cpbl-scrape-standings 2025 --history   # 改走 /standings/history（已完賽球季）

⭐ `--history` 走的是 `/standings/history`，該頁**遵守 `Year`**（2026-08-20 實測），是已完賽
球季的正確來源。⚠️ 它**不豁免對帳**：一樣要通過同一道 `cpbl.games` 對帳才寫得進去。
該頁沒有 `elim`／`streak`／`last10` 三欄，一律寫 NULL（需求方裁定：錯值比缺值危險）。

⚠️ `--history` 只接受 `cpbl_standings.HISTORY_SUPPORTED` 內的年份（目前只有 `2025/A`）。
那個限制在**寫入路徑**上，不在這支 CLI 的參數檢查——擋 CLI 擋不住其他呼叫端。理由：
`(g,w,t,l)` 對帳對歷史年份也會通過，攔不住 `team_name`／H2H 身分解析不出來的欄位品質
問題，而 `/api/v1/standings` 又優先採用這張表。
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date

from cpbl.db import migrate
from cpbl.ingest._cli import cli_parser
from cpbl.ingest.cpbl_standings import (
    scrape_history_standings,
    scrape_standings,
    standings_failures,
)


def _parser() -> argparse.ArgumentParser:
    p = cli_parser("cpbl-scrape-standings", __doc__)
    p.add_argument("year", nargs="?", type=int, help="年份（省略＝當年）")
    p.add_argument("--history", action="store_true",
                   help="改走 /standings/history（已完賽球季；該頁遵守 Year）")
    return p


def main() -> None:
    args = _parser().parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
    year = args.year if args.year is not None else date.today().year
    log = logging.getLogger("cpbl.standings")
    migrate()
    out = scrape_history_standings(year) if args.history else scrape_standings(year)
    failures = standings_failures()
    log.info("done %d: %s", year, out)
    if failures:
        # ⚠️ 失敗不外拋（不連坐每日鏈），但**必須看得見**：退出碼是唯一不依賴有人讀 log
        # 的訊號，缺了它就退回成「沒人讀的 warning」。
        log.error("%d 個 SeasonCode 未寫入：%s", len(failures),
                  "；".join(f"sc={f['season_code']} {f['kind']}" for f in failures))
        sys.exit(1)


if __name__ == "__main__":
    main()
