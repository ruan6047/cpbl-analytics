"""TEAM-STYLE1 純函式單元測試：normalization 數學性質、軸計算封閉解、穩定性統計。"""

from __future__ import annotations

import math

from scripts.team_style_vectors import (
    batting_axes_raw,
    pearson,
    pitching_axes_raw,
    rank_desc,
    season_axis_z,
    split_half,
    zscores,
)

# ---------------------------------------------------------------------------
# zscores：季內聯盟 z 的數學性質
# ---------------------------------------------------------------------------


def test_zscores_mean_zero_std_one():
    zs = zscores([0.31, 0.27, 0.29, 0.35, 0.22])
    n = len(zs)
    mean = sum(zs) / n
    std = math.sqrt(sum((z - mean) ** 2 for z in zs) / n)  # 母體 ddof=0
    assert abs(mean) < 1e-12
    assert abs(std - 1.0) < 1e-12


def test_zscores_preserves_order_and_closed_form():
    # [1,2,3] 母體 std = sqrt(2/3) → z = ±sqrt(3/2), 0
    zs = zscores([1.0, 2.0, 3.0])
    expect = math.sqrt(1.5)
    assert abs(zs[0] + expect) < 1e-12
    assert abs(zs[1]) < 1e-12
    assert abs(zs[2] - expect) < 1e-12
    assert zs == sorted(zs)


def test_zscores_constant_input_returns_zeros():
    assert zscores([0.3, 0.3, 0.3, 0.3]) == [0.0, 0.0, 0.0, 0.0]


def test_zscores_empty():
    assert zscores([]) == []


# ---------------------------------------------------------------------------
# pearson：封閉解與退化案例
# ---------------------------------------------------------------------------


def test_pearson_perfect_positive_and_negative():
    assert abs(pearson([1, 2, 3], [2, 4, 6]) - 1.0) < 1e-12
    assert abs(pearson([1, 2, 3], [6, 4, 2]) + 1.0) < 1e-12


def test_pearson_known_value():
    # 手算：x=[1,2,3,4], y=[1,3,2,4] → cov 部分 4，sxx=5, syy=5 → r=0.8
    assert abs(pearson([1, 2, 3, 4], [1, 3, 2, 4]) - 0.8) < 1e-12


def test_pearson_degenerate_returns_none():
    assert pearson([1, 1, 1], [1, 2, 3]) is None  # 零變異
    assert pearson([1, 2], [1, 2]) is None  # n < 3


# ---------------------------------------------------------------------------
# split_half：前 n//2 為 H1、其餘為 H2（奇數場 H2 多一場）
# ---------------------------------------------------------------------------


def test_split_half_even_and_odd():
    assert split_half(120) == (60, 60)
    assert split_half(119) == (59, 60)
    assert split_half(1) == (0, 1)


# ---------------------------------------------------------------------------
# 軸計算式封閉解（spec §0.2）
# ---------------------------------------------------------------------------


def test_batting_axes_closed_form():
    agg = {
        "pa": 1000, "ab": 880, "h": 240, "singles": 160, "tb": 360,
        "sh": 20, "sf": 10, "bb": 80, "hbp": 10, "so": 200, "sb": 40, "cs": 10,
    }
    raw = batting_axes_raw(agg)
    assert abs(raw["sba_rate"] - 50 / 250) < 1e-12  # (40+10)/(160+80+10)
    assert abs(raw["sh_rate"] - 0.02) < 1e-12
    assert abs(raw["iso"] - (360 - 240) / 880) < 1e-12
    assert abs(raw["bb_rate"] - 0.08) < 1e-12
    assert abs(raw["k_rate"] - 0.2) < 1e-12


def test_pitching_axes_closed_form():
    agg = {
        "outs": 3240, "starter_outs": 1944, "pa_against": 4500,
        "h_a": 1050, "hr_a": 90, "bb_a": 400, "hbp_a": 50, "so_a": 900,
    }
    raw = pitching_axes_raw(agg)
    assert abs(raw["starter_share"] - 0.6) < 1e-12
    assert abs(raw["kpct"] - 0.2) < 1e-12
    # BIP = 4500-400-50-900-90 = 3060；DER = 1 - (1050-90)/3060
    assert abs(raw["der"] - (1 - 960 / 3060)) < 1e-12


def test_axes_zero_denominators_return_none():
    zero_bat = dict.fromkeys(
        ("pa", "ab", "h", "singles", "tb", "sh", "sf", "bb", "hbp", "so", "sb", "cs"), 0)
    assert all(v is None for v in batting_axes_raw(zero_bat).values())
    zero_pit = dict.fromkeys(
        ("outs", "starter_outs", "pa_against", "h_a", "hr_a", "bb_a", "hbp_a", "so_a"), 0)
    assert all(v is None for v in pitching_axes_raw(zero_pit).values())


# ---------------------------------------------------------------------------
# season_axis_z：複合軸與尺度
# ---------------------------------------------------------------------------


def _raw(sba, sh, iso, bb, k, ss, kp, der):
    return {"sba_rate": sba, "sh_rate": sh, "iso": iso, "bb_rate": bb,
            "k_rate": k, "starter_share": ss, "kpct": kp, "der": der}


def test_season_axis_z_scale_and_polarity():
    raw = {
        "T1": _raw(0.10, 0.02, 0.12, 0.10, 0.15, 0.60, 0.22, 0.70),
        "T2": _raw(0.06, 0.01, 0.15, 0.08, 0.20, 0.55, 0.18, 0.68),
        "T3": _raw(0.02, 0.03, 0.10, 0.06, 0.25, 0.50, 0.20, 0.72),
    }
    z = season_axis_z(raw)
    for axis in ("speed", "smallball", "power", "discipline",
                 "starter_ip", "pitch_k", "defense"):
        vals = [z[t][axis] for t in ("T1", "T2", "T3")]
        mean = sum(vals) / 3
        std = math.sqrt(sum((v - mean) ** 2 for v in vals) / 3)
        assert abs(mean) < 1e-9, axis  # 季內 z：mean 0
        assert abs(std - 1.0) < 1e-9, axis  # 複合軸重新標準化後同尺度
    # 極性：T1 盜壘企圖率最高 → speed 最高；T3 K 率最高 → discipline 最低
    assert z["T1"]["speed"] == max(z[t]["speed"] for t in z)
    assert z["T3"]["discipline"] == min(z[t]["discipline"] for t in z)
    # discipline 封閉解：bb_rate z 與 −k_rate z 對 T1>T2>T3 同向 → 排序 T1>T2>T3
    assert z["T1"]["discipline"] > z["T2"]["discipline"] > z["T3"]["discipline"]


def test_rank_desc():
    z = {"A": 1.2, "B": -0.3, "C": 0.1}
    assert rank_desc(z, "A") == 1
    assert rank_desc(z, "C") == 2
    assert rank_desc(z, "B") == 3
