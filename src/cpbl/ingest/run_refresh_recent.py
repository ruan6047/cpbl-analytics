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
from cpbl.ingest.championships import build_championships
from cpbl.ingest.cpbl_advanced import AdvancedScrapeResult, scrape_advanced_result
from cpbl.ingest.cpbl_fighting import YEAR_CAREER, scrape_matchups
from cpbl.ingest.cpbl_gamelog import scrape_game_details, scrape_gamelogs
from cpbl.ingest.cpbl_pitch_tracking import scrape_pitches
from cpbl.ingest.cpbl_site import lineup_acnts, scrape_games
from cpbl.ingest.cpbl_standings import scrape_standings
from cpbl.ingest.cpbl_stats import scrape_all
from cpbl.ingest.cpbl_transactions import scrape_transactions
from cpbl.ingest.game_source_revisions import record_source_revision
from cpbl.ingest.splits_calc import build_career, build_splits

log = logging.getLogger("cpbl.refresh")


def _record_advanced_revisions(
    year: int,
    kind_code: str,
    snos: list[int],
    result: AdvancedScrapeResult,
) -> None:
    """把 season-player aggregate 的取得證據掛到相關場次，但明示非 game-level 完成訊號。"""
    payload = {
        "scope": "season_player_aggregate",
        "rows": result.rows,
        "outcome": result.outcome,
        "error_codes": result.error_codes,
    }
    for sno in snos:
        record_source_revision(
            year=year,
            kind_code=kind_code,
            game_sno=sno,
            source="advanced",
            outcome=result.outcome,
            row_count=result.rows,
            payload=payload,
            error_code=",".join(result.error_codes) or None,
            detail={
                "scope": "season_player_aggregate",
                "game_level_complete": False,
                "error_codes": list(result.error_codes),
            },
        )


def _completed_snos(year: int, days: list[date], kind_code: str = "A") -> list[int]:
    # 一/二軍 game_sno 為各自序列，必須依 kind 過濾（否則 D 的 sno 會混入 A 流程重爬錯場）
    with conn() as c:
        rows = c.execute(
            "SELECT game_sno FROM cpbl.games WHERE year = %s AND kind_code = %s AND game_date = ANY(%s) "
            "AND home_score + away_score > 0 ORDER BY game_sno",
            (year, kind_code, days),
        ).fetchall()
    return [r[0] for r in rows]


def _lagging_pitch_pitchers(year: int, kind_code: str, days_back: int = 3) -> set[str]:
    """近 days_back 天完成場中，逐球覆蓋 < 85% 者的所有投手 acnt（**不限現役**）。

    為什麼要這一步：TrackMan 資料源常延遲 0–2 天發布。refresh 隔天跑時源頭若還沒好，
    當日窗口的 scrape_pitches 會抓到投手但 Trackman=null（不存），下一輪換新窗口不再回頭
    → 該場永久缺（見 pitch-tracking-venue-coverage）。故每次 refresh 額外回抓近幾日
    覆蓋不足場次的投手，讓延遲發布的逐球在後續 refresh 自癒。逐投手全季一次抓故冪等。

    **只限「本季實證有設備」的球場**（某場曾達 80% 覆蓋）——否則會每輪重爬二軍多數
    無設備球場、大巨蛋等源頭本就無資料的場，永遠補不上白費請求。設備場的零覆蓋場
    （大巨蛋設備當日沒錄）最多多打幾天隨窗口滑出，可接受。
    """
    with conn() as c:
        rows = c.execute(
            """
            WITH cov AS (
              SELECT gm.game_sno, gm.venue, gm.game_date,
                (SELECT count(*) FROM cpbl.game_livelog ll
                   WHERE ll.year=gm.year AND ll.kind_code=gm.kind_code AND ll.game_sno=gm.game_sno
                     AND (ll.is_ball OR ll.is_strike)) AS pitches,
                (SELECT count(*) FROM cpbl.pitch_tracking pt
                   WHERE pt.year=gm.year AND pt.kind_code=gm.kind_code AND pt.game_sno=gm.game_sno) AS tracked
              FROM cpbl.games gm
              WHERE gm.year=%s AND gm.kind_code=%s AND gm.home_score + gm.away_score > 0
            ), equipped AS (  -- 本季曾達 0.80 覆蓋率的球場＝有設備
              SELECT DISTINCT venue FROM cov WHERE pitches >= 50 AND tracked >= pitches * 0.80
            )
            SELECT DISTINCT p.pitcher_acnt FROM cpbl.pitching_gamelog p
            JOIN cov ON cov.game_sno = p.game_sno
            WHERE p.year=%s AND p.kind_code=%s
              AND cov.game_date >= (CURRENT_DATE - %s::int)
              AND cov.venue IN (SELECT venue FROM equipped)
              AND cov.pitches >= 50 AND cov.tracked < cov.pitches * 0.85
            """,
            (year, kind_code, year, kind_code, days_back),
        ).fetchall()
    return {r[0] for r in rows}


