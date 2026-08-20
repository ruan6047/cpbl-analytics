"""CLI：抓昨天/今天比賽需更新的數值，並寫入刷新紀錄、偵測缺漏。

更新內容（皆當季）：
- games：官網逐場賽程/結果（一次抓整年，自然涵蓋昨天/今天的比分與勝敗投）
- 累計數據：投手/打者/守備/團隊（受近期比賽影響的季累計值）
- 增量對戰/分項：只更新「昨天/今天有上場」選手的 matchups / vs-team / splits
  （由 box score 抓當日上場 acnt，省去全名單重爬；off day 或無完成場次則略過）

每次執行於 cpbl.refresh_log 記一列（時間、區間、完成場次、各表更新數）。
若昨天有賽程卻未全部完成，於 note 警示（可能延賽或資料缺漏）。
抓取失敗也會記一列（ok=false）並以非零結束碼退出，避免「無聲缺漏」。

結束碼（DATA-BOX-DEEP-SILENT-FAIL1）：
- 0：完全成功。
- `EXIT_INCOMPLETE_SCRAPE`（69）：**逐場 gamelog 有失敗、其餘步驟照常完成**。
  refresh_log 記 ok=false 並在 note 列出失敗場號；`scripts/scrape-daily.sh` 對這個碼
  仍會執行生產同步（Q3 裁定＝甲-2：擋同步只是把「靜默失敗」換成「生產靜默落後」）。
- 1：硬失敗（含取 token 階段失敗＝整批一場都沒抓），同步不執行。

    uv run cpbl-refresh-recent          # 含增量對戰/分項
    uv run cpbl-refresh-recent fast     # 只更新 games+累計，跳過對戰/分項
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import date, timedelta
from typing import Any

from cpbl.completion import completed_games_sql
from cpbl.config import settings
from cpbl.db import conn, migrate
from cpbl.ingest.championships import build_championships
from cpbl.ingest.cpbl_advanced import AdvancedScrapeResult, scrape_advanced_result
from cpbl.ingest.cpbl_fighting import YEAR_CAREER, scrape_matchups
from cpbl.ingest.cpbl_gamelog import (
    EXIT_INCOMPLETE_SCRAPE,
    reconcile_line,
    scrape_game_details,
    scrape_gamelogs,
)
from cpbl.ingest.cpbl_pitch_tracking import is_frozen, scrape_game_pitches, scrape_pitches
from cpbl.ingest.cpbl_site import lineup_acnts, scrape_games
from cpbl.ingest.cpbl_standings import scrape_standings
from cpbl.ingest.cpbl_stats import scrape_all
from cpbl.ingest.cpbl_transactions import scrape_transactions
from cpbl.ingest.game_source_revisions import record_source_revision
from cpbl.ingest.pa_build import build_scope
from cpbl.ingest.splits_calc import build_career, build_splits

log = logging.getLogger("cpbl.refresh")

# canonical PA build 每日涵蓋範圍（INGEST-PA-DAILY1）：一軍一律嘗試 A/C/E——季後未開打
# 時 C/E 因無完成場自動被 _active_kinds 排除，開打後自動涵蓋，不需改碼（不得寫死 A）。
# 二軍 D 納入：builder 已支援＋歷史已有 1664 筆 published D build＋2026 現況覆蓋率與一軍
# 同等可信（見 INGEST-PA-DAILY1 Log 決策）。F（二軍總冠軍賽）明確不納入：從未被
# build 過（0 published，即使既有 cpbl-build-pa 預設 kind 列表也未含 F）、驗收文字未提及，
# 留待二軍季後接近時另立決策，不在此靜默擴大範圍。
_PA_BUILD_TIER_KINDS: dict[str, tuple[str, ...]] = {
    "major": ("A", "C", "E"),
    "farm": ("D",),
}


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
            f"AND {completed_games_sql()} ORDER BY game_sno",
            (year, kind_code, days),
        ).fetchall()
    return [r[0] for r in rows]


def _lagging_pitch_games(year: int, kind_code: str, days_back: int = 3) -> set[int]:
    """近 days_back 天完成場中，逐球覆蓋 < 85% 的 `game_sno` 集合（**限近期實證有設備的球場**）。

    為什麼要這一步：TrackMan 資料源常延遲 0–2 天發布。refresh 隔天跑時源頭若還沒好，
    當日窗口抓到的該場逐球會缺（Trackman=null 不存），下一輪換新窗口不再回頭
    → 該場永久缺（見 pitch-tracking-venue-coverage）。故每次 refresh 額外回抓近幾日
    覆蓋不足的**場次**，讓延遲發布的逐球在後續 refresh 自癒。單場 API 冪等 UPSERT。

    輸出改為場次維度（原 `_lagging_pitch_pitchers` 輸出投手 acnt）：呼叫端與當日窗口完成場
    **取聯集後單次**送進 `scrape_game_pitches`，故不構成第二條抓取路徑。

    **設備判準為「近期感知」**：`equipped` ＝ 該球場**最近 10 場完成場**中至少一場達
    `pitches >= 50 AND tracked >= pitches * 0.80`（不足 10 場以現有場次計）。
    此判準與兩個常數（10／0.80）是**需求方 2026-08-04 裁定的營運政策**
    （見 docs/tasks/INGEST-GAME-TM-REFACTOR1-G4.md 驗收條件與紅線 4），
    **不是資料推導的結果**，執行者不得自行更動；修訂須另有需求方 event。
    取捨：窗口愈小則死設備退出愈快但單場 downtime 較長的球場會失去自癒；愈大則反之。

    舊判準為「**本季曾**達 0.80」，其前提（設備狀態不隨時間變化）已被實測推翻——
    一個已停止產出的球場會因早季那幾場而永久通過測試、其死場次被每日重抓且永遠補不上。
    """
    with conn() as c:
        rows = c.execute(
            f"""
            WITH cov AS (
              SELECT gm.venue, gm.game_sno, gm.game_date,
                (SELECT count(*) FROM cpbl.game_livelog ll WHERE ll.year=gm.year
                   AND ll.kind_code=gm.kind_code AND ll.game_sno=gm.game_sno
                   AND (ll.is_ball OR ll.is_strike)) AS pitches,
                (SELECT count(*) FROM cpbl.pitch_tracking pt WHERE pt.year=gm.year
                   AND pt.kind_code=gm.kind_code AND pt.game_sno=gm.game_sno) AS tracked
              FROM cpbl.games gm
              WHERE gm.year=%s AND gm.kind_code=%s AND {completed_games_sql()}),
            r AS (SELECT *, row_number() OVER (PARTITION BY venue
                    ORDER BY game_date DESC, game_sno DESC) rn FROM cov),
            equipped AS (
              SELECT venue FROM (
                SELECT venue, bool_or(pitches>=50 AND tracked>=pitches*0.80) AS equipped
                FROM r WHERE rn<=10 GROUP BY venue
              ) e WHERE e.equipped
            )
            SELECT cov.game_sno FROM cov
            JOIN equipped ON equipped.venue = cov.venue
            WHERE cov.game_date >= (CURRENT_DATE - %s::int)
              AND cov.pitches >= 50 AND cov.tracked < cov.pitches * 0.85
            ORDER BY cov.game_sno
            """,
            (year, kind_code, days_back),
        ).fetchall()
    return {r[0] for r in rows}


def _pitchers_of_games(year: int, kind_code: str, snos: list[int]) -> set[str]:
    """指定場次的出賽投手 acnt（`pitching_gamelog`）——供 `pitcher` 回退路徑把場次映射回投手。

    刻意不重寫一套設備／落後判準：唯一的判準在 `_lagging_pitch_games`，這裡只做維度轉換，
    避免兩條路徑對「哪些場需要補抓」有各自的定義而分岔。
    """
    if not snos:
        return set()
    with conn() as c:
        rows = c.execute(
            "SELECT DISTINCT pitcher_acnt FROM cpbl.pitching_gamelog "
            "WHERE year=%s AND kind_code=%s AND game_sno = ANY(%s)",
            (year, kind_code, snos),
        ).fetchall()
    return {r[0] for r in rows}


def _refresh_pitches(year: int, kind_code: str, day_snos: list[int],
                     day_pitchers: list[str], delay: float) -> dict:
    """逐球 TrackMan 抓取的維度分派（`CPBL_PITCH_INGEST`）。

    - `game`（預設）：當日窗完成場 ∪ 落後場，**單次**送進 `scrape_game_pitches`（一場一請求）。
    - `pitcher`（回退）：當日上場投手 ∪ 落後場之出賽投手，送進 `scrape_pitches`（逐投手全季）。

    兩路皆走同一組 lagging 判準與同一 pure parser／冪等 UPSERT，故切換不改變入庫語意，
    只改變請求維度。`settings.pitch_ingest` 於呼叫時讀取（非 import 時），回退才能即時生效。

    **`day_snos` 允許為空**：呼叫端在當日窗無完成場時仍須呼叫本函式，讓落後場自癒在
    賽程空檔繼續運作（F2）；此時目標集合即 lagging 集合，仍是單次送出。
    **凍結例外場一律不進目標集合**（紅線 1），`_upsert` 另有最終過濾形成雙層 fail-closed。
    """
    mode = settings.pitch_ingest
    # 凍結例外（紅線 1）：在目標集合就先排除，凍結場不進入任何一條路徑的抓取清單。
    # `_upsert` 另有最終過濾（fail-closed 雙層），此處只是不浪費請求並讓摘要誠實。
    lagging = {s for s in _lagging_pitch_games(year, kind_code)
               if not is_frozen(year, kind_code, s)}
    if mode == "game":
        snos = sorted({s for s in day_snos if not is_frozen(year, kind_code, s)} | lagging)
        out = (scrape_game_pitches([(year, kind_code, s) for s in snos], delay=delay)
               if snos else {"games": 0, "pitches": 0})
    else:
        acnts = sorted(set(day_pitchers) | _pitchers_of_games(year, kind_code, sorted(lagging)))
        out = (scrape_pitches(acnts, year, kind_code=kind_code, delay=delay)
               if acnts else {"pitchers": 0, "pitches": 0})
    return {**out, "mode": mode, "lagging_games": len(lagging)}


def _missing_gamelog_snos(year: int, kind_code: str = "A") -> list[int]:
    """本季已完成但無 gamelog 的場（延賽補賽/漏跑 → 每日補齊,避免只靠近兩日窗口留 gap）。"""
    with conn() as c:
        rows = c.execute(
            f"""
            SELECT g.game_sno FROM cpbl.games g
            WHERE g.year = %s AND g.kind_code = %s AND {completed_games_sql()}
              AND NOT EXISTS (SELECT 1 FROM cpbl.batting_gamelog b
                              WHERE b.year = g.year AND b.kind_code = g.kind_code AND b.game_sno = g.game_sno)
            ORDER BY g.game_sno
            """,
            (year, kind_code),
        ).fetchall()
    return [r[0] for r in rows]


def _active_kinds(year: int, candidate_kinds: tuple[str, ...]) -> list[str]:
    """candidate_kinds 中，本季已有完成場的子集（依 canonical 完成場判定）。

    季後 C/E 未開打時因無完成場自動被排除（不需改碼）；開打後自動涵蓋——「不得寫死 A」
    的落地方式：候選清單本身固定，但「今天要不要處理它」動態依 DB 現況判定。
    """
    if not candidate_kinds:
        return []
    with conn() as c:
        rows = c.execute(
            f"""
            SELECT DISTINCT kind_code FROM cpbl.games
            WHERE year = %s AND kind_code = ANY(%s) AND {completed_games_sql()}
            """,
            (year, list(candidate_kinds)),
        ).fetchall()
    return sorted(r[0] for r in rows)


def _pa_build_targets(year: int, kinds: list[str], days: list[date]) -> list[tuple[int, str, int]]:
    """本次應嘗試 canonical PA build 的 (year, kind, game_sno) 清單。

    取聯集：
    - 當日窗（``days``，即 [昨天, 今天]）內的完成場，**不論是否已 published**——
      livelog 可能在同一 refresh 內被重抓／修正，須讓 builder 有機會偵測並走既有
      reconciliation（不覆寫已發布 pa_id，見 pa_build 模組契約）。
    - 全域缺口：完成場中尚無 published build 者，不限當日窗——涵蓋補齊缺 gamelog
      等其餘來源造成的延遲完成場（如 build 曾停擺累積的歷史缺口）。
    """
    if not kinds:
        return []
    with conn() as c:
        rows = c.execute(
            f"""
            SELECT g.year, g.kind_code, g.game_sno
            FROM cpbl.games g
            WHERE g.year = %s AND g.kind_code = ANY(%s) AND {completed_games_sql()}
              AND (
                g.game_date = ANY(%s)
                OR NOT EXISTS (
                  SELECT 1 FROM cpbl.game_recap_builds b
                  WHERE b.year = g.year AND b.kind_code = g.kind_code AND b.game_sno = g.game_sno
                    AND b.state = 'published'
                )
              )
            ORDER BY g.kind_code, g.game_sno
            """,
            (year, kinds, days),
        ).fetchall()
    return [(r[0], r[1], r[2]) for r in rows]


def _pa_build_coverage(year: int, kinds: list[str]) -> dict[str, dict[str, int]]:
    """完成場 vs published build 對帳（依 kind_code 分列），供 refresh_log 留痕與示警。"""
    if not kinds:
        return {}
    with conn() as c:
        rows = c.execute(
            f"""
            SELECT g.kind_code, count(*) AS completed,
                   count(*) FILTER (WHERE EXISTS (
                       SELECT 1 FROM cpbl.game_recap_builds b
                       WHERE b.year = g.year AND b.kind_code = g.kind_code AND b.game_sno = g.game_sno
                         AND b.state = 'published')) AS published
            FROM cpbl.games g
            WHERE g.year = %s AND g.kind_code = ANY(%s) AND {completed_games_sql()}
            GROUP BY g.kind_code
            """,
            (year, kinds),
        ).fetchall()
    return {r[0]: {"completed": r[1], "published": r[2], "gap": r[1] - r[2]} for r in rows}


def _build_pa_daily(year: int, days: list[date], *, include_farm: bool) -> dict[str, Any]:
    """對完成場執行 canonical PA build 接線（GAME-RECAP-PA1-BUILD1 的每日鏈；INGEST-PA-DAILY1）。

    只做接線：委派 ``pa_build.build_scope`` 逐場 build，taxonomy/pa_id/reconciliation
    語意完全不動。純 DB 重算不爬網，呼叫方需自行 fail-closed（本函式不吞例外，讓呼叫端
    決定要不要繼續其餘 refresh 步驟）。
    """
    candidates = list(_PA_BUILD_TIER_KINDS["major"])
    if include_farm:
        candidates += list(_PA_BUILD_TIER_KINDS["farm"])
    kinds = _active_kinds(year, tuple(candidates))
    games = _pa_build_targets(year, kinds, days)
    if games:
        # build_scope 的 only_games=[]（空清單，非 None）會被 `if only_games:` 判 falsy，
        # 退化成「全範圍」查詢（陷阱）——games 非空才呼叫，用短路取代空清單保護。
        result = build_scope(year, year, kinds, only_games=games)
    else:
        result = {"games": 0, "actions": {}, "build_states": {}, "errors": []}
    result["kinds"] = kinds
    result["coverage"] = _pa_build_coverage(year, kinds)
    return result


def _pa_build_step(year: int, days: list[date], *, include_farm: bool) -> dict[str, Any]:
    """``_build_pa_daily`` 的 fail-closed 外層：任何例外只記錄、絕不外拋。

    獨立成一個函式（而非直接寫在 ``main()`` 內）方便單獨單元測試 fail-closed 邊界，
    不必連帶 mock 整個 ``main()`` 流程。呼叫端（``main()``）仍照常繼續其餘 refresh 步驟。
    """
    try:
        result = _build_pa_daily(year, days, include_farm=include_farm)
        gap_total = sum(v["gap"] for v in result["coverage"].values())
        if result["errors"] or gap_total:
            log.warning("PA build 完成但仍有缺口／錯誤：%s", result)
        else:
            log.info("PA build 完成，完成場 published 覆蓋恆真：%s", result)
        return result
    except Exception as exc:  # noqa: BLE001 — fail-closed：build 失敗不得擋主流程
        log.error("PA build 失敗（不影響其餘 refresh 步驟）：%s", exc)
        return {"error": str(exc)}


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


_GAMELOG_GAPS: list[dict] = []
"""本次執行中被容忍（`allow_partial=True`）的逐場 gamelog 落差。

