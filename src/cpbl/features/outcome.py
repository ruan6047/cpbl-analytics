"""賽果預測特徵工程（leakage-safe）。

逐場依日期順序處理，維護每隊 running state（季內勝率、近10場、得失分、對戰史）。
每場特徵在「套用該場結果之前」計算 → 嚴格只用過去資訊，無資料洩漏。

completed 判定：走 `cpbl.completion.is_completed_game`——比分 > 0 **或**有官方完賽證據
（0:0 真和局屬後者，見 DATA-TIE-REMEDY1；未開打的場次比分同為 0-0，故不能只看比分）。

先發投手 ERA/WHIP/K9（ML-OUTCOME-LEAK1）：**賽前 as-of**。
舊版以 `(starter_id, year)` 讀同季彙總（`pitching_seasons`／`pitching_current`），
等於讓歷史回測的模型在賽前看見該投手該季之後的表現 → 前視洩漏
（實證見 `docs/research/GAME-RECAP-WP-STRENGTH1_RESULTS.md` §6.2）。現改為
`pitching_gamelog` 逐場 running state（快照賽前 state 後才套用本場計數）＋
前一季總量 prior 的部分池化收縮；fallback 順序＝前一季同口徑 → 前一季聯盟率。
"""

from __future__ import annotations

import logging
import math
from collections import defaultdict, deque
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone

from cpbl.completion import (
    completed_games_sql_with_evidence,
    is_completed_game,
)
from cpbl.db import conn

# 台北時區（DB timezone 為 UTC，完成場的「今天」須以台北日界為準）
_TAIPEI = timezone(timedelta(hours=8))

log = logging.getLogger("cpbl.features.outcome")

# 候選特徵（順序固定；frontend / 模型依此 key 取用）
# 每項皆「主隊相對客隊」；場均得分/失分拆開，方便在對戰卡上分別檢視。
CANDIDATE_FEATURES = [
    ("winrate_diff", "季內勝率"),
    ("prior_winpct_diff", "上季戰力"),
    ("runs_scored_diff", "打線得分力（場均得分）"),
    ("runs_allowed_diff", "守備失分力（場均失分）"),
    ("recent_form_diff", "近10場戰績"),
    ("rest_days_diff", "休息天數"),
    ("h2h_home", "對戰勝率"),
    ("starter_era_diff", "先發投手ERA"),
    ("starter_whip_diff", "先發投手WHIP"),
    ("starter_k9_diff", "先發投手K9"),
    ("prior_team_ops_diff", "上季團隊OPS"),
    ("prior_team_slg_diff", "上季團隊長打率"),
    ("prior_team_era_diff", "上季團隊ERA"),
    ("prior_team_whip_diff", "上季團隊WHIP"),
    ("team_ops_now_diff", "當季團隊OPS"),
    ("team_avg_now_diff", "當季團隊打擊率"),
    ("team_sb_now_diff", "當季淨盜壘/場"),
    ("team_wp_now_diff", "當季暴投/場"),
    ("team_err_now_diff", "當季失誤/場"),
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
    "starter_era_diff": "本場先發投手「開打前」的本季至今防禦率對比，越低越強。"
                        "季初樣本少時以上季成績（再無則上季聯盟平均）按比例收縮墊檔。",
    "starter_whip_diff": "先發投手開打前的本季至今每局被上壘率（WHIP），越低越強。"
                         "衡量壓制力；收縮方式同 ERA。",
    "starter_k9_diff": "先發投手開打前的本季至今每 9 局奪三振數（K9），越高越強。"
                       "衡量三振能力；收縮方式同 ERA。",
    "home_field": "主場球隊的基準勝率優勢（約 +5%）。以模型 intercept 表示。",
    "prior_team_ops_diff": "上季團隊整體攻擊 OPS 對比（全史可算）。衡量打線基底實力。",
    "prior_team_slg_diff": "上季團隊長打率 SLG 對比。衡量長打火力基底。",
    "prior_team_era_diff": "上季團隊防禦率 ERA 對比，越低越強。衡量投手戰力基底。",
    "prior_team_whip_diff": "上季團隊 WHIP 對比，越低越強。衡量壓制力基底。",
    "team_ops_now_diff": "本季至今團隊整體攻擊 OPS 對比（即時打線狀態）。僅 2018 年起有逐打席資料。",
    "team_avg_now_diff": "本季至今團隊打擊率對比（即時手感）。僅 2018 年起有逐打席資料。",
    "team_sb_now_diff": "本季至今每場淨盜壘（盜壘成功−失敗）對比，衡量壘間積極度。僅 2018 年起有。",
    "team_wp_now_diff": "本季至今投手群每場暴投數對比，越少越穩（控球/守成）。僅 2018 年起有。",
    "team_err_now_diff": "本季至今每場失誤數對比，越少守備越穩。僅 2018 年起有。",
}

