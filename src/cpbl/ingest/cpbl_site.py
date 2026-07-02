"""官網 cpbl.com.tw 逐場賽程/結果爬蟲（POST /schedule/getgamedatas）。

官網是 Vue SPA + ASP.NET MVC 自訂 anti-forgery 機制。實測確認的契約：
1. GET /schedule → 取 session cookie + 從 inline JS 抽 header token
   （正規表式 `RequestVerificationToken:\\s*'([^']+)'`；注意：**不是** hidden input 那個）。
2. POST /schedule/getgamedatas，token 放 **HTTP header** RequestVerificationToken，
   body = calendar(YYYY/01/01) + location + kindCode。
3. 回傳 {"Success": true, "GameDatas": "<JSON 字串>"}，GameDatas 需二次 json.loads。

純 HTTP，不需 headless browser（VPS 友善）。冪等 UPSERT。
"""

from __future__ import annotations

import json
import logging
import re
import time
from datetime import date, datetime

import httpx

from cpbl.db import conn

log = logging.getLogger("cpbl.scrape")

BASE = "https://www.cpbl.com.tw"
SCHEDULE_PAGE = f"{BASE}/schedule"
GAMES_ENDPOINT = f"{BASE}/schedule/getgamedatas"
_TOKEN_RE = re.compile(r"RequestVerificationToken:\s*'([^']+)'")

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
KIND_REGULAR = "A"  # 一軍例行賽


def _new_session() -> tuple[httpx.Client, str]:
    """建立帶 cookie 的 session 並取得 header token。"""
    client = httpx.Client(timeout=30.0, headers={"User-Agent": UA}, follow_redirects=True)
    resp = client.get(SCHEDULE_PAGE)
    resp.raise_for_status()
    m = _TOKEN_RE.search(resp.text)
    if not m:
        client.close()
        raise RuntimeError("找不到 RequestVerificationToken（官網結構可能已改版）")
    return client, m.group(1)


def _parse_date(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s).date()
    except ValueError:
        return None


