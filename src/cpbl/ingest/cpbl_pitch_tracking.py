"""逐球 TrackMan 追蹤資料爬蟲（stats.cpbl logs API）。

改走官方 JSON API `/api/proxy/v1/players/logs`（取代舊版解析投手頁 RSC __next_f 的
括號配對）：更穩、乾淨，且支援 kindCode A/C/D/E（一軍/一軍季後/二軍/二軍季後），
可完整補二軍與季後逐球。API 依 kindCode server-side 過濾，故不會跨 kind 重複。

回應結構：{"Data":{"Logs":[{...,"Trackman":{"Play":{"PitchTag":{…}},
"Pitch":{"Release":{…},"Location":{…}},"Hit":{"Launch":{…},"LandingFlat":{…}}}}]}}。
無 TrackMan 設備球場的球 Trackman=null → 不收（與舊版語意一致）。冪等 UPSERT。
"""

from __future__ import annotations

import datetime as _dt
import logging
import time

import httpx

from cpbl.db import conn

log = logging.getLogger("cpbl.pitch")

BASE = "https://stats.cpbl.com.tw"
LOGS_EP = f"{BASE}/api/proxy/v1/players/logs"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"


def _f(v) -> float | None:
    try:
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _i(v) -> int | None:
    try:
        return int(float(v)) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _fetch_logs(client: httpx.Client, acnt: str, year: int, kind_code: str) -> list[dict]:
    r = client.get(LOGS_EP, params={
        "playerType": "pitcher", "acnt": acnt, "year": str(year), "kindCode": kind_code})
    r.raise_for_status()
    return (r.json().get("Data") or {}).get("Logs") or []


def _record(p: dict, kind_default: str) -> tuple | None:
    tm = p.get("Trackman")
    if not tm:  # 無 TrackMan 設備球場 → 不收（同舊版）
        return None
    tag = (tm.get("Play") or {}).get("PitchTag") or {}
    pit = tm.get("Pitch") or {}
    rel = pit.get("Release") or {}
    loc = pit.get("Location") or {}
    hit = tm.get("Hit") or {}
    launch = hit.get("Launch") or {}
    land = hit.get("LandingFlat") or {}
    sno, pcnt, pacnt = _i(p.get("GameSno")), _i(p.get("PitchCnt")), p.get("PitcherAcnt")
    if sno is None or pcnt is None or not pacnt:
        return None
    return (
        _i(p.get("Year")), p.get("KindCode") or kind_default, sno, pacnt, pcnt,
        p.get("PitcherName"), p.get("HitterAcnt"), p.get("HitterName"),
        _i(p.get("InningSeq")), _i(p.get("BallCnt")), _i(p.get("StrikeCnt")), _i(p.get("OutCnt")),
        _i(p.get("BattingOrder")), p.get("Content"),
        tag.get("PitchCall"), tag.get("AutoPitchType"), tag.get("TaggedPitchType"),
        _f(rel.get("RelSpeed")), _f(rel.get("SpinRate")), _f(rel.get("RelSide")),
        _f(rel.get("RelHeight")), _f(rel.get("Extension")),
        _f(loc.get("ZoneSpeed")), _f(loc.get("PlateLocSide")), _f(loc.get("PlateLocHeight")),
        _f(launch.get("ExitSpeed")), _f(launch.get("Angle")), _f(launch.get("Direction")),
        _f(land.get("Distance")), _f(land.get("HangTime")),
    )


_COLS = ("year,kind_code,game_sno,pitcher_acnt,pitch_cnt,pitcher_name,hitter_acnt,hitter_name,"
         "inning_seq,ball_cnt,strike_cnt,out_cnt,batting_order,content,pitch_call,auto_pitch_type,"
         "tagged_pitch_type,rel_speed,spin_rate,rel_side,rel_height,extension,zone_speed,"
         "plate_loc_side,plate_loc_height,hit_exit_speed,hit_launch_angle,hit_direction,"
         "hit_distance,hit_hang_time")


def _upsert(records: list[tuple]) -> int:
    # 去重：同一 PK (year,kind,game,pitcher,pitch_cnt) 只留一筆
    seen, uniq = set(), []
    for r in records:
        key = (r[0], r[1], r[2], r[3], r[4])
        if key in seen:
            continue
        seen.add(key)
        uniq.append(r)
    if not uniq:
        return 0
    cols = [c.strip() for c in _COLS.split(",")]
    ph = "(" + ",".join(["%s"] * len(cols)) + ")"
    updates = ", ".join(f"{c}=EXCLUDED.{c}" for c in cols[5:])
    with conn() as c:
        c.cursor().executemany(
            f"INSERT INTO cpbl.pitch_tracking ({_COLS}) VALUES {ph} "
            f"ON CONFLICT (year, kind_code, game_sno, pitcher_acnt, pitch_cnt) DO UPDATE SET {updates}",
            uniq,
        )
    return len(uniq)


def scrape_pitches(pitcher_acnts: list[str], year: int | None = None,
                   kind_code: str = "A", delay: float = 1.0) -> dict:
    """逐投手抓其該季/該 kind 每球 TrackMan（logs API）。回傳 {pitchers, pitches}。

    year 預設本季；kind_code=A 一軍例行 / C 一軍季後 / D 二軍 / E 二軍季後。
    """
    year = year or _dt.date.today().year
    client = httpx.Client(timeout=60.0, headers={"User-Agent": UA}, follow_redirects=True)
    out = {"pitchers": 0, "pitches": 0}
    try:
        for idx, acnt in enumerate(pitcher_acnts, 1):
            time.sleep(delay)
            try:
                logs = _fetch_logs(client, acnt, year, kind_code)
            except (httpx.HTTPError, ValueError) as e:
                log.warning("[%d/%d] acnt=%s API 失敗：%s", idx, len(pitcher_acnts), acnt, e)
                continue
            rows = [t for t in (_record(p, kind_code) for p in logs) if t]
            n = _upsert(rows)
            out["pitchers"] += 1
            out["pitches"] += n
            log.info("[%d/%d] acnt=%s %d/%s → %d 球（累計 %d）",
                     idx, len(pitcher_acnts), acnt, year, kind_code, n, out["pitches"])
    finally:
        client.close()
    return out


def current_pitchers() -> list[str]:
    with conn() as c:
        return [r[0] for r in c.execute(
            "SELECT DISTINCT player_id FROM cpbl.pitching_current ORDER BY player_id").fetchall()]


def pitchers_by_kind(year: int, kind_code: str) -> list[str]:
    """有在該 year/kind 出賽的投手（自 pitching_gamelog）。供二軍/季後回填用。"""
    with conn() as c:
        return [r[0] for r in c.execute(
            "SELECT DISTINCT pitcher_acnt FROM cpbl.pitching_gamelog "
            "WHERE year=%s AND kind_code=%s ORDER BY 1", (year, kind_code)).fetchall()]
