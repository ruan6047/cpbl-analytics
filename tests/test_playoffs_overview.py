"""#285 S04 overview 純組裝（``cpbl.playoffs.overview.compute_overview``）。

場次取 2026 真實 E1–E4、C1–C7（``tests/fixtures/postseason_real_years.json``）；MVP id／姓名取本機 DB
唯讀查得的真實值（E1 勝騎士 0000005604、E2 喬登 0000007778、E3 獅帝芬 0000007597、E4 鄭浩均 0000002345）。
C1 完賽列是注入事件（比分、MVP 皆為測試用），只驗組裝，不作賽果實證。
"""

from __future__ import annotations

import ast
from dataclasses import replace
from pathlib import Path

from postseason_context_inputs import BRO, DRAGON, LION, NOW_2026, games, inputs, with_result

from cpbl import postseason_contract as pc
from cpbl.playoffs import overview as ov

MVP = {1: "0000005604", 2: "0000007778", 3: "0000007597", 4: "0000002345"}
NAMES = {"0000005604": "勝騎士", "0000007778": "喬登", "0000007597": "獅帝芬", "0000002345": "鄭浩均"}


def _games(*, c1=None, mvp=MVP):
    out = []
    for g in games(2026):
        if g.kind_code == "E":
            g = replace(g, mvp_id=mvp.get(g.game_sno))
        if g.kind_code == "C" and g.game_sno == 1 and c1:
            g = replace(with_result(g, *c1[:2]), mvp_id=c1[2])
        out.append(g)
    return out


def _context(**kw):
    return pc.compute_series_context(inputs(2026, games_override=_games(**kw)), now=NOW_2026)


def _overview(names=NAMES, **kw):
    return ov.compute_overview(ov.OverviewInputs(context=_context(**kw), names=names))


def _keys(node):
    if isinstance(node, dict):
        for k, v in node.items():
            yield k
            yield from _keys(v)
    elif isinstance(node, list):
        for v in node:
            yield from _keys(v)


def test_before_c1_gives_challenge_summary_and_g1_preview():
    o = _overview()
    ss = o["series_section"]
    assert o["contract"] == "playoffs-overview/v1" and o["default_series"] == "C"
    prev, cur = ss["previous"], ss["current"]
    assert prev["kind_code"] == "E" and prev["series_status"] == "decided" and prev["winner"] == BRO
    sides = {s["team_code"]: s for s in prev["sides"]}
    assert (sides[BRO]["initial_wins"], sides[BRO]["game_wins"], sides[BRO]["total_wins"]) == (1, 2, 3)
    assert (sides[LION]["game_wins"], sides[LION]["total_wins"]) == (2, 2)
    assert [(c["official_game_sno"], c["away_score"], c["home_score"]) for c in prev["games"]] == [
        (1, 1, 4), (2, 0, 1), (3, 4, 2), (4, 2, 8)]
    assert [c["mvp"]["name"] for c in prev["games"]] == ["勝騎士", "喬登", "獅帝芬", "鄭浩均"]
    assert all(c["mvp_missing_reason"] is None for c in prev["games"])
    assert cur["kind_code"] == "C" and cur["series_status"] == "pending" and len(cur["games"]) == 7
    nxt = ss["next_game"]
    assert nxt["game_key"] == {"year": 2026, "kind_code": "C", "game_sno": 1}
    assert (nxt["game_date"], nxt["start"], nxt["away_team_code"], nxt["home_team_code"]) == (
        "2026-10-17", "17:05", BRO, DRAGON)
    assert o["schedule_source"]["kind"] == "official_announcement"
    assert o["sections"]["watch"] == {"status": "ok", "series": "C", "game": 1}


def test_after_c1_final_shows_c1_score_and_c2_preview():
    o = _overview(c1=(3, 5, "0000002345"), names={**NAMES})
    cur = o["series_section"]["current"]
    c1 = cur["games"][0]
    assert (c1["completed"], c1["away_score"], c1["home_score"], c1["mvp"]["name"]) == (True, 3, 5, "鄭浩均")
    assert cur["series_status"] == "active"
    assert o["series_section"]["next_game"]["official_game_sno"] == 2
    assert o["sections"]["watch"]["game"] == 2


def test_completed_without_mvp_is_not_ingested_not_unpublished():
    o = _overview(mvp={1: "0000005604"}, names={"0000005604": "勝騎士"})
    prev = o["series_section"]["previous"]["games"]
    assert prev[0]["mvp"] == {"id": "0000005604", "name": "勝騎士"}
    assert all(c["mvp"] is None and c["mvp_missing_reason"] == "official_mvp_not_ingested" for c in prev[1:])


