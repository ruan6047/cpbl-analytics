"""#320 A2：官方先發分類（announced／changed／retracted／pending／unknown，整場 partial）。

基底列＝2026 台灣大賽 C3 本機真實 ``game_schedule_status_revisions`` 兩列（#320 Z4 唯讀快照
``~/.wf-evidence/cpbl-analytics/320/z4/c3-setup-1019/local-db.txt``，2026-10-19 11:39 台北）：
payload ``d07aa338``／``6a301274``，IsPlayBall=N、兩隊先發皆空、客 AAA011／主 ACN011、日期 2026-10-20。
其餘列是在此形狀上注入先發 acnt 的變體（本機 2026 季後 0 例更換／撤回，R2／R3）。
"""

from __future__ import annotations

from datetime import date, datetime

from cpbl.playoffs import starter_classification as sc
from cpbl.playoffs import watch_reader as wrd

DAY, VT, HT = date(2026, 10, 20), "AAA011", "ACN011"
TEAMS = [VT, HT]
A, B = "0000006848", "0000009999"
H_SIDE = "0000005151"
NAMES = {A: {"player_name": "林詔恩"}, B: {"player_name": "王某"}, H_SIDE: {"player_name": "羅戈"}}


def rev(vpa=None, hpa=None, *, h, fetched, seen=None, day="2026-10-20", ipb: str | None = "N", result=None, present=1,
        vt=VT, ht=HT):
    return {"raw_present_status": present, "raw_game_result": result, "raw_game_date": date.fromisoformat(day),
            "is_play_ball": ipb, "visiting_team_code": vt, "home_team_code": ht,
            "visiting_pitcher_acnt": vpa, "home_pitcher_acnt": hpa,
            "visiting_pitcher_name": None, "home_pitcher_name": None, "payload_hash": h,
            "fetched_at": datetime.fromisoformat(fetched), "last_seen_at": datetime.fromisoformat(seen or fetched)}


# 真實 C3 兩列（先發皆空）。
C3_FIRST = rev(h="d07aa338", fetched="2026-10-13T02:10:12.653764+00:00", seen="2026-10-17T08:39:08.807624+00:00")
C3_NOW = rev(h="6a301274", fetched="2026-10-17T11:29:48.704465+00:00", seen="2026-10-19T03:09:03.17818+00:00")


def starters(rows, names=NAMES, day=DAY):
    out, _ = wrd.official_starters(rows, target_date=day, teams=TEAMS, names=names)
    return out


def view(rows, **kw):
    return [(s["status"], s["classification"], s["text"]) for s in starters(rows, **kw)]


def game(rows, **kw):
    return sc.classify_game(s["classification"] for s in starters(rows, **kw))


def test_real_c3_rows_pending():
    assert view([C3_FIRST, C3_NOW]) == [("pending", "pending", "待公告")] * 2
    assert game([C3_FIRST, C3_NOW]) == "pending"


def test_announced_a():
    rows = [C3_FIRST, C3_NOW, rev(A, H_SIDE, h="a1", fetched="2026-10-20T08:35:00+00:00")]
    assert view(rows) == [("announced", "announced", "林詔恩"), ("announced", "announced", "羅戈")]
    assert game(rows) == "announced"


def test_same_starter_many_payloads_is_not_changed():
    """同一先發因其他欄位（如隊名）變動對應多列 ⇒ 以 acnt 去重，仍是 announced（R2 §3、R3 §3b）。"""
    rows = [C3_FIRST, rev(A, H_SIDE, h="p1", fetched="2026-10-20T08:35:00+00:00"),
            rev(A, H_SIDE, h="p2", fetched="2026-10-20T09:05:00+00:00"),
            rev(A, H_SIDE, h="p3", fetched="2026-10-20T09:30:00+00:00")]
    assert [c for _, c, _ in view(rows)] == ["announced", "announced"]


def test_a_to_b_changed():
    rows = [C3_NOW, rev(A, H_SIDE, h="a", fetched="2026-10-20T08:35:00+00:00"),
            rev(B, H_SIDE, h="b", fetched="2026-10-20T09:05:00+00:00")]
    assert view(rows) == [("announced", "changed", "王某（已更換）"), ("announced", "announced", "羅戈")]
    assert game(rows) == "announced"
    out = starters(rows)
    assert out[0]["player_id"] == B and out[0]["name"] == "王某"   # name 欄只放姓名，字樣在 text


