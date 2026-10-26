"""#342 先發 23:00 時點：純函式、只寫先發寫入器的不變量（真實 payload）、失敗通知、與晚間鏈 plan 的接線。

payload 一律取自 ``tests/fixtures/starter_watch_replay/revisions-2026.json``（本機修訂表唯讀匯出）；stats 列沿用
``tests/test_postseason_starter_checkpoints.py`` 的 SYNTHETIC 形狀。不連網、不碰 DB。
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from cpbl.ingest import postseason_evening as pe
from cpbl.ingest import starter_watch as sw

TPE = ZoneInfo("Asia/Taipei")
FIXTURE = Path(__file__).parent / "fixtures" / "starter_watch_replay" / "revisions-2026.json"
ROWS = json.loads(FIXTURE.read_text(encoding="utf-8"))["rows"]


def tpe(m, d, hh, mm) -> datetime:
    return datetime(2026, m, d, hh, mm, tzinfo=TPE)


def payloads(kind: str, sno: int) -> list[dict]:
    return [r["raw_payload"] for r in ROWS if r["kind_code"] == kind and r["game_sno"] == sno]


def sched(kind: str, sno: int, status: str, starts: str) -> dict:
    return {"year": 2026, "kind_code": kind, "game_sno": sno, "status": status, "starts_at": starts,
            "game_date": starts[:10], "away_code": "ACN011", "home_code": "AAA011", "venue": "大巨蛋"}


# =========================================================================== 只寫先發寫入器（真實 payload）

def test_writer_takes_published_pregame_starters():
    pre = [p for p in payloads("C", 6) if p["GameResult"] == "" and p["HomePitcherAcnt"]]
    assert pre and pre[0]["PresentStatus"] == 1, "前提：賽前 entry 的 PresentStatus 也是 1"
    rows, revs = sw.starter_rows(pre, {"2026-C-6"})
    assert rows == [(pre[0]["HomePitcherAcnt"], pre[0]["VisitingPitcherAcnt"], 2026, "C",
                     pre[0]["GameSeasonCode"], 6)]
    assert revs == pre
    assert sw.starter_rows(pre, {"2026-C-7"}) == ([], []), "只寫目標場"


def test_writer_mirrors_unpublished_pregame_entry():
    empty = [p for p in payloads("C", 6) if p["GameResult"] == "" and not p["HomePitcherAcnt"]][-1:]
    assert empty
    rows, revs = sw.starter_rows(empty, {"2026-C-6"})
    assert rows == [(None, None, 2026, "C", empty[0]["GameSeasonCode"], 6)] and revs == empty, \
        "官網空就寫空（同 upsert_games 兩欄語意；舊日期先發不殘留）"


@pytest.mark.parametrize("sno", [304, 306, 326])
def test_writer_never_touches_started_or_reserved_games(sno):
    """2026-A-304／A-306 賽中部分比分、A-326 保留：同組任一筆終局／保留／非零比分 ⇒ 一列都不碰、不記修訂。"""
    group = payloads("A", sno)
    assert any(p["GameResult"] in ("0", "2") or p["HomeScore"] or p["VisitingScore"] for p in group)
    for i in range(1, len(group) + 1):          # 依取得順序逐步出現（含只出現賽中那幾筆的時刻）
        seen = group[:i]
        if not any(p["GameResult"] in ("0", "2") or p["HomeScore"] or p["VisitingScore"] for p in seen):
            continue                            # 尚未開打（含只是延賽）的時刻不在此測
        assert sw.starter_rows(seen, {f"2026-A-{sno}"}) == ([], []), (sno, i)


def test_writer_uses_rescheduled_entry_as_primary():
    """2026-A-302：9/01 延賽（GameResult 1）改 9/30；主 entry 取 GameResult 空白者中最新 GameDate。"""
    group = [p for p in payloads("A", 302) if p["GameResult"] in ("", "1")]
    new = [p for p in group if p["GameResult"] == "" and p["HomePitcherAcnt"] and p["GameDate"].startswith("2026-09-30")]
    old = [p for p in group if p["GameResult"] == "1"]
    assert new and old
    rows, _ = sw.starter_rows(old + new[:1], {"2026-A-302"})
    assert rows == [(new[0]["HomePitcherAcnt"], new[0]["VisitingPitcherAcnt"], 2026, "A",
                     new[0]["GameSeasonCode"], 302)]


def test_writer_sql_sets_only_starter_columns():
    sql = sw._STARTER_SQL
    set_clause = sql.split("SET", 1)[1].split("WHERE", 1)[0]
    assert set_clause.count("=") == 2 and "home_starter_id" in set_clause and "away_starter_id" in set_clause
    for banned in ("score", "winning", "losing", "closer", "mvp", "game_date", "venue", "present_status"):
        assert banned not in set_clause
    assert "COALESCE(home_score, 0) = 0" in sql and "delay_kind IS DISTINCT FROM '保留'" in sql


def _violations(fn) -> list[str]:
    """不變量：對 fixture 每一場（依取得順序的每個前綴），已有終局／保留／比分的組不得產生任何寫入或修訂。"""
    bad = []
    by_game: dict[tuple, list[dict]] = {}
    for r in ROWS:
        by_game.setdefault((r["kind_code"], r["game_sno"]), []).append(r["raw_payload"])
    for (kind, sno), group in by_game.items():
        for i in range(1, len(group) + 1):
            seen = group[:i]
            started = any(str(p["GameResult"]) in ("0", "2") or p["HomeScore"] or p["VisitingScore"] for p in seen)
            if started and fn(seen, {f"2026-{kind}-{sno}"}) != ([], []):
                bad.append(f"2026-{kind}-{sno}#{i}")
    return bad


def test_invariant_holds_on_all_real_payloads():
    assert _violations(sw.starter_rows) == []


def test_invariant_mutations_are_caught(monkeypatch):
    """變異檢驗（PLAN 1 §4.2 第 6 點）：三種放寬都必須讓不變量檢查紅。"""
    from cpbl.ingest.cpbl_site import _primary_entry

    def like_upsert_games(games, keys):          # 換回 upsert_games 的選擇（不看開打與否）
        rows = []
        for g in games:
            p = _primary_entry([g])
            rows.append((p.get("HomePitcherAcnt"), p.get("VisitingPitcherAcnt")))
        return rows, list(games)
    assert _violations(like_upsert_games)

    with monkeypatch.context() as m:              # 把「保留」加回可寫集合
        m.setattr(sw, "_result", lambda e: "" if str(e.get("GameResult")) == "2" else str(e.get("GameResult")))
        assert _violations(sw.starter_rows)
    with monkeypatch.context() as m:              # 移除比分過濾
        m.setattr(sw, "_scored", lambda e: False)
        assert _violations(sw.starter_rows)



# =========================================================================== 前一天 23:00 時點

def test_fire_point_is_day_before_2300_and_follows_reschedule():
    assert sw.fire_point(tpe(10, 27, 18, 35)) == tpe(10, 26, 23, 0)
    assert sw.fire_point(tpe(10, 26, 15, 5)) == tpe(10, 25, 23, 0)
    rows = [sched("C", 7, "SCHEDULED", "2026-10-27T18:35:00")]
    assert sw.candidates(rows, tpe(10, 26, 22, 59), "AEC") == {}
    assert sw.candidates(rows, tpe(10, 26, 23, 0), "AEC") == {"2026-C-7": tpe(10, 27, 18, 35)}
    assert sw.candidates(rows, tpe(10, 27, 0, 59), "AEC") == {"2026-C-7": tpe(10, 27, 18, 35)}
    assert sw.candidates(rows, tpe(10, 27, 1, 0), "AEC") == {}, "最遲 01:00（深夜加嚴）"
    moved = [sched("C", 7, "SCHEDULED", "2026-10-28T18:35:00")]   # 延賽改期：新 S 的 F 自動成為新時點
    assert sw.candidates(moved, tpe(10, 26, 23, 5), "AEC") == {}
    assert sw.candidates(moved, tpe(10, 27, 23, 5), "AEC") == {"2026-C-7": tpe(10, 28, 18, 35)}


def test_only_scheduled_aec_games_are_targets():
    at = tpe(10, 26, 23, 10)
    rows = [sched("D", 1, "SCHEDULED", "2026-10-27T13:05:00"),
            sched("A", 2, "POSTPONED", "2026-10-27T18:35:00"),
            sched("A", 3, "START", "2026-10-27T17:05:00"),
            sched("A", 4, "", "2026-10-27T18:35:00"),
            sched("E", 5, "SCHEDULED", "not-a-date"),
            sched("E", 6, "SCHEDULED", "2026-10-27T18:35:00")]
    assert sw.candidates(rows, at, pe.EVENING_KINDS) == {"2026-E-6": tpe(10, 27, 18, 35)}


@pytest.mark.parametrize("hh,mm,inside", [(22, 59, False), (23, 0, True), (0, 59, True), (1, 0, False)])
def test_fire_hours(hh, mm, inside):
    assert sw.in_fire_hours(tpe(10, 26, hh, mm)) is inside


def test_fire_game_date():
    assert str(sw.fire_game_date(tpe(10, 26, 23, 30))) == "2026-10-27"
    assert str(sw.fire_game_date(tpe(10, 27, 0, 30))) == "2026-10-27"


def _armed(now: datetime) -> dict:
    state: dict = {"schedule": [sched("C", 7, "SCHEDULED", "2026-10-27T18:35:00")]}
    sw.refresh(state, now, sw.candidates(state["schedule"], now, "AEC"), state["schedule"])
    return state


def test_one_fetch_per_game_and_outcomes():
    t = tpe(10, 26, 23, 5)
    state = _armed(t)
    assert sw.due_kinds(state) == {"C"}
    sw.record_fetch(state, t, ["C"], (), {"2026-C-7"})
    rec = state["starter_watch"]["games"]["2026-C-7"]
    assert rec["state"] == "fetched" and sw.due_kinds(state) == set(), "每場只抓一次"
    sw.refresh(state, t + timedelta(minutes=30), sw.candidates(state["schedule"], t + timedelta(minutes=30), "AEC"),
               state["schedule"])
    assert sw.due_kinds(state) == set()
    sw.record_sync(state, t + timedelta(minutes=4), 0)
    assert rec["synced_at"]

    empty = _armed(t)
    sw.record_fetch(empty, t, ["C"], (), set())
    assert empty["starter_watch"]["games"]["2026-C-7"]["state"] == "empty"
    failed = _armed(t)
    sw.record_fetch(failed, t, ["C"], {"C"}, set())
    assert failed["starter_watch"]["games"]["2026-C-7"]["state"] == "failed"
    assert _armed(t)["starter_watch"]["games"]["2026-C-7"]["state"] == "due", "本機已有先發也照抓（可能是舊日期）"


def test_missed_after_0100_and_sync_failure():
    t = tpe(10, 26, 23, 5)
    state = _armed(t)
    sw.note_wait(state, ["C"], "www_blocked")
    sw.refresh(state, tpe(10, 27, 1, 0), {}, state["schedule"])
    rec = state["starter_watch"]["games"]["2026-C-7"]
    assert rec["state"] == "missed" and rec["wait"] == "www_blocked"
    s2 = _armed(t)
    sw.record_fetch(s2, t, ["C"], (), {"2026-C-7"})
    sw.record_sync(s2, t + timedelta(minutes=4), 68)
    assert s2["starter_watch"]["games"]["2026-C-7"]["state"] == "sync_failed"
    sw.record_sync(s2, t + timedelta(days=1), 0)
    assert s2["starter_watch"]["games"]["2026-C-7"]["synced_at"], "之後成功的同步照實記送達"


def test_notify_problems_once_with_file(tmp_path):
    sent = []
    notify = lambda t, m: sent.append((t, m)) or {"attempted": True}  # noqa: E731
    path = tmp_path / "alert.json"
    t = tpe(10, 26, 23, 5)
    state = _armed(t)
    assert sw.notify_problems(state, t, notify=notify, path=path) == [] and not path.exists()
    sw.record_fetch(state, t, ["C"], (), set())
    assert sw.notify_problems(state, t, notify=notify, path=path) == ["2026-C-7"]
    assert len(sent) == 1 and "官網先發仍空" in sent[0][1] and "10:10" in sent[0][1]
    assert json.loads(path.read_text())["games"]["2026-C-7"]["state"] == "empty"
    assert sw.notify_problems(state, t + timedelta(minutes=5), notify=notify, path=path) == []
    assert len(sent) == 1, "同一場只通知一次"
    sw.notify_problems(state, tpe(10, 27, 18, 36), notify=notify, path=path)
    assert not path.exists(), "開賽後不再列"


def test_notify_failure_is_recorded_not_raised(tmp_path):
    def boom(title, msg):
        raise OSError("osascript missing")
    t = tpe(10, 26, 23, 5)
    state = _armed(t)
    sw.record_fetch(state, t, ["C"], {"C"}, set())
    assert sw.notify_problems(state, t, notify=boom, path=tmp_path / "a.json") == ["2026-C-7"]
    assert "osascript missing" in state["starter_watch"]["notify_error"]["error"]
    assert json.loads((tmp_path / "a.json").read_text())["last_notification"]["error"]


def test_say_prefix(capsys):
    sw.say("x y")
    assert capsys.readouterr().err == "starter-watch x y\n"


def test_www_marker_card_342(caplog):
    from cpbl.ingest import _browser as b

    caplog.set_level("INFO", logger="cpbl.browser.www")
    with b.www_marker("other", "342", "2026/A/-", card="342"):
        b._note_goto(200, "2026-10-26T23:00:05+08:00")
    assert "WWW_REQ card=342 kind=other src=342 at=2026-10-26T23:00:05+08:00 game=2026/A/- status=200" in caplog.text
    with pytest.raises(ValueError):
        b.www_marker("other", "342", "2026/A/-").__enter__()   # 預設 card=293 仍只收 E／C、src 292／293
    with pytest.raises(ValueError):
        b.www_marker("other", "292", "2026/A/-", card="342").__enter__()


# =========================================================================== 晚間鏈接線

def raw_game(kind, sno, status, starts):
    return {"GameId": f"2026-{kind}-{sno}", "KindCode": kind, "GameSno": sno, "GameStatus": status,
            "PreExeDate": starts, "Visiting": {"Team": {"Code": "ACN011"}}, "Home": {"Team": {"Code": "AAA011"}},
            "Field": {"Abbe": "大巨蛋"}}


def local_for(games):
    return {g.key: pe.LocalGame(2026, g.kind_code, g.game_sno, g.game_date, g.away_code, g.home_code, g.venue, False)
            for g in games}


def test_flag_off_keeps_baseline():
    games = pe.parse_stats_games([raw_game("C", 7, "SCHEDULED", "2026-10-27T18:35:00")], 2026)
    state = pe.empty_state()
    out = pe.plan(state, tpe(10, 26, 23, 5), probe=lambda: games, load_local=lambda: local_for(games))
    assert out == ("idle", "no_events") and state["starter_watch"] == {}


def test_2300_fetch_ignores_a_gate_but_respects_challenge_stop(monkeypatch):
    """23:00 時今晚 A 仍有未終局場（P-A-FETCH-GATE 擋既有 A 抓取）：明天 A 場照抓，且只走只寫先發路徑。"""
    monkeypatch.setenv(pe.EVENING_KINDS_ENV, "")
    games = pe.parse_stats_games([raw_game("A", 10, "START", "2026-10-26T18:35:00"),
                                  raw_game("A", 11, "SCHEDULED", "2026-10-27T18:35:00")], 2026)
    state = pe.empty_state()
    now = tpe(10, 26, 23, 2)
    out = pe.plan(state, now, probe=lambda: games, load_local=lambda: local_for(games),
                  watch_enabled=True)
    assert out == ("scrape", "starter_watch")
    assert state["a_fetch_gate"]["reason"].startswith("a_in_progress_or_pending")
    assert state["scrape_kinds"] == ["A"] and state["starter_watch"]["watch_only"] == ["A"]
    assert sw.pending_keys(state) == ["2026-A-11"]

    blocked = pe.empty_state() | {"www_blocked_at": pe._iso(now - timedelta(hours=1))}
    assert pe.plan(blocked, now, probe=lambda: games, load_local=lambda: local_for(games),
                   watch_enabled=True)[0] == "idle"
    assert blocked["starter_watch"]["games"]["2026-A-11"]["wait"] == "www_blocked"


def test_2300_shares_kind_cooldown(monkeypatch):
    monkeypatch.setenv(pe.EVENING_KINDS_ENV, "")
    games = pe.parse_stats_games([raw_game("C", 7, "SCHEDULED", "2026-10-27T18:35:00")], 2026)
    now = tpe(10, 26, 23, 0)
    state = pe.empty_state() | {"www_requests": {"C": pe._iso(now - timedelta(minutes=10))}}
    assert pe.plan(state, now, probe=lambda: games, load_local=lambda: local_for(games),
                   watch_enabled=True)[0] == "idle"
    assert state["starter_watch"]["games"]["2026-C-7"]["wait"] == "cooldown"
    assert pe.plan(state, now + timedelta(minutes=10), probe=lambda: games, load_local=lambda: local_for(games),
                   watch_enabled=True) == ("scrape", "starter_watch")


def test_gate_wakes_on_rest_day_for_tomorrows_game():
    state = pe.empty_state() | {"schedule": [sched("C", 7, "SCHEDULED", "2026-10-27T18:35:00")]}
    now = tpe(10, 26, 23, 0)
    assert pe.evening_gate(state, now, None, db_lookup=lambda night: set())[0] == "quiet", "基準：休兵日 quiet"
    assert sw.gate_kinds(state, now, pe.EVENING_KINDS) == {"C"}
    assert sw.gate_kinds(state, tpe(10, 26, 22, 55), pe.EVENING_KINDS) == set()


# =========================================================================== 審核 review-1 回歸

def _a302(result: str, date: str, with_starters: bool) -> dict:
    return next(p for p in payloads("A", 302) if p["GameResult"] == result and p["GameDate"].startswith(date)
                and bool(p["HomePitcherAcnt"]) == with_starters)


def _found(rows) -> set[str]:
    return {f"{y}-{k}-{n}" for h, a, y, k, _s, n in rows if h and a}


def test_reschedule_lifecycle_binds_starters_to_new_schedule():
    """review-1 #1：2026-A-302 真實素材（9/01 延賽改 9/30；新日期兩隊先發都換人）。舊日期已抓到先發並送達（構造：
    修訂表沒有 9/01 賽前帶先發那一版），改期後到新 F 仍要抓一次，結局看這次的目前賽前 entry，舊先發不得沿用。"""
    old_s, new_s = "2026-09-01T18:35:00", "2026-09-30T18:35:00"
    state: dict = {"schedule": [sched("A", 302, "SCHEDULED", old_s)]}
    t_old = tpe(8, 31, 23, 2)
    sw.refresh(state, t_old, sw.candidates(state["schedule"], t_old, "AEC"), state["schedule"])
    sw.record_fetch(state, t_old, ["A"], (), {"2026-A-302"})                       # 構造：舊日期 fetched
    sw.record_sync(state, t_old + timedelta(minutes=4), 0)
    postponed = _a302("1", "2026-09-01", True)
    assert (postponed["HomePitcherAcnt"], postponed["VisitingPitcherAcnt"]) == ("0000007570", "0000005151")

    state["schedule"] = [sched("A", 302, "SCHEDULED", new_s)]                      # stats 改期
    t_new = tpe(9, 29, 23, 2)
    sw.refresh(state, t_new, sw.candidates(state["schedule"], t_new, "AEC"), state["schedule"])
    rec = state["starter_watch"]["games"]["2026-A-302"]
    assert rec["state"] == "due" and rec["fire_at"] == sw._iso(tpe(9, 29, 23, 0)) and sw.due_kinds(state) == {"A"}

    # 新日期先發尚未公布：寫成空（不殘留 7570／5151），結局 empty ⇒ 通知
    rows, _ = sw.starter_rows([_a302("", "2026-09-30", False), postponed], {"2026-A-302"})
    assert rows == [(None, None, 2026, "A", postponed["GameSeasonCode"], 302)]
    sw.record_fetch(state, t_new, ["A"], (), _found(rows))
    assert rec["state"] == "empty"

    # 同一時點若官網已公布（本機 9/29 22:54 首見）：寫新先發、結局 fetched
    state2: dict = {"schedule": [sched("A", 302, "SCHEDULED", new_s)]}
    sw.refresh(state2, t_new, sw.candidates(state2["schedule"], t_new, "AEC"), state2["schedule"])
    pub = _a302("", "2026-09-30", True)
    rows, _ = sw.starter_rows([pub, postponed], {"2026-A-302"})
    assert rows == [("0000007836", "0000005604", 2026, "A", pub["GameSeasonCode"], 302)]
    sw.record_fetch(state2, t_new, ["A"], (), _found(rows))
    assert state2["starter_watch"]["games"]["2026-A-302"]["state"] == "fetched"


def test_plan_fetches_at_new_fire_even_if_local_has_old_starters(monkeypatch):
    """review-1 #1 接線：plan 不查本機 DB 先發，改期後的新 F 一定排抓取。"""
    monkeypatch.setenv(pe.EVENING_KINDS_ENV, "")
    games = pe.parse_stats_games([raw_game("A", 302, "SCHEDULED", "2026-09-30T18:35:00")], 2026)
    state = pe.empty_state()
    state["starter_watch"] = {"games": {"2026-A-302": {"key": "2026-A-302", "state": "fetched",
                                                      "fire_at": sw._iso(tpe(8, 31, 23, 0)),
                                                      "starts_at": sw._iso(tpe(9, 1, 18, 35)),
                                                      "synced_at": "2026-08-31T15:06:00+00:00"}}}
    assert pe.plan(state, tpe(9, 29, 23, 2), probe=lambda: games, load_local=lambda: local_for(games),
                   watch_enabled=True) == ("scrape", "starter_watch")


