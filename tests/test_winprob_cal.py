"""GAME-RECAP-WP-CAL1 校準層離線測試（無 DB）。

核心合約（對應卡面統計紅線）：
1. 單調性 / 值域 [0,1] / 端點 f(0)=0、f(1)=1（終場收斂語意）——兩族皆須成立。
2. isotonic 小樣本尾端防護：每 PAV 區塊 ≥ min_bin_n、段數 ≤ max_bins、
   訓練對不足直接拒絕（fail closed）。
3. 嵌套時間分離：calibration_pairs 只吐 s < 驗證季 的 wf 對。
4. 選型規則決定性且只消費內部窗指標。
5. 判定閘門：v2 門檻沿用未放寬 + 「不得劣於未校準 base」+ 逐局帶惡化規則。
6. 可重跑性：擬合對輸入順序不敏感（DB 列序無關）。
"""

from __future__ import annotations

import math
import random

import pytest

from cpbl.models.winprob_cal import (
    CAL_THRESHOLDS,
    apply_calibrator,
    band_of,
    band_summary,
    cal_verdict,
    calibration_pairs,
    fit_beta,
    fit_isotonic,
    select_family,
)
from cpbl.models.winprob_val import THRESHOLDS

N_OK = CAL_THRESHOLDS["min_cal_pairs"]


def _synth_pairs(n: int, seed: int = 11, stretch: float = 1.0) -> list[tuple[float, float]]:
    """合成 (pred, outcome)：真實機率 = sigmoid(stretch·logit(pred))。

    stretch > 1 重現 WP-VAL1 的 S 型偏差方向：低分箱被高估、高分箱被低估
    （pred 0.15 → actual ~0.11、pred 0.85 → actual ~0.89）。"""
    rng = random.Random(seed)
    out = []
    for _ in range(n):
        p = min(max(rng.random(), 0.02), 0.98)
        z = stretch * math.log(p / (1 - p))
        true = 1 / (1 + math.exp(-z))
        out.append((p, 1.0 if rng.random() < true else 0.0))
    return out


# ───────────────────────── 單調 / 值域 / 端點（紅線 3） ─────────────────────────
GRID = [i / 200 for i in range(201)]


@pytest.mark.parametrize("fit", [fit_isotonic, fit_beta])
def test_monotone_range_endpoints(fit):
    cal = fit(_synth_pairs(N_OK, seed=3, stretch=1.6))
    vals = [cal.predict(p) for p in GRID]
    assert all(0.0 <= v <= 1.0 for v in vals)
    assert all(b >= a - 1e-12 for a, b in zip(vals, vals[1:], strict=False))  # 單調不減
    assert cal.predict(0.0) == 0.0 and cal.predict(1.0) == 1.0               # 終場收斂
    assert cal.predict(-0.5) == 0.0 and cal.predict(1.5) == 1.0              # 超界夾住


@pytest.mark.parametrize("fit", [fit_isotonic, fit_beta])
def test_monotone_preserves_ordering(fit):
    """單調映射不改變任兩狀態的 WP 次序 → 再見門檻語意（跨越次序）不被破壞。"""
    cal = fit(_synth_pairs(N_OK, seed=5, stretch=1.4))
    ps = sorted(random.Random(9).random() for _ in range(500))
    cs = [cal.predict(p) for p in ps]
    assert all(b >= a - 1e-12 for a, b in zip(cs, cs[1:], strict=False))


# ───────────────────────── isotonic 專屬合約 ─────────────────────────
def test_isotonic_pav_known_example():
    """箱均值出現違序時 PAV 必須合併：構造兩箱違序的極小可辨資料。"""
    # 4000 筆 pred≈0.2 全負、4000 筆 pred≈0.4 其中一半正——低段實際 0、高段 0.5
    pairs = ([(0.2 + i * 1e-6, 0.0) for i in range(4000)]
             + [(0.4 + i * 1e-6, 1.0 if i % 2 else 0.0) for i in range(4000)])
    cal = fit_isotonic(pairs, min_bin_n=2000, max_bins=4)
    # 低段校準值必須低於高段（保持資料的單調訊號），且值域正確
    assert cal.predict(0.2) < cal.predict(0.4)
    assert abs(cal.predict(0.2) - 0.0) < 0.05
    assert abs(cal.predict(0.4) - 0.5) < 0.05


