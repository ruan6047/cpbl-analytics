"""球隊頁「近日焦點」素材 2：近期打者熱區（UX-TEAM-FOCUS2；唯讀）。

口徑（2026-07-28 需求方定案，記於 docs/tasks/UX-TEAM-FOCUS2.md，不得自行更動）：

- v1 只做打者熱區。投手「近 7 天」在先發／後援之間不可比（先發 1 場 6 局 vs
  後援 3 場 3 局，同一排序軸會誤導），投手熱區另列 v1.1。
- 窗口＝近 7 個日曆天，以該隊「本季最後一場完賽日」回推（非以今日回推——
  季中休兵日不應清空區塊）；完賽判定沿用 completed-game-judgment 慣例
  （score>0 且 game_date<=CURRENT_DATE，排除因雨延賽保留但尚未真正開打的列）。
- 門檻＝窗口內 PA >= 10；不足門檻者不進榜，不得為湊數放寬。
- 排序＝窗口內 OPS 由高至低取前 3（2026-07-28 需求方看畫面後回饋，由原提案 5 收斂為 3；
  `TOP_N` 為唯一數量來源）；OPS 公式與 `_team_scoped_metrics`
  （standings.py）同一口徑：OBP=(H+BB+HBP)/(AB+BB+HBP+SF)、SLG=TB/AB。
- 每列同時標示「現行中的」連續安打場次（不是歷史最長）：由該球員本季（不限
  7 日窗口）最近一場往前數，H>0 記一場、AB>0 且 H=0 中止，AB=0（如保送/觸身
  球等無打數的場次）不計入也不中止（沿用一般連續安打慣例）。
- 每列必須顯示窗口內 PA 數，樣本極小是事實不是缺陷。

`available=False`＝本季尚無完賽（球季未開打／已結束前的空窗），前端應明示
「本季尚無完賽」而非空表格；`available=True` 但 `items=[]`＝視窗存在但無人
達 PA 門檻，前端須用不同文案（不得共用同一句話，避免混淆兩種退化成因）。
"""

from __future__ import annotations

from datetime import date, timedelta

from cpbl.db import conn

MIN_PA = 10
WINDOW_DAYS = 7
TOP_N = 3

_TEAM_CODE_EXPR = "CASE bg.visiting_home_type WHEN '2' THEN g.home_team_code ELSE g.away_team_code END"


def _last_completed_game_date(cur, code: str, season: int) -> date | None:
    cur.execute(
        "SELECT max(game_date) FROM cpbl.games "
        "WHERE year=%s AND kind_code='A' AND home_score+away_score>0 AND game_date<=CURRENT_DATE "
        "AND (home_team_code=%s OR away_team_code=%s)",
        (season, code, code),
    )
    row = cur.fetchone()
    return row[0] if row else None


def _current_hit_streak(cur, code: str, season: int, hitter_acnt: str) -> int:
    """由最近一場完賽（本季、該隊）往前數的現行連續安打場次。"""
    cur.execute(
        "SELECT bg.at_bats, bg.hits FROM cpbl.batting_gamelog bg "
        "JOIN cpbl.games g ON g.year=bg.year AND g.kind_code=bg.kind_code AND g.game_sno=bg.game_sno "
        "WHERE bg.year=%s AND bg.kind_code='A' AND bg.hitter_acnt=%s "
        f"AND g.home_score+g.away_score>0 AND g.game_date<=CURRENT_DATE AND {_TEAM_CODE_EXPR}=%s "
        "ORDER BY g.game_date DESC, g.game_sno DESC",
        (season, hitter_acnt, code),
    )
    streak = 0
    for ab, h in cur.fetchall():
        ab = int(ab or 0)
        h = int(h or 0)
        if h > 0:
            streak += 1
        elif ab > 0:
            break
        # ab==0 且 h==0（如保送/觸身球無打數）：不計入也不中止，跳過該場
    return streak


def hot_batters(code: str, season: int) -> dict:
    """球隊頁「近期球員熱區」（打者）：近 7 日窗口 OPS 前 TOP_N（PA>=10），附現行連續安打。"""
    with conn() as c:
        cur = c.cursor()
        last_date = _last_completed_game_date(cur, code, season)
        if last_date is None:
            return {"season": season, "available": False, "window": None, "items": []}

        window_start = last_date - timedelta(days=WINDOW_DAYS - 1)
        cur.execute(
            "SELECT bg.hitter_acnt, "
            "(array_agg(bg.hitter_name ORDER BY g.game_date DESC))[1] AS name, "
            "sum(bg.plate_appearances) AS pa, sum(bg.at_bats) AS ab, sum(bg.hits) AS h, "
            "sum(bg.total_bases) AS tb, sum(bg.bb) AS bb, sum(bg.hbp) AS hbp, sum(bg.sac_fly) AS sf "
            "FROM cpbl.batting_gamelog bg "
            "JOIN cpbl.games g ON g.year=bg.year AND g.kind_code=bg.kind_code AND g.game_sno=bg.game_sno "
            "WHERE bg.year=%s AND bg.kind_code='A' "
            "AND g.game_date BETWEEN %s AND %s "
            "AND g.home_score+g.away_score>0 AND g.game_date<=CURRENT_DATE "
            f"AND {_TEAM_CODE_EXPR}=%s "
            "GROUP BY bg.hitter_acnt HAVING sum(bg.plate_appearances) >= %s",
            (season, window_start, last_date, code, MIN_PA),
        )
        candidates = []
        for acnt, name, pa, ab, h, tb, bb, hbp, sf in cur.fetchall():
            ab = int(ab or 0)
            if ab <= 0:
                continue
            den = ab + int(bb or 0) + int(hbp or 0) + int(sf or 0)
            obp = ((int(h or 0) + int(bb or 0) + int(hbp or 0)) / den) if den else None
            slg = int(tb or 0) / ab
            ops = round(obp + slg, 3) if obp is not None else None
            if ops is None:
                continue
            candidates.append({
                "player_id": acnt, "name": name or acnt, "pa": int(pa or 0), "ops": ops,
            })
        candidates.sort(key=lambda x: x["ops"], reverse=True)
        top = candidates[:TOP_N]
        for item in top:
            item["streak"] = _current_hit_streak(cur, code, season, item["player_id"])

        return {
            "season": season,
            "available": True,
            "window": {"start": window_start.isoformat(), "end": last_date.isoformat()},
            "items": top,
        }
