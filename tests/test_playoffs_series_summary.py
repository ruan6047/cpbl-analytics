"""#288 S07 WP-G2 系列累計榜（``cpbl.playoffs.series_summary``）純函式。

場次取 2026 真實 E1–E4、C1–C7（``tests/fixtures/postseason_real_years.json``，同 overview 測試）；C1 完賽列與
所有打席都是合成事件，只驗歸屬／排序／涵蓋規則。ΔRE24 本身以替身代入（各打席 ``_d``／``_r``），因為
``pa_facts.delta_re24`` 已由 ``tests/test_pa_facts*.py`` 釘住；真實 PA×livelog×RE 的整合在 isolated 測試與
執行階段對帳 artifact。
"""

from __future__ import annotations

from dataclasses import replace

import pytest
from postseason_context_inputs import BRO, DRAGON, LION, NOW_2026, games, inputs, with_result

from cpbl import postseason_contract as pc
from cpbl.models import pa_facts
from cpbl.playoffs import overview as ov
from cpbl.playoffs import series_summary as ss

MVP = {1: "0000005604", 2: "0000007778", 3: "0000007597", 4: "0000002345"}
RE = {(b1 + b2 + b3, o): 0.0 for b1 in "1_" for b2 in "2_" for b3 in "3_" for o in (0, 1, 2)}


@pytest.fixture(autouse=True)
def _fake_delta(monkeypatch):
    """ΔRE24 替身：各打席的 ``_d``（值）與 ``_r``（不可得原因）原樣交回。"""
    def fake(pas, events, re_map, *, game_completed=True):
        assert game_completed is True
        return [{"pa_index": p["pa_index"], "delta_re24": p.get("_d"), "unavailable_reason": p.get("_r")}
                for p in sorted(pas, key=lambda p: p["pa_index"])]
    monkeypatch.setattr(pa_facts, "delta_re24", fake)


def _context(*, c1=None, mvp=MVP):
    out = []
    for g in games(2026):
        if g.kind_code == "E":
            g = replace(g, mvp_id=mvp.get(g.game_sno))
        if g.kind_code == "C" and g.game_sno == 1 and c1:
            g = replace(with_result(g, *c1[:2]), mvp_id=c1[2])
        out.append(g)
    return pc.compute_series_context(inputs(2026, games_override=out), now=NOW_2026)


def pa(i, hitter, pitcher, d, *, half="1", start_pitcher=None, family="out", reason=None, end_hitter=None):
    return {"pa_index": i, "hitter_acnt": hitter, "end_hitter_acnt": end_hitter or hitter,
            "start_pitcher_acnt": start_pitcher or pitcher, "end_pitcher_acnt": pitcher,
            "outcome_family": family, "pre_state": {"half": half}, "state": "ready", "_d": d, "_r": reason}


def ev(no, pitcher, balls, strikes, change=False):
    return {"main_event_no": no, "pitcher_acnt": pitcher, "ball_cnt": balls, "strike_cnt": strikes,
            "is_change_player": change, "hitter_acnt": None, "hitter_name": None, "pitcher_name": None}


def _rows(pas: dict, *, livelog=None, members=None, re_map=RE) -> ss.SeriesRows:
    return ss.SeriesRows(pas=pas, livelog=livelog or {}, members=members or {}, re_map=re_map,
                         build_ids={k: f"b-{k[0]}{k[1]}" for k in pas})


def _all_e(**per_game):
    """E1–E4 各一打席（預設）；per_game 以 e1=[...] 覆寫。"""
    return {("E", n): per_game.get(f"e{n}", [pa(0, "H0", "P0", 0.0)]) for n in (1, 2, 3, 4)}


# --- 母體：E/C 隔離、續賽同 key 只算一場 ---------------------------------------------------------

def test_e_and_c_are_aggregated_separately():
    ctx = _context(c1=(3, 1, "0000009999"))
    rows = _rows({**_all_e(e1=[pa(0, "HE", "PE", 1.0)]), ("C", 1): [pa(0, "HC", "PC", 2.0)]})
    e, c = ss.aggregate(ctx, "E", rows), ss.aggregate(ctx, "C", rows)
    assert {b.player_id for b in e.batters} == {"HE", "H0"} and [b.player_id for b in c.batters] == ["HC"]
    assert (e.games_total, c.games_total) == (4, 1)
    assert [m["player_id"] for m in c.mvp_counts] == ["0000009999"]
    assert "0000009999" not in {m["player_id"] for m in e.mvp_counts}


