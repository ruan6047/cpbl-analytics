"""球隊頁「近日焦點」素材 3：即將挑戰的紀錄（UX-TEAM-RECORDS1；唯讀）。

三種素材（2026-07-28 需求方定案，記於 docs/tasks/UX-TEAM-RECORDS1.md，不得自行更動）：

1. **個人生涯里程碑**（計數型）——生涯口徑一律走 `cpbl.api.routers.players` 的
   canonical helper（`_career_batting_per_year`/`_career_pitching_per_year` +
   `_sum_batting_career`/`_sum_pitching_career`），與球員頁
   `/api/v1/players/{id}/career` 同一份邏輯（該端點本身也改走這兩個 helper）。
   **嚴禁另行拼裝 `batting_seasons` ∪ gamelog**——那是卡面紅線：自行拼裝會與
   球員頁生涯數字對不起來。

   判準＝「下一場真的有機會達成」，可操作化為單一規則：**取「單場達成 ≥N」
   發生率仍 ≥5% 的最大 N**（Coordinator 2026-07-28 以 2018+ 一軍逐場資料實測，
   5% 這條線每項都切得乾淨，見卡面數字，不可為了湊整數偏離）。門檻**逐項不同**
   （`BATTER_MILESTONES`/`PITCHER_MILESTONES`，卡面表格，執行者不得逕自改動）：
   安打 3、打點 2、得分 2、全壘打 1、盜壘 1、勝投／救援中繼 1（結構上單場上限）；
   三振／局數見下方角色分流。排序＝「差距／階梯」比值由小到大（越接近越前面）。

   **三振／局數投手角色分流**（2026-07-28 需求方追加）：只有這兩項的單場分布
   隨角色差一個數量級（先發 vs 後援），其餘計數型與角色無關。判定用本季一軍
   `pitching_gamelog.role_type='先發'` 場次佔比：≥0.5 → 先發門檻（三振 8／局數 7）；
   其餘（含混合型與本季出賽 <5 場者）→ 後援門檻（三振 2／局數 2）——樣本不足
   一律歸後援是刻意的保守方向：後援門檻低 ⇒ 上榜少 ⇒ 不會對「今晚可能達成」
   做出兌現不了的宣稱（見 `_pitcher_role`）。

2. **進行中連續安打**——直接呼叫 `cpbl.api.team_focus._current_hit_streak`
   （UX-TEAM-FOCUS2 已上線，kind_code='A' 一軍口徑），不重寫。`STREAK_MIN`/
   `STREAK_TOP_N` 是本卡新增（卡面只要求複用計算本身，未定義呈現門檻/上限）——
   執行者提案 5 場起算、至多列 5 位，理由：避免每隊塞滿 0~2 場的雜訊，5 場
   在中職語境已算「連續安打」值得關注的長度。

3. **隊史紀錄逼近（僅計數型）**——franchise 範圍**限定 `*_seasons`（1990+），
   刻意不併入本季 gamelog**。這與素材 1「生涯」數字不同義：素材 1 問的是
   「這位球員全生涯（含本季）累積多少」，素材 3 問的是「這位球員在**這支球隊
   歷史上**排名如何、離隊史紀錄還差多少」——卡面背景表格明載這裡的資料源只到
   `*_seasons`，代表本季（gamelog 尚未併入 `*_seasons`）的貢獻要等年度資料
   落表後才會反映在隊史榜上，這是已知的更新延遲、不是缺陷，需在前端文案上
   避免誤導（不宣稱「即時」）。**連續型隊史紀錄（最長連續安打/無失分等）不做**
   ——需求方 2026-07-28 裁定，逐場資料僅 2018+ 會讓口徑半殘，任何「近年最佳」
   變體措辭也不得出現，本模組完全不產生這類欄位。
   門檻與判準沿用素材 1 同一組 `near`/`ladder`（卡面 2026-07-28 明定「隊史逼近
   沿用同一組門檻與同一個判準，不要留兩套門檻」）——三振／局數的隊史逼近也要
   套用同一位球員本季的角色分流門檻，不是另用固定值。

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

# 里程碑階梯與門檻（卡面表格 2026-07-28 定版，勿逕自改動數值；label/stat 對齊
# canonical 生涯欄位）。near＝「取單場達成 ≥N 發生率仍 ≥5% 的最大 N」的實測結果
# （2018+ 一軍逐場資料），不是階梯比例、也不是「單場上限」的粗略估計——勝投／
# 救援中繼剛好兩者相符（結構上單場上限即 1），其餘各項不相符（如三振單場遠
# 不只 3 次，但「達到差 8」這件事仍要看發生率，不是看上限）。
BATTER_MILESTONES = [
    {"stat": "h", "label": "安打", "ladder": 100, "start": 200, "near": 3},
    {"stat": "rbi", "label": "打點", "ladder": 100, "start": 200, "near": 2},
    {"stat": "r", "label": "得分", "ladder": 100, "start": 200, "near": 2},
    {"stat": "hr", "label": "全壘打", "ladder": 25, "start": 25, "near": 1},
    {"stat": "sb", "label": "盜壘", "ladder": 25, "start": 25, "near": 1},
]

# 三振／局數的 near 隨投手本季角色（先發／後援）而異，見 PITCHER_ROLE_NEAR +
# _pitcher_role。這裡的 near 只是「後援」（保守方向）的預設值，供角色查詢失敗
# 或呼叫端未解析角色時的 fallback；實際判斷一律走 near_by_player 覆寫。
PITCHER_MILESTONES = [
    {"stat": "so", "label": "三振", "ladder": 100, "start": 200, "near": 2},
    {"stat": "ip", "label": "投球局數", "ladder": 100, "start": 200, "near": 2},
    {"stat": "w", "label": "勝投", "ladder": 10, "start": 20, "near": 1},
    {"stat": "sv_hld", "label": "救援／中繼", "ladder": 25, "start": 25, "near": 1},
]
PITCHER_ROLE_NEAR = {
    "so": {"starter": 8, "reliever": 2},
    "ip": {"starter": 7, "reliever": 2},
}
ROLE_SPLIT_STATS = frozenset(PITCHER_ROLE_NEAR)
# 角色判定：本季出賽 <5 場者樣本不足，一律歸後援（保守方向，見 `_pitcher_role`）。
ROLE_MIN_GAMES = 5
ROLE_STARTER_RATIO = 0.5

STREAK_MIN = 5
STREAK_TOP_N = 5


def _next_milestone(current: int, ladder: int, start: int) -> tuple[int, int]:
    """回傳（下一個里程碑, 差距）。里程碑＝大於現值、且 ≥ 起始門檻的最小階梯倍數。"""
    candidate = ((current // ladder) + 1) * ladder
    if candidate < start:
        candidate = start
    return candidate, candidate - current


def _classify_pitcher_role(starts: int, total: int) -> str:
    """本季一軍先發場次佔比 ≥0.5 → 'starter'；其餘（含混合型與出賽 <5 場者，
    樣本不足時保守歸類）→ 'reliever'。純函式（不含 DB 查詢），只影響三振／局數
    兩項門檻；`total>=ROLE_MIN_GAMES` 在 `and` 左側短路，`total=0` 不會除以零。"""
    if total >= ROLE_MIN_GAMES and starts / total >= ROLE_STARTER_RATIO:
        return "starter"
    return "reliever"


def _pitcher_role(cur, pitcher_id: str, season: int) -> str:
    cur.execute(
        "SELECT count(*) FILTER (WHERE role_type='先發'), count(*) "
        "FROM cpbl.pitching_gamelog WHERE pitcher_acnt=%s AND year=%s AND kind_code='A'",
        (pitcher_id, season))
    starts, total = cur.fetchone()
    return _classify_pitcher_role(starts or 0, total or 0)


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


def _pitcher_near_by_player(cur, roster: list[dict], season: int) -> dict[str, dict[str, int]]:
    """每位投手本季角色（先發／後援）解析後的三振／局數 near 覆寫表。"""
    out: dict[str, dict[str, int]] = {}
    for pl in roster:
        role = _pitcher_role(cur, pl["player_id"], season)
        out[pl["player_id"]] = {stat: PITCHER_ROLE_NEAR[stat][role] for stat in ROLE_SPLIT_STATS}
    return out


def _pitcher_milestones(
    cur, roster: list[dict], near_by_player: dict[str, dict[str, int]],
) -> list[dict]:
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
        near_override = near_by_player.get(pl["player_id"], {})
        for m in PITCHER_MILESTONES:
            current = values[m["stat"]]
            near = near_override.get(m["stat"], m["near"])
            milestone, gap = _next_milestone(current, m["ladder"], m["start"])
            if 0 < gap <= near:
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
    near_by_player: dict[str, dict[str, int]] | None = None,
) -> list[dict]:
    """roster 中 franchise-scoped 總和逼近隊史紀錄（最大值）者。已是唯一持有人不算逼近。

    `near_by_player`：投手三振／局數的 near 隨球員本季角色而異（見模組 docstring），
    有提供時該球員該項目優先用它覆寫 `stat_defs` 裡的固定 near；打者與其餘投手
    項目不傳（沿用 `stat_defs` 的固定值），維持單一判準、不留第二套。
    """
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
            near = m["near"]
            if near_by_player is not None:
                near = near_by_player.get(pl["player_id"], {}).get(stat, near)
            if 0 < gap <= near:
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
        pitcher_near = _pitcher_near_by_player(cur, pitchers_roster, season)

        milestones = (
            _batter_milestones(cur, batters_roster)
            + _pitcher_milestones(cur, pitchers_roster, pitcher_near)
        )
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
            + _franchise_approach(pitchers_roster, franchise_pitchers, PITCHER_MILESTONES, "pitching",
                                  near_by_player=pitcher_near)
        )
        franchise_records.sort(key=lambda x: x["ratio"])

    return {
        "season": season,
        "milestones": milestones,
        "streaks": streaks,
        "franchise_records": franchise_records,
    }
