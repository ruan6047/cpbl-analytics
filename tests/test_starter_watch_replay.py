"""#342 驗收重播（縮小版，CI 可跑）：真實 payload × 模擬時鐘 × 真的晚間鏈 CLI。完整版與報告見
``tests/starter_watch_replay_harness.py``。不連網、不碰 DB、不寫 logs/。"""

from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, time, timedelta
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parent / "starter_watch_replay_harness.py"
_SPEC = importlib.util.spec_from_file_location("replay_starter_watch", _PATH)
assert _SPEC and _SPEC.loader
replay = importlib.util.module_from_spec(_SPEC)
sys.modules["replay_starter_watch"] = replay
_SPEC.loader.exec_module(replay)

GAMES, NOISE, META = replay.load_games()
BY_KEY = {g.key: g for g in GAMES}


def test_fixture_is_real_and_complete():
    assert META["rows"] == 428 and len(GAMES) == 117
    assert {g.kind for g in GAMES} == {"A", "E", "C"}
    assert {"2026-A-304", "2026-A-306", "2026-A-326"} <= {
        f"{p['Year']}-{p['KindCode']}-{p['GameSno']}" for p in NOISE}, "賽中比分／保留列混在每次 www 回應裡"


@pytest.mark.parametrize("key", ["2026-C-6", "2026-E-3", "2026-A-302"])
def test_daytime_publication_reaches_prod_within_an_hour_and_night_ones_alert(key):
    s = replay.sweep(BY_KEY[key], NOISE)
    late = [p for p in s["points"] if p.get("detected") and p["latency_min"] > 60]
    assert all(p["alert_by_limit"] for p in late), late[:3]
    # 已知缺口（照實釘住，不隱藏）：關窗前最後一個抓取間隔內的公布，觀察窗內偵測不到（窗口止於 S−30，
    # 裁定 6405294357 Q4）；之後只剩 #292 A1 S−30（A 被 P-A-FETCH-GATE 擋時也沒有）與隔日 J1。
    close = datetime.fromisoformat(s["window"][1])
    missed = [p for p in s["points"] if not p.get("detected")]
    assert all(datetime.fromisoformat(p["p"]) >= close - timedelta(minutes=36) for p in missed), missed[:3]
    for p in late:   # 超過 1 小時的公布時刻都落在夜間暫停或其前一個抓取間隔內
        t = datetime.fromisoformat(p["p"]).astimezone(replay.TAIPEI).time()
        assert time(0, 25) <= t < time(10, 0), p


def test_sweep_matches_full_simulation():
    g = BY_KEY["2026-C-6"]
    s = replay.sweep(g, NOISE)
    picks = [p for p in s["points"] if p.get("detected")][::97]
    for p in picks:
        full = replay.full_check(g, NOISE, datetime.fromisoformat(p["p"]))
        assert full["latency_min"] == p["latency_min"], (p, full)
        assert full["prod_starters"] == full["expected"]


@pytest.mark.parametrize("fault", ["F1_challenge", "F2_lock_60m", "F3_sleep_2h", "F4_sync_68", "F5_backup_fail"])
def test_faults_raise_alert_then_fill(fault):
    out = replay.run_faults(BY_KEY["2026-A-302"], NOISE)[fault]
    assert out["prod_at"], "事後補上：正式站最後有先發"
    assert out["alerts"], "超時告警有出現"
    assert out["alert_open_at_end"] is None, "補上後告警清除"
    assert out["alerts"][-1]["resolution"] == "delivered"
    titles = [n[1] for n in out["notifications"]]
    assert "CPBL 先發超時" in titles and "CPBL 先發告警解除" in titles
    assert any("已補上" in n[2] for n in out["notifications"])
    if out["latency_min"] > 60:
        first = datetime.fromisoformat(out["alerts"][0]["since"])
        assert first <= datetime.fromisoformat(out["publish_at"]) + timedelta(minutes=60)
