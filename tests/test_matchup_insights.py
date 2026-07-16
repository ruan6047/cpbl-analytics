"""ML-MATCHUP1 統計核心測試：wOBA 聚合、動差法先驗、收縮、對稱與敏感度。

fixture 皆為手算可驗的合成資料；固定數字 pin 住實作（spec 要求可重現）。
"""

from __future__ import annotations

import math

import pytest

from cpbl.models.matchup_insights import (
    CREDIBILITY_GATE,
    MIN_PAIRS_FOR_PRIOR,
    Hyperparameters,
    InsightCandidate,
    PairContext,
    PairSample,
    WobaLine,
    additive_expected,
    estimate_hyperparameters,
    evaluate_pairs,
    leave_pair_out,
    merge_lines,
    pair_context,
    per_opportunity_variance,
    rank_insights,
    sensitivity_report,
    shrink_delta,
    woba_line,
)


def test_woba_line_uses_standard_weights_and_denominator():
    counts = {
        "at_bats": 100, "singles": 20, "doubles": 5, "triples": 1,
        "home_runs": 3, "bb": 12, "ibb": 2, "hbp": 1, "sac_fly": 2,
    }
    line = woba_line(counts)

    # 分子 = .89*20 + 1.27*5 + 1.62*1 + 2.10*3 + .69*(12-2) + .72*1
    assert line.weighted_sum == pytest.approx(
        0.89 * 20 + 1.27 * 5 + 1.62 * 1 + 2.10 * 3 + 0.69 * 10 + 0.72 * 1
    )
    # 分母 = AB + uBB + HBP + SF（IBB 不進分母）
    assert line.opportunities == 100 + 10 + 1 + 2
    assert line.rate == pytest.approx(line.weighted_sum / 113)


def test_woba_line_tolerates_missing_fields_and_zero_denominator():
    assert woba_line({}).opportunities == 0
    assert woba_line({}).rate is None
    assert woba_line({"bb": 1, "ibb": 3}).weighted_sum == 0.0  # uBB 不可為負


def test_merge_lines_sums_counts_before_rates():
    # 兩年 0.500／0.100 的錯誤平均是 0.300；正解是先加總 (5+1)/(10+10)=0.3 恰同，
    # 換不對稱樣本驗證：10 機會 0.5 與 90 機會 0.1 → (5+9)/100 = 0.14 ≠ 平均 0.3。
    merged = merge_lines([WobaLine(5.0, 10), WobaLine(9.0, 90)])
    assert merged.rate == pytest.approx(0.14)


def test_per_opportunity_variance_matches_hand_computation():
    # 10 機會：1 支一安（0.89），9 個無事件（0）。μ=0.089。
    league = WobaLine(0.89, 10)
    sigma2 = per_opportunity_variance(league, {"singles": 1})
    expected = (1 * (0.89 - 0.089) ** 2 + 9 * 0.089**2) / 10
    assert sigma2 == pytest.approx(expected)


def _ctx(expected: float, rem: int = 10_000, official: int = 10_000) -> PairContext:
    return PairContext(
        expected=expected, hitter_rem=rem, pitcher_rem=rem,
        hitter_official=official, pitcher_official=official,
    )


def test_leave_pair_out_subtracts_raw_counts():
    baseline = WobaLine(100.0, 400)
    pair = WobaLine(30.0, 120)
    rem = leave_pair_out(baseline, pair)

    assert rem is not None
    assert rem.weighted_sum == pytest.approx(70.0)
    assert rem.opportunities == 280
    # 扣除後分母不為正、或加權和為負 → 不可評估（None），不得硬夾。
    assert leave_pair_out(WobaLine(30.0, 120), WobaLine(30.0, 120)) is None
    assert leave_pair_out(WobaLine(10.0, 400), WobaLine(20.0, 120)) is None


