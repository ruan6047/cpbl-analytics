"""路由快照：56 個端點一個都不能少（拆分 main.py 為 routers 時的守門測試）。

新增端點時把路徑加進 EXPECTED；若這條測試因「少了路徑」而 fail，代表重構
弄丟了端點，不是快照過期。
"""

from __future__ import annotations

from fastapi.routing import APIRoute

from cpbl.api.main import app

EXPECTED = {
    "/api/info",
    "/api/v1/franchises",
    "/api/v1/games/calendar",
    "/api/v1/games/recent",
    "/api/v1/games/{game_sno}/live",
    "/api/v1/games/{game_sno}/milestones",
    "/api/v1/games/{game_sno}/umpire",
    "/api/v1/games/{game_sno}/winprob",
    "/api/v1/matchups",
    "/api/v1/outcome/backtest",
    "/api/v1/outcome/evaluate",
    "/api/v1/outcome/features",
    "/api/v1/outcome/matchups",
    "/api/v1/outcome/simulate",
    "/api/v1/outcome/teams",
    "/api/v1/people/coach/{name}",
    "/api/v1/people/umpire/{name}",
    "/api/v1/players/roster",
    "/api/v1/players/{player_id}/ability-card",
    "/api/v1/players/{player_id}/advanced",
    "/api/v1/players/{player_id}/arsenal",
    "/api/v1/players/{player_id}/batting",
    "/api/v1/players/{player_id}/career",
    "/api/v1/players/{player_id}/discipline",
    "/api/v1/players/{player_id}/fielding",
    "/api/v1/players/{player_id}/matchups",
    "/api/v1/players/{player_id}/movement",
    "/api/v1/players/{player_id}/pitch-mix",
    "/api/v1/players/{player_id}/pitching",
    "/api/v1/players/{player_id}/profile",
    "/api/v1/players/{player_id}/sabr",
    "/api/v1/players/{player_id}/season",
    "/api/v1/players/{player_id}/splits",
    "/api/v1/players/{player_id}/traits",
    "/api/v1/players/{player_id}/trend",
    "/api/v1/players/{player_id}/trend-career",
    "/api/v1/players/{player_id}/vs-team",
    "/api/v1/postseason-summary",
    "/api/v1/projections/batting",
    "/api/v1/projections/pitching",
    "/api/v1/records",
    "/api/v1/records/championships",
    "/api/v1/season/batting-leaders",
    "/api/v1/season/fielding",
    "/api/v1/season/pitching-leaders",
    "/api/v1/season/standings",
    "/api/v1/seasons",
    "/api/v1/special-records",
    "/api/v1/standings",
    "/api/v1/standings-trend",
    "/api/v1/teams",
    "/api/v1/teams/{code}/der",
    "/api/v1/teams/{code}/eras",
    "/api/v1/teams/{code}/players",
    "/api/v1/umpires",
    "/api/v1/venues",
    "/api/v1/venues/{venue}/factors",
    "/api/v1/venues/{venue}/players",
    "/api/v1/venues/{venue}/stats",
    "/healthz",
}


def test_all_routes_present():
    actual = {r.path for r in app.routes if isinstance(r, APIRoute)}
    missing = EXPECTED - actual
    extra = actual - EXPECTED
    assert not missing, f"重構弄丟端點: {sorted(missing)}"
    assert not extra, f"快照過期，新端點請加入 EXPECTED: {sorted(extra)}"


def test_all_routes_are_get_only():
    """API 唯讀契約：只允許 GET（含自動 HEAD 不在此列）。"""
    for r in app.routes:
        if isinstance(r, APIRoute):
            assert r.methods <= {"GET", "HEAD"}, f"{r.path} 有非 GET 方法: {r.methods}"