def test_same_game_key_counted_once():
    ctx = _context()
    ctx = {**ctx, "games": [*ctx["games"], dict(next(g for g in ctx["games"] if g["game_key"]["kind_code"] == "E"))]}
    agg = ss.aggregate(ctx, "E", _rows(_all_e()))
    assert agg.games_total == 4
    assert sum(m["count"] for m in agg.mvp_counts) == 4


def test_unfinished_games_are_not_in_population():
    agg = ss.aggregate(_context(), "C", _rows({("C", 1): [pa(0, "HC", "PC", 2.0)]}))
    assert agg.status == "no_completed_games" and agg.games_total == 0 and agg.batters == []


# --- 歸屬：9.15(b)、9.16(h)(1)、投手轉號、純代跑 -------------------------------------------------

def test_batter_credit_goes_to_hitter_acnt_not_end_hitter():
    # 代打兩好球後接手被三振：記錄歸原打者（9.15(b)）
    rows = _rows(_all_e(e1=[pa(0, "ORIG", "P1", -0.3, end_hitter="PH")]))
    agg = ss.aggregate(_context(), "E", rows)
    ids = {b.player_id for b in agg.batters}
    assert "ORIG" in ids and "PH" not in ids


def test_pitcher_value_is_sign_flipped_batter_view():
    rows = _rows(_all_e(e1=[pa(0, "H1", "P1", 0.8), pa(1, "H2", "P1", -0.3)]))
    agg = ss.aggregate(_context(), "E", rows)
    p1 = next(p for p in agg.pitchers if p.player_id == "P1")
    assert p1.value == pytest.approx(-0.5) and p1.count == 2


@pytest.mark.parametrize(("count", "expected"), [
    ((2, 0), "PRIOR"),      # 換投時 2-0 ⇒ 歸前任
    ((3, 2), "PRIOR"),
    ((1, 0), "RELIEF"),     # 換投時 1-0 ⇒ 歸接手
    ((2, 2), "RELIEF"),
])
def test_mid_pa_pitching_change_walk_rule(count, expected):
    b, s = count
    events = [ev("1", "PRIOR", b, s), ev("2", "RELIEF", b, s, change=True), ev("3", "RELIEF", 4, s)]
    rows = _rows(_all_e(e1=[pa(0, "H1", "RELIEF", 1.0, start_pitcher="PRIOR", family="walk")]),
                 livelog={("E", 1): events}, members={("E", 1, 0): ["1", "2", "3"]})
    agg = ss.aggregate(_context(), "E", rows)
    charged = {p.player_id: p.value for p in agg.pitchers}
    assert charged.get(expected) == pytest.approx(-1.0)
    assert ({"PRIOR", "RELIEF"} - {expected}).isdisjoint(charged)
    assert agg.pitcher_unattributed == 0


def test_mid_pa_walk_unresolvable_is_not_charged_to_anyone():
    # 接手第一筆不是換人事件 ⇒ 判不出 ⇒ 不歸任何投手（⛔ 退回末投手）
    events = [ev("1", "PRIOR", 2, 0), ev("2", "RELIEF", 2, 0, change=False), ev("3", "RELIEF", 4, 0)]
    rows = _rows(_all_e(e1=[pa(0, "H1", "RELIEF", 1.0, start_pitcher="PRIOR", family="walk")]),
                 livelog={("E", 1): events}, members={("E", 1, 0): ["1", "2", "3"]})
    agg = ss.aggregate(_context(), "E", rows)
    assert agg.pitcher_unattributed == 1
    assert {"PRIOR", "RELIEF"}.isdisjoint({p.player_id for p in agg.pitchers})
    assert "H1" in {b.player_id for b in agg.batters}        # 打者照記


def test_mid_pa_change_non_walk_goes_to_end_pitcher():
    rows = _rows(_all_e(e1=[pa(0, "H1", "RELIEF", -0.4, start_pitcher="PRIOR", family="strikeout")]))
    agg = ss.aggregate(_context(), "E", rows)
    assert {p.player_id for p in agg.pitchers} >= {"RELIEF"} and "PRIOR" not in {p.player_id for p in agg.pitchers}


