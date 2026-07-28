"""球隊頁「近日焦點」素材 3：即將挑戰的紀錄（UX-TEAM-RECORDS1；唯讀）。

三種素材（2026-07-28 需求方定案，記於 docs/tasks/UX-TEAM-RECORDS1.md，不得自行更動）：

1. **個人生涯里程碑**（計數型）——生涯口徑一律走 `cpbl.api.routers.players` 的
   canonical helper（`_career_batting_per_year`/`_career_pitching_per_year` +
   `_sum_batting_career`/`_sum_pitching_career`），與球員頁
   `/api/v1/players/{id}/career` 同一份邏輯（該端點本身也改走這兩個 helper）。
   **嚴禁另行拼裝 `batting_seasons` ∪ gamelog**——那是卡面紅線：自行拼裝會與
   球員頁生涯數字對不起來。階梯／門檻表見 `BATTER_MILESTONES`/`PITCHER_MILESTONES`
   （卡面表格，Coordinator 依實測密度定案，執行者不得逕自改動數值）。
   排序＝「差距／階梯」比值由小到大（越接近越前面）。

2. **進行中連續安打**——直接呼叫 `cpbl.api.team_focus._current_hit_streak`
   （UX-TEAM-FOCUS2 已上線，kind_code='A' 一軍口徑），不重寫。`STREAK_MIN`/
   `STREAK_TOP_N` 是本卡新增（卡面只要求複用計算本身，未定義呈現門檻/上限）——
   執行者提案 5 場起算、至多列 5 位，理由：避免每隊塞滿 0~2 場的雜訊，5 場
   在中職語境已算「連續安打」值得關注的長度。

3. **隊史紀錄逼近（僅計數型）**——франchise 範圍**限定 `*_seasons`（1990+），
   刻意不併入本季 gamelog**。這與素材 1「生涯」數字不同義：素材 1 問的是
   「這位球員全生涯（含本季）累積多少」，素材 3 問的是「這位球員在**這支球隊
   歷史上**排名如何、離隊史紀錄還差多少」——卡面背景表格明載這裡的資料源只到
   `*_seasons`，代表本季（gamelog 尚未併入 `*_seasons`）的貢獻要等年度資料
   落表後才會反映在隊史榜上，這是已知的更新延遲、不是缺陷，需在前端文案上
   避免誤導（不宣稱「即時」）。**連續型隊史紀錄（最長連續安打/無失分等）不做**
   ——需求方 2026-07-28 裁定，逐場資料僅 2018+ 會讓口徑半殘，任何「近年最佳」
   變體措辭也不得出現，本模組完全不產生這類欄位。
   門檻沿用素材 1 同一組 `near`/`ladder`（執行者提案的延伸，卡面本身未定義
   隊史逼近的門檻，理由是維持同一組數字讓使用者好理解、避免另立一套語意）。

範圍限定**一軍現役名單**（`batting_current`/`pitching_current`，`year=season`）：
`_current_hit_streak` 本身即 kind_code='A'（一軍）口徑，混入二軍名單會造成
同一區塊內標準不一致；且二軍球員的 `*_seasons`/`batting_gamelog` 覆蓋是否對齊
未經查證，故本模組全程只看一軍現役名單（執行者範圍決定，非隊史/生涯口徑本身
的紅線）。

`available`／退化語意：三個陣列（`milestones`/`streaks`/`franchise_records`）
分別可能為空；前端在三者皆空時顯示統一退化文案「目前無接近中的紀錄」，
不顯示空區塊或零值（見 `docs/tasks/UX-TEAM-RECORDS1.md` 驗收條件）。
"""

from __future__ import annotations

from cpbl.api.helpers import DEFAULT_SEASON
from cpbl.api.routers.players import (
    _career_batting_per_year,
    _career_pitching_per_year,
    _sum_batting_career,
    _sum_pitching_career,
)
from cpbl.api.team_focus import _current_hit_streak
from cpbl.db import conn
from cpbl.franchises import franchise_prefixes

