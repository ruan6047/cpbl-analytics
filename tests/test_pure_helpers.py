"""API 純函式單元測試：局數換算、評級、球數分桶、逐球結果分類、分項合併。

這些函式無 DB 依賴，直接 import 測。重構搬移時同步更新 import 路徑即可，
測試本身即為行為快照。
"""

from __future__ import annotations

import pytest

from cpbl.api.helpers import _ip_disp, _ip_real, _parse_features, _real_ip, _round
from cpbl.api.routers.ability import _grade
from cpbl.api.routers.players import _merge_splits
from cpbl.api.routers.tracking import _batted_result, _count_bucket, _zone_result
from cpbl.api.team_records import (
    BATTER_MILESTONES,
    PITCHER_MILESTONES,
    _franchise_approach,
    _next_milestone,
)

# ---- 局數記法換算（.1=⅓、.2=⅔） ----


def test_ip_real_baseball_notation():
    assert _ip_real(180.2) == pytest.approx(180 + 2 / 3)
    assert _ip_real(7.1) == pytest.approx(7 + 1 / 3)
    assert _ip_real(9.0) == pytest.approx(9.0)
    assert _ip_real(0.0) == 0.0
    assert _ip_real(None) is None


def test_real_ip_none_is_zero():
    # 歷史差異：_real_ip 把 None 視為 0.0（用於加總），_ip_real 保留 None（用於顯示）
    assert _real_ip(None) == 0.0
    assert _real_ip(180.2) == pytest.approx(180 + 2 / 3)


def test_ip_disp_roundtrip():
    for disp in (0.0, 0.1, 0.2, 1.0, 7.1, 99.2, 180.2):
        assert _ip_disp(_ip_real(disp)) == disp
    assert _ip_disp(None) is None


def test_ip_disp_carries_three_outs():
    # 2.999… 局（浮點誤差逼近 3 outs）要進位成整數局
    assert _ip_disp(2 + 2.9999 / 3) == 3.0


# ---- 雜項純函式 ----


def test_parse_features():
    assert _parse_features("a, b ,c,,") == ["a", "b", "c"]
    assert _parse_features("") == []


def test_round_none_passthrough():
    assert _round(None, 3) is None
    assert _round(0.12345, 3) == 0.123


def test_grade_thresholds():
    assert _grade(100) == "S"
    assert _grade(90) == "S"
    assert _grade(89.9) == "A"
    assert _grade(80) == "A"
    assert _grade(65) == "B"
    assert _grade(50) == "C"
    assert _grade(35) == "D"
    assert _grade(20) == "E"
    assert _grade(10) == "F"
    assert _grade(9.9) == "G"
    assert _grade(0) == "G"


def test_count_bucket_priority():
    assert _count_bucket(0, 2) == "兩好球"
    assert _count_bucket(3, 2) == "兩好球"  # 兩好優先於打者領先
    assert _count_bucket(0, 0) == "第一球"
    assert _count_bucket(0, 1) == "投手領先"
    assert _count_bucket(2, 0) == "打者領先"
    assert _count_bucket(1, 1) == "平球數"


# ---- 逐球結果分類（含 DB 雙重編碼還原） ----


def _double_encode(s: str) -> str:
    """模擬 DB 中 UTF-8 bytes 被當 latin-1 存的雙重編碼字串。"""
    return s.encode("utf-8").decode("latin-1")


def test_batted_result_double_encoded():
    assert _batted_result(_double_encode("陽春全壘打")) == "hr"
    assert _batted_result(_double_encode("三壘安打")) == "3b"
    assert _batted_result(_double_encode("二壘安打")) == "2b"
    assert _batted_result(_double_encode("內野安打")) == "1b"
    assert _batted_result(_double_encode("游擊滾地球出局")) == "out"


def test_batted_result_plain_and_none():
    assert _batted_result("全壘打") == "hr"  # 未雙重編碼也要能判
    assert _batted_result(None) == "out"
    assert _batted_result("") == "out"


def test_zone_result():
    assert _zone_result("StrikeSwinging", None) == "whiff"
    assert _zone_result("FoulBallNotFieldable", None) == "foul"
    assert _zone_result("InPlay", _double_encode("一壘安打")) == "hit"
    assert _zone_result("InPlay", _double_encode("飛球出局")) == "out"
    assert _zone_result("BallCalled", None) == "take"
    assert _zone_result(None, None) == "take"


# ---- 跨賽別分項合併 ----


def _brow(**kw) -> dict:
    base = dict.fromkeys(
        ["plate_appearances", "at_bats", "hits", "rbi", "singles", "doubles", "triples",
         "home_runs", "total_bases", "sac_hit", "sac_fly", "bb", "ibb", "hbp", "so",
         "ground_outs", "fly_outs"], 0)
    base.update({"item_group_code": "G1", "item_index": 1, "item_name": "vs 左投"})
    base.update(kw)
    return base