def test_pending_record_superseded_by_reschedule_during_cooldown_or_lock(monkeypatch):
    """review-1 #2：23:00 建立待抓、因冷卻（或鎖被占：plan 已寫狀態、scrape 沒跑）延後；之後 stats 顯示改到後天
    ⇒ 舊待抓記 superseded，不抓、不通知；新 S 的 F 到了再另起一筆。"""
    monkeypatch.setenv(pe.EVENING_KINDS_ENV, "")
    now = tpe(10, 26, 23, 0)
    orig = pe.parse_stats_games([raw_game("C", 7, "SCHEDULED", "2026-10-27T18:35:00")], 2026)
    moved = pe.parse_stats_games([raw_game("C", 7, "SCHEDULED", "2026-10-28T18:35:00")], 2026)
    state = pe.empty_state() | {"www_requests": {"C": pe._iso(now - timedelta(minutes=10))}}
    assert pe.plan(state, now, probe=lambda: orig, load_local=lambda: local_for(orig), watch_enabled=True)[0] == "idle"
    assert state["starter_watch"]["games"]["2026-C-7"]["state"] == "due"
    later = now + timedelta(minutes=16)                                         # 下一次 probe（15 分）看到改期
    out = pe.plan(state, later, probe=lambda: moved, load_local=lambda: local_for(moved), watch_enabled=True)
    rec = state["starter_watch"]["games"]["2026-C-7"]
    assert out[0] == "idle" and rec["state"] == "superseded" and sw.due_kinds(state) == set()

    def no_notify(title, message):
        raise AssertionError("superseded 不該通知")
    assert sw.notify_problems(state, later, notify=no_notify, path=Path("/nonexistent-dir/never.json")) == []
    out = pe.plan(state, tpe(10, 27, 23, 1), probe=lambda: moved, load_local=lambda: local_for(moved),
                  watch_enabled=True)
    assert out == ("scrape", "starter_watch") and state["starter_watch"]["games"]["2026-C-7"]["state"] == "due"

    # 鎖被占：plan 回 scrape（已寫 inflight）但 scrape 沒跑；下一次 plan 看到 POSTPONED ⇒ superseded
    state = pe.empty_state()
    assert pe.plan(state, now, probe=lambda: orig, load_local=lambda: local_for(orig), watch_enabled=True)[0] == "scrape"
    gone = pe.parse_stats_games([raw_game("C", 7, "POSTPONED", "2026-10-27T18:35:00")], 2026)
    pe.plan(state, later, probe=lambda: gone, load_local=lambda: local_for(gone), watch_enabled=True)
    assert state["starter_watch"]["games"]["2026-C-7"]["state"] == "superseded"
    assert state["starter_watch"]["inflight"] == []


