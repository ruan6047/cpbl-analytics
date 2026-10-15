"""#292 A1 先發查核時點（開賽前 1h／0.5h、比賽結束後 1h）：注入時鐘的純函式與晚間鏈接線測試。

stats 回應是 SYNTHETIC（形狀沿用 ``tests/test_postseason_evening.py`` 的 ``raw_game``）；C-1 的
17:05 取自 #292 PLAN plan-3 §10 時程。⛔ 不是公站或正式資料證據。不連網、不碰 DB。
"""

from __future__ import annotations

import json
import sys
import types
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from cpbl.ingest import postseason_evening as pe
from cpbl.ingest import starter_checkpoints as sc

TPE = ZoneInfo("Asia/Taipei")


def tpe(m, d, hh, mm) -> datetime:
    return datetime(2026, m, d, hh, mm, tzinfo=TPE)


def raw_game(kind: str, sno: int, status: str, starts: str | None) -> dict:
    return {"GameId": f"2026-{kind}-{sno}", "KindCode": kind, "GameSno": sno,
            "GameStatus": status, "PreExeDate": starts,
            "Visiting": {"Team": {"Code": "ACN011"}}, "Home": {"Team": {"Code": "AAA011"}},
            "Field": {"Abbe": "大巨蛋"}}


def stats(*rows) -> list[pe.StatsGame]:
    return pe.parse_stats_games(list(rows), 2026)


def local_for(games: list[pe.StatsGame], completed: bool = False) -> dict[str, pe.LocalGame]:
    return {g.key: pe.LocalGame(2026, g.kind_code, g.game_sno, g.game_date, g.away_code,
                                g.home_code, g.venue, completed) for g in games}


C1 = stats(raw_game("C", 1, "SCHEDULED", "2026-10-17T17:05:00"))
C1_LOCAL = local_for(C1)
ENABLED_AT = tpe(10, 17, 15, 30)


def wake(state, now, games=None, *, enabled=True, local=None, www_starts=dict):
    games = C1 if games is None else games
    return pe.plan(state, now, probe=lambda: games, load_local=lambda: local if local is not None else local_for(games),
                   starter_enabled=enabled, www_starts=www_starts)


def fetch(state, now, *, changed=False, errors=()):
    """照 CLI scrape：先記既有事件帳，再把併入的時點入帳。"""
    kinds = state["scrape_kinds"]
    pe.record_scrape(state, now, errors=list(errors), changed=changed, stats_has_c=True,
                     local_c_rows=1, kinds=kinds)
    failed, challenged = pe.scrape_failures(errors, kinds)
    sc.record_attempt(state["starter_checkpoints"], state["starter_inflight"], now,
                      changed=changed, failed_kinds=failed, challenge_kinds=challenged)


def enabled_state():
    state = pe.empty_state()
    assert wake(state, ENABLED_AT) == ("idle", "no_events")
    return state


def records(state, point=None):
    return [r for r in state["starter_checkpoints"].values() if point in (None, r["point"])]


# —— 三時點與 17:05／18:35 ——

def test_c1_1705_fires_at_1605_and_1635_only_for_kind_c():
    state = enabled_state()
    assert wake(state, tpe(10, 17, 16, 4)) == ("idle", "no_events")
    assert records(state) == []
    assert wake(state, tpe(10, 17, 16, 5)) == ("scrape", "starter_checkpoint")
    assert state["scrape_kinds"] == ["C"]
    assert [sc.kind_of(i) for i in state["starter_inflight"]] == ["C"]
    fetch(state, tpe(10, 17, 16, 5))
    (s60,) = records(state, "S-60")
    assert (s60["outcome"], s60["fired_at"], s60["phase"]) == ("unchanged", pe._iso(tpe(10, 17, 16, 5)), "pregame")
    assert wake(state, tpe(10, 17, 16, 30)) == ("idle", "no_events")
    assert wake(state, tpe(10, 17, 16, 35)) == ("scrape", "starter_checkpoint")
    fetch(state, tpe(10, 17, 16, 35), changed=True)
    (s30,) = records(state, "S-30")
    assert s30["outcome"] == "changed" and s30["done"]
    assert s30["due_at"] == pe._iso(tpe(10, 17, 16, 35)) and s30["deadline_at"] == pe._iso(tpe(10, 17, 17, 5))