def test_merge_splits_batting_sums_and_rates():
    rows = [
        _brow(at_bats=10, hits=3, bb=1, total_bases=5, ground_outs=4, fly_outs=2),
        _brow(at_bats=10, hits=4, bb=1, total_bases=8, ground_outs=2, fly_outs=1),
    ]
    out = _merge_splits(rows, "batting")
    assert len(out) == 1
    g = out[0]
    assert g["at_bats"] == 20 and g["hits"] == 7
    assert g["avg"] == pytest.approx(0.35)
    # OBP = (H+BB+HBP)/(AB+BB+HBP+SF) = 9/22
    assert g["obp"] == pytest.approx(round(9 / 22, 4))
    assert g["slg"] == pytest.approx(round(13 / 20, 4))
    assert g["ops"] == pytest.approx(round(round(9 / 22, 4) + round(13 / 20, 4), 4))
    assert g["goao"] == pytest.approx(2.0)


def test_merge_splits_zero_ab_rates_are_none():
    out = _merge_splits([_brow(at_bats=0, bb=0)], "batting")
    assert out[0]["avg"] is None and out[0]["slg"] is None and out[0]["ops"] is None


def test_merge_splits_preserves_order_and_keys():
    rows = [
        _brow(item_group_code="G2", item_index=5, at_bats=1),
        _brow(item_group_code="G1", item_index=1, at_bats=2),
    ]
    out = _merge_splits(rows, "batting")
    assert [(r["item_group_code"], r["item_index"]) for r in out] == [("G2", 5), ("G1", 1)]


def test_merge_splits_pitching_outs_normalized():
    def prow(cnt, div3):
        base = dict.fromkeys(
            ["wins", "loses", "starts", "complete_games", "shutouts", "save_ok",
             "plate_appearances", "pitch_cnt", "strikes", "balls", "hits", "home_runs",
             "sac_hit", "sac_fly", "bb", "ibb", "hbp", "so", "wild_pitch", "balk",
             "runs", "earned_runs"], 0)
        base.update({"item_group_code": "P1", "item_index": 1,
                     "inning_pitched_cnt": cnt, "inning_pitched_div3": div3})
        return base

    # 5⅔ + 3⅔ = 9⅓ → cnt=9, div3=1
    out = _merge_splits([prow(5, 2), prow(3, 2)], "pitching")
    assert out[0]["inning_pitched_cnt"] == 9
    assert out[0]["inning_pitched_div3"] == 1


# ---- UX-TEAM-RECORDS1：里程碑階梯計算（純函式） ----


def test_next_milestone_matches_card_examples():
    # 卡面 Coordinator 實測範例：陳晨威生涯 891 安差 9 到 900；潘傑楷 490 差 10 到 500。
    assert _next_milestone(891, ladder=100, start=200) == (900, 9)
    assert _next_milestone(490, ladder=100, start=200) == (500, 10)


def test_next_milestone_below_start_threshold_is_far():
    # 90 安未達起始門檻(200)，下一個有效里程碑仍是 200，差距刻意很大（後續由呼叫端的
    # near 門檻過濾掉，不會誤標「快到了」）。
    milestone, gap = _next_milestone(90, ladder=100, start=200)
    assert milestone == 200
    assert gap == 110


def test_next_milestone_exact_multiple_rolls_to_next():
    # 現值剛好是階梯倍數（如剛達成 300 安）：下一個里程碑是 400，不是 300 本身。
    assert _next_milestone(300, ladder=100, start=200) == (400, 100)


def test_next_milestone_small_ladder():
    assert _next_milestone(22, ladder=25, start=25) == (25, 3)
    assert _next_milestone(78, ladder=10, start=20) == (80, 2)


def test_franchise_approach_excludes_sole_holder_and_far_gaps():
    stat_defs = [d for d in BATTER_MILESTONES if d["stat"] == "h"]
    roster = [
        {"player_id": "leader", "name": "領先者"},
        {"player_id": "close", "name": "逼近者"},
        {"player_id": "far", "name": "遙遠者"},
        {"player_id": "unknown", "name": "無隊史資料"},
    ]
    totals = {
        "leader": {"name": "領先者", "h": 1000},
        "close": {"name": "逼近者", "h": 997},   # 差 3 <= near(3)：單場 3 安可能達成
        "far": {"name": "遙遠者", "h": 500},      # 差 500 > near(3)
    }
    out = _franchise_approach(roster, totals, stat_defs, role="batting")
    assert [r["player_id"] for r in out] == ["close"]
    assert out[0]["record"] == 1000
    assert out[0]["remaining"] == 3
    assert out[0]["holder"] == "領先者"


def test_franchise_approach_empty_totals_is_empty():
    stat_defs = [d for d in BATTER_MILESTONES if d["stat"] == "h"]
    assert _franchise_approach([{"player_id": "x", "name": "x"}], {}, stat_defs, "batting") == []


def test_milestone_near_thresholds_match_2026_07_28_card_revision():
    # 卡面 2026-07-28 改判準為「單場可累積上限」：勝投/救援/中繼單場上限=1，
    # 其餘（含全壘打排除四響砲）單場上限=3。鎖住數值，避免日後不小心改回舊的
    # 「階梯 1/10~1/8」密度門檻。
    near_by_stat = {d["stat"]: d["near"] for d in [*BATTER_MILESTONES, *PITCHER_MILESTONES]}
    assert near_by_stat == {
        "h": 3, "rbi": 3, "r": 3, "hr": 3, "sb": 3,
        "so": 3, "ip": 3, "w": 1, "sv_hld": 1,
    }