def test_main_plan_wakes_on_rest_day_even_if_local_has_both_starters(tmp_path, monkeypatch, capsys):
    """review-2：真的 ``main(['plan'])`` 喚醒路徑。今晚休兵、狀態檔沒有明日賽程（從未 probe 到），本機 games 明日 A 場
    兩隊先發都已有值（可能是改期前的舊先發）⇒ 外層退路仍要醒、進內層、23:00 照抓一次（⛔ 不得因已有先發回 quiet）。

    本機 DB 以記憶體替身代：只有一場 2026-A-302（game_date 2026-09-30、兩隊先發皆非空）。替身照 SQL 的 WHERE 回答：
    查詢若要求「先發有空值」就沒有列（這場兩隊都有）。stats 回明日 A-302 SCHEDULED。"""
    from contextlib import contextmanager

    from cpbl import db as cdb

    now = tpe(9, 29, 23, 2)
    queries: list[str] = []

    class Cur:
        def __init__(self, rows):
            self.rows = rows

        def fetchall(self):
            return self.rows

    class Conn:
        def execute(self, sql, params=()):
            queries.append(sql)
            if "FROM cpbl.games" in sql and "game_date = %s" in sql:
                kinds, day = params[0], params[1]
                has_null_filter = "home_starter_id IS NULL OR away_starter_id IS NULL" in sql
                hit = "A" in kinds and str(day) == "2026-09-30" and not has_null_filter
                return Cur([("A",)] if hit else [])
            return Cur([])

    @contextmanager
    def fake_conn():
        yield Conn()

    stats = pe.parse_stats_games([raw_game("A", 302, "SCHEDULED", "2026-09-30T18:35:00")], 2026)
    monkeypatch.setattr(cdb, "conn", fake_conn)
    monkeypatch.setattr(pe, "_now", lambda: now)
    monkeypatch.setattr(pe, "stats_probe", lambda year, months, kinds=pe.EVENING_KINDS, **kw: stats)
    monkeypatch.setattr(pe, "load_local_games", lambda year, now, kinds=None: local_for(stats))
    monkeypatch.setattr(pe, "local_first_seen", lambda year, kinds=None: {})
    monkeypatch.setattr(pe, "local_www_starts", lambda year, kinds=None: {})
    monkeypatch.setattr(pe, "local_scheduled_kinds", lambda night, kinds=None: set())
    monkeypatch.setattr(pe, "publish_signals", lambda state, year, now: None)
    monkeypatch.setattr(sw, "_schedule_watch_notify", lambda title, msg: {"attempted": True})
    flag = tmp_path / "starter-watch.enabled"
    flag.write_text("", encoding="utf-8")
    for k, v in {"POSTSEASON_STATE": tmp_path / "state.json", "POSTSEASON_STATUS": tmp_path / "status.json",
                 "POSTSEASON_STARTER_WATCH_FLAG": flag, "POSTSEASON_STARTER_WATCH_ALERT": tmp_path / "a.json",
                 "POSTSEASON_STARTER_FLAG": tmp_path / "no.enabled",
                 "POSTSEASON_TODAY_SCHEDULE": tmp_path / "no-today.json", "POSTSEASON_YEAR": "2026"}.items():
        monkeypatch.setenv(k, str(v))
    monkeypatch.setenv(pe.EVENING_KINDS_ENV, "")
    assert pe.main(["plan"]) == 0
    out = capsys.readouterr().out.strip().splitlines()[-1]
    assert any("FROM cpbl.games" in q and "game_date = %s" in q for q in queries), "外層退路有查本機 games"
    assert out == "scrape", "休兵日＋本機已有先發：仍要進內層並排 23:00 抓取"
    state = pe.load_state(tmp_path / "state.json")
    assert state["starter_watch"]["games"]["2026-A-302"]["state"] == "due"
    assert state["starter_watch"]["inflight"] == ["A"]
