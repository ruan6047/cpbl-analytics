"""賽果預測特徵工程（leakage-safe）。

逐場依日期順序處理，維護每隊 running state（季內勝率、近10場、得失分、對戰史）。
每場特徵在「套用該場結果之前」計算 → 嚴格只用過去資訊，無資料洩漏。

completed 判定：home_score + away_score > 0（未開打的場次比分為 0-0）。
先發投手 ERA 用「前一季」pitching_seasons 的 ERA（無前季資料 → 聯盟均值）。
"""

from __future__ import annotations

import logging
from collections import defaultdict, deque

from cpbl.db import conn

log = logging.getLogger("cpbl.features.outcome")

# 候選特徵（順序固定；frontend / 模型依此 key 取用）
# 每項皆「主隊相對客隊」；場均得分/失分拆開，方便在對戰卡上分別檢視。
CANDIDATE_FEATURES = [
    ("winrate_diff", "季內勝率"),
    ("prior_winpct_diff", "上季戰力"),
    ("runs_scored_diff", "場均得分"),
    ("runs_allowed_diff", "場均失分（防禦）"),
    ("recent_form_diff", "近10場戰績"),
    ("rest_days_diff", "休息天數"),
    ("h2h_home", "對戰勝率"),
    ("starter_era_diff", "先發投手ERA"),
    ("starter_whip_diff", "先發投手WHIP"),
    ("starter_k9_diff", "先發投手K9"),
    ("home_field", "主場優勢"),
]
FEATURE_KEYS = [k for k, _ in CANDIDATE_FEATURES]
FEATURE_LABELS = dict(CANDIDATE_FEATURES)
REAL_FEATURES_LABELS = {k: v for k, v in CANDIDATE_FEATURES if k != "home_field"}

# 滑鼠移過去的參數說明（前端 tooltip）。皆以「本季」為準。
FEATURE_DESC = {
    "winrate_diff": "本季至今的勝率（勝÷出賽）。整體實力的基準指標。",
    "prior_winpct_diff": "上季最終勝率對比。季初本季樣本少時提供穩定的戰力先驗（無上季資料以五成計）。",
    "runs_scored_diff": "本季場均得分，衡量打線火力。",
    "runs_allowed_diff": "本季場均失分，越低代表投手與守備越強（即防禦力）。",
    "recent_form_diff": "最近 10 場勝率，反映近期手感。屬弱訊號，預設權重低。",
    "rest_days_diff": "距上一場的休息天數對比。較多休息＝先發輪值充裕、體能較佳（季內首戰視為持平）。",
    "h2h_home": "本季兩隊交手中主隊的勝率（雙方主客場都計入）。未交手則視為五五波。",
    "starter_era_diff": "本場先發投手的本季防禦率對比，越低越強。未達合格投手則以聯盟平均墊檔。",
    "starter_whip_diff": "先發投手每局被上壘率（WHIP），越低越強。衡量壓制力。",
    "starter_k9_diff": "先發投手每 9 局奪三振數（K9），越高越強。衡量三振能力。",
    "home_field": "主場球隊的基準勝率優勢（約 +5%）。以模型 intercept 表示。",
}


def _prior_era() -> tuple[dict[tuple[str, int], float], float]:
    """{(player_id, year): 該季 ERA}；以及聯盟平均 ERA。
    2023-2024 由 opendata pitching_seasons 計算（全投手）；2025+ 由本季爬蟲
    pitching_current 覆蓋（含進階數據，但僅合格投手）。"""
    era: dict[tuple[str, int], float] = {}
    with conn() as c:
        cur = c.cursor()
        cur.execute("SELECT player_id, year, er, ip FROM cpbl.pitching_seasons WHERE ip > 0 AND er IS NOT NULL")
        for pid, year, er, ip in cur.fetchall():
            ipf = float(ip)
            if ipf > 0:
                era[(pid, year)] = er * 9.0 / ipf
        cur.execute("SELECT player_id, year, era FROM cpbl.pitching_current WHERE era IS NOT NULL")
        for pid, year, e in cur.fetchall():
            era[(pid, year)] = float(e)
    vals = list(era.values())
    return era, (sum(vals) / len(vals) if vals else 4.0)


def _pitcher_adv() -> tuple[dict, dict, float, float]:
    """{(pid,year): WHIP}、{(pid,year): K9} 與兩者聯盟平均。
    2023-24 由 opendata 計算（WHIP=(BB+H)/IP, K9=SO*9/IP），2025+ 由 pitching_current。"""
    whip: dict[tuple[str, int], float] = {}
    k9: dict[tuple[str, int], float] = {}
    with conn() as c:
        cur = c.cursor()
        cur.execute("SELECT player_id, year, bb, h, so, ip FROM cpbl.pitching_seasons WHERE ip > 0")
        for pid, year, bb, h, so, ip in cur.fetchall():
            ipf = float(ip)
            if ipf > 0:
                whip[(pid, year)] = ((bb or 0) + (h or 0)) / ipf
                k9[(pid, year)] = (so or 0) * 9.0 / ipf
        cur.execute("SELECT player_id, year, whip, k9 FROM cpbl.pitching_current WHERE whip IS NOT NULL")
        for pid, year, w, k in cur.fetchall():
            whip[(pid, year)] = float(w)
            if k is not None:
                k9[(pid, year)] = float(k)
    lw = sum(whip.values()) / len(whip) if whip else 1.3
    lk = sum(k9.values()) / len(k9) if k9 else 7.0
    return whip, k9, lw, lk


