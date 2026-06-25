"""單場對戰預測:把雙方真實數字攤開 + 訓練出預設權重 + 可手動微調。

設計（對齊使用者重新規劃的需求）:
- 以「比賽」為主角:每場顯示主客兩隊的場均得分 / 失分(防禦) / 勝率 / 近況等真實數字。
- 勝率引擎=「訓練預設 + 手動微調」:後端用歷史資料 fit 邏輯回歸得到各變因「預設權重」
  與標準化參數;每場回傳各變因的標準化值 z。前端 logit = Σ weight_k · z_k → sigmoid,
  使用者拖權重滑桿即可即時重算（home_field 的權重即 intercept/主場優勢）。
- 兩種對象:今日/近期真實賽事(upcoming) + 任選兩隊模擬(simulate)，皆用當季到當日統計。
"""

from __future__ import annotations

import math
from datetime import date

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score
from sklearn.preprocessing import StandardScaler

from cpbl.db import conn
from cpbl.features.outcome import CANDIDATE_FEATURES, FEATURE_KEYS

HOME_FIELD = "home_field"
# 各「球隊級」變因 → team_stats 的 key
TEAM_STAT = {
    "winrate_diff": "win_pct",
    "prior_winpct_diff": "prior_wp",
    "runs_scored_diff": "rs_pg",
    "runs_allowed_diff": "ra_pg",
    "recent_form_diff": "form",
    "rest_days_diff": "rest_days",
}
# 定向：把每個變數轉成「正值 = 有利主隊」。失分/ERA 越低越好故取負；對戰勝率以 0.5 為中心。
ORIENT_SIGN = {
    "winrate_diff": 1.0, "prior_winpct_diff": 1.0, "runs_scored_diff": 1.0,
    "runs_allowed_diff": -1.0, "recent_form_diff": 1.0, "rest_days_diff": 1.0,
    "h2h_home": 1.0,
    "starter_era_diff": -1.0, "starter_whip_diff": -1.0, "starter_k9_diff": 1.0,
}
ORIENT_CENTER = {"h2h_home": 0.5}
# 先發投手變因 → pitcher_stats 的欄位
STARTER_STAT = {"starter_era_diff": "era", "starter_whip_diff": "whip", "starter_k9_diff": "k9"}
LABELS = dict(CANDIDATE_FEATURES)


def _oriented(key: str, raw: float) -> float:
    """把原始差值/比率轉成「正值=有利主隊」的定向值。"""
    return ORIENT_SIGN[key] * (raw - ORIENT_CENTER.get(key, 0.0))


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def _validate(features: list[str]) -> tuple[list[str], list[str], bool]:
    sel = [f for f in features if f in FEATURE_KEYS]
    if not sel:
        raise ValueError("至少需選一個變因")
    real = [f for f in sel if f != HOME_FIELD]
    return sel, real, HOME_FIELD in sel


# ---------- 球隊當季到當日統計 ----------

def _prior_winpct(season: int) -> dict[str, float]:
    """{team_code: 上一季(一軍例行賽)最終勝率}；季初冷啟動的戰力先驗。"""
    with conn() as c:
        cur = c.cursor()
        cur.execute(
            """
            SELECT team, sum(w)::float / NULLIF(sum(w + l), 0) FROM (
                SELECT home_team_code AS team,
                       count(*) FILTER (WHERE home_score > away_score) w,
                       count(*) FILTER (WHERE home_score < away_score) l
                FROM cpbl.games WHERE kind_code='A' AND year=%s AND home_score+away_score>0
                GROUP BY home_team_code
                UNION ALL
                SELECT away_team_code,
                       count(*) FILTER (WHERE away_score > home_score),
                       count(*) FILTER (WHERE away_score < home_score)
                FROM cpbl.games WHERE kind_code='A' AND year=%s AND home_score+away_score>0
                GROUP BY away_team_code
            ) t GROUP BY team
            """,
            (season - 1, season - 1),
        )
        return {code: float(wp) for code, wp in cur.fetchall() if wp is not None}


