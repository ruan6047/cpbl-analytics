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


def wg(kind, sno, day, away=AWAY, home=HOME, completed=True, box_away=None, box_home=None,
       delay_kind=None, orig_date=None):
    """box_* 預設＝完賽與否（未完賽場預設尚無投球紀錄）。"""
    box_away = completed if box_away is None else box_away
    box_home = completed if box_home is None else box_home
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


# —— 官方先發投手（#314）：官方賽程現行列 ——————————————————————————————————
#
# 列形狀取自本機 DB 唯讀抽取的真實 ``game_schedule_status_revisions``（2026-10-16 13:4x，#314 執行證據
# probes/revisions_E_C.txt），投影成 OFFICIAL_SCHEDULE_SQL 的欄位：賽前列 acnt 有值、姓名空（E2／E3）；
# 先發未填＝空字串 → SQL NULLIF 成 None（C1、E3 首版、E4 賽前）。


def rev(day, vt, ht, vpa=None, hpa=None, *, result=None, present=1, vpn=None, hpn=None, h="h", fetched, seen=None):
    return {"raw_present_status": present, "raw_game_result": result, "raw_game_date": date.fromisoformat(day),
            "visiting_team_code": vt, "home_team_code": ht, "visiting_pitcher_acnt": vpa, "home_pitcher_acnt": hpa,
            "visiting_pitcher_name": vpn, "home_pitcher_name": hpn, "payload_hash": h,
            "fetched_at": datetime.fromisoformat(fetched), "last_seen_at": datetime.fromisoformat(seen or fetched)}


# 真實列（本機 2026-10-16 抽取）。
C1_NOW = rev("2026-10-17", AWAY, HOME, h="d2145728", fetched="2026-10-13T02:10:12+00:00",
             seen="2026-10-16T02:10:17+00:00")
E3_FIRST = rev("2026-10-11", "ADD011", "ACN011", h="be9f67d5", fetched="2026-10-10T02:10:15+00:00")
E3_PREGAME = rev("2026-10-11", "ADD011", "ACN011", "0000006848", "0000005151", h="1c1dc856",
                 fetched="2026-10-11T02:10:10+00:00")
E3_FINAL = rev("2026-10-11", "ADD011", "ACN011", "0000006848", "0000005151", result="0", vpn="林詔恩", hpn="羅戈",
               h="93aacb78", fetched="2026-10-12T02:10:27+00:00", seen="2026-10-16T02:10:16+00:00")
E2_PREGAME = rev("2026-10-10", "ACN011", "ADD011", "0000007560", "0000007778", h="898ecd0c",
                 fetched="2026-10-10T02:10:15+00:00")
E3_DAY, E3_TEAMS = date(2026, 10, 11), ["ADD011", "ACN011"]
NAMES = {"0000006848": {"player_name": "林詔恩", "gamelog_name": "林詔恩"},
         "0000005151": {"player_name": "羅戈", "gamelog_name": "羅戈"}}


def starters_of(rows, names=None, day=E3_DAY, teams=None):
    return wrd.official_starters(rows, target_date=day, teams=teams or E3_TEAMS, names=names or {})


def test_starters_pending_when_not_announced_real_c1_row():
    w = run(official_schedule=[C1_NOW])
    assert [(s["team_code"], s["status"], s["text"]) for s in w["starters"]] == [
        (AWAY, "pending", "待公告"), (HOME, "pending", "待公告")]
    assert {f"starter_not_announced:{AWAY}", f"starter_not_announced:{HOME}"} <= set(w["missing_reason"])
    assert all(s["player_id"] is None and s["name"] is None for s in w["starters"])


def test_starters_announced_real_pregame_row_names_from_players():
    out, missing = starters_of([E3_FIRST, E3_PREGAME], NAMES)
    assert [(s["team_code"], s["status"], s["player_id"], s["text"]) for s in out] == [
        ("ADD011", "announced", "0000006848", "林詔恩"), ("ACN011", "announced", "0000005151", "羅戈")]
    assert missing == []


def test_starter_name_three_priorities():
    row = dict(E3_PREGAME, visiting_pitcher_name="官方名")
    names = {"0000006848": {"player_name": "主檔名", "gamelog_name": "逐場名"},
             "0000005151": {"player_name": None, "gamelog_name": "逐場名"}}
    out, _ = starters_of([row], names)
    assert [s["text"] for s in out] == ["官方名", "逐場名"]
    out, _ = starters_of([E3_PREGAME], {"0000006848": {"player_name": "主檔名", "gamelog_name": "逐場名"}})
    assert out[0]["text"] == "主檔名"
    # 三者皆無 ⇒ 已公告（姓名待更新），⛔ 顯示 acnt。
    assert out[1]["status"] == "announced" and out[1]["text"] == "已公告（姓名待更新）" and out[1]["name"] is None


def test_starter_name_missing_real_e2_shape():
    out, missing = starters_of([E2_PREGAME], day=date(2026, 10, 10), teams=["ACN011", "ADD011"])
    assert [s["text"] for s in out] == ["已公告（姓名待更新）"] * 2
    assert missing == ["starter_name_missing:ACN011", "starter_name_missing:ADD011"]
    assert "0000007560" not in [s["text"] for s in out]


def test_starters_one_side_announced():
    for empty in (None, "", "  "):   # SQL 端 NULLIF(btrim)；純函式對未投影的原字串也不當成已公告
        out, missing = starters_of([dict(E3_PREGAME, home_pitcher_acnt=empty)], NAMES)
        assert [(s["status"], s["text"]) for s in out] == [("announced", "林詔恩"), ("pending", "待公告")]
        assert missing == ["starter_not_announced:ACN011"]


