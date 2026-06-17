"""逐球 TrackMan 追蹤資料爬蟲（stats.cpbl 投手頁）。

每位投手頁的 RSC 內嵌其本季每球（含 trackman.pitch.release/location、hit.launch/landingFlat）。
以括號配對擷取每筆含 trackman 的事件物件並 json.loads（實測可 100% 解析）。冪等 UPSERT。
"""

from __future__ import annotations

import json
import logging
import re
import time

import httpx

from cpbl.db import conn

log = logging.getLogger("cpbl.pitch")

BASE = "https://stats.cpbl.com.tw"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
_PUSH_RE = re.compile(r'self\.__next_f\.push\(\[1,"((?:[^"\\]|\\.)*)"\]\)')
_REC_RE = re.compile(r'"trackman":\{"play"')


def _payload(client: httpx.Client, acnt: str) -> str:
    html = client.get(f"{BASE}/players/{acnt}").text
    return "".join(_PUSH_RE.findall(html)).encode().decode("unicode_escape", errors="replace")


def _enclosing(s: str, i: int) -> str:
    depth, j = 0, i
    while j > 0:
        c = s[j]
        if c == "}":
            depth += 1
        elif c == "{":
            if depth == 0:
                break
            depth -= 1
        j -= 1
    depth, k = 0, j
    while k < len(s):
        c = s[k]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                break
        k += 1
    return s[j:k + 1]


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


def _record(r: dict, kind_default: str) -> tuple | None:
    tm = r.get("trackman") or {}
    tag = (tm.get("play") or {}).get("pitchTag") or {}
    pit = tm.get("pitch") or {}
    rel = pit.get("release") or {}
    loc = pit.get("location") or {}
    hit = tm.get("hit") or {}
    launch = hit.get("launch") or {}
    land = hit.get("landingFlat") or {}
    sno, pcnt, pacnt = _i(r.get("gameSno")), _i(r.get("pitchCnt")), r.get("pitcherAcnt")
    if sno is None or pcnt is None or not pacnt:
        return None
    return (
        _i(r.get("year")), r.get("kindCode") or kind_default, sno, pacnt, pcnt,
        r.get("pitcherName"), r.get("hitterAcnt"), r.get("hitterName"),
        _i(r.get("inningSeq")), _i(r.get("ballCnt")), _i(r.get("strikeCnt")), _i(r.get("outCnt")),
        _i(r.get("battingOrder")), r.get("content"),
        tag.get("pitchCall"), tag.get("autoPitchType"), tag.get("taggedPitchType"),
        _f(rel.get("relSpeed")), _f(rel.get("spinRate")), _f(rel.get("relSide")),
        _f(rel.get("relHeight")), _f(rel.get("extension")),
        _f(loc.get("zoneSpeed")), _f(loc.get("plateLocSide")), _f(loc.get("plateLocHeight")),
        _f(launch.get("exitSpeed")), _f(launch.get("angle")), _f(launch.get("direction")),
        _f(land.get("distance")), _f(land.get("hangTime")),
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


def scrape_pitches(pitcher_acnts: list[str], kind_default: str = "A", delay: float = 1.0) -> dict:
    """逐投手抓其本季每球 TrackMan。回傳 {pitchers, pitches}。"""
    client = httpx.Client(timeout=60.0, headers={"User-Agent": UA}, follow_redirects=True)
    out = {"pitchers": 0, "pitches": 0}
    try:
        for idx, acnt in enumerate(pitcher_acnts, 1):
            time.sleep(delay)
            try:
                payload = _payload(client, acnt)
            except httpx.HTTPError as e:
                log.warning("[%d/%d] acnt=%s HTTP 失敗：%s", idx, len(pitcher_acnts), acnt, e)
                continue
            recs = []
            for m in _REC_RE.finditer(payload):
                try:
                    recs.append(json.loads(_enclosing(payload, m.start())))
                except (json.JSONDecodeError, ValueError):
                    pass
            rows = [t for t in (_record(r, kind_default) for r in recs) if t]
            n = _upsert(rows)
            out["pitchers"] += 1
            out["pitches"] += n
            log.info("[%d/%d] acnt=%s → %d 球（累計 %d）", idx, len(pitcher_acnts), acnt, n, out["pitches"])
    finally:
        client.close()
    return out


def current_pitchers() -> list[str]:
    with conn() as c:
        return [r[0] for r in c.execute(
            "SELECT DISTINCT player_id FROM cpbl.pitching_current ORDER BY player_id").fetchall()]