def test_pure_pinch_runner_never_enters_board():
    # 純代跑者不會是任何打席的 hitter_acnt ⇒ 無 PA、不入榜
    agg = ss.aggregate(_context(), "E", _rows(_all_e()))
    assert all(b.count >= 1 for b in agg.batters) and "RUNNER" not in {b.player_id for b in agg.batters}


def test_team_from_half_inning():
    # 2026 E1：ADD011（客）@ ACN011（主）。上半局客隊進攻。
    rows = _rows(_all_e(e1=[pa(0, "TOP", "HOMEP", 1.0, half="1"), pa(1, "BOT", "AWAYP", 1.0, half="2")]))
    agg = ss.aggregate(_context(), "E", rows)
    teams = agg.teams                     # 全員（不截前 N）
    g1 = next(g for g in _context()["games"] if g["game_key"]["kind_code"] == "E" and g["game_key"]["game_sno"] == 1)
    assert teams["TOP"] == g1["away_team_code"] and teams["HOMEP"] == g1["home_team_code"]
    assert teams["BOT"] == g1["home_team_code"] and teams["AWAYP"] == g1["away_team_code"]


# --- 涵蓋：正常歸桶 vs 資料缺口 ---------------------------------------------------------------------

@pytest.mark.parametrize("reason", ["pa_state_truncated", "pa_state_non_pa", "negative_runs_on_play"])
def test_runner_bucket_reasons_are_not_gaps(reason):
    rows = _rows(_all_e(e1=[pa(0, "H1", "P1", 0.5), pa(1, None, "P1", None, reason=reason)]))
    agg = ss.aggregate(_context(), "E", rows)
    assert agg.status == "ok" and agg.games_covered == 4 and agg.missing_games == []
    assert next(p for p in agg.pitchers if p.player_id == "P1").count == 1   # 不可得的打席不計 BF


@pytest.mark.parametrize("reason", sorted(ss.GAP_REASONS))
def test_gap_game_is_excluded_whole(reason):
    rows = _rows(_all_e(e2=[pa(0, "GAPPY", "P9", 9.0), pa(1, "H1", "P9", None, reason=reason)]))
    agg = ss.aggregate(_context(), "E", rows)
    assert agg.status == "partial" and (agg.games_covered, agg.games_total) == (3, 4)
    assert agg.missing_games == [2] and agg.excluded_games == [{"series_game_no": 2, "reason": reason}]
    assert "GAPPY" not in {b.player_id for b in agg.batters}   # 整場排除，不部分採計


def test_status_by_coverage():
    ctx = _context()
    assert ss.aggregate(ctx, "E", _rows(_all_e())).status == "ok"
    part = ss.aggregate(ctx, "E", _rows({("E", 1): [pa(0, "H1", "P1", 1.0)]}))
    assert (part.status, part.games_covered, part.missing_games) == ("partial", 1, [2, 3, 4])
    none = ss.aggregate(ctx, "E", _rows({}))
    assert (none.status, none.games_covered, none.batters) == ("pending_pa", 0, [])
    assert [m["count"] for m in none.mvp_counts] == [1, 1, 1, 1]          # MVP 次數不等 PA


def test_read_failure_or_incomplete_re_is_unavailable():
    ctx = _context()
    down = ss.aggregate(ctx, "E", None)
    assert down.status == "unavailable" and down.batters == [] and len(down.mvp_counts) == 4
    short = ss.aggregate(ctx, "E", _rows(_all_e(), re_map=dict(list(RE.items())[:23])))
    assert short.status == "unavailable"


# --- 排序與上限 ------------------------------------------------------------------------------------

def test_sorts_by_unrounded_value_then_player_id():
    # 1.04 與 1.0449 展示都是 +1.0：以原值排；同原值以 ID 升冪
    rows = _rows(_all_e(e1=[pa(0, "B", "P", 1.04), pa(1, "A", "P", 1.0449), pa(2, "D", "P", 1.04),
                            pa(3, "C", "P", 2.0)]))
    agg = ss.aggregate(_context(), "E", rows)
    assert [b.player_id for b in agg.batters] == ["C", "A", "B"]


