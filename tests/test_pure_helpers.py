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
    PITCHER_ROLE_NEAR,
    _classify_pitcher_role,
    _franchise_records,
    _merge_current_season,
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


def test_franchise_records_approaching_excludes_sole_holder_and_far_gaps():
    # prior == current here (no one refreshed anything this season) → pure「逼近中」情境。
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
    out = _franchise_records(roster, totals, totals, stat_defs, role="batting")
    assert [r["player_id"] for r in out] == ["close"]
    assert out[0]["state"] == "approaching"
    assert out[0]["record"] == 1000
    assert out[0]["remaining"] == 3
    assert out[0]["holder"] == "領先者"
    assert out[0]["holder_active"] is False  # active_ids 預設空集合


def test_franchise_records_empty_totals_is_empty():
    stat_defs = [d for d in BATTER_MILESTONES if d["stat"] == "h"]
    assert _franchise_records([{"player_id": "x", "name": "x"}], {}, {}, stat_defs, "batting") == []


def test_franchise_records_refreshed_state_when_current_exceeds_prior():
    # 卡面實例（曾子祐得分）的最小重現：現役球員本季總計超過「上季結束時」基準，
    # 且是目前唯一/並列最高者 → 呈現為成就，不是「還差 N」。
    stat_defs = [d for d in BATTER_MILESTONES if d["stat"] == "r"]
    roster = [{"player_id": "zeng", "name": "曾子祐"}]
    prior = {
        "zeng": {"name": "曾子祐", "r": 128},
        "mo_ying": {"name": "魔鷹", "r": 130},   # 上季結束時的隊史最高
    }
    current = {
        "zeng": {"name": "曾子祐", "r": 177},    # 128+49（本季franchise-scoped增量）
        "mo_ying": {"name": "魔鷹", "r": 162},   # 130+32，仍在，但已非最高
    }
    out = _franchise_records(roster, prior, current, stat_defs, role="batting")
    assert len(out) == 1
    assert out[0] == {
        "player_id": "zeng", "name": "曾子祐", "role": "batting",
        "stat": "r", "label": "得分", "state": "refreshed",
        "current": 177, "prior_record": 130, "prior_holder": "魔鷹",
        "prior_holder_id": "mo_ying", "ratio": 0.0,
    }


def test_franchise_records_prior_holder_id_self_refresh_uses_player_id_not_name():
    # 卡面實例（六隊實測 21 筆 refreshed 中 19 筆是自己刷新自己）：本季總計超過
    # 「自己上季結束時」的舊基準，`prior_holder_id` 必須等於自己的 player_id，
    # 前端才能靠 id 比對判斷「原紀錄保持人＝本人」進而省略原紀錄段落。
    #
    # 刻意讓 prior/current 的姓名字串不同（模擬改名或舊資料殘留名稱）：若實作
    # 誤退回姓名比對（例如用 `v["name"] == pl["name"]` 找 prior 持有人），會因
    # 字串不相等而找不到任何人，`prior_holder_id` 會變成 None——本斷言必須
    # 依 player_id（dict key）正確歸屬，不受姓名字串差異影響。
    stat_defs = [d for d in BATTER_MILESTONES if d["stat"] == "hr"]
    roster = [{"player_id": "p1", "name": "新名字"}]
    prior = {"p1": {"name": "舊名字（改名前）", "hr": 20}}
    current = {"p1": {"name": "新名字", "hr": 26}}

    out = _franchise_records(roster, prior, current, stat_defs, role="batting")

    assert len(out) == 1
    assert out[0]["state"] == "refreshed"
    assert out[0]["player_id"] == "p1"
    assert out[0]["prior_holder_id"] == "p1", (
        "prior_holder_id 必須依 player_id 歸屬本人，不能被姓名字串差異誤導為 None"
    )


def test_franchise_records_prior_holder_id_none_when_prior_tied_across_multiple_players():
    # 並列多人時（罕見邊界）：prior_holder_id 回傳 None，前端保守視為「不同人」
    # （寧可多顯示一個氣泡，也不要在並列情境下誤判成本人而漏掉資訊）。
    stat_defs = [d for d in BATTER_MILESTONES if d["stat"] == "hr"]
    roster = [{"player_id": "a", "name": "甲"}]
    prior = {"a": {"name": "甲", "hr": 20}, "b": {"name": "乙", "hr": 20}}  # 並列
    current = {"a": {"name": "甲", "hr": 26}}

    out = _franchise_records(roster, prior, current, stat_defs, role="batting")

    assert len(out) == 1
    assert out[0]["prior_holder_id"] is None