def test_1835_game_points_are_1735_and_1805():
    g = stats(raw_game("C", 2, "SCHEDULED", "2026-10-18T18:35:00"))
    rows = sc.preview([pe.asdict(x) for x in g], {}, tpe(10, 18, 12, 0))
    got = {r["point"]: (r.get("due_at"), r.get("deadline_at")) for r in rows}
    assert got["S-60"] == (tpe(10, 18, 17, 35).isoformat(), tpe(10, 18, 17, 55).isoformat())
    assert got["S-30"] == (tpe(10, 18, 18, 5).isoformat(), tpe(10, 18, 18, 35).isoformat())
    assert "F+60" in got and got["F+60"] == (None, None)


def test_flag_off_keeps_268_baseline_and_enabling_later_does_not_backfill():
    state = pe.empty_state()
    assert wake(state, tpe(10, 17, 16, 5), enabled=False) == ("idle", "no_events")
    assert state["starter_checkpoints"] == {} and state["starter_enabled_since"] is None
    # 16:20 才開：S-60（16:05）已過開啟起點 → 不補建；S-30 照常。
    assert wake(state, tpe(10, 17, 16, 20)) == ("idle", "no_events")
    assert records(state) == []
    assert wake(state, tpe(10, 17, 16, 35))[0] == "scrape"
    assert [r["point"] for r in records(state)] == ["S-30"]
    # 關掉再開：起點重設
    wake(state, tpe(10, 17, 16, 40), enabled=False)
    assert state["starter_enabled_since"] is None


# —— 錯窗、冷卻延後、讓位、鎖 ——

def test_missed_window_is_recorded_not_backfilled():
    """Mac 睡到 16:41：S-60（最遲 16:25）建立即結清為 missed，⛔ 不補打；S-30 照常查。"""
    state = enabled_state()
    assert wake(state, tpe(10, 17, 16, 41)) == ("scrape", "starter_checkpoint")
    (s60,) = records(state, "S-60")
    assert (s60["outcome"], s60["reason"], s60["attempts"]) == ("missed", "no_wake_in_window", [])
    assert [sc.kind_of(i) for i in state["starter_inflight"]] == ["C"]
    assert state["starter_inflight"] == [i for i, r in state["starter_checkpoints"].items()
                                         if r["point"] == "S-30"]


def test_cooldown_delays_without_counting_then_fires_inside_window():
    state = enabled_state()
    state["www_requests"]["C"] = pe._iso(tpe(10, 17, 16, 20))   # 事件剛抓過 C
    assert wake(state, tpe(10, 17, 16, 35)) == ("idle", "no_events")
    (s30,) = records(state, "S-30")
    assert s30["wait_reason"] == "cooldown" and s30["attempts"] == []
    assert wake(state, tpe(10, 17, 16, 40)) == ("scrape", "starter_checkpoint")


def test_cooldown_past_deadline_becomes_missed_with_reason():
    state = enabled_state()
    state["www_requests"]["C"] = pe._iso(tpe(10, 17, 16, 0))
    wake(state, tpe(10, 17, 16, 5))
    assert records(state, "S-60")[0]["wait_reason"] == "cooldown"
    wake(state, tpe(10, 17, 16, 26))
    (s60,) = records(state, "S-60")
    # 16:20 冷卻已過但這段沒有喚醒（測試直接跳到 16:26）→ 逾時，原因保留最後的等待原因。
    assert (s60["outcome"], s60["reason"]) == ("missed", "cooldown")


def test_busy_lock_only_postpones_and_never_counts():
    """plan 回 scrape 後腳本取鎖失敗（exit 75，不跑 scrape）：下次喚醒同一筆仍到點、次數 0。"""
    state = enabled_state()
    assert wake(state, tpe(10, 17, 16, 5))[0] == "scrape"
    assert wake(state, tpe(10, 17, 16, 10))[0] == "scrape"
    (s60,) = records(state, "S-60")
    assert s60["attempts"] == [] and not s60["done"]