def test_pair_context_uses_leave_pair_out_expected():
    # 打者官方 400 機會 @0.35，其中配對佔 100 機會 @0.50 → 剩餘 (140−50)/300=0.30。
    # 投手官方 4000 機會 @0.34，配對同 100 機會 @0.50 → 剩餘 (1360−50)/3900≈0.3359。
    pair = WobaLine(0.50 * 100, 100)
    ctx = pair_context(
        pair,
        WobaLine(0.35 * 400, 400),
        WobaLine(0.34 * 4000, 4000),
        bat_league_mean=0.32,
        pit_league_mean=0.315,
    )

    assert ctx is not None
    assert ctx.hitter_rem == 300 and ctx.pitcher_rem == 3900
    assert ctx.hitter_official == 400 and ctx.pitcher_official == 4000
    lpo_bat_dev = (0.35 * 400 - 50.0) / 300 - 0.32
    lpo_pit_dev = (0.34 * 4000 - 50.0) / 3900 - 0.315
    assert ctx.expected == pytest.approx(0.32 + lpo_bat_dev + lpo_pit_dev)
    # 配對吃光其中一側母體 → 整體不可評估。
    assert pair_context(
        pair, WobaLine(0.50 * 100, 100), WobaLine(0.34 * 4000, 4000),
        bat_league_mean=0.32, pit_league_mean=0.315,
    ) is None


def _formula_pairs():
    """20 組殘差 ±0.1、各 n=100 的配對（達 MIN_PAIRS_FOR_PRIOR），數字可手算。"""
    pairs, contexts = [], {}
    for i in range(20):
        rate = 0.45 if i % 2 == 0 else 0.25
        key = (f"H{i:02d}", f"P{i:02d}")
        pairs.append(PairSample(key[0], key[1], WobaLine(rate * 100, 100)))
        contexts[key] = _ctx(0.35)
    return pairs, contexts


def test_method_of_moments_recovers_between_pair_variance():
    # 殘差 ±0.1、n=100；leave-pair-out 剩餘 10k → noise ≈ sigma²。
    # tau² = Σ(n·r² − sigma²·(1+n/10000·2))/Σn = (100·0.01 − 0.408)/100 = 0.00592。
    pairs, contexts = _formula_pairs()
    hyper = estimate_hyperparameters(pairs, contexts=contexts, sigma2=0.4)

    noise = 0.4 * (1 + 100 / 10_000 + 100 / 10_000)
    assert hyper.tau2 == pytest.approx((100 * 0.01 - noise) / 100)
    assert hyper.pairs_used == 20
    assert hyper.prior_strength == pytest.approx(0.4 / hyper.tau2)


def test_estimation_excludes_tiny_pairs_and_missing_contexts():
    # 微樣本配對（n<50）與缺 leave-pair-out 脈絡的配對都不得進 tau² 估計。
    pairs, contexts = _formula_pairs()
    tiny = PairSample("H98", "P98", WobaLine(2.10 * 5, 5))        # n<50
    orphan = PairSample("H99", "P99", WobaLine(0.45 * 100, 100))  # 無脈絡
    contexts[("H98", "P98")] = _ctx(0.35)
    hyper = estimate_hyperparameters(
        [*pairs, tiny, orphan], contexts=contexts, sigma2=0.4
    )

    assert hyper.pairs_used == 20


def test_estimation_fails_closed_below_min_pairs():
    # 可用配對 < MIN_PAIRS_FOR_PRIOR → 先驗不可靠，必須拋錯（呼叫端 fail-closed），
    # 不得回傳任意常數先驗。
    pairs, contexts = _formula_pairs()
    with pytest.raises(ValueError):
        estimate_hyperparameters(
            pairs[: MIN_PAIRS_FOR_PRIOR - 1], contexts=contexts, sigma2=0.4
        )


def test_shrinkage_pulls_small_samples_to_zero():
    hyper = Hyperparameters(sigma2=0.4, tau2=0.002, pairs_used=100)
    tiny = shrink_delta(0.6, 2, hyper)      # 1 打數大爆發
    large = shrink_delta(0.1, 400, hyper)   # 大樣本小差異

    # K = 0.4/0.002 = 200 等效機會：n=2 時權重 2/202 ≈ 0.0099
    assert tiny.delta_shrunk == pytest.approx(0.6 * 2 / 202)
    assert abs(tiny.delta_shrunk) < abs(large.delta_shrunk)
    assert tiny.credibility < CREDIBILITY_GATE  # 小樣本不可信
    assert large.credibility > 0.95


