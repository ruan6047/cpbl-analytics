"""賽中即時推算細分球種（需求方 2026-09-24 裁定做；UX-LIVE-TRACKMAN1 Design Gate 2026-08-02
列為後續卡的「自家即時球種模型」）。

做法：取該投手本季（一二軍合算，與離線分群同一個樣本口徑 `pitch_type.POOL_KINDS`）已有
離線球種標籤的逐球，4 維特徵 `(rel_speed, ivb_cm, hb_cm, spin_rate)` 投手內標準化後，
對新進的一球做 kNN（k=5）多數決。標籤取網站完賽後顯示的同一個值
`COALESCE(pitch_type_pred_v2, pitch_type_pred)`，所以賽中與賽後用同一套名稱。
IVB/HB 由 `cpbl_pitch_tracking._traj` 計算——與入庫同一條公式，不另寫一份。

準確度（2026-09-24 實測：以本季 9/1 前的資料建模，預測 9/1 後一軍 12,316 球）：與賽後離線
標籤一致 97.62%（12,023 球），最差投手（≥30 球）71.7%。最近中心點 97.09%、k=15 97.53%。
⚠️ 不一致主要來自賽後每日重新分群會移動邊界——存完整 KMeans 模型也消不掉，所以前端的
「推算」字樣不可省，⛔ 也不得把賽中推算當成賽後結果回寫任何表。

樣本不足（< `pitch_type.MIN_N` 球，與離線分群門檻相同）或輸入缺欄 → None，前端整個打席退回
官網分類（`game-board.tsx` 的 PA 來源鎖定，不混用兩種來源）。
"""

from __future__ import annotations

import time
from collections import Counter
from dataclasses import dataclass

import numpy as np

from cpbl.db import conn
from cpbl.ingest.cpbl_pitch_tracking import _traj
from cpbl.models.pitch_type import MIN_N, POOL_KINDS

K = 5
CACHE_TTL_SECONDS = 3600   # 離線標籤每日更新一次；一小時內重用同一份樣本
_TRAJ_INPUTS = ("zone_time", "traj_y", "traj_z")   # 推算完即自公開快照移除（前端用不到）


@dataclass(frozen=True)
class PitcherSamples:
    mu: np.ndarray       # (4,) 投手內特徵平均
    sd: np.ndarray       # (4,) 投手內特徵標準差（0 以 1 代）
    z: np.ndarray        # (n, 4) 標準化後的歷史逐球
    labels: np.ndarray   # (n,) 離線球種標籤


_cache: dict[tuple[int, str], tuple[float, PitcherSamples | None]] = {}


def live_features(tm: dict) -> tuple[float, float, float, float] | None:
    """快照 trackman → (rel_speed, ivb_cm, hb_cm, spin_rate)；任一缺值回 None。"""
    pit = {"Flight": {"PolyFit": {"PitchTrajectory": {"Y": tm.get("traj_y"), "Z": tm.get("traj_z")}}},
           "Location": {"ZoneTime": tm.get("zone_time")}}
    _, _, _, ivb, hb = _traj(pit)
    speed, spin = tm.get("rel_speed"), tm.get("spin_rate")
    if ivb is None or hb is None or speed is None or spin is None:
        return None
    return (float(speed), float(ivb), float(hb), float(spin))


def fit_samples(rows: list[tuple[float, float, float, float, str]]) -> PitcherSamples | None:
    """[(rel_speed, ivb, hb, spin, label), ...] → 標準化樣本；不足 MIN_N 回 None（純函式）。"""
    if len(rows) < MIN_N:
        return None
    x = np.array([r[:4] for r in rows], dtype=float)
    mu, sd = x.mean(axis=0), x.std(axis=0)
    sd[sd == 0] = 1.0
    return PitcherSamples(mu, sd, (x - mu) / sd, np.array([r[4] for r in rows]))


def estimate(samples: PitcherSamples, feats: tuple[float, float, float, float],
             k: int = K) -> str:
    """kNN 多數決（純函式）。同票時取較近者的標籤（Counter 依首見順序＝距離由近到遠）。"""
    q = (np.array(feats, dtype=float) - samples.mu) / samples.sd
    d = ((samples.z - q) ** 2).sum(axis=1)
    nearest = np.argsort(d, kind="stable")[:k]
    return Counter(samples.labels[nearest].tolist()).most_common(1)[0][0]


def _load_samples(year: int, acnts: list[str]) -> dict[str, PitcherSamples | None]:
    """一次查多位投手的本季已標逐球（一二軍合算）。"""
    by: dict[str, list[tuple]] = {a: [] for a in acnts}
    with conn() as c:
        rows = c.execute(
            "SELECT pitcher_acnt, rel_speed, ivb_cm, hb_cm, spin_rate, "
            "COALESCE(pitch_type_pred_v2, pitch_type_pred) FROM cpbl.pitch_tracking "
            "WHERE year=%s AND kind_code = ANY(%s) AND pitcher_acnt = ANY(%s) "
            "AND COALESCE(pitch_type_pred_v2, pitch_type_pred) IS NOT NULL "
            "AND rel_speed IS NOT NULL AND ivb_cm IS NOT NULL AND hb_cm IS NOT NULL "
            "AND spin_rate IS NOT NULL "
            "ORDER BY pitcher_acnt, kind_code, game_sno, pitch_cnt",
            (year, list(POOL_KINDS), acnts)).fetchall()
    for acnt, *vals in rows:
        by[acnt].append(tuple(vals))
    return {a: fit_samples(r) for a, r in by.items()}


def samples_for(year: int, acnts: set[str]) -> dict[str, PitcherSamples | None]:
    """帶 TTL 快取的樣本（API process 內）。只查快取沒有或過期的投手。"""
    now = time.monotonic()
    missing = [a for a in acnts
               if (year, a) not in _cache or now - _cache[(year, a)][0] > CACHE_TTL_SECONDS]
    if missing:
        for a, s in _load_samples(year, missing).items():
            _cache[(year, a)] = (now, s)
    return {a: _cache[(year, a)][1] for a in acnts}


def annotate(snapshot: dict | None, year: int) -> dict | None:
    """在公開快照的每顆 trackman 補 `pitch_type_est`，並移除軌跡輸入欄（就地修改後回傳）。

    `pitch_type_est`：推算得出的球種名；樣本不足或輸入缺欄為 None。
    """
    if not snapshot:
        return snapshot
    rows = [r for r in (snapshot.get("livelog") or []) if isinstance(r.get("trackman"), dict)]
    acnts = {str(r["PitcherAcnt"]) for r in rows if r.get("PitcherAcnt")}
    samples = samples_for(year, acnts) if acnts else {}
    for r in rows:
        tm = r["trackman"]
        s = samples.get(str(r.get("PitcherAcnt") or ""))
        feats = live_features(tm)
        tm["pitch_type_est"] = estimate(s, feats) if (s is not None and feats is not None) else None
        for key in _TRAJ_INPUTS:
            tm.pop(key, None)
    return snapshot
