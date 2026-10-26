"""#342 驗收重播（CI 可跑）：真實 payload × 模擬時鐘 × 真的晚間鏈 CLI。完整報告由
``tests/starter_watch_replay_harness.py --out`` 產生。不連網、不碰 DB、不寫 logs/。"""

from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parent / "starter_watch_replay_harness.py"
_SPEC = importlib.util.spec_from_file_location("starter_watch_replay_harness", _PATH)
assert _SPEC and _SPEC.loader
replay = importlib.util.module_from_spec(_SPEC)
sys.modules["starter_watch_replay_harness"] = replay
_SPEC.loader.exec_module(replay)

GAMES, NOISE, META = replay.load_games()
BY_KEY = {g.key: g for g in GAMES}


def test_fixture_is_real_and_complete():
    assert META["rows"] == 428 and len(GAMES) == 117
    assert {g.kind for g in GAMES} == {"A", "E", "C"}
    assert {"2026-A-304", "2026-A-306", "2026-A-326"} <= {
        f"{p['Year']}-{p['KindCode']}-{p['GameSno']}" for p in NOISE}, "賽中比分／保留列混在每次 www 回應裡"


@pytest.mark.parametrize("key", ["2026-C-6", "2026-E-3", "2026-A-302", "2026-A-14"])
def test_2300_fetches_once_writes_and_syncs(key):
    g = BY_KEY[key]
    row = replay.normal(g, NOISE)
    assert row["state"] == "fetched" and row["synced_at"] and row["www_fetches"] == 1
    assert row["prod_starters"] == row["expected"]
    attempted = datetime.fromisoformat(row["attempted_at"])
    assert g.fire <= attempted < g.fire + timedelta(minutes=6), "23:00 後第一次喚醒就抓"
    assert row["notifications"] == 0


@pytest.mark.parametrize("case,state", [("challenge", "failed"), ("still_empty", "empty"),
                                        ("lock_until_0100", "missed"), ("sync_68", "sync_failed")])
def test_failures_notify_once(case, state):
    out = replay.run_faults(BY_KEY["2026-C-6"], NOISE)[case]
    assert out["state"] == state and out["notified_at"]
    assert len(out["notifications"]) == 1 and "隔日 10:10 每日鏈補上" in out["notifications"][0][2]
    assert out["www_fetches"] == (0 if case == "lock_until_0100" else 1), "每場最多抓一次、不重試"


def test_a_target_overlapping_a_event_uses_342_path_with_real_marker(tmp_path, monkeypatch):
    """review-1 #3：23:00 有明日 A 目標，同晚又有 A 事件（新場次＋今晚 A 已終局、閘門放行）。A 必須走 #342 路徑
    （真的 www_marker card=342），⛔ 不得交給既有 A 抓取（真的 marking_scrape_games＋evening_games_step 會在 marker raise）。
    只換掉 www 本體（fetch_year→真實 payload）與本機 DB；marker、plan、scrape CLI 都是真的。"""
    from cpbl.ingest import postseason_evening as pe
    from cpbl.ingest import run_refresh_recent as rr

    g = BY_KEY["2026-A-302"]                                   # S 9/30 18:35 ⇒ F 9/29 23:00
    now = g.fire + timedelta(minutes=2)
    called = []
    monkeypatch.setattr(rr, "scrape_games", lambda *a, **k: called.append(a))   # 既有 A 抓取若被叫到就留痕
    real_marking, real_step = pe.marking_scrape_games, pe.evening_games_step
    world = replay.World(g, g.fire - timedelta(minutes=1), NOISE, now=now)
    rows = [{"GameId": f"2026-A-{sno}", "KindCode": "A", "GameSno": sno, "GameStatus": st, "PreExeDate": at,
             "Visiting": {"Team": {"Code": "ACN011"}}, "Home": {"Team": {"Code": "AAA011"}}, "Field": {"Abbe": "大巨蛋"}}
            for sno, st, at in ((301, "FINISHED", "2026-09-29T18:35:00"), (302, "SCHEDULED", "2026-09-30T18:35:00"),
                                (999, "SCHEDULED", "2026-10-02T18:35:00"))]
    stats = pe.parse_stats_games(rows, 2026)
    local = {k: v for k, v in {s.key: pe.LocalGame(2026, "A", s.game_sno, s.game_date, s.away_code, s.home_code,
                                                   s.venue, s.status == "FINISHED") for s in stats}.items()
             if not k.endswith("-999")}                        # 999 本機沒有 ⇒ new_game 事件
    with replay.patched(world, tmp_path):
        pe.marking_scrape_games, pe.evening_games_step = real_marking, real_step   # 還原真的（patched 結束時照原樣還原）
        state = pe.empty_state()
        assert pe.plan(state, now, probe=lambda: stats, load_local=lambda: local, watch_enabled=True) == ("scrape", "event")
        assert state["a_fetch_gate"] is None and "new_game:2026-A-999" in state["events"]
        assert state["scrape_kinds"] == ["A"] and state["starter_watch"]["watch_only"] == ["A"]
        pe.save_json(pe.state_path(), state)
        assert replay._cli("scrape") == "changed"
        after = pe.load_state(pe.state_path())
    assert called == [], "既有 A 抓取沒有被呼叫"
    assert after["starter_watch"]["games"]["2026-A-302"]["state"] == "fetched"
    assert world.local[g.key] == [g.published["HomePitcherAcnt"], g.published["VisitingPitcherAcnt"]]
    assert len(world.fetch_log) == 1
    assert after["events"]["new_game:2026-A-999"]["attempts"] == [], "這次只走 #342，A 事件不計次、之後照既有規則再抓"


def test_negative_control_existing_a_path_raises_in_real_marker(monkeypatch):
    """對照：同一個 A 若交給既有路徑，真的 marking_scrape_games 在 www_marker 就失敗（#365 既有行為，本卡不修）。"""
    from cpbl.ingest import postseason_evening as pe
    from cpbl.ingest import run_refresh_recent as rr

    called = []
    monkeypatch.setattr(rr, "scrape_games", lambda *a, **k: called.append(a))
    state = {"events": {"new_game:2026-A-999": {"key": "2026-A-999", "state": "open", "attempts": []}}}
    with pe.marking_scrape_games(state, 2026):
        out = pe.evening_games_step(2026, ("A",))
    assert called == [] and "www_marker 參數不合法" in out["errors"][0]["error"]


def test_historical_provable_subset():
    """review-1 重播判定：只有本機首見「賽前、有先發」真實時刻 ≤ F 的 15 場可當歷史證據；www 自那個真實時刻起回有先發版。"""
    proven = [g for g in GAMES if replay._ts(g.published_seen) <= g.fire]
    assert [g.key for g in proven] == ["2026-A-276", "2026-A-302", "2026-A-316", "2026-A-317", "2026-A-352",
                                       "2026-A-353", "2026-A-354", "2026-A-355", "2026-A-356", "2026-A-357",
                                       "2026-C-1", "2026-C-2", "2026-C-3", "2026-C-4", "2026-C-6"]
    for g in proven:
        row = replay.normal(g, NOISE, publish_at=replay._ts(g.published_seen))
        assert row["state"] == "fetched" and row["prod_starters"] == row["expected"] and row["www_fetches"] == 1, g.key