def test_additive_expected_is_symmetric_and_clipped():
    # league + batter_dev + pitcher_dev；偏差相加對稱。
    assert additive_expected(0.30 - 0.32, 0.36 - 0.32, 0.32) == pytest.approx(0.34)
    assert additive_expected(-0.31, -0.30, 0.32) == 0.0  # 夾下界


def _universe(pair: PairSample):
    """合成母體：聯盟均值 0.32；兩側 leave-pair-out 剩餘各 10k 機會（期望 0.32）。"""
    contexts = {(pair.hitter_id, pair.pitcher_id): _ctx(0.32)}
    hyper = Hyperparameters(sigma2=0.4, tau2=0.002, pairs_used=50)
    return contexts, hyper


def test_symmetry_role_flip_mirrors_labels_without_double_advantage():
    # BAT vs ACE：200 機會、觀察 0.20（低於期望 0.32）→ 有利投手。
    pair = PairSample("BAT", "ACE", WobaLine(0.20 * 200, 200))
    contexts, hyper = _universe(pair)

    as_batter = evaluate_pairs(
        [pair], role="batting", contexts=contexts, hyper=hyper,
    )[0]
    as_pitcher = evaluate_pairs(
        [pair], role="pitching", contexts=contexts, hyper=hyper,
    )[0]

    # 同一組對戰：期望、|delta| 與可信度完全相同（角色翻轉不變）。
    assert as_batter.expected == pytest.approx(as_pitcher.expected)
    assert as_batter.shrunk.delta_shrunk == pytest.approx(as_pitcher.shrunk.delta_shrunk)
    assert as_batter.shrunk.credibility == pytest.approx(as_pitcher.shrunk.credibility)

    batter_view = rank_insights([as_batter], role="batting")
    pitcher_view = rank_insights([as_pitcher], role="pitching")
    # 打者視角＝天敵（disadvantage）；投手視角＝優勢（advantage）。不得雙方同優。
    assert [c.opponent_id for c in batter_view.disadvantages] == ["ACE"]
    assert not batter_view.advantages
    assert [c.opponent_id for c in pitcher_view.advantages] == ["BAT"]
    assert not pitcher_view.disadvantages


def test_one_hit_wonder_never_becomes_nemesis():
    # 1 打數 1 全壘打：raw delta 巨大，但收縮＋閘門後不得成為候選。
    pair = PairSample("BAT", "NOBODY", WobaLine(2.10, 1))
    candidates = evaluate_pairs(
        [pair], role="batting", contexts={("BAT", "NOBODY"): _ctx(0.32)},
        hyper=Hyperparameters(sigma2=0.4, tau2=0.002, pairs_used=50),
    )
    ranked = rank_insights(candidates, role="batting")

    assert not ranked.advantages
    assert not ranked.disadvantages
    assert ranked.gated_out == 1


def test_rank_orders_by_shrunk_effect_and_respects_limit():
    hyper = Hyperparameters(sigma2=0.4, tau2=0.01, pairs_used=10)
    def cand(opp, delta, n):
        return InsightCandidate(
            opponent_id=opp, opportunities=n, observed=0.32 + delta,
            expected=0.32, shrunk=shrink_delta(delta, n, hyper),
        )
    rows = [cand("A", 0.20, 300), cand("B", 0.10, 300), cand("C", 0.30, 300),
            cand("D", -0.25, 300)]
    ranked = rank_insights(rows, role="batting", limit=2)

    assert [c.opponent_id for c in ranked.advantages] == ["C", "A"]
    assert [c.opponent_id for c in ranked.disadvantages] == ["D"]


