"""CLI：抓昨天/今天比賽需更新的數值，並寫入刷新紀錄、偵測缺漏。

更新內容（皆當季）：
- games：官網逐場賽程/結果（一次抓整年，自然涵蓋昨天/今天的比分與勝敗投）
- 累計數據：投手/打者/守備/團隊（受近期比賽影響的季累計值）
- 增量對戰/分項：只更新「昨天/今天有上場」選手的 matchups / vs-team / splits
  （由 box score 抓當日上場 acnt，省去全名單重爬；off day 或無完成場次則略過）

每次執行於 cpbl.refresh_log 記一列（時間、區間、完成場次、各表更新數）。
若昨天有賽程卻未全部完成，於 note 警示（可能延賽或資料缺漏）。
抓取失敗也會記一列（ok=false）並以非零結束碼退出，避免「無聲缺漏」。

    uv run cpbl-refresh-recent          # 含增量對戰/分項
    uv run cpbl-refresh-recent fast     # 只更新 games+累計，跳過對戰/分項
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import date, timedelta

from cpbl.db import conn, migrate
from cpbl.ingest import cpbl_player_detail
from cpbl.ingest.championships import build_championships
from cpbl.ingest.cpbl_advanced import scrape_advanced
from cpbl.ingest.cpbl_fighting import YEAR_CAREER, scrape_matchups
from cpbl.ingest.cpbl_gamelog import scrape_gamelogs
from cpbl.ingest.cpbl_pitch_tracking import scrape_pitches
from cpbl.ingest.cpbl_site import lineup_acnts, scrape_games
from cpbl.ingest.cpbl_standings import scrape_standings
from cpbl.ingest.cpbl_stats import scrape_all
from cpbl.ingest.cpbl_transactions import scrape_transactions

log = logging.getLogger("cpbl.refresh")


def _completed_snos(year: int, days: list[date]) -> list[int]:
    with conn() as c:
        rows = c.execute(
            "SELECT game_sno FROM cpbl.games WHERE year = %s AND game_date = ANY(%s) "
            "AND home_score + away_score > 0 ORDER BY game_sno",
            (year, days),
        ).fetchall()
    return [r[0] for r in rows]


def _roster_ids(table: str) -> set[str]:
    with conn() as c:
        return {r[0] for r in c.execute(f"SELECT player_id FROM cpbl.{table}").fetchall()}


def _day_opponents(year: int, snos: list[int]) -> dict[str, list[tuple[str, str]]]:
    """{打者 acnt: [(kind_code, 對手隊 team_code), ...]}：當日各打者面對的對手隊。

    供投打對決「當日增量」捷徑用——打者當日對戰的投手全在對手隊，故只需重抓對手隊。
    visiting_home_type：'1'=客隊、'2'=主隊；對手隊即另一側。
    """
    with conn() as c:
        rows = c.execute(
            """
            SELECT b.hitter_acnt, g.kind_code,
                   CASE WHEN b.visiting_home_type = '2'
                        THEN g.away_team_code ELSE g.home_team_code END AS opp
            FROM cpbl.batting_gamelog b
            JOIN cpbl.games g
              ON g.year = b.year AND g.kind_code = b.kind_code AND g.game_sno = b.game_sno
            WHERE b.year = %s AND b.game_sno = ANY(%s)
            """,
            (year, snos),
        ).fetchall()
    out: dict[str, list[tuple[str, str]]] = {}
    for acnt, kind, opp in rows:
        if not acnt or not opp:
            continue
        pair = (kind, opp)
        lst = out.setdefault(acnt, [])
        if pair not in lst:
            lst.append(pair)
    return out


def _incremental_detail(year: int, days: list[date], delay: float = 1.2) -> dict:
    """只更新當日上場且本季登錄選手的 對戰/分項。回傳摘要。"""
    snos = _completed_snos(year, days)
    if not snos:
        return {"skipped": "近兩日無已完成場次"}
    # 賽況（逐局比分 + 逐打席事件）：當日完成場
    gamelog = scrape_gamelogs(year, snos)
    batters_played, pitchers_played = lineup_acnts(year, snos)
    cur_b, cur_p = _roster_ids("batting_current"), _roster_ids("pitching_current")
    rb = sorted(batters_played & cur_b)
    rp = sorted(pitchers_played & cur_p)
    if not rb and not rp:
        return {"completed_games": len(snos), "gamelog": gamelog,
                "lineup_batters": 0, "lineup_pitchers": 0}
    # 對戰：只重抓「當日打者 × 當日對手隊」的生涯對戰即涵蓋所有變動的 (打者,投手) 組合
    # （對手投手全在當日對手隊，故無需掃該打者生涯面對過的所有隊，省 ~15× 請求）。
    day_targets = _day_opponents(year, snos)
    m = scrape_matchups([YEAR_CAREER], delay=delay, batter_ids=rb,
                        pitcher_ids=cur_p, day_targets=day_targets)
    d = cpbl_player_detail.scrape(delay=delay, batter_ids=rb, pitcher_ids=rp)
    # 官方進階：當日上場選手（打者進攻 / 投手被打）
    adv = scrape_advanced(year, [(a, "batting") for a in rb] + [(a, "pitching") for a in rp], delay=delay)
    # 逐球 TrackMan：當日上場投手（自其頁面，當天場次仍在視窗內）
    pitches = scrape_pitches(rp, delay=delay) if rp else {"pitchers": 0, "pitches": 0}
    return {"completed_games": len(snos), "gamelog": gamelog,
            "lineup_batters": len(rb), "lineup_pitchers": len(rp),
            "matchup_rows": m, "advanced": adv, "pitches": pitches, **d}


def _recent_counts(year: int, days: list[date]) -> list[tuple[date, int, int]]:
    """回傳 [(日期, 總場次, 已完成場次)]（含未開打）。"""
    with conn() as c:
        rows = c.execute(
            """
            SELECT game_date, count(*),
                   count(*) FILTER (WHERE home_score + away_score > 0)
            FROM cpbl.games
            WHERE year = %s AND game_date = ANY(%s)
            GROUP BY game_date ORDER BY game_date
            """,
            (year, days),
        ).fetchall()
    return [(d, t, comp) for d, t, comp in rows]


def _log_refresh(scope: str, frm: date, to: date, total: int, completed: int,
                 detail: dict, ok: bool, note: str | None) -> None:
    with conn() as c:
        c.execute(
            """
            INSERT INTO cpbl.refresh_log
                (scope, from_date, to_date, games_total, games_completed, detail, ok, note)
            VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s)
            """,
            (scope, frm, to, total, completed, json.dumps(detail), ok, note),
        )


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
    skip_detail = len(sys.argv) > 1 and sys.argv[1] == "fast"
    today = date.today()
    yesterday = today - timedelta(days=1)
    year = today.year
    migrate()

    try:
        games = scrape_games(year, year)
        stats = scrape_all(year, year, year)
        scrape_standings(year)  # 官方球隊戰績（含和局/勝差/上下半季），輕量每次更新
        trans = scrape_transactions([year])  # 升降一/二軍事件（輕量；供一/二軍選手判定）
        build_championships()  # 由更新後 games 重建年度總冠軍成員（純 SQL、賽季末才會變）
        detail_inc = {} if skip_detail else _incremental_detail(year, [yesterday, today])
    except Exception as e:  # noqa: BLE001 — 失敗也要留痕，避免無聲缺漏
        log.error("抓取失敗：%s", e)
        _log_refresh("recent-games", yesterday, today, 0, 0,
                     {"error": str(e)}, ok=False, note=f"抓取失敗：{e}")
        sys.exit(1)

    recent = _recent_counts(year, [yesterday, today])
    by_date = {d: (t, comp) for d, t, comp in recent}
    y_total, y_done = by_date.get(yesterday, (0, 0))

    # 昨天的比賽理應已打完；若有賽程卻未全完成 → 可能延賽或缺漏
    note = None
    if y_total > 0 and y_done < y_total:
        note = f"昨日({yesterday}) {y_done}/{y_total} 完成，請確認是否延賽或資料缺漏"
        log.warning(note)

    total = sum(t for _, t, _ in recent)
    completed = sum(comp for _, _, comp in recent)
    detail = {
        "games": games, "stats": stats, "transactions": trans, "incremental_detail": detail_inc,
        "recent": [{"date": d.isoformat(), "total": t, "completed": comp} for d, t, comp in recent],
    }
    _log_refresh("recent-games", yesterday, today, total, completed, detail, ok=True, note=note)

    log.info("刷新完成 | 近兩日場次 %s | games=%s stats=%s | 增量對戰/分項=%s",
             {d.isoformat(): f"{comp}/{t}" for d, t, comp in recent}, games, stats, detail_inc)


if __name__ == "__main__":
    main()