def test_starters_a_b_a_selects_latest_and_marks_changed():
    """A→B→A：官網改回 A 時，同 payload 的 A 列 last_seen_at 更新 ⇒ 選 A；賽前歷程出現過 B ⇒ 標更換
    （#320 A2，需求方裁定 6261389955 取代 #314 Q3「不標更換」）。``status`` 值域不變、⛔ 帶任何時間欄。"""
    a = rev("2026-10-11", "ADD011", "ACN011", "0000006848", "0000005151", h="a",
            fetched="2026-10-10T10:00:00+00:00", seen="2026-10-11T08:30:00+00:00")
    b = rev("2026-10-11", "ADD011", "ACN011", "0000009999", "0000005151", h="b",
            fetched="2026-10-11T02:10:00+00:00")
    a, b = dict(a, is_play_ball="N"), dict(b, is_play_ball="N")
    out, _ = starters_of([b, a], NAMES)
    assert [(s["player_id"], s["status"], s["classification"], s["text"]) for s in out] == [
        ("0000006848", "announced", "changed", "林詔恩（已更換）"), ("0000005151", "announced", "announced", "羅戈")]
    out, _ = starters_of([dict(a, last_seen_at=a["fetched_at"]), b], NAMES)  # 停在 B
    assert out[0]["player_id"] == "0000009999" and out[0]["text"] == "已公告（姓名待更新）（已更換）"
    for s in out:
        assert set(s) == {"team_code", "status", "reason", "player_id", "name", "text", "classification"}
        assert s["status"] in {"announced", "pending", "unknown"}


def test_starters_pending_when_not_pregame_or_mismatch():
    cases = {
        "official_schedule_postponed": [dict(E3_PREGAME, raw_game_result="1")],
        "official_schedule_reserved": [dict(E3_PREGAME, raw_game_result="2")],
        "official_schedule_final": [E3_FINAL],
        "official_schedule_unknown": [dict(E3_PREGAME, raw_present_status=0)],
        "official_schedule_missing": [],
        "official_schedule_date_mismatch": [dict(E3_PREGAME, raw_game_date=date(2026, 10, 12))],
        "official_schedule_team_mismatch": [dict(E3_PREGAME, visiting_team_code="AAA011")],
    }
    for reason, rows in cases.items():
        out, missing = starters_of(rows, NAMES)
        assert [(s["status"], s["reason"], s["text"], s["player_id"]) for s in out] == [
            ("pending", reason, "待公告", None)] * 2, reason
        assert missing == ["starter_not_announced:ADD011", "starter_not_announced:ACN011"]
    out, _ = starters_of([E3_PREGAME], NAMES, day=None)
    assert {s["reason"] for s in out} == {"official_schedule_date_mismatch"}


def test_starters_unavailable_when_read_failed():
    w = run(official_schedule=None)
    assert [(s["status"], s["text"]) for s in w["starters"]] == [("unknown", "暫時無法取得")] * 2
    assert "starter_source_unavailable" in w["missing_reason"]
    assert "starter_source_not_delivered" not in w["missing_reason"]


def test_starters_ignore_s02_074_status():
    w = run(context=context(starters={AWAY: "announced", HOME: "changed"}), official_schedule=[C1_NOW])
    assert {s["status"] for s in w["starters"]} == {"pending"}  # S02 的 074 狀態不得被轉出
    assert "announcement" not in w


def test_starters_change_watch_version():
    a = run(official_schedule=[C1_NOW])
    b = run(official_schedule=[dict(C1_NOW, visiting_pitcher_acnt="0000005151")],
            starter_names={"0000005151": {"player_name": "羅戈", "gamelog_name": None}})
    assert b["starters"][0]["text"] == "羅戈"
    assert a["watch_version"] != b["watch_version"]


def test_module_does_not_read_074_or_starter_ids_directly():
    """本模組不讀 074、不讀 starter_id。覆蓋範圍只有本模組的 import 與 *_SQL；經 S02
    ``read_series_inputs`` 的間接 074 讀取不在此守衛內（需求方裁定 R2 乙，issuecomment-6184818006）。"""
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(wrd))
    imported = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)} | {
        a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    assert not {m for m in imported if m and m.startswith("cpbl.reports")}
    sql = " ".join(v for k, v in vars(wrd).items() if k.endswith("_SQL"))
    for banned in ("game_lineup_announcement_revisions", "starter_id"):
        assert banned not in sql


# —— 4B 占位移除（#314）、歷史目標、版本欄 ——————————————————————————————————


def test_no_publication_placeholder():
    """S09 已停止（#290）：回應不帶 ``publication``，全文不再出現 ``s09_not_enabled``／「賽前快照尚未發布」。"""
    import json

    for w in (run(), run(series="E", requested_game=4), run(series="E"), run(requested_game=2)):
        assert "publication" not in w
        dumped = json.dumps(w, ensure_ascii=False, default=str)
        assert "s09_not_enabled" not in dumped and "賽前快照尚未發布" not in dumped and "S09" not in dumped
    w = run()
    assert w["policy_version"] == "playoffs-policy/v2.0-proposed"
    for k in ("series_id", "target_game_key", "context_version", "source_manifest", "as_of", "coverage",
              "missing_reason", "watch_version", "registration"):
        assert k in w


def test_requested_completed_game_is_historical():
    w = run(series="E", requested_game=4)
    assert w["status"] == "historical_not_published" and w["teams"] == []
    w2 = run(series="E")  # S02 目標停在已完賽 E4（系列已決定）
    assert w2["status"] == "historical_not_published"
    for x in (w, w2):
        assert x["text"] == "本場已完賽，觀戰重點只提供系列下一場"
        assert x["missing_reason"] == ["historical_not_supported"]


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
