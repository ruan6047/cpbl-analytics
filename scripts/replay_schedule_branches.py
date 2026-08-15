# LIFECYCLE: oneshot · 卡片一次性產物——不要跑；刪除須需求方裁定（INGEST-GAME-TM-REFACTOR1-G4）
"""Gate 3 條件 3 補證：對歷史賽程回放既有分類邏輯，證明延期/保留賽分支在真實資料上跑過。

唯讀：只打官方 schedule API，不寫任何 DB、不改任何凍結範圍內的邏輯。
只 import 既有函式（parse_schedule_row / classify_schedule / dedupe_latest_per_game）。
"""

import argparse
import collections

from cpbl.ingest.game_tm_shadow import (
    _client,
    classify_schedule,
    dedupe_latest_per_game,
    fetch_schedule_month,
    parse_schedule_row,
)

YEAR = 2026
KIND = "A"
MONTHS = range(3, 9)  # 3~8 月：本季至今

USAGE = """\
replay_schedule_branches.py — 對歷史賽程回放既有分類邏輯（Gate 3 條件 3 補證）

在做什麼
  抓 2026 年 3~8 月的官方賽程，套既有的 parse_schedule_row / classify_schedule /
  dedupe_latest_per_game，印出去重前後的狀態分布，證明延期／保留賽分支在真實資料上跑過。

會寫什麼（⚠️ 沒有 dry-run，也沒有離線模式）
  · **對官方賽程 API 抓六個月**（3~8 月，每月一次請求）——這是它唯一的資料來源，
    沒有快取、沒有 fixture，每跑一次就是六次對外請求
  · 不寫 DB、不落任何檔案；產物只有 stdout

  ⚠️ 爬蟲紅線（CLAUDE.md）：連續冷啟動會讓官網節流升級，症狀會惡化。
     失敗後請先冷卻 15–20 分鐘再單次重試，不要連續重跑。

怎麼呼叫（不接受任何參數，年份與月份是碼內常數）
  uv run python scripts/replay_schedule_branches.py

⚠️ 母卡 INGEST-GAME-TM-REFACTOR1-G4 的 Gate 1-3 已 merge，本檔是凍結的一次性產物。
   除非你正在重現該 Gate 的數字，否則**不要跑它**。
"""


def _parser() -> argparse.ArgumentParser:
    return argparse.ArgumentParser(
        prog="replay_schedule_branches",
        description=USAGE,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )


def main() -> None:
    # ⚠️ argv 必須在任何 I/O 之前解析。改版前本檔完全不看 argv，
    # `--help` 會直接落進下面的 `_client()`，對官方賽程 API 抓滿六個月。
    _parser().parse_args()
    all_rows = []
    with _client() as client:
        for m in MONTHS:
            games = fetch_schedule_month(client, YEAR, KIND, m)
            rows = [r for g in games if (r := parse_schedule_row(g, YEAR))]
            all_rows.extend(rows)
            print(f"  month={m:>2}  raw_games={len(games):>3}  parsed={len(rows):>3}")

    print(f"\n原始列（未去重）共 {len(all_rows)} 筆")

    raw_buckets = classify_schedule(all_rows)
    print("\n[A] 去重前——賽程 feed 曾出現過的狀態分布（證明分支被真實資料觸發）")
    for status, rows in sorted(raw_buckets.items()):
        print(f"  {status:<10} {len(rows):>4}")

    deduped = dedupe_latest_per_game(all_rows)
    dedup_buckets = classify_schedule(deduped)
    print(f"\n[B] 去重後（每場取最新 PreExeDate）共 {len(deduped)} 場——現況判定")
    for status, rows in sorted(dedup_buckets.items()):
        print(f"  {status:<10} {len(rows):>4}")

    # 多態場次：同一 game_sno 有多筆歷史記錄者
    by_sno = collections.defaultdict(list)
    for r in all_rows:
        by_sno[r.game_sno].append(r)
    multi = {sno: rs for sno, rs in by_sno.items() if len(rs) > 1}
    print(f"\n[C] 有多筆歷史記錄的場次共 {len(multi)} 場（延期/保留改期留痕）")
    for sno in sorted(multi)[:15]:
        trail = " → ".join(
            f"{r.game_status}@{(r.pre_exe_date or '')[:10]}"
            for r in sorted(multi[sno], key=lambda r: r.pre_exe_date or "")
        )
        final = classify_schedule(dedupe_latest_per_game(multi[sno]))
        final_status = next(s for s, v in final.items() if v)
        print(f"  {YEAR}-{KIND}-{sno}: {trail}   ⇒ 判定 {final_status}")
    if len(multi) > 15:
        print(f"  …另 {len(multi) - 15} 場略")

    print("\n[D] 條件 3 覆蓋判定")
    for status in ("POSTPONED", "RESERVED", "SCHEDULED"):
        seen = len(raw_buckets.get(status, []))
        print(f"  {status:<10} 真實資料出現 {seen:>3} 次  {'✅' if seen else '❌'}")
    unknown = len(raw_buckets.get("UNKNOWN", []))
    print(f"  UNKNOWN    {unknown:>3} 次  {'（官方新增未知狀態，需查）' if unknown else '（無未知狀態，值域假設成立）'}")


if __name__ == "__main__":
    main()