def team_stats(season: int) -> dict[str, dict]:
    """回傳 {team_code: {name, w, l, win_pct, rs_pg, ra_pg, form, prior_wp, rest_days}}
    （當季完成場次累計；prior_wp=上季戰力先驗、rest_days=距上一場至今天的休息天數）。"""
    prior = _prior_winpct(season)
    with conn() as c:
        cur = c.cursor()
        cur.execute(
            """
            SELECT game_date, home_team_code, home_team_name, away_team_code, away_team_name,
                   home_score, away_score
            FROM cpbl.games
            WHERE year = %s AND kind_code = 'A' AND home_score + away_score > 0
            ORDER BY game_date, game_sno
            """,
            (season,),
        )
        rows = cur.fetchall()

    st: dict[str, dict] = {}

    def ensure(code, name):
        if code not in st:
            st[code] = {"name": name, "w": 0, "l": 0, "rf": 0, "ra": 0, "g": 0, "last10": [], "last_date": None}
        elif name:
            st[code]["name"] = name

    for d, hc, hn, ac, an, hs, as_ in rows:
        ensure(hc, hn); ensure(ac, an)
        st[hc]["rf"] += hs; st[hc]["ra"] += as_; st[hc]["g"] += 1; st[hc]["last_date"] = d
        st[ac]["rf"] += as_; st[ac]["ra"] += hs; st[ac]["g"] += 1; st[ac]["last_date"] = d
        if hs > as_:
            st[hc]["w"] += 1; st[ac]["l"] += 1
            st[hc]["last10"].append(1); st[ac]["last10"].append(0)
        elif hs < as_:
            st[hc]["l"] += 1; st[ac]["w"] += 1
            st[hc]["last10"].append(0); st[ac]["last10"].append(1)

    today = date.today()
    out: dict[str, dict] = {}
    for code, s in st.items():
        gp = s["w"] + s["l"]
        last10 = s["last10"][-10:]
        rest = min((today - s["last_date"]).days, 7) if s["last_date"] else 0.0
        out[code] = {
            "name": s["name"], "w": s["w"], "l": s["l"], "g": s["g"],
            "win_pct": s["w"] / gp if gp else 0.5,
            "prior_wp": prior.get(code, 0.5),
            "rest_days": float(rest),
            "rs_pg": s["rf"] / s["g"] if s["g"] else 0.0,
            "ra_pg": s["ra"] / s["g"] if s["g"] else 0.0,
            "form": sum(last10) / len(last10) if last10 else 0.5,
            "last10": f"{sum(last10)}-{len(last10) - sum(last10)}",
        }
    return out


def pitcher_stats(season: int) -> dict[str, dict]:
    """本季投手 {player_id: {name, era, whip, k9, fip}}（來自 pitching_current）。"""
    out: dict[str, dict] = {}
    with conn() as c:
        cur = c.cursor()
        cur.execute(
            "SELECT player_id, name, era, whip, k9, fip FROM cpbl.pitching_current WHERE year = %s",
            (season,),
        )
        for pid, name, era, whip, k9, fip in cur.fetchall():
            out[pid] = {
                "name": name,
                "era": float(era) if era is not None else None,
                "whip": float(whip) if whip is not None else None,
                "k9": float(k9) if k9 is not None else None,
                "fip": float(fip) if fip is not None else None,
            }
    return out


def league_pitch(season: int) -> dict[str, float]:
    """投手各指標的聯盟平均（先發未達合格時的墊檔值）。"""
    ps = pitcher_stats(season).values()
    defaults = {"era": 4.0, "whip": 1.3, "k9": 7.0}
    out: dict[str, float] = {}
    for stat, d in defaults.items():
        vals = [p[stat] for p in ps if p.get(stat) is not None]
        out[stat] = sum(vals) / len(vals) if vals else d
    return out


def h2h_rate(home: str, away: str, season: int) -> float:
    """本季兩隊交手中主隊的勝率（雙方主客場都算；無交手 → 0.5）。"""
    with conn() as c:
        cur = c.cursor()
        cur.execute(
            """
            SELECT
                count(*) FILTER (WHERE (home_team_code = %s AND home_score > away_score)
                                    OR (away_team_code = %s AND away_score > home_score)),
                count(*)
            FROM cpbl.games
            WHERE year = %s AND home_score + away_score > 0
              AND ((home_team_code = %s AND away_team_code = %s)
                OR (home_team_code = %s AND away_team_code = %s))
            """,
            (home, home, season, home, away, away, home),
        )
        hw, tot = cur.fetchone()
    return hw / tot if tot else 0.5