# 顯示群組（前端依此分區呈現）。
FEATURE_GROUP = {
    "winrate_diff": "整體實力", "prior_winpct_diff": "整體實力", "recent_form_diff": "整體實力",
    "runs_scored_diff": "打擊表現", "prior_team_ops_diff": "打擊表現", "prior_team_slg_diff": "打擊表現",
    "team_ops_now_diff": "打擊表現", "team_avg_now_diff": "打擊表現",
    "team_sb_now_diff": "壘間",
    "runs_allowed_diff": "守備／失分", "team_err_now_diff": "守備／失分", "team_wp_now_diff": "守備／失分",
    "starter_era_diff": "先發投手", "starter_whip_diff": "先發投手", "starter_k9_diff": "先發投手",
    "prior_team_era_diff": "團隊投手", "prior_team_whip_diff": "團隊投手",
    "h2h_home": "對戰記錄", "rest_days_diff": "場地／賽事因數", "home_field": "場地／賽事因數",
}
# 相依（共線）群組：同 id 的特徵彼此高度相關，前端選了多個會軟提醒（仍可選，聯合 fit 自動分攤）。
FEATURE_CORR = {
    "starter_era_diff": "先發壓制", "starter_whip_diff": "先發壓制", "starter_k9_diff": "先發壓制",
    "winrate_diff": "整體戰力", "prior_winpct_diff": "整體戰力", "recent_form_diff": "整體戰力",
    "runs_scored_diff": "打線火力", "prior_team_ops_diff": "打線火力", "prior_team_slg_diff": "打線火力",
    "team_ops_now_diff": "打線火力", "team_avg_now_diff": "打線火力",
    "runs_allowed_diff": "投手戰力", "prior_team_era_diff": "投手戰力", "prior_team_whip_diff": "投手戰力",
}


# ── 先發投手賽前指標（as-of running state + 前一季 prior 收縮）─────────────
# 收縮強度（IP 當量），約 5 場先發的投球局數。**開跑前釘死的常數**：不因回測
# 數字調整（統計紅線——不得為了數字好看而調參）。當季分母增加 → prior 自然退位。
STARTER_KAPPA_IP = 30.0
# 全史最早一季（無前一季可退）時的最終墊檔；量級取 CPBL 長期水準。
_LG_DEFAULT_ER_IP, _LG_DEFAULT_WHIP, _LG_DEFAULT_SO_IP = 4.2 / 9.0, 1.40, 6.5 / 9.0


@dataclass
class _PitchCounts:
    """逐場可加總的投球原始計數；rate 一律由此推導，不存半成品比率。"""

    er: float = 0.0
    h: float = 0.0
    bb: float = 0.0
    so: float = 0.0
    ip: float = 0.0

    def add(self, o: _PitchCounts) -> None:
        self.er += o.er; self.h += o.h; self.bb += o.bb; self.so += o.so; self.ip += o.ip

    def frozen(self) -> _PitchCounts:
        return replace(self)


_ZERO_COUNTS = _PitchCounts()


def _ip_decimal(ip) -> float:
    """`pitching_seasons.ip` 是棒球記法（.1 = 1/3 局、.2 = 2/3 局）→ 轉真實局數。
    舊版 `_prior_era` 直接把 .1 當 0.1 相除，是一併修掉的既有誤差。"""
    if ip is None:
        return 0.0
    v = float(ip)
    whole = math.floor(v)
    return whole + (v - whole) * 10.0 / 3.0