def test_sensitivity_report_is_stable_for_clear_effects():
    hyper = Hyperparameters(sigma2=0.4, tau2=0.01, pairs_used=10)
    clear = InsightCandidate(
        opponent_id="A", opportunities=500, observed=0.62, expected=0.32,
        shrunk=shrink_delta(0.30, 500, hyper), opponent_baseline_opportunities=5_000,
    )
    report = sensitivity_report([clear], role="batting", limit=3, hyper=hyper)

    assert report["stable"] is True
    assert report["reference_members"] == ["A"]
    assert set(report["variants"]) == {
        "gate_0.70", "gate_0.75", "gate_0.80",
        "prior_x0.5", "prior_x1", "prior_x2",
        "opp_baseline_ge_100",
    }


def test_sensitivity_flags_thin_opponent_baseline():
    # 對手官方 baseline 稀疏（<100）：覆蓋敏感度移除後名單改變 → unstable。
    hyper = Hyperparameters(sigma2=0.4, tau2=0.01, pairs_used=10)
    thin = InsightCandidate(
        opponent_id="THIN", opportunities=500, observed=0.62, expected=0.32,
        shrunk=shrink_delta(0.30, 500, hyper), opponent_baseline_opportunities=40,
    )
    report = sensitivity_report([thin], role="batting", limit=3, hyper=hyper)

    assert report["variants"]["opp_baseline_ge_100"] == []
    assert report["stable"] is False


def test_sensitivity_report_flags_borderline_candidates():
    hyper = Hyperparameters(sigma2=0.4, tau2=0.002, pairs_used=10)
    # 找一個 credibility 剛好落在 0.70–0.80 之間的樣本量。
    borderline = None
    for n in range(1, 400):
        s = shrink_delta(0.12, n, hyper)
        if 0.70 <= s.credibility < 0.80:
            borderline = InsightCandidate(
                opponent_id="EDGE", opportunities=n, observed=0.44,
                expected=0.32, shrunk=s,
            )
            break
    assert borderline is not None, "找不到邊界樣本，測試設計失效"
    report = sensitivity_report([borderline], role="batting", limit=3, hyper=hyper)

    assert report["stable"] is False


def test_estimate_hyperparameters_requires_pairs():
    with pytest.raises(ValueError):
        estimate_hyperparameters([], contexts={}, sigma2=0.4)


def test_credibility_is_two_sided_posterior_sign_probability():
    hyper = Hyperparameters(sigma2=0.4, tau2=0.01, pairs_used=10)
    s = shrink_delta(0.2, 100, hyper)
    z = abs(s.delta_shrunk) / s.posterior_sd
    assert s.credibility == pytest.approx(0.5 * (1 + math.erf(z / math.sqrt(2))))


# ───────────── 第二輪審核 regression（P1-2／P1-3）：universe 層級 ─────────────
# 這批測試繞過純函式簽名、直接打 `_build_universe`（缺陷版 a1fcbe7 同樣存在此
# 介面），確保「缺陷版跑紅、修正版跑綠」是行為層級的證據，不是 import error。

import random  # noqa: E402

from cpbl.api.matchups import _build_universe  # noqa: E402


def test_universe_prior_unavailable_when_no_estimable_pairs():
    """P1-2：全部配對 n<50 → tau² 無法可靠估計 → hyper 必須為 None（fail-closed）。

    缺陷版 fallback 是 Hyperparameters(tau2=sigma2)（等效先驗僅 1 機會，
    1 PA 對手 credibility 可達 0.99），此測試在 a1fcbe7 必紅。
    """
    batter_rows = [("9001", 600, 180, 30, 5, 10, 50, 5, 5, 5)]
    pitcher_rows = [("8001", 600, 150, 12, 40, 4, 6)]
    pair_rows = [("9001", "8001", 10, 3, 0, 0, 0, 1, 0, 0, 0)]

    universe = _build_universe(batter_rows, pitcher_rows, pair_rows)

    assert universe.hyper is None


