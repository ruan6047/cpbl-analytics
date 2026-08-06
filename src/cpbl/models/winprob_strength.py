"""GAME-RECAP-WP-STRENGTH1：場中 WP 戰力感知先驗（唯讀；A 一軍例行、核心資料 2018+）。

在既有局面 WP（models/winprob.py run_dist × WE DP）之上，融合一層**只由賽前可知
資訊形成的隊伍戰力／先發投手先驗**，消除 WP-VAL1 證實的時間外 S 型偏差
（低分箱 +4.2~+6.0pt／高分箱 −4.3pt）。WP-CAL1 已證明事後校準無法治本
（修正不具時間平穩性，見其報告 §5）；本卡走 VAL1 §7 路徑 2。

融合形式（卡面凍結，不得改動）::

    p0(g)       = sigmoid(beta0 + beta · x_pre(g))
    p_base0(Y)  = 同一代 base run_dist／ruleset 在「1 局上、0 出局、空壘、0:0」的主隊 WP
    t(s)        = clamp(((inning - 1) * 6 + half_offset * 3 + outs) / 54, 0, 1)
    w_gamma(t)  = (1 - t) ** gamma
    WP_adj      = sigmoid(logit_clip(WP_situ) + w_gamma(t) *
                          (logit_clip(p0) - logit_clip(p_base0)))

`p_base0` 取自**同一代 base 解算器的開場狀態** → t=0 時 WP_adj = p0，避免把 base
已含的主場優勢重複相加（CAL1 全域中心下修的死因）。

統計紅線（卡面八條；違反即退回）：
1. **時間分離與擬合對象**：驗證季 Y 的 base 與最終先驗參數只 fit 2018..Y−1；超參／
   融合選型只能看「fit 2018..Y−2 後對 Y−1 產生」的 out-of-time 預測。兩種擬合對象
   在 artifact 分開標記（`inner_selection` vs `final`）。
2. **特徵洩漏**：僅八項凍結賽前特徵；season running state 一律在套用該場結果前計算。
   明確禁用 `game_features.starter_era_diff/whip/k9`（`features/outcome.py` 以
   `(starter_id, year)` 讀同季彙總 → 對歷史賽前模型會看見該季後續資料）、同季最終
   standing、同場比分／PA 結果、`pitching_current` 全季快照、只有 2026 累計值的
   `advanced_stats`。
3. **選型洩漏**：模型族、特徵、kappa/lambda/gamma 網格、目標、tie-break、融合式與
   門檻皆在卡面凍結；不得以 2023–2026 任一目標季表現挑選或事後改動。
4. **WP-VAL1 v2 門檻只可加嚴**：coverage ≥ 0.98、Brier 須勝該季 leakage-safe 主場常數
   基準、且不得劣於同代未融合 base；池化十分位 n≥1000 若 |dev| > 0.03 且 99%
   game-cluster CI 排除 0 即硬性失敗。全部判定使用**未捨入值**。
5. **逐局帶是硬性判定**：池化 1-3／4-6／7-9 各帶 n≥1000 若 |dev| > 0.03 且 99% CI
   排除 0 即失敗；相對同代 base 任一帶 |dev| 惡化 > 2pt，或至少兩帶各惡化 > 1pt，
   亦失敗（沿用 CAL1 已預註冊門檻）。10+ 僅揭露。
6. **語意與數值合約**：固定 (p0,t) 時 WP_adj 對 WP_situ 單調、值域 [0,1]；開場等於
   p0；終場／再見端點 0/1 不經 clip 與融合；w(t) 不增且 9 局完成後為 0。
7. **基準、時期與小樣本**：逐季與池化並排未融合 base、CAL1 歷史判定與主場常數；
   報告先列 2026 鎖箱結果。p0、≤2017 prior 與 2026 advanced shadow 只作診斷。
8. **可重現**：DB 全程唯讀，bootstrap seed 固定 20260725；`--out` 可導向 scratch，
   `--seasons` 支援單季／部分重跑，禁止覆寫 canonical artifact。

執行（host 即可，無 LightGBM 相依；~5 分鐘）::

    uv run python -m cpbl.models.winprob_strength
    uv run python -m cpbl.models.winprob_strength --seasons 2026 --out /tmp/scratch.json

產出：docs/research/game_recap_wp_strength1_metrics.json（機器 artifact）+ stdout 表。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import math
import random
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field, replace
from datetime import date, datetime
from pathlib import Path

from cpbl.db import conn
from cpbl.models.winprob_cal import BANDS, REGULATION_BANDS, band_of, band_summary
from cpbl.models.winprob_val import (
    FIRST_YEAR,
    PRE_SCORE_SOURCES,
    THRESHOLDS,
    _resolve_pre_scores,
    brier_constant,
    collect_training_counts,
    dist_from_counts,
    load_eval_season,
    metrics,
    ruleset_for,
    score_pas,
    we_solver_rules,
    wp_state_rules,
)

log = logging.getLogger("cpbl.winprob_strength")

KIND = "A"                       # 本卡僅 A 一軍例行（卡面範圍）
CORE_FIRST = FIRST_YEAR          # 核心訓練／驗證母體起始（2018；canonical PA 與 gamelog 起點）
COLD_START_YEAR = 2017           # ≤2017 唯一用途：2018 首季的 rate prior（無逐場母體）
LAST_YEAR = 2026
VAL_FIRST, VAL_LAST = 2023, 2026  # 驗證季；2026 為鎖箱 holdout（報告首列）
EPS = 1e-6                       # logit_clip 與機率夾擠；只供數值計算
SEED = 20260725                  # bootstrap 固定 seed（紅線 8）

# 凍結特徵清單（卡面；方向皆「正值有利主隊」）。執行不得臨時增刪。
FEATURE_KEYS: tuple[str, ...] = (
    "prior_winpct_diff",                  # 主−客上季最終勝率（新隊／缺值 0.5）
    "winrate_diff",                       # 主−客本季截至該場「套用結果前」勝率
    "run_margin_diff",                    # (場均得分差) − (場均失分差)
    "rest_days_diff",                     # 主−客賽前休息天數（上限 7、季內首戰 0）
    "starter_kbb_adv",                    # 主−客先發 (SO−BB)/PA
    "starter_recorded_strike_share_adv",  # 主−客先發 strike_cnt/pitch_cnt（非官方 zone%）
    "starter_fip_proxy_adv",              # 客−主先發 FIP proxy（低者強 → 反向）
    "bullpen_kbb_adv",                    # 主−客非先發投手 (SO−BB)/PA
)
# 預註冊消融（僅診斷；full 是唯一驗收候選，不得因消融較佳而換上線模型）
ABLATIONS: dict[str, tuple[str, ...]] = {
    "team_only": FEATURE_KEYS[:4],
    "team_starter": FEATURE_KEYS[:7],
    "full": FEATURE_KEYS,
}

# 固定候選集合（卡面凍結）。掃描順序即 tie-break 的 canonical 順序：kappa 升冪 → lambda 升冪。
KAPPA_GRID: tuple[int, ...] = (50, 100, 200)     # PA-equivalent 部分池化強度
LAMBDA_GRID: tuple[float, ...] = (0.1, 1.0, 10.0, 100.0)  # L2；intercept 不懲罰
GAMMA_GRID: tuple[float, ...] = (0.5, 1.0, 2.0)
GAMMA_TIE_RANK = {1.0: 0, 2.0: 1, 0.5: 2}        # 同分順序：先取線性衰減
TIE_EPS = 1e-5                                    # 未捨入差 < 此值視為同分（卡面）

# 本卡新增門檻（跑驗證前預先註冊；v2 門檻沿用 winprob_val.THRESHOLDS 不放寬）
STRENGTH_THRESHOLDS = {
    "band_min_n": 1000,          # 逐局帶硬性判定的最低樣本
    "band_dev_max": 0.03,        # 帶絕對偏差上限（同池化十分位）
    "band_worsen_pt": 0.01,      # 相對 base 惡化 >1pt 記一次
    "band_worsen_hard_pt": 0.02,  # 單帶惡化 >2pt 即硬性失敗
}


# ───────────────────────── 數值基礎 ─────────────────────────
def sigmoid(z: float) -> float:
    if z >= 0.0:
        return 1.0 / (1.0 + math.exp(-z))
    e = math.exp(z)
    return e / (1.0 + e)


def logit_clip(p: float, eps: float = EPS) -> float:
    """紅線 6：只供數值計算的 logit；端點 0/1 由呼叫端先行短路，不進此函式。"""
    q = min(max(p, eps), 1.0 - eps)
    return math.log(q / (1.0 - q))


def progress_t(inning: int, vht: str, outs: int) -> float:
    """regulation outs 進度 t ∈ [0,1]；上半 half_offset=0、下半=1。

    9 局下 3 出局＝54 → t=1；10 局起亦夾為 1 ⇒ w(t)=0（延長賽不調整）。
    """
    half_offset = 0 if str(vht) == "1" else 1
    o = min(max(int(outs), 0), 2)
    return min(max(((inning - 1) * 6 + half_offset * 3 + o) / 54.0, 0.0), 1.0)


def fuse(wp_situ: float, p0: float, t: float, gamma: float, p_base0: float) -> float:
    """卡面凍結的 logit 空間 opening-anchor 融合（紅線 6）。

    canonical 端點（已終場／再見 ⇒ WP_situ 恰為 0/1）直接回傳，不經 clip 與融合。
    """
    if wp_situ <= 0.0:
        return 0.0
    if wp_situ >= 1.0:
        return 1.0
    w = (1.0 - t) ** gamma
    return sigmoid(logit_clip(wp_situ) + w * (logit_clip(p0) - logit_clip(p_base0)))


def opening_wp(dist: dict, year: int) -> float:
    """同一代 base 解算器的開場狀態主隊 WP（1 局上、0 出局、空壘、0:0）。

    紅線 6 的 anchor：不得以跨代經驗主場勝率代替，否則 t=0 時會重複計入主場優勢。
    """
    rules = ruleset_for(KIND, year)
    we_top, we_bot = we_solver_rules(dist, rules)
    return wp_state_rules(dist, we_top, we_bot, rules, 1, "1", 0, "___", 0)


# ───────────────────────── 投球原始計數 ─────────────────────────
@dataclass
class Counts:
    """逐場可加總的投球原始計數；rate 一律由此推導，不存半成品比率。"""

    pa: float = 0.0
    so: float = 0.0
    bb: float = 0.0
    hbp: float = 0.0
    hr: float = 0.0
    pitch: float = 0.0
    strike: float = 0.0
    ip: float = 0.0

    def add(self, o: Counts) -> None:
        self.pa += o.pa
        self.so += o.so
        self.bb += o.bb
        self.hbp += o.hbp
        self.hr += o.hr
        self.pitch += o.pitch
        self.strike += o.strike
        self.ip += o.ip

    def frozen(self) -> Counts:
        return replace(self)


ZERO = Counts()


@dataclass(frozen=True)
class GameRow:
    """單場賽前特徵所需的全部原料（皆為「套用該場結果前」的狀態）。"""

    year: int
    game_sno: int
    game_date: date
    home_team: str
    away_team: str
    y: float                       # 主隊勝=1／和=0.5／敗=0（由 games 比分建立，非 home_win）
    team_feats: dict[str, float]   # 前四項（來自 game_features 賽前 running／prior 欄）
    home_sp: Counts                # 主隊先發本季至該場前累計
    away_sp: Counts
    home_sp_prior: Counts | None   # 主隊先發前一季總量（None＝無 → 退聯盟率）
    away_sp_prior: Counts | None
    home_bp: Counts                # 主隊非先發投手本季至該場前累計
    away_bp: Counts
    home_bp_prior: Counts | None
    away_bp_prior: Counts | None
    sp_source: tuple[str, str] = ("", "")   # (home, away) 先發分母來源層級：own/prior/league
    bp_source: tuple[str, str] = ("", "")


def _row_counts(r: dict) -> Counts:
    return Counts(
        pa=float(r["plate_appearances"] or 0),
        so=float(r["so"] or 0),
        bb=float(r["bb"] or 0),
        hbp=float(r["hbp"] or 0),
        hr=float(r["home_runs"] or 0),
        pitch=float(r["pitch_cnt"] or 0),
        strike=float(r["strike_cnt"] or 0),
        ip=float(r["inning_pitched_cnt"] or 0) + float(r["inning_pitched_div3"] or 0) / 3.0,
    )


def load_cold_start_prior(cur) -> dict[str, Counts]:
    """≤2017 唯一用途：2018 首季先發的 rate prior（`pitching_seasons(year=2017)`）。

    該表無好球數 → `pitch/strike` 留 0，好球率 prior 只能退 fit-window 聯盟率
    （紅線 7：此為診斷可見的降級，不得以任何同季快照補）。
    """
    cur.execute(
        "SELECT player_id, sum(bf), sum(so), sum(bb), sum(hbp), sum(hr), "
        "sum(floor(ip) + (ip - floor(ip)) * 10 / 3.0) "
        "FROM cpbl.pitching_seasons WHERE year=%s AND ip > 0 GROUP BY player_id",
        (COLD_START_YEAR,))
    out: dict[str, Counts] = {}
    for pid, bf, so, bb, hbp, hr, ip in cur.fetchall():
        out[pid] = Counts(pa=float(bf or 0), so=float(so or 0), bb=float(bb or 0),
                          hbp=float(hbp or 0), hr=float(hr or 0), ip=float(ip or 0))
    return out


def load_game_rows(cur, first_year: int = CORE_FIRST,
                   last_year: int = LAST_YEAR,
                   as_of: date | None = None) -> list[GameRow]:
    """建立 2018..last_year 的逐場賽前原料（全程唯讀）。

    前四項隊伍特徵直接取 `game_features` 中已於賽前更新的 running／prior 欄
    （`features/outcome.py` 在「套用該場結果之前」寫入）；先發／牛棚指標則由
    `pitching_gamelog` 逐場原始計數在此重建 running state，避免使用同季彙總欄。
    """
    cur.execute(
        "SELECT g.year, g.game_sno, g.game_date, g.home_team_code, g.away_team_code, "
        "       g.home_score, g.away_score, g.home_starter_id, g.away_starter_id, "
        "       f.prior_winpct_diff, f.winrate_diff, f.runs_scored_diff, "
        "       f.runs_allowed_diff, f.rest_days_diff "
        "FROM cpbl.games g "
        "JOIN cpbl.game_features f ON f.year=g.year AND f.kind_code=g.kind_code "
        "  AND f.game_season_code=g.game_season_code AND f.game_sno=g.game_sno "
        "WHERE g.kind_code=%s AND g.year BETWEEN %s AND %s "
        "  AND g.home_score + g.away_score > 0 AND g.game_date <= %s "
        "ORDER BY g.game_date, g.game_sno",
        (KIND, first_year, last_year, as_of or date.today()))
    games = cur.fetchall()

    cur.execute(
        "SELECT year, game_sno, pitcher_acnt, visiting_home_type, role_type, "
        "       plate_appearances, so, bb, hbp, home_runs, pitch_cnt, strike_cnt, "
        "       inning_pitched_cnt, inning_pitched_div3 "
        "FROM cpbl.pitching_gamelog WHERE kind_code=%s AND year BETWEEN %s AND %s",
        (KIND, first_year, last_year))
    cols = [d[0] for d in cur.description]
    pglog: dict[tuple[int, int], list[dict]] = defaultdict(list)
    for row in cur.fetchall():
        r = dict(zip(cols, row, strict=True))
        pglog[(r["year"], r["game_sno"])].append(r)

    cold = load_cold_start_prior(cur)

    # 第一遍：整季總量 → 供「下一季」當 prior（球員 / 球隊牛棚各一組）
    season_sp: dict[tuple[int, str], Counts] = defaultdict(Counts)
    season_bp: dict[tuple[int, str], Counts] = defaultdict(Counts)
    for (year, sno, _d, home, away, *_rest) in games:
        for r in pglog.get((year, sno), ()):
            team = home if str(r["visiting_home_type"]) == "2" else away
            c = _row_counts(r)
            season_sp[(year, r["pitcher_acnt"])].add(c)
            if r["role_type"] != "先發":
                season_bp[(year, team)].add(c)

    def sp_prior(year: int, pid: str) -> Counts | None:
        if year - 1 == COLD_START_YEAR:
            return cold.get(pid)
        return season_sp.get((year - 1, pid))

    def bp_prior(year: int, team: str) -> Counts | None:
        # 2018 的 prior 季（2017）無逐場 gamelog → None → 退 fit-window 聯盟率
        return season_bp.get((year - 1, team))

    # 第二遍：依 (game_date, game_sno) 走查，快照賽前 state 後才套用本場計數
    run_sp: dict[str, Counts] = defaultdict(Counts)
    run_bp: dict[str, Counts] = defaultdict(Counts)
    cur_season: int | None = None
    rows: list[GameRow] = []
    for g in games:
        (year, sno, gdate, home, away, hs, as_, hsp, asp,
         prior_wp, winrate, rs, ra, rest) = g
        if cur_season != year:          # 新球季：season-to-date 歸零
            cur_season = year
            run_sp.clear()
            run_bp.clear()
        hp, ap = sp_prior(year, hsp), sp_prior(year, asp)
        hbp_p, abp_p = bp_prior(year, home), bp_prior(year, away)
        rows.append(GameRow(
            year=year, game_sno=sno, game_date=gdate, home_team=home, away_team=away,
            y=1.0 if hs > as_ else (0.0 if hs < as_ else 0.5),
            team_feats={
                "prior_winpct_diff": float(prior_wp or 0.0),
                "winrate_diff": float(winrate or 0.0),
                "run_margin_diff": float(rs or 0.0) - float(ra or 0.0),
                "rest_days_diff": float(rest or 0.0),
            },
            home_sp=run_sp[hsp].frozen(), away_sp=run_sp[asp].frozen(),
            home_sp_prior=hp, away_sp_prior=ap,
            home_bp=run_bp[home].frozen(), away_bp=run_bp[away].frozen(),
            home_bp_prior=hbp_p, away_bp_prior=abp_p,
            sp_source=(_tier(run_sp[hsp], hp), _tier(run_sp[asp], ap)),
            bp_source=(_tier(run_bp[home], hbp_p), _tier(run_bp[away], abp_p)),
        ))
        for r in pglog.get((year, sno), ()):     # 套用本場（在快照之後 ⇒ leakage-safe）
            team = home if str(r["visiting_home_type"]) == "2" else away
            c = _row_counts(r)
            run_sp[r["pitcher_acnt"]].add(c)
            if r["role_type"] != "先發":
                run_bp[team].add(c)
    return rows


def _tier(own: Counts, prior: Counts | None) -> str:
    """該場該側 rate 的資訊來源層級（診斷用；不影響計算）。"""
    if own.pa > 0:
        return "own"
    if prior is not None and prior.pa > 0:
        return "prior"
    return "league"


# ───────────────────────── fit 窗聯盟率（收縮 prior 與 kappa 換算） ─────────────────────────
@dataclass(frozen=True)
class LeagueRates:
    """只由 fit 窗建立的聯盟率與 kappa 分母換算比（紅線 1/2）。"""

    years: tuple[int, ...]
    sp_kbb: float
    sp_strike_share: float
    sp_hr_ip: float
    sp_bb_ip: float
    sp_hbp_ip: float
    sp_so_ip: float
    bp_kbb: float
    pitch_per_pa: float   # kappa（PA-equivalent）→ 投球數分母的換算比
    ip_per_pa: float      # kappa（PA-equivalent）→ 局數分母的換算比
    n_sp_pa: float
    n_bp_pa: float

    def as_dict(self) -> dict:
        return {"years": list(self.years),
                "sp_kbb": round(self.sp_kbb, 6),
                "sp_strike_share": round(self.sp_strike_share, 6),
                "sp_hr_per_ip": round(self.sp_hr_ip, 6),
                "sp_bb_per_ip": round(self.sp_bb_ip, 6),
                "sp_hbp_per_ip": round(self.sp_hbp_ip, 6),
                "sp_so_per_ip": round(self.sp_so_ip, 6),
                "bp_kbb": round(self.bp_kbb, 6),
                "pitch_per_pa": round(self.pitch_per_pa, 5),
                "ip_per_pa": round(self.ip_per_pa, 5),
                "n_starter_pa": self.n_sp_pa, "n_bullpen_pa": self.n_bp_pa}


def league_rates(cur, y0: int, y1: int) -> LeagueRates:
    """fit 窗 [y0, y1] 的角色分流聯盟率；先發／牛棚各自同口徑，不互相借用。"""
    cur.execute(
        "SELECT role_type = '先發' AS is_sp, sum(plate_appearances), sum(so), sum(bb), "
        "       sum(hbp), sum(home_runs), sum(pitch_cnt), sum(strike_cnt), "
        "       sum(inning_pitched_cnt + inning_pitched_div3 / 3.0) "
        "FROM cpbl.pitching_gamelog WHERE kind_code=%s AND year BETWEEN %s AND %s "
        "GROUP BY 1", (KIND, y0, y1))
    agg = {bool(r[0]): Counts(pa=float(r[1] or 0), so=float(r[2] or 0), bb=float(r[3] or 0),
                              hbp=float(r[4] or 0), hr=float(r[5] or 0),
                              pitch=float(r[6] or 0), strike=float(r[7] or 0),
                              ip=float(r[8] or 0)) for r in cur.fetchall()}
    sp, bp = agg.get(True, Counts()), agg.get(False, Counts())
    if sp.pa <= 0 or sp.ip <= 0 or sp.pitch <= 0 or bp.pa <= 0:
        raise ValueError(f"fit 窗 {y0}-{y1} 聯盟率分母不足，拒絕擬合")
    return LeagueRates(
        years=tuple(range(y0, y1 + 1)),
        sp_kbb=(sp.so - sp.bb) / sp.pa,
        sp_strike_share=sp.strike / sp.pitch,
        sp_hr_ip=sp.hr / sp.ip, sp_bb_ip=sp.bb / sp.ip,
        sp_hbp_ip=sp.hbp / sp.ip, sp_so_ip=sp.so / sp.ip,
        bp_kbb=(bp.so - bp.bb) / bp.pa,
        pitch_per_pa=sp.pitch / sp.pa, ip_per_pa=sp.ip / sp.pa,
        n_sp_pa=sp.pa, n_bp_pa=bp.pa,
    )


# ───────────────────────── 部分池化收縮與八項特徵 ─────────────────────────
def shrink(num: float, den: float, prior_rate: float, kappa_den: float) -> float:
    """預註冊部分池化近似：(current_num + kappa * prior_rate) / (current_den + kappa)。

    受 empirical-Bayes 小樣本研究啟發，但本卡未由資料估計完整階層分布，
    不冒稱完整 empirical-Bayes fit（卡面用語）。當季分母增加 ⇒ 自然取得更高權重。
    """
    return (num + kappa_den * prior_rate) / (den + kappa_den)


def _rate_or(prior: Counts | None, num, den, fallback: float) -> float:
    """前一季同口徑值優先；分母為 0 或無前一季 → fit 窗聯盟率（卡面 fallback 順序）。"""
    if prior is None:
        return fallback
    d = den(prior)
    return num(prior) / d if d > 0 else fallback


def starter_metrics(own: Counts, prior: Counts | None, lg: LeagueRates,
                    kappa: float) -> tuple[float, float, float]:
    """(K−BB%, recorded strike share, FIP proxy)；kappa 為 PA-equivalent。

    非 PA 分母的指標以 fit 窗聯盟 `分母/PA` 比換算 kappa，使單一 kappa 在三種
    分母上具可比的收縮強度（卡面：共同控制、不得各指標另調）。
    """
    k_pa = kappa
    k_pitch = kappa * lg.pitch_per_pa
    k_ip = kappa * lg.ip_per_pa
    kbb = shrink(own.so - own.bb, own.pa,
                 _rate_or(prior, lambda c: c.so - c.bb, lambda c: c.pa, lg.sp_kbb), k_pa)
    ss = shrink(own.strike, own.pitch,
                _rate_or(prior, lambda c: c.strike, lambda c: c.pitch,
                         lg.sp_strike_share), k_pitch)
    # FIP proxy：四個事件計數各自以同一 kappa 對應的 prior event rate 收縮後才組合
    # （卡面禁止直接平均 rate）。分母同為 IP ⇒ 組合後仍是良好定義的 per-IP 率。
    r_hr = shrink(own.hr, own.ip,
                  _rate_or(prior, lambda c: c.hr, lambda c: c.ip, lg.sp_hr_ip), k_ip)
    r_bb = shrink(own.bb, own.ip,
                  _rate_or(prior, lambda c: c.bb, lambda c: c.ip, lg.sp_bb_ip), k_ip)
    r_hbp = shrink(own.hbp, own.ip,
                   _rate_or(prior, lambda c: c.hbp, lambda c: c.ip, lg.sp_hbp_ip), k_ip)
    r_so = shrink(own.so, own.ip,
                  _rate_or(prior, lambda c: c.so, lambda c: c.ip, lg.sp_so_ip), k_ip)
    return kbb, ss, 13.0 * r_hr + 3.0 * (r_bb + r_hbp) - 2.0 * r_so


def bullpen_kbb(own: Counts, prior: Counts | None, lg: LeagueRates, kappa: float) -> float:
    return shrink(own.so - own.bb, own.pa,
                  _rate_or(prior, lambda c: c.so - c.bb, lambda c: c.pa, lg.bp_kbb), kappa)


def game_features(row: GameRow, lg: LeagueRates, kappa: float) -> dict[str, float]:
    """八項凍結賽前特徵（方向皆「正值有利主隊」）。"""
    h_kbb, h_ss, h_fip = starter_metrics(row.home_sp, row.home_sp_prior, lg, kappa)
    a_kbb, a_ss, a_fip = starter_metrics(row.away_sp, row.away_sp_prior, lg, kappa)
    return {
        **row.team_feats,
        "starter_kbb_adv": h_kbb - a_kbb,
        "starter_recorded_strike_share_adv": h_ss - a_ss,
        # FIP 低者較強 → 客−主，使正值有利主隊
        "starter_fip_proxy_adv": a_fip - h_fip,
        "bullpen_kbb_adv": (bullpen_kbb(row.home_bp, row.home_bp_prior, lg, kappa)
                            - bullpen_kbb(row.away_bp, row.away_bp_prior, lg, kappa)),
    }


# ───────────────────────── L2 邏輯斯迴歸（intercept 不懲罰） ─────────────────────────
@dataclass(frozen=True)
class PriorModel:
    keys: tuple[str, ...]
    mean: tuple[float, ...]
    std: tuple[float, ...]
    coef: tuple[float, ...]      # 標準化空間係數；零變異欄固定 0
    intercept: float
    lam: float
    kappa: int
    n_games: int
    n_iter: int
    converged: bool
    fit_years: tuple[int, ...] = ()

    def predict(self, feats: dict[str, float]) -> float:
        z = self.intercept
        for k, m, s, b in zip(self.keys, self.mean, self.std, self.coef, strict=True):
            if s > 0.0:
                z += b * (feats[k] - m) / s
        return sigmoid(z)

    def params(self) -> dict:
        return {"kappa": self.kappa, "lambda": self.lam, "n_games": self.n_games,
                "fit_years": list(self.fit_years), "intercept": round(self.intercept, 6),
                "n_iter": self.n_iter, "converged": self.converged,
                "coef_standardized": {k: round(b, 6)
                                      for k, b in zip(self.keys, self.coef, strict=True)},
                "feature_mean": {k: round(m, 6)
                                 for k, m in zip(self.keys, self.mean, strict=True)},
                "feature_std": {k: round(s, 6)
                                for k, s in zip(self.keys, self.std, strict=True)}}


def standardize_stats(xs: Sequence[Sequence[float]]) -> tuple[list[float], list[float]]:
    """fit 窗的 mean/std（母體標準差 ddof=0）；零變異欄 std=0 → 呼叫端固定係數 0。"""
    n = len(xs)
    p = len(xs[0])
    mean = [sum(r[j] for r in xs) / n for j in range(p)]
    std = []
    for j in range(p):
        var = sum((r[j] - mean[j]) ** 2 for r in xs) / n
        std.append(math.sqrt(var) if var > 1e-24 else 0.0)
    return mean, std


def nll_and_grad(z: Sequence[Sequence[float]], y: Sequence[float],
                 theta: Sequence[float], lam: float) -> tuple[float, list[float]]:
    """目標＝sum(binomial NLL) + lambda/2 * ||beta||²（intercept 不懲罰）。

    y ∈ {0, 0.5, 1}：與「兩筆 sample_weight=0.5 的 y=0/1 拆分」逐項等價
    （tests/test_winprob_strength.py 以 loss、梯度、擬合結果三重證明），
    且每場總權重恆為 1 ⇒ 不因拆列改變 game weighting。
    """
    p = len(theta)
    loss = 0.0
    grad = [0.0] * p
    for row, yi in zip(z, y, strict=True):
        s = theta[0] + sum(theta[j + 1] * row[j] for j in range(p - 1))
        q = sigmoid(s)
        qc = min(max(q, EPS), 1.0 - EPS)
        loss -= yi * math.log(qc) + (1.0 - yi) * math.log(1.0 - qc)
        d = q - yi
        grad[0] += d
        for j in range(p - 1):
            grad[j + 1] += d * row[j]
    for j in range(1, p):
        loss += 0.5 * lam * theta[j] ** 2
        grad[j] += lam * theta[j]
    return loss, grad


NEWTON_TOL = 1e-10       # Newton decrement 收斂門檻（與目標同尺度，故對 n 不敏感）


def fit_logistic_l2(feats: Sequence[dict[str, float]], y: Sequence[float], *,
                    keys: Sequence[str], lam: float, kappa: int,
                    fit_years: Sequence[int] = (), max_iter: int = 200
                    ) -> PriorModel:
    """決定性 Newton（帶回溯線搜尋）解 L2 邏輯斯迴歸；無隨機抽樣。

    收斂判準用 **Newton decrement**（½·stepᵀ·grad ≈ 目前點與最優點的目標值差）。
    目標是 sum(NLL) 而非 mean，梯度尺度隨場數成長 ⇒ 對梯度取絕對門檻會使大
    fit 窗＋弱正則（lambda=0.1）永遠達不到而空轉滿 max_iter；decrement 與目標
    同尺度，對 n 不敏感，是此處唯一正確的停止準則。
    """
    import numpy as np

    raw = [[float(f[k]) for k in keys] for f in feats]
    mean, std = standardize_stats(raw)
    active = [j for j, s in enumerate(std) if s > 0.0]
    z = [[(r[j] - mean[j]) / std[j] for j in active] for r in raw]
    yv = list(map(float, y))
    theta = [0.0] * (len(active) + 1)
    theta[0] = logit_clip(min(max(sum(yv) / len(yv), EPS), 1.0 - EPS))  # 起點＝基礎率
    Z = np.array(z, dtype=float) if active else np.zeros((len(z), 0))
    D = np.column_stack([np.ones(len(z)), Z]) if active else np.ones((len(z), 1))
    yarr = np.array(yv, dtype=float)
    pen = np.eye(len(theta))
    pen[0, 0] = 0.0
    cur_loss, _ = nll_and_grad(z, yv, theta, lam)
    n_iter, converged = 0, False
    while n_iter < max_iter:
        n_iter += 1
        th = np.array(theta, dtype=float)
        q = 1.0 / (1.0 + np.exp(-(D @ th)))
        grad = D.T @ (q - yarr) + lam * (pen @ th)
        w = np.clip(q * (1.0 - q), 1e-12, None)
        hess = (D * w[:, None]).T @ D + lam * pen + 1e-10 * np.eye(len(theta))
        step = np.linalg.solve(hess, grad)
        if 0.5 * float(step @ grad) < NEWTON_TOL:
            converged = True
            break
        t = 1.0
        improved = False
        for _ in range(40):
            trial = (th - t * step).tolist()
            trial_loss, _ = nll_and_grad(z, yv, trial, lam)
            if trial_loss <= cur_loss + 1e-15:
                theta, cur_loss, improved = trial, trial_loss, True
                break
            t *= 0.5
        if not improved:            # 線搜尋全敗 ⇒ 已在最優點附近
            converged = True
            break
    coef = [0.0] * len(keys)
    for idx, j in enumerate(active):
        coef[j] = theta[idx + 1]
    return PriorModel(keys=tuple(keys), mean=tuple(mean), std=tuple(std),
                      coef=tuple(coef), intercept=theta[0], lam=lam, kappa=kappa,
                      n_games=len(raw), n_iter=n_iter, converged=converged,
                      fit_years=tuple(fit_years))


# ───────────────────────── 指標（判定一律用未捨入值） ─────────────────────────
def raw_brier(scored: Sequence[tuple[float, float, bool, object]]) -> float:
    return sum((p - y) ** 2 for p, y, _, _ in scored) / len(scored) if scored else 0.0


def game_brier(preds: Sequence[float], ys: Sequence[float]) -> float:
    return sum((p - y) ** 2 for p, y in zip(preds, ys, strict=True)) / len(preds)


def game_logloss(preds: Sequence[float], ys: Sequence[float]) -> float:
    tot = 0.0
    for p, y in zip(preds, ys, strict=True):
        q = min(max(p, EPS), 1.0 - EPS)
        tot -= y * math.log(q) + (1.0 - y) * math.log(1.0 - q)
    return tot / len(preds)


def band_dev(band_row: dict | None) -> float | None:
    """band_summary 的顯示值已捨入；判定改用本函式接未捨入輸入（見 band_stats）。"""
    if not band_row:
        return None
    return band_row["pred"] - band_row["actual"]


def band_stats(innings: Sequence[int], scored: Sequence[tuple]) -> dict[str, dict]:
    """逐局帶未捨入 (pred, actual, dev, n)；紅線 4/5 的判定輸入。"""
    acc: dict[str, list[float]] = {b: [0.0, 0.0, 0.0] for b in BANDS}
    for inn, (p, y, _irr, _gk) in zip(innings, scored, strict=True):
        a = acc[band_of(inn)]
        a[0] += p
        a[1] += y
        a[2] += 1
    return {b: {"n": int(a[2]), "pred": a[0] / a[2], "actual": a[1] / a[2],
                "dev": (a[0] - a[1]) / a[2]}
            for b, a in acc.items() if a[2]}


def brier_delta_bootstrap(base: Sequence[tuple], adj: Sequence[tuple], *,
                          reps: int = THRESHOLDS["boot_reps"],
                          ci: float = THRESHOLDS["boot_ci"],
                          seed: int = SEED) -> dict:
    """融合 − 未融合 的 Brier 差，附 game-cluster bootstrap CI（**診斷，不進判定**）。

    卡面硬門檻是「融合後不得劣於同代 base」的點估計比較；本函式只回答「這個差
    是否可與 0 區分」，供報告誠實描述效果量，不改變任何 Go/No-Go 判定。
    """
    per_game: dict[object, list[float]] = {}
    for (pb, yb, _ib, gb), (pa, ya, _ia, ga) in zip(base, adj, strict=True):
        assert gb == ga and yb == ya, "base 與 adj 的逐 PA 對齊被破壞"
        d = per_game.setdefault(gb, [0.0, 0.0])
        d[0] += (pa - ya) ** 2 - (pb - yb) ** 2
        d[1] += 1
    games = list(per_game.values())
    point = sum(g[0] for g in games) / sum(g[1] for g in games)
    rng = random.Random(seed)
    draws = []
    for _ in range(reps):
        pick = rng.choices(games, k=len(games))
        draws.append(sum(g[0] for g in pick) / sum(g[1] for g in pick))
    draws.sort()
    n = len(draws)
    mean = sum(draws) / n
    se = (sum((d - mean) ** 2 for d in draws) / max(n - 1, 1)) ** 0.5
    lo_q, hi_q = (1 - ci) / 2, 1 - (1 - ci) / 2
    return {"delta_brier": round(point, 6), "se": round(se, 6),
            "ci": [round(draws[int(lo_q * (n - 1))], 6),
                   round(draws[int(hi_q * (n - 1))], 6)],
            "n_games": len(games),
            "note": "診斷用；硬門檻仍以點估計比較，本 CI 不進判定"}


def band_cluster_bootstrap(innings: Sequence[int], scored: Sequence[tuple], *,
                           reps: int = THRESHOLDS["boot_reps"],
                           ci: float = THRESHOLDS["boot_ci"],
                           seed: int = SEED) -> dict[str, dict]:
    """逐局帶 game-cluster bootstrap（整場重抽）。

    同場打席共享同一賽果 ⇒ 有效樣本≈場數；逐 PA binomial 誤差會嚴重低估帶級
    偏差的不確定度。與 winprob_val.cluster_bootstrap_devs 同語意，改以局帶分組。
    """
    by_game: dict[object, dict[str, list[float]]] = {}
    for inn, (p, y, _irr, gk) in zip(innings, scored, strict=True):
        g = by_game.setdefault(gk, {b: [0.0, 0.0, 0.0] for b in BANDS})
        a = g[band_of(inn)]
        a[0] += p
        a[1] += y
        a[2] += 1
    games = list(by_game.values())
    rng = random.Random(seed)
    devs: dict[str, list[float]] = defaultdict(list)
    for _ in range(reps):
        agg = {b: [0.0, 0.0, 0.0] for b in BANDS}
        for g in rng.choices(games, k=len(games)):
            for b in BANDS:
                agg[b][0] += g[b][0]
                agg[b][1] += g[b][1]
                agg[b][2] += g[b][2]
        for b in BANDS:
            if agg[b][2]:
                devs[b].append((agg[b][0] - agg[b][1]) / agg[b][2])
    return _ci_from_draws(devs, ci)


def _ci_from_draws(devs: dict, ci: float) -> dict:
    """bootstrap 抽樣 → 未捨入的 (se, ci)。

    **不得捨入**：紅線 4／5 的硬門檻直接讀這些值（iteration 1 查核 F1：捨入後
    貼近邊界的 CI 會被錯誤判為含 0 或排除 0）。顯示用捨入由報告層自行處理。
    """
    lo_q, hi_q = (1 - ci) / 2, 1 - (1 - ci) / 2
    out: dict = {}
    for key, ds in devs.items():
        ds.sort()
        n = len(ds)
        mean = sum(ds) / n
        se = (sum((d - mean) ** 2 for d in ds) / max(n - 1, 1)) ** 0.5
        out[key] = {"se": se, "ci": [ds[int(lo_q * (n - 1))], ds[int(hi_q * (n - 1))]]}
    return out


def home_rate_exact(cur, kind: str, y0: int, y1: int, as_of: date) -> float:
    """訓練窗聯盟主隊勝率的**未捨入**值（和=0.5）；leakage-safe 主場常數基準。

    與 `winprob_val.home_rate_from_games()` 同一個 SQL，但該函式回傳前捨入 4 位
    （iteration 2 查核 F1a：硬門檻的 `baseline_home_const.brier_raw` 因而只是
    「對已捨入 p 的未捨入計算」）。此處不捨入，並吃 `as_of` 而非 `CURRENT_DATE`。
    """
    cur.execute(
        "SELECT avg(CASE WHEN home_score>away_score THEN 1.0 "
        "WHEN home_score<away_score THEN 0.0 ELSE 0.5 END) FROM cpbl.games "
        "WHERE year BETWEEN %s AND %s AND kind_code=%s "
        "AND home_score+away_score>0 AND game_date<=%s", (y0, y1, kind, as_of))
    v = cur.fetchone()[0]
    return float(v) if v is not None else 0.5


def raw_ece(scored: Sequence[tuple]) -> float:
    """樣本加權 ECE 的**未捨入**值；gamma 選型 tie-break 用（iteration 2 查核 F1b）。

    `winprob_val.metrics()["ece_weighted"]` 由捨入 4 位的 decile 均值算出、最後再
    捨入 5 位；當 gamma 的 Brier 差 < 1e-5 而落到 ECE tie-break 時可能選錯 gamma。
    本函式直接由未捨入的 `decile_stats()` 重算。
    """
    st = decile_stats(scored)
    n = sum(d["n"] for d in st.values())
    return sum(abs(d["dev"]) * d["n"] for d in st.values()) / n if n else 0.0


def decile_stats(scored: Sequence[tuple]) -> dict[int, dict]:
    """池化十分位的**未捨入** (n, pred, actual, dev)；紅線 4 的判定輸入。

    winprob_val.metrics() 的 deciles 會捨入 4 位（顯示用），iteration 1 查核 F1
    指出以其比較 0.03 門檻違反「全部判定使用未捨入值」，故在此獨立重算。
    """
    acc: dict[int, list[float]] = {i: [0.0, 0.0, 0.0] for i in range(10)}
    for p, y, _irr, _gk in scored:
        a = acc[min(int(p * 10), 9)]
        a[0] += p
        a[1] += y
        a[2] += 1
    return {i: {"n": int(a[2]), "pred": a[0] / a[2], "actual": a[1] / a[2],
                "dev": (a[0] - a[1]) / a[2]}
            for i, a in acc.items() if a[2]}


def decile_cluster_bootstrap(scored: Sequence[tuple], *,
                             reps: int = THRESHOLDS["boot_reps"],
                             ci: float = THRESHOLDS["boot_ci"],
                             seed: int = SEED) -> dict[int, dict]:
    """十分位 game-cluster bootstrap，回傳**未捨入** CI（同語意於 band 版）。"""
    by_game: dict[object, dict[int, list[float]]] = {}
    for p, y, _irr, gk in scored:
        g = by_game.setdefault(gk, {i: [0.0, 0.0, 0.0] for i in range(10)})
        a = g[min(int(p * 10), 9)]
        a[0] += p
        a[1] += y
        a[2] += 1
    games = list(by_game.values())
    rng = random.Random(seed)
    devs: dict[int, list[float]] = defaultdict(list)
    for _ in range(reps):
        agg = {i: [0.0, 0.0, 0.0] for i in range(10)}
        for g in rng.choices(games, k=len(games)):
            for i in range(10):
                agg[i][0] += g[i][0]
                agg[i][1] += g[i][1]
                agg[i][2] += g[i][2]
        for i in range(10):
            if agg[i][2]:
                devs[i].append((agg[i][0] - agg[i][1]) / agg[i][2])
    return _ci_from_draws(devs, ci)


# ───────────────────────── 選型（決定性 tie-break；紅線 3） ─────────────────────────
@dataclass
class PriorCandidate:
    kappa: int
    lam: float
    brier: float
    logloss: float
    model: PriorModel = field(repr=False)


def better_prior(cand: PriorCandidate, best: PriorCandidate | None) -> bool:
    """逐場 Brier 最低者勝；未捨入差 < 1e-5 依序：log-loss → 較大 lambda → 較大 kappa。

    掃描順序固定為 kappa 升冪 → lambda 升冪（見 KAPPA_GRID／LAMBDA_GRID），
    故 epsilon 比較在同一輸入下完全決定性。
    """
    if best is None:
        return True
    d = cand.brier - best.brier
    if abs(d) >= TIE_EPS:
        return d < 0
    d = cand.logloss - best.logloss
    if abs(d) >= TIE_EPS:
        return d < 0
    if cand.lam != best.lam:
        return cand.lam > best.lam
    if cand.kappa != best.kappa:
        return cand.kappa > best.kappa
    return False


@dataclass
class GammaCandidate:
    gamma: float
    brier: float
    ece: float


def better_gamma(cand: GammaCandidate, best: GammaCandidate | None) -> bool:
    """逐 PA Brier 最低者勝；差 < 1e-5 比 ECE；再同分依 gamma=1 → 2 → 0.5。"""
    if best is None:
        return True
    d = cand.brier - best.brier
    if abs(d) >= TIE_EPS:
        return d < 0
    d = cand.ece - best.ece
    if abs(d) >= TIE_EPS:
        return d < 0
    return GAMMA_TIE_RANK[cand.gamma] < GAMMA_TIE_RANK[best.gamma]


# ───────────────────────── 嵌套 walk-forward 主流程 ─────────────────────────
@dataclass
class SeasonPack:
    """單季 base 評分包：wf 預測（span ≤ Y−1）＋逐 PA 對齊資訊。"""

    year: int
    span_end: int
    scored: list[tuple[float, float, bool, object]]
    innings: list[int]
    ts: list[float]
    snos: list[int]
    p_base0: float
    coverage: float                  # 顯示用（winprob_val 已捨入 4 位）
    coverage_raw: float              # 未捨入 build coverage（判定用；紅線 4）
    effective_coverage: float        # 未捨入「有 published build **且**有賽前特徵」佔完成場比例
    n_completed_games: int
    n_scored_games: int              # 實際進入評分的完成場數（＝ effective coverage 分子）
    n_irregular_games: int
    pa_state_counts: dict
    home_p: float
    excluded_no_prior: int


def _rows_md5(rows: Sequence[GameRow]) -> str:
    """實際餵給模型的 GameRow 的內容摘要（含 team_feats 與四組 Counts／來源層級）。

    比「完成場 sno 集合」嚴格得多：比分修訂、gamelog 補值、`game_features` 重算都會改變
    這裡的值，而 sno 集合完全看不出來（iteration 3 查核 F1）。float 走 `json.dumps` 的
    repr（最短往返表示），同一份輸入必得同一個摘要。
    """
    payload = json.dumps([asdict(r) for r in sorted(rows, key=lambda r: (r.year, r.game_sno))],
                         sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.md5(payload.encode("utf-8")).hexdigest()


def population_fingerprint(cur, as_of: date, rows: Sequence[GameRow],
                           scored_snos: dict[int, set[int]]) -> dict:
    """輸入指紋——`as_of` 只鎖日期界限，鎖不住入庫狀態，故另存內容摘要供漂移偵測。

    iteration 2 查核 F2 的實測教訓：同一個 `--as-of 2026-07-26`，在不同時點重跑會得到
    216 vs 219 場——那 3 場的 `game_date` 早在界限內，只是**比分後來才入庫**。因此
    「日期截止」不等於「輸入可重現」。

    iteration 3 查核 F1：只 hash 完成場 sno 集合，偵測不到比分／先發投手／`game_features`
    被修訂、同場 PA 重新發布、gamelog 補值——場數與 sno 全都沒變，數字卻會變。故本版
    涵蓋三層，任一層變動都看得見：

    1. `games_md5`   完成場的 sno＋比分＋延賽別（抓比分修訂與完成場判定翻轉）。
    2. `model_inputs_md5` **實際進入模型的 GameRow**（抓上游任何影響特徵的變動）。
    3. `published_builds_md5` **實際被評分的那些場**的 published build identity（build_id＋
       builder／taxonomy 版本；抓 PA 重新發布——它會改變評分母體卻不動 games）。範圍限定在
       評分母體而非整季：iteration 4 查核 F4 實測，`--as-of 2026-06-30` 的模型母體只有 177 場，
       整季查詢卻記下 216 個 build，多出的 39 場在截止日之後，會造成保守型假陽性漂移。

    紅線 8（經需求方 2026-07-27 sign-off 放寬為漂移偵測）：本指紋只保證「漂移可被偵測且
    fail loudly」，不保證能重建舊結果——真正逐位重建需要輸入快照，成本超出本卡。
    """
    cur.execute(
        "SELECT year, count(*), "
        "       md5(string_agg(game_sno::text, ',' ORDER BY game_sno)), "
        "       md5(string_agg(game_sno || ':' || home_score || '-' || away_score "
        "                      || ':' || coalesce(delay_kind, ''), ',' ORDER BY game_sno)) "
        "FROM cpbl.games WHERE kind_code=%s AND year BETWEEN %s AND %s "
        "AND home_score + away_score > 0 AND game_date <= %s GROUP BY year ORDER BY year",
        (KIND, CORE_FIRST, LAST_YEAR, as_of))
    per_year = {int(y): {"n_completed": int(n), "sno_md5": h, "games_md5": g}
                for y, n, h, g in cur.fetchall()}
    rows_by_year: dict[int, list[GameRow]] = defaultdict(list)
    for r in rows:
        rows_by_year[r.year].append(r)
    for y, entry in per_year.items():
        entry["model_inputs_md5"] = _rows_md5(rows_by_year.get(y, []))
        entry["n_model_rows"] = len(rows_by_year.get(y, []))
    builds: dict[int, dict] = {}
    for y in sorted(scored_snos):
        snos = sorted(scored_snos[y])
        cur.execute(
            "SELECT count(*), md5(string_agg(game_sno || ':' || build_id::text || ':' "
            "                     || builder_version || ':' || taxonomy_version, "
            "                     ',' ORDER BY game_sno)) "
            "FROM cpbl.game_recap_builds "
            "WHERE year=%s AND kind_code=%s AND state='published' AND game_sno = ANY(%s)",
            (y, KIND, snos))
        n, digest = cur.fetchone()
        builds[y] = {"n_published": int(n or 0), "n_scored_games": len(snos),
                     "build_md5": digest}
    return {"note": "as_of 只鎖 game_date 界限；晚到入庫／比分修訂／PA 重新發布仍會改變輸入，"
                    "故三層內容摘要（games／model inputs／published builds）供漂移偵測",
            "by_year": per_year,
            "published_builds_by_eval_year": builds,
            "model_inputs_md5": _rows_md5(rows),
            "n_completed_total": sum(v["n_completed"] for v in per_year.values())}


def fingerprint_diff(expected: dict, actual: dict) -> list[str]:
    """兩份指紋的逐項差異（空 list ＝ 輸入未漂移）。

    比對刻意逐鍵展開而非整體 hash：漂移時要能直接說出「2026 的 model inputs 變了」，
    而不是只丟一句「不一致」讓重跑者自己找。
    """
    diffs: list[str] = []
    if expected.get("model_inputs_md5") != actual.get("model_inputs_md5"):
        diffs.append("全域 model_inputs_md5 不一致")
    for label, key in (("完成場", "by_year"), ("published build", "published_builds_by_eval_year")):
        exp, act = expected.get(key) or {}, actual.get(key) or {}
        for y in sorted({*map(str, exp), *map(str, act)}):
            e, a = exp.get(y) or exp.get(int(y)) or {}, act.get(y) or act.get(int(y)) or {}
            for field_name in sorted({*e, *a}):
                if e.get(field_name) != a.get(field_name):
                    diffs.append(f"{label} {y} 的 {field_name}："
                                 f"{e.get(field_name)} → {a.get(field_name)}")
    return diffs


def _built_snos(season: dict) -> set[int]:
    """該季有 published build 的完成場 sno 集合（由 pa_state_counts 無法還原，改由 pas 推導）。"""
    return {p["game_sno"] for p in season["pas"]}


# `load_eval_season()` 判定 pre_state 是否可用的欄位；此處必須與上游完全一致。
_PRE_STATE_REQUIRED = ("inning", "half", "outs", "home_score", "away_score")


def _pa_state_counts_as_of(cur, year: int, as_of: date, as_of_snos: set[int],
                           pre_score_source: str = "events") -> dict:
    """`pa_state_counts` 的 as-of 版本。

    上游 `load_eval_season()` 的 PA 查詢**完全沒有日期界限**，`games` 那一半才以
    `CURRENT_DATE` 為界；直接沿用會讓這個欄位隨當下全表漂移（iteration 3 查核 F1）。
    winprob_val 是本卡禁改區（紅線 1），故在此以相同判準重算：

    - state 計數：涵蓋 `game_date <= as_of` 的所有 published PA（對應上游的「無日期界限」，
      把界限換成 as_of）。
    - `ready_incomplete_state`：僅在**完成場**（as_of 母體）且 `pre_state` 關鍵欄位缺值時計入，
      與上游 `sno not in games → continue` 的順序一致。

    - `ready_pre_score_unresolved`：ML-WP-VAL-RESAMPLE1 起上游改以事件流解打席前比分，
      解不出來的 ready 打席 fail closed 排除；此處以同一支 `_resolve_pre_scores()`
      重算，判準與順序（state → 完成場 → pre_state 完整 → 比分可解）逐條對齊上游。

    兩處判準日後分岔是這個重算最大的風險，故以
    `test_as_of_pa_state_counts_match_upstream_when_as_of_is_future` 釘住：as_of 取未來日時，
    本函式輸出必須與 `load_eval_season()` 的 `pa_state_counts` 逐鍵相同。
    """
    cur.execute(
        "SELECT pa.game_sno, pa.state, pa.pre_state, pa.pa_index, pa.start_event_no "
        "FROM cpbl.game_plate_appearances pa "
        "JOIN cpbl.game_recap_builds b ON b.build_id = pa.build_id "
        "  AND b.state = 'published' "
        "JOIN cpbl.games g ON g.year = pa.year AND g.kind_code = pa.kind_code "
        "  AND g.game_sno = pa.game_sno "
        "WHERE pa.year=%s AND pa.kind_code=%s AND g.game_date <= %s",
        (year, KIND, as_of))
    fetched = list(cur.fetchall())
    pa_rows_by_game: dict[int, list[dict]] = defaultdict(list)
    for sno, _state, _pre, pa_index, start_event_no in fetched:
        pa_rows_by_game[sno].append({"pa_index": pa_index, "start_event_no": start_event_no})
    pre_scores = (_resolve_pre_scores(cur, KIND, year, pa_rows_by_game)
                  if pre_score_source == "events" else None)
    counts: Counter = Counter()
    for sno, state, pre, pa_index, _start in fetched:
        counts[state] += 1
        if state != "ready" or sno not in as_of_snos:
            continue
        if any((pre or {}).get(f) is None for f in _PRE_STATE_REQUIRED):
            counts["ready_incomplete_state"] += 1
            continue
        if pre_scores is not None and (sno, pa_index) not in pre_scores:
            counts["ready_pre_score_unresolved"] += 1
    return dict(counts)


def build_season_pack(cur, per_year, year: int, span_end: int,
                      known_snos: set[int], as_of: date,
                      pre_score_source: str = "events") -> SeasonPack | None:
    """以 span [2018, span_end] 的 base run_dist 評 `year` 的 canonical PA。

    fail closed：無賽前特徵的場次（例：缺 game_features 列）整場排除並計數，
    不以同季快照或代理值補（紅線 2）。

    **coverage 三值**（iteration 1 查核 F1／F3）：
    - `coverage`：winprob_val 的顯示值（已捨入 4 位），只供報告呈現。
    - `coverage_raw`：未捨入的 published build coverage，判定用。
    - `effective_coverage`：**實際進入評分的完成場 ÷ 完成場**——同時要求 published build
      與賽前特徵。原實作把缺賽前特徵的場次靜默排除卻仍沿用 build coverage，理論上可在
      縮小後的母體上維持 1.0 並通過 gate；改以交集計算後該漏洞關閉。
    """
    season = load_eval_season(cur, KIND, year, pre_score_source=pre_score_source)
    if not season["pas"]:
        return None
    # `load_eval_season()` 內部以 CURRENT_DATE 為界（winprob_val，本卡不得修改），
    # 故在此依 as_of 重新界定完成場母體——否則進行中賽季每次重跑母體都會漂移，
    # 部分重跑無法逐位重現（iteration 2 查核 F2）。
    cur.execute(
        "SELECT game_sno FROM cpbl.games WHERE year=%s AND kind_code=%s "
        "AND home_score + away_score > 0 AND game_date <= %s", (year, KIND, as_of))
    as_of_snos = {r[0] for r in cur.fetchall()}
    dist = dist_from_counts(per_year, CORE_FIRST, span_end)
    scored_all = score_pas(dist, season["rules"], season["pas"])
    keep = [i for i, p in enumerate(season["pas"])
            if p["game_sno"] in known_snos and p["game_sno"] in as_of_snos]
    excluded = sum(1 for p in season["pas"]
                   if p["game_sno"] in as_of_snos and p["game_sno"] not in known_snos)
    pas = [season["pas"][i] for i in keep]
    n_completed = len(as_of_snos)
    n_scored = len({p["game_sno"] for p in pas})
    coverage_raw = (len(as_of_snos & _built_snos(season)) / n_completed) if n_completed else 0.0
    # 以下三個欄位原本直接取自 `season`（＝`load_eval_season()`，以 CURRENT_DATE 為界），
    # 故 `as_of` 之後才入庫的比賽仍會改變它們——artifact 標著 data_as_of 卻不是該日的內容
    # （iteration 3 查核 F1）。改為一律由 as_of 母體重算。
    return SeasonPack(
        year=year, span_end=span_end,
        scored=[scored_all[i] for i in keep],
        innings=[p["inning"] for p in pas],
        ts=[progress_t(p["inning"], p["vht"], p["outs"]) for p in pas],
        snos=[p["game_sno"] for p in pas],
        p_base0=opening_wp(dist, year),
        coverage=round(coverage_raw, 4),   # 顯示值＝未捨入值的 4 位（判定一律讀 raw）
        coverage_raw=coverage_raw,
        effective_coverage=(n_scored / n_completed) if n_completed else 0.0,
        n_completed_games=n_completed,
        n_scored_games=n_scored,
        n_irregular_games=sum(1 for sno in as_of_snos
                              if season["games"].get(sno, {}).get("irregular")),
        pa_state_counts=_pa_state_counts_as_of(cur, year, as_of, as_of_snos,
                                               pre_score_source),
        home_p=home_rate_exact(cur, KIND, CORE_FIRST, span_end, as_of),
        excluded_no_prior=excluded,
    )


def fuse_season(pack: SeasonPack, p0_by_sno: dict[int, float],
                gamma: float) -> list[tuple[float, float, bool, object]]:
    return [(fuse(wp, p0_by_sno[sno], t, gamma, pack.p_base0), y, irr, gk)
            for (wp, y, irr, gk), sno, t in zip(pack.scored, pack.snos, pack.ts,
                                                strict=True)]


def fit_prior(rows: Sequence[GameRow], lg: LeagueRates, kappa: int, lam: float,
              keys: Sequence[str] = FEATURE_KEYS) -> PriorModel:
    feats = [game_features(r, lg, kappa) for r in rows]
    return fit_logistic_l2(feats, [r.y for r in rows], keys=keys, lam=lam,
                           kappa=kappa, fit_years=sorted({r.year for r in rows}))


def predict_prior(model: PriorModel, rows: Sequence[GameRow],
                  lg: LeagueRates, kappa: int) -> dict[int, float]:
    return {r.game_sno: model.predict(game_features(r, lg, kappa)) for r in rows}


def run_strength(out_path: Path, val_seasons: Sequence[int],
                 as_of: date | None = None,
                 expect_fingerprint: dict | None = None,
                 pre_score_source: str = "events") -> dict:
    result: dict = {
        "card": "GAME-RECAP-WP-STRENGTH1",
        "kind": KIND,
        # ML-WP-VAL-RESAMPLE1：局面分差的打席前比分來源。events＝事件流（唯一正確）；
        # pre_state＝受污染的舊讀法，僅供 A/B 對照，產出不得作為對外數字。
        "pre_score_source": pre_score_source,
        "core_span": [CORE_FIRST, LAST_YEAR],
        "val_seasons": list(val_seasons),
        "feature_keys": list(FEATURE_KEYS),
        "grids": {"kappa": list(KAPPA_GRID), "lambda": list(LAMBDA_GRID),
                  "gamma": list(GAMMA_GRID)},
        "thresholds": {**THRESHOLDS, **STRENGTH_THRESHOLDS},
        "seed": SEED,
        "data_as_of": (as_of or date.today()).isoformat(),
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "seasons": [],
    }
    with conn() as c:
        cur = c.cursor()
        rows = load_game_rows(cur, as_of=as_of)
        by_year: dict[int, list[GameRow]] = defaultdict(list)
        for r in rows:
            by_year[r.year].append(r)
        result["population"] = {
            "n_games": len(rows),
            "by_year": {y: len(v) for y, v in sorted(by_year.items())},
            "tie_games": sum(1 for r in rows if r.y == 0.5),
            "source_tiers": _tier_counts(rows),
        }
        log.info("賽前母體：%d 場（%s）", len(rows),
                 ", ".join(f"{y}:{len(v)}" for y, v in sorted(by_year.items())))

        per_year = collect_training_counts(cur, KIND, CORE_FIRST, LAST_YEAR)
        # base wf 評分包：季 s 用 span [2018, s−1]（= winprob_val 的 walk-forward）
        need = sorted({y for Y in val_seasons for y in (Y - 1, Y)})
        packs: dict[int, SeasonPack] = {}
        for s in need:
            known = {r.game_sno for r in by_year.get(s, ())}
            pack = build_season_pack(cur, per_year, s, s - 1, known, as_of or date.today(),
                                     pre_score_source)
            if pack:
                packs[s] = pack
                assert pack.span_end <= s - 1, f"wf {s} base span 洩漏"
                log.info("base wf %d [%d-%d]：n_pa=%d p_base0=%.5f cov=%.4f",
                         s, CORE_FIRST, pack.span_end, len(pack.scored),
                         pack.p_base0, pack.coverage)

        pooled: dict[str, list] = {"base": [], "adj": []}
        pooled_innings: list[int] = []
        pooled_baseline_num = 0.0
        for Y in val_seasons:
            srow = _run_one_season(cur, Y, by_year, packs)
            if srow is None:
                continue
            result["seasons"].append(srow["report"])
            pooled["base"].extend(srow["base_scored"])
            pooled["adj"].extend(srow["adj_scored"])
            pooled_innings.extend(srow["innings"])
            pooled_baseline_num += (srow["report"]["baseline_home_const"]["brier_raw"]
                                    * len(srow["base_scored"]))

        result["advanced_shadow_2026"] = advanced_shadow(cur, rows)
        # `advanced_shadow()` 讀 advanced_stats／pitch_tracking／gamelog 的**當下全季累計**，
        # 完全不吃 as_of；標成 `data_as_of` 會讓讀者以為它是那一天的內容（iteration 3 查核 F1）。
        # 改標 observed_at＝觀測時刻，並明示它不在逐位比對範圍內。
        result["advanced_shadow_2026"]["observed_at"] = result["generated_at"]
        result["advanced_shadow_2026"]["as_of_bounded"] = False
        result["advanced_shadow_2026"]["excluded_from_bitwise_compare"] = (
            "本節不吃 as_of，隨當下全表變動；比對重跑輸出時須與 generated_at 一併排除")
        # 先驗訊號四路對照原本只有 `--diagnostics` 印在終端、報告 §6.2 靠人工謄寫，
        # 於是它成了 iteration 3 查核 F2 的 8 處過期數字之二。寫進 artifact 後，
        # 報告該表改由 `scripts/strength1_report_tables.py` 產生，過期在結構上不可能。
        result["prior_signal_diagnostics"] = prior_signal_diagnostics(cur, rows)
        result["population_fingerprint"] = population_fingerprint(
            cur, as_of or date.today(), rows,
            {Y: set(packs[Y].snos) for Y in val_seasons if Y in packs})
        if expect_fingerprint is not None:
            diffs = fingerprint_diff(expect_fingerprint, result["population_fingerprint"])
            if diffs:
                # fail loudly（紅線 8）：輸入已漂移就不得靜默產出「看起來像重現」的數字。
                raise RuntimeError(
                    "輸入指紋與期望不符，重跑無法對照既有 artifact；差異：\n  "
                    + "\n  ".join(diffs))

    if pooled["base"]:
        # `metrics()` 的 brier／deciles／CI 皆為捨入顯示值；判定另存 *_raw／raw_deciles／
        # decile_boot 三組未捨入值（紅線 4；iteration 1 查核 F1）。
        pooled_out: dict = {
            fam: {**metrics(pooled[fam], bootstrap=True),
                  "brier_raw": raw_brier(pooled[fam]),
                  "raw_deciles": decile_stats(pooled[fam]),
                  "decile_boot": decile_cluster_bootstrap(pooled[fam])}
            for fam in ("base", "adj")
        }
        pooled_out["baseline_home_const_brier"] = round(
            pooled_baseline_num / len(pooled["base"]), 5)
        pooled_out["brier_delta_diagnostic"] = brier_delta_bootstrap(
            pooled["base"], pooled["adj"])
        result["pooled"] = pooled_out
        result["pooled_inning_bands"] = {
            fam: {"display": band_summary(pooled_innings, pooled[fam]),
                  "raw": band_stats(pooled_innings, pooled[fam]),
                  "boot": band_cluster_bootstrap(pooled_innings, pooled[fam])}
            for fam in ("base", "adj")
        }
        result["verdict"] = strength_verdict(
            result["seasons"], result["pooled"]["adj"],
            result["pooled_inning_bands"]["base"], result["pooled_inning_bands"]["adj"],
            complete=sorted(val_seasons) == list(range(VAL_FIRST, VAL_LAST + 1)))
    else:
        result["verdict"] = {"status": "unsupported", "reasons": ["無可評樣本"],
                             "disclosure": []}

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=1))
    log.info("artifact → %s", out_path)
    return result


def _tier_counts(rows: Sequence[GameRow]) -> dict:
    """先發／牛棚 rate 的資訊來源層級分佈（own/prior/league）——降級可見性。"""
    out: dict[str, dict[str, int]] = {"starter": defaultdict(int), "bullpen": defaultdict(int)}
    for r in rows:
        for t in r.sp_source:
            out["starter"][t] += 1
        for t in r.bp_source:
            out["bullpen"][t] += 1
    return {k: dict(sorted(v.items())) for k, v in out.items()}


def nested_windows(Y: int) -> tuple[list[int], int, list[int]]:
    """驗證季 Y 的嵌套窗口（紅線 1；唯一定義處）。

    回傳 (inner_fit=2018..Y−2, inner_selection=Y−1, final_fit=2018..Y−1)。
    超參／gamma 只能看 inner_fit 擬合後對 Y−1 的 out-of-time 預測；鎖定後才以
    final_fit 重擬合並「只」評 Y。三者皆 ≤ Y−1，與 Y 嚴格分離。
    """
    inner_fit = list(range(CORE_FIRST, Y - 1))
    sel_year = Y - 1
    final_fit = list(range(CORE_FIRST, Y))
    if not inner_fit or max(inner_fit) >= sel_year or sel_year >= Y:
        raise ValueError(f"驗證季 {Y} 無法構成嵌套窗口（inner={inner_fit} sel={sel_year}）")
    assert max(final_fit) == Y - 1, "final fit 窗必須止於 Y−1"
    return inner_fit, sel_year, final_fit


def _run_one_season(cur, Y: int, by_year: dict[int, list[GameRow]],
                    packs: dict[int, SeasonPack]) -> dict | None:
    """單一驗證季的完整嵌套程序（inner 選型 → final refit → 只評 Y）。"""
    inner_fit_years, sel_year, final_fit_years = nested_windows(Y)
    if Y not in packs or sel_year not in packs:
        log.warning("驗證季 %d 缺 base 評分包，略過", Y)
        return None

    inner_rows = [r for y in inner_fit_years for r in by_year.get(y, ())]
    sel_rows = by_year.get(sel_year, [])
    final_rows = [r for y in final_fit_years for r in by_year.get(y, ())]
    if not inner_rows or not sel_rows:
        log.warning("驗證季 %d 內部窗樣本不足，略過", Y)
        return None

    # 1) (kappa, lambda) 選型：fit 2018..Y−2 → 只看 Y−1 的 out-of-time 逐場 Brier
    lg_inner = league_rates(cur, CORE_FIRST, Y - 2)
    sel_y = [r.y for r in sel_rows]
    best: PriorCandidate | None = None
    grid_rows = []
    for kappa in KAPPA_GRID:
        for lam in LAMBDA_GRID:
            model = fit_prior(inner_rows, lg_inner, kappa, lam)
            preds = [model.predict(game_features(r, lg_inner, kappa)) for r in sel_rows]
            cand = PriorCandidate(kappa, lam, game_brier(preds, sel_y),
                                  game_logloss(preds, sel_y), model)
            grid_rows.append({"kappa": kappa, "lambda": lam,
                              "sel_brier": round(cand.brier, 6),
                              "sel_logloss": round(cand.logloss, 6)})
            if better_prior(cand, best):
                best = cand
    assert best is not None
    log.info("Y=%d 先驗選型：kappa=%d lambda=%g（Y−1=%d Brier=%.6f）",
             Y, best.kappa, best.lam, sel_year, best.brier)

    # 2) gamma 選型：以選定 (kappa,lambda) 對 Y−1 產生 p0，融合同代 base（span ≤ Y−2）
    sel_pack = packs[sel_year]
    p0_sel = predict_prior(best.model, sel_rows, lg_inner, best.kappa)
    missing = [s for s in set(sel_pack.snos) if s not in p0_sel]
    assert not missing, f"選型季 {sel_year} 缺 p0 的場次：{missing[:5]}"
    best_g: GammaCandidate | None = None
    gamma_rows = []
    for gamma in GAMMA_GRID:
        fused = fuse_season(sel_pack, p0_sel, gamma)
        cand = GammaCandidate(gamma, raw_brier(fused), raw_ece(fused))
        gamma_rows.append({"gamma": gamma, "sel_brier": round(cand.brier, 6),
                           "sel_ece": round(cand.ece, 6)})
        if better_gamma(cand, best_g):
            best_g = cand
    assert best_g is not None
    log.info("Y=%d gamma 選型：%.1f（Y−1 融合 Brier=%.6f，未融合 %.6f）",
             Y, best_g.gamma, best_g.brier, raw_brier(sel_pack.scored))

    # 3) 鎖定超參後才以 2018..Y−1 重 fit；base 亦換 span 2018..Y−1；只評 Y
    lg_final = league_rates(cur, CORE_FIRST, Y - 1)
    final_model = fit_prior(final_rows, lg_final, best.kappa, best.lam)
    pack = packs[Y]
    val_rows = by_year.get(Y, [])
    p0_val = predict_prior(final_model, val_rows, lg_final, best.kappa)
    missing = [s for s in set(pack.snos) if s not in p0_val]
    assert not missing, f"驗證季 {Y} 缺 p0 的場次：{missing[:5]}"
    adj_scored = fuse_season(pack, p0_val, best_g.gamma)

    base_m = metrics(pack.scored, bootstrap=True)
    adj_m = metrics(adj_scored, bootstrap=True)
    val_y = [r.y for r in val_rows]
    p0_list = [p0_val[r.game_sno] for r in val_rows]

    # 消融（僅診斷；full 是唯一驗收候選）
    ablation = {}
    for name, keys in ABLATIONS.items():
        m_ab = fit_prior(final_rows, lg_final, best.kappa, best.lam, keys=keys)
        preds_ab = [m_ab.predict(game_features(r, lg_final, best.kappa)) for r in val_rows]
        p0_ab = {r.game_sno: p for r, p in zip(val_rows, preds_ab, strict=True)}
        ab_scored = fuse_season(pack, p0_ab, best_g.gamma)
        ablation[name] = {
            "n_features": len(keys),
            "p0_game_brier": round(game_brier(preds_ab, val_y), 6),
            "fused_pa_brier": round(raw_brier(ab_scored), 6),
            "coef_standardized": m_ab.params()["coef_standardized"],
        }

    report = {
        "year": Y,
        "holdout_sealed": Y == VAL_LAST,
        "windows": {
            "inner_fit": [inner_fit_years[0], inner_fit_years[-1]],
            "inner_selection": sel_year,
            "final_fit": [final_fit_years[0], final_fit_years[-1]],
            "base_model_span": f"{CORE_FIRST}-{pack.span_end}/{KIND}",
            "validation": Y,
        },
        "coverage": pack.coverage,                        # 顯示用（已捨入）
        "coverage_raw": pack.coverage_raw,                # 判定用（未捨入；紅線 4）
        "effective_coverage": pack.effective_coverage,    # 判定用（build ∩ 賽前特徵；F3）
        "n_scored_games": pack.n_scored_games,
        "n_completed_games": pack.n_completed_games,
        "n_irregular_games": pack.n_irregular_games,
        "n_val_games": len(val_rows),
        "pa_state_counts": pack.pa_state_counts,
        "excluded_pa_no_pregame_features": pack.excluded_no_prior,
        "selection": {
            "chosen": {"kappa": best.kappa, "lambda": best.lam, "gamma": best_g.gamma},
            "prior_grid": grid_rows,
            "gamma_grid": gamma_rows,
            "inner_league_rates": lg_inner.as_dict(),
            "inner_model": best.model.params(),
            "selection_season_base_brier": round(raw_brier(sel_pack.scored), 6),
        },
        "final_model": final_model.params(),
        "final_league_rates": lg_final.as_dict(),
        "p_base0": round(pack.p_base0, 5),
        "p0_diagnostics": {
            "n_games": len(val_rows),
            "game_brier": round(game_brier(p0_list, val_y), 6),
            "game_logloss": round(game_logloss(p0_list, val_y), 6),
            "baseline_home_const_game_brier": round(
                game_brier([pack.home_p] * len(val_y), val_y), 6),
            "mean_p0": round(sum(p0_list) / len(p0_list), 5),
            "min_p0": round(min(p0_list), 5), "max_p0": round(max(p0_list), 5),
        },
        "baseline_home_const": {"p": pack.home_p,
                                "brier": brier_constant(pack.scored, pack.home_p),
                                "brier_raw": sum((pack.home_p - y) ** 2
                                                 for _, y, _, _ in pack.scored)
                                / len(pack.scored)},
        "base": {**base_m, "brier_raw": raw_brier(pack.scored)},
        "adjusted": {**adj_m, "brier_raw": raw_brier(adj_scored)},
        "brier_delta_diagnostic": brier_delta_bootstrap(pack.scored, adj_scored),
        "inning_bands": {
            "base": {"display": band_summary(pack.innings, pack.scored),
                     "raw": band_stats(pack.innings, pack.scored)},
            "adjusted": {"display": band_summary(pack.innings, adj_scored),
                         "raw": band_stats(pack.innings, adj_scored)},
        },
        "ablation": ablation,
    }
    log.info("Y=%d base Brier=%.6f → adj %.6f（主場基準 %.6f，cov=%.4f）",
             Y, report["base"]["brier_raw"], report["adjusted"]["brier_raw"],
             report["baseline_home_const"]["brier_raw"], pack.coverage)
    return {"report": report, "base_scored": pack.scored, "adj_scored": adj_scored,
            "innings": pack.innings}


# ───────────────────────── 2026 advanced shadow（診斷；不進判定） ─────────────────────────
def advanced_shadow(cur, rows: Sequence[GameRow]) -> dict:
    """2026 官方 advanced／TrackMan 的 coverage 與相關性。

    **明確不進本卡候選集合、超參選型或 Go/No-Go**（紅線 3）：`advanced_stats` 只有
    2026 的**全季累計**快照、無 as-of 時間版本，對歷史賽前模型不可重建；逐球
    TrackMan 亦有球場端設備缺場。此節只回答「若未來有 as-of snapshot，這些欄位與
    核心指標的關係如何」，並由 `GAME-RECAP-WP-STRENGTH-ADV1` 另卡處理。
    """
    cur.execute(
        "SELECT count(*) FILTER (WHERE role='pitching'), count(*) FILTER (WHERE role='batting') "
        "FROM cpbl.advanced_stats WHERE year=2026")
    n_pit, n_bat = cur.fetchone()
    cur.execute(
        "SELECT count(DISTINCT game_sno), count(*) FROM cpbl.pitch_tracking "
        "WHERE year=2026 AND kind_code=%s", (KIND,))
    tm_games, tm_pitches = cur.fetchone()
    n_2026 = sum(1 for r in rows if r.year == 2026)

    # 相關性：2026 全季 gamelog 彙總（先發身分）vs 官方進階欄位——皆為季末量，
    # 只可回答「概念是否對齊」，不可用於任何賽前預測。
    cur.execute(
        "SELECT pitcher_acnt, sum(plate_appearances), sum(so), sum(bb), "
        "       sum(pitch_cnt), sum(strike_cnt) "
        "FROM cpbl.pitching_gamelog WHERE kind_code=%s AND year=2026 AND role_type='先發' "
        "GROUP BY pitcher_acnt HAVING sum(plate_appearances) >= 100", (KIND,))
    core = {}
    for pid, pa, so, bb, pitch, strike in cur.fetchall():
        if pa and pitch:
            core[pid] = {"kbb": (float(so or 0) - float(bb or 0)) / float(pa),
                         "strike_share": float(strike or 0) / float(pitch)}
    cur.execute(
        "SELECT acnt, whiffp, chasep, kp, bbp FROM cpbl.advanced_stats "
        "WHERE year=2026 AND role='pitching'")
    adv = {a: {"whiffp": w, "chasep": ch, "kp": k, "bbp": b}
           for a, w, ch, k, b in cur.fetchall()}
    joined = [(core[p], adv[p]) for p in core if p in adv]
    corr = {}
    for cm in ("kbb", "strike_share"):
        for am in ("whiffp", "chasep", "kp", "bbp"):
            xs = [(c[cm], a[am]) for c, a in joined if a[am] is not None]
            corr[f"{cm}~{am}"] = round(_pearson(xs), 4) if len(xs) >= 10 else None
    return {
        "note": "僅診斷／前瞻蒐集；不進候選集合、超參選型或 Go/No-Go（卡面紅線 3）",
        "advanced_stats_2026": {"pitching_rows": n_pit, "batting_rows": n_bat,
                                "as_of_snapshot": False,
                                "reason_unusable": "只有全季累計、無時間版本 → 歷史賽前狀態不可重建"},
        "pitch_tracking_2026_A": {"games_with_tracking": tm_games,
                                  "completed_games": n_2026,
                                  "coverage": round(tm_games / n_2026, 4) if n_2026 else None,
                                  "pitches": tm_pitches,
                                  "reason_unusable": "球場端設備缺場；缺場機制尚未查核"},
        "season_end_correlation": {"n_starters_joined": len(joined), "pearson": corr},
    }


DIAG_KAPPA, DIAG_LAMBDA = 100, 100.0     # 診斷用固定超參（不參與任何選型）


def prior_signal_diagnostics(cur, rows: Sequence[GameRow]) -> list[dict]:
    """先驗訊號的四路對照（**診斷，不進判定**；紅線 3／7）。

    回答「p0 的弱訊號是實作不足還是資料本身沒有」：

    - `in_sample`：同窗擬合同窗評分 → 管線確實能找到訊號時應明顯優於常數。
    - `out_of_time`：本卡正式用法（fit 2018..Y−1 → 評 Y）。
    - `home_const`：leakage-safe 主場常數基準。
    - `leaky_same_season`：加入 `game_features` 的 `starter_era_diff`／`whip`／`k9`。

      ⚠️ **此欄的語意取決於 `cpbl.game_features` 當下的內容，非本模組可自證**。
      2026-07-27 之前該三欄由 `features/outcome.py` 以 `(starter_id, year)` 讀**同季
      彙總**（＝卡面紅線 2 禁用的洩漏欄），此對照因而能量化「若違規會看到多大的
      假性改善」；**`ML-OUTCOME-LEAK1`（merge 5a683d1）已將該三欄改為 leakage-safe
      的賽前 as-of 值**，故本對照在該 merge 之後不再產生假性改善——這是預期行為，
      不是缺陷。iteration 1 查核 F2 即由此不一致觸發。
      **教訓（已納入報告 §6.2）**：依賴可變 DB 狀態的診斷不構成可重現證據；
      artifact 未快照輸入即無法自證。洩漏本身的存在改由不依賴本 harness 的證據
      確立（見 `ML-OUTCOME-LEAK1` 的變異測試與 DB 層反證）。
    - `late_season`：雙方皆已打 ≥40 場後的子集 → 檢驗弱訊號是否只是季初
      running state 噪音。

    超參固定為 kappa=100／lambda=100，與正式選型無關，避免此診斷回頭影響判定。
    """
    by_year: dict[int, list[GameRow]] = defaultdict(list)
    for r in rows:
        by_year[r.year].append(r)
    cur.execute(
        "SELECT year, game_sno, starter_era_diff, starter_whip_diff, starter_k9_diff "
        "FROM cpbl.game_features WHERE kind_code=%s AND year BETWEEN %s AND %s",
        (KIND, CORE_FIRST, LAST_YEAR))
    leaky = {(y, s): {"starter_era_diff": -float(e or 0.0),
                      "starter_whip_diff": -float(w or 0.0),
                      "starter_k9_diff": float(k or 0.0)}
             for y, s, e, w, k in cur.fetchall()}
    leaky_keys = FEATURE_KEYS + ("starter_era_diff", "starter_whip_diff",
                                 "starter_k9_diff")
    out = []
    for Y in range(VAL_FIRST, VAL_LAST + 1):
        fit_rows = [r for y in range(CORE_FIRST, Y) for r in by_year.get(y, ())]
        val_rows = by_year.get(Y, [])
        if not fit_rows or not val_rows:
            continue
        lg = league_rates(cur, CORE_FIRST, Y - 1)
        ff = [game_features(r, lg, DIAG_KAPPA) for r in fit_rows]
        vf = [game_features(r, lg, DIAG_KAPPA) for r in val_rows]
        fy = [r.y for r in fit_rows]
        vy = [r.y for r in val_rows]
        m = fit_logistic_l2(ff, fy, keys=FEATURE_KEYS, lam=DIAG_LAMBDA, kappa=DIAG_KAPPA)
        ml = fit_logistic_l2([{**f, **leaky[(r.year, r.game_sno)]}
                              for f, r in zip(ff, fit_rows, strict=True)], fy,
                             keys=leaky_keys, lam=DIAG_LAMBDA, kappa=DIAG_KAPPA)
        seen: dict[str, int] = defaultdict(int)
        late = []
        for r, f in zip(val_rows, vf, strict=True):
            if seen[r.home_team] >= 40 and seen[r.away_team] >= 40:
                late.append((f, r.y))
            seen[r.home_team] += 1
            seen[r.away_team] += 1
        const_p = sum(fy) / len(fy)
        out.append({
            "year": Y,
            "fit_window": [CORE_FIRST, Y - 1],
            "n_fit_games": len(fit_rows), "n_val_games": len(val_rows),
            "in_sample": round(game_brier([m.predict(f) for f in ff], fy), 6),
            "out_of_time": round(game_brier([m.predict(f) for f in vf], vy), 6),
            "home_const": round(game_brier([const_p] * len(vy), vy), 6),
            "leaky_same_season": round(game_brier(
                [ml.predict({**f, **leaky[(r.year, r.game_sno)]})
                 for f, r in zip(vf, val_rows, strict=True)], vy), 6),
            "late_season": round(game_brier([m.predict(f) for f, _ in late],
                                            [y for _, y in late]), 6) if late else None,
            "late_season_const": round(game_brier([const_p] * len(late),
                                                  [y for _, y in late]), 6) if late else None,
            "n_late_games": len(late),
        })
    return out


def run_diagnostics(as_of: date | None = None) -> list[dict]:
    with conn() as c:
        cur = c.cursor()
        return prior_signal_diagnostics(cur, load_game_rows(cur, as_of=as_of))


def _pearson(xs: Sequence[tuple[float, float]]) -> float:
    n = len(xs)
    mx = sum(a for a, _ in xs) / n
    my = sum(b for _, b in xs) / n
    sxy = sum((a - mx) * (b - my) for a, b in xs)
    sxx = sum((a - mx) ** 2 for a, _ in xs)
    syy = sum((b - my) ** 2 for _, b in xs)
    return sxy / math.sqrt(sxx * syy) if sxx > 0 and syy > 0 else 0.0


# ───────────────────────── Go/No-Go（紅線 4/5；一律未捨入值） ─────────────────────────
# 條號與規則敘述的**唯一定義處**；報告 §5 由 `verdict.gate_results` 格式化，不得自行複述。
GATE_RULES: tuple[tuple[str, str], ...] = (
    ("4a", "任一季 coverage 或 effective coverage < 0.98"),
    ("4b", "任一季 Brier 未勝主場常數基準"),
    ("4c", "**任一季 Brier 劣於同代未融合 base**"),
    ("4d", "池化十分位 n≥1000 且 |dev|>0.03 且 99% CI 排除 0"),
    ("5a", "池化局帶 n≥1000 且 |dev|>0.03 且 99% CI 排除 0"),
    ("5b", "單帶 |dev| 惡化 >2pt，或 ≥2 帶各惡化 >1pt"),
    ("8", "全部預註冊驗證季皆執行"),
)
def strength_verdict(season_rows: Sequence[dict], pooled_adj: dict,
                     pooled_bands_base: dict, pooled_bands_adj: dict,
                     *, complete: bool = True) -> dict:
    """A scope（含戰力先驗融合）Go/No-Go。硬性失敗任一 → unsupported（No-Go）。

    - 任一驗證季 **coverage 或 effective coverage** < 0.98；
    - 任一驗證季融合後 Brier 未勝主場常數基準，或劣於同代未融合 base；
    - 池化十分位 n≥1000 且 |dev| > 0.03 且 99% game-cluster CI 排除 0；
    - 池化局帶 n≥1000 且 |dev| > 0.03 且 99% CI 排除 0；
    - 例行局帶相對同代 base 系統性惡化（單帶 >2pt，或 ≥2 帶各 >1pt）。

    **全部輸入皆為未捨入值**（紅線 4）。iteration 1 查核 F1 指出三條捨入路徑
    （coverage 4 位、metrics() deciles 4 位、bootstrap CI 4/5 位）會讓貼近邊界的
    值被錯誤判定，已改為讀 `coverage_raw`／`effective_coverage`／`raw_deciles`／
    `decile_boot`；`metrics()` 的捨入值僅供報告顯示。
    F3：`effective_coverage` 要求「published build **且**有賽前特徵」，關閉「靜默
    排除缺特徵場次後在縮小母體上維持 1.0」的漏洞。
    """
    hard: list[str] = []
    disclosure: list[str] = []
    # 逐條門檻的歸因。`hard` 的內容與順序完全不變（附加而非改寫），另外記下每個
    # 失敗屬於哪一條，供報告 §5 直接格式化——iteration 5 查核 F1：報告腳本原本
    # 為了印那張表**重寫了一次門檻邏輯**，四條各有落差（4a 漏 effective coverage、
    # 4d 漏 |dev| 上限、5a 漏 CI 條件、5b 規則寫反），報告因此可能顯示與真實判定
    # 相反的結果。判定只能有一條路徑，報告只負責格式化。
    by_gate: dict[str, list[str]] = defaultdict(list)
    evidence: dict[str, str] = {}

    def fail(gate: str, message: str) -> None:
        hard.append(message)
        by_gate[gate].append(message)

    for s in season_rows:
        tag = f"A{s['year']}"
        adj, base, hc = s["adjusted"], s["base"], s["baseline_home_const"]
        # 紅線 4：coverage 一律讀**未捨入**值（iteration 1 查核 F1：真實 0.97996 會被
        # 捨入為 0.9800 而錯誤通過）。並同時把 effective coverage（要求 published build
        # **且**有賽前特徵）納入硬門檻（F3：否則可在縮小後母體上維持 1.0 過關）。
        for label, value in (("coverage", s["coverage_raw"]),
                             ("effective coverage", s["effective_coverage"])):
            if value < THRESHOLDS["min_coverage"]:
                fail("4a", f"{tag} {label} {value:.6f} < {THRESHOLDS['min_coverage']}")
        if adj["brier_raw"] >= hc["brier_raw"]:
            fail("4b", f"{tag} 融合後 Brier {adj['brier_raw']:.6f} 未勝主場常數基準 "
                       f"{hc['brier_raw']:.6f}")
        if adj["brier_raw"] > base["brier_raw"]:
            fail("4c", f"{tag} 融合後 Brier {adj['brier_raw']:.6f} 劣於同代未融合 base "
                       f"{base['brier_raw']:.6f}")
        if adj.get("significant_bins"):
            disclosure.append(f"{tag} 逐季顯著偏差分箱 {adj['significant_bins']}"
                              "（99% 叢集 CI 排除 0）")
    # 紅線 4：十分位判定改讀 decile_stats／decile_cluster_bootstrap 的**未捨入**值，
    # 不再使用 winprob_val.metrics() 捨入 4 位的顯示 deciles（iteration 1 查核 F1）。
    raw_dec, boot_dec = pooled_adj["raw_deciles"], pooled_adj["decile_boot"]
    for b in sorted(raw_dec):
        d = raw_dec[b]
        ci = boot_dec.get(b, {}).get("ci")
        if ci is None or d["n"] < 1000:
            continue
        if ci[0] > 0 or ci[1] < 0:
            if abs(d["dev"]) > THRESHOLDS["pooled_bin_dev_max"]:
                fail("4d", f"池化十分位 {b} 偏差 {d['dev']:+.6f} 顯著且超過 "
                           f"±{THRESHOLDS['pooled_bin_dev_max']}（n={d['n']}）")
            else:
                disclosure.append(f"池化十分位 {b} 偏差 {d['dev']:+.6f} 顯著但幅度受控"
                                  f"（n={d['n']}）")
    worsened: list[str] = []
    raw_base, raw_adj = pooled_bands_base["raw"], pooled_bands_adj["raw"]
    boot_adj = pooled_bands_adj["boot"]
    for b in REGULATION_BANDS:
        pb, cb = raw_base.get(b), raw_adj.get(b)
        if not pb or not cb:
            continue
        ci = boot_adj.get(b, {}).get("ci")
        if (cb["n"] >= STRENGTH_THRESHOLDS["band_min_n"]
                and abs(cb["dev"]) > STRENGTH_THRESHOLDS["band_dev_max"]
                and ci is not None and (ci[0] > 0 or ci[1] < 0)):
            fail("5a", f"池化局帶 {b} 偏差 {cb['dev']:+.4f} 顯著且超過 "
                       f"±{STRENGTH_THRESHOLDS['band_dev_max']}（n={cb['n']}）")
        delta = abs(cb["dev"]) - abs(pb["dev"])
        if delta > STRENGTH_THRESHOLDS["band_worsen_hard_pt"]:
            fail("5b", f"局帶 {b} |dev| 相對同代 base 惡化 {delta * 100:+.1f}pt > 2pt")
        elif delta > STRENGTH_THRESHOLDS["band_worsen_pt"]:
            worsened.append(b)
            disclosure.append(f"局帶 {b} |dev| 相對同代 base 惡化 {delta * 100:+.1f}pt")
    if len(worsened) >= 2:
        fail("5b", f"例行局帶系統性惡化：{worsened} 皆 |dev| 增 >1pt")
    if "10+" in raw_adj and "10+" in raw_base:
        disclosure.append(
            f"10+ 帶（含 2024+ 突破僵局，n={raw_adj['10+']['n']}，僅揭露不作判定證據）："
            f"base |dev| {abs(raw_base['10+']['dev']) * 100:.1f}pt → "
            f"融合後 {abs(raw_adj['10+']['dev']) * 100:.1f}pt")
    if not complete:
        fail("8", "部分重跑：未涵蓋全部預註冊驗證季 2023–2026，不得作 Go 證據")

    years = [s["year"] for s in season_rows]
    evidence["4a"] = "；".join(
        f"{s['year']} {s['coverage_raw']:.6f}／{s['effective_coverage']:.6f}"
        for s in season_rows) + "（coverage／effective）"
    margins = {s["year"]: s["baseline_home_const"]["brier_raw"] - s["adjusted"]["brier_raw"]
               for s in season_rows}
    if margins:
        lo, hi = min(margins, key=margins.get), max(margins, key=margins.get)
        evidence["4b"] = f"最小優勢 {margins[lo]:.4f}（{lo}）、最大 {margins[hi]:.4f}（{hi}）"
    evidence["4c"] = "；".join(
        f"{s['year']} {s['adjusted']['brier_raw'] - s['base']['brier_raw']:+.6f}"
        for s in season_rows)
    evidence["4d"] = (f"顯著且超限分箱 {len(by_gate['4d'])} 個"
                      if by_gate["4d"] else "無分箱同時顯著且 |dev| 超限")
    band_devs = {b: raw_adj[b]["dev"] for b in REGULATION_BANDS if b in raw_adj}
    evidence["5a"] = ("；".join(f"{b} {d:+.5f}" for b, d in band_devs.items())
                      if band_devs else "—")
    gaps = {b: (abs(raw_adj[b]["dev"]) - abs(raw_base[b]["dev"])) * 100
            for b in REGULATION_BANDS if b in raw_adj and b in raw_base}
    evidence["5b"] = ("；".join(f"{b} {g:+.2f}pt" for b, g in gaps.items())
                      if gaps else "—")
    evidence["8"] = (f"{min(years)}–{max(years)}（{len(years)} 季）" if years else "無驗證季")

    return {"status": "unsupported" if hard else "supported",
            "reasons": hard, "disclosure": disclosure,
            # 報告 §5 直接讀這裡格式化；**不得**在報告端重新判定（iteration 5 查核 F1）。
            "gate_results": [
                {"gate": gate, "rule": rule, "passed": not by_gate[gate],
                 "failures": by_gate[gate], "evidence": evidence.get(gate, "—")}
                for gate, rule in GATE_RULES
            ]}


# ───────────────────────── CLI ─────────────────────────
def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    ap = argparse.ArgumentParser(description="GAME-RECAP-WP-STRENGTH1 戰力感知先驗（唯讀）")
    ap.add_argument("--out", default="docs/research/game_recap_wp_strength1_metrics.json",
                    help="artifact 路徑；部分重跑務必導向 scratch（紅線 8）")
    ap.add_argument("--seasons", default="",
                    help="逗號分隔的驗證季（預設 2023-2026 全跑）")
    ap.add_argument("--as-of", default="",
                    help="資料截止日 YYYY-MM-DD（預設今日）。進行中賽季的部分重跑務必指定，"
                         "否則完成場母體會隨時間漂移而無法逐位重現（artifact 的 data_as_of）")
    ap.add_argument("--expect-fingerprint", default="",
                    help="既有 artifact 路徑；跑之前比對輸入指紋，不符即中止（紅線 8 漂移偵測）。"
                         "重跑要與既有數字對照時務必指定，否則輸入已變也看不出來")
    ap.add_argument("--diagnostics", action="store_true",
                    help="只印先驗訊號四路對照（診斷；不寫 artifact、不進判定）")
    ap.add_argument("--pre-score-source", default="events", choices=list(PRE_SCORE_SOURCES),
                    help="局面分差的打席前比分來源。events＝事件流（預設，唯一正確）；"
                         "pre_state＝已知受污染的舊讀法，只給 ML-WP-VAL-RESAMPLE1 的 A/B "
                         "對照用，產出不得作為對外數字")
    args = ap.parse_args()
    as_of = date.fromisoformat(args.as_of) if args.as_of else None
    expect = (json.loads(Path(args.expect_fingerprint).read_text(encoding="utf-8"))
              .get("population_fingerprint") if args.expect_fingerprint else None)
    if args.diagnostics:
        print("先驗訊號診斷（固定 kappa=100 lambda=100；不進 Go/No-Go）")
        print(f"{'Y':>5} {'in-sample':>10} {'out-of-time':>12} {'主場常數':>9} "
              f"{'洩漏對照':>9} {'後半季':>8} {'後半季常數':>11}")
        for d in run_diagnostics(as_of):
            late = f"{d['late_season']:.6f}" if d["late_season"] is not None else "—"
            late_c = f"{d['late_season_const']:.6f}" if d["late_season_const"] else "—"
            print(f"{d['year']:>5} {d['in_sample']:>10.6f} {d['out_of_time']:>12.6f} "
                  f"{d['home_const']:>9.6f} {d['leaky_same_season']:>9.6f} "
                  f"{late:>8} {late_c:>11}  (n_late={d['n_late_games']})")
        print("『洩漏對照』欄讀 game_features 的 starter_era/whip/k9；其語意取決於該表當下內容，")
        print("ML-OUTCOME-LEAK1（merge 5a683d1）已將該三欄改為 leakage-safe，故該欄不再顯示假性")
        print("改善——此為預期行為。詳見報告 §6.2 的可重現性更正。")
        return
    seasons = ([int(s) for s in args.seasons.split(",") if s.strip()]
               or list(range(VAL_FIRST, VAL_LAST + 1)))
    result = run_strength(Path(args.out), sorted(seasons), as_of, expect,
                          args.pre_score_source)
    v = result["verdict"]
    print(f"\n=== GAME-RECAP-WP-STRENGTH1 A scope：{v['status']} ===")
    for label, items in (("硬性", v["reasons"]), ("揭露", v.get("disclosure", []))):
        for r in items:
            print(f"  [{label}] {r}")
    # 報告順序：2026 鎖箱 holdout 首列，再列歷史穩定性（紅線 7）
    for s in sorted(result["seasons"], key=lambda r: -r["year"]):
        sel = s["selection"]["chosen"]
        print(f"  {s['year']}{'（鎖箱 holdout）' if s['holdout_sealed'] else ''} "
              f"[fit {s['windows']['final_fit'][0]}-{s['windows']['final_fit'][1]}|"
              f"sel {s['windows']['inner_selection']}|k={sel['kappa']} "
              f"λ={sel['lambda']} γ={sel['gamma']}] "
              f"base={s['base']['brier_raw']:.6f} adj={s['adjusted']['brier_raw']:.6f} "
              f"主場基準={s['baseline_home_const']['brier_raw']:.6f} cov={s['coverage']}")
    pooled = result.get("pooled")
    if pooled:
        for fam in ("base", "adj"):
            m = pooled[fam]
            print(f"  池化 {fam}: n_pa={m['n_pa']} Brier={m['brier_raw']:.6f} "
                  f"ECE={m['ece_weighted']} 顯著分箱={m.get('significant_bins')}")
        print(f"  池化主場常數基準 Brier={pooled['baseline_home_const_brier']}")
        for fam in ("base", "adj"):
            raw = result["pooled_inning_bands"][fam]["raw"]
            print(f"  池化局帶 {fam}: "
                  + " ".join(f"{b}={raw[b]['dev'] * 100:+.1f}pt(n={raw[b]['n']})"
                             for b in BANDS if b in raw))


if __name__ == "__main__":
    main()