def _starter_game_counts() -> dict[tuple[int, int], dict[str, _PitchCounts]]:
    """{(year, game_sno): {pitcher_id: 該場計數}}（一軍例行賽；僅 2018+ 有逐場 box）。
    供逐場 running state 累積。"""
    out: dict[tuple[int, int], dict[str, _PitchCounts]] = {}
    with conn() as c:
        cur = c.cursor()
        cur.execute(
            "SELECT year, game_sno, pitcher_acnt, earned_runs, hits, bb, so, "
            "       inning_pitched_cnt, inning_pitched_div3 "
            "FROM cpbl.pitching_gamelog WHERE kind_code = 'A'")
        for y, sno, pid, er, h, bb, so, ipc, ipd in cur.fetchall():
            out.setdefault((y, sno), {})[pid] = _PitchCounts(
                er=float(er or 0), h=float(h or 0), bb=float(bb or 0), so=float(so or 0),
                ip=float(ipc or 0) + float(ipd or 0) / 3.0)
    return out


def _pitcher_season_totals(
    game_counts: dict[tuple[int, int], dict[str, _PitchCounts]],
) -> dict[tuple[int, str], _PitchCounts]:
    """{(year, pid): 該季總量}，供「下一季」當 prior。

    2018+ 直接由逐場 gamelog 彙總（與 running state 同口徑）；更早年份退
    `pitching_seasons`（1990+，逐年彙總）。**只會被以 `year - 1` 查詢**，故對
    目標場次而言恆為已完結的過去資訊。"""
    totals: dict[tuple[int, str], _PitchCounts] = defaultdict(_PitchCounts)
    with conn() as c:
        cur = c.cursor()
        cur.execute("SELECT player_id, year, er, h, bb, so, ip FROM cpbl.pitching_seasons WHERE ip > 0")
        for pid, year, er, h, bb, so, ip in cur.fetchall():
            # 同年多隊會有多列（PK 含 team_id）→ 累加。
            totals[(year, pid)].add(_PitchCounts(
                er=float(er or 0), h=float(h or 0), bb=float(bb or 0), so=float(so or 0),
                ip=_ip_decimal(ip)))
    gamelog_years: set[int] = set()
    from_gamelog: dict[tuple[int, str], _PitchCounts] = defaultdict(_PitchCounts)
    for (year, _sno), per_pitcher in game_counts.items():
        gamelog_years.add(year)
        for pid, c_ in per_pitcher.items():
            from_gamelog[(year, pid)].add(c_)
    for key in list(totals):
        if key[0] in gamelog_years:
            del totals[key]
    totals.update(from_gamelog)
    return dict(totals)


def _league_pitch_rates(
    totals: dict[tuple[int, str], _PitchCounts],
) -> dict[int, tuple[float, float, float]]:
    """{year: (ER/IP, WHIP, SO/IP)} 全聯盟。呼叫端一律取 `year - 1` 當 fallback，
    因此不含目標季任何資訊。"""
    agg: dict[int, _PitchCounts] = defaultdict(_PitchCounts)
    for (year, _pid), c_ in totals.items():
        agg[year].add(c_)
    return {y: (t.er / t.ip, (t.h + t.bb) / t.ip, t.so / t.ip)
            for y, t in agg.items() if t.ip > 0}


def _shrink(num: float, den: float, prior_rate: float, kappa: float) -> float:
    """部分池化：(當季累計分子 + kappa × prior 率) / (當季累計分母 + kappa)。
    當季分母為 0（季初／無逐場資料的年份）時恰好退回 prior 率。"""
    return (num + kappa * prior_rate) / (den + kappa)


def _starter_rates(own: _PitchCounts, prior: _PitchCounts | None,
                   lg: tuple[float, float, float]) -> tuple[float, float, float]:
    """(ERA, WHIP, K9)：賽前 as-of 累計以「前一季同口徑」收縮；無前一季 → 前一季聯盟率。

    兩層部分池化：前一季率本身先向前一季聯盟率收縮，再當本季 running state 的 prior。
    少了這層，只投 1-2 局的前一季紀錄會產生 ±50 的 ERA 離群值主導標準化
    （這是分布穩定性的結構決策，與回測數字無關；kappa 仍是釘死的常數）。
    """
    lg_er_ip, lg_whip, lg_so_ip = lg
    k = STARTER_KAPPA_IP
    p_ip = prior.ip if prior is not None else 0.0
    p_er = _shrink(prior.er if prior else 0.0, p_ip, lg_er_ip, k)
    p_whip = _shrink((prior.h + prior.bb) if prior else 0.0, p_ip, lg_whip, k)
    p_so = _shrink(prior.so if prior else 0.0, p_ip, lg_so_ip, k)
    return (
        9.0 * _shrink(own.er, own.ip, p_er, k),
        _shrink(own.h + own.bb, own.ip, p_whip, k),
        9.0 * _shrink(own.so, own.ip, p_so, k),
    )