def list_teams(season: int) -> list[dict]:
    s = team_stats(season)
    return sorted(({"code": c, "name": v["name"]} for c, v in s.items()), key=lambda x: x["code"])


# ---------- 訓練：預設權重 + 標準化參數 ----------

def train_model(features: list[str]) -> dict:
    sel, real, use_intercept = _validate(features)
    cols = ", ".join(FEATURE_KEYS)
    with conn() as c:
        cur = c.cursor()
        cur.execute(
            f"""
            SELECT season, home_win, {cols} FROM cpbl.game_features
            WHERE completed = true AND home_win IN (0,1)
            ORDER BY game_date, game_sno
            """
        )
        rows = cur.fetchall()

    idx = {k: 2 + FEATURE_KEYS.index(k) for k in real}
    seasons = sorted({r[0] for r in rows})
    test_season = seasons[-1]
    train = [r for r in rows if r[0] < test_season] or rows
    test = [r for r in rows if r[0] == test_season] or rows

    weights: dict[str, float] = {}
    mean: dict[str, float] = {}
    std: dict[str, float] = {}
    ytr = np.array([r[1] for r in train], dtype=int)
    yte = np.array([r[1] for r in test], dtype=int)
    base = float(ytr.mean())

    # 預設權重 = 每個「定向後」變數單獨的標準化係數；負（反直覺/無正向訊號）歸零，
    # 預設不採信但使用者可手動加上去。符號因定向恆為「正=有利主隊」。
    for k in real:
        xtr = np.array([[_oriented(k, r[idx[k]])] for r in train], dtype=float)
        scaler = StandardScaler().fit(xtr)
        clf = LogisticRegression(fit_intercept=False, max_iter=1000)
        clf.fit(scaler.transform(xtr), ytr)
        weights[k] = round(max(float(clf.coef_[0][0]), 0.0), 4)
        mean[k] = float(scaler.mean_[0])
        std[k] = float(scaler.scale_[0])
    # 主場優勢權重 = 主場基準勝率的 log-odds（intercept）。
    if use_intercept:
        weights[HOME_FIELD] = round(math.log(base / (1 - base)), 4)

    # 以「加權標準化和」這個實際使用的模型評估 test 準確率（誠實對齊使用者看到的機率）。
    def _logit(r) -> float:
        s = weights.get(HOME_FIELD, 0.0)
        for k in real:
            s += weights[k] * ((_oriented(k, r[idx[k]]) - mean[k]) / (std[k] or 1.0))
        return s

    pred = np.array([1 if _logit(r) >= 0 else 0 for r in test], dtype=int)
    accuracy = round(float(accuracy_score(yte, pred)), 4)
    baseline = round(max(float(yte.mean()), 1 - float(yte.mean())), 4)

    return {
        "features": sel, "real": real, "use_intercept": use_intercept,
        "weights": weights, "mean": mean, "std": std,
        "accuracy": accuracy, "baseline": baseline,
        "n_train": len(train), "n_test": len(test), "test_season": test_season,
    }


# ---------- 組對戰卡 ----------

def _factor_rows(home_s: dict, away_s: dict, h2h: float, model: dict,
                 starter_vals: dict[str, tuple[float, float]]) -> tuple[list[dict], dict[str, float]]:
    """回傳每個選定變因的雙方數值/有利方，以及標準化值 z（供前端算 logit）。"""
    rows: list[dict] = []
    z: dict[str, float] = {}
    for k in model["features"]:
        if k == HOME_FIELD:
            z[k] = 1.0
            rows.append({"key": k, "label": LABELS[k], "home_val": None, "away_val": None, "favored": "home"})
            continue
        if k in TEAM_STAT:
            hv, av = home_s[TEAM_STAT[k]], away_s[TEAM_STAT[k]]
            raw = hv - av
        elif k in STARTER_STAT:
            hv, av = starter_vals[k]
            raw = hv - av
        else:  # h2h_home（比率，主隊視角）
            hv, av, raw = h2h, None, h2h
        ov = _oriented(k, raw)  # 正=有利主隊
        favored = "even" if abs(ov) < 1e-9 else ("home" if ov > 0 else "away")
        sd = model["std"].get(k) or 1.0
        z[k] = (ov - model["mean"].get(k, 0.0)) / (sd if sd else 1.0)
        rows.append({"key": k, "label": LABELS[k], "home_val": hv, "away_val": av, "favored": favored})
    return rows, z


