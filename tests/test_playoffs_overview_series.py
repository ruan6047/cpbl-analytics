"""#285 批次 B WP-S1：overview 選填 ``series``（``/playoffs?series=E|C``）。

場次取 2026 真實 E1–E4、C1–C7（``tests/fixtures/postseason_real_years.json``）；S02 預設系列為 C。
所選系列只換組裝的軸；``default_series``、``context_version`` 照舊是 S02 原值。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from postseason_context_inputs import BRO, NOW_2026, games, inputs

from cpbl import postseason_contract as pc
from cpbl.api.main import app
from cpbl.playoffs import overview as ov
from cpbl.playoffs import series_summary as ss

client = TestClient(app)


def _inputs(games_override=None) -> ov.OverviewInputs:
    ctx = pc.compute_series_context(inputs(2026, games_override=games_override), now=NOW_2026)
    return ov.OverviewInputs(context=ctx, names={}, series_summary=ss.aggregate_all(ctx, None), summary_names={})


def test_without_series_only_adds_selected_series():
    i = _inputs()
    o = ov.compute_overview(i)
    assert o["default_series"] == "C" and o["selected_series"] == "C"
    assert ov.compute_overview(i, None) == o
    # 與未加參數前相同：除 selected_series 外各欄仍以 S02 預設系列為軸
    assert o["series_section"]["current"]["kind_code"] == "C"
    assert o["series_section"]["previous"]["kind_code"] == "E"
    assert o["sections"]["watch"]["series"] == "C"
    assert o["series_id"] == i.context["series"]["C"]["series_id"]


def test_series_c_equals_default():
    i = _inputs()
    assert ov.compute_overview(i, "C") == ov.compute_overview(i)


def test_series_e_switches_axis_and_matches_c_page_previous():
    i = _inputs()
    e = ov.compute_overview(i, "E")
    c = ov.compute_overview(i)
    assert e["default_series"] == "C" and e["selected_series"] == "E"
    ss_e = e["series_section"]
    assert ss_e["current"]["kind_code"] == "E" and ss_e["previous"] is None
    assert ss_e["current"]["winner"] == BRO and ss_e["current"]["series_status"] == "decided"
    assert ss_e["next_game"] is None and ss_e["next_game_missing_reason"] == "series_decided"
    assert e["series_id"] == i.context["series"]["E"]["series_id"]
    assert e["target_game_key"] == i.context["state"]["by_series"]["E"]["target_game_key"]
    assert e["sections"]["watch"]["series"] == "E"
    # 6214203757：E 頁與 C 頁 previous 位置同源
    assert ss_e["current"] == c["series_section"]["previous"]
    assert e["series_summary"]["current"]["kind_code"] == "E" and e["series_summary"]["previous"] is None
    # 批次 E 方案 A：C 頁不再帶挑戰賽累計榜；E 頁 current 自證為 E 的累計榜
    assert c["series_summary"]["previous"] is None
    assert e["series_summary"]["current"] == ss.summary_json(i.series_summary, i.summary_names, current="E",
                                                             previous=None)["current"]


def test_context_version_and_manifest_do_not_depend_on_series():
    i = _inputs()
    e, c = ov.compute_overview(i, "E"), ov.compute_overview(i, "C")
    assert e["context_version"] == c["context_version"] == i.context["context_version"]
    assert e["source_manifest"] == c["source_manifest"]


def test_series_e_without_e_rows_degrades_not_raises():
    only_c = [g for g in games(2026) if g.kind_code == "C"]
    o = ov.compute_overview(_inputs(only_c), "E")
    ss_e = o["series_section"]
    assert o["selected_series"] == "E"
    assert "series_games_missing" in ss_e["missing_reason"]
    assert ss_e["current"]["kind_code"] == "E" and ss_e["current"]["games"] == []
    assert ss_e["previous"] is None


@pytest.mark.parametrize(("params", "expected"), [
    ({"season": 2026}, None), ({"season": 2026, "series": "E"}, "E"), ({"season": 2026, "series": "C"}, "C")])
def test_route_passes_series(monkeypatch, params, expected):
    seen = {}

    def fake(season, *, series=None, connect=None, live_reader=None, now=None):
        seen.update(season=season, series=series)
        return {"contract": ov.CONTRACT, "selected_series": series or "C"}

    monkeypatch.setattr(ov, "playoffs_overview", fake)
    r = client.get("/api/v1/playoffs/overview", params=params)
    assert r.status_code == 200
    assert seen == {"season": 2026, "series": expected}


@pytest.mark.parametrize("bad", ["A", "c", "e", "EC", ""])
def test_route_rejects_bad_series(monkeypatch, bad):
    monkeypatch.setattr(ov, "playoffs_overview", lambda *a, **k: pytest.fail("不應讀取"))
    assert client.get("/api/v1/playoffs/overview", params={"season": 2026, "series": bad}).status_code == 422