def _prior_winpct() -> dict[tuple[int, str], float]:
    """{(season, team_code): 上季最終勝率}。由 games（一軍例行賽）逐季彙總，
    供季初冷啟動的戰力先驗。無上季資料的 key 由呼叫端 fallback 0.5。"""
    wl: dict[tuple[int, str], list[int]] = defaultdict(lambda: [0, 0])
    with conn() as c:
        cur = c.cursor()
        cur.execute(
            f"""
            SELECT year, home_team_code, away_team_code, home_score, away_score
            FROM cpbl.games
            WHERE kind_code = 'A' AND {completed_games_sql_with_evidence('games')}
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


def _prior_team_stats() -> dict[tuple[int, str], dict]:
    """{(season, team_code): 上季團隊 OPS/SLG/ERA/WHIP}。由 *_seasons 逐季彙總、存於 (year+1, team)，
    供冷啟動的打線/投手戰力先驗。team_id 與 games 同碼（同 franchise-era）；缺則呼叫端 fallback。"""
    out: dict[tuple[int, str], dict] = {}
    with conn() as c:
        cur = c.cursor()
        cur.execute(
            "SELECT year, team_id, sum(ab), sum(h), sum(tb), sum(bb), sum(hbp), sum(sf) "
            "FROM cpbl.batting_seasons GROUP BY year, team_id")
        for y, t, ab, h, tb, bb, hbp, sf in cur.fetchall():
            ab = ab or 0
            if ab <= 0:
                continue
            bb, hbp, sf, tb, h = bb or 0, hbp or 0, sf or 0, tb or 0, h or 0
            den = ab + bb + hbp + sf
            slg = tb / ab
            ops = ((h + bb + hbp) / den if den else 0) + slg
            # team_id 老年份 3 碼(ACC)、近年 6 碼(ACC011)→ 統一取前 3 碼當 key 對齊 games。
            out.setdefault((y + 1, t[:3]), {}).update({"prior_ops": ops, "prior_slg": slg})
        cur.execute(
            "SELECT year, team_id, sum(floor(ip)+(ip-floor(ip))*10/3.0), sum(er), sum(h), sum(bb) "
            "FROM cpbl.pitching_seasons GROUP BY year, team_id")
        for y, t, ip, er, h, bb in cur.fetchall():
            if not ip or ip <= 0:
                continue
            out.setdefault((y + 1, t[:3]), {}).update(
                {"prior_era": (er or 0) * 9 / ip, "prior_whip": ((h or 0) + (bb or 0)) / ip})
    return out


def _team_batting_box() -> dict[tuple[int, str, int], dict]:
    """{(year, kind_code, game_sno): {'2': {ab,h,bb,hbp,tb,sf}, '1': {...}}}（逐場主/客隊打擊
    box，僅 2018+ 有逐打席）。供「當季到此」團隊打擊 running state。"""
    box: dict[tuple[int, str, int], dict] = {}
    with conn() as c:
        cur = c.cursor()
        cur.execute(
            "SELECT year, kind_code, game_sno, visiting_home_type, sum(at_bats), sum(hits), "
            "sum(bb), sum(hbp), sum(total_bases), sum(sac_fly), sum(sb), sum(cs), sum(errors) "
            "FROM cpbl.batting_gamelog GROUP BY year, kind_code, game_sno, visiting_home_type")
        for y, k, sno, vh, ab, h, bb, hbp, tb, sf, sb, cs, err in cur.fetchall():
            box.setdefault((y, k, sno), {})[str(vh)] = {
                "ab": ab or 0, "h": h or 0, "bb": bb or 0, "hbp": hbp or 0, "tb": tb or 0,
                "sf": sf or 0, "sb": sb or 0, "cs": cs or 0, "err": err or 0, "g": 1}
        # 暴投：本場各隊投手群暴投數（pitching_gamelog；防守方視角）。
        cur.execute(
            "SELECT year, kind_code, game_sno, visiting_home_type, sum(wild_pitch) "
            "FROM cpbl.pitching_gamelog GROUP BY year, kind_code, game_sno, visiting_home_type")
        for y, k, sno, vh, wp in cur.fetchall():
            box.setdefault((y, k, sno), {}).setdefault(str(vh), {})["wp"] = wp or 0
    return box


def _completion_evidence() -> set[tuple[int, str, int]]:
    """已取得外部完賽證據的場次集合（0:0 真和局靠它才判得出完成）。"""
    with conn() as c:
        cur = c.cursor()
        cur.execute(
            "SELECT year, kind_code, game_sno FROM cpbl.game_completion_evidence")
        return {(y, k, s) for y, k, s in cur.fetchall()}


def build_game_features() -> list[dict]:
    # 完賽判定所需：外部證據集合 + 日期界線（台北日界）。逐場在迴圈內以
    # `is_completed_game` 判定，與 SQL 端的 `completed_games_sql_with_evidence` 同語意。
    _evidence = _completion_evidence()
    _AS_OF = datetime.now(_TAIPEI).date()
    pitch_game = _starter_game_counts()
    pitch_season = _pitcher_season_totals(pitch_game)
    lg_pitch = _league_pitch_rates(pitch_season)
    prior_wp = _prior_winpct()
    prior_team = _prior_team_stats()
    box = _team_batting_box()
    # 當季到此團隊累計（打擊 + 壘間/守備/投手細項）
    team_bat: dict[str, dict] = defaultdict(
        lambda: {"ab": 0, "h": 0, "bb": 0, "hbp": 0, "tb": 0, "sf": 0,
                 "sb": 0, "cs": 0, "err": 0, "wp": 0, "g": 0})

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
    # 投手季內累計（pitcher_id -> 計數）；每季歸零，於「快照特徵之後」才套用本場。
    run_pitch: dict[str, _PitchCounts] = defaultdict(_PitchCounts)
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
            team_bat.clear(); run_pitch.clear()

        rec = h2h[frozenset((home, away))]
        hw, aw = rec.get(home, 0), rec.get(away, 0)
        # 休息天數差：任一隊季內首戰（None）→ 視為持平 0。
        hr, ar = rest_days(home, date), rest_days(away, date)
        rest_diff = 0.0 if (hr is None or ar is None) else float(hr - ar)
        # 上季戰力差：無上季資料（新隊/首季）→ 0.5 中性。
        prior_diff = prior_wp.get((year, home), 0.5) - prior_wp.get((year, away), 0.5)
        # 上季團隊打擊/投手差：任一隊無上季資料 → 0 中性。
        pth, pta = prior_team.get((year, home[:3]), {}), prior_team.get((year, away[:3]), {})

        def _ptd(key: str) -> float:
            return (pth[key] - pta[key]) if key in pth and key in pta else 0.0

        # 當季到此團隊細項（打擊 OPS/AVG、淨盜壘、暴投、失誤）；僅 2018+ 有逐打席 box，
        # 更早年份 → None（train_model 自動限縮）。各為主-客差，None 表該軸無資料。
        def _ops_avg(team: str):
            s = team_bat[team]
            if s["ab"] <= 0:
                return None, None
            den = s["ab"] + s["bb"] + s["hbp"] + s["sf"]
            return s["h"] / s["ab"], (((s["h"] + s["bb"] + s["hbp"]) / den) if den else 0) + s["tb"] / s["ab"]

        def _pg(team: str, num):
            s = team_bat[team]
            return num(s) / s["g"] if s["g"] > 0 else None

        def _d(hf, af):
            return (hf - af) if hf is not None and af is not None else 0.0
        if year >= 2018:
            (ha, ho), (aa, ao) = _ops_avg(home), _ops_avg(away)
            team_avg_now, team_ops_now = _d(ha, aa), _d(ho, ao)
            team_sb_now = _d(_pg(home, lambda s: s["sb"] - s["cs"]), _pg(away, lambda s: s["sb"] - s["cs"]))
            team_wp_now = _d(_pg(home, lambda s: s["wp"]), _pg(away, lambda s: s["wp"]))
            team_err_now = _d(_pg(home, lambda s: s["err"]), _pg(away, lambda s: s["err"]))
        else:
            team_avg_now = team_ops_now = team_sb_now = team_wp_now = team_err_now = None

        # 先發投手賽前指標：本季至該場前累計（快照）＋ 前一季 prior 收縮。
        # 前一季聯盟率作最終 fallback；全史首季無前一季 → 固定墊檔常數。
        lg_prev = lg_pitch.get(year - 1, (_LG_DEFAULT_ER_IP, _LG_DEFAULT_WHIP, _LG_DEFAULT_SO_IP))
        h_era, h_whip, h_k9 = _starter_rates(
            run_pitch.get(hsp, _ZERO_COUNTS) if hsp else _ZERO_COUNTS,
            pitch_season.get((year - 1, hsp)) if hsp else None, lg_prev)
        a_era, a_whip, a_k9 = _starter_rates(
            run_pitch.get(asp, _ZERO_COUNTS) if asp else _ZERO_COUNTS,
            pitch_season.get((year - 1, asp)) if asp else None, lg_prev)

        feats = {
            "winrate_diff": winrate(home) - winrate(away),
            "prior_winpct_diff": prior_diff,
            "runs_scored_diff": rs_pg(home) - rs_pg(away),
            "runs_allowed_diff": ra_pg(home) - ra_pg(away),
            "recent_form_diff": form(home) - form(away),
            "rest_days_diff": rest_diff,
            "h2h_home": (hw / (hw + aw)) if (hw + aw) > 0 else 0.5,
            "home_field": 1.0,
            # 先發投手賽前 as-of（主-客）；ERA/WHIP 越低越好（定向取負），K9 越高越好。
            "starter_era_diff": h_era - a_era,
            "starter_whip_diff": h_whip - a_whip,
            "starter_k9_diff": h_k9 - a_k9,
            "prior_team_ops_diff": _ptd("prior_ops"),
            "prior_team_slg_diff": _ptd("prior_slg"),
            "prior_team_era_diff": _ptd("prior_era"),
            "prior_team_whip_diff": _ptd("prior_whip"),
            "team_ops_now_diff": team_ops_now,
            "team_avg_now_diff": team_avg_now,
            "team_sb_now_diff": team_sb_now,
            "team_wp_now_diff": team_wp_now,
            "team_err_now_diff": team_err_now,
        }

        completed = is_completed_game(
            hs, as_, date, _AS_OF, (year, kind, sno) in _evidence)
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
        # 累計本場團隊打擊 box 到 running state（在算完特徵之後 → leakage-safe）。
        gb = box.get((year, kind, sno))
        if gb:
            for vh, tcode in (("2", home), ("1", away)):
                s = gb.get(vh)
                if s:
                    for key in ("ab", "h", "bb", "hbp", "tb", "sf", "sb", "cs", "err", "wp", "g"):
                        team_bat[tcode][key] += s.get(key, 0)
        # 累計本場投手 box 到 running state（同樣在算完特徵之後 → leakage-safe）。
        for pid, pc in pitch_game.get((year, sno), {}).items():
            run_pitch[pid].add(pc)

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
         r["prior_winpct_diff"], r["rest_days_diff"],
         r["prior_team_ops_diff"], r["prior_team_slg_diff"],
         r["prior_team_era_diff"], r["prior_team_whip_diff"],
         r["team_ops_now_diff"], r["team_avg_now_diff"],
         r["team_sb_now_diff"], r["team_wp_now_diff"], r["team_err_now_diff"])
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
                 prior_winpct_diff, rest_days_diff,
                 prior_team_ops_diff, prior_team_slg_diff, prior_team_era_diff, prior_team_whip_diff,
                 team_ops_now_diff, team_avg_now_diff,
                 team_sb_now_diff, team_wp_now_diff, team_err_now_diff)
            VALUES (%s,%s,%s,%s,%s,%s, %s,%s,%s,%s, %s,%s, %s,%s,%s,%s,%s,%s,%s,%s,%s, %s,%s, %s,%s,%s,%s, %s,%s, %s,%s,%s)
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
                prior_winpct_diff=EXCLUDED.prior_winpct_diff, rest_days_diff=EXCLUDED.rest_days_diff,
                prior_team_ops_diff=EXCLUDED.prior_team_ops_diff,
                prior_team_slg_diff=EXCLUDED.prior_team_slg_diff,
                prior_team_era_diff=EXCLUDED.prior_team_era_diff,
                prior_team_whip_diff=EXCLUDED.prior_team_whip_diff,
                team_ops_now_diff=EXCLUDED.team_ops_now_diff,
                team_avg_now_diff=EXCLUDED.team_avg_now_diff,
                team_sb_now_diff=EXCLUDED.team_sb_now_diff,
                team_wp_now_diff=EXCLUDED.team_wp_now_diff,
                team_err_now_diff=EXCLUDED.team_err_now_diff
            """,
            records,
        )
    return len(records)