def test_isotonic_tail_guard_bin_floor_and_segment_cap():
    pairs = _synth_pairs(30000, seed=7, stretch=1.5)
    cal = fit_isotonic(pairs)
    assert cal.n_segments <= CAL_THRESHOLDS["iso_max_bins"]
    assert all(n >= CAL_THRESHOLDS["iso_min_bin_n"] for n in cal.bin_ns)
    assert sum(cal.bin_ns) == len(pairs)


def test_isotonic_small_n_shrinks_segments():
    """樣本剛過下限時段數退化（n // min_bin_n），不會出現小樣本尾端細段。"""
    pairs = _synth_pairs(N_OK, seed=13)
    cal = fit_isotonic(pairs)
    assert cal.n_segments <= N_OK // CAL_THRESHOLDS["iso_min_bin_n"]


@pytest.mark.parametrize("fit", [fit_isotonic, fit_beta])
def test_reject_insufficient_pairs(fit):
    with pytest.raises(ValueError, match="拒絕擬合"):
        fit(_synth_pairs(N_OK - 1))


@pytest.mark.parametrize("fit", [fit_isotonic, fit_beta])
def test_fit_order_invariant(fit):
    """擬合結果與輸入列序無關（DB 無 ORDER BY 也可逐位重現）。"""
    pairs = _synth_pairs(8000, seed=17, stretch=1.3)
    shuffled = pairs[:]
    random.Random(99).shuffle(shuffled)
    c1, c2 = fit(pairs), fit(shuffled)
    assert c1.params() == c2.params()


# ───────────────────────── beta 專屬合約 ─────────────────────────
def test_beta_near_identity_on_calibrated_data():
    cal = fit_beta(_synth_pairs(60000, seed=21, stretch=1.0))
    assert abs(cal.a - 1.0) < 0.15 and abs(cal.b - 1.0) < 0.15 and abs(cal.c) < 0.1
    assert not cal.at_bound
    for p in (0.1, 0.3, 0.5, 0.7, 0.9):
        assert abs(cal.predict(p) - p) < 0.03


def test_beta_learns_stretch_direction():
    """S 型偏差（真實比預測更極端）→ a,b > 1：低端往下拉、高端往上推。"""
    cal = fit_beta(_synth_pairs(60000, seed=23, stretch=1.6))
    assert cal.a > 1.1 and cal.b > 1.1
    assert cal.predict(0.15) < 0.15
    assert cal.predict(0.85) > 0.85


@pytest.mark.parametrize("fit", [fit_isotonic, fit_beta])
def test_calibration_improves_biased_predictions(fit):
    """對 S 型偏差資料，校準後留出樣本 Brier 必須改善（同分布、不同 seed）。"""
    cal = fit(_synth_pairs(60000, seed=31, stretch=1.6))
    held = _synth_pairs(60000, seed=37, stretch=1.6)
    base = sum((p - y) ** 2 for p, y in held) / len(held)
    caled = sum((cal.predict(p) - y) ** 2 for p, y in held) / len(held)
    assert caled < base


# ───────────────────────── 嵌套時間分離（紅線 1/2） ─────────────────────────
def _fake_wf(*years):
    return {y: [(0.5, 1.0, False, (y, "A", i)) for i in range(3)] for y in years}


def test_calibration_pairs_strictly_before_target():
    wf = _fake_wf(2021, 2022, 2023, 2024, 2025)
    seasons, pairs = calibration_pairs(wf, 2023)
    assert seasons == [2021, 2022]
    assert len(pairs) == 6                      # 只含 2021+2022 的對
    seasons, pairs = calibration_pairs(wf, 2026)
    assert seasons == [2021, 2022, 2023, 2024, 2025]


