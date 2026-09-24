"""賽中即時推算球種（models/pitch_type_live）的離線測試，無 DB 依賴。

準確度不在這裡驗：那是對真實資料的量測（模組 docstring：9/1 後一軍 12,316 球與賽後離線
標籤一致 97.62%）。這裡釘住的是機制——特徵與入庫同一條公式、樣本門檻、多數決、快照
補欄與移除軌跡輸入。
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest

from cpbl.ingest.cpbl_pitch_tracking import _traj
from cpbl.ingest.live_game_worker import build_snapshot
from cpbl.models import pitch_type_live as ptl
from cpbl.models.pitch_type import MIN_N

FIXTURE = Path(__file__).parent / "fixtures" / "stats_game_2026-A-234.json"
T0 = datetime(2026, 9, 24, 11, 0, tzinfo=UTC)


def _real_snapshot() -> tuple[dict, list[dict]]:
    raw = json.loads(FIXTURE.read_text())
    game = raw.get("Game", raw) if "LiveLog" not in raw else raw
    raw_pitches = [e for e in game["LiveLog"] if e.get("Trackman")]
    return build_snapshot(game, fetched_at=T0), raw_pitches


def test_live_features_match_the_offline_formula_on_a_real_game() -> None:
    """賽中特徵必須與入庫（cpbl_pitch_tracking._traj）逐球相同，否則賽中與賽後在不同空間比。"""
    snapshot, raw_pitches = _real_snapshot()
    rows = [r for r in snapshot["livelog"] if r.get("trackman")]
    assert len(rows) == len(raw_pitches) == 6
    for row, raw in zip(rows, raw_pitches, strict=True):
        pit = raw["Trackman"]["Pitch"]
        _, _, _, ivb, hb = _traj(pit)
        assert ptl.live_features(row["trackman"]) == pytest.approx(
            (pit["Release"]["RelSpeed"], ivb, hb, pit["Release"]["SpinRate"]))


def test_missing_input_yields_no_features() -> None:
    tm = {"rel_speed": 140.0, "spin_rate": None, "zone_time": 0.4,
          "traj_y": [1.0, 0.5, -3.0], "traj_z": [0.3, 0.1, 1.0]}
    assert ptl.live_features(tm) is None
    assert ptl.live_features({**tm, "spin_rate": 2200.0, "traj_y": None}) is None


def _rows(n: int, label: str, center: tuple[float, float, float, float]) -> list[tuple]:
    rng = np.random.default_rng(0)
    return [(*(np.array(center) + rng.normal(0, 1, 4)), label) for _ in range(n)]


def test_fit_requires_the_same_minimum_as_offline_clustering() -> None:
    assert ptl.fit_samples(_rows(MIN_N - 1, "四縫", (145, 45, -20, 2300))) is None
    assert ptl.fit_samples(_rows(MIN_N, "四縫", (145, 45, -20, 2300))) is not None


def test_estimate_takes_the_majority_of_the_k_nearest() -> None:
    rows = _rows(100, "四縫", (148, 45, -20, 2350)) + _rows(100, "滑球", (130, 5, 25, 2500))
    s = ptl.fit_samples(rows)
    assert ptl.estimate(s, (147.5, 44.0, -19.0, 2340.0)) == "四縫"
    assert ptl.estimate(s, (131.0, 6.0, 24.0, 2490.0)) == "滑球"


def test_majority_overrides_a_single_nearest_outlier() -> None:
    """最近的一顆是別的球種、其後 4 顆一致 → 取多數，不被單一離群球帶走。"""
    s = ptl.PitcherSamples(mu=np.zeros(4), sd=np.ones(4),
                           z=np.array([[0.0, 0, 0, 0], [0.2, 0, 0, 0], [0.3, 0, 0, 0],
                                       [0.4, 0, 0, 0], [0.5, 0, 0, 0]]),
                           labels=np.array(["滑球", "四縫", "四縫", "四縫", "四縫"]))
    assert ptl.estimate(s, (0.0, 0, 0, 0)) == "四縫"


def test_estimate_ties_go_to_the_nearer_label() -> None:
    """k=2 同票：取較近鄰居的標籤（決定性，不隨機）。"""
    s = ptl.PitcherSamples(mu=np.zeros(4), sd=np.ones(4),
                           z=np.array([[0.0, 0, 0, 0], [3.0, 0, 0, 0]]),
                           labels=np.array(["近", "遠"]))
    assert ptl.estimate(s, (0.1, 0, 0, 0), k=2) == "近"


def test_annotate_fills_estimates_and_strips_trajectory_inputs(monkeypatch) -> None:
    snapshot, _ = _real_snapshot()
    acnts = {str(r["PitcherAcnt"]) for r in snapshot["livelog"] if r.get("trackman")}
    known = sorted(acnts)[0]
    feats = [ptl.live_features(r["trackman"]) for r in snapshot["livelog"]
             if r.get("trackman") and str(r["PitcherAcnt"]) == known]
    samples = ptl.fit_samples(_rows(MIN_N, "四縫", tuple(np.mean(feats, axis=0))))
    monkeypatch.setattr(ptl, "samples_for",
                        lambda year, want: {a: (samples if a == known else None) for a in want})

    out = ptl.annotate(snapshot, 2026)
    for r in out["livelog"]:
        tm = r.get("trackman")
        if not tm:
            continue
        assert tm["pitch_type_est"] == ("四縫" if str(r["PitcherAcnt"]) == known else None)
        assert not {"traj_y", "traj_z", "zone_time"} & tm.keys()   # 前端用不到、不外送
        assert "spin_rate" in tm and "rel_speed" in tm


def test_pitcher_without_enough_samples_gets_no_estimate(monkeypatch) -> None:
    """樣本不足（samples=None）→ None，讓前端整打席退回官網分類；⛔ 不得硬猜一個球種。"""
    snapshot, _ = _real_snapshot()
    monkeypatch.setattr(ptl, "samples_for", lambda year, want: {a: None for a in want})
    out = ptl.annotate(snapshot, 2026)
    ests = [r["trackman"]["pitch_type_est"] for r in out["livelog"] if r.get("trackman")]
    assert ests and all(e is None for e in ests)


def test_annotate_passes_through_a_missing_snapshot() -> None:
    assert ptl.annotate(None, 2026) is None