def test_fewer_candidates_means_fewer_rows():
    rows = _rows({("E", n): [pa(0, "ONLY", "SOLO", 0.1)] for n in (1, 2, 3, 4)})
    agg = ss.aggregate(_context(), "E", rows)
    assert [b.player_id for b in agg.batters] == ["ONLY"] and [p.player_id for p in agg.pitchers] == ["SOLO"]
    assert agg.batters[0].count == 4


def test_limits_are_three_and_two():
    rows = _rows(_all_e(e1=[pa(i, f"H{i}", f"P{i}", i * 0.1) for i in range(6)]))
    agg = ss.aggregate(_context(), "E", rows)
    assert len(agg.batters) == 3 and len(agg.pitchers) == 2


# --- MVP 次數、獎項、輸出形狀 ------------------------------------------------------------------------

def test_mvp_counts_only_official_and_missing_listed():
    agg = ss.aggregate(_context(mvp={1: "X", 2: "X", 4: "Y"}), "E", _rows(_all_e()))
    assert [(m["player_id"], m["count"]) for m in agg.mvp_counts] == [("X", 2), ("Y", 1)]
    assert agg.mvp_missing_games == [3]


def _all_strings(node):
    if isinstance(node, dict):
        for k, v in node.items():
            yield k
            yield from _all_strings(v)
    elif isinstance(node, list):
        for v in node:
            yield from _all_strings(v)
    elif isinstance(node, str):
        yield node


def test_json_shape_awards_pending_and_no_title_for_re24_leader():
    rows = _rows(_all_e(e1=[pa(0, "0000007778", "P1", 5.0)]))
    aggs = ss.aggregate_all(_context(), rows)
    out = ss.summary_json(aggs, {"0000007778": "喬登"}, current="C", previous="E")
    assert out["contract"] == "playoffs-series-summary/v1" and out["current"]["status"] == "no_completed_games"
    e = out["previous"]
    assert e["awards"] == {"status": "pending_source"}
    top = e["batters"][0]
    assert (top["player_id"], top["name"], top["pa"], top["re24_raw"], top["mvp_count"]) == (
        "0000007778", "喬登", 1, 5.0, 1)
    strings = list(_all_strings(out))
    assert not any(s in {"is_mvp", "mvp", "leader", "rank", "series_mvp"} for s in strings)
    assert not any("MVP" in s for s in strings)


def test_manifest_entry_scope_and_status():
    ctx = _context()
    m = ss.manifest_entry(ss.aggregate_all(ctx, _rows({("E", 1): [pa(0, "H", "P", 0.1)]})), observed_at="t")
    assert (m["source"], m["scope"], m["status"]) == ("pa_published", "series:E:1/4", "ok")
    assert ss.manifest_entry(ss.aggregate_all(ctx, None), observed_at="t")["status"] == "unavailable"


# --- 掛進 overview：既有欄位與 context_version 不變 ------------------------------------------------

def test_overview_attaches_summary_without_touching_context_version():
    ctx = _context()
    names = {v: v for v in MVP.values()}
    plain = ov.compute_overview(ov.OverviewInputs(context=ctx, names=names))
    aggs = ss.aggregate_all(ctx, _rows(_all_e()))
    full = ov.compute_overview(ov.OverviewInputs(context=ctx, names=names, series_summary=aggs, summary_names=names))
    assert full["context_version"] == plain["context_version"]
    assert full["series_section"] == plain["series_section"]
    assert full["source_manifest"][-1]["source"] == "players"              # players 仍是最後一筆
    assert full["source_manifest"][-2]["source"] == "pa_published"
    assert full["source_manifest"][-1] == plain["source_manifest"][-1]
    assert full["series_summary"]["current"]["kind_code"] == "C"
    assert full["series_summary"]["previous"]["kind_code"] == "E"
    assert plain["series_summary"] is None


def test_current_e_has_no_previous():
    # 挑戰賽進行中（當前系列＝E）：沒有前一系列
    ctx = _context()
    ctx = {**ctx, "state": {**ctx["state"], "default_series": "E"}}
    aggs = ss.aggregate_all(ctx, _rows(_all_e()))
    out = ss.summary_json(aggs, {}, current="E", previous=None)
    assert out["current"]["kind_code"] == "E" and out["previous"] is None


def test_teams_constants_are_real():
    assert {BRO, DRAGON, LION} >= {g["away_team_code"] for g in _context()["games"]
                                    if g["game_key"]["kind_code"] == "E"}