def test_a_b_a_changed_current_is_a():
    """A→B→A：A 的 payload 相同 ⇒ 只更新舊列 last_seen_at；目前值為 A，歷程有 B ⇒ changed。"""
    rows = [rev(A, H_SIDE, h="a", fetched="2026-10-20T08:35:00+00:00", seen="2026-10-20T09:35:00+00:00"),
            rev(B, H_SIDE, h="b", fetched="2026-10-20T09:05:00+00:00")]
    assert view(rows)[0] == ("announced", "changed", "林詔恩（已更換）")


def test_a_to_empty_retracted():
    rows = [rev(A, H_SIDE, h="a", fetched="2026-10-20T08:35:00+00:00"),
            rev(None, H_SIDE, h="e", fetched="2026-10-20T09:05:00+00:00")]
    assert view(rows) == [("pending", "retracted", "待公告（先前公告已撤回）"), ("announced", "announced", "羅戈")]
    s = starters(rows)[0]
    assert s["player_id"] is None and s["name"] is None and s["reason"] == "starter_not_announced"
    assert game(rows) == "partial"


def test_one_side_partial_no_label():
    rows = [C3_NOW, rev(A, None, h="a", fetched="2026-10-20T08:35:00+00:00")]
    assert view(rows) == [("announced", "announced", "林詔恩"), ("pending", "pending", "待公告")]
    assert game(rows) == "partial"
    # 一隊更換、另一隊未公告 ⇒ 仍是 partial
    rows2 = [*rows, rev(B, None, h="b", fetched="2026-10-20T09:05:00+00:00")]
    assert game(rows2) == "partial" and view(rows2)[0][1] == "changed"


def test_postponed_only_new_date_rows_count():
    """改期：舊日期列上的先發（含不同人）不算賽前歷程；新日期只出現 B ⇒ announced。"""
    rows = [rev(A, H_SIDE, h="old", day="2026-10-19", fetched="2026-10-19T08:35:00+00:00"),
            rev(B, H_SIDE, h="new", fetched="2026-10-20T08:35:00+00:00")]
    assert [c for _, c, _ in view(rows)] == ["announced", "announced"]
    # 新日期只剩空欄、舊日期曾有先發 ⇒ pending（⛔ retracted）
    rows = [rev(A, H_SIDE, h="old", day="2026-10-19", fetched="2026-10-19T08:35:00+00:00"),
            rev(h="new", fetched="2026-10-20T08:35:00+00:00")]
    assert [c for _, c, _ in view(rows)] == ["pending", "pending"]


def test_rows_after_first_pitch_not_in_history():
    """開打後列（IsPlayBall=Y）與結果非空列不算賽前歷程。"""
    pre = rev(A, H_SIDE, h="pre", fetched="2026-10-20T08:35:00+00:00")
    live = rev(B, H_SIDE, h="live", ipb="Y", fetched="2026-10-20T10:40:00+00:00")
    assert sc.pregame_rows([pre, live], target_date=DAY, teams=TEAMS) == [pre]
    final = rev(B, H_SIDE, h="fin", result="0", fetched="2026-10-20T14:00:00+00:00")
    assert sc.pregame_rows([pre, final], target_date=DAY, teams=TEAMS) == [pre]
    no_flag = rev(B, H_SIDE, h="nf", ipb=None, fetched="2026-10-20T09:00:00+00:00")   # 未投影／缺欄 ⇒ 不當賽前
    assert sc.pregame_rows([no_flag], target_date=DAY, teams=TEAMS) == []
    # 目前值是開打後列的 A、賽前也只有 A ⇒ announced
    live_a = rev(A, H_SIDE, h="live", ipb="Y", fetched="2026-10-20T10:40:00+00:00")
    assert [c for _, c, _ in view([pre, live_a])] == ["announced", "announced"]


def test_current_not_in_pregame_history_is_changed():
    """局部調整（plan-1 §1.1 的 |S|>1 以 S∪{目前值} 計）：賽前只見 A、目前（開打後列）是 B ⇒ changed。"""
    pre = rev(A, H_SIDE, h="pre", fetched="2026-10-20T08:35:00+00:00")
    live_b = rev(B, H_SIDE, h="live", ipb="Y", fetched="2026-10-20T10:40:00+00:00")
    assert view([pre, live_b])[0] == ("announced", "changed", "王某（已更換）")