def test_franchise_records_no_refresh_without_prior_baseline():
    # franchise 在 *_seasons 完全沒有基準（理論上只會發生在一支隊伍的第一個
    # 有紀錄球季）：不判刷新——沒有基準就沒有「被刷新的對象」。
    stat_defs = [d for d in BATTER_MILESTONES if d["stat"] == "h"]
    roster = [{"player_id": "rookie", "name": "新秀"}]
    out = _franchise_records(roster, {}, {"rookie": {"name": "新秀", "h": 50}}, stat_defs, "batting")
    assert out == []


def test_franchise_records_only_current_leader_gets_refreshed_not_runner_up():
    # 兩位現役隊友都超過舊紀錄，只有目前真正最高者算刷新——避免同隊多人自稱刷新。
    #
    # 2026-07-28 需求方追加規則後更新：落後者原本會產生「approaching」（逼近
    # 「目前」最高，不是逼近舊紀錄），但現在**同一 stat 已有 refreshed 時該
    # approaching 會被抑制**（見下方
    # test_franchise_records_approaching_suppressed_when_refreshed_exists_for_same_stat
    # 的專屬覆蓋）——這裡改為只斷言「refreshed 歸屬正確（只有真正最高者，不是
    # 隨便誰超過舊紀錄就算）」，不再斷言 runner-up 的 approaching 列存在（那一半
    # 斷言現在由新規則的專屬測試覆蓋，且新行為下 runner-up 本來就不該出現）。
    stat_defs = [d for d in BATTER_MILESTONES if d["stat"] == "hr"]  # near=1
    roster = [{"player_id": "a", "name": "甲"}, {"player_id": "b", "name": "乙"}]
    prior = {"a": {"name": "甲", "hr": 55}, "b": {"name": "乙", "hr": 55}}
    current = {"a": {"name": "甲", "hr": 67}, "b": {"name": "乙", "hr": 66}}
    out = _franchise_records(roster, prior, current, stat_defs, "batting")
    states = {r["player_id"]: r["state"] for r in out}
    assert states == {"a": "refreshed"}


def test_franchise_records_approaching_suppressed_when_refreshed_exists_for_same_stat():
    # 卡面實例（台鋼雄鷹三振）的最小重現：後勁本季刷新隊史三振紀錄（163→216），
    # 艾速特差 8（在 near=10 門檻內）本會產出「approaching」——但兩張卡標題都是
    # 「三振」、外觀相同，讀者看不出在講同一件事。需求方裁定：同一 stat 已有
    # refreshed 時，該 stat 的 approaching 全部抑制（不反過來丟 refreshed——
    # 刷新是既成事實，逼近是進行式，留前者）。
    stat_defs = [{"stat": "so", "label": "三振", "ladder": 100, "start": 200, "near": 10}]
    roster = [{"player_id": "houjin", "name": "後勁"}, {"player_id": "aisute", "name": "艾速特"}]
    prior = {"houjin": {"name": "後勁", "so": 163}}
    current = {"houjin": {"name": "後勁", "so": 216}, "aisute": {"name": "艾速特", "so": 208}}

    out = _franchise_records(roster, prior, current, stat_defs, "pitching")

    states = {r["player_id"]: r["state"] for r in out}
    assert states == {"houjin": "refreshed"}, (
        "同一 stat 已有 refreshed 時，該 stat 的 approaching 必須被抑制——"
        f"實得 {states}"
    )


def test_franchise_records_approaching_kept_when_no_refreshed_for_stat():
    # 對照組：同一 stat 若沒有任何 refreshed（沒人刷新這項紀錄），approaching
    # 照常輸出——新規則不能誤傷「現行行為不變」的一般情境。
    stat_defs = [{"stat": "so", "label": "三振", "ladder": 100, "start": 200, "near": 10}]
    roster = [{"player_id": "a", "name": "甲"}, {"player_id": "b", "name": "乙"}]
    # prior_record（300）高於現在的 leader（250）→ 甲不算刷新（沒有真的超過舊紀錄）。
    prior = {"a": {"name": "甲", "so": 300}}
    current = {"a": {"name": "甲", "so": 250}, "b": {"name": "乙", "so": 245}}

    out = _franchise_records(roster, prior, current, stat_defs, "pitching")

    states = {r["player_id"]: r["state"] for r in out}
    assert states == {"b": "approaching"}
    assert not any(r["state"] == "refreshed" for r in out)