def _i(v) -> int | None:
    try:
        return int(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def fetch_year(year: int, kind_code: str = KIND_REGULAR) -> list[dict]:
    """抓某年某賽別的所有比賽（一次請求回整年）。

    官網主站加了 HiNet 反爬挑戰，改走 Playwright session（見 _browser.py）：
    開 /schedule 過挑戰、抽 token、於頁面 context 內 fetch getgamedatas。
    """
    from cpbl.ingest._browser import session
    s = session()
    m = _TOKEN_RE.search(s.page_html("/schedule"))
    if not m:
        raise RuntimeError("找不到 RequestVerificationToken（官網結構可能已改版）")
    status, text = s.post(
        "/schedule", "/schedule/getgamedatas",
        {"calendar": f"{year}/01/01", "location": "", "kindCode": kind_code},
        headers={"RequestVerificationToken": m.group(1)},
    )
    if status != 200:
        raise RuntimeError(f"getgamedatas HTTP {status}（year={year}, kind={kind_code}；反爬挑戰未過？）")
    payload = json.loads(text)
    if not payload.get("Success"):
        raise RuntimeError(f"getgamedatas 回 Success=false（year={year}, kind={kind_code}）")
    return json.loads(payload["GameDatas"])  # GameDatas 是 JSON 字串


def _primary_entry(entries: list[dict]) -> dict:
    """同 sno 多筆排程 entry 中選主記錄：已開打(PresentStatus=1)優先，再取最新 GameDate。"""
    played = [e for e in entries if _i(e.get("PresentStatus")) == 1]
    pool = played or entries
    return max(pool, key=lambda e: (_parse_date(e.get("GameDate")) or date.min))


def _delay_meta(entries: list[dict]) -> tuple[str | None, date | None]:
    """由同 sno 的排程歷程推導延賽/保留：GameResult 2=保留(已開賽中止) 優先於 1=延賽。
    orig_date：保留取該場開賽日、延賽取最早原定日（可能多次延期）。"""
    def _od(e: dict) -> date | None:
        return _parse_date(e.get("PreExeDate")) or _parse_date(e.get("GameDate"))
    r2 = [d for e in entries if str(e.get("GameResult")) == "2" and (d := _od(e))]
    if r2:
        return "保留", min(r2)
    r1 = [d for e in entries if str(e.get("GameResult")) == "1" and (d := _od(e))]
    if r1:
        return "延賽", min(r1)
    return None, None


def _to_record(g: dict, delay_kind: str | None, orig_date: date | None) -> tuple:
    return (
        _i(g.get("Year")), g.get("KindCode"), g.get("GameSeasonCode"), _i(g.get("GameSno")),
        _parse_date(g.get("GameDate")), _i(g.get("PresentStatus")), g.get("FieldAbbe"),
        g.get("HomeTeamCode"), g.get("HomeTeamName"),
        g.get("VisitingTeamCode"), g.get("VisitingTeamName"),
        _i(g.get("HomeScore")), _i(g.get("VisitingScore")),
        g.get("HomePitcherAcnt") or None, g.get("VisitingPitcherAcnt") or None,
        g.get("WinningPitcherAcnt") or None, g.get("LoserPitcherAcnt") or None,
        g.get("CloserAcnt") or None, g.get("MvpAcnt") or None,
        delay_kind, orig_date,
    )


def upsert_games(games: list[dict]) -> int:
    # 依 PK 聚合同 sno 的多筆排程 entry（延期/保留會回多筆），主記錄取完成場、
    # delay_kind/orig_date 由整段歷程推導。
    groups: dict[tuple, list[dict]] = {}
    for g in games:
        if g.get("GameSno") is None:
            continue
        pk = (_i(g.get("Year")), g.get("KindCode"), g.get("GameSeasonCode"), _i(g.get("GameSno")))
        groups.setdefault(pk, []).append(g)
    records = []
    for entries in groups.values():
        kind, orig = _delay_meta(entries)
        records.append(_to_record(_primary_entry(entries), kind, orig))
    with conn() as c:
        c.cursor().executemany(
            """
            INSERT INTO cpbl.games
                (year, kind_code, game_season_code, game_sno, game_date, present_status, venue,
                 home_team_code, home_team_name, away_team_code, away_team_name,
                 home_score, away_score,
                 home_starter_id, away_starter_id,
                 winning_pitcher_id, losing_pitcher_id, closer_id, mvp_id,
                 delay_kind, orig_date)
            VALUES (%s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (year, kind_code, game_season_code, game_sno) DO UPDATE SET
                game_date=EXCLUDED.game_date, present_status=EXCLUDED.present_status,
                venue=EXCLUDED.venue,
                home_team_code=EXCLUDED.home_team_code, home_team_name=EXCLUDED.home_team_name,
                away_team_code=EXCLUDED.away_team_code, away_team_name=EXCLUDED.away_team_name,
                home_score=EXCLUDED.home_score, away_score=EXCLUDED.away_score,
                home_starter_id=EXCLUDED.home_starter_id, away_starter_id=EXCLUDED.away_starter_id,
                winning_pitcher_id=EXCLUDED.winning_pitcher_id,
                losing_pitcher_id=EXCLUDED.losing_pitcher_id,
                closer_id=EXCLUDED.closer_id, mvp_id=EXCLUDED.mvp_id,
                delay_kind=EXCLUDED.delay_kind, orig_date=EXCLUDED.orig_date
            """,
            records,
        )
    return len(records)


def scrape_games(start_year: int, end_year: int, kind_code: str = KIND_REGULAR) -> dict[int, int]:
    """抓 [start_year, end_year] 各年比賽並 UPSERT。回傳 {year: 場次數}。"""
    totals: dict[int, int] = {}
    for year in range(start_year, end_year + 1):
        games = fetch_year(year, kind_code)
        n = upsert_games(games)
        totals[year] = n
        log.info("year %s kind=%s: %d games", year, kind_code, n)
        time.sleep(1.0)  # 禮貌性間隔
    return totals


BOX_PAGE = f"{BASE}/box"
LIVE_ENDPOINT = f"{BASE}/box/getlive"


def lineup_acnts(
    year: int, snos: list[int], kind_code: str = KIND_REGULAR, delay: float = 0.7,
) -> tuple[set[str], set[str]]:
    """指定場次實際上場的選手 acnt：回傳 (打者集合, 投手集合)。

    走 box/getlive 的 BattingJson(HitterAcnt) / PitchingJson(PitcherAcnt)；
    用於只增量更新「當日有上場」選手的對戰/分項，省去全名單重爬。
    """
    batters: set[str] = set()
    pitchers: set[str] = set()
    if not snos:
        return batters, pitchers
    client = httpx.Client(
        timeout=30.0, follow_redirects=True,
        headers={"User-Agent": UA, "X-Requested-With": "XMLHttpRequest"},
    )

    def _token() -> str:
        html = client.get(BOX_PAGE, params={"year": year, "KindCode": kind_code, "gameSno": 1}).text
        # box 頁 token 在 hidden input；保險起見也試 JS 形式
        m = re.search(r'name="__RequestVerificationToken"[^>]*value="([^"]+)"', html) or _TOKEN_RE.search(html)
        if not m:
            raise RuntimeError("box 頁找不到 RequestVerificationToken（官網可能改版）")
        return m.group(1)

    try:
        token = _token()
        for sno in snos:
            time.sleep(delay)
            try:
                resp = client.post(
                    LIVE_ENDPOINT,
                    data={"GameSno": str(sno), "KindCode": kind_code, "Year": str(year)},
                    headers={"RequestVerificationToken": token},
                )
                if "json" not in resp.headers.get("content-type", ""):
                    token = _token()
                    continue
                payload = resp.json()
            except httpx.HTTPError as e:
                log.warning("getlive 失敗 sno=%s: %s", sno, e)
                continue
            for b in json.loads(payload.get("BattingJson") or "[]"):
                if b.get("HitterAcnt"):
                    batters.add(b["HitterAcnt"])
            for p in json.loads(payload.get("PitchingJson") or "[]"):
                if p.get("PitcherAcnt"):
                    pitchers.add(p["PitcherAcnt"])
    finally:
        client.close()
    return batters, pitchers