def test_calibration_pairs_rejects_empty_window():
    with pytest.raises(ValueError, match="無可用校準窗"):
        calibration_pairs(_fake_wf(2021, 2022), 2021)


def test_calibration_pairs_ignores_pre_first_season():
    """first_season 之前的季（無 wf 語意保證）不得進入校準窗。"""
    wf = _fake_wf(2019, 2021, 2022)
    seasons, _ = calibration_pairs(wf, 2023)
    assert seasons == [2021, 2022]


# ───────────────────────── 選型（紅線 6） ─────────────────────────
def test_select_family_by_brier_then_ece_then_parsimony():
    iso, beta = {"brier": 0.150, "ece_weighted": 0.02}, {"brier": 0.151, "ece_weighted": 0.01}
    assert select_family({"isotonic": iso, "beta": beta})[0] == "isotonic"
    iso = {"brier": 0.151, "ece_weighted": 0.02}
    beta = {"brier": 0.150, "ece_weighted": 0.03}
    assert select_family({"isotonic": iso, "beta": beta})[0] == "beta"
    tie_brier = {"brier": 0.150, "ece_weighted": 0.010}
    assert select_family({"isotonic": tie_brier,
                          "beta": {"brier": 0.150, "ece_weighted": 0.012}})[0] == "isotonic"
    same = {"brier": 0.150, "ece_weighted": 0.010}
    choice, why = select_family({"isotonic": same, "beta": dict(same)})
    assert choice == "beta" and "低複雜度" in why


# ───────────────────────── 套用與逐局帶 ─────────────────────────
def test_apply_calibrator_preserves_metadata():
    cal = fit_isotonic(_synth_pairs(N_OK, seed=41))
    scored = [(0.3, 1.0, False, ("g", 1)), (0.8, 0.5, True, ("g", 2))]
    out = apply_calibrator(cal, scored)
    assert [(y, irr, gk) for _, y, irr, gk in out] == \
        [(y, irr, gk) for _, y, irr, gk in scored]
    assert all(0.0 <= wp <= 1.0 for wp, *_ in out)


def test_band_of_edges():
    assert band_of(1) == "1-3" and band_of(3) == "1-3"
    assert band_of(4) == "4-6" and band_of(6) == "4-6"
    assert band_of(7) == "7-9" and band_of(9) == "7-9"
    assert band_of(10) == "10+" and band_of(14) == "10+"


def test_band_summary_alignment():
    innings = [1, 5, 9, 12]
    scored = [(0.4, 0.0, False, 1), (0.6, 1.0, False, 1),
              (0.7, 1.0, False, 2), (0.9, 1.0, False, 2)]
    bands = band_summary(innings, scored)
    assert bands["1-3"]["n"] == 1 and bands["4-6"]["n"] == 1
    assert bands["7-9"]["pred"] == 0.7 and bands["10+"]["actual"] == 1.0
    with pytest.raises(ValueError):
        band_summary([1, 2], scored)            # 長度不齊 → strict zip 直接炸


# ───────────────────────── 判定閘門（紅線 4/5） ─────────────────────────
def _srow(year=2024, *, cov=1.0, cal_brier=0.150, base_brier=0.153, home=0.245, sig=()):
    return {"year": year, "coverage": cov,
            "calibrated": {"brier": cal_brier, "significant_bins": list(sig)},
            "base": {"brier": base_brier},
            "baseline_home_const": {"brier": home}}


def _pooled_cal(deciles=()):
    return {"n_pa": 100000, "deciles": list(deciles)}


def _bands(dev=0.01, n=30000):
    return {b: {"n": n, "pred": 0.5 + dev, "actual": 0.5, "brier": 0.15}
            for b in ("1-3", "4-6", "7-9")}


def test_verdict_supported_when_all_gates_pass():
    v = cal_verdict([_srow(2023), _srow(2024)], _pooled_cal(), _bands(0.02), _bands(0.01))
    assert v["status"] == "supported"
    assert not v["reasons"]


