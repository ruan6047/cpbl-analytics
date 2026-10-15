"""#289 S08 WP2：watch 讀取面純組裝（compute_watch／day_coverage／appearance_of）。

合成形狀的事實輸入，不連 DB；SQL 語意另由 ``test_playoffs_watch_reader_isolated.py`` 在隔離庫驗。
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from cpbl.playoffs import watch_reader as wrd
from cpbl.playoffs.watch_reader import WatchInputs, compute_watch, day_coverage
from cpbl.playoffs.watch_rules import Appearance

NOW = datetime(2026, 10, 17, 2, 0, tzinfo=UTC)  # 台北 10/17 10:00，C1 賽前
D = date(2026, 10, 17)
AWAY, HOME = "ACN011", "AAA011"


def gk(kind, sno, year=2026):
    return {"year": year, "kind_code": kind, "game_sno": sno}


def context(target_status="scheduled", completed=False, starters=None, target: int | None = 1):
    games = [
        {"game_key": gk("C", 1), "game_date": "2026-10-17", "away_team_code": AWAY, "home_team_code": HOME,
         "completed": completed, "target_status": target_status},
        {"game_key": gk("C", 2), "game_date": "2026-10-18", "away_team_code": AWAY, "home_team_code": HOME,
         "completed": False, "target_status": "scheduled"},
        {"game_key": gk("E", 4), "game_date": "2026-10-12", "away_team_code": "ADD011", "home_team_code": AWAY,
         "completed": True, "target_status": "final"},
    ]
    starters = starters or {}
    return {
        "context_version": "ctx-v1",
        "source_manifest": [{"source": "games", "status": "ok", "observed_at": "x"}],
        "as_of": {"last_refresh_at": "2026-10-16T02:24:00+00:00", "last_completed_game_date": "2026-10-12"},
        "series": {"C": {"series_id": {"year": 2026, "kind_code": "C"}}, "E": {"series_id": {"kind_code": "E"}}},
        "state": {"by_series": {"C": {"target_game_key": gk("C", target) if target else None},
                                "E": {"target_game_key": gk("E", 4)}}},
        "games": games,
        "teams": [{"series": "C", "team_code": t, "starter_status": starters.get(t, "missing")} for t in (AWAY, HOME)],
    }


def wg(kind, sno, day, away=AWAY, home=HOME, completed=True, box_away=True, box_home=True,
       delay_kind=None, orig_date=None):
    return {"year": 2026, "kind_code": kind, "game_sno": sno, "game_date": day, "orig_date": orig_date,
            "delay_kind": delay_kind, "away_team_code": away, "home_team_code": home,
            "completed": completed, "box_away": box_away, "box_home": box_home}


def roster(*members):
    return {"roster_id": "r1", "published_date": "2026-10-16", "source_url": "https://www.cpbl.com.tw/x",
            "annotation_version": 1,
            "members": [{"player_id": pid, "announced_name": f"投手{pid[-2:]}", "tactical_role": role}
                        for pid, role in members]}


def ap(day, pitches, kind="A", sno=None, outs=3, er=0):
    return Appearance(game_key=(2026, kind, sno or (day.toordinal() % 1000)), date=day, date_trusted=True,
                      pitch_cnt=pitches, outs=outs, er=er, role_type="中繼")


def run(**kw):
    base = dict(year=2026, series="C", context=context(), rosters={AWAY: None, HOME: None}, window_games=[])
    base.update(kw)
    return compute_watch(WatchInputs(**base), now=NOW)


# —— 名單 ——————————————————————————————————————————————————————————


def test_roster_missing_lists_no_pitchers():
    w = run()
    assert w["status"] == "ok"
    for t in w["teams"]:
        assert t["roster_status"] == "missing"
        assert t["roster_text"] == "32 人名單尚未提交"
        assert t["pitchers"] == []
    assert "roster_missing:ACN011" in w["missing_reason"]
    assert w["coverage"] == "unknown"


def test_roster_missing_does_not_infer_from_appearances():
    # 有出賽紀錄但沒名單 ⇒ 仍不列投手（⛔ 以出賽反推名單）
    w = run(appearances={"0000000001": [ap(D - timedelta(days=1), 20)]})
    assert all(t["pitchers"] == [] for t in w["teams"])


def test_roster_source_unavailable():
    w = run(rosters=None)
    assert {t["roster_status"] for t in w["teams"]} == {"unavailable"}
    assert "roster_unavailable:AAA011" in w["missing_reason"]


def test_default_visible_roles_and_rotation_exempt():
    r = roster(("0000000001", "終結"), ("0000000002", "輪值"), ("0000000003", None),
               ("0000000004", "勝利組"), ("0000000005", "長中繼"))
    w = run(rosters={AWAY: r, HOME: None})
    ps = w["teams"][0]["pitchers"]
    assert [p["player_id"] for p in ps] == ["0000000001", "0000000004", "0000000005", "0000000002", "0000000003"]
    assert [p["default_visible"] for p in ps] == [True, True, True, False, False]
    by = {p["player_id"]: p for p in ps}
    assert by["0000000002"]["load"]["level"] == "starter_exempt"
    assert by["0000000001"]["load"]["level"] == "low"
    assert by["0000000003"]["tactical_role"] is None  # 角色未標記不被刪
    assert by["0000000001"]["role_source"] == "本站註記（非官方數據）"
    assert by["0000000001"]["registration"]["status"] == "unknown"
    assert w["coverage"] == "complete"


def test_loads_and_consecutive_era():
    r = roster(("0000000001", "勝利組"), ("0000000002", "終結"))
    apps = {
        "0000000001": [ap(D - timedelta(days=1), 20, kind="C", sno=1), ap(D - timedelta(days=2), 18, kind="E", sno=4),
                       ap(date(2026, 9, 1), 10), ap(date(2026, 9, 2), 12, outs=3, er=1)],
        "0000000002": [ap(D - timedelta(days=1), 31, kind="C", sno=1)],
    }
    games = [wg("C", 1, D - timedelta(days=1)), wg("E", 4, D - timedelta(days=2), away="ADD011", home=AWAY)]
    w = run(rosters={AWAY: r, HOME: None}, appearances=apps, window_games=games)
    by = {p["player_id"]: p for p in w["teams"][0]["pitchers"]}
    p1 = by["0000000001"]
    assert p1["load"]["level"] == "medium" and p1["load"]["metrics"]["S2"] == 38
    assert p1["consecutive_era"]["appearances"] == 1 and p1["consecutive_era"]["era"] == 9.0
    assert len(p1["recent"]) == 3 and p1["recent"][0]["game_key"] == gk("C", 1)
    assert by["0000000002"]["load"]["level"] == "high"
    assert by["0000000002"]["consecutive_era"] is None


# —— 覆蓋：box 未送達、未完賽、保留賽、二軍、即時 ——————————————————————


def test_box_missing_greys_pitchers():
    r = roster(("0000000001", "終結"))
    games = [wg("C", 9, D - timedelta(days=1), box_away=False)]
    w = run(rosters={AWAY: r, HOME: None}, window_games=games)
    t = w["teams"][0]
    d1 = next(d for d in t["days"] if d["offset"] == 1)
    assert d1["reasons"] == ["box_missing"] and d1["text"] == ["該隊當日正式場已完賽，但投手逐場紀錄尚未送達"]
    assert t["pitchers"][0]["load"]["level"] == "unknown"
    # 主隊有 box ⇒ 主隊該日完整
    assert next(d for d in w["teams"][1]["days"] if d["offset"] == 1)["complete"] is True
    assert "box_missing" in w["missing_reason"]
    assert w["coverage"] == "incomplete"


def test_game_not_final_greys():
    cov = day_coverage(AWAY, D - timedelta(days=1), [wg("C", 9, D - timedelta(days=1), completed=False)],
                       target_key=(2026, "C", 1), target_date=D, target_status="scheduled")
    assert cov.reasons == ("game_not_final",)


def test_target_pre_game_counts_zero_live_unobserved():
    g = [wg("C", 1, D, completed=False)]
    kw = dict(target_key=(2026, "C", 1), target_date=D)
    assert day_coverage(AWAY, D, g, target_status="scheduled", **kw).complete is True
    assert day_coverage(AWAY, D, g, target_status="postponed", **kw).complete is True
    live = day_coverage(AWAY, D, g, target_status="live", **kw)
    assert live.reasons == ("live_unobserved",) and live.live is True
    assert day_coverage(AWAY, D, g, target_status="unknown", **kw).reasons == ("schedule_unavailable",)
    assert day_coverage(AWAY, D, g, target_status="suspended", **kw).reasons == ("game_not_final",)


def test_live_target_greys_all_pitchers():
    r = roster(("0000000001", "終結"))
    w = run(context=context(target_status="live"), rosters={AWAY: r, HOME: None},
            window_games=[wg("C", 1, D, completed=False)])
    p = w["teams"][0]["pitchers"][0]
    assert p["load"]["level"] == "unknown"
    assert "live_unobserved" in p["load"]["incomplete"][0]["reasons"]


def test_doubleheader_earlier_game_unfinished_on_target_day():
    g = [wg("A", 300, D, completed=False), wg("C", 1, D, completed=False)]
    cov = day_coverage(AWAY, D, g, target_key=(2026, "C", 1), target_date=D, target_status="scheduled")
    assert cov.reasons == ("game_not_final",)


def test_reserve_game_orig_date_in_window_not_completed():
    g = [wg("A", 274, date(2026, 10, 30), completed=False, delay_kind="保留", orig_date=D - timedelta(days=2))]
    cov = day_coverage(AWAY, D - timedelta(days=2), g, target_key=(2026, "C", 1), target_date=D,
                       target_status="scheduled")
    assert cov.reasons == ("game_not_final",)


def test_farm_game_counts_for_team():
    g = [wg("D", 50, D - timedelta(days=3), away="ACN022", home="AAA022", box_away=False)]
    cov = day_coverage(AWAY, D - timedelta(days=3), g, target_key=(2026, "C", 1), target_date=D,
                       target_status="scheduled")
    assert cov.reasons == ("box_missing",)
    assert wrd.farm_code("AAA011") == "AAA022" and wrd.farm_code("X") is None


def test_other_teams_games_ignored():
    g = [wg("A", 1, D - timedelta(days=1), away="ADD011", home="AEO011", completed=False)]
    assert day_coverage(AWAY, D - timedelta(days=1), g, target_key=None, target_date=D,
                        target_status="scheduled").complete is True


def test_window_unavailable_greys():
    r = roster(("0000000001", "終結"))
    w = run(rosters={AWAY: r, HOME: None}, window_games=None)
    assert w["teams"][0]["pitchers"][0]["load"]["level"] == "unknown"
    assert "schedule_unavailable" in w["missing_reason"]


def test_appearances_unavailable_not_green():
    r = roster(("0000000001", "終結"))
    w = run(rosters={AWAY: r, HOME: None}, appearances_ok=False)
    assert w["teams"][0]["pitchers"][0]["load"]["level"] == "unknown"
    assert "pitching_gamelog_unavailable" in w["missing_reason"]


def test_appearance_of_reserve_and_outs():
    a = wrd.appearance_of({"year": 2026, "kind_code": "A", "game_sno": 3, "game_date": date(2026, 9, 5),
                           "orig_date": date(2026, 9, 4), "delay_kind": "保留", "pitch_cnt": 20,
                           "inning_pitched_cnt": 1, "inning_pitched_div3": 2, "earned_runs": 1, "role_type": "中繼"})
    assert a.date_trusted is False and a.possible_dates == (date(2026, 9, 4), date(2026, 9, 5)) and a.outs == 5
    b = wrd.appearance_of({"year": 2026, "kind_code": "A", "game_sno": 4, "game_date": date(2026, 9, 6),
                           "orig_date": date(2026, 8, 1), "delay_kind": "延賽", "pitch_cnt": 20,
                           "inning_pitched_cnt": None, "inning_pitched_div3": None, "earned_runs": None})
    assert b.date_trusted is True and b.possible_dates == () and b.outs is None


# —— 官方先發投手：S11 定案前恆未知（E1／E2） ——————————————————————————————


def test_starters_unknown_until_s11():
    w = run(context=context(starters={AWAY: "announced", HOME: "changed"}))  # S02 的 074 狀態不得被轉出
    assert w["starters"] == [
        {"team_code": t, "status": "unknown", "reason": "starter_source_not_delivered",
         "text": "官方先發投手：未知（來源尚未接入，S11）"} for t in (AWAY, HOME)]
    assert "starter_source_not_delivered" in w["missing_reason"]
    assert "announcement" not in w


def test_reader_does_not_read_074_or_starter_ids():
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(wrd))
    imported = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)} | {
        a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    assert not {m for m in imported if m and m.startswith("cpbl.reports")}
    sql = " ".join(v for k, v in vars(wrd).items() if k.endswith("_SQL"))
    for banned in ("game_lineup_announcement_revisions", "starter_id"):
        assert banned not in sql


# —— 4B 未發布、歷史目標、版本欄 ——————————————————————————————————————


def test_publication_not_published_both_slots():
    w = run()
    assert w["publication"]["status"] == "not_published"
    assert [s["text"] for s in w["publication"]["slots"]] == ["賽前快照尚未發布", "賽前快照尚未發布"]
    assert w["policy_version"] == "playoffs-policy/v2.0-proposed"
    for k in ("series_id", "target_game_key", "context_version", "source_manifest", "as_of", "coverage",
              "missing_reason", "watch_version", "registration"):
        assert k in w


def test_requested_completed_game_is_historical():
    w = run(series="E", requested_game=4)
    assert w["status"] == "historical_not_published" and w["teams"] == []
    w2 = run(series="E")  # S02 目標停在已完賽 E4（系列已決定）
    assert w2["status"] == "historical_not_published"


def test_requested_future_non_target():
    w = run(requested_game=2)
    assert w["status"] == "not_target" and w["teams"] == []


def test_unknown_game_and_no_target():
    assert run(requested_game=99)["status"] == "game_unknown"
    assert run(context=context(target=None))["status"] == "no_target"


def test_watch_version_ignores_now():
    a = run()
    b = compute_watch(WatchInputs(year=2026, series="C", context=context(), rosters={AWAY: None, HOME: None},
                                  window_games=[]), now=NOW + timedelta(minutes=5))
    assert a["watch_version"] == b["watch_version"]
    assert a["as_of"]["now"] != b["as_of"]["now"]
