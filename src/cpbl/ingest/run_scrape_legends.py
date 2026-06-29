"""CLI：抓「退役傳奇／現任教練」的生涯分項成績（getapartscore 9999 A/C/E）。

逐場/逐年資料眾多，故名單限縮在兩類最具價值的退役選手：
  1. 現任教練群（2026 coaches）中、可唯一對應且有生涯成績的前球員。
  2. 各項生涯排行榜前十名（與 records 頁同類別：打 HR/H/RBI/SB；投 W/SV/SO）。

只抓生涯分項（year=9999、A/C/E），不抓對戰各隊（官網僅本季 2026，退役者無）。
已在本季登錄名單者由 cpbl-scrape-detail 日常涵蓋，這裡排除以免重複打官網。
冪等 UPSERT，中途中斷可重跑。

    uv run cpbl-scrape-legends            # 全部，delay 1.2s
    uv run cpbl-scrape-legends 2.0        # 指定每請求間隔秒數
"""

from __future__ import annotations

import logging
import sys

from cpbl.db import conn, migrate
from cpbl.ingest.cpbl_player_detail import scrape

log = logging.getLogger("cpbl.legends")

# 生涯分項：A 例行賽 + C 總冠軍 + E 季後挑戰（官網生涯彙總 9999）。不含本季 2026。
LEGEND_COMBOS = [(9999, "A"), (9999, "C"), (9999, "E")]

# 生涯排行榜類別（對齊 records 頁）：每項取前十名。
_BAT_BOARDS = ("hr", "h", "rbi", "sb")
_PIT_BOARDS = ("w", "sv", "so")
_TOP_N = 10


def _targets() -> tuple[list[str], list[str]]:
    """回傳 (batter_ids, pitcher_ids)：退役傳奇/現任教練中曾打擊/曾投球者。

    排除本季登錄者（日常 detail 已涵蓋）。一人可同時在兩份清單（兩刀流）。
    """
    bat_union = " UNION ".join(
        f"(SELECT player_id FROM bat ORDER BY {c} DESC NULLS LAST LIMIT {_TOP_N})" for c in _BAT_BOARDS)
    pit_union = " UNION ".join(
        f"(SELECT player_id FROM pit ORDER BY {c} DESC NULLS LAST LIMIT {_TOP_N})" for c in _PIT_BOARDS)
    sql = f"""
        WITH bat AS (SELECT player_id, sum(hr) hr, sum(h) h, sum(rbi) rbi, sum(sb) sb
                     FROM cpbl.batting_seasons GROUP BY player_id),
             pit AS (SELECT player_id, sum(w) w, sum(sv) sv, sum(so) so
                     FROM cpbl.pitching_seasons GROUP BY player_id),
             -- 現任教練：唯一名字對應 + 有生涯成績（排除未打過職棒的洋教練/同名歧義）
             coach_ids AS (
                 SELECT p.id FROM cpbl.players p
                 WHERE p.name IN (SELECT name FROM cpbl.coaches WHERE year=(SELECT max(year) FROM cpbl.coaches))
                   AND (EXISTS(SELECT 1 FROM cpbl.batting_seasons b WHERE b.player_id=p.id)
                     OR EXISTS(SELECT 1 FROM cpbl.pitching_seasons q WHERE q.player_id=p.id))
                   AND (SELECT count(*) FROM cpbl.players p2 WHERE p2.name=p.name)=1),
             leaders AS ({bat_union} UNION {pit_union}),
             targets AS (SELECT id pid FROM coach_ids UNION SELECT player_id FROM leaders)
        SELECT t.pid,
               EXISTS(SELECT 1 FROM cpbl.batting_seasons b WHERE b.player_id=t.pid) was_bat,
               EXISTS(SELECT 1 FROM cpbl.pitching_seasons q WHERE q.player_id=t.pid) was_pit
        FROM targets t
        WHERE NOT EXISTS(SELECT 1 FROM cpbl.batting_current bc WHERE bc.player_id=t.pid)
          AND NOT EXISTS(SELECT 1 FROM cpbl.pitching_current pc WHERE pc.player_id=t.pid)
        ORDER BY t.pid
    """
    with conn() as c:
        rows = c.execute(sql).fetchall()
    batters = [pid for pid, was_bat, _ in rows if was_bat]
    pitchers = [pid for pid, _, was_pit in rows if was_pit]
    return batters, pitchers


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
    delay = float(sys.argv[1]) if len(sys.argv) >= 2 else 1.2
    migrate()
    batters, pitchers = _targets()
    log.info("退役/教練生涯分項：打者 %d / 投手 %d（去重後不重複球員若干），delay=%.1fs",
             len(batters), len(pitchers), delay)
    out = scrape(delay=delay, apart_combos=LEGEND_COMBOS,
                 batter_ids=batters, pitcher_ids=pitchers, with_vs_team=False)
    log.info("done: %s", out)


if __name__ == "__main__":
    main()