def _missing_gamelog_snos(year: int, kind_code: str = "A") -> list[int]:
    """本季已完成但無 gamelog 的場（延賽補賽/漏跑 → 每日補齊,避免只靠近兩日窗口留 gap）。"""
    with conn() as c:
        rows = c.execute(
            """
            SELECT g.game_sno FROM cpbl.games g
            WHERE g.year = %s AND g.kind_code = %s AND g.home_score + g.away_score > 0
              AND NOT EXISTS (SELECT 1 FROM cpbl.batting_gamelog b
                              WHERE b.year = g.year AND b.kind_code = g.kind_code AND b.game_sno = g.game_sno)
            ORDER BY g.game_sno
            """,
            (year, kind_code),
        ).fetchall()
    return [r[0] for r in rows]


def _sync_player_names() -> int:
    """以「最近一場逐場登錄名」更新 players.name（處理球員改名，如 象魔力→魔力藍）。
    gamelog 名為官方當場登錄名、最乾淨；current 表名帶 #/◎/* roster 標記故不用。
    純 SQL、用已爬資料，改名隔日自動修正。回傳更新列數。"""
    with conn() as c:
        cur = c.execute(
            """
            WITH gl AS (
              SELECT hitter_acnt acnt, hitter_name nm, year, game_sno FROM cpbl.batting_gamelog
              UNION ALL SELECT pitcher_acnt, pitcher_name, year, game_sno FROM cpbl.pitching_gamelog
            ),
            latest AS (
              SELECT DISTINCT ON (acnt) acnt, regexp_replace(nm, '^[*＊#＃◎●○◇]+', '') AS nm
              FROM gl WHERE nm IS NOT NULL ORDER BY acnt, year DESC, game_sno DESC
            )
            UPDATE cpbl.players p SET name = l.nm
            FROM latest l WHERE p.id = l.acnt AND p.name <> l.nm AND l.nm <> ''
            """
        )
        return cur.rowcount


