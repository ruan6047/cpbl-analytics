"""GAME-RECAP-WP-API1 contract 紅燈＋API 測試（無 DB 依賴）。

紅燈核心：新 recap-wp API 必須**只消費 GAME-RECAP-PA1 canonical 打席**
（cpbl.game_plate_appearances），不得沿用 /winprob 的近似分組——
`(inning, half, batting_order, hitter)` 去重會把「同半局同打者二度上場」
（打線輪轉）合併成一個打席。本檔以合成事件流證明兩種分組產生不同打席數，
並以 contract 測試釘住新 API 回傳 canonical 打席數（近似分組實作必紅）。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from cpbl.ingest.pa_build import load_taxonomy, plate_appearances

TAX = load_taxonomy()


# ---------------------------------------------------------------------------
# 合成事件流：同半局同打者（同 batting_order）二度上場
# ---------------------------------------------------------------------------
def ev(
    no: int, hitter: str | None, *, inning: int = 1, half: str = "1", pitcher: str = "P1",
    pitch_cnt: int | None = None, action: str = "", change: bool = False,
    is_strike: bool = False, is_ball: bool = False, out: int = 0,
    order: int = 1, away: int = 0, home: int = 0,
) -> dict:
    return {
        "year": 2026, "kind_code": "A", "game_sno": 1,
        "main_event_no": f"{no:010d}",
        "inning_seq": inning, "visiting_home_type": half,
        "hitter_acnt": hitter, "pitcher_acnt": pitcher, "pitch_cnt": pitch_cnt,
        "action_name": action, "batting_action_name": "", "content": "",
        "is_strike": is_strike, "is_ball": is_ball, "is_score": False,
        "is_change_player": change, "is_special_event": False,
        "out_cnt": out, "ball_cnt": 0, "strike_cnt": 0,
        "first_base": None, "second_base": None, "third_base": None,
        "visiting_score": away, "home_score": home, "batting_order": order,
    }


# 一上：H1 安打 → H2 安打 → H1（同 batting_order=1，輪轉後二度上場）三振
REPEAT_BATTER_EVENTS = [
    ev(1, "H1", action="一壘安打", pitch_cnt=1, is_strike=True, order=1),
    ev(2, "H2", action="一壘安打", pitch_cnt=2, is_strike=True, order=2),
    ev(3, "H1", action="三振", pitch_cnt=3, is_strike=True, order=1),
    # 一下：主隊一個打席（讓比賽有下半局）
    ev(4, "B1", half="2", pitcher="P2", action="三振", pitch_cnt=1, is_strike=True, order=1),
]


def _legacy_pa_points(events: list[dict]) -> list[tuple]:
    """逐行複刻 routers/games.py `game_winprob` 的近似去重（紅燈對照基準）。"""
    items, seen = [], set()
    for e in sorted(events, key=lambda r: int(r["main_event_no"])):
        if e.get("is_change_player") or not e.get("hitter_acnt"):
            continue
        pa_key = (e["inning_seq"], str(e["visiting_home_type"]),
                  e.get("batting_order"), e["hitter_acnt"])
        if pa_key in seen:
            continue
        seen.add(pa_key)
        items.append(pa_key)
    return items


def _canonical_rows(events: list[dict]) -> list[dict]:
    """合成事件 → canonical PA rows（模擬 published build 的 DB 列）。"""
    return [{
        "pa_id": str(p.pa_id), "pa_index": p.pa_index, "state": p.state,
        "hitter_acnt": p.hitter_acnt, "start_pitcher_acnt": p.start_pitcher_acnt,
        "end_pitcher_acnt": p.end_pitcher_acnt, "result_action": p.result_action,
        "outcome_family": p.outcome_family, "pre_state": p.pre_state,
    } for p in plate_appearances(2026, "A", 1, events, TAX)]


# 最小 run_dist：只需上/下半局空壘 0 出局分布（其餘狀態 fallback）
DIST = {
    ("1", "___", 0): [0.7, 0.15, 0.08, 0.04, 0.02, 0.01, 0.0],
    ("2", "___", 0): [0.65, 0.17, 0.1, 0.05, 0.02, 0.01, 0.0],
}


def test_legacy_grouping_merges_repeat_batter() -> None:
    """近似分組缺陷實證：同半局同打者二度上場被合併（3 個真實打席只剩 2 點）。"""
    legacy = [k for k in _legacy_pa_points(REPEAT_BATTER_EVENTS) if k[1] == "1"]
    assert len(legacy) == 2  # H1 第二打席被去重吃掉
    canonical = [r for r in _canonical_rows(REPEAT_BATTER_EVENTS)
                 if r["state"] == "ready" and r["pre_state"]["half"] == "1"]
    assert len(canonical) == 3
    assert [r["hitter_acnt"] for r in canonical] == ["H1", "H2", "H1"]


# ---------------------------------------------------------------------------
# API contract（monkeypatch DB adapter；不碰真 DB）
# ---------------------------------------------------------------------------
@pytest.fixture()
def recap_module(monkeypatch):
    from cpbl.api.routers import recap

    recap._dist_cache.clear()
    recap._solver_cache.clear()
    monkeypatch.setattr(recap, "_load_dist", lambda span, kind: dict(DIST))
    yield recap
    recap._dist_cache.clear()
    recap._solver_cache.clear()


def _get(recap, monkeypatch, rows, game, **params):
    from cpbl.api.main import app

    monkeypatch.setattr(recap, "_load_pa_rows", lambda season, kind, sno: rows)
    monkeypatch.setattr(recap, "_load_game_row", lambda season, kind, sno: game)
    q = {"season": 2026, "kind_code": "A", **params}
    return TestClient(app).get("/api/v1/games/1/recap-wp", params=q)


def test_recap_api_returns_canonical_pa_not_legacy_grouping(recap_module, monkeypatch) -> None:
    """紅燈 contract：API 打席數 = canonical PA 數（近似分組實作在此必紅）。"""
    rows = _canonical_rows(REPEAT_BATTER_EVENTS)
    game = {"home_score": 0, "away_score": 1, "completed": True}
    resp = _get(recap_module, monkeypatch, rows, game)
    assert resp.status_code == 200
    body = resp.json()
    items = body["items"]
    # canonical：4 個打席（一上 3 + 一下 1），近似分組只會給 3
    assert len(items) == 4
    assert len(items) != len(_legacy_pa_points(REPEAT_BATTER_EVENTS))
    top = [i for i in items if i["half"] == "1" and i["inning"] == 1]
    assert [i["hitter"] for i in top] == ["H1", "H2", "H1"]
    # pa_id 全部相異且穩定（UUIDv5 canonical 身分）
    assert len({i["pa_id"] for i in items}) == 4
    assert body["completed"] is True
    # 逐列引用 PA1 契約欄位（不重建）：與 DB 列逐一對齊
    for it, r in zip(items, rows, strict=True):
        assert it["pa_id"] == r["pa_id"]
        assert it["state"] == r["state"]
        assert it["result"] == r["result_action"]


def test_recap_api_response_shape_and_model_metadata(recap_module, monkeypatch) -> None:
    rows = _canonical_rows(REPEAT_BATTER_EVENTS)
    game = {"home_score": 0, "away_score": 1, "completed": True}
    body = _get(recap_module, monkeypatch, rows, game).json()
    assert {"season", "kind_code", "game_sno", "completed", "final", "build_published",
            "model", "wp_reliability", "items"} <= set(body)
    m = body["model"]
    assert m["model_span"] == "2018-2025"
    assert m["model_kind"] == "A"
    assert m["distribution_source"] == "own"
    assert "model_built_at" in m  # run_dist artifact 無時戳欄位 → 誠實回 null
    assert m["model_built_at"] is None
    it = body["items"][0]
    assert {"pa_id", "pa_index", "state", "inning", "half", "outs_before", "bases_before",
            "away_score_before", "home_score_before", "hitter", "start_pitcher",
            "end_pitcher", "result", "outcome_family", "home_wp_before", "home_wp_after",
            "wpa", "beneficiary_team", "wp_status", "wp_unavailable_reason"} <= set(it)
    assert body["final"] == {"home_score": 0, "away_score": 1, "result": "away_win"}


def test_recap_api_ruleset_follows_kind_and_season(recap_module, monkeypatch) -> None:
    """延長規則參數化：2023 無突破僵局、2024+ tb10；C/E 無和局。"""
    rows = _canonical_rows(REPEAT_BATTER_EVENTS)
    game = {"home_score": 0, "away_score": 1, "completed": True}
    m23 = _get(recap_module, monkeypatch, rows, game, season=2023).json()["model"]
    m24 = _get(recap_module, monkeypatch, rows, game, season=2024).json()["model"]
    assert m23["ruleset"] == "cap12,tie"
    assert m24["ruleset"] == "cap12,tb10,tie"
    mc = _get(recap_module, monkeypatch, rows, game, kind_code="C").json()["model"]
    assert mc["ruleset"] == "cap20,no-tie"
    assert mc["model_kind"] == "A"
    assert mc["distribution_source"] == "borrowed"


def test_recap_api_model_not_built_fails_closed(recap_module, monkeypatch) -> None:
    """D scope（生產無自身分布 artifact）：保留事件列，WP 全欄不可用。"""
    def raise_missing(span, kind):
        raise RuntimeError(f"run_dist 無 {span}/{kind}")
    monkeypatch.setattr(recap_module, "_load_dist", raise_missing)
    rows = _canonical_rows(REPEAT_BATTER_EVENTS)
    game = {"home_score": 0, "away_score": 1, "completed": True}
    body = _get(recap_module, monkeypatch, rows, game, kind_code="D").json()
    assert body["model"] is None
    assert len(body["items"]) == 4  # 事件列保留
    assert all(i["wp_status"] == "unavailable" for i in body["items"])
    assert all(i["wp_unavailable_reason"] == "model_not_built" for i in body["items"])
    assert all(i["home_wp_before"] is None for i in body["items"])


def test_recap_api_unknown_game_404(recap_module, monkeypatch) -> None:
    resp = _get(recap_module, monkeypatch, [], None)
    assert resp.status_code == 404


def test_recap_api_no_published_build(recap_module, monkeypatch) -> None:
    """games 有列但無 published build：不猜、items 空、build_published=false。"""
    game = {"home_score": 3, "away_score": 1, "completed": True}
    body = _get(recap_module, monkeypatch, [], game).json()
    assert body["build_published"] is False
    assert body["items"] == []