# 里程碑階梯與門檻（卡面表格，勿逕自改動數值；label/stat 對齊 canonical 生涯欄位）。
BATTER_MILESTONES = [
    {"stat": "h", "label": "安打", "ladder": 100, "start": 200, "near": 10},
    {"stat": "rbi", "label": "打點", "ladder": 100, "start": 200, "near": 10},
    {"stat": "r", "label": "得分", "ladder": 100, "start": 200, "near": 10},
    {"stat": "hr", "label": "全壘打", "ladder": 25, "start": 25, "near": 3},
    {"stat": "sb", "label": "盜壘", "ladder": 25, "start": 25, "near": 3},
]
PITCHER_MILESTONES = [
    {"stat": "so", "label": "三振", "ladder": 100, "start": 200, "near": 10},
    {"stat": "ip", "label": "投球局數", "ladder": 100, "start": 200, "near": 10},
    {"stat": "w", "label": "勝投", "ladder": 10, "start": 20, "near": 2},
    {"stat": "sv_hld", "label": "救援／中繼", "ladder": 25, "start": 25, "near": 3},
]

STREAK_MIN = 5
STREAK_TOP_N = 5


def _next_milestone(current: int, ladder: int, start: int) -> tuple[int, int]:
    """回傳（下一個里程碑, 差距）。里程碑＝大於現值、且 ≥ 起始門檻的最小階梯倍數。"""
    candidate = ((current // ladder) + 1) * ladder
    if candidate < start:
        candidate = start
    return candidate, candidate - current


def _roster(cur, code: str, season: int) -> tuple[list[dict], list[dict]]:
    """一軍現役名單（打者／投手），供三種素材共用。"""
    cur.execute(
        "SELECT player_id, name FROM cpbl.batting_current WHERE team_code=%s AND year=%s ORDER BY name",
        (code, season))
    batters = [{"player_id": p, "name": n} for p, n in cur.fetchall()]
    cur.execute(
        "SELECT player_id, name FROM cpbl.pitching_current WHERE team_code=%s AND year=%s ORDER BY name",
        (code, season))
    pitchers = [{"player_id": p, "name": n} for p, n in cur.fetchall()]
    return batters, pitchers


def _batter_milestones(cur, roster: list[dict]) -> list[dict]:
    out = []
    for pl in roster:
        per = _career_batting_per_year(cur, pl["player_id"])
        if not per:
            continue
        tot = _sum_batting_career(per)
        for m in BATTER_MILESTONES:
            current = int(tot.get(m["stat"], 0) or 0)
            milestone, gap = _next_milestone(current, m["ladder"], m["start"])
            if 0 < gap <= m["near"]:
                out.append({
                    "player_id": pl["player_id"], "name": pl["name"], "role": "batting",
                    "stat": m["stat"], "label": m["label"], "current": current,
                    "milestone": milestone, "remaining": gap, "ladder": m["ladder"],
                    "ratio": round(gap / m["ladder"], 4),
                })
    return out


def _pitcher_milestones(cur, roster: list[dict]) -> list[dict]:
    out = []
    for pl in roster:
        pper = _career_pitching_per_year(cur, pl["player_id"])
        if not pper:
            continue
        pt = _sum_pitching_career(pper)
        outs = round(pt.get("rip", 0.0) * 3)
        values = {
            "so": int(pt.get("so", 0) or 0),
            "ip": outs // 3,
            "w": int(pt.get("w", 0) or 0),
            "sv_hld": int(pt.get("sv", 0) or 0) + int(pt.get("hld", 0) or 0),
        }
        for m in PITCHER_MILESTONES:
            current = values[m["stat"]]
            milestone, gap = _next_milestone(current, m["ladder"], m["start"])
            if 0 < gap <= m["near"]:
                out.append({
                    "player_id": pl["player_id"], "name": pl["name"], "role": "pitching",
                    "stat": m["stat"], "label": m["label"], "current": current,
                    "milestone": milestone, "remaining": gap, "ladder": m["ladder"],
                    "ratio": round(gap / m["ladder"], 4),
                })
    return out


def _franchise_batting_totals(cur, prefixes: list[str]) -> dict[str, dict]:
    cur.execute(
        "SELECT bs.player_id, max(p.name), sum(bs.h), sum(bs.rbi), sum(bs.r), sum(bs.hr), sum(bs.sb) "
        "FROM cpbl.batting_seasons bs LEFT JOIN cpbl.players p ON p.id = bs.player_id "
        "WHERE substring(bs.team_id,1,3) = ANY(%s) GROUP BY bs.player_id",
        (prefixes,))
    return {
        pid: {"name": nm or pid, "h": h or 0, "rbi": rbi or 0, "r": r or 0, "hr": hr or 0, "sb": sb or 0}
        for pid, nm, h, rbi, r, hr, sb in cur.fetchall()
    }


def _franchise_pitching_totals(cur, prefixes: list[str]) -> dict[str, dict]:
    cur.execute(
        "SELECT ps.player_id, max(p.name), sum(ps.so), "
        "sum(trunc(ps.ip)+(ps.ip-trunc(ps.ip))*10/3.0), sum(ps.w), sum(ps.sv), sum(ps.hld) "
        "FROM cpbl.pitching_seasons ps LEFT JOIN cpbl.players p ON p.id = ps.player_id "
        "WHERE substring(ps.team_id,1,3) = ANY(%s) GROUP BY ps.player_id",
        (prefixes,))
    out = {}
    for pid, nm, so, rip, w, sv, hld in cur.fetchall():
        outs = round(float(rip or 0.0) * 3)
        out[pid] = {"name": nm or pid, "so": so or 0, "ip": outs // 3, "w": w or 0,
                    "sv_hld": (sv or 0) + (hld or 0)}
    return out


def _franchise_approach(
    roster: list[dict], totals: dict[str, dict], stat_defs: list[dict], role: str,
) -> list[dict]:
    """roster 中franchise-scoped 總和逼近隊史紀錄（最大值）者。已是唯一持有人不算逼近。"""
    out = []
    for m in stat_defs:
        stat = m["stat"]
        best_val = max((v[stat] for v in totals.values()), default=0)
        if best_val <= 0:
            continue
        holders = sorted({v["name"] for v in totals.values() if v[stat] == best_val})
        for pl in roster:
            v = totals.get(pl["player_id"])
            if v is None:
                continue
            current = v[stat]
            gap = best_val - current
            if 0 < gap <= m["near"]:
                out.append({
                    "player_id": pl["player_id"], "name": pl["name"], "role": role,
                    "stat": stat, "label": m["label"], "current": current,
                    "record": best_val, "remaining": gap, "holder": "、".join(holders),
                    "ratio": round(gap / m["ladder"], 4),
                })
    return out


def upcoming_records(code: str, season: int = DEFAULT_SEASON) -> dict:
    """球隊頁「即將挑戰的紀錄」：生涯里程碑 + 進行中連續安打 + 隊史紀錄逼近（計數型）。"""
    with conn() as c:
        cur = c.cursor()
        batters_roster, pitchers_roster = _roster(cur, code, season)

        milestones = _batter_milestones(cur, batters_roster) + _pitcher_milestones(cur, pitchers_roster)
        milestones.sort(key=lambda x: x["ratio"])

        streaks = []
        for pl in batters_roster:
            s = _current_hit_streak(cur, code, season, pl["player_id"])
            if s >= STREAK_MIN:
                streaks.append({"player_id": pl["player_id"], "name": pl["name"], "streak": s})
        streaks.sort(key=lambda x: -x["streak"])
        streaks = streaks[:STREAK_TOP_N]

        prefixes = sorted(franchise_prefixes(code))
        franchise_batters = _franchise_batting_totals(cur, prefixes)
        franchise_pitchers = _franchise_pitching_totals(cur, prefixes)
        franchise_records = (
            _franchise_approach(batters_roster, franchise_batters, BATTER_MILESTONES, "batting")
            + _franchise_approach(pitchers_roster, franchise_pitchers, PITCHER_MILESTONES, "pitching")
        )
        franchise_records.sort(key=lambda x: x["ratio"])

    return {
        "season": season,
        "milestones": milestones,
        "streaks": streaks,
        "franchise_records": franchise_records,
    }
