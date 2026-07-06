"""Marcel projection — 棒球界公認的「最笨但難打敗」成績預測 baseline。

三步驟：
1. 加權前 3 季（權重 5/4/3，近季權重高）。
2. 回歸聯盟均值（加入 reg_pa 個聯盟平均 PA，抑制小樣本暴衝）。
3. 年齡調整（以 29 歲為峰值，年輕加成、老化衰退）。

LightGBM 的存在價值就是要證明能比這條 baseline 更準；若打不贏 Marcel，
就代表模型沒學到東西——這是誠實的工程驗收標準。
"""

from __future__ import annotations

from cpbl.features.batting import STAT_DEFS, SeasonAgg

WEIGHTS = (5, 4, 3)  # lag1, lag2, lag3
DEFAULT_REG_PA = 200  # 回歸均值強度（單位：聯盟平均 PA）
PEAK_AGE = 29
YOUNG_SLOPE = 0.006  # < 29 歲：每年成長
OLD_SLOPE = 0.003  # > 29 歲：每年衰退


def _age_factor(age: int | None) -> float:
    if age is None:
        return 1.0
    slope = YOUNG_SLOPE if age < PEAK_AGE else OLD_SLOPE
    return 1.0 + (PEAK_AGE - age) * slope


def project_stat(
    priors: list[SeasonAgg | None],
    stat: str,
    age: int | None,
    league_rate: float,
    reg_pa: int = DEFAULT_REG_PA,
) -> float | None:
    """對單一 rate stat 做 Marcel 投影。priors = [lag1, lag2, lag3]。"""
    extractor = STAT_DEFS[stat]
    wnum = wden = 0.0
    for w, p in zip(WEIGHTS, priors, strict=False):
        if p is None:
            continue
        num, den = extractor(p.__dict__)
        wnum += w * num
        wden += w * den
    if wden == 0:
        return None
    reg_num = reg_pa * league_rate
    pre_age = (wnum + reg_num) / (wden + reg_pa)
    return pre_age * _age_factor(age)


def project(
    priors: list[SeasonAgg | None],
    age: int | None,
    league_rates: dict[str, float],
    reg_pa: int = DEFAULT_REG_PA,
) -> dict[str, float | None]:
    """產出 avg/obp/slg/ops 的 Marcel 投影。"""
    out: dict[str, float | None] = {}
    for stat in STAT_DEFS:
        out[stat] = project_stat(priors, stat, age, league_rates.get(stat, 0.0), reg_pa)
    out["ops"] = (
        (out["obp"] or 0) + (out["slg"] or 0) if out["obp"] is not None and out["slg"] is not None else None
    )
    return out


# ── 投手版 Marcel ────────────────────────────────────────────────────────────
# 與打者版差異：(1) 分母=outs、回歸壓艙量以出局數計（投手 rate 噪音更大，
# 壓艙量由 train 在「訓練期」內小格點挑選，給 baseline 最強版本才誠實）；
# (2) 年齡曲線方向感知——ERA/WHIP/BB9 低為佳，年輕改善=數值下降。

from cpbl.features.pitching import LOWER_BETTER as _P_LOWER_BETTER  # noqa: E402
from cpbl.features.pitching import STAT_DEFS as _P_STAT_DEFS  # noqa: E402

PIT_PEAK_AGE = 27
PIT_YOUNG_SLOPE = 0.004
PIT_OLD_SLOPE = 0.003
DEFAULT_REG_OUTS = 210  # 70 IP；train 會在訓練期 grid 覆寫


def _pit_age_factor(age: int | None, stat: str) -> float:
    if age is None:
        return 1.0
    slope = PIT_YOUNG_SLOPE if age < PIT_PEAK_AGE else PIT_OLD_SLOPE
    delta = (PIT_PEAK_AGE - age) * slope
    # 高為佳（k9）：年輕 → 乘 (1+delta)；低為佳（era/whip/bb9）：年輕 → 乘 (1-delta)
    return 1.0 - delta if stat in _P_LOWER_BETTER else 1.0 + delta


def project_pitching_stat(priors: list, stat: str, age: int | None,
                          league_rate: float, reg_outs: int = DEFAULT_REG_OUTS) -> float | None:
    """對單一投手 rate stat 做 Marcel 投影。priors = [lag1, lag2, lag3] SeasonAgg。"""
    extractor = _P_STAT_DEFS[stat]
    wnum = wden = 0.0
    for w, p in zip(WEIGHTS, priors, strict=False):
        if p is None:
            continue
        num, den = extractor(p.__dict__)
        wnum += w * num
        wden += w * den
    if wden == 0:
        return None
    pre_age = (wnum + reg_outs * league_rate) / (wden + reg_outs)
    return pre_age * _pit_age_factor(age, stat)


def project_pitching(priors: list, age: int | None, league_rates: dict[str, float],
                     reg_outs: int = DEFAULT_REG_OUTS) -> dict[str, float | None]:
    """產出 era/whip/k9/bb9 的 Marcel 投影。"""
    return {stat: project_pitching_stat(priors, stat, age,
                                        league_rates.get(stat, 0.0), reg_outs)
            for stat in _P_STAT_DEFS}