def _prob(z: dict[str, float], weights: dict[str, float]) -> float:
    logit = sum(weights.get(k, 0.0) * zk for k, zk in z.items())
    return _sigmoid(logit)


def _starter(pitchers: dict, pid: str | None) -> dict | None:
    """先發投手顯示資訊（名字 + 本季 ERA/WHIP/K9）；查無回 None。"""
    if not pid:
        return None
    p = pitchers.get(pid)
    if not p:
        return {"name": None, "era": None, "whip": None, "k9": None}  # 有 ID 但未達合格投手
    return {"name": p["name"], "era": p["era"], "whip": p["whip"], "k9": p["k9"]}


def build_matchup(home: str, away: str, stats: dict, model: dict, season: int,
                  game_date: str | None = None, home_starter: str | None = None,
                  away_starter: str | None = None, pitchers: dict | None = None,
                  lg_pitch: dict | None = None) -> dict:
    hs, as_ = stats.get(home), stats.get(away)
    if not hs or not as_:
        return {}
    pitchers = pitchers or {}
    lg = lg_pitch or {"era": 4.0, "whip": 1.3, "k9": 7.0}
    h2h = h2h_rate(home, away, season)

    hp, ap = _starter(pitchers, home_starter), _starter(pitchers, away_starter)

    def sv(side: dict | None, stat: str) -> float:
        return side[stat] if side and side.get(stat) is not None else lg[stat]

    starter_vals = {
        k: (sv(hp, stat), sv(ap, stat)) for k, stat in STARTER_STAT.items()
    }

    rows, z = _factor_rows(hs, as_, h2h, model, starter_vals)
    return {
        "game_date": game_date,
        "home": {"code": home, "name": hs["name"], "win_pct": round(hs["win_pct"], 3),
                 "rs_pg": round(hs["rs_pg"], 2), "ra_pg": round(hs["ra_pg"], 2),
                 "form": hs["last10"], "record": f"{hs['w']}-{hs['l']}", "starter": hp},
        "away": {"code": away, "name": as_["name"], "win_pct": round(as_["win_pct"], 3),
                 "rs_pg": round(as_["rs_pg"], 2), "ra_pg": round(as_["ra_pg"], 2),
                 "form": as_["last10"], "record": f"{as_['w']}-{as_['l']}", "starter": ap},
        "h2h_home": round(h2h, 3),
        "factors": rows,
        "z": {k: round(v, 4) for k, v in z.items()},
        "home_win_prob": round(_prob(z, model["weights"]), 4),
    }


def upcoming(features: list[str], season: int, limit: int = 20) -> dict:
    model = train_model(features)
    stats = team_stats(season)
    pitchers = pitcher_stats(season)
    lg = league_pitch(season)
    with conn() as c:
        cur = c.cursor()
        cur.execute(
            """
            SELECT game_date, home_team_code, away_team_code, home_starter_id, away_starter_id
            FROM cpbl.games
            WHERE year = %s AND home_score + away_score = 0 AND game_date >= %s
            ORDER BY game_date, game_sno
            LIMIT %s
            """,
            (season, date.today(), limit),
        )
        games = cur.fetchall()
    items = [
        m for d, h, a, hsp, asp in games
        if (m := build_matchup(h, a, stats, model, season, d.isoformat() if d else None,
                               hsp or None, asp or None, pitchers, lg))
    ]
    return {"model": model, "items": items}


def simulate(home: str, away: str, features: list[str], season: int) -> dict:
    model = train_model(features)
    stats = team_stats(season)
    pitchers = pitcher_stats(season)
    # 任選兩隊無排定先發 → 先發投手變因以聯盟平均墊檔（中性）。
    return {"model": model,
            "matchup": build_matchup(home, away, stats, model, season,
                                     pitchers=pitchers, lg_pitch=league_pitch(season))}
