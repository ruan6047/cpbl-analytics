"""#268 WP3 事件觸發晚間鏈：偵測／節奏／時點語意的純函式測試（合成 fixture，不連網、不碰 DB）。

stats 回應與本機列都是 SYNTHETIC，形狀取自 live_game_worker／lineup_announcements 已使用的
stats 賽程 API 欄位（GameId／KindCode／GameSno／GameStatus／PreExeDate／Visiting.Team.Code／
Field.Abbe）。⛔ 不是公站或正式資料證據。
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from cpbl.ingest import postseason_evening as pe

TPE = ZoneInfo("Asia/Taipei")


def tpe(y, m, d, hh, mm) -> datetime:
    return datetime(y, m, d, hh, mm, tzinfo=TPE)


def raw_game(kind: str, sno: int, status: str, starts: str, away="ADD011", home="ACN011",
             venue="洲際") -> dict:
    return {"GameId": f"2026-{kind}-{sno}", "KindCode": kind, "GameSno": sno,
            "GameStatus": status, "PreExeDate": starts,
            "Visiting": {"Team": {"Code": away}}, "Home": {"Team": {"Code": home}},
            "Field": {"Abbe": venue}}


E4_FINISHED = pe.parse_stats_games([raw_game("E", 4, "FINISHED", "2026-10-12T18:35:00")], 2026)
E4_LOCAL_PENDING = {"2026-E-4": pe.LocalGame(2026, "E", 4, "2026-10-12", "ADD011", "ACN011",
                                             "洲際", False)}
E4_LOCAL_DONE = {"2026-E-4": pe.LocalGame(2026, "E", 4, "2026-10-12", "ADD011", "ACN011",
                                          "洲際", True)}


# —— stats 解析與唯讀探針 ——

def test_parse_reads_identity_teams_and_venue_and_skips_mismatched_rows():
    rows = [raw_game("C", 1, "SCHEDULED", "2026-10-17T17:05:00", away="ACN011", home="AAA011",
                     venue="大巨蛋"),
            {**raw_game("C", 2, "SCHEDULED", "2026-10-18T17:05:00"), "GameSno": 9},  # 身分不一致
            raw_game("A", 300, "FINISHED", "2026-10-01T18:35:00")]                   # 非季後
    games = pe.parse_stats_games(rows, 2026)
    assert [(g.kind_code, g.game_sno, g.away_code, g.home_code, g.venue, g.game_date)
            for g in games] == [("C", 1, "ACN011", "AAA011", "大巨蛋", "2026-10-17")]


def test_stats_probe_is_get_only_and_fails_closed():
    calls = []

    def fetch(path, params):
        calls.append((path, params))
        return {"Data": {"Games": [raw_game(params["kindCode"], 1, "SCHEDULED", "2026-10-17T17:05:00")]}}

    games = pe.stats_probe(2026, [10, 11], fetch=fetch)
    assert {(p["kindCode"], p["month"]) for _, p in calls} == {("E", "10"), ("E", "11"), ("C", "10"), ("C", "11")}
    assert all(path == pe.SCHEDULE_PATH for path, _ in calls)
    assert {g.key for g in games} == {"2026-E-1", "2026-C-1"}

    def broken(path, params):
        raise TimeoutError("stats timeout")

    with pytest.raises(pe.ProbeUnavailable):
        pe.stats_probe(2026, [10], fetch=broken)
    with pytest.raises(pe.ProbeUnavailable):
        pe.stats_probe(2026, [10], fetch=lambda p, q: {"Data": {"Games": {"not": "a list"}}})


# —— 三類事件 ——

def test_detect_three_event_types_and_nothing_when_in_sync():
    stats = pe.parse_stats_games([
        raw_game("E", 4, "FINISHED", "2026-10-12T18:35:00"),
        raw_game("C", 1, "SCHEDULED", "2026-10-17T17:05:00", away="ACN011", home="AAA011"),
        raw_game("C", 2, "SCHEDULED", "2026-10-19T17:05:00", away="ACN011", home="AAA011",
                 venue="大巨蛋"),
    ], 2026)
    local = {**E4_LOCAL_PENDING,
             "2026-C-2": pe.LocalGame(2026, "C", 2, "2026-10-18", "ACN011", "AAA011", "大巨蛋", False)}
    events = {(e.type, e.key, e.detail) for e in pe.detect_events(stats, local)}
    assert events == {("final_not_ingested", "2026-E-4", ()),
                      ("new_game", "2026-C-1", ()),
                      ("schedule_changed", "2026-C-2", ("date",))}
    assert pe.detect_events(E4_FINISHED, E4_LOCAL_DONE) == []


def test_venue_change_is_an_official_schedule_change_per_approved_plan():
    """核定規劃：日期、主客或球場變動都是事件。缺值不比、空白不算差異。"""
    moved = pe.parse_stats_games([raw_game("C", 3, "SCHEDULED", "2026-10-20T18:35:00",
                                           away="AAA011", home="ACN011", venue="洲際")], 2026)
    local = {"2026-C-3": pe.LocalGame(2026, "C", 3, "2026-10-20", "AAA011", "ACN011", "大巨蛋", False)}
    assert [(e.type, e.detail) for e in pe.detect_events(moved, local)] == [("schedule_changed", ("venue",))]
    same = {"2026-C-3": pe.LocalGame(2026, "C", 3, "2026-10-20", "AAA011", "ACN011", " 洲際 ", False)}
    assert pe.detect_events(moved, same) == []
    unknown = {"2026-C-3": pe.LocalGame(2026, "C", 3, "2026-10-20", "AAA011", "ACN011", None, False)}
    assert pe.detect_events(moved, unknown) == []


# —— 無事件不連 www ——

def test_no_event_never_returns_scrape():
    state = pe.empty_state()
    action, reason = pe.plan(state, tpe(2026, 10, 13, 21, 0), probe=lambda: E4_FINISHED,
                             load_local=lambda: E4_LOCAL_DONE)
    assert (action, reason) == ("idle", "no_events")


def test_plan_path_never_imports_the_www_scraper():
    """plan 階段不得載入 run_refresh_recent／Playwright（子行程乾淨 import 證明）。"""
    code = ("import sys, cpbl.ingest.postseason_evening as m; "
            "print(json.dumps(sorted(x for x in sys.modules if x in "
            "('cpbl.ingest.run_refresh_recent', 'cpbl.ingest.cpbl_site', 'playwright'))))")
    out = subprocess.run([sys.executable, "-c", "import json; " + code],
                         capture_output=True, text=True, check=True)
    assert json.loads(out.stdout) == []


def test_probe_unavailable_never_scrapes_even_with_open_events():
    state = pe.empty_state()
    pe.plan(state, tpe(2026, 10, 12, 21, 0), probe=lambda: E4_FINISHED, load_local=lambda: E4_LOCAL_PENDING)

    def down():
        raise pe.ProbeUnavailable("timeout")

    now = tpe(2026, 10, 12, 21, 30)
    for i in range(3):
        action, reason = pe.plan(state, now + timedelta(minutes=5 * i), probe=down,
                                 load_local=lambda: E4_LOCAL_PENDING)
        assert (action, reason) == ("idle", "probe_unavailable")
    assert state["probe_status"] == "probe_unavailable"


# —— 跨日：沒有鐘點截止 ——

def test_cross_midnight_events_keep_being_processed_with_real_timestamps():
    """23:45 首見 → 00:30 → 02:10 第三次 www 才出現 final；T1–T3 照實記錄跨日時刻。"""
    state = pe.empty_state()
    t_first = tpe(2026, 10, 12, 23, 45)
    assert pe.plan(state, t_first, probe=lambda: E4_FINISHED,
                   load_local=lambda: E4_LOCAL_PENDING)[0] == "scrape"
    pe.record_scrape(state, t_first, errors=[], changed=False, stats_has_c=False, local_c_rows=0)

    t_second = tpe(2026, 10, 13, 0, 30)
    assert pe.probe_due(state, t_second) == (True, "hot_open_events")
    assert pe.plan(state, t_second, probe=lambda: E4_FINISHED,
                   load_local=lambda: E4_LOCAL_PENDING)[0] == "scrape"
    pe.record_scrape(state, t_second, errors=[], changed=False, stats_has_c=False, local_c_rows=0)

    t_third = tpe(2026, 10, 13, 2, 10)
    assert pe.plan(state, t_third, probe=lambda: E4_FINISHED,
                   load_local=lambda: E4_LOCAL_PENDING)[0] == "scrape"
    assert pe.record_scrape(state, t_third, errors=[], changed=True, stats_has_c=False,
                            local_c_rows=0) == "changed"
    pe.apply_detection(state, pe.detect_events(E4_FINISHED, E4_LOCAL_DONE), t_third,
                       {"2026-E-4": "2026-10-12T18:09:00+00:00"}, resolved_by_chain=True)
    assert pe.record_sync(state, tpe(2026, 10, 13, 2, 25), 0) == "synced"

    (row,) = pe.timeline(state)
    assert row["state"] == "synced" and row["www_attempts"] == 3
    assert datetime.fromisoformat(row["t1_stats_first_seen"]).astimezone(TPE) == t_first
    assert datetime.fromisoformat(row["t3_synced"]).astimezone(TPE) == tpe(2026, 10, 13, 2, 25)
    assert row["game_date"] == "2026-10-12", "歸屬賽事日，但時點不改寫成 10/12"
    assert row["t4_user_visible"] is None
    assert state["pending_sync"] is False


def test_max_three_www_attempts_then_unreached_not_retried():
    state = pe.empty_state()
    t = tpe(2026, 10, 12, 22, 0)
    for i in range(3):
        now = t + timedelta(minutes=25 * i)
        assert pe.plan(state, now, probe=lambda: E4_FINISHED, load_local=lambda: E4_LOCAL_PENDING)[0] == "scrape"
        pe.record_scrape(state, now, errors=[], changed=False, stats_has_c=False, local_c_rows=0)
        pe.apply_detection(state, pe.detect_events(E4_FINISHED, E4_LOCAL_PENDING), now)
    later = t + timedelta(hours=3)
    assert pe.plan(state, later, probe=lambda: E4_FINISHED, load_local=lambda: E4_LOCAL_PENDING)[0] == "idle"
    (row,) = pe.timeline(state)
    assert (row["state"], row["reason"]) == ("unreached", "www_no_final_after_max_attempts")


def test_resolved_by_next_morning_daily_run_is_unreached_not_same_night():
    """本鏈試過但沒拿到 final，隔日 10:10 才補上 → 記未達，不得冒稱同晚達成。"""
    state = pe.empty_state()
    t = tpe(2026, 10, 12, 23, 0)
    pe.plan(state, t, probe=lambda: E4_FINISHED, load_local=lambda: E4_LOCAL_PENDING)
    pe.record_scrape(state, t, errors=[], changed=False, stats_has_c=False, local_c_rows=0)
    pe.plan(state, tpe(2026, 10, 13, 10, 40), probe=lambda: E4_FINISHED, load_local=lambda: E4_LOCAL_DONE)
    (row,) = pe.timeline(state)
    assert (row["state"], row["reason"]) == ("unreached", "resolved_outside_evening_chain")
    assert row["t3_synced"] is None


def test_www_cooldown_is_twenty_minutes():
    state = pe.empty_state()
    t = tpe(2026, 10, 12, 22, 0)
    pe.plan(state, t, probe=lambda: E4_FINISHED, load_local=lambda: E4_LOCAL_PENDING)
    pe.record_scrape(state, t, errors=[], changed=False, stats_has_c=False, local_c_rows=0)
    assert pe.www_decision(state, t + timedelta(minutes=10)) == (False, "cooldown_or_exhausted")
    assert pe.www_decision(state, t + timedelta(minutes=20)) == (True, "event")


def test_two_challenge_failures_stop_www_for_the_night_and_release_next_noon():
    state = pe.empty_state()
    t = tpe(2026, 10, 12, 22, 0)
    pe.plan(state, t, probe=lambda: E4_FINISHED, load_local=lambda: E4_LOCAL_PENDING)
    err = [{"kind": "E", "error": "POST /schedule/getgamedatas 重試後仍失敗（status=428，反爬節流？）"}]
    assert pe.record_scrape(state, t, errors=err, changed=False, stats_has_c=False, local_c_rows=0) == "failed"
    assert state["www_blocked_at"] is None
    t2 = t + timedelta(minutes=21)
    pe.record_scrape(state, t2, errors=err, changed=False, stats_has_c=False, local_c_rows=0)
    assert state["www_blocked_at"] is not None
    assert pe.www_decision(state, tpe(2026, 10, 13, 1, 0)) == (False, "blocked")
    assert pe.www_blocked(state, tpe(2026, 10, 13, 11, 59)) is True
    assert pe.www_blocked(state, tpe(2026, 10, 13, 12, 0)) is False


def test_yields_to_the_daily_run_without_cutting_the_evening():
    state = pe.empty_state()
    pe.plan(state, tpe(2026, 10, 13, 9, 0), probe=lambda: E4_FINISHED, load_local=lambda: E4_LOCAL_PENDING)
    assert pe.www_decision(state, tpe(2026, 10, 13, 10, 0)) == (False, "yield_to_daily")
    assert pe.www_decision(state, tpe(2026, 10, 13, 10, 20)) == (True, "event")
    # 深夜沒有任何鐘點截止
    for hh in (23, 0, 1, 2, 3, 4):
        assert pe.in_daily_guard(tpe(2026, 10, 13, hh, 30)) is False


def test_game_day_cadence_goes_hot_ninety_minutes_after_start():
    state = pe.empty_state()
    c1 = pe.parse_stats_games([raw_game("C", 1, "SCHEDULED", "2026-10-17T17:05:00",
                                        away="ACN011", home="AAA011", venue="大巨蛋")], 2026)
    local = {"2026-C-1": pe.LocalGame(2026, "C", 1, "2026-10-17", "ACN011", "AAA011", "大巨蛋", False)}
    pe.plan(state, tpe(2026, 10, 17, 17, 0), probe=lambda: c1, load_local=lambda: local)
    assert pe.probe_due(state, tpe(2026, 10, 17, 17, 10)) == (False, "idle")
    assert pe.probe_due(state, tpe(2026, 10, 17, 17, 20)) == (True, "idle")
    assert pe.probe_due(state, tpe(2026, 10, 17, 18, 40)) == (True, "hot_game_day")
    # 23:59、00:10 都照樣 hot（場次仍未 FINISHED 就繼續）
    assert pe.probe_due(state, tpe(2026, 10, 17, 23, 59))[0] is True


def test_sync_failure_halts_until_a_human_clears_it():
    state = pe.empty_state()
    state["pending_sync"] = True
    assert pe.record_sync(state, tpe(2026, 10, 12, 23, 0), 67) == "halted"
    action, reason = pe.plan(state, tpe(2026, 10, 12, 23, 5), probe=lambda: E4_FINISHED,
                             load_local=lambda: E4_LOCAL_PENDING)
    assert (action, reason) == ("halted", "sync_exit_67")


def test_reconcile_mismatch_stops_only_tonight_and_keeps_pending():
    state = pe.empty_state()
    state["pending_sync"] = True
    t = tpe(2026, 10, 12, 23, 30)
    assert pe.record_sync(state, t, 68) == "blocked"
    assert state["halted"] is None and state["pending_sync"] is True
    assert pe.plan(state, tpe(2026, 10, 13, 1, 0), probe=lambda: E4_FINISHED,
                   load_local=lambda: E4_LOCAL_DONE) == ("idle", "sync_blocked_tonight")
    assert pe.plan(state, tpe(2026, 10, 13, 12, 5), probe=lambda: E4_FINISHED,
                   load_local=lambda: E4_LOCAL_DONE)[0] == "sync"


def test_pending_sync_is_synced_without_touching_www():
    state = pe.empty_state()
    state["pending_sync"] = True
    action, _ = pe.plan(state, tpe(2026, 10, 12, 23, 0), probe=lambda: E4_FINISHED,
                        load_local=lambda: E4_LOCAL_DONE)
    assert action == "sync"


def test_c_rows_still_zero_after_successful_www_stops_only_that_item():
    state = pe.empty_state()
    c1 = pe.parse_stats_games([raw_game("C", 1, "SCHEDULED", "2026-10-17T17:05:00",
                                        away="ACN011", home="AAA011")], 2026)
    t = tpe(2026, 10, 13, 20, 0)
    assert pe.plan(state, t, probe=lambda: c1, load_local=dict)[0] == "scrape"
    assert pe.record_scrape(state, t, errors=[], changed=False, stats_has_c=True, local_c_rows=0) == "unchanged"
    assert state["halted"] is None, "只停該項，不停整條鏈"
    assert state["needs_owner_decision"]["reason"] == "c_rows_still_zero_after_www_success"
    (row,) = pe.timeline(state)
    assert row["state"] == "unreached"
    assert pe.plan(state, t + timedelta(hours=1), probe=lambda: c1, load_local=dict)[0] == "idle"


# —— #268 D1：官方異動訊號（cpbl.official_change_signals 的應開啟集合；寫入由隔離 PG 測試驗）——

def _sig(rows):
    return [(r["kind_code"], r["game_sno"], r["field"], r["official_value"]) for r in rows]


def test_detection_carries_official_values_and_only_schedule_changes_become_signals():
    stats = pe.parse_stats_games([
        raw_game("E", 4, "FINISHED", "2026-10-12T18:35:00"),
        raw_game("C", 1, "SCHEDULED", "2026-10-17T17:05:00", away="ACN011", home="AAA011", venue="大巨蛋"),
        raw_game("C", 2, "SCHEDULED", "2026-10-19T17:05:00", away="AAA011", home="ACN011", venue="洲際"),
    ], 2026)
    local = {**E4_LOCAL_PENDING,
             "2026-C-2": pe.LocalGame(2026, "C", 2, "2026-10-18", "ACN011", "AAA011", "大巨蛋", False)}
    state = pe.empty_state()
    pe.apply_detection(state, pe.detect_events(stats, local), tpe(2026, 10, 13, 20, 0))
    # E4 完賽未入庫屬完賽軸（coverage 已處理），不進異動訊號。
    assert _sig(pe.signal_rows(state)) == [
        ("C", 1, "game", "2026-10-17T17:05:00"),
        ("C", 2, "date", "2026-10-19"),
        ("C", 2, "teams", "AAA011@ACN011"),
        ("C", 2, "venue", "洲際")]
    assert state["signals_dirty"] is True


def test_signal_stays_open_until_sync_reconciles_then_resolves():
    """本鏈抓進本機（ingested）但同步對帳未通過：訊號維持開啟；68 對帳不等仍開啟；synced 才解決。"""
    c1 = pe.parse_stats_games([raw_game("C", 1, "SCHEDULED", "2026-10-17T17:05:00",
                                        away="ACN011", home="AAA011", venue="大巨蛋")], 2026)
    c1_local = {"2026-C-1": pe.LocalGame(2026, "C", 1, "2026-10-17", "ACN011", "AAA011", "大巨蛋", False)}
    state = pe.empty_state()
    t = tpe(2026, 10, 13, 23, 50)
    assert pe.plan(state, t, probe=lambda: c1, load_local=dict)[0] == "scrape"
    assert _sig(pe.signal_rows(state)) == [("C", 1, "game", "2026-10-17T17:05:00")]

    pe.record_scrape(state, t, errors=[], changed=True, stats_has_c=True, local_c_rows=1)
    pe.apply_detection(state, pe.detect_events(c1, c1_local), t, resolved_by_chain=True)
    assert _sig(pe.signal_rows(state)) == [("C", 1, "game", "2026-10-17T17:05:00")], "正式站尚未同步"

    assert pe.record_sync(state, tpe(2026, 10, 14, 0, 10), 68) == "blocked"
    assert len(pe.signal_rows(state)) == 1, "對帳不等：仍待更新"
    state["sync_blocked_at"] = None
    assert pe.record_sync(state, tpe(2026, 10, 14, 0, 40), 0) == "synced"
    assert pe.signal_rows(state) == [] and state["signals_dirty"] is True


def test_unreached_change_stays_open_while_detected_and_resolves_when_another_path_lands_it():
    """www 次數用盡（未達）但官方異動仍在：頁面必須仍說待更新；隔日由其他路徑補上 → 解決（仍記未達）。"""
    moved = pe.parse_stats_games([raw_game("C", 3, "SCHEDULED", "2026-10-21T18:35:00",
                                           away="AAA011", home="ACN011", venue="大巨蛋")], 2026)
    stale = {"2026-C-3": pe.LocalGame(2026, "C", 3, "2026-10-20", "AAA011", "ACN011", "大巨蛋", False)}
    fixed = {"2026-C-3": pe.LocalGame(2026, "C", 3, "2026-10-21", "AAA011", "ACN011", "大巨蛋", False)}
    state = pe.empty_state()
    t = tpe(2026, 10, 19, 22, 0)
    for i in range(3):
        now = t + timedelta(minutes=25 * i)
        pe.plan(state, now, probe=lambda: moved, load_local=lambda: stale)
        pe.record_scrape(state, now, errors=[], changed=False, stats_has_c=True, local_c_rows=3)
        pe.apply_detection(state, pe.detect_events(moved, stale), now)
    assert pe.timeline(state)[0]["state"] == "unreached"
    pe.plan(state, t + timedelta(hours=3), probe=lambda: moved, load_local=lambda: stale)
    assert _sig(pe.signal_rows(state)) == [("C", 3, "date", "2026-10-21")]

    pe.plan(state, tpe(2026, 10, 20, 10, 40), probe=lambda: moved, load_local=lambda: fixed)
    assert pe.signal_rows(state) == []
    assert pe.timeline(state)[0]["state"] == "unreached", "解決訊號不等於同晚達成"


def test_failed_probe_keeps_the_last_known_signals():
    c1 = pe.parse_stats_games([raw_game("C", 1, "SCHEDULED", "2026-10-17T17:05:00")], 2026)
    state = pe.empty_state()
    pe.plan(state, tpe(2026, 10, 13, 20, 0), probe=lambda: c1, load_local=dict)

    def down():
        raise pe.ProbeUnavailable("timeout")

    state["signals_dirty"] = False
    pe.plan(state, tpe(2026, 10, 13, 20, 30), probe=down, load_local=dict)
    assert len(pe.signal_rows(state)) == 1 and state["signals_dirty"] is False


def test_publish_signals_failure_is_recorded_not_swallowed(monkeypatch):
    import cpbl.db

    def broken():
        raise RuntimeError("relation cpbl.official_change_signals does not exist")

    monkeypatch.setattr(cpbl.db, "conn", broken)
    state = {**pe.empty_state(), "signals_dirty": True}
    pe.publish_signals(state, 2026, tpe(2026, 10, 13, 20, 0))
    assert state["signals_dirty"] is True and state["signals_error"]["error"] == "RuntimeError"
    clean = pe.empty_state()
    pe.publish_signals(clean, 2026, tpe(2026, 10, 13, 20, 0))   # 不 dirty：完全不連 DB
    assert clean["signals_error"] is None


# —— #268 B1：異動訊號表同步到正式站（需求方裁定 6142744045）——

def _fake_signal_db(monkeypatch, changed: int) -> list:
    """假 conn／write_signals：記下寫出的集合，回傳指定的「實際變動列數」。零 DB。"""
    import contextlib

    import cpbl.change_signals
    import cpbl.db

    written = []

    class _Conn:
        def cursor(self):
            return object()

    monkeypatch.setattr(cpbl.db, "conn", lambda: contextlib.nullcontext(_Conn()))
    monkeypatch.setattr(cpbl.change_signals, "write_signals",
                        lambda cur, year, rows, now: written.append(list(rows)) or changed)
    return written


def test_publish_marks_prod_stale_only_when_the_local_table_really_changed(monkeypatch):
    _fake_signal_db(monkeypatch, changed=0)
    same = {**pe.empty_state(), "signals_dirty": True}
    pe.publish_signals(same, 2026, tpe(2026, 10, 13, 20, 0))
    assert same["signals_dirty"] is False and same["signals_unsynced"] is False, "重寫同一集合不觸發同步"

    _fake_signal_db(monkeypatch, changed=1)
    moved = {**pe.empty_state(), "signals_dirty": True}
    pe.publish_signals(moved, 2026, tpe(2026, 10, 13, 20, 0))
    assert moved["signals_unsynced"] is True


def test_signal_only_change_syncs_when_www_is_blocked_and_never_scrapes():
    """www 被挑戰擋下（失敗情境）但訊號表已變：仍走一次同步（限定路徑），⛔ 不連 www。"""
    state = pe.empty_state()
    t = tpe(2026, 10, 19, 22, 0)
    moved = pe.parse_stats_games([raw_game("C", 3, "SCHEDULED", "2026-10-21T18:35:00",
                                           away="AAA011", home="ACN011", venue="大巨蛋")], 2026)
    stale = {"2026-C-3": pe.LocalGame(2026, "C", 3, "2026-10-20", "AAA011", "ACN011", "大巨蛋", False)}
    pe.plan(state, t, probe=lambda: moved, load_local=lambda: stale)
    state["www_blocked_at"] = pe._iso(t)
    assert pe.plan(state, t + timedelta(minutes=5), probe=lambda: moved,
                   load_local=lambda: stale) == ("idle", "blocked"), "訊號已同步過：照舊閒置"
    state["signals_unsynced"] = True
    assert pe.plan(state, t + timedelta(minutes=10), probe=lambda: moved,
                   load_local=lambda: stale) == ("sync", "signals_only")


def test_signal_only_sync_also_covers_probe_failure_and_no_event_wakes():
    def down():
        raise pe.ProbeUnavailable("timeout")

    state = {**pe.empty_state(), "signals_unsynced": True}
    assert pe.plan(state, tpe(2026, 10, 13, 23, 50), probe=down, load_local=dict) == ("sync", "signals_only")
    quiet = {**pe.empty_state(), "signals_unsynced": True}
    assert pe.plan(quiet, tpe(2026, 10, 14, 0, 20), probe=lambda: E4_FINISHED,
                   load_local=lambda: E4_LOCAL_DONE) == ("sync", "signals_only"), "跨午夜照常，無鐘點截止"


def test_signal_only_sync_respects_halt_tonight_stop_and_the_daily_yield():
    base = {**pe.empty_state(), "signals_unsynced": True}
    halted = {**base, "halted": {"at": "x", "reason": "sync_exit_67"}}
    assert pe.plan(halted, tpe(2026, 10, 13, 22, 0), probe=lambda: E4_FINISHED,
                   load_local=lambda: E4_LOCAL_DONE)[0] == "halted"
    blocked = {**base}
    assert pe.record_sync(blocked, tpe(2026, 10, 13, 22, 0), 68) == "blocked"
    assert blocked["signals_unsynced"] is True, "對帳不等不算已同步"
    assert pe.plan(blocked, tpe(2026, 10, 13, 23, 0), probe=lambda: E4_FINISHED,
                   load_local=lambda: E4_LOCAL_DONE) == ("idle", "sync_blocked_tonight")
    assert pe.signals_sync_due(base, tpe(2026, 10, 14, 10, 0)) is False, "讓位 10:10"
    assert pe.signals_sync_due(base, tpe(2026, 10, 14, 10, 20)) is True


def test_resolution_after_reconcile_reaches_prod_on_the_next_signal_only_sync(monkeypatch):
    """順序照裁定 D1：同步對帳通過 → 才寫 resolved_at（本機）→ 本機表變了 → 下一次僅訊號同步把解決送到正式站。"""
    c1 = pe.parse_stats_games([raw_game("C", 1, "SCHEDULED", "2026-10-17T17:05:00",
                                        away="ACN011", home="AAA011", venue="大巨蛋")], 2026)
    c1_local = {"2026-C-1": pe.LocalGame(2026, "C", 1, "2026-10-17", "ACN011", "AAA011", "大巨蛋", False)}
    state = pe.empty_state()
    t = tpe(2026, 10, 13, 23, 50)
    pe.plan(state, t, probe=lambda: c1, load_local=dict)
    pe.record_scrape(state, t, errors=[], changed=True, stats_has_c=True, local_c_rows=1)
    pe.apply_detection(state, pe.detect_events(c1, c1_local), t, resolved_by_chain=True)
    state["signals_unsynced"] = True   # scrape 那次 publish 寫過訊號（開啟中）

    assert pe.record_sync(state, tpe(2026, 10, 14, 0, 5), 0) == "synced"
    assert state["signals_unsynced"] is False, "這次同步已帶上當下的（仍開啟的）訊號"
    written = _fake_signal_db(monkeypatch, changed=1)   # 解決 C1 那一列
    pe.publish_signals(state, 2026, tpe(2026, 10, 14, 0, 5))
    assert written == [[]] and state["signals_unsynced"] is True
    assert pe.plan(state, tpe(2026, 10, 14, 0, 10), probe=lambda: c1,
                   load_local=lambda: c1_local) == ("sync", "signals_only")
    assert pe.record_sync(state, tpe(2026, 10, 14, 0, 15), 0) == "synced"
    _fake_signal_db(monkeypatch, changed=0)
    pe.publish_signals(state, 2026, tpe(2026, 10, 14, 0, 15))
    assert state["signals_unsynced"] is False
    assert pe.plan(state, tpe(2026, 10, 14, 0, 20), probe=lambda: c1,
                   load_local=lambda: c1_local)[0] == "idle", "收斂：不再重複同步"


def test_cli_help_has_no_side_effects():
    out = subprocess.run([sys.executable, "-m", "cpbl.ingest.postseason_evening", "--help"],
                         capture_output=True, text=True, check=False)
    assert out.returncode == 0 and "plan" in out.stdout
    bad = subprocess.run([sys.executable, "-m", "cpbl.ingest.postseason_evening", "--dry-run"],
                         capture_output=True, text=True, check=False)
    assert bad.returncode != 0
