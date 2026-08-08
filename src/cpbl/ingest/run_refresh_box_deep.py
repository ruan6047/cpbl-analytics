"""CLI：深度重抓近 N 天已完成場的 box（DATA-BOX-REVISION-SNAPSHOT1 深度層）。

    uv run cpbl-refresh-box-deep                  # 當年 A、近 30 天已完成場
    uv run cpbl-refresh-box-deep 2026              # 指定年份，賽別預設 A
    uv run cpbl-refresh-box-deep 2026 D            # 指定年份＋賽別
    uv run cpbl-refresh-box-deep 2026 A 14         # 指定天數窗（預設 30）

為什麼要這一支：每日 refresh（`cpbl-refresh-recent`）只重抓 `[昨天, 今天]` 2 天窗
（見 `run_refresh_recent.py::_incremental_detail`），一場比賽的 box 一旦被成功抓過
一次，自動排程不會再回頭重抓它。若官方在賽後 2 天以後才修正 ER（規則 9.01(b)(1)：
聯盟得令記錄員更正），現行每日窗架構下永遠不會被 `cpbl.box_pitching_revisions`
觀測到。本 CLI 每週跑一次，重抓「近 30 天內已完成場」的 box，把「近 N 天內的
修正」收斂進快照——**不改動每日窗的邏輯或範圍**，是完全獨立的路徑，只是重用既有
`scrape_gamelogs()`（本卡 Part 1 已在其中掛入快照寫入，逐投手內容雜湊去重、
不重複匯入不新增列）。

30 天是保守選擇，不是量測結果：目前不知道官方改判的延遲分布（那正是本卡要
累積出來的資料）。累積出第一批 `days_since_game` 分布後，若修正集中在更短窗內，
可以收窄；若發現有落在 30 天外的修正，代表窗開太小，需要加大——這是留給未來
用資料回頭調整的參數，不是這次的定論。

冪等；單一 kind 失敗不影響另一 kind（呼叫方逐 kind 呼叫、自行決定是否繼續）。
不做任何自動重試——單次執行內某場請求失敗只記錄並跳到下一場（既有
`scrape_gamelogs` 行為），不會對同一場連續重試；整支 CLI 若中途失敗直接非零
退出，**不在程式內重跑**，下週排程會用同一個「近 30 天」窗從頭跑一次，任何這週
沒抓到的場次下週會自然涵蓋（窗是相對「今天」算的，不是記錄「上次抓到哪」的
斷點續傳，所以不需要額外的重試/續傳邏輯）。
"""

from __future__ import annotations

import logging
from datetime import date

from cpbl.db import migrate
from cpbl.ingest._cli import KIND_CODES, cli_parser
from cpbl.ingest.cpbl_gamelog import completed_snos_within_days, scrape_gamelogs

log = logging.getLogger("cpbl.gamelog.box_deep")


def _parser():
    p = cli_parser("cpbl-refresh-box-deep", __doc__)
    p.add_argument("year", nargs="?", type=int, default=None, help="年份（省略＝當年）")
    p.add_argument("kind", nargs="?", choices=KIND_CODES, default=None,
                   help="賽別（省略＝A 一軍例行）")
    p.add_argument("days_back", nargs="?", type=int, default=30, help="回看天數（省略＝30）")
    p.add_argument("--delay", type=float, default=1.2,
                   help="每場請求間隔秒數（省略＝1.2；比每日窗的 0.7 更保守——"
                        "深度層單次請求量較大，拉長間隔降低節流風險）")
    return p


def main() -> None:
    args = _parser().parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
    year = args.year if args.year is not None else date.today().year
    kind = args.kind or "A"
    migrate()
    snos = completed_snos_within_days(year, kind, args.days_back)
    log.info("深度重抓 box：year=%s kind=%s days_back=%s → %d 場", year, kind, args.days_back, len(snos))
    out = scrape_gamelogs(year, snos, kind, delay=args.delay)
    log.info("done: %s", out)


if __name__ == "__main__":
    main()