def test_daily_guard_yields():
    state = pe.empty_state()
    morning = stats(raw_game("C", 1, "SCHEDULED", "2026-10-17T11:00:00"))
    state["starter_enabled_since"] = pe._iso(tpe(10, 17, 9, 0))
    assert wake(state, tpe(10, 17, 10, 0), morning) == ("idle", "no_events")
    assert records(state, "S-60")[0]["wait_reason"] == "yield_to_daily"
    assert wake(state, tpe(10, 17, 10, 15), morning)[0] == "scrape"


def test_challenge_stop_blocks_and_expires_as_blocked():
    state = enabled_state()
    state["www_blocked_at"] = pe._iso(tpe(10, 17, 15, 50))
    assert wake(state, tpe(10, 17, 16, 5)) == ("idle", "no_events")
    wake(state, tpe(10, 17, 16, 26))
    (s60,) = records(state, "S-60")
    assert (s60["outcome"], s60["reason"]) == ("blocked", "www_blocked")


@pytest.mark.parametrize("setup,reason", [
    (lambda s: s.__setitem__("sync_blocked_at", pe._iso(tpe(10, 17, 15, 40))), "sync_blocked"),
    (lambda s: s.__setitem__("pending_sync", True), "pending_sync"),
])
def test_tonight_stop_and_pending_sync_do_not_fetch(setup, reason):
    state = enabled_state()
    setup(state)
    action, _ = wake(state, tpe(10, 17, 16, 5))
    assert action in ("idle", "sync")
    assert records(state, "S-60")[0]["wait_reason"] == reason
    assert state["starter_inflight"] == []


def test_probe_failure_fails_closed():
    state = enabled_state()

    def down():
        raise pe.ProbeUnavailable("timeout")

    state["last_probe_at"] = None   # 強制到期去讀 stats
    assert pe.plan(state, tpe(10, 17, 16, 5), probe=down, load_local=lambda: C1_LOCAL,
                   starter_enabled=True)[1] == "probe_unavailable"
    assert records(state, "S-60")[0]["wait_reason"] == "probe_unavailable"


# —— 改期、未知開賽時刻、保留／延賽、開打 ——

def test_reschedule_creates_new_points_and_old_ones_expire():
    state = enabled_state()
    wake(state, tpe(10, 17, 16, 5))           # 舊時刻 S-60 到點但沒抓（鎖）
    moved = stats(raw_game("C", 1, "SCHEDULED", "2026-10-17T18:35:00"))
    state["last_probe_at"] = None
    assert wake(state, tpe(10, 17, 16, 30), moved) == ("idle", "no_events")
    old = state["starter_checkpoints"][f"2026-C-1|S-60|{pe._iso(tpe(10, 17, 17, 5))}"]
    assert (old["outcome"], old["reason"]) == ("missed", "no_wake_in_window")
    assert wake(state, tpe(10, 17, 17, 35), moved)[0] == "scrape"
    assert any(r["anchor_at"] == pe._iso(tpe(10, 17, 18, 35)) for r in records(state, "S-60"))


def test_unknown_start_time_never_fires():
    state = enabled_state()
    unknown = stats(raw_game("C", 1, "SCHEDULED", None))
    state["last_probe_at"] = None
    assert wake(state, tpe(10, 17, 16, 5), unknown) == ("idle", "no_events")
    assert {r["outcome"] for r in records(state)} == {"start_time_unknown"}
    assert sc.due(state["starter_checkpoints"], tpe(10, 17, 16, 35)) == []


def test_postponed_or_reserved_records_no_final_and_closes_pregame():
    state = enabled_state()
    wake(state, tpe(10, 17, 16, 5))
    held = stats(raw_game("C", 1, "RESERVED", "2026-10-17T17:05:00"))
    state["last_probe_at"] = None
    wake(state, tpe(10, 17, 17, 10), held, local=C1_LOCAL)
    by_point = {r["point"]: r for r in records(state)}
    assert by_point["F+60"]["outcome"] == "no_final"
    assert (by_point["S-60"]["outcome"], by_point["S-60"]["reason"]) == ("missed", "game_status_RESERVED")


