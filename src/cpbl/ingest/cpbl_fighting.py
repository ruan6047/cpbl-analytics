"""官網選手頁「投打對決」爬蟲（POST /team/getfightingscore）。

實測確認的契約（與 getgamedatas 同屬 ASP.NET MVC anti-forgery，token 走 **header**）：
1. GET /team/fighting?Acnt=<打者> → 取 session cookie + 從 inline JS 抽兩個 header token
   （getSelectOpts / getFightingScore 各有專屬 token）。
2. POST /team/getfightingoptsaction（acnt/kindCode/year/fightingTeamNo/fightingAcnt）
   → FightingTeamOpts 給「該打者對戰過的球隊」清單。
3. POST /team/getfightingscore，**只給 fightingTeamNo、不給 fightingAcnt**
   → 一次回傳對該隊**所有投手**的對決列（大幅減少請求數）。
   回 {"Success": true, "FightingScore": "<JSON 字串>"}，需二次 json.loads。

官網偶發回 Big5 的 500 錯誤頁（anti-forgery / 限流），故每個請求帶重試與退避，
連續失敗則重建 session（換 token）。冪等 UPSERT。
"""

from __future__ import annotations

import json
import logging
import re
import time

import httpx

from cpbl.db import conn

log = logging.getLogger("cpbl.fighting")

BASE = "https://www.cpbl.com.tw"
FIGHTING_PAGE = f"{BASE}/team/fighting"
OPTS_ENDPOINT = f"{BASE}/team/getfightingoptsaction"
SCORE_ENDPOINT = f"{BASE}/team/getfightingscore"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
KIND_REGULAR = "A"

_TOKEN_RE = re.compile(r"RequestVerificationToken:\s*'([^']+)'")


def _token_in(html: str, fn_marker: str) -> str:
    """抽某個 JS 函式區塊內的專屬 header token。"""
    blk = html[html.find(fn_marker):][:1600]
    m = _TOKEN_RE.search(blk)
    if not m:
        raise RuntimeError(f"找不到 {fn_marker} 的 RequestVerificationToken（官網可能改版）")
    return m.group(1)


