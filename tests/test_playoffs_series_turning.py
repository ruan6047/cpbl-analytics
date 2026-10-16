"""#288 S07 WP-G3 三大轉折（``series_summary.turning_points`` 與 ``aggregate`` 的轉折段）純函式。

打席與勝率都是合成值：勝率替身 ``scorer`` 依 (局, 半局) 查表，故某打席的 ΔWP＝下一打席局面的值 −
本打席局面的值（最後一個打席接終場結果），與 :func:`pa_facts.wp_swings` 的錨點語意一致。
真實 E1–E4 的整合在 isolated 測試與執行階段對帳 artifact。
"""

from __future__ import annotations

import pytest

from cpbl.models import pa_facts
from cpbl.playoffs import series_summary as ss


def g(no: int, *, home: int | None = 3, away: int | None = 1, kind="E"):
    return {"series_game_no": no, "game_key": {"year": 2026, "kind_code": kind, "game_sno": no},
            "away_team_code": "AWY", "home_team_code": "HOM", "home_score": home, "away_score": away}


def f(i: int, inning: int, *, half="1", d_re=0.1, state="ready", pa_id=None):
    return {"pa_index": i, "pa_id": pa_id or f"pa-{i:03d}", "state": state, "inning": inning, "half": half,
            "outs_before": 0, "bases_before": [], "away_score_before": 0, "home_score_before": 0,
            "away_score_after": 0, "home_score_after": 0, "hitter": {"player_id": f"H{i}", "name": None},
            "pitcher": {"player_id": f"P{i}", "name": None}, "result_action": "一壘安打",
            "delta_re24": d_re, "unavailable_reason": None}


def scorer_from(table: dict[tuple[int, str], float]):
    return lambda inning, half, diff, bases, outs: table[(inning, half)]


def facts_with_swings(swings: list[float], *, start=0.5, final=1.0, d_re=0.1):
    """依序產生打席，使第 k 個打席的 ΔWP＝swings[k]（最後一個接終場 final，需與累計值一致）。"""
    table, facts, wp = {}, [], start
    for k, _ in enumerate(swings):
        table[(k + 1, "1")] = wp
        facts.append(f(k, k + 1, d_re=d_re))
        wp = round(wp + swings[k], 4)
    assert abs(wp - final) < 1e-9, "測試資料：累計後須等於終場結果"
    return facts, table


def test_population_is_whole_series_not_per_game_top_n():
    # G1 有 4 個中等擺動、G2 只有 1 個最大擺動：前 3 應是 G2 那筆＋G1 最大的 2 筆（跨場比較，不先單場截）
    f1, t1 = facts_with_swings([0.10, 0.09, 0.08, 0.07, 0.16], start=0.5, final=1.0)
    f2, t2 = facts_with_swings([0.30, 0.20], start=0.5, final=1.0)
    table = {**t1, **{(k + 100, h): v for (k, h), v in t2.items()}}
    for x in f2:
        x["inning"] += 100
    out = ss.turning_points([(g(1), f1), (g(2), f2)], scorer=scorer_from(table), scorer_reason=None,
                            full_scope=True)
    assert out["signal"] == "delta_wp" and out["degraded"] is False and out["scope"] == "full"
    picked = [(t["series_game_no"], t["pa_index"], t["delta_wp"]) for t in out["items"]]
    assert sorted(abs(p[2]) for p in picked) == [0.16, 0.2, 0.3]
    # 取定後依時間排序（系列場序、pa_index）
    assert [(p[0], p[1]) for p in picked] == [(1, 4), (2, 0), (2, 1)]


def test_tie_break_by_game_then_pa_index_then_pa_id():
    f1, t1 = facts_with_swings([0.10, 0.10, 0.30], start=0.5, final=1.0)
    out = ss.turning_points([(g(1), f1)], scorer=scorer_from(t1), scorer_reason=None, full_scope=True, limit=2)
    # 0.30 必選；兩個 0.10 平手取 pa_index 小者
    assert [t["pa_index"] for t in out["items"]] == [0, 2]


def test_threshold_kept_and_fewer_than_three_not_padded():
    f1, t1 = facts_with_swings([0.02, 0.01, 0.47], start=0.5, final=1.0)
    out = ss.turning_points([(g(1), f1)], scorer=scorer_from(t1), scorer_reason=None, full_scope=True)
    assert [t["pa_index"] for t in out["items"]] == [2]          # 0.02／0.01 低於 0.03，不補
    assert out["min_abs"] == pa_facts.KEY_PLAY_MIN_WP_ABS


def test_home_perspective_sign_is_kept():
    f1, t1 = facts_with_swings([-0.40, -0.10], start=0.5, final=0.0)
    out = ss.turning_points([(g(1, home=0, away=2), f1)], scorer=scorer_from(t1), scorer_reason=None,
                            full_scope=True)
    assert [t["delta_wp"] for t in out["items"]] == [-0.4, -0.1]


def test_any_game_without_wp_degrades_whole_group_to_re24():
    f1, t1 = facts_with_swings([0.30, 0.20], start=0.5, final=1.0)
    for x, d in zip(f1, (0.2, 0.9), strict=True):
        x["delta_re24"] = d
    f2 = [f(0, 50, d_re=-1.5), f(1, 51, d_re=0.31), f(2, 52, d_re=0.29)]
    # G2 比分未知 ⇒ 拿不到 WP ⇒ 整組改 |ΔRE24|，不混用
    out = ss.turning_points([(g(1), f1), (g(2, home=None), f2)], scorer=scorer_from(t1), scorer_reason=None,
                            full_scope=True)
    assert out["signal"] == "delta_re24" and out["degraded"] is True
    assert out["reason"] == "final_unknown" and out["degraded_games"] == [2]
    assert out["min_abs"] == pa_facts.KEY_PLAY_MIN_ABS
    assert [(t["series_game_no"], t["pa_index"]) for t in out["items"]] == [(1, 1), (2, 0), (2, 1)]
    assert all(t["delta_wp"] is None for t in out["items"])


