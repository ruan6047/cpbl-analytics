"""特殊戰績：從逐場 games + 逐局 game_scoreboard 即時計算（隊級）。

涵蓋（定義由使用者定調）：
- 場地：人工草皮 / 天然草皮 / 室內（venues.py 對照）。
- 先被得分：對方先得分的場次戰績。
- 戰況激烈：曾被追平（領先後回到平手）之後才分出勝負。
- 順風場：該隊比賽中曾領先 ≥3 分。
- 逆風場：該隊比賽中曾落後 ≥3 分（與順風對稱）。
- 系列賽橫掃：同對手連續 3 連戰且 3-0（僅 3 連戰）。

皆用逐場 + 逐局（覆蓋完整），不依賴有設備限制的逐球。
"""

from __future__ import annotations

from cpbl.db import conn
from cpbl.venues import is_artificial, is_indoor

LEAD_MARGIN = 3  # 順風/逆風門檻


def _trajectory_flags(events: list[tuple[int, int]]) -> dict:
    """events: 依時序的 (away_inc, home_inc) 每半局得分。回傳該場的軌跡衍生標記。

    away=客隊(visiting_home_type=1)、home=主隊(=2)。
    """
    away = home = 0
    first_scorer: str | None = None      # "away" | "home"
    ever_nonzero_lead = False            # 是否曾有人領先（非 0-0）
    tied_after_lead = False              # 領先後又回到平手
    max_away_lead = 0                    # 客隊最大領先（away-home 的最大值）
    max_home_lead = 0                    # 主隊最大領先
    for ai, hi in events:
        away += ai
        home += hi
        if first_scorer is None and (away > 0 or home > 0):
            first_scorer = "away" if away > home else "home" if home > away else None
        diff = away - home
        max_away_lead = max(max_away_lead, diff)
        max_home_lead = max(max_home_lead, -diff)
        if diff != 0:
            ever_nonzero_lead = True
        elif ever_nonzero_lead and (away > 0 or home > 0):
            tied_after_lead = True       # 曾領先後又被追平
    final_diff = away - home
    decided = final_diff != 0
    return {
        "first_scorer": first_scorer,
        "intense": tied_after_lead and decided,   # 戰況激烈：被追平後才分勝負
        "away_comeback_wind": max_away_lead,       # 客隊曾領先幅度
        "home_comeback_wind": max_home_lead,       # 主隊曾領先幅度（=客隊曾落後幅度）
    }


def _blank() -> dict:
    return {k: [0, 0] for k in (
        "artificial", "natural", "indoor", "scored_first_against", "intense", "tailwind", "headwind")}


def team_situational(season: int, kind_code: str = "A") -> dict[str, dict]:
    """回 {team_code: {各情境: [W, L]}}（不含橫掃，見 team_sweeps）。"""
    with conn() as c:
        games = c.execute(
            "SELECT game_sno, venue, home_team_code, away_team_code, home_score, away_score "
            "FROM cpbl.games WHERE year=%s AND kind_code=%s AND home_score+away_score>0",
            (season, kind_code),
        ).fetchall()
        sb = c.execute(
            "SELECT game_sno, visiting_home_type, inning_seq, COALESCE(score_cnt,0) "
            "FROM cpbl.game_scoreboard WHERE year=%s AND kind_code=%s",
            (season, kind_code),
        ).fetchall()

    # 逐場彙整逐局事件（依 inning 升序、同局先上半(客)後下半(主)）
    by_game: dict[int, list[tuple]] = {}
    for sno, vht, inn, sc in sb:
        by_game.setdefault(sno, []).append((int(inn), int(vht), int(sc)))

    out: dict[str, dict] = {}

    def rec(team: str, cat: str, win: bool) -> None:
        out.setdefault(team, _blank())[cat][0 if win else 1] += 1

    for sno, venue, hc, ac, hs, as_ in games:
        rows = sorted(by_game.get(sno, []), key=lambda r: (r[0], r[1]))
        events = [(sc if vht == 1 else 0, sc if vht == 2 else 0) for inn, vht, sc in rows]
        f = _trajectory_flags(events)
        home_win = hs > as_
        # 場地（雙方同記）
        if is_artificial(venue):
            rec(hc, "artificial", home_win); rec(ac, "artificial", not home_win)
        else:
            rec(hc, "natural", home_win); rec(ac, "natural", not home_win)
        if is_indoor(venue):
            rec(hc, "indoor", home_win); rec(ac, "indoor", not home_win)
        # 先被得分：對方先得分
        if f["first_scorer"] == "home":   # 主先得 → 客是先被得分
            rec(ac, "scored_first_against", not home_win)
        elif f["first_scorer"] == "away":
            rec(hc, "scored_first_against", home_win)
        # 戰況激烈（雙方同記）
        if f["intense"]:
            rec(hc, "intense", home_win); rec(ac, "intense", not home_win)
        # 順風（曾領先≥3）/ 逆風（曾落後≥3）
        if f["home_comeback_wind"] >= LEAD_MARGIN:
            rec(hc, "tailwind", home_win)
        if f["away_comeback_wind"] >= LEAD_MARGIN:
            rec(ac, "tailwind", not home_win)
        if f["away_comeback_wind"] >= LEAD_MARGIN:   # 主隊曾落後 = 客隊曾領先幅度
            rec(hc, "headwind", home_win)
        if f["home_comeback_wind"] >= LEAD_MARGIN:
            rec(ac, "headwind", not home_win)
    return out


def team_sweeps(season: int, kind_code: str = "A") -> dict[str, int]:
    """系列賽橫掃次數：同 (主隊,客隊) 連續 3 連戰且 3-0。回 {team_code: 主動橫掃次數}。"""
    with conn() as c:
        games = c.execute(
            "SELECT game_date, game_sno, home_team_code, away_team_code, home_score, away_score "
            "FROM cpbl.games WHERE year=%s AND kind_code=%s AND home_score+away_score>0 "
            "ORDER BY home_team_code, away_team_code, game_date, game_sno",
            (season, kind_code),
        ).fetchall()
    sweeps: dict[str, int] = {}
    # 同 (hc,ac) 連續場次分組為系列（相鄰日期間隔 ≤2 天視為同系列）
    series: list[tuple] = []
    cur: list[tuple] = []
    prev_key = None
    prev_date = None
    for gd, _sno, hc, ac, hs, as_ in games:
        key = (hc, ac)
        gap = (gd - prev_date).days if (prev_date and key == prev_key) else 99
        if key != prev_key or gap > 2:
            if cur:
                series.append((prev_key, cur))
            cur = []
        cur.append((hs, as_))
        prev_key, prev_date = key, gd
    if cur:
        series.append((prev_key, cur))
    for (hc, ac), gms in series:
        if len(gms) != 3:        # 僅 3 連戰
            continue
        if all(hs > as_ for hs, as_ in gms):
            sweeps[hc] = sweeps.get(hc, 0) + 1   # 主隊橫掃
        elif all(as_ > hs for hs, as_ in gms):
            sweeps[ac] = sweeps.get(ac, 0) + 1   # 客隊橫掃
    return sweeps