def _i(v) -> int | None:
    try:
        return int(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _f(v) -> float | None:
    try:
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


OPTS_PATH = "/team/getfightingoptsaction"
SCORE_PATH = "/team/getfightingscore"


class _Session:
    """單一打者的抓取 session：走共用 browser session（過反爬挑戰），持有兩個 token。"""

    def __init__(self, acnt: str, delay: float):
        self.acnt = acnt
        self.delay = delay
        self.page_path = f"/team/fighting?Acnt={acnt}"
        self._open()

    def _open(self) -> None:
        from cpbl.ingest._browser import session
        html = session().page_html(self.page_path)
        self.opts_token = _token_in(html, "getSelectOpts: function")
        self.score_token = _token_in(html, "getFightingScore: function")

    def close(self) -> None:
        pass  # 共用 browser session，不在此關閉

    def _post(self, api_path: str, token: str, data: dict, retries: int = 4) -> dict:
        """於該打者 fighting 頁 context POST 並解析 JSON；失敗退避重試、重取 token。"""
        from cpbl.ingest._browser import session
        for attempt in range(retries):
            time.sleep(self.delay)
            try:
                status, text = session().post(
                    self.page_path, api_path, data,
                    headers={"RequestVerificationToken": token},
                )
                if status == 200:
                    try:
                        return json.loads(text)
                    except (json.JSONDecodeError, ValueError):
                        pass
                log.warning("非 JSON 回應 (%s) acnt=%s attempt=%d", status, self.acnt, attempt + 1)
            except Exception as e:  # noqa: BLE001 — 退避重試
                log.warning("例外 acnt=%s: %s", self.acnt, e)
            time.sleep(2.0 * (attempt + 1))  # 線性退避
            if attempt == retries - 2:  # 倒數第二次：重取 token
                self._open()
                token = self.score_token if api_path == SCORE_PATH else self.opts_token
        raise RuntimeError(f"{api_path} 連續失敗 acnt={self.acnt}")

    def teams_faced(self, year: int, kind_code: str) -> list[str]:
        j = self._post(OPTS_PATH, self.opts_token, {
            "acnt": self.acnt, "kindCode": kind_code, "year": str(year),
            "fightingTeamNo": "", "fightingAcnt": "",
        })
        opts = json.loads(j.get("FightingTeamOpts") or "[]")
        return [o["Value"] for o in opts if o.get("Value")]

    def vs_team(self, year: int, kind_code: str, team_no: str) -> list[dict]:
        j = self._post(SCORE_PATH, self.score_token, {
            "acnt": self.acnt, "kindCode": kind_code, "year": str(year),
            "fightingTeamNo": team_no, "fightingAcnt": "",
        })
        return json.loads(j.get("FightingScore") or "[]")


def _to_record(g: dict, year: int, kind_code: str) -> tuple:
    return (
        year, kind_code, g.get("HitterAcnt"), g.get("PitcherAcnt"),
        g.get("HitterName"), g.get("PitcherName"),
        g.get("HitterTeamNo"), g.get("PitcherTeamNo"),
        _i(g.get("PlateAppearances")), _i(g.get("HitCnt")), _i(g.get("HittingCnt")),
        _i(g.get("RunBattedINCnt")), _i(g.get("OneBaseHitCnt")), _i(g.get("TwoBaseHitCnt")),
        _i(g.get("ThreeBaseHitCnt")), _i(g.get("HomeRunCnt")), _i(g.get("TotalBases")),
        _f(g.get("Avg")), _f(g.get("Obp")), _f(g.get("Slg")), _f(g.get("Ops")),
        _i(g.get("SacrificeHitCnt")), _i(g.get("SacrificeFlyCnt")),
        _i(g.get("BasesONBallsCnt")), _i(g.get("IntentionalBasesONBallsCnt")),
        _i(g.get("HitBYPitchCnt")), _i(g.get("StrikeOutCnt")),
        _i(g.get("GroundOut")), _i(g.get("FlyOut")), _f(g.get("Goao")),
        _f(g.get("Strike_Pct")), _f(g.get("Ball_Pct")), _f(g.get("Swing_Pct")),
        _f(g.get("First_Pitch_Swing_Pct")), _f(g.get("Whiff_Pct")),
        _f(g.get("GB_Pct")), _f(g.get("LD_Pct")), _f(g.get("FB_Pct")),
    )


_COLS = (
    "year, kind_code, hitter_acnt, pitcher_acnt, hitter_name, pitcher_name, "
    "hitter_team_no, pitcher_team_no, plate_appearances, at_bats, hits, rbi, "
    "singles, doubles, triples, home_runs, total_bases, avg, obp, slg, ops, "
    "sac_hit, sac_fly, bb, ibb, hbp, so, ground_out, fly_out, goao, "
    "strike_pct, ball_pct, swing_pct, first_pitch_swing_pct, whiff_pct, gb_pct, ld_pct, fb_pct"
)


def upsert_matchups(records: list[tuple]) -> int:
    records = [r for r in records if r[2] and r[3]]  # 需有 hitter+pitcher acnt
    if not records:
        return 0
    placeholders = "(" + ", ".join(["%s"] * 38) + ")"
    updates = ", ".join(
        f"{c.strip()}=EXCLUDED.{c.strip()}"
        for c in _COLS.split(",")[4:]  # PK 後的欄位都更新
    ) + ", updated_at=now()"
    with conn() as c:
        c.cursor().executemany(
            f"INSERT INTO cpbl.batter_pitcher_matchups ({_COLS}) VALUES {placeholders} "
            f"ON CONFLICT (year, kind_code, hitter_acnt, pitcher_acnt) DO UPDATE SET {updates}",
            records,
        )
    return len(records)


def _current_batters() -> list[str]:
    """本季登錄打者（batting_current）。"""
    with conn() as c:
        rows = c.execute(
            "SELECT DISTINCT player_id FROM cpbl.batting_current ORDER BY player_id"
        ).fetchall()
    return [r[0] for r in rows]


def _current_pitchers() -> set[str]:
    """本季登錄投手（pitching_current）— 用於只保留一軍現役投手的對戰。"""
    with conn() as c:
        rows = c.execute("SELECT DISTINCT player_id FROM cpbl.pitching_current").fetchall()
    return {r[0] for r in rows}


# 一軍正式賽別：A 例行賽 / C 總冠軍賽 / E 季後挑戰賽（排除熱身/明星/二軍/交流）
KINDS_FIRST_TEAM = ["A", "C", "E"]
YEAR_CAREER = 9999  # 年度累計


def scrape_matchups(
    years: list[int], kinds: list[str] | None = None, delay: float = 1.2,
    batter_ids: list[str] | None = None, pitcher_ids: set[str] | None = None,
) -> int:
    """逐打者抓投打對決並 UPSERT。回傳總對戰列數。

    `years` × `kinds` 為要抓的（年度 × 賽別）組合；每位打者共用一個 session
    （1 GET），再對各組合做 opts + 各隊 score。每請求間隔 `delay` 秒。
    `pitcher_ids` 不為 None 時，只保留對戰投手屬於該集合（本季登錄一軍投手）的列。
    冪等：中途中斷可重跑，已寫入的列會被覆寫更新。
    """
    kinds = kinds or KINDS_FIRST_TEAM
    batters = batter_ids if batter_ids is not None else _current_batters()
    combos = [(y, k) for y in dict.fromkeys(years) for k in kinds]  # 年度去重
    log.info("投打對決：%d 位打者 × %d 組合(年度×賽別)=%s，delay=%.1fs，投手過濾=%s",
             len(batters), len(combos), combos, delay, "本季一軍" if pitcher_ids is not None else "無")
    total = 0
    for idx, acnt in enumerate(batters, 1):
        try:
            s = _Session(acnt, delay)
        except (httpx.HTTPError, RuntimeError) as e:
            log.error("[%d/%d] acnt=%s 建 session 失敗，略過：%s", idx, len(batters), acnt, e)
            continue
        try:
            n = 0
            for year, kind in combos:
                for team_no in s.teams_faced(year, kind):
                    rows = s.vs_team(year, kind, team_no)
                    if pitcher_ids is not None:
                        rows = [g for g in rows if g.get("PitcherAcnt") in pitcher_ids]
                    n += upsert_matchups([_to_record(g, year, kind) for g in rows])
            total += n
            log.info("[%d/%d] acnt=%s → %d 對戰列（累計 %d）", idx, len(batters), acnt, n, total)
        except (httpx.HTTPError, RuntimeError, KeyError, ValueError) as e:
            log.error("[%d/%d] acnt=%s 抓取失敗，略過：%s", idx, len(batters), acnt, e)
        finally:
            s.close()
    return total