def test_no_scorer_degrades_with_its_reason():
    f1 = [f(0, 1, d_re=0.5), f(1, 2, d_re=0.1)]
    out = ss.turning_points([(g(1), f1)], scorer=None, scorer_reason="winprob_model_not_built", full_scope=False)
    assert (out["signal"], out["reason"], out["scope"]) == ("delta_re24", "winprob_model_not_built", "covered_only")
    assert [t["pa_index"] for t in out["items"]] == [0]


def test_facts_without_delta_re24_are_not_candidates():
    f1, t1 = facts_with_swings([0.30, 0.20], start=0.5, final=1.0)
    f1[0]["delta_re24"] = None
    out = ss.turning_points([(g(1), f1)], scorer=scorer_from(t1), scorer_reason=None, full_scope=True)
    assert [t["pa_index"] for t in out["items"]] == [1]


def test_output_has_no_text_and_carries_teams():
    f1, t1 = facts_with_swings([0.5], start=0.5, final=1.0)
    item = ss.turning_points([(g(1), f1)], scorer=scorer_from(t1), scorer_reason=None, full_scope=True)["items"][0]
    assert (item["away_team_code"], item["home_team_code"]) == ("AWY", "HOM")
    assert not any(k in item for k in ("text", "sentence", "label"))


# --- scorer_for：既有解算器的取得與降級原因 -------------------------------------------------------------

def test_scorer_for_reasons(monkeypatch):
    from cpbl.models import winprob_scorer as ws

    assert ss.scorer_for("F", 2026) == (None, "wp_scope_unsupported")
    monkeypatch.setattr(ws, "get_scorer", lambda k, s: (None, None))
    assert ss.scorer_for("C", 2026) == (None, "winprob_model_not_built")

    def boom(k, s):
        raise RuntimeError("x")
    monkeypatch.setattr(ws, "get_scorer", boom)
    assert ss.scorer_for("E", 2026) == (None, "winprob_model_error")
    sentinel = object()
    monkeypatch.setattr(ws, "get_scorer", lambda k, s: (sentinel, {}))
    assert ss.scorer_for("E", 2026) == (sentinel, None)


# --- 掛在 aggregate／summary_json：E/C 隔離、姓名、未涵蓋 ----------------------------------------------

@pytest.fixture
def ctx():
    from postseason_context_inputs import NOW_2026, games, inputs

    from cpbl import postseason_contract as pc
    return pc.compute_series_context(inputs(2026, games_override=games(2026)), now=NOW_2026)


def _rows_from(per_game: dict) -> ss.SeriesRows:
    re = {(b1 + b2 + b3, o): 0.0 for b1 in "1_" for b2 in "2_" for b3 in "3_" for o in (0, 1, 2)}
    return ss.SeriesRows(pas=per_game, livelog={}, members={}, re_map=re, build_ids={k: "b" for k in per_game})


def test_aggregate_turning_isolated_per_series_and_scope(ctx, monkeypatch):
    # delta_re24 替身：把 PA 列原樣當事實（PA 列已帶事實欄位）
    monkeypatch.setattr(pa_facts, "delta_re24", lambda pas, events, re_map, *, game_completed=True: [dict(p) for p in pas])
    asked: list[tuple[str, int]] = []

    def fake_scorer_for(kind, season):
        asked.append((kind, season))
        return None, "winprob_model_not_built"

    pa = {**f(0, 1, d_re=0.9), "hitter_acnt": "HX", "end_pitcher_acnt": "PX", "start_pitcher_acnt": "PX",
          "outcome_family": "single", "pre_state": {"half": "1"}}
    rows = _rows_from({("E", 1): [pa], ("E", 2): [dict(pa, pa_index=0)]})
    aggs = ss.aggregate_all(ctx, rows, scorer_for=fake_scorer_for)
    e, c = aggs["E"], aggs["C"]
    assert asked == [("E", 2026)]                                   # C 沒有完賽場 ⇒ 不取 scorer
    assert c.turning is None
    assert e.turning["scope"] == "covered_only"                    # E3、E4 未送達
    assert {t["series_game_no"] for t in e.turning["items"]} == {1, 2}
    out = ss.summary_json(aggs, {"HX": "打者X"}, current="C", previous="E")
    assert out["current"]["turning_points"] is None
    item = out["previous"]["turning_points"]["items"][0]
    assert item["hitter"] == {"player_id": "H0", "name": None}      # 事實流的 hitter 欄（替身沒有姓名）
    assert "H0" in ss.player_ids(aggs) and "P0" in ss.player_ids(aggs)


def test_aggregate_without_scorer_for_is_explicitly_degraded(ctx, monkeypatch):
    monkeypatch.setattr(pa_facts, "delta_re24", lambda pas, events, re_map, *, game_completed=True: [dict(p) for p in pas])
    pa = {**f(0, 1, d_re=0.9), "hitter_acnt": "HX", "end_pitcher_acnt": "PX", "start_pitcher_acnt": "PX",
          "outcome_family": "single", "pre_state": {"half": "1"}}
    e = ss.aggregate(ctx, "E", _rows_from({("E", 1): [pa]}))
    assert e.turning["degraded"] is True and e.turning["reason"] == "winprob_not_requested"


def test_no_covered_games_means_no_turning(ctx):
    e = ss.aggregate(ctx, "E", _rows_from({}), scorer_for=lambda k, s: (None, "x"))
    assert e.status == "pending_pa" and e.turning is None
