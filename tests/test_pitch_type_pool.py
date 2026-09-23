"""球種推算一二軍合算分群樣本（2026-09-23）的離線單元測試（無 DB 依賴）。

合算的依據與範圍見 `cpbl.models.pitch_type` 模組 docstring。這裡守住四件事：
1. 合算樣本與目標 kind 無關（同一投手一二軍兩次執行，KMeans 輸入逐位相同）。
2. 合算後 key 必含 kind——一二軍的 game_sno 會重號，少了 kind 會互相覆蓋。
3. 合算真的讓「單邊不足 MIN_N、合計足夠」的投手得到分群命名（這正是本改動要買的東西）。
4. 寫回只寫本次的 kind。
"""

from __future__ import annotations

import numpy as np
import pytest

from cpbl.models import pitch_type as pt


def _arsenal(kind: str, n: int, seed: int, acnt: str = "P1") -> list[dict]:
    """右投、四縫＋滑球各半：四縫 145km/h／IVB 45／臂側 HB −20、滑球 128／IVB 5／手套側 +20。"""
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n):
        fb = i % 2 == 0
        rows.append({
            "kind_code": kind, "pitcher_acnt": acnt,
            "game_sno": 1 + i // 50, "pitch_cnt": i % 50 + 1,     # 一二軍刻意用同一組場次號
            "rel_speed": (145.0 if fb else 128.0) + rng.normal(0, 1),
            "ivb_cm": (45.0 if fb else 5.0) + rng.normal(0, 2),
            "hb_cm": (-20.0 if fb else 20.0) + rng.normal(0, 2),
            "spin_rate": (2300.0 if fb else 2500.0) + rng.normal(0, 50),
            "rel_side": 1.5,
            "tagged_pitch_type": "fastball" if fb else "breakingball",
        })
    return rows


def _loaded(a_rows: list[dict], d_rows: list[dict]) -> dict[str, dict[str, list[dict]]]:
    return {"A": {"P1": a_rows}, "D": {"P1": d_rows}}


def _games(rows: list[dict]) -> set[int]:
    return {r["game_sno"] for r in rows}


def test_pool_for_pairs_major_and_farm_only() -> None:
    assert pt._pool_for("A") == pt._pool_for("D") == ("A", "D")
    assert pt._pool_for("C") == ("C",)            # 季後賽等其餘 kind 維持只用自己
    assert pt._pool_for("E") == ("E",)


def test_pooled_sample_does_not_depend_on_target_kind() -> None:
    """同一投手一二軍兩次執行的分群輸入必須逐位相同，否則兩邊標籤對不上。"""
    a, d = _arsenal("A", 60, 1), _arsenal("D", 60, 2)
    loaded = _loaded(a, d)
    complete = {"A": _games(a), "D": _games(d) - {2}}          # 二軍第 2 場覆蓋不完整

    for_a = pt._pooled_rows("P1", loaded, complete, pt._pool_for("A"))
    for_d = pt._pooled_rows("P1", loaded, complete, pt._pool_for("D"))

    assert for_a == for_d
    assert [r["kind_code"] for r in for_a] == ["A"] * 60 + ["D"] * 50   # 固定一軍在前
    assert all(not (r["kind_code"] == "D" and r["game_sno"] == 2) for r in for_a)


def test_keys_include_kind_so_shared_game_numbers_do_not_collide() -> None:
    a, d = _arsenal("A", 100, 1), _arsenal("D", 100, 2)

    result = pt._classify_pitcher(a + d)

    assert len(result) == 200                                   # 少了 kind 只會剩 100
    assert {k for k, _, _ in result} == {"A", "D"}


def test_pooling_lets_a_short_major_sample_get_real_names() -> None:
    """一軍 100 顆單獨算不足 MIN_N → 滑球只能退回「變化球」；合算 200 顆 → 得到「滑球/橫掃」。"""
    assert 100 < pt.MIN_N <= 200
    a, d = _arsenal("A", 100, 1), _arsenal("D", 100, 2)
    a_sliders = {(r["kind_code"], r["game_sno"], r["pitch_cnt"]) for r in a
                 if r["tagged_pitch_type"] == "breakingball"}

    alone = pt._classify_pitcher(a)
    pooled = pt._classify_pitcher(a + d)

    assert {alone[k] for k in a_sliders} == {"變化球"}
    assert {pooled[k] for k in a_sliders} == {"滑球/橫掃"}


@pytest.mark.parametrize("kind", ["A", "D"])
def test_classify_writes_only_the_target_kind(monkeypatch: pytest.MonkeyPatch, kind: str) -> None:
    a, d = _arsenal("A", 100, 1), _arsenal("D", 100, 2)
    rows_by_kind = {"A": a, "D": d}
    written: dict = {}

    monkeypatch.setattr(pt, "_load", lambda year, k: {"P1": rows_by_kind[k]})
    monkeypatch.setattr(pt, "_complete_games", lambda year, k: _games(rows_by_kind[k]))

    def fake_write(year: int, k: str, preds: list) -> int:
        written["kind"], written["preds"] = k, preds
        return len(preds)

    monkeypatch.setattr(pt, "_write", fake_write)

    summary = pt.classify(2026, kind)

    own = {(r["game_sno"], r["pitch_cnt"]) for r in rows_by_kind[kind]}
    assert written["kind"] == kind
    assert {(g, pc) for g, _, pc, _ in written["preds"]} == own     # 只寫本次 kind、一顆不漏
    assert summary["pooled_pitchers"] == 1 and summary["gmm"] == 1 and summary["fallback"] == 0
    sliders = {(r["game_sno"], r["pitch_cnt"]) for r in rows_by_kind[kind]
               if r["tagged_pitch_type"] == "breakingball"}
    assert {p for g, _, pc, p in written["preds"] if (g, pc) in sliders} == {"滑球/橫掃"}