def _prior_winpct() -> dict[tuple[int, str], float]:
    """{(season, team_code): 上季最終勝率}。由 games（一軍例行賽）逐季彙總，
    供季初冷啟動的戰力先驗。無上季資料的 key 由呼叫端 fallback 0.5。"""
    wl: dict[tuple[int, str], list[int]] = defaultdict(lambda: [0, 0])
    with conn() as c:
        cur = c.cursor()
        cur.execute(
            """
            SELECT year, home_team_code, away_team_code, home_score, away_score
            FROM cpbl.games
            WHERE kind_code = 'A' AND home_score + away_score > 0
            """
        )
        for year, hc, ac, hs, as_ in cur.fetchall():
            if hs > as_:
                wl[(year, hc)][0] += 1; wl[(year, ac)][1] += 1
            elif hs < as_:
                wl[(year, hc)][1] += 1; wl[(year, ac)][0] += 1
    # 轉成「下一季可查」：key=(season, team) 存放 season-1 的勝率
    prior: dict[tuple[int, str], float] = {}
    for (year, team), (w, l) in wl.items():
        if w + l > 0:
            prior[(year + 1, team)] = w / (w + l)
    return prior


def build_game_features() -> list[dict]:
    era, lg_era = _prior_era()
    whip, k9, lg_whip, lg_k9 = _pitcher_adv()
    prior_wp = _prior_winpct()

    with conn() as c:
        cur = c.cursor()
        # 只取一軍例行賽（kind A）：季內 running state 才一致；排除二軍(D)/季後(C,E)，
        # 否則混入不同層級會汙染勝率/交手/休息天數等狀態。
        cur.execute(
            """
            SELECT year, kind_code, game_season_code, game_sno, game_date,
                   home_team_code, home_team_name, away_team_code, away_team_name,
                   home_score, away_score, home_starter_id, away_starter_id
            FROM cpbl.games
            WHERE game_date IS NOT NULL AND kind_code = 'A'
            ORDER BY game_date, game_sno
            """
        )
        games = cur.fetchall()

    wl: dict[str, list[int]] = defaultdict(lambda: [0, 0])          # team -> [W, L] 季內
    rfra: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])     # team -> [得分, 失分, 場數]
    last10: dict[str, deque] = defaultdict(lambda: deque(maxlen=10))
    # 本季雙向交手：frozenset({A,B}) -> {team: 勝場}。每季歸零、不分主客。
    h2h: dict[frozenset, dict[str, int]] = defaultdict(dict)
    last_game: dict[str, object] = {}  # team -> 上一場日期（季內；算休息天數）
    cur_season: int | None = None

    def rest_days(t: str, d) -> float:
        """距上一場的休息天數（季內首戰 → None 由呼叫端視為持平）。上限 7 天，
        避免明星賽/雨延等長假產生離群值主導標準化。"""
        prev = last_game.get(t)
        return min((d - prev).days, 7) if prev is not None else None

    def winrate(t: str) -> float:
        w, l = wl[t]
        return w / (w + l) if (w + l) > 0 else 0.5

    def form(t: str) -> float:
        d = last10[t]
        return sum(d) / len(d) if d else 0.5

    def rs_pg(t: str) -> float:
        rf, _ra, n = rfra[t]
        return rf / n if n > 0 else 0.0

    def ra_pg(t: str) -> float:
        _rf, ra, n = rfra[t]
        return ra / n if n > 0 else 0.0

    rows: list[dict] = []
    for g in games:
        (year, kind, scode, sno, date, home, hname, away, aname,
         hs, as_, hsp, asp) = g

        if cur_season != year:  # 新球季：所有季內統計（含交手史/休息天數）歸零
            cur_season = year
            wl.clear(); rfra.clear(); last10.clear(); h2h.clear(); last_game.clear()

        rec = h2h[frozenset((home, away))]
        hw, aw = rec.get(home, 0), rec.get(away, 0)
        # 休息天數差：任一隊季內首戰（None）→ 視為持平 0。
        hr, ar = rest_days(home, date), rest_days(away, date)
        rest_diff = 0.0 if (hr is None or ar is None) else float(hr - ar)
        # 上季戰力差：無上季資料（新隊/首季）→ 0.5 中性。
        prior_diff = prior_wp.get((year, home), 0.5) - prior_wp.get((year, away), 0.5)
        feats = {
            "winrate_diff": winrate(home) - winrate(away),
            "prior_winpct_diff": prior_diff,
            "runs_scored_diff": rs_pg(home) - rs_pg(away),
            "runs_allowed_diff": ra_pg(home) - ra_pg(away),
            "recent_form_diff": form(home) - form(away),
            "rest_days_diff": rest_diff,
            "h2h_home": (hw / (hw + aw)) if (hw + aw) > 0 else 0.5,
            "home_field": 1.0,
            # 本季先發投手（主-客）；ERA/WHIP 越低越好（定向取負），K9 越高越好。
            "starter_era_diff": era.get((hsp, year), lg_era) - era.get((asp, year), lg_era),
            "starter_whip_diff": whip.get((hsp, year), lg_whip) - whip.get((asp, year), lg_whip),
            "starter_k9_diff": k9.get((hsp, year), lg_k9) - k9.get((asp, year), lg_k9),
        }

        completed = hs is not None and as_ is not None and (hs + as_) > 0
        home_win = None
        if completed:
            home_win = 1 if hs > as_ else (0 if hs < as_ else None)

        rows.append({
            "year": year, "kind_code": kind, "game_season_code": scode, "game_sno": sno,
            "game_date": date, "season": year,
            "home_team_code": home, "away_team_code": away,
            "home_team_name": hname, "away_team_name": aname,
            "home_win": home_win, "completed": completed, **feats,
        })

        # 休息天數依賽程推進（不論勝負/是否開打），下一場才有正確間隔。
        last_game[home] = date; last_game[away] = date

        if completed:  # 套用結果更新 state（在計算特徵「之後」）
            rfra[home][0] += hs; rfra[home][1] += as_; rfra[home][2] += 1
            rfra[away][0] += as_; rfra[away][1] += hs; rfra[away][2] += 1
            if hs > as_:
                wl[home][0] += 1; wl[away][1] += 1
                last10[home].append(1); last10[away].append(0)
                rec[home] = rec.get(home, 0) + 1
            elif hs < as_:
                wl[home][1] += 1; wl[away][0] += 1
                last10[home].append(0); last10[away].append(1)
                rec[away] = rec.get(away, 0) + 1

    return rows