def test_mvp_name_missing_or_players_unavailable_degrades_per_card():
    o = _overview(names={k: v for k, v in NAMES.items() if k != "0000007778"})
    e2 = o["series_section"]["previous"]["games"][1]
    assert e2["mvp"] == {"id": "0000007778", "name": None}
    assert e2["mvp_missing_reason"] == "player_name_unavailable"
    down = _overview(names=None)
    assert "player_names_unavailable" in down["series_section"]["missing_reason"]
    assert down["source_manifest"][-1]["source"] == "players"
    assert down["source_manifest"][-1]["status"] == "unavailable"
    assert all(c["mvp_missing_reason"] == "player_name_unavailable" for c in down["series_section"]["previous"]["games"])


def test_unfinished_scores_are_null_and_no_starter_fields_anywhere():
    o = _overview()
    assert all(c["away_score"] is None and c["home_score"] is None and c["mvp"] is None
               for c in o["series_section"]["current"]["games"])
    # D7：第 1 區不顯示先發投手 ⇒ overview 任何層都沒有 starter 欄位（S02 teams[].starter_status 也不轉出）
    assert not [k for k in _keys(o) if "starter" in k]


def test_context_version_is_s02_original_and_output_is_deterministic():
    ctx = _context()
    a = ov.compute_overview(ov.OverviewInputs(context=ctx, names=NAMES))
    b = ov.compute_overview(ov.OverviewInputs(context=ctx, names=dict(NAMES)))
    assert a["context_version"] == ctx["context_version"]
    assert a["series_id"] == ctx["series"]["C"]["series_id"]
    assert a == b


def test_series_decided_has_no_preview():
    results = [(1, 3), (2, 4), (0, 5), (1, 2)]   # 注入：味全主場連勝四場
    gs = []
    for g in _games():
        if g.kind_code == "C" and g.game_sno <= 4:
            a, h = results[g.game_sno - 1] if g.home_team_code == DRAGON else results[g.game_sno - 1][::-1]
            g = with_result(g, a, h)
        gs.append(g)
    ctx = pc.compute_series_context(inputs(2026, games_override=gs), now=NOW_2026)
    o = ov.compute_overview(ov.OverviewInputs(context=ctx, names=NAMES))
    assert o["series_section"]["current"]["series_status"] == "decided"
    assert o["series_section"]["next_game"] is None
    assert o["series_section"]["next_game_missing_reason"] == "series_decided"


def test_current_series_rows_missing_keeps_previous_summary():
    """審核 F1：C 列尚未入庫時，E 總結照常給；區塊不是空態，缺列記在 missing_reason。"""
    only_e = [g for g in _games() if g.kind_code == "E"]
    ctx = pc.compute_series_context(inputs(2026, games_override=only_e), now=NOW_2026)
    o = ov.compute_overview(ov.OverviewInputs(context=ctx, names=NAMES))
    ss = o["series_section"]
    assert o["default_series"] == "C"
    assert ss["status"] == "ok" and o["sections"]["series"]["status"] == "ok"
    assert "series_games_missing" in ss["missing_reason"]
    assert [c["mvp"]["name"] for c in ss["previous"]["games"]] == ["勝騎士", "喬登", "獅帝芬", "鄭浩均"]
    assert ss["previous"]["winner"] == BRO
    assert ss["current"]["games"] == [] and ss["next_game"] is None
    assert ss["next_game_missing_reason"] == "no_target"


def test_no_postseason_rows_at_all_is_empty():
    ctx = pc.compute_series_context(inputs(2026, games_override=[]), now=NOW_2026)
    o = ov.compute_overview(ov.OverviewInputs(context=ctx, names={}))
    assert o["series_section"]["status"] == "empty"
    assert o["series_section"]["previous"] is None


def test_mvp_ids_only_from_completed_games_deduplicated():
    ctx = _context(mvp={1: "0000005604", 2: "0000005604", 3: "0000007597"})
    assert ov.mvp_ids(ctx) == ["0000005604", "0000007597"]


def test_overview_module_does_not_import_shared_report_background():
    """A15「GET 不重建全季背景」：overview 模組不 import ``reports.background``／``assembler``（#272）。"""
    tree = ast.parse(Path(ov.__file__).read_text(encoding="utf-8"))
    mods = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)} | {
        a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    assert not [m for m in mods if m and ("background" in m or "assembler" in m)]
