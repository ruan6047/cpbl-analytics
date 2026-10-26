"""#342 先發觀察窗：純函式、只寫先發寫入器的不變量（真實 payload）、告警、與晚間鏈 plan 的接線。

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


# =========================================================================== 觀察窗

def test_window_is_s_minus_33h_to_s_minus_30m_and_follows_reschedule():
    s = tpe(10, 27, 18, 35)
    assert sw.window(s) == (tpe(10, 26, 9, 35), tpe(10, 27, 18, 5))
    rows = [sched("C", 7, "SCHEDULED", "2026-10-27T18:35:00")]
    assert sw.candidates(rows, tpe(10, 26, 9, 34), "AEC") == {}
    assert sw.candidates(rows, tpe(10, 26, 9, 35), "AEC") == {"2026-C-7": s}
    assert sw.candidates(rows, tpe(10, 27, 18, 5), "AEC") == {}, "S−30 起交 #292 A1"
    moved = [sched("C", 7, "SCHEDULED", "2026-10-28T18:35:00")]   # 延賽改期：新 S 自動成為新窗口
    assert sw.candidates(moved, tpe(10, 26, 10, 0), "AEC") == {}
    assert sw.candidates(moved, tpe(10, 27, 10, 0), "AEC") == {"2026-C-7": tpe(10, 28, 18, 35)}


def test_only_scheduled_aec_games_are_targets():
    at = tpe(10, 26, 12, 0)
    rows = [sched("D", 1, "SCHEDULED", "2026-10-27T13:05:00"),
            sched("A", 2, "POSTPONED", "2026-10-27T18:35:00"),
            sched("A", 3, "START", "2026-10-26T17:05:00"),
            sched("A", 4, "", "2026-10-27T18:35:00"),
            sched("E", 5, "SCHEDULED", "not-a-date"),
            sched("E", 6, "SCHEDULED", "2026-10-27T18:35:00")]
    assert sw.candidates(rows, at, pe.EVENING_KINDS) == {"2026-E-6": tpe(10, 27, 18, 35)}


@pytest.mark.parametrize("hh,mm,paused", [(0, 59, False), (1, 0, True), (9, 44, True), (9, 45, False)])
def test_night_pause(hh, mm, paused):
    assert sw.in_pause(tpe(10, 26, hh, mm)) is paused


def test_due_every_30_minutes_outside_pause_until_local_has_starters():
    state: dict = {"schedule": [sched("C", 7, "SCHEDULED", "2026-10-27T18:35:00")]}
    now = tpe(10, 26, 12, 0)
    sw.refresh(state, now, sw.candidates(state["schedule"], now, "AEC"), set())
    assert sw.due_kinds(state, now) == {"C"}
    sw.record_fetch(state, now, ["C"])
    assert sw.due_kinds(state, now + timedelta(minutes=29)) == set()
    assert sw.due_kinds(state, now + timedelta(minutes=30)) == {"C"}
    assert sw.due_kinds(state, tpe(10, 27, 2, 0)) == set(), "夜間暫停"
    sw.note_local(state, now + timedelta(minutes=31), {"2026-C-7"})
    assert sw.due_kinds(state, now + timedelta(hours=2)) == set(), "本機已有先發就停"


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


# =========================================================================== 告警

def _armed(now: datetime) -> dict:
    state: dict = {"schedule": [sched("C", 7, "SCHEDULED", "2026-10-27T18:35:00")]}
    sw.refresh(state, now, sw.candidates(state["schedule"], now, "AEC"), set())
    return state


def test_detect_gap_raises_once_and_resolves_on_delivery(tmp_path):
    sent = []
    notify = lambda t, m: sent.append((t, m)) or {"attempted": True}  # noqa: E731
    path = tmp_path / "alert.json"
    t0 = tpe(10, 26, 12, 0)
    state = _armed(t0)
    sw.record_fetch(state, t0, ["C"])
    assert sw.apply_alerts(state, t0 + timedelta(minutes=45), notify=notify, path=path)["raised"] == []
    out = sw.apply_alerts(state, t0 + timedelta(minutes=46), notify=notify, path=path)
    assert out["raised"] == ["2026-C-7"] and path.exists() and len(sent) == 1
    assert sw.apply_alerts(state, t0 + timedelta(minutes=50), notify=notify, path=path)["raised"] == []
    assert len(sent) == 1, "只在轉變時通知"
    sw.note_local(state, t0 + timedelta(minutes=55), {"2026-C-7"})
    sw.record_sync(state, t0 + timedelta(minutes=58), 0)
    out = sw.apply_alerts(state, t0 + timedelta(minutes=58), notify=notify, path=path)
    assert out["resolved"] == [("2026-C-7", "delivered")] and not path.exists()
    assert "已補上" in sent[-1][1]
    assert state["starter_watch"]["games"]["2026-C-7"]["alerts"][0]["resolution"] == "delivered"


def test_sync_late_after_15_minutes_and_failed_sync_does_not_count(tmp_path):
    t0 = tpe(10, 26, 12, 0)
    state = _armed(t0)
    sw.record_fetch(state, t0, ["C"])
    sw.note_local(state, t0, {"2026-C-7"})
    sw.record_sync(state, t0 + timedelta(minutes=4), 68)
    assert sw.alert_reasons(state, t0 + timedelta(minutes=15)) == {}
    assert sw.alert_reasons(state, t0 + timedelta(minutes=16)) == {"2026-C-7": "sync_late"}
    sw.record_sync(state, t0 + timedelta(minutes=40), 0)
    assert sw.alert_reasons(state, t0 + timedelta(minutes=41)) == {}


def test_no_alert_when_window_closes_without_publication():
    t0 = tpe(10, 27, 17, 0)
    state = _armed(t0)
    sw.record_fetch(state, t0, ["C"])
    assert sw.alert_reasons(state, tpe(10, 27, 18, 5)) == {}, "關窗仍無先發：官網可能真的沒公布"


def test_notify_failure_is_recorded_not_raised(tmp_path):
    def boom(title, msg):
        raise OSError("osascript missing")
    t0 = tpe(10, 26, 12, 0)
    state = _armed(t0)
    out = sw.apply_alerts(state, t0 + timedelta(hours=1), notify=boom, path=tmp_path / "a.json")
    assert out["raised"] == ["2026-C-7"]
    assert "osascript missing" in state["starter_watch"]["notify_error"]["error"]
    assert json.loads((tmp_path / "a.json").read_text())["notify_error"]


def test_preexisting_starters_are_not_alerted():
    t0 = tpe(10, 26, 12, 0)
    state: dict = {"schedule": [sched("C", 7, "SCHEDULED", "2026-10-27T18:35:00")]}
    sw.refresh(state, t0, sw.candidates(state["schedule"], t0, "AEC"), {"2026-C-7"})
    rec = state["starter_watch"]["games"]["2026-C-7"]
    assert rec["via"] == "preexisting" and rec["synced_at"]
    assert sw.alert_reasons(state, t0 + timedelta(hours=3)) == {}


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
    out = pe.plan(state, tpe(10, 26, 12, 0), probe=lambda: games, load_local=lambda: local_for(games))
    assert out == ("idle", "no_events") and state["starter_watch"] == {}


def test_watch_fetch_ignores_a_gate_but_respects_daily_guard_and_challenge_stop(monkeypatch):
    """A 今晚有未終局場（P-A-FETCH-GATE 擋既有 A 抓取）時，明天 A 場的觀察抓取仍照發，且只走只寫先發路徑。"""
    monkeypatch.setenv(pe.EVENING_KINDS_ENV, "")
    games = pe.parse_stats_games([raw_game("A", 10, "START", "2026-10-26T17:05:00"),
                                  raw_game("A", 11, "SCHEDULED", "2026-10-27T18:35:00")], 2026)
    state = pe.empty_state()
    now = tpe(10, 26, 19, 0)
    out = pe.plan(state, now, probe=lambda: games, load_local=lambda: local_for(games),
                  watch_enabled=True, local_starters=lambda keys: set())
    assert out == ("scrape", "starter_watch")
    assert state["a_fetch_gate"]["reason"].startswith("a_in_progress_or_pending")
    assert state["scrape_kinds"] == ["A"] and state["starter_watch"]["watch_only"] == ["A"]
    assert sw.pending_keys(state, now) == ["2026-A-11"], "今晚開打中的 A-10 不是目標"

    guard = pe.empty_state()
    assert pe.plan(guard, tpe(10, 26, 10, 0), probe=lambda: games, load_local=lambda: local_for(games),
                   watch_enabled=True, local_starters=lambda keys: set())[0] == "idle"
    blocked = pe.empty_state() | {"www_blocked_at": pe._iso(now - timedelta(hours=1))}
    assert pe.plan(blocked, now, probe=lambda: games, load_local=lambda: local_for(games),
                   watch_enabled=True, local_starters=lambda keys: set())[0] == "idle"


def test_watch_shares_kind_cooldown_with_event_fetches(monkeypatch):
    monkeypatch.setenv(pe.EVENING_KINDS_ENV, "")
    games = pe.parse_stats_games([raw_game("C", 7, "SCHEDULED", "2026-10-27T18:35:00")], 2026)
    now = tpe(10, 26, 19, 0)
    state = pe.empty_state() | {"www_requests": {"C": pe._iso(now - timedelta(minutes=10))}}
    assert pe.plan(state, now, probe=lambda: games, load_local=lambda: local_for(games),
                   watch_enabled=True, local_starters=lambda keys: set())[0] == "idle"
    assert pe.plan(state, now + timedelta(minutes=10), probe=lambda: games, load_local=lambda: local_for(games),
                   watch_enabled=True, local_starters=lambda keys: set()) == ("scrape", "starter_watch")


def test_gate_wakes_on_rest_day_for_tomorrows_game():
    state = pe.empty_state() | {"schedule": [sched("C", 7, "SCHEDULED", "2026-10-27T18:35:00")]}
    now = tpe(10, 26, 21, 0)
    assert pe.evening_gate(state, now, None, db_lookup=lambda night: set())[0] == "quiet", "基準：休兵日 quiet"
    assert sw.gate_kinds(state, now, pe.EVENING_KINDS) == {"C"}