def materialize() -> int:
    rows = build_game_features()
    records = [
        (r["year"], r["kind_code"], r["game_season_code"], r["game_sno"], r["game_date"], r["season"],
         r["home_team_code"], r["away_team_code"], r["home_team_name"], r["away_team_name"],
         r["home_win"], r["completed"],
         r["winrate_diff"], r["runs_scored_diff"], r["runs_allowed_diff"],
         r["recent_form_diff"], r["h2h_home"], r["home_field"], r["starter_era_diff"],
         r["starter_whip_diff"], r["starter_k9_diff"],
         r["prior_winpct_diff"], r["rest_days_diff"])
        for r in rows
    ]
    with conn() as c:
        # 全史重建：清掉舊資料（含早期未過濾 kind 而混入的二軍/季後場次），避免汙染訓練查詢。
        c.cursor().execute("TRUNCATE cpbl.game_features")
        c.cursor().executemany(
            """
            INSERT INTO cpbl.game_features
                (year, kind_code, game_season_code, game_sno, game_date, season,
                 home_team_code, away_team_code, home_team_name, away_team_name,
                 home_win, completed,
                 winrate_diff, runs_scored_diff, runs_allowed_diff,
                 recent_form_diff, h2h_home, home_field, starter_era_diff,
                 starter_whip_diff, starter_k9_diff,
                 prior_winpct_diff, rest_days_diff)
            VALUES (%s,%s,%s,%s,%s,%s, %s,%s,%s,%s, %s,%s, %s,%s,%s,%s,%s,%s,%s,%s,%s, %s,%s)
            ON CONFLICT (year, kind_code, game_season_code, game_sno) DO UPDATE SET
                game_date=EXCLUDED.game_date, season=EXCLUDED.season,
                home_team_name=EXCLUDED.home_team_name, away_team_name=EXCLUDED.away_team_name,
                home_win=EXCLUDED.home_win, completed=EXCLUDED.completed,
                winrate_diff=EXCLUDED.winrate_diff,
                runs_scored_diff=EXCLUDED.runs_scored_diff,
                runs_allowed_diff=EXCLUDED.runs_allowed_diff,
                recent_form_diff=EXCLUDED.recent_form_diff, h2h_home=EXCLUDED.h2h_home,
                home_field=EXCLUDED.home_field, starter_era_diff=EXCLUDED.starter_era_diff,
                starter_whip_diff=EXCLUDED.starter_whip_diff, starter_k9_diff=EXCLUDED.starter_k9_diff,
                prior_winpct_diff=EXCLUDED.prior_winpct_diff, rest_days_diff=EXCLUDED.rest_days_diff
            """,
            records,
        )
    return len(records)
