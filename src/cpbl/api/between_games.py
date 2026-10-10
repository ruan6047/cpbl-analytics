"""上場到下場的賽事報告（#238）：純計算，不連 DB、不讀時鐘。

報告身分＝「完賽場 X」。只計算呼叫端核實完成／截止的場集合；不自行讀現行資料。
歷史依截至 X 完成集合及既有公告首見版本重建，不混入後續結果。

紅線：
1. 未知一律 None／status 標記，⛔ 不補 0；查無對戰列不等於「無交手」。
2. 局數只由出局數換算；用球數照官方值（含真正的 0）；角色照原文，「最後一任」不是救援。
3. 連續登板只算連續日曆日，每天都要是可信的投球日；保留賽跨日時日期不可信。
4. 比率條件不成立就回 None，⛔ 不用累計量比較不同長度的期間。
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import date, datetime
from typing import Any

# —— 比率（單一共用函式；條件不成立回 None） ————————————————————————

_RATE_FIELDS = ("ab", "h", "b2", "b3", "hr", "bb", "hbp", "sf")


def _ratio(num: float, den: float, nd: int) -> float | None:
    return round(num / den, nd) if den > 0 else None


def batting_rates(c: Mapping[str, Any]) -> dict[str, float | None]:
    """打擊三圍與 OPS。沿既有 box 計數口徑，BB 包含故意四壞。

    條件：AB>0，且 H、2B、3B、HR、BB、HBP、SF 都不是 None；任一不成立四項全回 None。
    """
    if any(c.get(k) is None for k in _RATE_FIELDS) or c["ab"] <= 0:
        return {"avg": None, "obp": None, "slg": None, "ops": None}
    ab, h, bb, hbp, sf = c["ab"], c["h"], c["bb"], c["hbp"], c["sf"]
    tb = h + c["b2"] + 2 * c["b3"] + 3 * c["hr"]
    obp = _ratio(h + bb + hbp, ab + bb + hbp + sf, 3)
    slg = _ratio(tb, ab, 3)
    return {
        "avg": _ratio(h, ab, 3),
        "obp": obp,
        "slg": slg,
        "ops": round(obp + slg, 3) if obp is not None and slg is not None else None,
    }


def pa_rates(pa: int | None, so: int | None, bb: int | None) -> dict[str, float | None]:
    """三振率（SO/PA）與保送率（BB/PA，含故意四壞），與 `batting_current.k_pct/bb_pct` 同義。

    條件：PA>0，SO 與 BB 都不是 None 且不大於 PA。
    """
    if pa is None or so is None or bb is None or pa <= 0 or so > pa or bb > pa:
        return {"k_rate": None, "bb_rate": None}
    return {"k_rate": round(so / pa, 3), "bb_rate": round(bb / pa, 3)}


def pitching_rates(c: Mapping[str, Any]) -> dict[str, float | None]:
    """ERA、WHIP、SO/BB；出局數為 0 或缺值時回 None。"""
    outs, er, h, bb, so = (c.get(k) for k in ("outs", "er", "h", "bb", "so"))
    if outs is None or outs <= 0 or er is None or h is None or bb is None:
        era = whip = None
    else:
        era = round(er * 27 / outs, 2)
        whip = round((h + bb) * 3 / outs, 2)
    so_bb = round(so / bb, 2) if so is not None and bb else None
    return {"era": era, "whip": whip, "so_bb": so_bb}


def ip_text(outs: int | None) -> str | None:
    """出局數 → 局數字串（7 出局＝"2.1"）。"""
    return None if outs is None else f"{outs // 3}.{outs % 3}"


# —— 系列截至 ————————————————————————————————————————————————


def order_series(games: Iterable[Mapping[str, Any]]) -> tuple[list[dict[str, Any]], bool]:
    """系列場次依 (日期, 場號) 排序（與 postseason-summary 同序）。

    第二個回傳值＝場號順序是否與日期順序一致。不用 sno 大小代替完成場集合。
    """
    ordered = sorted((dict(g) for g in games), key=lambda g: (g["game_date"], g["game_sno"]))
    snos = [g["game_sno"] for g in ordered]
    return ordered, snos == sorted(snos)


def through(ordered: list[dict[str, Any]], game_sno: int) -> list[dict[str, Any]] | None:
    """截至 X（含）的場次；X 不在系列內回 None。"""
    for i, g in enumerate(ordered):
        if g["game_sno"] == game_sno:
            return ordered[: i + 1]
    return None


def date_trusted(game: Mapping[str, Any]) -> bool:
    """該場的比賽日期能否當作每位投手的實際投球日。

    保留賽跨兩個日曆日，無法分辨每位投手是哪一天投的 → 不可信；延賽場的 game_date
    就是實際比賽日（原定日在 orig_date）→ 可信。
    """
    return game.get("delay_kind") != "保留" and game.get("game_date") is not None


# —— 投手使用 ————————————————————————————————————————————————


def _as_date(v: Any) -> date | None:
    if v is None or isinstance(v, date):
        return v
    return date.fromisoformat(str(v)[:10])


def pitcher_usage(
    appearances: list[Mapping[str, Any]], next_date: date | None,
) -> dict[str, Any]:
    """一位投手在截至 X 的系列登板 → 局數、最後登板日、連續日曆日、（選看）合計球數與間隔。

    appearances：`{game_sno, date, date_trusted, role_type, outs, pitch_cnt}`，依系列順序。
    """
    apps = [dict(a) for a in appearances]
    outs = [a["outs"] for a in apps]
    total_outs = None if not outs or any(o is None for o in outs) else sum(outs)
    trusted = bool(apps) and all(a["date_trusted"] and _as_date(a["date"]) for a in apps)
    days = sorted({_as_date(a["date"]) for a in apps}) if trusted else []
    last = days[-1] if days else None
    consecutive = None
    if trusted and days:
        consecutive = 1
        for prev, cur in zip(reversed(days[:-1]), reversed(days[1:]), strict=True):
            if (cur - prev).days != 1:
                break
            consecutive += 1
    pitches = [a["pitch_cnt"] for a in apps]
    pitch_total = None if not pitches or any(p is None for p in pitches) else sum(pitches)
    gap = (next_date - last).days if (last is not None and next_date is not None) else None
    return {
        "appearances": apps,
        "outs": total_outs,
        "ip": ip_text(total_outs),
        "last_date": last,
        "dates_trusted": trusted,
        "consecutive_days": consecutive,
        "pitch_total": pitch_total,
        "days_to_next": gap,
        "started": any(a.get("role_type") == "先發" for a in apps),
    }


# —— 下一場：官方仍未開打時的最後賽程版本 ————————————————————————————


def _started_obs(row: Mapping[str, Any]) -> bool:
    # 官方 getgamedatas 的 PresentStatus 沒有「進行中」；開打只能讀 IsPlayBall=Y，
    # 或已出現官方完賽（GameResult=0）／保留（=2，已開賽中止）。（WP0 P2）
    return row.get("is_play_ball") == "Y" or (row.get("raw_game_result") or "") in ("0", "2")


def pregame_schedule(
    rows: list[Mapping[str, Any]], game_date: date | None,
) -> dict[str, Any]:
    """下一場的賽程版本 → 官方開打判定與開賽前的先發公告。

    rows：該場全部 `game_schedule_status_revisions`（投影 is_play_ball、away_p、home_p）。
    開賽前版本必須有正面 IsPlayBall=N 原證、現行列、明確空結果與可信首次 fetched_at。
    有第一筆已開打觀測時，首次取得須嚴格早於它。last_seen 不作公告首次取得時間。
    不以預定時間、未知 enum 或僅未觀測 Y 成立公告。
    """
    started = [r["fetched_at"] for r in rows if _started_obs(r) and r.get("fetched_at")]
    first_started = min(started) if started else None
    cands = [
        r for r in rows
        if r.get("raw_present_status") == 1 and r.get("raw_game_result") in (None, "")
        and r.get("is_play_ball") == "N" and r.get("fetched_at") is not None
        and game_date is not None and _as_date(r.get("raw_game_date")) == game_date
        and (first_started is None or r["fetched_at"] < first_started)
    ]
    pre = max(cands, key=lambda r: (r["fetched_at"], r.get("payload_hash") or ""),
              default=None)

    def starter(side: str) -> dict[str, Any]:
        acnt = pre.get(f"{side}_p") if pre else None
        if not acnt:
            return {"status": "unverified", "acnt": None, "observed_at": None}
        return {"status": "announced", "acnt": acnt, "observed_at": pre.get("fetched_at"),
                "source_version": pre.get("payload_hash"),
                "pregame_evidence": {"is_play_ball": "N", "fetched_at": pre.get("fetched_at"),
                                     "first_started_at": first_started}}

    return {
        "official_started": "confirmed" if first_started is not None else "not_observed",
        "started_observed_at": first_started,
        "schedule_observed_at": None if pre is None else pre.get("fetched_at"),
        "scheduled_start": None if pre is None else pre.get("scheduled_start"),
        "away_starter": starter("away"),
        "home_starter": starter("home"),
    }


# —— 打者 ————————————————————————————————————————————————————


_BAT_KEYS = ("pa", "ab", "h", "b2", "b3", "hr", "bb", "ibb", "hbp", "sf", "so", "r", "rbi", "sb")


def sum_batting(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """逐場列加總；任一場某欄為 None，該欄合計就是 None（不當 0）。"""
    rows = list(rows)
    out: dict[str, Any] = {"g": len(rows) if rows else None}
    for k in _BAT_KEYS:
        vals = [r.get(k) for r in rows]
        out[k] = None if not vals or any(v is None for v in vals) else sum(vals)
    out["xbh"] = None if None in (out["b2"], out["b3"], out["hr"]) else out["b2"] + out["b3"] + out["hr"]
    out.update(batting_rates(out))
    out.update(pa_rates(out["pa"], out["so"], out["bb"]))
    return out


# —— 觀察問題（固定規則模板，只引用截至 X 的事實；不判可用性或疲勞） ——————————————


def watch_points(pitchers: list[dict[str, Any]], batters: list[dict[str, Any]],
                 through_date: date | None, limit: int = 3) -> list[dict[str, str]]:
    """依固定順序挑少量看點：連續登板的投手 → 本系列長打最多的打者。"""
    points: list[dict[str, str]] = []
    streaks = sorted(
        (p for p in pitchers
         if p["consecutive_days"] and p["consecutive_days"] >= 2 and p["last_date"] == through_date),
        key=lambda p: (-p["consecutive_days"], p["name"] or ""))
    for p in streaks[:1]:
        points.append({
            "kind": "pitcher_streak", "player_id": p["player_id"],
            "fact": f"{p['name']}本系列已連續 {p['consecutive_days']} 個日曆日登板（截至此場）。",
            "question": f"下一場{p['name']}會不會再上場、在第幾局上場？",
        })
    hitters = sorted(
        (b for b in batters if b["series"]["xbh"] and b["series"]["pa"]),
        key=lambda b: (-b["series"]["xbh"], -(b["series"]["h"] or 0), b["name"] or ""))
    for b in hitters[:1]:
        s = b["series"]
        points.append({
            "kind": "batter_xbh", "player_id": b["player_id"],
            "fact": f"{b['name']}本系列 {s['pa']} 個打席、{s['h']} 支安打，其中 {s['xbh']} 支長打（截至此場）。",
            "question": f"下一場{b['name']}能不能延續長打？",
        })
    return points[:limit]


def iso(v: Any) -> Any:
    """JSON 友善：date/datetime 轉 ISO 字串，其餘原樣。"""
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    return v
