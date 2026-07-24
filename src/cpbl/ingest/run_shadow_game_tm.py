"""CLI：INGEST-GAME-TM-REFACTOR1 Gate 3 — shadow harness 觀測週期（每日手動觸發）。

寫入隔離 `cpbl.game_tm_shadow_*` 表，**不動** `cpbl.pitch_tracking`／逐球 refresh 正式路徑。
與正式 `cpbl-scrape-pitches`／`cpbl-refresh-recent` 完全獨立，可安全每天重跑（冪等，不影響
正式資料）。14 天觀測窗滿且無未解差異後，才可另開 Gate 4 cutover 卡。

    uv run cpbl-shadow-game-tm                    # 本季 A，近 3 天窗口，跑一次觀測週期
    uv run cpbl-shadow-game-tm 2026 A 5           # 指定年/kind/窗口天數
    uv run cpbl-shadow-game-tm --report           # 不重跑，只印最近一次 run 摘要+未解差異
"""

from __future__ import annotations

import datetime as _dt
import logging
import sys

from cpbl.db import migrate
from cpbl.ingest.game_tm_shadow import (
    latest_run_report,
    observation_window_days,
    run_shadow_cycle,
)

log = logging.getLogger("cpbl.shadow")


def _parse_args(argv: list[str]) -> tuple[bool, int, str, int]:
    """回傳 (report_only, year, kind, window_days)。"""
    if "--report" in argv:
        return True, 0, "A", 0
    year = _dt.date.today().year
    kind = "A"
    window_days = 3
    nums = [a for a in argv if a not in ("A", "C", "D", "E")]
    for a in argv:
        if a in ("A", "C", "D", "E"):
            kind = a
    if nums:
        if len(nums[0]) == 4:
            year = int(nums[0])
            nums = nums[1:]
    if nums:
        window_days = int(nums[0])
    return False, year, kind, window_days


def _print_report(report: dict | None) -> None:
    if not report:
        print("尚無任何 shadow run。")
        return
    print(f"最近一次 run id={report['run_id']} started_at={report['started_at']} "
          f"ok={report['ok']} note={report['note']}")
    print(f"摘要：{report['summary']}")
    diffs = report["diffs"]
    print(f"未解差異：{len(diffs)} 筆")
    for d in diffs[:30]:
        print(f"  · [{d['diff_type']}] game_sno={d['game_sno']} {d['detail']}")
    days = observation_window_days(report["kind_code"])
    print(f"觀測窗已進行 {days} 天（目標 14 天）")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
    report_only, year, kind, window_days = _parse_args(sys.argv[1:])
    migrate()

    if report_only:
        _print_report(latest_run_report())
        return

    try:
        summary = run_shadow_cycle(year=year, kind_code=kind, window_days=window_days)
    except Exception as e:  # noqa: BLE001 — 已在 run_shadow_cycle 內留痕，這裡只需非零結束碼
        log.error("shadow run 失敗：%s", e)
        sys.exit(1)

    print(f"shadow run id={summary['run_id']} 完成：games_finished={summary['games_finished']} "
          f"games_fetched={summary['games_fetched']} diffs_found={summary['diffs_found']} "
          f"（skipped: postponed={summary['games_skipped_postponed']} "
          f"reserved={summary['games_skipped_reserved']} "
          f"scheduled={summary['games_skipped_scheduled']} "
          f"unknown={summary['games_skipped_unknown_status']}）")
    days = observation_window_days(kind)
    print(f"觀測窗已進行 {days} 天（目標 14 天）")
    if summary["diffs_found"]:
        print("⚠️ 有未解差異，詳見 cpbl.game_tm_shadow_diffs（或 --report）")


if __name__ == "__main__":
    main()