def test_franchise_records_holder_active_marker():
    # 目前持有人若仍在本隊現役名單，approaching 列須標注 holder_active=True——
    # 這是台鋼雄鷹「隊史紀錄是活的不是碑」場景的核心判準。
    stat_defs = [d for d in BATTER_MILESTONES if d["stat"] == "hr"]
    roster = [{"player_id": "chaser", "name": "追趕者"}]
    prior = {"holder": {"name": "持有人", "hr": 10}}
    current = {"holder": {"name": "持有人", "hr": 10}, "chaser": {"name": "追趕者", "hr": 9}}
    out_active = _franchise_records(roster, prior, current, stat_defs, "batting",
                                     active_ids=frozenset({"holder"}))
    assert out_active[0]["holder_active"] is True
    out_inactive = _franchise_records(roster, prior, current, stat_defs, "batting")
    assert out_inactive[0]["holder_active"] is False


def test_merge_current_season_adds_delta_only_for_roster():
    prior = {
        "active": {"name": "現役員", "h": 100},
        "retired": {"name": "退役員", "h": 200},
    }
    roster = [{"player_id": "active", "name": "現役員"}]
    delta = {"active": {"h": 15}}
    merged = _merge_current_season(prior, roster, delta, ["h"])
    assert merged["active"]["h"] == 115          # 100 + 15
    assert merged["retired"]["h"] == 200         # 非現役維持原值不動
    assert prior["active"]["h"] == 100           # 不得就地修改 prior（回傳新 dict）


def test_merge_current_season_roster_player_with_no_prior_row_starts_from_zero():
    # 現役新秀在 *_seasons 完全沒有基準列（史上首次代表這支 franchise 出賽）：
    # 從 0 起算再加本季增量，不是拋錯或跳過。
    merged = _merge_current_season(
        {}, [{"player_id": "new", "name": "新人"}], {"new": {"h": 5}}, ["h"])
    assert merged["new"]["h"] == 5


def test_milestone_near_thresholds_match_2026_07_28_measured_revision():
    # 卡面 2026-07-28 定版：near＝「單場達成 ≥N 發生率仍 ≥5% 的最大 N」，2018+ 一軍
    # 逐場資料實測值，逐項不同（不是階梯比例、也不是粗略的「單場上限」估計——
    # 勝投/救援中繼恰好兩者相符，其餘不相符）。三振／局數的實際 near 隨投手角色
    # 分流（見 test_pitcher_role_near_split_values），這裡鎖住的是 PITCHER_MILESTONES
    # 表內的固定值（w/sv_hld）與 so/ip 的 fallback（＝後援門檻，保守方向）。
    # 鎖住數值，避免日後不小心改回舊的「一律 ≤3」或「階梯 1/10~1/8」設計。
    near_by_stat = {d["stat"]: d["near"] for d in [*BATTER_MILESTONES, *PITCHER_MILESTONES]}
    assert near_by_stat == {
        "h": 3, "rbi": 2, "r": 2, "hr": 1, "sb": 1,
        "so": 2, "ip": 2, "w": 1, "sv_hld": 1,
    }


def test_pitcher_role_near_split_values():
    # 只有三振／局數需要角色分流（單場分布隨角色差一個數量級）；勝投/救援中繼
    # 結構上單場上限即 1，與角色無關，不在分流表內。
    assert PITCHER_ROLE_NEAR == {
        "so": {"starter": 8, "reliever": 2},
        "ip": {"starter": 7, "reliever": 2},
    }


def test_classify_pitcher_role_ratio_and_min_sample():
    # 佔比 >=0.5 才算先發；邊界值 0.5 本身算先發（>= 不是 >）。
    assert _classify_pitcher_role(starts=3, total=5) == "starter"     # 0.6
    assert _classify_pitcher_role(starts=5, total=10) == "starter"    # 0.5 邊界
    assert _classify_pitcher_role(starts=2, total=5) == "reliever"    # 0.4
    assert _classify_pitcher_role(starts=0, total=20) == "reliever"   # 純後援


def test_classify_pitcher_role_low_sample_is_always_reliever():
    # 本季出賽 <5 場者一律歸後援，即使全部都是先發（保守方向：樣本不足時不敢
    # 對後援門檻以外的宣稱背書，避免「差 8 個三振」掛在只投兩場的球員身上）。
    assert _classify_pitcher_role(starts=4, total=4) == "reliever"    # 全先發但只 4 場
    assert _classify_pitcher_role(starts=0, total=0) == "reliever"    # 本季無出賽（不除以零）
