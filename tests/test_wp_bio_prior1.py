"""ML-WP-BIO-PRIOR1 純函式單元測試（協定見 docs/research/ML-WP-BIO-PRIOR1_SPEC.md）。"""

from datetime import date

import pytest

from scripts.wp_bio_prior1 import (
    FEATURE_KEYS,
    age_years,
    bio_diffs,
    brier,
    import_flag,
    neutral_fill_mean,
    paired_bootstrap,
    percentile_ci,
    seniority,
)


def test_feature_keys_frozen_seven():
    """spec §2：七項凍結，隊伍四項在前、bio 三項在後；防執行期增刪。"""
    assert FEATURE_KEYS == (
        "prior_winpct_diff", "winrate_diff", "run_margin_diff", "rest_days_diff",
        "starter_age_diff", "starter_import_diff", "starter_seniority_diff",
    )


def test_age_years():
    assert age_years(date(2026, 7, 27), None) is None
    # 2024 為閏年 → 366 天 / 365.25
    assert age_years(date(2025, 1, 1), date(2024, 1, 1)) == pytest.approx(366 / 365.25)
    # 30 年整（含 7~8 個閏日）落在 30 附近
    assert age_years(date(2026, 7, 27), date(1996, 7, 27)) == pytest.approx(30.0, abs=0.01)


def test_import_flag_canonical_binarization():
    """spec §3：{import, loree} → 1；{local, nagata} → 0；未知分類碼必須爆錯。"""
    assert import_flag("import") == 1
    assert import_flag("loree") == 1
    assert import_flag("local") == 0
    assert import_flag("nagata") == 0
    with pytest.raises(KeyError):
        import_flag("unknown")


def test_seniority_strictly_before_game_year():
    """spec §4：只算嚴格早於比賽年的首見年；當季初登板與無前史皆 0。"""
    assert seniority(2026, [2019, 2021, 2026]) == 7
    assert seniority(2026, [2026]) == 0          # 當季才首見 → 賽前年資 0
    assert seniority(2026, []) == 0              # 零 CPBL 前史
    assert seniority(2023, [2022]) == 1


def test_neutral_fill_mean():
    assert neutral_fill_mean([28.0, 32.0]) == 30.0
    with pytest.raises(ValueError):
        neutral_fill_mean([])


def test_bio_diffs_with_fill():
    """spec §5：缺生日側以 fill 填補 → 對缺值側年齡差貢獻中性。"""
    home = (33.0, "import", 0)
    away = (None, "local", 8)
    d = bio_diffs(home, away, fill_age=30.0)
    assert d["starter_age_diff"] == pytest.approx(3.0)
    assert d["starter_import_diff"] == 1.0
    assert d["starter_seniority_diff"] == -8.0
    # 兩側皆缺 → 年齡差 0（完全中性）
    both = bio_diffs((None, "local", 2), (None, "local", 2), fill_age=30.0)
    assert both["starter_age_diff"] == 0.0
    assert both["starter_import_diff"] == 0.0
    assert both["starter_seniority_diff"] == 0.0


def test_percentile_ci_index_convention():
    draws = [float(i) for i in range(1, 101)]           # 1..100
    lo, hi = percentile_ci(draws, 0.99)
    assert lo == 1.0 and hi == 99.0                     # 索引法 int(q*(n−1))：0 與 98
    lo90, hi90 = percentile_ci(draws, 0.90)
    assert lo90 == 5.0 and hi90 == 95.0


def test_paired_bootstrap_deterministic_and_unrounded():
    deltas = [0.01, -0.02, 0.005, -0.001, 0.0]
    a = paired_bootstrap(deltas, reps=200, seed=42)
    b = paired_bootstrap(deltas, reps=200, seed=42)
    assert a == b                                       # seed 固定 → 全等
    assert a["point"] == pytest.approx(sum(deltas) / len(deltas))
    assert a["ci"][0] <= a["point"] <= a["ci"][1]


def test_brier():
    assert brier([0.5, 1.0], [1.0, 1.0]) == pytest.approx(0.125)
    assert brier([0.5], [0.5]) == 0.0                   # 和局 y=0.5 同口徑