# 合成宇宙的真值：tau²(wOBA) = (0.89 × d 機率標準差)²。
_SYN_TAU_PROB_SD = 0.0225
_SYN_TAU2_TRUE = (0.89 * _SYN_TAU_PROB_SD) ** 2  # ≈ 0.0004


def _synthetic_matchup_rows():
    """合成 matchup 宇宙：官方 baseline『明確包含』被評配對（sum of pairs）。

    形狀貼近真實 regime（噪音 sigma²/n >> tau²、每打者對手數十人）：
    - 400 打者 × 25 投手全配對、各 n=50（過 _EST_MIN_N）。打者官方母體
      N=1250、自我納入比重 n/N=4%——缺陷版對每一對都用「含配對」baseline
      並以獨立樣本假設扣噪，兩項相依偏差合計會把 tau² 壓到接近 0。
    - 事件只有一壘安打（權重 0.89）：sigma² 可由聯盟分布精確重現、
      投手安打拆分無近似誤差。
    - 真實率 p_ij = p0 + b_i + q_j + d_ij，d ~ N(0, 0.0225²)（機率單位）
      → tau²(wOBA) ≈ 0.0004，與實資料估出的量級一致。
    """
    rng = random.Random(20260716)
    n = 50
    p0 = 0.36
    offsets = (-0.03, -0.01, 0.01, 0.03)
    hitters = [f"9{i:03d}" for i in range(400)]  # player_id 需為數字字串（int() 相容）
    pitchers = [f"8{j:03d}" for j in range(25)]

    pair_rows = []
    bat_totals = {h: [0, 0] for h in hitters}   # [ab, hits]
    pit_totals = {p: [0, 0] for p in pitchers}
    for i, hitter in enumerate(hitters):
        for j, pitcher in enumerate(pitchers):
            d = rng.gauss(0.0, _SYN_TAU_PROB_SD)
            p = min(max(p0 + offsets[i % 4] + offsets[j % 4] + d, 0.02), 0.98)
            hits = rng.binomialvariate(n, p)
            pair_rows.append((hitter, pitcher, n, hits, 0, 0, 0, 0, 0, 0, 0))
            bat_totals[hitter][0] += n
            bat_totals[hitter][1] += hits
            pit_totals[pitcher][0] += n
            pit_totals[pitcher][1] += hits

    batter_rows = [
        (h, ab, hits, 0, 0, 0, 0, 0, 0, 0) for h, (ab, hits) in bat_totals.items()
    ]
    pitcher_rows = [
        (p, bf, hits, 0, 0, 0, 0) for p, (bf, hits) in pit_totals.items()
    ]
    return batter_rows, pitcher_rows, pair_rows


def test_universe_tau2_recovery_with_self_inclusive_official_baseline():
    """P1-3：已知 tau² 的合成宇宙，官方 baseline 含被評配對。

    修正版（leave-pair-out expected＋一致的 noise 公式）須在 ±45% 內回收
    tau²≈0.0004；缺陷版（full-baseline expected＋獨立樣本 noise 假設）忽略
    配對與 baseline 的 covariance、過度扣噪，tau² 被壓到趨近 floor
    （固定 seed 下遠低於容忍帶）→ a1fcbe7 必紅。
    """
    batter_rows, pitcher_rows, pair_rows = _synthetic_matchup_rows()
    # 結構自證：官方打者母體 = 該打者所有配對之和（self-inclusion 成立）。
    h0_official = next(row[1] for row in batter_rows if row[0] == "9000")
    h0_pairs = sum(row[2] for row in pair_rows if row[0] == "9000")
    assert h0_official == h0_pairs

    universe = _build_universe(batter_rows, pitcher_rows, pair_rows)

    assert universe.hyper is not None
    assert universe.hyper.pairs_used == 400 * 25
    assert 0.55 * _SYN_TAU2_TRUE <= universe.hyper.tau2 <= 1.45 * _SYN_TAU2_TRUE, (
        f"tau2={universe.hyper.tau2:.6f} 偏離真值 {_SYN_TAU2_TRUE:.6f}"
    )