def _day_opponents(year: int, snos: list[int], kind_code: str = "A") -> dict[str, list[tuple[str, str]]]:
    """{打者 acnt: [(kind_code, 對手隊 team_code), ...]}：當日各打者面對的對手隊。

    供投打對決「當日增量」捷徑用——打者當日對戰的投手全在對手隊，故只需重抓對手隊。
    visiting_home_type：'1'=客隊、'2'=主隊；對手隊即另一側。
    一/二軍 game_sno 序列不同，需依 kind_code 過濾（否則同號的另一軍場會誤配）。
    """
    with conn() as c:
        rows = c.execute(
            """
            SELECT b.hitter_acnt, b.kind_code,
                   CASE WHEN b.visiting_home_type = '2'
                        THEN g.away_team_code ELSE g.home_team_code END AS opp
            FROM cpbl.batting_gamelog b
            JOIN cpbl.games g
              ON g.year = b.year AND g.kind_code = b.kind_code AND g.game_sno = b.game_sno
            WHERE b.year = %s AND b.kind_code = %s AND b.game_sno = ANY(%s)
            """,
            (year, kind_code, snos),
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


def _farm_detail(year: int, days: list[date], delay: float = 1.2) -> dict:
    """二軍(D)增量：當日完成二軍場的 賽況(gamelog/box) + 投打對決 + 分項 + 逐球。

    來源限制：**vs-team(對戰各隊) 與 官方進階 無 kindCode**（getfighterscore 只有 defendStation、
    stats.cpbl 進階經 gated proxy），故二軍不含此兩項；其餘皆與一軍同源可抓。
    matchups 走當日對手隊捷徑(kind=D)；splits 走 apart(kindCode=D 本季+生涯)且跳過 vs-team；
    逐球以當日上場二軍投手抓其頁面（逐球自帶 kindCode，涵蓋該場二軍打者面對）。
    """
    d_snos = _completed_snos(year, days, "D")
    if not d_snos:
        return {"skipped": "近兩日無二軍完成場"}
    gamelog = scrape_gamelogs(year, d_snos, "D")
    scrape_game_details(year, d_snos, "D")  # 觀眾/裁判/時長
    batters, pitchers = lineup_acnts(year, d_snos, "D")
    rb, rp = sorted(batters), sorted(pitchers)
    # 二軍投打對決（當日對手隊, kind=D；不過濾投手＝完整涵蓋二軍對戰）
    targets = _day_opponents(year, d_snos, "D")
    m = scrape_matchups([YEAR_CAREER], delay=delay, batter_ids=rb, day_targets=targets) if rb else 0
    # 二軍分項（本季+生涯）已全改重算（build_splits + build_career），apart 停爬
    # 二軍官方進階（leaderboard JSON API，gameKind=D；bulk 一次全抓再濾當日出賽者）
    adv_result = (
        scrape_advanced_result(
            year,
            [(a, "batting") for a in rb] + [(a, "pitching") for a in rp],
            kind_code="D",
        )
        if (rb or rp)
        else AdvancedScrapeResult(rows=0, outcome="missing", error_codes=())
    )
    _record_advanced_revisions(year, "D", d_snos, adv_result)
    rp_pitch = sorted(set(rp) | _lagging_pitch_pitchers(year, "D"))  # 補 TrackMan 發布延遲（同一軍）
    pitches = scrape_pitches(rp_pitch, year, kind_code="D", delay=delay) if rp_pitch else {"pitchers": 0, "pitches": 0}
    return {"completed_games": len(d_snos), "gamelog": gamelog,
            "lineup_batters": len(rb), "lineup_pitchers": len(rp),
            "matchup_rows": m, "advanced": adv_result.rows, "pitches": pitches}


def _incremental_detail(year: int, days: list[date], delay: float = 1.2) -> dict:
    """更新當日上場選手的 對戰/分項/逐球（一軍）+ 二軍賽況/逐球。回傳摘要。"""
    farm = _farm_detail(year, days, delay)          # 二軍獨立跑（一軍無場也要更新二軍）
    snos = _completed_snos(year, days, "A")
    if not snos:
        return {"skipped": "近兩日無一軍完成場", "farm": farm}
    # 賽況（逐局比分 + 逐打席事件）：當日完成場
    gamelog = scrape_gamelogs(year, snos)
    scrape_game_details(year, snos, "A")  # 觀眾/裁判/時長
    # 當日出賽者全抓，不過濾現役名單（比照二軍 _farm_detail，完整涵蓋；避免當日被下放/
    # 釋出的投手被漏掉。近 14 天實測過濾未漏人，但保守起見取消此潛在漏洞）。
    batters_played, pitchers_played = lineup_acnts(year, snos)
    rb, rp = sorted(batters_played), sorted(pitchers_played)
    if not rb and not rp:
        _record_advanced_revisions(
            year, "A", snos, AdvancedScrapeResult(rows=0, outcome="missing", error_codes=()),
        )
        return {"completed_games": len(snos), "gamelog": gamelog,
                "lineup_batters": 0, "lineup_pitchers": 0, "farm": farm}
    # 對戰：只重抓「當日打者 × 當日對手隊」的生涯對戰即涵蓋所有變動的 (打者,投手) 組合
    # （對手投手全在當日對手隊，故無需掃該打者生涯面對過的所有隊，省 ~15× 請求）。
    # 不帶 pitcher_ids＝不濾對戰投手層級（比照二軍，完整保留對戰史）。
    day_targets = _day_opponents(year, snos)
    m = scrape_matchups([YEAR_CAREER], delay=delay, batter_ids=rb, day_targets=day_targets)
    # 分項（本季+生涯）與 vs-team 已全改重算：本季=build_splits、生涯=base+本季
    # （build_career，錨定見 anchor_career）。apart 爬蟲全停；季後賽 C/E 開打時
    # 把 C/E 加進 build_splits kinds 即自動累加（gamelog/livelog 照爬）。
    # 官方進階：當日上場選手（打者進攻 / 投手被打）
    adv_result = scrape_advanced_result(
        year,
        [(a, "batting") for a in rb] + [(a, "pitching") for a in rp],
        delay=delay,
    )
    _record_advanced_revisions(year, "A", snos, adv_result)
    # 逐球 TrackMan：當日上場投手 ∪ 近幾日「逐球覆蓋不足」場次投手（補 TrackMan 發布延遲，自癒）
    rp_pitch = sorted(set(rp) | _lagging_pitch_pitchers(year, "A"))
    pitches = scrape_pitches(rp_pitch, year, delay=delay) if rp_pitch else {"pitchers": 0, "pitches": 0}
    return {"completed_games": len(snos), "gamelog": gamelog,
            "lineup_batters": len(rb), "lineup_pitchers": len(rp),
            "matchup_rows": m, "advanced": adv_result.rows, "pitches": pitches, "farm": farm}


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
        games = scrape_games(year, year)              # 一軍例行賽賽程/結果
        games_farm = scrape_games(year, year, "D")    # 二軍賽程/結果（供二軍成績卡/逐球/戰績）
        stats = scrape_all(year, year, year)          # 投打/團隊 + 守備一軍(A)+二軍(D)
        scrape_standings(year)  # 官方球隊戰績（含和局/勝差/上下半季），輕量每次更新
        trans = scrape_transactions([year])  # 升降一/二軍事件（輕量；供一/二軍選手判定）
        build_championships()  # 由更新後 games 重建年度總冠軍成員（純 SQL、賽季末才會變）
        detail_inc = {} if skip_detail else _incremental_detail(year, [yesterday, today])
        # 補齊任何完成卻無 gamelog 的場（延賽補賽/漏跑）；本季 gap 通常少，故廉價
        for kc in ("A", "D"):
            miss = _missing_gamelog_snos(year, kc)
            if miss:
                log.info("補齊缺 gamelog 場 kind=%s：%s", kc, miss)
                scrape_gamelogs(year, miss, kc)
                scrape_game_details(year, miss, kc)
        # 分項＋vs各隊全面重算寫回：本季=gamelog/livelog 重算、生涯=base+本季
        # （apart/vs-team 爬蟲全停，見 splits_calc / anchor_career）
        splits_built = build_splits(year, ("A", "D"))
        splits_built["career"] = build_career(year, ("A", "D"))
        log.info("重算分項寫回：%s", splits_built)
        renamed = _sync_player_names()  # 由最新 gamelog 名同步 players.name（改名自動修正）
        if renamed:
            log.info("更新 %d 位球員登錄名（改名同步）", renamed)
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
        "games": games, "games_farm": games_farm, "stats": stats, "transactions": trans,
        "splits_built": splits_built, "incremental_detail": detail_inc,
        "recent": [{"date": d.isoformat(), "total": t, "completed": comp} for d, t, comp in recent],
    }
    _log_refresh("recent-games", yesterday, today, total, completed, detail, ok=True, note=note)

    log.info("刷新完成 | 近兩日場次 %s | games=%s stats=%s | 增量對戰/分項=%s",
             {d.isoformat(): f"{comp}/{t}" for d, t, comp in recent}, games, stats, detail_inc)


if __name__ == "__main__":
    main()