def test_early_start_closes_unfired_pregame_points():
    state = enabled_state()
    started = stats(raw_game("C", 1, "START", "2026-10-17T17:05:00"))
    wake(state, tpe(10, 17, 16, 5))
    state["last_probe_at"] = None
    wake(state, tpe(10, 17, 16, 40), started, local=C1_LOCAL)
    assert all(r["done"] for r in records(state))
    assert sc.due(state["starter_checkpoints"], tpe(10, 17, 16, 40)) == []


# —— 終場：F＝本機首見 FINISHED ——

def test_final_point_anchors_on_first_local_finished_observation():
    state = enabled_state()
    done = stats(raw_game("C", 1, "FINISHED", "2026-10-17T17:05:00"))
    state["last_probe_at"] = None
    wake(state, tpe(10, 17, 20, 12), done, local=local_for(done, completed=True))
    wake(state, tpe(10, 17, 20, 17), done, local=local_for(done, completed=True))
    assert state["finished_first_seen"]["2026-C-1"] == pe._iso(tpe(10, 17, 20, 12))
    assert wake(state, tpe(10, 17, 21, 11), done, local=local_for(done, completed=True)) == ("idle", "no_events")
    assert wake(state, tpe(10, 17, 21, 12), done, local=local_for(done, completed=True)) == (
        "scrape", "starter_checkpoint")
    (f60,) = records(state, "F+60")
    assert f60["phase"] == "postgame"
    assert f60["deadline_at"] == pe._iso(tpe(10, 17, 21, 42))


def test_finished_first_seen_is_recorded_even_when_flag_is_off():
    state = pe.empty_state()
    done = stats(raw_game("C", 1, "FINISHED", "2026-10-17T17:05:00"))
    wake(state, tpe(10, 17, 20, 12), done, enabled=False, local=local_for(done, completed=True))
    assert state["finished_first_seen"] == {"2026-C-1": pe._iso(tpe(10, 17, 20, 12))}
    assert state["starter_checkpoints"] == {}


# —— D2 有界重送 ——

def _s30_failed_once(errors):
    state = enabled_state()
    wake(state, tpe(10, 17, 16, 35))
    fetch(state, tpe(10, 17, 16, 35), errors=errors)
    return state


def test_s30_failure_retries_once_after_twenty_minutes_before_start():
    state = _s30_failed_once([{"kind": "C", "error": "TimeoutError"}])
    (s30,) = records(state, "S-30")
    assert (s30["outcome"], s30["reason"], s30["done"]) == ("failed", "retry_pending", False)
    # 重送間隔本身（不靠賽別冷卻也成立）
    assert sc.due(state["starter_checkpoints"], tpe(10, 17, 16, 54)) == []
    assert len(sc.due(state["starter_checkpoints"], tpe(10, 17, 16, 55))) == 1
    assert wake(state, tpe(10, 17, 16, 50)) == ("idle", "no_events")
    assert wake(state, tpe(10, 17, 16, 55)) == ("scrape", "starter_checkpoint")
    fetch(state, tpe(10, 17, 16, 55), errors=[{"kind": "C", "error": "TimeoutError"}])
    (s30,) = records(state, "S-30")
    assert (s30["outcome"], s30["reason"], len(s30["attempts"])) == ("failed", "retry_exhausted", 2)


def test_retry_pending_is_closed_when_the_game_starts_early():
    """等重送中的 S-30 若官方已開打，就不再以賽前名義重查。"""
    state = _s30_failed_once([{"kind": "C", "error": "TimeoutError"}])
    started = stats(raw_game("C", 1, "START", "2026-10-17T17:05:00"))
    state["last_probe_at"] = None
    assert wake(state, tpe(10, 17, 16, 56), started, local=C1_LOCAL) == ("idle", "no_events")
    (s30,) = records(state, "S-30")
    assert (s30["outcome"], s30["reason"], s30["done"]) == ("failed", "game_status_START", True)


def test_s30_retry_window_closes_at_start():
    state = _s30_failed_once([{"kind": "C", "error": "TimeoutError"}])
    wake(state, tpe(10, 17, 17, 6))
    (s30,) = records(state, "S-30")
    assert (s30["outcome"], s30["reason"]) == ("failed", "retry_window_passed")