def test_other_team_codes_not_in_history():
    rows = [rev(B, H_SIDE, h="x", vt="ADD011", fetched="2026-10-20T08:00:00+00:00"),
            rev(A, H_SIDE, h="a", fetched="2026-10-20T08:35:00+00:00")]
    assert [c for _, c, _ in view(rows)] == ["announced", "announced"]


def test_read_failure_unknown():
    assert view(None) == [("unknown", "unknown", "暫時無法取得")] * 2
    assert sc.classify_game(s["classification"] for s in starters(None)) == "unknown"


def test_gate_ignores_history():
    """既有 gate 不變：現行列非賽前／日期或隊伍不符 ⇒ pending，⛔ 因歷程變成 retracted。"""
    pre = rev(A, H_SIDE, h="pre", fetched="2026-10-20T08:35:00+00:00")
    for cur in (rev(h="pp", result="1", fetched="2026-10-20T09:00:00+00:00"),            # 延賽
                rev(A, H_SIDE, h="fin", result="0", fetched="2026-10-20T14:00:00+00:00")):  # 終場
        assert [c for _, c, _ in view([pre, cur])] == ["pending", "pending"]
    assert [c for _, c, _ in view([pre], day=date(2026, 10, 21))] == ["pending", "pending"]


def test_changed_name_missing_keeps_template():
    rows = [rev(A, H_SIDE, h="a", fetched="2026-10-20T08:35:00+00:00"),
            rev(B, H_SIDE, h="b", fetched="2026-10-20T09:05:00+00:00")]
    assert view(rows, names={})[0] == ("announced", "changed", "已公告（姓名待更新）（已更換）")


def test_no_time_fields_in_output():
    rows = [rev(A, H_SIDE, h="a", fetched="2026-10-20T08:35:00+00:00"),
            rev(B, H_SIDE, h="b", fetched="2026-10-20T09:05:00+00:00")]
    for s in starters(rows):
        assert set(s) == {"team_code", "status", "reason", "player_id", "name", "text", "classification"}


def test_classify_side_and_game_table():
    assert sc.classify_side(A, frozenset()) == "announced"
    assert sc.classify_side(A, frozenset({A})) == "announced"
    assert sc.classify_side(A, frozenset({A, B})) == "changed"
    assert sc.classify_side(None, frozenset({A})) == "retracted"
    assert sc.classify_side("  ", frozenset()) == "pending"
    assert sc.classify_game(["announced", "changed"]) == "announced"
    assert sc.classify_game(["changed", "retracted"]) == "partial"
    assert sc.classify_game(["retracted", "pending"]) == "pending"
    assert sc.classify_game(["unknown", "announced"]) == "unknown"


def test_watch_and_overview_next_game_show_same_classification():
    """第 4 區（compute_watch）與第 1 區 next_game（compute_overview）共用 official_starters ⇒ 同字、同分類。"""
    from postseason_context_inputs import BRO, DRAGON, NOW_2026, inputs

    from cpbl import postseason_contract as pc
    from cpbl.playoffs import overview as ov
    from cpbl.playoffs import series_summary as ss

    ctx = pc.compute_series_context(inputs(2026), now=NOW_2026)
    tg = ctx["state"]["by_series"]["C"]["target_game_key"]
    g = next(x for x in ctx["games"] if x["game_key"] == tg)
    day = g["game_date"]
    assert [g["away_team_code"], g["home_team_code"]] == [BRO, DRAGON]
    rows = [rev(A, H_SIDE, h="a", day=day, vt=BRO, ht=DRAGON, fetched=f"{day}T08:35:00+00:00"),
            rev(B, None, h="b", day=day, vt=BRO, ht=DRAGON, fetched=f"{day}T09:05:00+00:00")]
    o = ov.compute_overview(ov.OverviewInputs(context=ctx, names={}, series_summary=ss.aggregate_all(ctx, None),
                                              summary_names={}, starters={"C": (rows, NAMES)}), "C")
    nxt = o["series_section"]["next_game"]["starters"]
    w = wrd.compute_watch(wrd.WatchInputs(year=2026, series="C", context=ctx, rosters={BRO: None, DRAGON: None},
                                          window_games=[], official_schedule=rows, starter_names=NAMES),
                          now=NOW_2026)
    assert w["starters"] == nxt
    assert [(s["classification"], s["text"]) for s in nxt] == [("changed", "王某（已更換）"),
                                                               ("retracted", "待公告（先前公告已撤回）")]
    assert w["starters_classification"] == "partial"
    assert o["context_version"] == ctx["context_version"]          # 分類不進 context_version
