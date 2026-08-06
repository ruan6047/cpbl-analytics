"""GAME-RECAP-WP-STRENGTH1 離線合約測試（零 DB 依賴）。

覆蓋卡面驗收條列的合約：三期 routing、八項凍結特徵與方向、逐場分子／分母只含
該場前事件、kappa 收縮與缺值 fallback、和局 y=0.5 的加權拆分等價且 game
weighting 不變、嵌套窗口、選型只讀 inner season、決定性 tie-break、w(t) 單調
與端點、開場 anchor、[0,1] 與固定狀態單調性，以及 v2 門檻未被放寬。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date

import pytest

from cpbl.models.winprob_strength import (
    ABLATIONS,
    COLD_START_YEAR,
    CORE_FIRST,
    FEATURE_KEYS,
    GAMMA_GRID,
    KAPPA_GRID,
    LAMBDA_GRID,
    STRENGTH_THRESHOLDS,
    VAL_FIRST,
    VAL_LAST,
    Counts,
    GammaCandidate,
    LeagueRates,
    PriorCandidate,
    band_stats,
    better_gamma,
    better_prior,
    bullpen_kbb,
    fit_logistic_l2,
    fuse,
    game_features,
    league_rates,
    load_game_rows,
    logit_clip,
    nested_windows,
    nll_and_grad,
    opening_wp,
    progress_t,
    shrink,
    starter_metrics,
    strength_verdict,
)
from cpbl.models.winprob_val import THRESHOLDS

LG = LeagueRates(
    years=(2018, 2019), sp_kbb=0.10, sp_strike_share=0.64, sp_hr_ip=0.10,
    sp_bb_ip=0.30, sp_hbp_ip=0.05, sp_so_ip=0.78, bp_kbb=0.09,
    pitch_per_pa=3.8, ip_per_pa=0.23, n_sp_pa=1000.0, n_bp_pa=800.0,
)


# ───────────────────────── 凍結基線（防臨時增刪） ─────────────────────────
def test_feature_keys_frozen():
    assert FEATURE_KEYS == (
        "prior_winpct_diff", "winrate_diff", "run_margin_diff", "rest_days_diff",
        "starter_kbb_adv", "starter_recorded_strike_share_adv",
        "starter_fip_proxy_adv", "bullpen_kbb_adv")


def test_grids_and_ablations_frozen():
    assert KAPPA_GRID == (50, 100, 200)
    assert LAMBDA_GRID == (0.1, 1.0, 10.0, 100.0)
    assert GAMMA_GRID == (0.5, 1.0, 2.0)
    assert ABLATIONS["team_only"] == FEATURE_KEYS[:4]
    assert ABLATIONS["team_starter"] == FEATURE_KEYS[:7]
    assert ABLATIONS["full"] == FEATURE_KEYS


def test_v2_thresholds_not_relaxed():
    """紅線 4：沿用 WP-VAL1 v2，只可加嚴。"""
    assert THRESHOLDS["pooled_bin_dev_max"] == 0.03
    assert THRESHOLDS["min_coverage"] == 0.98
    assert THRESHOLDS["boot_ci"] == 0.99
    assert THRESHOLDS["boot_reps"] == 500
    assert STRENGTH_THRESHOLDS == {"band_min_n": 1000, "band_dev_max": 0.03,
                                   "band_worsen_pt": 0.01, "band_worsen_hard_pt": 0.02}


def test_three_era_routing_constants():
    """三期邊界：≤2017 只作冷啟動 prior、核心自 2018、驗證 2023–2026。"""
    assert COLD_START_YEAR == 2017
    assert CORE_FIRST == 2018
    assert (VAL_FIRST, VAL_LAST) == (2023, 2026)


# ───────────────────────── 嵌套窗口（紅線 1） ─────────────────────────
@pytest.mark.parametrize("Y", [2023, 2024, 2025, 2026])
def test_nested_windows_strictly_separated(Y):
    inner, sel, final = nested_windows(Y)
    assert inner[0] == CORE_FIRST and inner[-1] == Y - 2
    assert sel == Y - 1
    assert final[0] == CORE_FIRST and final[-1] == Y - 1
    assert max(inner) < sel < Y            # 超參只看 out-of-time 的 Y−1
    assert Y not in inner and Y not in final and sel not in inner


def test_nested_windows_reject_too_early():
    """2019 之前無法構成 inner fit ⇒ 拒絕，不得靜默退化成 in-sample 選型。"""
    with pytest.raises(ValueError):
        nested_windows(2019)


# ───────────────────────── 融合語意合約（紅線 6） ─────────────────────────
def test_progress_t_endpoints_and_monotone():
    assert progress_t(1, "1", 0) == 0.0                 # 開場
    assert progress_t(9, "2", 2) == pytest.approx(53 / 54)
    assert progress_t(10, "1", 0) == 1.0                # 延長賽夾為 1
    assert progress_t(12, "2", 2) == 1.0
    seq = [progress_t(i, h, o) for i in range(1, 10) for h in ("1", "2")
           for o in (0, 1, 2)]
    assert seq == sorted(seq)


@pytest.mark.parametrize("gamma", GAMMA_GRID)
def test_weight_decreasing_with_fixed_endpoints(gamma):
    w = [(1.0 - progress_t(i, h, o)) ** gamma
         for i in range(1, 11) for h in ("1", "2") for o in (0, 1, 2)]
    assert w[0] == 1.0                                   # w(0)=1
    assert w[-1] == 0.0                                  # 9 局完成後恆 0
    assert all(a >= b - 1e-15 for a, b in zip(w, w[1:], strict=False))  # 不增


@pytest.mark.parametrize("gamma", GAMMA_GRID)
def test_fuse_opening_anchor_equals_p0(gamma):
    """t=0 且 WP_situ=p_base0 ⇒ WP_adj=p0（避免重複計入主場優勢）。"""
    for p0 in (0.35, 0.5, 0.54, 0.7):
        assert fuse(0.538, p0, 0.0, gamma, 0.538) == pytest.approx(p0, abs=1e-9)


@pytest.mark.parametrize("gamma", GAMMA_GRID)
def test_fuse_strictly_monotone_in_wp_situ(gamma):
    out = [fuse(w, 0.62, 0.3, gamma, 0.53) for w in
           [0.01, 0.1, 0.25, 0.5, 0.75, 0.9, 0.99]]
    assert all(a < b for a, b in zip(out, out[1:], strict=False))


def test_fuse_range_and_canonical_endpoints():
    for w in (0.0, 1e-9, 0.5, 1 - 1e-9, 1.0):
        for p0 in (0.01, 0.5, 0.99):
            v = fuse(w, p0, 0.2, 1.0, 0.53)
            assert 0.0 <= v <= 1.0
    # 終場／再見的 canonical 端點不經 clip 與融合
    assert fuse(0.0, 0.99, 0.0, 1.0, 0.53) == 0.0
    assert fuse(1.0, 0.01, 0.0, 1.0, 0.53) == 1.0


def test_fuse_zero_weight_is_identity():
    """w(t)=0（9 局完成／延長賽）⇒ 完全不調整。"""
    for w in (0.2, 0.5, 0.87):
        assert fuse(w, 0.9, 1.0, 1.0, 0.53) == pytest.approx(w, abs=1e-12)


def test_logit_clip_finite_at_extremes():
    assert math.isfinite(logit_clip(0.0)) and math.isfinite(logit_clip(1.0))
    assert logit_clip(0.5) == pytest.approx(0.0)


def test_opening_wp_uses_supplied_generation():
    """p_base0 取自傳入的該代 dist；不同代 ⇒ 不同 anchor（不得跨代借用）。"""
    def toy(p_home_extra: float) -> dict:
        d: dict = {}
        for side in ("1", "2"):
            for bases in ("___", "1__", "_2_", "__3", "12_", "1_3", "_23", "123"):
                for outs in (0, 1, 2):
                    q = 0.72 - (p_home_extra if side == "2" else 0.0)
                    d[(side, bases, outs)] = [q, 1 - q, 0.0, 0.0, 0.0, 0.0, 0.0]
        return d
    a, b = opening_wp(toy(0.0), 2023), opening_wp(toy(0.05), 2023)
    assert 0.0 < a < 1.0 and 0.0 < b < 1.0
    assert a != b


# ───────────────────────── 部分池化收縮與 fallback ─────────────────────────
def test_shrink_endpoints_and_monotone_in_kappa():
    assert shrink(0.0, 0.0, 0.11, 100.0) == pytest.approx(0.11)   # 無當季資料 → prior
    assert shrink(50.0, 100.0, 0.11, 0.0) == pytest.approx(0.5)   # kappa=0 → 純當季
    pulls = [abs(shrink(50.0, 100.0, 0.11, k) - 0.5) for k in (0, 50, 100, 200)]
    assert pulls == sorted(pulls)                                  # kappa 越大越靠 prior
    # 分母增加 ⇒ 當季權重自然提高（卡面設計意圖）
    near = shrink(500.0, 1000.0, 0.11, 100.0)
    far = shrink(5.0, 10.0, 0.11, 100.0)
    assert abs(near - 0.5) < abs(far - 0.5)


def test_starter_metrics_fallback_tiers():
    """無當季且無前一季 → 聯盟率；有前一季 → 前一季（卡面 fallback 順序）。"""
    kbb, ss, fip = starter_metrics(Counts(), None, LG, 100)
    assert kbb == pytest.approx(LG.sp_kbb)
    assert ss == pytest.approx(LG.sp_strike_share)
    assert fip == pytest.approx(13 * LG.sp_hr_ip + 3 * (LG.sp_bb_ip + LG.sp_hbp_ip)
                                - 2 * LG.sp_so_ip)
    prior = Counts(pa=600, so=150, bb=30, hbp=10, hr=15, pitch=2300, strike=1500, ip=140)
    kbb2, ss2, _ = starter_metrics(Counts(), prior, LG, 100)
    assert kbb2 == pytest.approx((150 - 30) / 600)
    assert ss2 == pytest.approx(1500 / 2300)


def test_cold_start_prior_without_strike_falls_back_to_league():
    """2017 `pitching_seasons` 無好球數 ⇒ pitch/strike=0 ⇒ 好球率退聯盟率。"""
    prior = Counts(pa=600, so=150, bb=30, hbp=10, hr=15, pitch=0, strike=0, ip=140)
    _kbb, ss, _fip = starter_metrics(Counts(), prior, LG, 100)
    assert ss == pytest.approx(LG.sp_strike_share)


def test_kappa_converted_to_each_denominator():
    """kappa 是 PA-equivalent：非 PA 分母以 fit 窗 `分母/PA` 比換算，單一 kappa 控全部。"""
    own = Counts(pa=100, so=30, bb=5, hbp=2, hr=3, pitch=380, strike=250, ip=23)
    prior = Counts(pa=600, so=60, bb=60, hbp=10, hr=15, pitch=2280, strike=1300, ip=138)
    kbb, ss, _ = starter_metrics(own, prior, LG, 100)
    # 好球率的等效 kappa = 100 * pitch_per_pa
    assert ss == pytest.approx((250 + 100 * LG.pitch_per_pa * (1300 / 2280))
                               / (380 + 100 * LG.pitch_per_pa))
    assert kbb == pytest.approx((30 - 5 + 100 * (0 / 600)) / (100 + 100))


def test_fip_proxy_shrinks_components_then_combines():
    """卡面：四個事件計數各自收縮後才組合，禁止直接平均 FIP rate。"""
    own = Counts(pa=100, so=30, bb=5, hbp=2, hr=3, pitch=380, strike=250, ip=23)
    prior = Counts(pa=600, so=120, bb=40, hbp=8, hr=12, pitch=2280, strike=1450, ip=140)
    k_ip = 100 * LG.ip_per_pa
    exp = 0.0
    for coefficient, own_n, pri_n in ((13.0, own.hr, prior.hr), (3.0, own.bb, prior.bb),
                                      (3.0, own.hbp, prior.hbp), (-2.0, own.so, prior.so)):
        exp += coefficient * (own_n + k_ip * (pri_n / prior.ip)) / (own.ip + k_ip)
    assert starter_metrics(own, prior, LG, 100)[2] == pytest.approx(exp)


def test_bullpen_uses_bullpen_league_rate():
    assert bullpen_kbb(Counts(), None, LG, 100) == pytest.approx(LG.bp_kbb)
    assert LG.bp_kbb != LG.sp_kbb          # 角色分流，不互相借用


# ───────────────────────── 八項特徵方向（正值有利主隊） ─────────────────────────
def _row(**kw):
    from cpbl.models.winprob_strength import GameRow
    base = dict(
        year=2024, game_sno=1, game_date=date(2024, 4, 1),
        home_team="H", away_team="A", y=1.0,
        team_feats={"prior_winpct_diff": 0.0, "winrate_diff": 0.0,
                    "run_margin_diff": 0.0, "rest_days_diff": 0.0},
        home_sp=Counts(), away_sp=Counts(), home_sp_prior=None, away_sp_prior=None,
        home_bp=Counts(), away_bp=Counts(), home_bp_prior=None, away_bp_prior=None)
    base.update(kw)
    return GameRow(**base)


def test_neutral_inputs_give_zero_features():
    f = game_features(_row(), LG, 100)
    assert all(abs(f[k]) < 1e-12 for k in FEATURE_KEYS)


def test_starter_feature_directions():
    strong = Counts(pa=400, so=110, bb=20, hbp=4, hr=6, pitch=1500, strike=1000, ip=95)
    weak = Counts(pa=400, so=50, bb=60, hbp=12, hr=20, pitch=1600, strike=950, ip=90)
    f = game_features(_row(home_sp=strong, away_sp=weak), LG, 100)
    assert f["starter_kbb_adv"] > 0                       # 主隊先發三振保送較佳
    assert f["starter_recorded_strike_share_adv"] > 0
    assert f["starter_fip_proxy_adv"] > 0                 # 主隊 FIP 較低 ⇒ 正值
    swapped = game_features(_row(home_sp=weak, away_sp=strong), LG, 100)
    for k in ("starter_kbb_adv", "starter_recorded_strike_share_adv",
              "starter_fip_proxy_adv"):
        assert swapped[k] == pytest.approx(-f[k])          # 主客對調 ⇒ 反號


def test_bullpen_feature_direction():
    good = Counts(pa=300, so=90, bb=20)
    bad = Counts(pa=300, so=40, bb=50)
    f = game_features(_row(home_bp=good, away_bp=bad), LG, 100)
    assert f["bullpen_kbb_adv"] > 0


# ───────────────────────── 逐場 running state 不含該場（紅線 2） ─────────────────────────
GAMES_COLS = ("year", "game_sno", "game_date", "home_team_code", "away_team_code",
              "home_score", "away_score", "home_starter_id", "away_starter_id",
              "prior_winpct_diff", "winrate_diff", "runs_scored_diff",
              "runs_allowed_diff", "rest_days_diff")
PGLOG_COLS = ("year", "game_sno", "pitcher_acnt", "visiting_home_type", "role_type",
              "plate_appearances", "so", "bb", "hbp", "home_runs", "pitch_cnt",
              "strike_cnt", "inning_pitched_cnt", "inning_pitched_div3")


class FakeCursor:
    """依 SQL 內容分派的最小 cursor：讓 leakage 合約可離線驗證。"""

    def __init__(self, games, pglog, seasons_2017=()):
        self._games, self._pglog, self._s2017 = games, pglog, seasons_2017
        self._rows: list = []
        self.description: list = []

    def execute(self, sql, params=None):
        if "FROM cpbl.games g" in sql:
            self._rows, self.description = self._games, [(c,) for c in GAMES_COLS]
        elif "FROM cpbl.pitching_gamelog" in sql and "GROUP BY 1" in sql:
            self._rows, self.description = self._pglog_agg(), []
        elif "FROM cpbl.pitching_gamelog" in sql:
            self._rows, self.description = self._pglog, [(c,) for c in PGLOG_COLS]
        elif "FROM cpbl.pitching_seasons" in sql:
            self._rows, self.description = list(self._s2017), []
        else:
            raise AssertionError(f"未預期的查詢：{sql[:60]}")

    def _pglog_agg(self):
        out: dict[bool, list[float]] = {}
        for r in self._pglog:
            d = dict(zip(PGLOG_COLS, r, strict=True))
            a = out.setdefault(d["role_type"] == "先發", [0.0] * 8)
            for i, k in enumerate(("plate_appearances", "so", "bb", "hbp", "home_runs",
                                   "pitch_cnt", "strike_cnt")):
                a[i] += d[k]
            a[7] += d["inning_pitched_cnt"] + d["inning_pitched_div3"] / 3.0
        return [(k, *v) for k, v in out.items()]

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._rows[0]


def _pg(year, sno, pid, vht, role, pa, so, bb, hbp, hr, pitch, strike, ip, div3=0):
    return (year, sno, pid, vht, role, pa, so, bb, hbp, hr, pitch, strike, ip, div3)


def _gm(year, sno, day, hsp, asp):
    return (year, sno, date(year, 4, day), "H", "A", 5, 3, hsp, asp,
            0.0, 0.0, 0.0, 0.0, 0.0)


def test_running_state_excludes_the_game_itself():
    """紅線 2：該場的分子／分母都不得進入自己的賽前特徵。"""
    games = [_gm(2019, 1, 1, "P1", "P2"), _gm(2019, 2, 8, "P1", "P2")]
    pglog = [
        _pg(2019, 1, "P1", "2", "先發", 25, 7, 2, 1, 1, 95, 60, 6),
        _pg(2019, 1, "P2", "1", "先發", 24, 5, 3, 0, 2, 92, 57, 5),
        _pg(2019, 1, "R1", "2", "中繼", 10, 3, 1, 0, 0, 40, 25, 3),
        _pg(2019, 2, "P1", "2", "先發", 26, 9, 1, 0, 0, 99, 66, 7),
        _pg(2019, 2, "P2", "1", "先發", 22, 4, 4, 1, 1, 90, 55, 5),
    ]
    rows = load_game_rows(FakeCursor(games, pglog), 2019, 2019)
    assert [r.game_sno for r in rows] == [1, 2]
    # 第一場：季內尚無任何累計
    assert rows[0].home_sp.pa == 0 and rows[0].away_sp.pa == 0
    assert rows[0].home_bp.pa == 0
    assert rows[0].sp_source == ("league", "league")
    # 第二場：恰等於第一場的量，且不含第二場自身
    assert rows[1].home_sp.pa == 25 and rows[1].home_sp.so == 7
    assert rows[1].home_sp.strike == 60 and rows[1].home_sp.ip == pytest.approx(6.0)
    assert rows[1].away_sp.pa == 24
    assert rows[1].home_bp.pa == 10          # 只有中繼進牛棚，先發不算
    assert rows[1].away_bp.pa == 0
    assert rows[1].sp_source == ("own", "own")


def test_season_boundary_resets_running_state_but_keeps_prior():
    """跨季歸零；前一季總量改以 prior 進入收縮（不得跨季累加當季分母）。"""
    games = [_gm(2019, 1, 1, "P1", "P2"), _gm(2020, 1, 1, "P1", "P2")]
    pglog = [
        _pg(2019, 1, "P1", "2", "先發", 25, 7, 2, 1, 1, 95, 60, 6),
        _pg(2019, 1, "P2", "1", "先發", 24, 5, 3, 0, 2, 92, 57, 5),
        _pg(2020, 1, "P1", "2", "先發", 26, 9, 1, 0, 0, 99, 66, 7),
        _pg(2020, 1, "P2", "1", "先發", 22, 4, 4, 1, 1, 90, 55, 5),
    ]
    rows = load_game_rows(FakeCursor(games, pglog), 2019, 2020)
    y2020 = rows[1]
    assert y2020.year == 2020
    assert y2020.home_sp.pa == 0                      # 當季分母歸零
    assert y2020.home_sp_prior is not None
    assert y2020.home_sp_prior.pa == 25               # 前一季總量作 prior
    assert y2020.sp_source == ("prior", "prior")


def test_cold_start_prior_reads_only_2017_seasons_table():
    """三期 routing：2018 的 prior 來自 pitching_seasons(2017)，且無好球數。"""
    games = [_gm(2018, 1, 1, "P1", "P2")]
    pglog = [_pg(2018, 1, "P1", "2", "先發", 25, 7, 2, 1, 1, 95, 60, 6),
             _pg(2018, 1, "P2", "1", "先發", 24, 5, 3, 0, 2, 92, 57, 5)]
    s2017 = [("P1", 600, 150, 30, 10, 15, 140.0)]
    rows = load_game_rows(FakeCursor(games, pglog, s2017), 2018, 2018)
    prior = rows[0].home_sp_prior
    assert prior is not None and prior.pa == 600
    assert prior.pitch == 0.0 and prior.strike == 0.0      # 該表無好球數
    assert rows[0].away_sp_prior is None                   # 2017 無資料者不得虛構


def test_tie_label_from_scores_not_home_win():
    """和局標籤 0.5 由 games 比分建立；`game_features.home_win` 和局為 NULL 不可用。"""
    games = [(2019, 1, date(2019, 4, 1), "H", "A", 3, 3, "P1", "P2",
              0.0, 0.0, 0.0, 0.0, 0.0)]
    pglog = [_pg(2019, 1, "P1", "2", "先發", 25, 7, 2, 1, 1, 95, 60, 6)]
    assert load_game_rows(FakeCursor(games, pglog), 2019, 2019)[0].y == 0.5


def test_league_rates_split_by_role():
    pglog = [_pg(2019, 1, "P1", "2", "先發", 100, 30, 5, 2, 3, 380, 250, 23),
             _pg(2019, 1, "R1", "2", "中繼", 50, 10, 8, 1, 2, 200, 120, 11)]
    lg = league_rates(FakeCursor([], pglog), 2019, 2019)
    assert lg.sp_kbb == pytest.approx((30 - 5) / 100)
    assert lg.bp_kbb == pytest.approx((10 - 8) / 50)
    assert lg.pitch_per_pa == pytest.approx(380 / 100)     # 換算比只用先發口徑


# ───────────────────────── 和局軟標籤等價性（Gemini P3 finding） ─────────────────────────
def _split_rows(feats, ys):
    """把 y=0.5 拆成兩筆 weight 0.5 的 y=0/1；其餘 y 保持 weight 1。"""
    out = []
    for f, y in zip(feats, ys, strict=True):
        if y == 0.5:
            out += [(f, 1.0, 0.5), (f, 0.0, 0.5)]
        else:
            out.append((f, y, 1.0))
    return out


def _weighted_nll_and_grad(rows, keys, mean, std, theta, lam):
    from cpbl.models.winprob_strength import sigmoid
    loss = 0.0
    grad = [0.0] * len(theta)
    for f, y, w in rows:
        z = [(f[k] - m) / s if s > 0 else 0.0
             for k, m, s in zip(keys, mean, std, strict=True)]
        s_ = theta[0] + sum(theta[j + 1] * z[j] for j in range(len(z)))
        q = sigmoid(s_)
        loss -= w * (y * math.log(q) + (1 - y) * math.log(1 - q))
        d = w * (q - y)
        grad[0] += d
        for j in range(len(z)):
            grad[j + 1] += d * z[j]
    for j in range(1, len(theta)):
        loss += 0.5 * lam * theta[j] ** 2
        grad[j] += lam * theta[j]
    return loss, grad


def _toy_dataset(n=90):
    feats, ys = [], []
    for i in range(n):
        a = (i % 7) / 7.0 - 0.5
        b = ((i * 3) % 5) / 5.0 - 0.4
        feats.append({"a": a, "b": b})
        ys.append(0.5 if i % 11 == 0 else (1.0 if a + b > 0 else 0.0))
    return feats, ys


def test_tie_softlabel_loss_and_gradient_match_weighted_split():
    """卡面／Gemini P3：y=0.5 的自訂凸目標須與加權拆分逐項等價。"""
    feats, ys = _toy_dataset()
    keys = ("a", "b")
    from cpbl.models.winprob_strength import standardize_stats
    raw = [[f[k] for k in keys] for f in feats]
    mean, std = standardize_stats(raw)
    z = [[(r[j] - mean[j]) / std[j] for j in range(2)] for r in raw]
    for theta in ([0.0, 0.0, 0.0], [0.2, -0.7, 0.4], [-1.1, 0.3, 1.5]):
        soft_loss, soft_grad = nll_and_grad(z, ys, theta, lam=3.0)
        w_loss, w_grad = _weighted_nll_and_grad(_split_rows(feats, ys), keys, mean,
                                                std, theta, lam=3.0)
        assert soft_loss == pytest.approx(w_loss, rel=1e-12, abs=1e-12)
        for a, b in zip(soft_grad, w_grad, strict=True):
            assert a == pytest.approx(b, rel=1e-12, abs=1e-12)


def test_tie_softlabel_fit_matches_hard_split_fit():
    """擬合結果亦等價：把和局拆成 y=1／y=0 兩筆，係數與預測完全相同。

    以「整體 ×2」把 0.5 權重化為整數列：soft 每列複製兩次 vs split 中和局改為
    (y=1)+(y=0)、非和局複製兩次。兩者目標函數逐項相等，且特徵多重集合相同
    ⇒ 標準化統計亦相同 ⇒ 同一最優解。這正是卡面要求「不因拆列改變 game
    weighting」的可執行證明（每場總權重恆為 2）。
    """
    feats, ys = _toy_dataset()
    soft_f, soft_y, split_f, split_y = [], [], [], []
    for f, y in zip(feats, ys, strict=True):
        soft_f += [f, f]
        soft_y += [y, y]
        split_f += [f, f]
        split_y += ([1.0, 0.0] if y == 0.5 else [y, y])
    a = fit_logistic_l2(soft_f, soft_y, keys=("a", "b"), lam=3.0, kappa=100)
    b = fit_logistic_l2(split_f, split_y, keys=("a", "b"), lam=3.0, kappa=100)
    assert a.mean == b.mean and a.std == b.std       # 標準化統計不因拆列改變
    assert a.intercept == pytest.approx(b.intercept, abs=1e-9)
    for ca, cb in zip(a.coef, b.coef, strict=True):
        assert ca == pytest.approx(cb, abs=1e-9)
    probe = {"a": 0.21, "b": -0.34}
    assert a.predict(probe) == pytest.approx(b.predict(probe), abs=1e-9)


def test_tie_softlabel_objective_is_a_true_optimum():
    """soft 解在加權拆分目標下的梯度亦為 0（同一凸問題的同一駐點）。"""
    feats, ys = _toy_dataset()
    m = fit_logistic_l2(feats, ys, keys=("a", "b"), lam=3.0, kappa=100)
    z = [[(f[k] - mu) / sd for k, mu, sd
          in zip(("a", "b"), m.mean, m.std, strict=True)] for f in feats]
    theta = [m.intercept, *m.coef]
    _, grad = nll_and_grad(z, ys, theta, lam=3.0)
    _, wgrad = _weighted_nll_and_grad(_split_rows(feats, ys), ("a", "b"), m.mean,
                                      m.std, theta, lam=3.0)
    for a, b in zip(grad, wgrad, strict=True):
        assert a == pytest.approx(b, abs=1e-10)
    # 相對於目標尺度（sum over n 列）的梯度已可忽略
    assert max(abs(g) for g in grad) / len(feats) < 1e-6


def test_game_weighting_unchanged_by_split():
    """每場總權重恆為 1 ⇒ 拆列不改變 game weighting。"""
    feats, ys = _toy_dataset()
    rows = _split_rows(feats, ys)
    assert sum(w for _, _, w in rows) == pytest.approx(float(len(feats)))
    assert sum(1 for y in ys if y == 0.5) > 0     # 樣本確實含和局


# ───────────────────────── L2 邏輯斯迴歸 ─────────────────────────
def test_logistic_recovers_known_signal():
    feats, ys = [], []
    for i in range(400):
        a = ((i * 7) % 100) / 50.0 - 1.0
        feats.append({"a": a, "noise": ((i * 13) % 9) / 9.0})
        ys.append(1.0 if a > 0 else 0.0)          # 完全由 a 決定
    m = fit_logistic_l2(feats, ys, keys=("a", "noise"), lam=1.0, kappa=100)
    assert m.converged
    assert m.coef[0] > 1.0 and abs(m.coef[1]) < m.coef[0] / 4


def test_stronger_lambda_shrinks_coefficients():
    feats, ys = _toy_dataset(200)
    norms = []
    for lam in LAMBDA_GRID:
        m = fit_logistic_l2(feats, ys, keys=("a", "b"), lam=lam, kappa=100)
        assert m.converged
        norms.append(sum(c * c for c in m.coef))
    assert norms == sorted(norms, reverse=True)


def test_zero_variance_column_gets_zero_coefficient():
    feats, ys = _toy_dataset()
    for f in feats:
        f["const"] = 1.0
    m = fit_logistic_l2(feats, ys, keys=("a", "b", "const"), lam=1.0, kappa=100)
    assert m.std[2] == 0.0 and m.coef[2] == 0.0
    # 零變異欄不得影響預測
    assert m.predict({"a": 0.1, "b": 0.2, "const": 1.0}) == pytest.approx(
        m.predict({"a": 0.1, "b": 0.2, "const": 99.0}))


def test_prediction_uses_fit_window_standardization_only():
    feats, ys = _toy_dataset()
    m = fit_logistic_l2(feats, ys, keys=("a", "b"), lam=1.0, kappa=100)
    assert m.fit_years == ()
    z = m.intercept + sum(c * (0.3 - mu) / sd for c, mu, sd
                          in zip(m.coef, m.mean, m.std, strict=True))
    from cpbl.models.winprob_strength import sigmoid
    assert m.predict({"a": 0.3, "b": 0.3}) == pytest.approx(sigmoid(z))


# ───────────────────────── 決定性 tie-break（紅線 3） ─────────────────────────
def _pc(kappa, lam, brier, ll):
    return PriorCandidate(kappa, lam, brier, ll, model=None)  # type: ignore[arg-type]


def test_prior_tiebreak_order():
    best = _pc(50, 1.0, 0.2400, 0.690)
    assert better_prior(_pc(50, 1.0, 0.2398, 0.700), best)          # Brier 差 ≥1e-5 勝出
    assert not better_prior(_pc(50, 1.0, 0.2402, 0.680), best)
    # Brier 同分 → log-loss
    assert better_prior(_pc(50, 1.0, 0.240001, 0.6800), best)
    # Brier、log-loss 皆同分 → 較大 lambda → 較大 kappa
    assert better_prior(_pc(50, 10.0, 0.240001, 0.690001), best)
    assert not better_prior(_pc(50, 0.1, 0.240001, 0.690001), best)
    assert better_prior(_pc(200, 1.0, 0.240001, 0.690001), best)
    assert not better_prior(_pc(50, 1.0, 0.240001, 0.690001), best)  # 完全同 → 不換


def test_gamma_tiebreak_prefers_linear_decay():
    best = GammaCandidate(0.5, 0.1500, 0.020)
    assert better_gamma(GammaCandidate(1.0, 0.150001, 0.020001), best)   # 同分取 γ=1
    assert better_gamma(GammaCandidate(2.0, 0.150001, 0.020001), best)   # 再取 γ=2
    assert not better_gamma(GammaCandidate(0.5, 0.150001, 0.020001), best)
    assert better_gamma(GammaCandidate(2.0, 0.1490, 0.030), best)        # Brier 優先


# ───────────────────────── 局帶與判定 ─────────────────────────
def _sc(p, y, gk=1):
    return (p, y, False, gk)


def test_band_stats_requires_strict_alignment():
    with pytest.raises(ValueError):
        band_stats([1, 2, 3], [_sc(0.5, 1.0), _sc(0.5, 0.0)])


def test_band_stats_unrounded():
    stats = band_stats([1, 5, 8, 11],
                       [_sc(0.6, 1.0), _sc(0.4, 0.0), _sc(0.7, 0.0), _sc(0.9, 1.0)])
    assert stats["1-3"]["dev"] == pytest.approx(0.6 - 1.0)
    assert stats["10+"]["n"] == 1
    assert set(stats) == {"1-3", "4-6", "7-9", "10+"}


def _season(year, *, cov=1.0, eff=None, adj=0.15, base=0.16, const=0.24):
    return {"year": year, "coverage": round(cov, 4), "coverage_raw": cov,
            "effective_coverage": cov if eff is None else eff,
            "adjusted": {"brier_raw": adj, "ece_weighted": 0.02},
            "base": {"brier_raw": base},
            "baseline_home_const": {"brier_raw": const}}


def _pooled(deciles=()):
    """deciles: [(bin, n, dev, ci)]；未捨入，直接餵判定路徑。"""
    return {"raw_deciles": {b: {"n": n, "pred": 0.5 + d, "actual": 0.5, "dev": d}
                            for b, n, d, _ in deciles},
            "decile_boot": {b: {"ci": ci} for b, _, _, ci in deciles}}


def _bands(dev_by_band, n=5000):
    raw = {b: {"n": n, "pred": 0.5 + d, "actual": 0.5, "dev": d}
           for b, d in dev_by_band.items()}
    return {"raw": raw, "boot": {b: {"ci": [d - 0.001, d + 0.001]}
                                 for b, d in dev_by_band.items()}}


CLEAN_BANDS = {"1-3": 0.001, "4-6": 0.001, "7-9": 0.001}


def test_verdict_passes_when_all_gates_clean():
    v = strength_verdict([_season(2023), _season(2026)], _pooled(),
                         _bands(CLEAN_BANDS), _bands(CLEAN_BANDS))
    assert v["status"] == "supported" and v["reasons"] == []


def test_verdict_hard_fails_on_coverage():
    v = strength_verdict([_season(2026, cov=0.9722)], _pooled(),
                         _bands(CLEAN_BANDS), _bands(CLEAN_BANDS))
    assert v["status"] == "unsupported"
    assert any("coverage" in r for r in v["reasons"])


def test_verdict_hard_fails_when_worse_than_base():
    v = strength_verdict([_season(2025, adj=0.1601, base=0.1600)], _pooled(),
                         _bands(CLEAN_BANDS), _bands(CLEAN_BANDS))
    assert any("劣於同代未融合 base" in r for r in v["reasons"])


def test_verdict_hard_fails_when_not_beating_home_constant():
    v = strength_verdict([_season(2025, adj=0.245, base=0.246, const=0.244)],
                         _pooled(), _bands(CLEAN_BANDS), _bands(CLEAN_BANDS))
    assert any("未勝主場常數基準" in r for r in v["reasons"])


def test_verdict_hard_fails_on_significant_pooled_decile():
    pooled = _pooled([(7, 6000, -0.05, [-0.09, -0.01])])
    v = strength_verdict([_season(2026)], pooled, _bands(CLEAN_BANDS),
                         _bands(CLEAN_BANDS))
    assert any("池化十分位 7" in r for r in v["reasons"])


def test_verdict_pooled_decile_within_ci_is_disclosure_only():
    pooled = _pooled([(7, 6000, -0.05, [-0.09, 0.02])])
    v = strength_verdict([_season(2026)], pooled, _bands(CLEAN_BANDS),
                         _bands(CLEAN_BANDS))
    assert v["status"] == "supported"


def test_verdict_hard_fails_on_significant_band_deviation():
    bad = {"1-3": 0.045, "4-6": 0.001, "7-9": 0.001}
    v = strength_verdict([_season(2026)], _pooled(),
                         _bands({"1-3": 0.044, "4-6": 0.001, "7-9": 0.001}), _bands(bad))
    assert any("池化局帶 1-3" in r for r in v["reasons"])


def test_verdict_hard_fails_on_single_band_worsening_over_2pt():
    v = strength_verdict([_season(2026)], _pooled(),
                         _bands({"1-3": 0.001, "4-6": 0.001, "7-9": 0.001}),
                         _bands({"1-3": 0.026, "4-6": 0.001, "7-9": 0.001}))
    assert any("惡化" in r and "> 2pt" in r for r in v["reasons"])


def test_verdict_hard_fails_on_two_bands_worsening_over_1pt():
    v = strength_verdict([_season(2026)], _pooled(),
                         _bands({"1-3": 0.001, "4-6": 0.001, "7-9": 0.001}),
                         _bands({"1-3": 0.015, "4-6": 0.016, "7-9": 0.001}))
    assert any("系統性惡化" in r for r in v["reasons"])


def test_verdict_small_band_not_a_gate():
    """n < 1000 的帶只揭露、不作否決證據（紅線 7）。"""
    v = strength_verdict([_season(2026)], _pooled(),
                         _bands({"1-3": 0.001, "4-6": 0.001, "7-9": 0.001}),
                         _bands({"1-3": 0.045, "4-6": 0.001, "7-9": 0.001}, n=400))
    assert not any("池化局帶" in r for r in v["reasons"])


def test_partial_rerun_cannot_be_go_evidence():
    v = strength_verdict([_season(2026)], _pooled(), _bands(CLEAN_BANDS),
                         _bands(CLEAN_BANDS), complete=False)
    assert v["status"] == "unsupported"
    assert any("部分重跑" in r for r in v["reasons"])


# ── iteration 2：紅線 4「全部判定使用未捨入值」的邊界回歸（查核 F1／F3）──
def test_coverage_just_below_threshold_is_not_rounded_up():
    """0.97996 捨入 4 位為 0.9800 會錯誤通過；判定須讀 coverage_raw。"""
    v = strength_verdict([_season(2026, cov=0.97996)], _pooled(),
                         _bands(CLEAN_BANDS), _bands(CLEAN_BANDS))
    assert v["status"] == "unsupported"
    assert any("coverage 0.979960" in r for r in v["reasons"])


def test_effective_coverage_gates_missing_pregame_features():
    """build coverage 1.0 但大量場次缺賽前特徵 ⇒ effective coverage 必須擋下。"""
    v = strength_verdict([_season(2026, cov=1.0, eff=0.90)], _pooled(),
                         _bands(CLEAN_BANDS), _bands(CLEAN_BANDS))
    assert v["status"] == "unsupported"
    assert any("effective coverage" in r for r in v["reasons"])
    # 兩者皆足時不得誤擋
    assert strength_verdict([_season(2026, cov=1.0, eff=1.0)], _pooled(),
                            _bands(CLEAN_BANDS), _bands(CLEAN_BANDS))["status"] == "supported"


def test_decile_dev_just_over_threshold_is_not_rounded_down():
    """dev 0.030004 捨入 4 位為 0.0300（不超界）；未捨入才會正確硬性失敗。"""
    v = strength_verdict([_season(2026)],
                         _pooled([(3, 6000, 0.030004, [0.01, 0.05])]),
                         _bands(CLEAN_BANDS), _bands(CLEAN_BANDS))
    assert any("池化十分位 3" in r for r in v["reasons"])


def test_decile_ci_just_excluding_zero_is_not_rounded_to_include_it():
    """CI 下界 0.000004 捨入 5 位為 0.0 會被誤判為含 0；未捨入才會判顯著。"""
    v = strength_verdict([_season(2026)],
                         _pooled([(3, 6000, 0.05, [0.000004, 0.09])]),
                         _bands(CLEAN_BANDS), _bands(CLEAN_BANDS))
    assert any("池化十分位 3" in r for r in v["reasons"])


def test_bootstrap_ci_helper_returns_unrounded():
    """_ci_from_draws 不得捨入（band 與 decile 兩條 bootstrap 共用）。"""
    from cpbl.models.winprob_strength import _ci_from_draws
    draws = {"x": [0.0000012345 + i * 1e-9 for i in range(1000)]}
    out = _ci_from_draws(draws, 0.99)["x"]
    assert out["ci"][0] != round(out["ci"][0], 5)     # 保留 5 位以下精度
    assert out["se"] != round(out["se"], 5)


def test_decile_stats_unrounded_and_complete():
    rows = [(0.6, 1.0, False, 1), (0.62, 0.0, False, 1), (0.31, 1.0, False, 2)]
    from cpbl.models.winprob_strength import decile_stats
    st = decile_stats(rows)
    assert set(st) == {3, 6}
    assert st[6]["dev"] == pytest.approx((0.6 + 0.62 - 1.0) / 2)
    assert st[6]["dev"] != round(st[6]["dev"], 4)


@dataclass(frozen=True)
class _GameRowStub:
    """`_rows_md5` 只做 `dataclasses.asdict`，故摘要測試用最小 dataclass 即可。"""

    year: int
    game_sno: int
    team_feats: dict


# ─────────────── iteration 3 查核 F3：iteration 3／4 的修正須有回歸測試 ───────────────
# 前三輪的修正（未捨入判定路徑、as-of、指紋）全部零測試，於是每輪都要靠查核者手動重現才
# 抓得到殘留缺陷。以下把那些修正的**行為**釘住，而不只是測目前的實作長相。


class _AsOfCursor:
    """只回答 as-of 相關查詢的最小 cursor：讓 as-of 語意可離線驗證。"""

    def __init__(self, games):
        # games: [(game_date, home_score, away_score), ...]
        self._games = games
        self._rows: list = []

    def execute(self, sql, params=None):
        if "avg(CASE WHEN home_score>away_score" in sql:
            as_of = params[3]
            vals = [1.0 if h > a else (0.0 if h < a else 0.5)
                    for d, h, a in self._games if d <= as_of]
            self._rows = [(sum(vals) / len(vals) if vals else None,)]
        else:
            raise AssertionError(f"未預期的查詢：{sql[:60]}")

    def fetchone(self):
        return self._rows[0]


def test_home_rate_exact_is_unrounded_and_honors_as_of():
    """iteration 2 查核 F1a：主場常數基準須未捨入，且吃傳入的 as_of 而非 CURRENT_DATE。"""
    from cpbl.models.winprob_strength import home_rate_exact
    # 3 勝 4 敗 → 3/7 = 0.428571…，捨入 4 位會變 0.4286
    games = [(date(2026, 4, d), 1, 0) for d in range(1, 4)] + \
            [(date(2026, 4, d), 0, 1) for d in range(4, 8)]
    early = [(date(2026, 4, d), 1, 0) for d in range(1, 4)]      # as_of 前只有 3 勝
    cur = _AsOfCursor(games)
    full = home_rate_exact(cur, "A", 2026, 2026, date(2026, 4, 30))
    assert full == pytest.approx(3 / 7)
    assert full != round(full, 4)                                 # 未捨入
    cut = home_rate_exact(_AsOfCursor(games), "A", 2026, 2026, date(2026, 4, 3))
    assert cut == 1.0 and len(early) == 3                         # as_of 之後的敗場不計入


def test_raw_ece_matches_unrounded_decile_closed_form():
    """iteration 2 查核 F1b：raw_ece 必須由未捨入 decile 重算，不得沿用捨入顯示值。"""
    from cpbl.models.winprob_strength import decile_stats, raw_ece
    rows = [(0.6123456, 1.0, False, 1), (0.6234567, 0.0, False, 1),
            (0.3111111, 1.0, False, 2), (0.3222222, 0.0, False, 2)]
    st = decile_stats(rows)
    n = sum(d["n"] for d in st.values())
    expected = sum(abs(d["dev"]) * d["n"] for d in st.values()) / n
    assert raw_ece(rows) == pytest.approx(expected, abs=0.0)
    assert raw_ece(rows) != round(raw_ece(rows), 4)


class _FingerprintCursor:
    """games／published build 兩段查詢的最小替身；rows 由呼叫端直接給。"""

    def __init__(self, per_year, builds):
        self._per_year, self._builds = per_year, builds
        self._rows: list = []

    def execute(self, sql, params=None):
        if "FROM cpbl.games" in sql:
            self._rows = list(self._per_year)
        elif "FROM cpbl.game_recap_builds" in sql:
            self._rows = [self._builds[params[0]]]
        else:
            raise AssertionError(f"未預期的查詢：{sql[:60]}")

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._rows[0]


def _fp(per_year=None, builds=None, rows=None):
    from cpbl.models.winprob_strength import population_fingerprint
    per_year = per_year or [(2026, 2, "sno-md5", "games-md5")]
    builds = builds or {2026: (2, "build-md5")}
    return population_fingerprint(_FingerprintCursor(per_year, builds),
                                  date(2026, 7, 27), rows or [], {2026: {1, 2}})


def test_fingerprint_covers_scores_builds_and_model_inputs():
    """iteration 3 查核 F1：只 hash sno 集合，比分修訂／PA 重新發布／特徵重算全看不見。"""
    base = _fp()
    # ① 比分被修訂：sno 集合一模一樣，games_md5 必須變
    revised = _fp(per_year=[(2026, 2, "sno-md5", "games-md5-REVISED")])
    assert revised["by_year"][2026]["sno_md5"] == base["by_year"][2026]["sno_md5"]
    assert revised["by_year"][2026]["games_md5"] != base["by_year"][2026]["games_md5"]
    # ② PA 重新發布：games 完全沒動，published build identity 必須變
    republished = _fp(builds={2026: (2, "build-md5-REPUBLISHED")})
    assert republished["by_year"] == base["by_year"]
    assert (republished["published_builds_by_eval_year"][2026]["build_md5"]
            != base["published_builds_by_eval_year"][2026]["build_md5"])


def test_fingerprint_tracks_actual_model_inputs():
    """特徵值變動（gamelog 補值等）必須改變 model_inputs_md5——場數與 sno 都不會動。"""
    def row(kbb):
        return _GameRowStub(2026, 1, {"winrate_diff": kbb})
    a = _fp(rows=[row(0.10)])
    b = _fp(rows=[row(0.11)])
    assert a["by_year"][2026]["n_completed"] == b["by_year"][2026]["n_completed"]
    assert a["model_inputs_md5"] != b["model_inputs_md5"]


def test_fingerprint_diff_names_the_drifted_key():
    """漂移時要說得出「哪一年的哪一項變了」，不能只回一句不一致。"""
    from cpbl.models.winprob_strength import fingerprint_diff
    base = _fp()
    drifted = _fp(per_year=[(2026, 3, "sno-md5-NEW", "games-md5-NEW")])
    diffs = fingerprint_diff(base, drifted)
    assert diffs, "指紋不同卻回報無差異"
    assert any("2026" in d and "n_completed" in d for d in diffs)
    assert fingerprint_diff(base, _fp()) == []


class _SeasonPackCursor:
    """`build_season_pack` 用到的四段查詢：as-of 完成場、as-of PA state、逐球事件流
    （ML-WP-VAL-RESAMPLE1 起 `_pa_state_counts_as_of()` 要解打席前比分）、主場勝率。"""

    def __init__(self, as_of_games, pas, livelog=()):
        self._as_of_games, self._pas, self._livelog = as_of_games, pas, list(livelog)
        self._rows: list = []

    def execute(self, sql, params=None):
        if "SELECT game_sno FROM cpbl.games" in sql:
            as_of = params[2]
            self._rows = [(sno,) for sno, d in self._as_of_games if d <= as_of]
        elif "FROM cpbl.game_livelog WHERE" in sql:
            self._rows = list(self._livelog)
        elif "FROM cpbl.game_plate_appearances" in sql:
            as_of = params[2]
            self._rows = [(sno, state, pre, index, str(index))
                          for index, (sno, d, state, pre) in enumerate(self._pas, start=1)
                          if d <= as_of]
        elif "avg(CASE WHEN home_score>away_score" in sql:
            self._rows = [(0.5,)]
        else:
            raise AssertionError(f"未預期的查詢：{sql[:60]}")

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._rows[0]


def test_season_metadata_ignores_games_after_as_of(monkeypatch):
    """iteration 3 查核 F1：coverage／n_irregular_games／pa_state_counts 原本取自
    `load_eval_season()`（以 CURRENT_DATE 為界），as_of 之後入庫的比賽會混進來。"""
    from cpbl.models import winprob_strength as ws

    early, late = date(2026, 6, 1), date(2026, 7, 20)
    pas = [{"game_sno": 1, "inning": 1, "vht": "T", "outs": 0, "outcome": 1.0,
            "irregular": False, "game_key": (2026, "A", 1), "diff": 0, "bases": "___"},
           {"game_sno": 2, "inning": 1, "vht": "T", "outs": 0, "outcome": 0.0,
            "irregular": False, "game_key": (2026, "A", 2), "diff": 0, "bases": "___"}]
    monkeypatch.setattr(ws, "load_eval_season", lambda cur, kind, year, **kw: {
        "pas": pas, "rules": None,
        # 上游一律看到兩場（含 as_of 之後那場），且其中一場 irregular
        "games": {1: {"outcome": 1.0, "irregular": False},
                  2: {"outcome": 0.0, "irregular": True}},
        "coverage": 1.0, "n_irregular_games": 1,
        "pa_state_counts": {"ready": 2},
    })
    monkeypatch.setattr(ws, "score_pas", lambda dist, rules, ps: [(0.5, p["outcome"], False,
                                                                   p["game_key"]) for p in ps])
    monkeypatch.setattr(ws, "dist_from_counts", lambda *a, **k: {})
    monkeypatch.setattr(ws, "opening_wp", lambda dist, year: 0.5)

    cur = _SeasonPackCursor(
        as_of_games=[(1, early), (2, late)],
        pas=[(1, early, "ready", {"inning": 1, "half": "T", "outs": 0,
                                  "home_score": 0, "away_score": 0}),
             (2, late, "ready", {"inning": 1, "half": "T", "outs": 0,
                                 "home_score": 0, "away_score": 0})],
        # PA 的 start_event_no 由 fixture 依序給 "1"／"2"，事件流需對得回去
        livelog=[(1, "1", 0, 0), (2, "2", 0, 0)])
    pack = ws.build_season_pack(cur, {}, 2026, 2025, {1, 2}, date(2026, 6, 30))

    assert pack.n_completed_games == 1              # 只算 as_of 界限內的完成場
    assert pack.n_irregular_games == 0              # 那場 irregular 在 as_of 之後
    assert pack.pa_state_counts == {"ready": 1}     # 上游會回 {"ready": 2}
    assert pack.coverage == round(pack.coverage_raw, 4)


class _StateCountCursor:
    """同一份 fixture 同時餵給 `load_eval_season()` 與 `_pa_state_counts_as_of()`。

    四段查詢以 SQL 特徵分派：games＋livelog 彙總（上游完成場）、逐球事件流
    （兩邊解打席前比分共用）、無 games join 的 PA 查詢（上游）、有 games join＋
    日期界限的 PA 查詢（本卡）。
    """

    def __init__(self, games, pas, livelog=()):
        # games:   [(sno, home_score, away_score, delay_kind, max_inn, game_date), ...]
        # pas:     [(sno, state, pre_state, pa_index, start_event_no), ...]
        # livelog: [(sno, main_event_no, visiting_score, home_score), ...]
        self._games, self._pas, self._livelog = games, pas, list(livelog)
        self._date = {g[0]: g[5] for g in games}
        self._rows: list = []

    def execute(self, sql, params=None):
        if "FROM cpbl.games g " in sql and "game_livelog" in sql:
            self._rows = [(sno, hs, aw, delay, mx)
                          for sno, hs, aw, delay, mx, _d in self._games if hs + aw > 0]
        elif "FROM cpbl.game_livelog WHERE" in sql:
            self._rows = list(self._livelog)
        elif "FROM cpbl.game_plate_appearances" in sql and "JOIN cpbl.games g" in sql:
            as_of = params[2]
            self._rows = [row for row in self._pas if self._date[row[0]] <= as_of]
        elif "FROM cpbl.game_plate_appearances" in sql:
            self._rows = list(self._pas)          # 上游：無日期界限
        else:
            raise AssertionError(f"未預期的查詢：{sql[:70]}")

    def fetchall(self):
        return self._rows


def _state_fixture():
    """涵蓋所有 state 與缺欄位組合：

    - sno 1：完成場、`ready` 且 pre_state 完整 → 只進 `ready`；其中一筆的
      `start_event_no` 對不回事件流 → 另計 `ready_pre_score_unresolved`
      （ML-WP-VAL-RESAMPLE1 新增的 fail-closed 分支）
    - sno 2：完成場、`ready` 但缺 `outs` → `ready` ＋ `ready_incomplete_state`
    - sno 3：**未完成場**（0-0）、`ready` 且完整 → 只進 `ready`，不得計 incomplete
      （上游 `sno not in games` 就 continue，本卡以 as_of 完成場集合對應）
    - sno 4：完成場、非 ready 的兩種 state → 各自計數，且**不得**碰 incomplete 判斷
    """
    full = {"inning": 3, "half": "T", "outs": 1, "home_score": 2, "away_score": 1}
    missing_outs = {**full, "outs": None}
    games = [(1, 3, 1, None, 9, date(2026, 4, 1)),
             (2, 5, 2, None, 9, date(2026, 4, 2)),
             (3, 0, 0, None, None, date(2026, 4, 3)),
             (4, 1, 0, "雨", 7, date(2026, 4, 4))]
    pas = [(1, "ready", full, 1, "101"), (1, "ready", full, 2, "999"),
           (2, "ready", missing_outs, 1, "201"),
           (3, "ready", full, 1, "301"),
           (4, "truncated", full, 1, "401"), (4, "non_pa", full, 2, "402"),
           (4, "ready", missing_outs, 3, "403")]
    # "999" 刻意不入事件流 → sno 1 的第二筆打席前比分解不出（fail closed）
    livelog = [(1, "101", 0, 0), (2, "201", 0, 0), (3, "301", 0, 0),
               (4, "401", 0, 0), (4, "402", 0, 0), (4, "403", 0, 0)]
    return games, pas, livelog


def test_as_of_pa_state_counts_match_upstream_when_as_of_is_future():
    """iteration 4 查核 F2：`_pa_state_counts_as_of()` 複製了上游的判準（winprob_val 是禁改區），
    兩處分岔是最大的風險。as_of 取未來日時，本卡重算必須與 `load_eval_season()` 逐鍵相同。

    這支測試是那份 docstring 宣稱的實體——iteration 4 只寫了宣稱、沒寫測試。
    """
    from cpbl.models.winprob_strength import KIND, _pa_state_counts_as_of
    from cpbl.models.winprob_val import load_eval_season

    games, pas, livelog = _state_fixture()
    upstream = load_eval_season(_StateCountCursor(games, pas, livelog), KIND, 2026)
    far_future = date(2099, 12, 31)
    as_of_snos = {sno for sno, hs, aw, _d, _m, _dt in games if hs + aw > 0}
    mine = _pa_state_counts_as_of(_StateCountCursor(games, pas, livelog), 2026,
                                  far_future, as_of_snos)

    assert mine == upstream["pa_state_counts"], (
        f"與上游判準分岔：本卡 {mine} vs 上游 {upstream['pa_state_counts']}")
    # 光是相等不夠——fixture 必須真的走過每一條分支，否則這個等式是空的
    assert set(mine) == {"ready", "ready_incomplete_state", "ready_pre_score_unresolved",
                         "truncated", "non_pa"}
    assert mine["ready"] == 5 and mine["ready_incomplete_state"] == 2
    assert mine["ready_pre_score_unresolved"] == 1
    assert mine["truncated"] == 1 and mine["non_pa"] == 1


def test_as_of_pa_state_counts_drop_games_after_the_cutoff():
    """同一份 fixture，as_of 往前挪 → 只留界限內的場次；上游則永遠是全部。"""
    from cpbl.models.winprob_strength import KIND, _pa_state_counts_as_of
    from cpbl.models.winprob_val import load_eval_season

    games, pas, livelog = _state_fixture()
    upstream = load_eval_season(_StateCountCursor(games, pas, livelog), KIND, 2026)
    cut = date(2026, 4, 2)
    mine = _pa_state_counts_as_of(_StateCountCursor(games, pas, livelog), 2026, cut, {1, 2})

    assert mine == {"ready": 3, "ready_incomplete_state": 1,
                    "ready_pre_score_unresolved": 1}
    assert upstream["pa_state_counts"]["ready"] == 5      # 上游看得到界限後的場次


# ───────── iteration 5 查核 F1：報告 §5 只能格式化 canonical 判定，不得自行重判 ─────────
# 報告腳本原本重寫了一次門檻，四條各有落差。判定改為只出自 strength_verdict()，
# 並輸出結構化 gate_results；以下四支測試釘住那四條落差各自的邊界。


def _gate(verdict: dict, gate: str) -> dict:
    return next(g for g in verdict["gate_results"] if g["gate"] == gate)


def test_gate_4a_reads_effective_coverage_not_only_raw():
    """查核者的原始重現：effective_coverage 0.5、coverage_raw 1.0——報告曾印 ✅ 通過。"""
    v = strength_verdict([_season(2023, cov=1.0, eff=0.5)], _pooled(),
                         _bands(CLEAN_BANDS), _bands(CLEAN_BANDS))
    g = _gate(v, "4a")
    assert g["passed"] is False
    assert any("effective coverage" in f for f in g["failures"])


def test_gate_4d_needs_both_significance_and_magnitude():
    """顯著但 |dev| 未超 0.03 只是揭露；兩者同時成立才算 4d 失敗。"""
    sig_small = strength_verdict([_season(2026)], _pooled([(3, 6000, 0.02, [0.01, 0.03])]),
                                 _bands(CLEAN_BANDS), _bands(CLEAN_BANDS))
    assert _gate(sig_small, "4d")["passed"] is True
    sig_big = strength_verdict([_season(2026)], _pooled([(3, 6000, 0.05, [0.01, 0.09])]),
                               _bands(CLEAN_BANDS), _bands(CLEAN_BANDS))
    assert _gate(sig_big, "4d")["passed"] is False


def test_gate_5a_needs_the_ci_condition_too():
    """局帶 |dev| 超 0.03 但 99% CI 含 0 → 不算 5a 失敗（報告版曾漏掉 CI 條件）。"""
    bands = {"raw": {"1-3": {"n": 5000, "pred": 0.55, "actual": 0.5, "dev": 0.05},
                     "4-6": {"n": 5000, "pred": 0.5, "actual": 0.5, "dev": 0.0},
                     "7-9": {"n": 5000, "pred": 0.5, "actual": 0.5, "dev": 0.0}},
             "boot": {"1-3": {"ci": [-0.02, 0.12]},          # 含 0
                      "4-6": {"ci": [-0.001, 0.001]}, "7-9": {"ci": [-0.001, 0.001]}}}
    v = strength_verdict([_season(2026)], _pooled(), _bands(CLEAN_BANDS), bands)
    assert _gate(v, "5a")["passed"] is True
    bands["boot"]["1-3"]["ci"] = [0.02, 0.08]                # 排除 0 → 才失敗
    assert _gate(strength_verdict([_season(2026)], _pooled(), _bands(CLEAN_BANDS), bands),
                 "5a")["passed"] is False


def test_gate_5b_rule_is_one_band_over_2pt_or_two_bands_over_1pt():
    """報告版把「最大惡化 ≤1pt」當通過條件，等於把單帶 1–2pt 誤判成失敗。"""
    base = _bands({"1-3": 0.0, "4-6": 0.0, "7-9": 0.0})
    one_mid = _bands({"1-3": 0.015, "4-6": 0.0, "7-9": 0.0})    # 單帶 +1.5pt → 只揭露
    assert _gate(strength_verdict([_season(2026)], _pooled(), base, one_mid),
                 "5b")["passed"] is True
    one_big = _bands({"1-3": 0.025, "4-6": 0.0, "7-9": 0.0})    # 單帶 +2.5pt → 失敗
    assert _gate(strength_verdict([_season(2026)], _pooled(), base, one_big),
                 "5b")["passed"] is False
    two_mid = _bands({"1-3": 0.015, "4-6": 0.015, "7-9": 0.0})  # 兩帶各 +1.5pt → 失敗
    assert _gate(strength_verdict([_season(2026)], _pooled(), base, two_mid),
                 "5b")["passed"] is False


def test_gate_results_cover_every_rule_and_agree_with_reasons():
    """gate_results 必須涵蓋全部條號，且其 failures 的聯集恰等於 reasons（不多不少）。"""
    from cpbl.models.winprob_strength import GATE_RULES
    v = strength_verdict([_season(2023, adj=0.17, base=0.16), _season(2026, cov=0.90)],
                         _pooled(), _bands(CLEAN_BANDS), _bands(CLEAN_BANDS), complete=False)
    assert [g["gate"] for g in v["gate_results"]] == [gid for gid, _ in GATE_RULES]
    flattened = [f for g in v["gate_results"] for f in g["failures"]]
    assert sorted(flattened) == sorted(v["reasons"])