def test_challenge_failure_is_never_retried():
    state = _s30_failed_once([{"kind": "C", "error": "反爬挑戰未過"}])
    (s30,) = records(state, "S-30")
    assert (s30["done"], s30["reason"]) == (True, "challenge_no_retry")
    assert state["challenge_failures"], "挑戰計入既有晚間停機帳"


def test_s60_failure_is_not_retried():
    state = enabled_state()
    wake(state, tpe(10, 17, 16, 5))
    fetch(state, tpe(10, 17, 16, 5), errors=[{"kind": "C", "error": "TimeoutError"}])
    (s60,) = records(state, "S-60")
    assert (s60["done"], s60["reason"]) == (True, "no_retry_for_point")


def test_f60_failure_retries_inside_f90():
    state = enabled_state()
    done = stats(raw_game("C", 1, "FINISHED", "2026-10-17T17:05:00"))
    state["last_probe_at"] = None
    loc = local_for(done, completed=True)
    wake(state, tpe(10, 17, 20, 0), done, local=loc)
    wake(state, tpe(10, 17, 21, 0), done, local=loc)
    fetch(state, tpe(10, 17, 21, 0), errors=[{"kind": "C", "error": "HTTP 500"}])
    assert wake(state, tpe(10, 17, 21, 20), done, local=loc)[0] == "scrape"
    assert sc.due(state["starter_checkpoints"], tpe(10, 17, 21, 31)) == []


# —— 事件與時點合併、同步碼 ——

def test_event_and_checkpoint_of_same_kind_share_one_fetch():
    state = enabled_state()
    local_missing: dict = {}
    assert wake(state, tpe(10, 17, 16, 5), local=local_missing) == ("scrape", "event")
    assert state["scrape_kinds"] == ["C"] and len(state["starter_inflight"]) == 1
    fetch(state, tpe(10, 17, 16, 5))
    assert state["events"]["new_game:2026-C-1"]["attempts"] == [pe._iso(tpe(10, 17, 16, 5))]
    assert records(state, "S-60")[0]["attempts"][0]["at"] == pe._iso(tpe(10, 17, 16, 5))


def test_sync_code_is_attached_only_to_changed_attempts():
    state = enabled_state()
    wake(state, tpe(10, 17, 16, 5))
    fetch(state, tpe(10, 17, 16, 5), changed=False)
    sc.record_sync(state["starter_checkpoints"], state["starter_inflight"], 0)
    assert records(state, "S-60")[0]["sync_code"] is None
    wake(state, tpe(10, 17, 16, 35))
    fetch(state, tpe(10, 17, 16, 35), changed=True)
    sc.record_sync(state["starter_checkpoints"], state["starter_inflight"], 66)
    assert records(state, "S-30")[0]["sync_code"] == 66


def test_scrape_failures_maps_kindless_errors_to_all_fetched_kinds():
    assert pe.scrape_failures([], ("C",)) == (set(), set())
    assert pe.scrape_failures([{"error": "REDIRECT loop"}], ("E", "C")) == ({"E", "C"}, {"E", "C"})
    assert pe.scrape_failures([{"kind": "C", "error": "Timeout"}], ("E", "C")) == ({"C"}, set())


def test_www_start_is_recorded_alongside_and_stats_wins():
    state = enabled_state()
    wake(state, tpe(10, 17, 16, 5), www_starts=lambda: {"2026-C-1": "18:35"})
    (s60,) = records(state, "S-60")
    assert (s60["www_start_raw"], s60["start_mismatch"]) == ("18:35", True)
    assert s60["anchor_at"] == pe._iso(tpe(10, 17, 17, 5)), "以 stats 為準"


# —— E3 主風險：只輸出本機觀測時刻 ——

def test_no_output_carries_an_announcement_time():
    state = enabled_state()
    done = stats(raw_game("C", 1, "FINISHED", "2026-10-17T17:05:00"))
    wake(state, tpe(10, 17, 16, 5))
    fetch(state, tpe(10, 17, 16, 5), changed=True)
    state["last_probe_at"] = None
    wake(state, tpe(10, 17, 20, 0), done, local=local_for(done, completed=True))
    wake(state, tpe(10, 17, 21, 0), done, local=local_for(done, completed=True))
    blob = json.dumps([state["starter_checkpoints"], sc.timeline(state["starter_checkpoints"]),
                       sc.preview(state["schedule"], state["finished_first_seen"], tpe(10, 17, 12, 0))])
    assert "announced" not in blob and "publish" not in blob
    phases = {r["point"]: r["phase"] for r in records(state)}
    assert phases == {"S-60": "pregame", "F+60": "postgame"}


