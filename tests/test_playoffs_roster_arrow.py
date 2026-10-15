"""#286 S05 WP3（A08 主責）：第 3 區冷熱箭頭邊界。

不重疊兩窗（W1 最近 15 次、W0 緊接在前 15 次）；29 次不比較、30 次比較；打數／出局 29/30；
OPS+ 差 14.9/15、ERA+ 差 19.9/20（正負向）；ERA=0 ⇒ undefined、不造 ∞；proposed 版本斷言。
"""

from __future__ import annotations

import pytest

from cpbl.api.routers.trend import N_ROLL, era_plus_raw, ops_plus_raw
from cpbl.playoffs import roster_reader as rr
from cpbl.playoffs.roster_reader import ARROW_POLICY, arrow_of, arrow_status

LG_OBP, LG_SLG, LG_ERA = 0.330, 0.380, 3.60


def bat(ab=2, h=0, bb=0, hbp=0, sf=0, tb=0):
    return {"ab": ab, "h": h, "bb": bb, "hbp": hbp, "sf": sf, "tb": tb}


def pit(outs=3, er=0):
    return {"ipc": outs // 3, "ip3": outs % 3, "er": er}


def arrow(rows, role="batting", **kw):
    return arrow_of(rows, role, lg_obp=kw.get("lg_obp", LG_OBP), lg_slg=kw.get("lg_slg", LG_SLG),
                    lg_era=kw.get("lg_era", LG_ERA))


def test_policy_is_prd_v2_proposed_values():
    assert ARROW_POLICY == {"version": "playoffs-arrow/prd-v2-proposed", "status": "proposed", "window": 15,
                            "bat_min_ab": 30, "pit_min_outs": 30, "ops_plus_delta": 15, "era_plus_delta": 20}
    assert ARROW_POLICY["window"] == N_ROLL        # 與球員頁走勢同一窗長


def test_payload_carries_policy_version_and_status():
    out = rr.compute_roster(rr.RosterInputs(year=2026, series="C", context={"series": {}}), now=__import__(
        "datetime").datetime(2026, 10, 16, tzinfo=__import__("datetime").UTC))
    assert out["arrow_policy"]["version"] == "playoffs-arrow/prd-v2-proposed"
    assert out["arrow_policy"]["status"] == "proposed"


@pytest.mark.parametrize("v1,v0,expect", [
    (114.9, 100, "flat"), (115, 100, "up"), (85.1, 100, "flat"), (85, 100, "down"),
])
def test_ops_plus_delta_boundary(v1, v0, expect):
    assert arrow_status(v1, v0, ARROW_POLICY["ops_plus_delta"]) == expect


@pytest.mark.parametrize("v1,v0,expect", [
    (119.9, 100, "flat"), (120, 100, "up"), (80.1, 100, "flat"), (80, 100, "down"),
])
def test_era_plus_delta_boundary(v1, v0, expect):
    assert arrow_status(v1, v0, ARROW_POLICY["era_plus_delta"]) == expect


def test_29_appearances_do_not_compare_30_do():
    assert arrow([bat()] * 29)["status"] == "insufficient"
    assert arrow([bat()] * 29)["reason"] == "appearances"
    assert arrow([bat(h=1, tb=1)] * 30)["status"] in ("up", "down", "flat")


def test_windows_do_not_overlap_and_use_newest_first():
    # W1＝前 15 列（最新），W0＝第 16–30 列；第 31 列以後不讀。
    rows = [bat(ab=2, h=2, tb=8)] * 15 + [bat(ab=2, h=0)] * 15 + [bat(ab=2, h=2, tb=8)] * 10
    a = arrow(rows)
    assert a["w1"]["ab"] == 30 and a["w0"]["ab"] == 30
    assert a["w1"]["h"] == 30 and a["w0"]["h"] == 0
    assert a["status"] == "up"
    assert a["appearances"] == 30


def _ab_rows(ab_w1, ab_w0):
    """W1／W0 各 15 次出賽，打數總和分別為 ab_w1、ab_w0（其餘場打數 0＝代跑形狀）。"""
    def window(total):
        out = [bat(ab=2, h=1, tb=1)] * (total // 2) + ([bat(ab=1, h=0)] if total % 2 else [])
        return out + [bat(ab=0)] * (15 - len(out))
    return window(ab_w1) + window(ab_w0)


def test_ab_29_vs_30_each_window():
    assert arrow(_ab_rows(29, 30))["status"] == "insufficient"
    assert arrow(_ab_rows(30, 29))["status"] == "insufficient"
    assert arrow(_ab_rows(30, 29))["reason"] == "sample"
    assert arrow(_ab_rows(30, 30))["status"] in ("up", "down", "flat")


def _outs_rows(o1, o0):
    def window(total):
        return [pit(outs=2, er=1)] * (total // 2) + ([pit(outs=1, er=0)] if total % 2 else []) \
            + [pit(outs=0)] * (15 - total // 2 - total % 2)
    return window(o1) + window(o0)


def test_outs_29_vs_30_each_window():
    assert arrow(_outs_rows(29, 30), "pitching")["status"] == "insufficient"
    assert arrow(_outs_rows(30, 29), "pitching")["status"] == "insufficient"
    assert arrow(_outs_rows(30, 30), "pitching")["status"] in ("up", "down", "flat")


def test_era_zero_is_undefined_keeps_era_and_sample():
    rows = [pit(outs=3, er=0)] * 15 + [pit(outs=3, er=1)] * 15
    a = arrow(rows, "pitching")
    assert a["status"] == "undefined" and a["reason"] == "era_zero"
    assert a["w1"]["era"] == 0.0 and a["w1"]["outs"] == 45
    assert a["w1"]["value"] is None and a["delta"] is None   # ⛔ ∞／999


def test_missing_baseline_is_undefined():
    rows = [bat(ab=2, h=1, tb=1)] * 30
    assert arrow(rows, lg_obp=None)["status"] == "undefined"
    assert arrow(rows, lg_obp=None)["reason"] == "baseline"


def test_raw_counts_summed_before_rate_and_unrounded_comparison():
    rows = [bat(ab=3, h=1, bb=1, tb=2)] * 15 + [bat(ab=3, h=1, tb=1)] * 15
    a = arrow(rows)
    obp1, slg1 = (15 + 15) / (45 + 15), 30 / 45
    obp0, slg0 = 15 / 45, 15 / 45
    d = ops_plus_raw(obp1, slg1, LG_OBP, LG_SLG) - ops_plus_raw(obp0, slg0, LG_OBP, LG_SLG)
    assert a["delta"] == round(d, 1)
    assert a["status"] == ("up" if d >= 15 else "down" if d <= -15 else "flat")


def test_pitching_down_direction_follows_era_plus_higher_is_better():
    rows = [pit(outs=3, er=1)] * 15 + [pit(outs=3, er=0)] * 14 + [pit(outs=3, er=1)]
    a = arrow(rows, "pitching")
    v1 = era_plus_raw(15 * 27 / 45, LG_ERA)
    v0 = era_plus_raw(1 * 27 / 45, LG_ERA)
    assert a["status"] == "down" and v1 < v0
