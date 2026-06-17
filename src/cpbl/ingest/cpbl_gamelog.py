"""每場賽況爬蟲：box/getlive 的 ScoreboardJson（逐局比分）+ LiveLogJson（逐打席事件）。

一個 token 可重用於多場 getlive。冪等 UPSERT；偶發非 JSON 回應時重取 token。
"""

from __future__ import annotations

import json
import logging
import re
import time

import httpx

from cpbl.db import conn
from cpbl.ingest.cpbl_site import BASE, KIND_REGULAR, UA

log = logging.getLogger("cpbl.gamelog")

BOX_PAGE = f"{BASE}/box"
LIVE_ENDPOINT = f"{BASE}/box/getlive"
_HIDDEN_RE = re.compile(r'name="__RequestVerificationToken"[^>]*value="([^"]+)"')


def _i(v) -> int | None:
    try:
        return int(float(v)) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _b(v) -> bool | None:
    if v in (None, ""):
        return None
    return str(v) in ("1", "true", "True", "Y")


def _scoreboard_rows(year: int, kind: str, sno: int, data: list[dict]) -> list[tuple]:
    return [
        (year, kind, sno, r.get("TeamNo"), _i(r.get("InningSeq")), r.get("VisitingHomeType"),
         r.get("TeamName"), _i(r.get("ScoreCnt")), _i(r.get("HittingCnt")), _i(r.get("ErrorCnt")))
        for r in data if r.get("TeamNo") and r.get("InningSeq") is not None
    ]


def _livelog_rows(year: int, kind: str, sno: int, data: list[dict]) -> list[tuple]:
    out = []
    for r in data:
        if not r.get("MainEventNo"):
            continue
        out.append((
            year, kind, sno, r.get("MainEventNo"), _i(r.get("InningSeq")), r.get("VisitingHomeType"),
            _i(r.get("BattingOrder")), _i(r.get("OutCnt")), _i(r.get("BallCnt")), _i(r.get("StrikeCnt")),
            _i(r.get("PitchCnt")), r.get("Content"), r.get("ActionName"), r.get("BattingActionName"),
            r.get("DefendStationCode"), r.get("HitterAcnt"), r.get("HitterName"),
            r.get("PitcherAcnt"), r.get("PitcherName"), r.get("CatcherAcnt"), r.get("CatcherName"),
            r.get("FirstBase") or None, r.get("SecondBase") or None, r.get("ThirdBase") or None,
            _b(r.get("IsStrike")), _b(r.get("IsBall")), _b(r.get("IsScoreCnt")),
            _b(r.get("IsChangePlayer")), _b(r.get("IsSpecialEvent")),
            _i(r.get("VisitingScore")), _i(r.get("HomeScore")),
        ))
    return out


_SB_COLS = ("year,kind_code,game_sno,team_no,inning_seq,visiting_home_type,team_name,"
            "score_cnt,hitting_cnt,error_cnt")
_LL_COLS = ("year,kind_code,game_sno,main_event_no,inning_seq,visiting_home_type,batting_order,"
            "out_cnt,ball_cnt,strike_cnt,pitch_cnt,content,action_name,batting_action_name,"
            "defend_station_code,hitter_acnt,hitter_name,pitcher_acnt,pitcher_name,catcher_acnt,"
            "catcher_name,first_base,second_base,third_base,is_strike,is_ball,is_score,"
            "is_change_player,is_special_event,visiting_score,home_score")


def _upsert(table: str, cols: str, n_pk: int, records: list[tuple]) -> int:
    if not records:
        return 0
    col_list = [c.strip() for c in cols.split(",")]
    ph = "(" + ",".join(["%s"] * len(col_list)) + ")"
    updates = ", ".join(f"{c}=EXCLUDED.{c}" for c in col_list[n_pk:])
    pk = ", ".join(col_list[:n_pk])
    with conn() as c:
        c.cursor().executemany(
            f"INSERT INTO cpbl.{table} ({cols}) VALUES {ph} "
            f"ON CONFLICT ({pk}) DO UPDATE SET {updates}",
            records,
        )
    return len(records)


def scrape_gamelogs(year: int, snos: list[int], kind_code: str = KIND_REGULAR,
                    delay: float = 0.7) -> dict:
    """抓指定場次的賽況並 UPSERT。回傳 {games, scoreboard, livelog}。"""
    out = {"games": 0, "scoreboard": 0, "livelog": 0}
    if not snos:
        return out
    client = httpx.Client(
        timeout=30.0, follow_redirects=True,
        headers={"User-Agent": UA, "X-Requested-With": "XMLHttpRequest"},
    )

    def _token() -> str:
        html = client.get(BOX_PAGE, params={"year": year, "KindCode": kind_code, "gameSno": 1}).text
        m = _HIDDEN_RE.search(html)
        if not m:
            raise RuntimeError("box 頁找不到 token（官網可能改版）")
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
            sb = json.loads(payload.get("ScoreboardJson") or "[]")
            ll = json.loads(payload.get("LiveLogJson") or "[]")
            out["scoreboard"] += _upsert("game_scoreboard", _SB_COLS, 5,
                                         _scoreboard_rows(year, kind_code, sno, sb))
            out["livelog"] += _upsert("game_livelog", _LL_COLS, 4,
                                      _livelog_rows(year, kind_code, sno, ll))
            out["games"] += 1
            log.info("sno=%s scoreboard=%d livelog=%d", sno, len(sb), len(ll))
    finally:
        client.close()
    return out


def completed_snos(year: int, kind_code: str = KIND_REGULAR) -> list[int]:
    """本季已完成（比分>0）場次的 game_sno。"""
    with conn() as c:
        rows = c.execute(
            "SELECT game_sno FROM cpbl.games WHERE year = %s AND kind_code = %s "
            "AND home_score + away_score > 0 ORDER BY game_sno",
            (year, kind_code),
        ).fetchall()
    return [r[0] for r in rows]