# —— CLI：plan --dry 不連網不寫；scrape／record-sync／finish 接線 ——

def _cli_env(tmp_path, monkeypatch, state):
    path = tmp_path / "state.json"
    path.write_text(json.dumps(state), encoding="utf-8")
    monkeypatch.setenv("POSTSEASON_STATE", str(path))
    monkeypatch.setenv("POSTSEASON_STATUS", str(tmp_path / "last.json"))
    monkeypatch.setenv("POSTSEASON_STARTER_FLAG", str(tmp_path / "flag"))
    monkeypatch.setenv("POSTSEASON_YEAR", "2026")
    return path


def test_plan_dry_lists_c1_points_without_network_db_or_writes(tmp_path, monkeypatch, capsys):
    import socket

    state = pe.empty_state()
    state["schedule"] = [pe.asdict(g) for g in C1]
    path = _cli_env(tmp_path, monkeypatch, state)
    before = path.read_bytes()

    def no_net(*a, **k):
        raise AssertionError("plan --dry 不得連網")

    monkeypatch.setattr(socket.socket, "connect", no_net)
    monkeypatch.setattr(pe, "load_local_games", lambda *a: pytest.fail("不得讀 DB"))
    monkeypatch.setattr(pe, "local_www_starts", lambda *a: pytest.fail("不得讀 DB"))
    monkeypatch.setattr(pe, "publish_signals", lambda *a: pytest.fail("不得寫 DB"))
    assert pe.main(["plan", "--dry", "--now", "2026-10-17T12:00:00"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["starter_enabled"] is False
    pts = {r["point"]: r for r in out["points"]}
    assert pts["S-60"]["due_at"] == "2026-10-17T16:05:00+08:00"
    assert pts["S-30"]["due_at"] == "2026-10-17T16:35:00+08:00"
    assert "F+60" in pts and "note" in pts["F+60"]
    assert path.read_bytes() == before


def test_cli_scrape_sync_finish_record_the_checkpoint(tmp_path, monkeypatch, capsys):
    state = pe.empty_state()
    wake(state, ENABLED_AT)
    assert wake(state, tpe(10, 17, 16, 5))[0] == "scrape"
    path = _cli_env(tmp_path, monkeypatch, state)
    (tmp_path / "flag").touch()
    sigs = iter(["before", "after"])
    monkeypatch.setattr(pe, "_now", lambda: tpe(10, 17, 16, 6))
    monkeypatch.setattr(pe, "local_signature", lambda year: next(sigs))
    monkeypatch.setattr(pe, "load_local_games", lambda year, now: C1_LOCAL)
    monkeypatch.setattr(pe, "local_first_seen", lambda year: {})
    monkeypatch.setattr(pe, "publish_signals", lambda *a: None)
    monkeypatch.setattr(pe, "log_local_refresh", lambda *a: None)
    fake = types.ModuleType("cpbl.ingest.run_refresh_recent")
    fake._postseason_games_step = lambda year, kinds: {"games": {k: 1 for k in kinds}, "errors": []}
    monkeypatch.setitem(sys.modules, "cpbl.ingest.run_refresh_recent", fake)

    assert pe.main(["scrape"]) == 0 and capsys.readouterr().out.strip() == "changed"
    assert pe.main(["record-sync", "--code", "0"]) == 0
    assert pe.main(["finish"]) == 0
    saved = json.loads(path.read_text(encoding="utf-8"))
    (s60,) = [r for r in saved["starter_checkpoints"].values() if r["point"] == "S-60"]
    assert (s60["outcome"], s60["sync_code"], s60["fired_at"]) == ("changed", 0, pe._iso(tpe(10, 17, 16, 6)))
    status = json.loads(Path(tmp_path / "last.json").read_text(encoding="utf-8"))
    assert [r["point"] for r in status["starter_checkpoints"]] == ["S-60"]
    assert status["starter_checkpoints"][0]["phase"] == "pregame"
