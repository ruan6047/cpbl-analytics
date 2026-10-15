"""#287 第 1 次合併：`GET /api/v1/playoffs/comparison` 路由與區層級 status（#285 掛點契約 §2）。

路由測試以假 reader 取代 DB（不連任何庫）；真實資料下的 status 見 test_team_comparison_integration。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from cpbl.api.main import app
from cpbl.playoffs.team_comparison import reader

client = TestClient(app)


def test_route_returns_payload_body_without_envelope(monkeypatch):
    seen = {}

    def fake(season, series, *, connect=None, now=None):
        seen.update(season=season, series=series, connect=connect)
        return {"contract": reader.CONTRACT, "status": "ok", "context_version": "v", "series_id": {},
                "as_of": "t", "scopes": {}}

    monkeypatch.setattr(reader, "comparison_payload", fake)
    r = client.get("/api/v1/playoffs/comparison", params={"season": 2025, "series": "C"})
    assert r.status_code == 200
    assert r.json()["contract"] == "playoffs-comparison/v1" and r.json()["status"] == "ok"
    assert seen["season"] == 2025 and seen["series"] == "C" and seen["connect"] is not None


def test_read_failure_is_503_not_empty_200(monkeypatch):
    def boom(*a, **kw):
        raise RuntimeError("db down")

    monkeypatch.setattr(reader, "comparison_payload", boom)
    r = client.get("/api/v1/playoffs/comparison", params={"season": 2025, "series": "E"})
    assert r.status_code == 503
    assert "第 2 區" in r.json()["detail"]


@pytest.mark.parametrize("params", [{"season": 2025}, {"season": 2025, "series": "A"},
                                    {"season": 2025, "series": "c"}, {"season": "x", "series": "C"}])
def test_bad_params_are_422_and_do_not_read(monkeypatch, params):
    monkeypatch.setattr(reader, "comparison_payload", lambda *a, **k: pytest.fail("不應讀取"))
    assert client.get("/api/v1/playoffs/comparison", params=params).status_code == 422


def _scope(status, teams=True):
    return {"status": status, "teams": {"AAA011": {}} if teams else {}}


@pytest.mark.parametrize(("season", "h2h", "series", "expected"), [
    (_scope("available"), _scope("available"), _scope("available"), "ok"),
    (_scope("available"), _scope("available"), _scope("not_started", False), "ok"),
    (_scope("stale"), _scope("stale"), _scope("available"), "partial"),
    (_scope("available"), _scope("available"), _scope("pending_source"), "partial"),
    (_scope("available"), _scope("participants_pending", False), _scope("participants_pending", False), "partial"),
    (_scope("summary_missing", False), _scope("summary_missing", False), _scope("available"), "partial"),
    (_scope("summary_missing", False), _scope("summary_missing", False), _scope("not_started", False), "unavailable"),
])
def test_overall_status(season, h2h, series, expected):
    assert reader.overall_status({"season_a": season, "head_to_head_a": h2h, "series": series}) == expected
