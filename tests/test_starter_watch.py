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


def test_writer_records_unpublished_pregame_without_touching_games():
    empty = [p for p in payloads("C", 7) if not p["HomePitcherAcnt"]][-1:]
    rows, revs = sw.starter_rows(empty, {"2026-C-7"})
    assert rows == [] and revs == empty


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


def _armed(now: datetime, have=()) -> dict:
    state: dict = {"schedule": [sched("C", 7, "SCHEDULED", "2026-10-27T18:35:00")]}
    sw.refresh(state, now, sw.candidates(state["schedule"], now, "AEC"), have)
    return state


def test_one_fetch_per_game_and_outcomes():
    t = tpe(10, 26, 23, 5)
    state = _armed(t)
    assert sw.due_kinds(state) == {"C"}
    sw.record_fetch(state, t, ["C"], (), {"2026-C-7"})
    rec = state["starter_watch"]["games"]["2026-C-7"]
    assert rec["state"] == "fetched" and sw.due_kinds(state) == set(), "每場只抓一次"
    sw.refresh(state, t + timedelta(minutes=30), sw.candidates(state["schedule"], t + timedelta(minutes=30), "AEC"), ())
    assert sw.due_kinds(state) == set()
    sw.record_sync(state, t + timedelta(minutes=4), 0)
    assert rec["synced_at"]

    empty = _armed(t)
    sw.record_fetch(empty, t, ["C"], (), set())
    assert empty["starter_watch"]["games"]["2026-C-7"]["state"] == "empty"
    failed = _armed(t)
    sw.record_fetch(failed, t, ["C"], {"C"}, set())
    assert failed["starter_watch"]["games"]["2026-C-7"]["state"] == "failed"
    already = _armed(t, have={"2026-C-7"})
    assert already["starter_watch"]["games"]["2026-C-7"]["state"] == "already" and sw.due_kinds(already) == set()


def test_missed_after_0100_and_sync_failure():
    t = tpe(10, 26, 23, 5)
    state = _armed(t)
    sw.note_wait(state, ["C"], "www_blocked")
    sw.refresh(state, tpe(10, 27, 1, 0), {}, ())
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
                  watch_enabled=True, local_starters=lambda keys: set())
    assert out == ("scrape", "starter_watch")
    assert state["a_fetch_gate"]["reason"].startswith("a_in_progress_or_pending")
    assert state["scrape_kinds"] == ["A"] and state["starter_watch"]["watch_only"] == ["A"]
    assert sw.pending_keys(state) == ["2026-A-11"]

    blocked = pe.empty_state() | {"www_blocked_at": pe._iso(now - timedelta(hours=1))}
    assert pe.plan(blocked, now, probe=lambda: games, load_local=lambda: local_for(games),
                   watch_enabled=True, local_starters=lambda keys: set())[0] == "idle"
    assert blocked["starter_watch"]["games"]["2026-A-11"]["wait"] == "www_blocked"


def test_2300_shares_kind_cooldown(monkeypatch):
    monkeypatch.setenv(pe.EVENING_KINDS_ENV, "")
    games = pe.parse_stats_games([raw_game("C", 7, "SCHEDULED", "2026-10-27T18:35:00")], 2026)
    now = tpe(10, 26, 23, 0)
    state = pe.empty_state() | {"www_requests": {"C": pe._iso(now - timedelta(minutes=10))}}
    assert pe.plan(state, now, probe=lambda: games, load_local=lambda: local_for(games),
                   watch_enabled=True, local_starters=lambda keys: set())[0] == "idle"
    assert state["starter_watch"]["games"]["2026-C-7"]["wait"] == "cooldown"
    assert pe.plan(state, now + timedelta(minutes=10), probe=lambda: games, load_local=lambda: local_for(games),
                   watch_enabled=True, local_starters=lambda keys: set()) == ("scrape", "starter_watch")


def test_gate_wakes_on_rest_day_for_tomorrows_game():
    state = pe.empty_state() | {"schedule": [sched("C", 7, "SCHEDULED", "2026-10-27T18:35:00")]}
    now = tpe(10, 26, 23, 0)
    assert pe.evening_gate(state, now, None, db_lookup=lambda night: set())[0] == "quiet", "基準：休兵日 quiet"
    assert sw.gate_kinds(state, now, pe.EVENING_KINDS) == {"C"}
    assert sw.gate_kinds(state, tpe(10, 26, 22, 55), pe.EVENING_KINDS) == set()
