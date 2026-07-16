"""ML-MATCHUP1 統計核心測試：wOBA 聚合、動差法先驗、收縮、對稱與敏感度。

fixture 皆為手算可驗的合成資料；固定數字 pin 住實作（spec 要求可重現）。
"""

from __future__ import annotations

import math

import pytest

from cpbl.models.matchup_insights import (
    CREDIBILITY_GATE,
    Hyperparameters,
    InsightCandidate,
    PairSample,
    WobaLine,
    additive_expected,
    estimate_hyperparameters,
    evaluate_pairs,
    merge_lines,
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


_BIG_OPPS = {"H1": 10_000, "H2": 10_000, "P1": 10_000, "P2": 10_000}


def test_method_of_moments_recovers_between_pair_variance():
    # 兩組配對殘差 ±0.1、各 n=100；官方 baseline 大（10k）→ noise ≈ sigma²。
    # tau² = Σ(n·r² − sigma²·(1+n/10000·2))/Σn ≈ (100·0.01 − 0.408)·2 / 200 = 0.00296。
    pairs = [
        PairSample("H1", "P1", WobaLine(0.45 * 100, 100)),
        PairSample("H2", "P2", WobaLine(0.25 * 100, 100)),
    ]
    expected = {("H1", "P1"): 0.35, ("H2", "P2"): 0.35}
    hyper = estimate_hyperparameters(
        pairs, expected=expected, hitter_opps=_BIG_OPPS,
        pitcher_opps=_BIG_OPPS, sigma2=0.4,
    )

    noise = 0.4 * (1 + 100 / 10_000 + 100 / 10_000)
    assert hyper.tau2 == pytest.approx((100 * 0.01 - noise) * 2 / 200)
    assert hyper.pairs_used == 2
    assert hyper.prior_strength == pytest.approx(0.4 / hyper.tau2)


def test_estimation_excludes_tiny_pairs_and_missing_baselines():
    # 微樣本配對（n<10）與缺官方 baseline 的配對都不得進 tau² 估計。
    good = PairSample("H1", "P1", WobaLine(0.45 * 100, 100))
    tiny = PairSample("H1", "P2", WobaLine(2.10 * 5, 5))       # n<10
    orphan = PairSample("H2", "P1", WobaLine(0.45 * 100, 100))  # H2 無官方 baseline
    expected = {
        ("H1", "P1"): 0.35, ("H1", "P2"): 0.35, ("H2", "P1"): 0.35,
    }
    hitter_opps = {"H1": 10_000}  # 無 H2
    hyper = estimate_hyperparameters(
        [good, tiny, orphan], expected=expected,
        hitter_opps=hitter_opps, pitcher_opps=_BIG_OPPS, sigma2=0.4,
    )

    assert hyper.pairs_used == 1


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
    """合成母體：聯盟均值 0.32；兩側官方 baseline 各 10k 機會 @0.32（偏差 0）。"""
    hitter_opps = {pair.hitter_id: 10_000}
    pitcher_opps = {pair.pitcher_id: 10_000}
    # 官方 baseline 都是聯盟均值 → expected = 0.32。
    expected = {(pair.hitter_id, pair.pitcher_id): 0.32}
    hyper = Hyperparameters(sigma2=0.4, tau2=0.002, pairs_used=50)
    return expected, hitter_opps, pitcher_opps, hyper


def test_symmetry_role_flip_mirrors_labels_without_double_advantage():
    # BAT vs ACE：200 機會、觀察 0.20（低於期望 0.32）→ 有利投手。
    pair = PairSample("BAT", "ACE", WobaLine(0.20 * 200, 200))
    expected, hitter_opps, pitcher_opps, hyper = _universe(pair)

    as_batter = evaluate_pairs(
        [pair], role="batting", expected=expected, hitter_opps=hitter_opps,
        pitcher_opps=pitcher_opps, hyper=hyper,
    )[0]
    as_pitcher = evaluate_pairs(
        [pair], role="pitching", expected=expected, hitter_opps=hitter_opps,
        pitcher_opps=pitcher_opps, hyper=hyper,
    )[0]

    # 同一組對戰：|delta| 與可信度完全相同（對稱期望保證單一號向）。
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
    expected = {("BAT", "NOBODY"): 0.32}
    candidates = evaluate_pairs(
        [pair], role="batting", expected=expected,
        hitter_opps={"BAT": 10_000}, pitcher_opps={"NOBODY": 10_000},
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
        estimate_hyperparameters(
            [], expected={}, hitter_opps={}, pitcher_opps={}, sigma2=0.4
        )


def test_credibility_is_two_sided_posterior_sign_probability():
    hyper = Hyperparameters(sigma2=0.4, tau2=0.01, pairs_used=10)
    s = shrink_delta(0.2, 100, hyper)
    z = abs(s.delta_shrunk) / s.posterior_sd
    assert s.credibility == pytest.approx(0.5 * (1 + math.erf(z / math.sqrt(2))))