def test_verdict_hard_fail_worse_than_uncalibrated_base():
    v = cal_verdict([_srow(cal_brier=0.154, base_brier=0.153)], _pooled_cal(),
                    _bands(), _bands())
    assert v["status"] == "unsupported"
    assert any("劣於未校準 base" in r for r in v["reasons"])


def test_verdict_hard_fail_vs_home_baseline_and_coverage():
    v = cal_verdict([_srow(cal_brier=0.25, home=0.245)], _pooled_cal(), _bands(), _bands())
    assert any("未勝主場常數基準" in r for r in v["reasons"])
    v = cal_verdict([_srow(cov=0.97)], _pooled_cal(), _bands(), _bands())
    assert any("coverage" in r for r in v["reasons"])


def test_verdict_pooled_decile_gate_matches_v2():
    big = {"bin": 2, "pred": 0.25, "actual": 0.21, "n": 8000,
           "dev_ci": [0.01, 0.07]}
    v = cal_verdict([_srow()], _pooled_cal([big]), _bands(), _bands())
    assert v["status"] == "unsupported"
    bounded = {"bin": 2, "pred": 0.52, "actual": 0.50, "n": 8000,
               "dev_ci": [0.005, 0.036]}
    v = cal_verdict([_srow()], _pooled_cal([bounded]), _bands(), _bands())
    assert v["status"] == "supported"
    assert any("受控" in d for d in v["disclosure"])
    small_n = {"bin": 2, "pred": 0.25, "actual": 0.20, "n": 800,
               "dev_ci": [0.01, 0.09]}
    v = cal_verdict([_srow()], _pooled_cal([small_n]), _bands(), _bands())
    assert v["status"] == "supported"           # n<1000 分箱不進判定（v2 同語意）


def test_verdict_band_worsening_rules():
    # 單帶惡化 >2pt → 硬性
    worse = _bands(0.01)
    worse["7-9"] = {"n": 30000, "pred": 0.55, "actual": 0.50, "brier": 0.15}
    v = cal_verdict([_srow()], _pooled_cal(), _bands(0.02), worse)
    assert any("惡化" in r and "7-9" in r for r in v["reasons"])
    # 兩帶各惡化 >1pt（未達 2pt）→ 系統性惡化硬性
    two = _bands(0.035)
    v = cal_verdict([_srow()], _pooled_cal(), _bands(0.02), two)
    assert any("系統性惡化" in r for r in v["reasons"])
    # 單帶 1.2pt → 只揭露
    one = _bands(0.02)
    one["4-6"] = {"n": 30000, "pred": 0.532, "actual": 0.50, "brier": 0.15}
    v = cal_verdict([_srow()], _pooled_cal(), _bands(0.02), one)
    assert v["status"] == "supported"
    assert any("4-6" in d for d in v["disclosure"])


def test_verdict_extras_band_disclosure_only():
    base_b, cal_b = _bands(0.01), _bands(0.005)
    base_b["10+"] = {"n": 500, "pred": 0.55, "actual": 0.50, "brier": 0.2}
    cal_b["10+"] = {"n": 500, "pred": 0.60, "actual": 0.50, "brier": 0.2}   # 惡化 5pt
    v = cal_verdict([_srow()], _pooled_cal(), base_b, cal_b)
    assert v["status"] == "supported"           # 10+ 不否決
    assert any("10+" in d for d in v["disclosure"])


def test_v2_thresholds_not_relaxed():
    """判定沿用 WP-VAL1 v2 門檻——常數被改動（放寬）時本測試必須紅。"""
    assert THRESHOLDS["pooled_bin_dev_max"] == 0.03
    assert THRESHOLDS["min_coverage"] == 0.98
    assert THRESHOLDS["boot_ci"] == 0.99
    assert CAL_THRESHOLDS["min_cal_pairs"] == 5000
    assert CAL_THRESHOLDS["iso_min_bin_n"] == 500
