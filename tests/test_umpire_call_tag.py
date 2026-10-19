"""#285 批次 G 判決標籤（``cpbl.models.umpire_call_tag``）。

純函式以合成落點驗規則（容差邊界、單方／兩方、資料不足）；黃金值（2026 E3 獅捨、C1 成全）與 2026 一軍命中率
以本機共享庫唯讀重算，證據見 #285 exec-8（probe/hitrate-2026A.json），不在單元測試內連庫。
"""

from __future__ import annotations

import pytest

from cpbl.models import umpire_call_tag as ut
from cpbl.models.pa_facts import _empty
from cpbl.models.umpire_impact import BALL_RADIUS_M, height_scaled_proxy_zone
from cpbl.playoffs import series_highlights as sh

H = 180
ZONE = height_scaled_proxy_zone(H)
MID = (ZONE.bottom + ZONE.top) / 2
R_CM = BALL_RADIUS_M * 100


def pitch(pa, call, side, height=MID, hcm=H):
    return {"pa_index": pa, "pitch_call": call, "plate_loc_side": side, "plate_loc_height": height, "height_cm": hcm}


def outside(cm):          # 球心在帶外（水平）cm 公分
    return ZONE.half_width + cm / 100


def inside(cm):           # 球心在帶內（水平）cm 公分
    return ZONE.half_width - cm / 100


QUAL = [{"pa_index": 1, "half": "1"}, {"pa_index": 2, "half": "2"}]
TRK = {1: "available", 2: "available"}


def tag(pitches, qual=QUAL, trk=TRK):
    return ut.umpire_call_tag(qual, trk, pitches, away="ADD011", home="AAA011")


def test_tolerance_boundaries_strike_and_ball():
    # 判好球：球心在「帶＋球半徑」外 >1 吋才算；帶外 R+2.54 cm 是邊界
    edge = R_CM + ut.TOLERANCE_CM
    assert ut.called_beneficiary("StrikeCalled", outside(edge - 0.1), MID, H) is None
    assert ut.called_beneficiary("StrikeCalled", outside(edge + 0.1), MID, H) == "fielding"
    # 判壞球：球心在「帶＋球半徑」內 >1 吋才算；帶外 R−2.54 cm 是邊界（帶內任何位置都算）
    edge_b = R_CM - ut.TOLERANCE_CM
    assert ut.called_beneficiary("BallCalled", outside(edge_b + 0.1), MID, H) is None
    assert ut.called_beneficiary("BallCalled", outside(edge_b - 0.1), MID, H) == "batting"
    assert ut.called_beneficiary("BallCalled", inside(5), MID, H) == "batting"
    # 一致的判決不算
    assert ut.called_beneficiary("StrikeCalled", inside(5), MID, H) is None
    assert ut.called_beneficiary("BallCalled", outside(20), MID, H) is None


def test_beneficiary_team_by_half_single_and_both_sides():
    # pa 1＝上半局（客隊 ADD011 進攻）：判好球在帶外 ⇒ 守備方（主隊 AAA011）得利
    assert tag([pitch(1, "StrikeCalled", outside(10))]) == {"team_code": "AAA011", "reason": None}
    # pa 1 判壞球在帶內 ⇒ 打擊方（客隊 ADD011）得利
    assert tag([pitch(1, "BallCalled", inside(3))]) == {"team_code": "ADD011", "reason": None}
    # pa 2＝下半局（主隊進攻）：判好球帶外 ⇒ 守備方客隊得利
    assert tag([pitch(2, "StrikeCalled", outside(10))]) == {"team_code": "ADD011", "reason": None}
    # 同一隊多次得利仍只回一次；兩隊都有 ⇒ 不出
    assert tag([pitch(1, "StrikeCalled", outside(10)), pitch(2, "BallCalled", inside(3))])["team_code"] == "AAA011"
    assert tag([pitch(1, "StrikeCalled", outside(10)), pitch(2, "StrikeCalled", outside(10))]) == \
        {"team_code": None, "reason": "both_sides"}
    assert tag([pitch(1, "StrikeCalled", inside(3))]) == {"team_code": None, "reason": "no_mismatch"}


@pytest.mark.parametrize(("pitches", "qual", "trk", "reason"), [
    ([], [], TRK, "no_qualifying_pa"),
    ([pitch(1, "StrikeCalled", outside(10))], QUAL, {1: "available", 2: "source_missing"}, "tracking_unavailable"),
    ([pitch(1, "StrikeCalled", outside(10), hcm=None)], QUAL, TRK, "batter_height_missing"),
    ([pitch(1, "StrikeCalled", None)], QUAL, TRK, "pitch_location_missing"),
])
def test_insufficient_data_means_whole_game_not_shown(pitches, qual, trk, reason):
    assert tag(pitches, qual, trk) == {"team_code": None, "reason": reason}


def test_qualifying_pas_threshold_and_missing_wp():
    facts = [{"pa_index": 1, "half": "1", "state": "ready"}, {"pa_index": 2, "half": "2", "state": "ready"},
             {"pa_index": 3, "half": "2", "state": "non_pa"}]
    swings = {1: {"delta": 0.10}, 2: {"delta": -0.0999}}
    assert ut.qualifying_pas(facts, swings) == [{"pa_index": 1, "half": "1"}]
    assert ut.qualifying_pas(facts, {1: {"delta": 0.5}}) is None          # ready 打席 2 缺 WP ⇒ 整場不處理
    assert ut.compute_from_facts(None, season=2026, kind_code="A", game_sno=1, facts=facts, swings={},
                                 wp_reason="winprob_model_not_built", game={}) == \
        {"team_code": None, "reason": "winprob_model_not_built"}


def test_non_authoritative_facts_payload_has_no_tag():
    assert _empty(2026, "A", 1, "pending", "awaiting_official_data")["umpire_call"] == \
        {"team_code": None, "reason": "not_authoritative"}


def test_playoffs_highlights_carries_umpire_call_per_ready_game_outside_input():
    from postseason_context_inputs import NOW_2026, inputs
    from test_playoffs_highlights import _rows

    from cpbl import postseason_contract as pc
    ctx = pc.compute_series_context(inputs(2026), now=NOW_2026)
    p = sh.compute_payload(ctx, "E", _rows([1, 2, 3, 4], drop={("livelog", 2)}), {},
                           {1: {"team_code": None, "reason": "no_mismatch"}, 3: {"team_code": "ADD011", "reason": None}})
    by = {g["series_game_no"]: g for g in p["games"]}
    assert by[3]["umpire_call"] == {"team_code": "ADD011", "reason": None}
    assert by[2]["umpire_call"] is None and by[2]["data_status"] == "pending"
    assert by[4]["umpire_call"] is None                     # 有資料但未算（未給）⇒ None
    assert "umpire_call" not in by[3]["input"]              # 不進 input（input 欄位集合不變）
    assert sh.compute_payload(ctx, "E", _rows([1]), {})["games"][0]["umpire_call"] is None


def test_playoffs_router_passes_umpire_for(monkeypatch):
    """正式 router 帶 connect=conn，series_highlights 不會自取判決標籤 ⇒ router 必須明確傳 umpire_for。"""
    import cpbl.playoffs.series_highlights as sh
    from cpbl.api.routers.playoffs_highlights import playoffs_highlights
    from cpbl.models.umpire_call_tag import game_umpire_call

    seen = {}

    def fake(season, series, **kw):
        seen.update(kw)
        return {}

    monkeypatch.setattr(sh, "series_highlights", fake)
    playoffs_highlights(season=2026, series="C")
    assert seen["umpire_for"] is game_umpire_call
