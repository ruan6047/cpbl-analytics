"""#283 S02 WP1／WP3：年度規則推導、系列計數與 ``postseason-series-context/v2`` 組裝（不連 DB）。

年度規則實證用 ``tests/fixtures/postseason_real_years.json``（本機 DB 唯讀抽取，見其 ``_provenance``）。
注入案例只改事件，隊碼一律真實；標「真實事件未發生、未驗證」者不算年度規則實證。
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime

import pytest
from postseason_context_inputs import (
    BRO,
    DRAGON,
    GUARDIAN,
    HAWK,
    LAMIGO,
    LION,
    NOW_2026,
    RAKUTEN,
    case_b_rule,
    games,
    inputs,
    standings,
    with_result,
)

from cpbl import postseason_contract as pc


def _ctx(year, now=NOW_2026, **kw):
    return pc.compute_series_context(inputs(year, **kw), now=now)


def _side(series, code):
    return next(s for s in series["sides"] if s["team_code"] == code)


def _key(year, kind, sno):
    return {"year": year, "kind_code": kind, "game_sno": sno}


# —— A01 年度規則實證（真實年份） ————————————————————————————————————————————

def test_2026_rule_instance_matches_regs_standings_and_announcement():
    """§60-1：H1 味全、H2 兄弟；全年味全 67-53 > 兄弟 56-62 ⇒ E 兄弟 +1 對獅（半季冠軍以外全年最高）。"""
    plan = pc.derive_series_plan(pc.SEASON_RULES[2026], standings(2026))
    assert plan["case"] == "A"
    assert plan["E"] == {"teams": [BRO, LION], "initial_wins": {BRO: 1, LION: 0}}
    assert plan["C"] == {"seed": DRAGON, "seed_initial_wins": 0}
    assert not pc._announcement_mismatch(plan, pc.ANNOUNCEMENT_2026)


def test_2026_e_handicap_is_decisive_at_e4_and_c_is_pending_with_known_opponent():
    ctx = _ctx(2026)
    e, c = ctx["series"]["E"], ctx["series"]["C"]
    assert (e["series_status"], e["winner"], e["decided_by_game_key"]) == ("decided", BRO, _key(2026, "E", 4))
    assert (_side(e, BRO)["initial_wins"], _side(e, BRO)["game_wins"], _side(e, BRO)["total_wins"]) == (1, 2, 3)
    assert (_side(e, LION)["game_wins"], _side(e, LION)["total_wins"]) == (2, 2)
    assert _side(e, BRO)["initial_wins_basis"] == "announcement_confirmed"
    assert e["summary_kind"] == "advance_summary"
    assert c["series_status"] == "pending" and c["participants_status"] == "known"
    assert [(s["team_code"], s["initial_wins"]) for s in c["sides"]] == [(DRAGON, 0), (BRO, 0)]
    assert c["summary_kind"] == "championship_summary"


@pytest.mark.parametrize(("year", "e_winner", "e_by", "handicap", "c_winner", "c_by"), [
    (2022, BRO, 3, BRO, BRO, 4),          # E3 結束（兄弟 2＋1）決定性；C 無讓勝於 C4
    (2023, RAKUTEN, 3, LION, DRAGON, 7),  # C 7 戰：有讓勝會在 C6 結束 ⇒ 無讓勝決定性
    (2024, LION, 3, LION, BRO, 5),        # E3（獅 2＋1）決定性；C5 結束 ⇒ 無讓勝
    (2025, RAKUTEN, 4, LION, RAKUTEN, 5),  # 已完成 E→C 回歸樣本年
])
def test_real_years_2022_2025_e_handicap_and_c_without_handicap(year, e_winner, e_by, handicap, c_winner, c_by):
    ctx = _ctx(year)
    e, c = ctx["series"]["E"], ctx["series"]["C"]
    assert (e["winner"], e["decided_by_game_key"]) == (e_winner, _key(year, "E", e_by))
    assert [s["team_code"] for s in e["sides"] if s["initial_wins"]] == [handicap]
    assert all(s["initial_wins"] == 0 for s in c["sides"])
    assert (c["series_status"], c["winner"], c["decided_by_game_key"]) == ("decided", c_winner, _key(year, "C", c_by))
    assert c["conflict_reason"] is None and e["conflict_reason"] is None


@pytest.mark.parametrize(("year", "e_teams", "c_by"), [
    (2017, {LION, BRO}, 4),     # C4 結束：Lamigo 實勝 3＋規則勝 1（無讓勝不會在 C4 結束）
    (2018, {LION, HAWK}, 5),    # C5 結束：Lamigo 實勝 3＋規則勝 1；E 獅 E4 才 3 勝 ⇒ E 無讓勝
])
def test_case_b_c_handicap_real_years_2017_2018(year, e_teams, c_by):
    """T3：§60-2（同隊雙半季第 1）C 讓勝只以 2017／2018 實證；規則為測試內注入，不進 API 常數。"""
    assert year not in pc.SEASON_RULES
    ctx = _ctx(year, rule=case_b_rule(year), rule_given=True)
    e, c = ctx["series"]["E"], ctx["series"]["C"]
    assert {s["team_code"] for s in e["sides"]} == e_teams and all(s["initial_wins"] == 0 for s in e["sides"])
    assert e["series_status"] == "decided"
    assert _side(c, LAMIGO)["initial_wins"] == 1
    assert (c["winner"], c["decided_by_game_key"]) == (LAMIGO, _key(year, "C", c_by))
    assert _side(c, LAMIGO)["game_wins"] == 3 and c["conflict_reason"] is None


def test_2006_counterexample_proves_rule_changes_by_year():
    """2006 La New 雙半季第 1，但 C 打到 C4 且 4 場實勝：套現行 §60-2 會在 C3 決勝 ⇒ C4 成為決勝後完賽列。"""
    ctx = _ctx(2006, rule=case_b_rule(2006), rule_given=True)
    c = ctx["series"]["C"]
    assert c["series_status"] == "unknown" and c["conflict_reason"] == "game_after_decided"


def test_years_without_rule_constant_are_unsourced_not_guessed():
    ctx = _ctx(2017)
    assert ctx["rule_status"] == "unsourced" and "rule_unsourced" in ctx["missing_reason"]
    for s in ctx["series"].values():
        assert s["series_status"] == "unknown"
        assert all(x["initial_wins"] is None and x["initial_wins_basis"] == "unsourced" for x in s["sides"])


def test_api_rule_constants_serve_2022_to_2026_only():
    assert sorted(pc.SEASON_RULES) == [2022, 2023, 2024, 2025, 2026]
    assert all(r.announcement is None for y, r in pc.SEASON_RULES.items() if y != 2026)


def test_seed_tie_is_unknown_not_guessed():
    st = standings(2026)
    tied = replace(st, first=(pc.TeamRecord(DRAGON, 30, 20), pc.TeamRecord(HAWK, 30, 20), *st.first[2:]))
    plan = pc.derive_series_plan(pc.SEASON_RULES[2026], tied)
    assert plan["status"] == "unknown" and plan["missing_reason"] == ["seed_tiebreak_pending"]


def test_win_pct_uses_exact_fraction_not_rounded_column():
    """53-46（.5354）與 61-53（.5351）四捨五入同為 .535，精確分數仍分得出高低。"""
    a, b = pc.TeamRecord("X", 53, 46), pc.TeamRecord("Y", 61, 53)
    assert a.pct is not None and b.pct is not None
    assert round(float(a.pct), 3) == round(float(b.pct), 3) and a.pct > b.pct
    assert pc._unique_top([a, b]) == ("X", False)


def test_announcement_mismatch_is_conflict_not_rewritten():
    ann = replace(pc.ANNOUNCEMENT_2026, e_handicap_team=LION)
    rule = replace(pc.SEASON_RULES[2026], announcement=ann)
    ctx = _ctx(2026, rule=rule, rule_given=True)
    assert ctx["series"]["E"]["conflict_reason"] == "announcement_mismatch"
    assert ctx["series"]["E"]["series_status"] == "unknown"
    assert "announcement_mismatch" in ctx["missing_reason"]


# —— A01 注入案例（真實事件未發生、未驗證；隊碼真實） ————————————————————————————

def _c_games(results):
    """2026 C 真實列，依序灌入 (away, home) 比分。"""
    cs = [g for g in games(2026) if g.kind_code == "C"]
    out = [g for g in games(2026) if g.kind_code == "E"]
    for g, r in zip(cs, results + [None] * (len(cs) - len(results)), strict=True):
        out.append(with_result(g, *r) if r else g)
    return out


def test_tie_is_not_a_win_and_does_not_end_series():
    # C1 兄弟@味全 3:3 和局；C2 味全勝。
    ctx = _ctx(2026, games_override=_c_games([(3, 3), (1, 2)]))
    c = ctx["series"]["C"]
    assert c["ties"] == 1 and _side(c, DRAGON)["game_wins"] == 1 and _side(c, BRO)["game_wins"] == 0
    assert c["series_status"] == "active"
    g1 = next(g for g in ctx["games"] if g["game_key"] == _key(2026, "C", 1))
    assert g1["result"] == "tie" and g1["counted_for_wins"] is False


def test_official_g8_beyond_best_of_counts_only_as_real_row():
    """§67 平手再賽：只認 DB 真實列；series_game_no 可超過 best_of。"""
    gs = _c_games([(3, 3), (1, 2), (2, 1), (1, 2), (2, 1), (1, 2), (2, 1)])   # 和 1、味全 3、兄弟 3
    g8 = replace(gs[-1], game_sno=8, game_date=date(2026, 10, 26), away_score=0, home_score=4)
    ctx = _ctx(2026, games_override=[*gs, g8])
    c = ctx["series"]["C"]
    row8 = next(g for g in ctx["games"] if g["game_key"] == _key(2026, "C", 8))
    assert row8["series_game_no"] == 8 and c["best_of"] == 7
    assert (c["winner"], c["decided_by_game_key"]) == (DRAGON, _key(2026, "C", 8))
    # 公告沒有 G8：不綁公告格，另成一格「公告外真實列」（slot_id 不冒充公告場序）
    assert row8["announced_slot_id"] == "C-sno8"
    s8 = next(s for s in ctx["arrangement"]["slots"] if s["slot_id"] == "C-sno8")
    assert (s8["announced"], s8["seq"], s8["display_status"]) == (False, 8, "final")


def _g8_pending():
    """F1（再審）：C1–C7 一和、雙方各三勝，官方新增 C8（真實 key、未完賽）。注入事件，隊碼真實。"""
    gs = _c_games([(3, 3), (1, 2), (2, 1), (1, 2), (2, 1), (1, 2), (2, 1)])
    g8 = replace(gs[-1], game_sno=8, game_date=date(2026, 10, 26), away_score=0, home_score=0,
                 completed=False, official_status="scheduled")
    return [*gs, g8]


G8_NOW = datetime.fromisoformat("2026-10-26T12:00:00+08:00")


def test_pending_official_g8_is_next_and_keeps_series_remaining():
    """F1：公告外的真實 C8 進下一場與 remaining；系列 active、state 目標同一場。"""
    ctx = _ctx(2026, now=G8_NOW, games_override=_g8_pending())
    assert ctx["series"]["C"]["series_status"] == "active"
    assert ctx["state"]["target_game_key"] == _key(2026, "C", 8)
    arr = ctx["arrangement"]
    assert (arr["next_slot_id"], arr["remaining"]) == ("C-sno8", True)
    s8 = next(s for s in arr["slots"] if s["slot_id"] == "C-sno8")
    assert s8["game_key"] == _key(2026, "C", 8) and s8["display_status"] == "scheduled"
    assert s8["announced"] is False and s8["announced_date"] is None
    assert [s["slot_id"] for s in arr["slots"] if s["announced"]] == [
        "E1", "E2", "E3", "E4", "C1", "C2", "C3", "C4", "C5", "C6", "C7"]   # 公告格原樣保留


def test_decided_hides_unneeded_slots_but_keeps_original_arrangement():
    ctx = _ctx(2026, games_override=_c_games([(5, 1), (5, 1), (1, 5), (1, 5)]))   # 兄弟四連勝
    c = ctx["series"]["C"]
    assert (c["winner"], c["decided_by_game_key"]) == (BRO, _key(2026, "C", 4))
    slots = {s["slot_id"]: s for s in ctx["arrangement"]["slots"]}
    for k in ("C5", "C6", "C7"):
        assert slots[k]["hidden_not_needed"] and slots[k]["display_status"] == "not_needed"
        assert slots[k]["announced_date"] and slots[k]["venue"] and slots[k]["game_key"]   # 原安排保留
    assert ctx["arrangement"]["next_slot_id"] is None and ctx["arrangement"]["remaining"] is False
    # 真實 DB 列永遠輸出
    assert {g["game_key"]["game_sno"] for g in ctx["games"] if g["game_key"]["kind_code"] == "C"} == set(range(1, 8))


def test_both_teams_reaching_wins_needed_is_conflict_not_first_sorted():
    gs = _c_games([(5, 1), (5, 1), (1, 5), (1, 5), (1, 5), (1, 5), (1, 5)])   # 兄弟先 4 勝後，味全又 4 勝
    gs = [replace(g, game_sno=g.game_sno) for g in gs]
    gs.append(replace(gs[-1], game_sno=8, game_date=date(2026, 10, 26), away_score=1, home_score=5))
    ctx = _ctx(2026, games_override=gs)
    c = ctx["series"]["C"]
    assert c["series_status"] == "unknown" and c["conflict_reason"] == "both_reached" and c["winner"] is None


def test_game_after_decided_is_conflict():
    ctx = _ctx(2026, games_override=_c_games([(5, 1), (5, 1), (1, 5), (1, 5), (5, 1)]))
    assert ctx["series"]["C"]["conflict_reason"] == "game_after_decided"


def test_team_mismatch_is_conflict():
    gs = _c_games([])
    gs[4] = replace(gs[4], away_team_code=LION, away_score=1, home_score=2, completed=True)
    assert _ctx(2026, games_override=gs)["series"]["C"]["conflict_reason"] == "team_mismatch"


def test_official_retraction_recomputes_from_current_facts():
    """撤回：E4 官方不再 final ⇒ canonical completed=false ⇒ 系列依現況回到 active，留更正證據。"""
    gs = [replace(g, completed=False, official_status="final") if (g.kind_code, g.game_sno) == ("E", 4) else g
          for g in games(2026)]
    ctx = _ctx(2026, games_override=gs)
    e = ctx["series"]["E"]
    assert e["series_status"] == "active" and e["winner"] is None
    assert _side(e, BRO)["clinch"] and _side(e, LION)["clinch"]   # 2:2 雙方聽牌＝雙方面臨淘汰
    assert _side(e, BRO)["facing_elimination"] and _side(e, LION)["facing_elimination"]
    assert {"game_key": _key(2026, "E", 4), "reason": "official_final_not_completed"} in e["corrections"]
    assert ctx["series"]["C"]["participants_status"] == "pending_e_winner"


def test_unresolved_change_signal_records_correction_and_pending_overlay():
    sig = {"year": 2026, "kind_code": "C", "game_sno": 1, "game_date": "2026-10-18"}
    ctx = _ctx(2026, change_signals=[sig])
    assert {"game_key": _key(2026, "C", 1), "reason": "official_change_unresolved"} in ctx["series"]["C"]["corrections"]
    assert ctx["coverage"] == "pending_update"
    assert "pending_update" in ctx["state"]["by_series"]["C"]["overlays"]


# —— G01–G04 ——————————————————————————————————————————————————————————————

def test_g01_keys_are_year_kind_sno_only_even_with_blank_season_code():
    """2026 E 列 game_season_code=''（其他年 '0'）：契約 key 只有三欄，不帶 season code。"""
    ctx = _ctx(2026)
    assert all(set(g["game_key"]) == {"year", "kind_code", "game_sno"} for g in ctx["games"])
    assert ctx["series"]["E"]["decided_by_game_key"] == _key(2026, "E", 4)


def test_g02_c_slots_bind_only_to_real_rows_and_target_is_null_without_row():
    gs = [g for g in games(2026) if g.kind_code == "E"]   # C 尚未入庫
    ctx = _ctx(2026, games_override=gs)
    c_slots = [s for s in ctx["arrangement"]["slots"] if s["kind_code"] == "C"]
    assert all(s["game_key"] is None for s in c_slots)
    assert all(s["display_status"] == "announced" for s in c_slots)
    assert ctx["state"]["by_series"]["C"]["target_game_key"] is None


@pytest.mark.parametrize("variant", ["nonzero_score", "time_passed", "refresh_ok"])
def test_g03_final_only_from_canonical_completed(variant):
    c1 = next(g for g in games(2026) if (g.kind_code, g.game_sno) == ("C", 1))
    probe = {
        "nonzero_score": replace(c1, away_score=3, home_score=2, official_status="scheduled"),
        "time_passed": replace(c1, official_status="scheduled"),
        "refresh_ok": replace(c1, official_status="unknown"),
    }[variant]
    now = datetime.fromisoformat("2026-10-18T09:00:00+08:00")
    gs = [probe if g.key == c1.key else g for g in games(2026)]
    kw = {"last_refresh": {"at": now, "ok": True, "scope": "daily"}} if variant == "refresh_ok" else {}
    ctx = _ctx(2026, now=now, games_override=gs, **kw)
    row = next(g for g in ctx["games"] if g["game_key"] == _key(2026, "C", 1))
    assert row["target_status"] != "final" and row["completed"] is False and row["away_score"] is None


def test_g04_decided_mvp_and_analysis_are_independent():
    ctx = _ctx(2026, analysis={})   # PA 全未發布、MVP 欄全空
    e = ctx["series"]["E"]
    assert e["series_status"] == "decided" and e["analysis_status"] == "pending"
    assert all(g["official_mvp_id"] is None for g in ctx["games"])
    assert ctx["state"]["by_series"]["E"]["layout_state"] == "T5"


# —— 組裝：版本與時間線（A03 部分） ——————————————————————————————————————————————

def test_same_inputs_same_context_version_and_changes_with_sources():
    a, b = _ctx(2026), _ctx(2026, now=datetime.fromisoformat("2026-10-15T02:00:00+08:00"))
    assert a["context_version"] == b["context_version"]       # observed_at 不入版本
    changed = pc.compute_series_context(replace(inputs(2026), manifest=[
        {"source": "games", "scope": "2026/E,C", "version_or_hash": "other", "observed_at": None, "status": "ok"}]),
        now=NOW_2026)
    assert changed["context_version"] != a["context_version"]


def test_team_fields_keep_32_28_and_starter_separate():
    ctx = _ctx(2026)
    c_teams = [t for t in ctx["teams"] if t["series"] == "C"]
    assert {t["team_code"] for t in c_teams} == {DRAGON, BRO}
    assert all((t["roster_status"], t["registration_status"], t["starter_status"]) == ("missing", "unknown", "missing")
               for t in c_teams)
    assert {"roster_store_not_delivered", "registration_source_not_delivered",
            "ended_at_unavailable"} <= set(ctx["missing_reason"])


def test_registration_reader_returns_empty_until_s11():
    assert pc.registration_observations(None, (2026, "C", 1)) == []


def test_guardian_is_never_inferred_as_participant():
    """富邦全年 .483（第 4）——任何推導都不應出現。"""
    ctx = _ctx(2026)
    assert GUARDIAN not in {s["team_code"] for x in ctx["series"].values() for s in x["sides"]}
