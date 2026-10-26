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