單一 CLI 程序內的累積器：`scrape_gamelogs` 的失敗在每日鏈裡不能就地中止（見
`_tolerate_gamelog_gap` 的理由），但也絕不能就地消失——落差累積到這裡，由 `main()`
在所有步驟跑完後轉成 refresh_log 的 ok=false／note 與退出碼 69。
"""


def _tolerate_gamelog_gap(result: dict, why: str) -> dict:
    """登記一次「已容忍的逐場失敗」，回傳原結果不變。

    ⚠️ 呼叫端必須在自己那一行寫 `allow_partial=True` 與理由字串，本函式**不**代為
    放寬任何東西——它只負責讓落差有地方去。少叫一次的後果不是靜默成功而是漏報，
    故三個呼叫點都必須成對出現（`scrape_gamelogs(..., allow_partial=True)` ＋ 本函式）。
    """
    if result.get("failed"):
        log.warning("已容忍的 gamelog 落差（%s）：%s", why, reconcile_line(result))
        _GAMELOG_GAPS.append({"why": why, "reconcile": reconcile_line(result),
                              "kind_code": result.get("kind_code"),
                              "failed": list(result["failed"]),
                              "failures": list(result.get("failures") or [])})
    return result


def _gamelog_gap_note(gaps: list[dict]) -> str | None:
    """落差清單 → refresh_log 的 note 字串（無落差回 None）。純函式，供測試釘住。"""
    if not gaps:
        return None
    parts = [f"{g.get('kind_code')}:{g['failed']}" for g in gaps]
    total = sum(len(g["failed"]) for g in gaps)
    return f"gamelog 逐場失敗 {total} 場（未抓到）：{'；'.join(parts)}"


def _farm_detail(year: int, days: list[date], delay: float = 1.2) -> dict:
    """二軍(D)增量：當日完成二軍場的 賽況(gamelog/box) + 投打對決 + 分項 + 逐球。

    來源限制：**vs-team(對戰各隊) 與 官方進階 無 kindCode**（getfighterscore 只有 defendStation、
    stats.cpbl 進階經 gated proxy），故二軍不含此兩項；其餘皆與一軍同源可抓。
    matchups 走當日對手隊捷徑(kind=D)；splits 走 apart(kindCode=D 本季+生涯)且跳過 vs-team；
    逐球走 `_refresh_pitches`（預設單場 API、與一軍同一條路徑與同一 pure parser）。
    """
    d_snos = _completed_snos(year, days, "D")
    if not d_snos:
        # 當日窗無完成場**仍須跑 lagging 自癒**：TrackMan 發布延遲 0–2 天，賽程空檔
        # （週一休兵、二軍連續無賽）正是延遲最容易卡住的時候——若連 `_refresh_pitches`
        # 一起跳過，前幾日覆蓋不足的場會隨窗口滑出而永久缺（F2，第 1 輪查核 Critical）。
        # 聯集語意不變：day_snos 為空 → 目標＝lagging 集合，仍是單次送出。
        return {"skipped": "近兩日無二軍完成場",
                "pitches": _refresh_pitches(year, "D", [], [], delay)}
    # allow_partial=True 的理由：二軍當日窗抓不到某一場，不該連帶讓後面的分項重算、
    # PA build、逐球自癒與生產同步全部停擺——那是把一場的缺漏放大成整天的缺漏。
    # 落差交給 `_tolerate_gamelog_gap` 累積，main() 以退出碼 69 ＋ refresh_log
    # ok=false 回報（Q3 裁定＝甲-2：看得見，但不擋下游）。
    gamelog = _tolerate_gamelog_gap(
        scrape_gamelogs(year, d_snos, "D", allow_partial=True), "二軍當日窗 gamelog"
    )
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
    # 逐球：當日窗完成場 ∪ 落後場（補 TrackMan 發布延遲自癒），單次送出（同一軍）
    pitches = _refresh_pitches(year, "D", d_snos, rp, delay)
    return {"completed_games": len(d_snos), "gamelog": gamelog,
            "lineup_batters": len(rb), "lineup_pitchers": len(rp),
            "matchup_rows": m, "advanced": adv_result.rows, "pitches": pitches}


def _incremental_detail(year: int, days: list[date], delay: float = 1.2) -> dict:
    """更新當日上場選手的 對戰/分項/逐球（一軍）+ 二軍賽況/逐球。回傳摘要。"""
    farm = _farm_detail(year, days, delay)          # 二軍獨立跑（一軍無場也要更新二軍）
    snos = _completed_snos(year, days, "A")
    if not snos:
        # 同 `_farm_detail`：窗空仍跑 lagging 自癒（F2）。farm 已於上一行獨立處理完畢。
        return {"skipped": "近兩日無一軍完成場",
                "pitches": _refresh_pitches(year, "A", [], [], delay), "farm": farm}
    # 賽況（逐局比分 + 逐打席事件）：當日完成場
    # allow_partial=True 的理由：同 `_farm_detail`——一軍當日窗單場失敗不得中止其餘
    # 增量步驟。落差累積後由 main() 以退出碼 69 回報，不在此就地拋出。
    gamelog = _tolerate_gamelog_gap(
        scrape_gamelogs(year, snos, allow_partial=True), "一軍當日窗 gamelog"
    )
    scrape_game_details(year, snos, "A")  # 觀眾/裁判/時長
    # 當日出賽者全抓，不過濾現役名單（比照二軍 _farm_detail，完整涵蓋；避免當日被下放/
    # 釋出的投手被漏掉。近 14 天實測過濾未漏人，但保守起見取消此潛在漏洞）。
    batters_played, pitchers_played = lineup_acnts(year, snos)
    rb, rp = sorted(batters_played), sorted(pitchers_played)
    if not rb and not rp:
        _record_advanced_revisions(
            year, "A", snos, AdvancedScrapeResult(rows=0, outcome="missing", error_codes=()),
        )
        # 與 F2 同類：名冊抓不到（box score 尚未發布）不該連逐球一起跳過——**場次維度
        # 根本不需要名冊**，snos 已在手上。此處仍送出當日窗 ∪ lagging。
        return {"completed_games": len(snos), "gamelog": gamelog,
                "lineup_batters": 0, "lineup_pitchers": 0,
                "pitches": _refresh_pitches(year, "A", snos, [], delay), "farm": farm}
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
    # 逐球 TrackMan：當日窗完成場 ∪ 近幾日「逐球覆蓋不足」場次（補 TrackMan 發布延遲，自癒）
    pitches = _refresh_pitches(year, "A", snos, rp, delay)
    return {"completed_games": len(snos), "gamelog": gamelog,
            "lineup_batters": len(rb), "lineup_pitchers": len(rp),
            "matchup_rows": m, "advanced": adv_result.rows, "pitches": pitches, "farm": farm}


def _recent_counts(year: int, days: list[date]) -> list[tuple[date, int, int]]:
    """回傳 [(日期, 總場次, 已完成場次)]（含未開打）。"""
    with conn() as c:
        rows = c.execute(
            f"""
            SELECT game_date, count(*),
                   count(*) FILTER (WHERE {completed_games_sql()})
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
    _GAMELOG_GAPS.clear()   # 一次執行一份帳（模組級累積器，同程序內重複呼叫不得互相污染）
    today = date.today()
    yesterday = today - timedelta(days=1)
    year = today.year
    migrate()

    # PA build 失敗必須 fail-closed（不得擋住爬取/同步），故結果初始化在 try 外、
    # 呼叫本身包一層獨立 try/except，例外不外拋。
    pa_build_result: dict[str, Any] = {"games": 0, "actions": {}, "build_states": {}, "errors": []}
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
                # allow_partial=True 的理由：補缺迴圈是「順手收斂歷史缺口」，它抓不到
                # 的場次下次執行仍會被同一支查詢挑出來重試；就地拋出只會讓當天其餘
                # 步驟一起停。⚠️ 這裡原本完全丟棄回傳值——本卡要修的正是它：現在落差
                # 必須經 `_tolerate_gamelog_gap` 進帳，才會出現在退出碼與 refresh_log。
                _tolerate_gamelog_gap(
                    scrape_gamelogs(year, miss, kc, allow_partial=True),
                    f"補齊缺 gamelog 場 kind={kc}",
                )
                scrape_game_details(year, miss, kc)
        # canonical PA build（INGEST-PA-DAILY1）：gamelog 寫入後對當日窗＋全域缺口逐場
        # build，使「完成場皆有 published build」恆成立。fail-closed：build 失敗（含
        # reconciliation_required）只記錄，不擋其餘 refresh 步驟（見 _pa_build_step）。
        pa_build_result = _pa_build_step(year, [yesterday, today], include_farm=True)
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
                     {"error": str(e), "pa_build": pa_build_result}, ok=False, note=f"抓取失敗：{e}")
        sys.exit(1)

    recent = _recent_counts(year, [yesterday, today])
    by_date = {d: (t, comp) for d, t, comp in recent}
    y_total, y_done = by_date.get(yesterday, (0, 0))

    # 昨天的比賽理應已打完；若有賽程卻未全完成 → 可能延賽或缺漏
    note = None
    if y_total > 0 and y_done < y_total:
        note = f"昨日({yesterday}) {y_done}/{y_total} 完成，請確認是否延賽或資料缺漏"
        log.warning(note)

    # 被容忍的逐場 gamelog 落差在這裡結清：refresh_log 的 ok 必須誠實（有沒抓到的場
    # 就不是成功的一次刷新），note 列出失敗場號，退出碼另用 69 讓下游可分辨。
    gap_note = _gamelog_gap_note(_GAMELOG_GAPS)
    if gap_note:
        note = gap_note if note is None else f"{note}；{gap_note}"
        log.error(gap_note)

    total = sum(t for _, t, _ in recent)
    completed = sum(comp for _, _, comp in recent)
    detail = {
        "games": games, "games_farm": games_farm, "stats": stats, "transactions": trans,
        "splits_built": splits_built, "incremental_detail": detail_inc, "pa_build": pa_build_result,
        "gamelog_gaps": _GAMELOG_GAPS,
        "recent": [{"date": d.isoformat(), "total": t, "completed": comp} for d, t, comp in recent],
    }
    _log_refresh("recent-games", yesterday, today, total, completed, detail,
                 ok=not _GAMELOG_GAPS, note=note)

    log.info("刷新完成 | 近兩日場次 %s | games=%s stats=%s | 增量對戰/分項=%s | PA build=%s",
             {d.isoformat(): f"{comp}/{t}" for d, t, comp in recent}, games, stats, detail_inc,
             pa_build_result)

    if _GAMELOG_GAPS:
        # 所有步驟都跑完了才退出：69 的語意是「有逐場失敗但其餘完成」，
        # `scripts/scrape-daily.sh` 據此仍會同步生產。
        sys.exit(EXIT_INCOMPLETE_SCRAPE)


if __name__ == "__main__":
    main()
