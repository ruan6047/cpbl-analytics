"""紀錄室 API（RECORD-API1）：冠軍編的 coverage 紅線與並列排名。"""

from __future__ import annotations

import pytest

from cpbl.ingest.championships import championship_coverage


def _client():
    from fastapi.testclient import TestClient

    from cpbl.api.main import app
    return TestClient(app)


def _get(path: str):
    try:
        r = _client().get(path)
    except Exception as exc:  # noqa: BLE001 — 無 DB 時跳過（CI 無 Postgres）
        pytest.skip(f"需本機 DB：{exc}")
    if r.status_code != 200:
        pytest.skip(f"需本機 DB（{r.status_code}）")
    return r.json()


def test_coverage_is_always_present():
    """**紅線**：coverage 必須隨回應附帶——缺年時前端才有辦法降級，不出「歷史最多」結論。"""
    d = _get("/api/v1/records/championships")

    assert "coverage" in d
    assert {"from_year", "through_year", "complete", "missing_years"} <= set(d["coverage"])


def test_rankings_only_when_coverage_complete():
    """coverage 不完整時**不得**回傳累計排行——由 API 擋，而非交給前端自律。"""
    d = _get("/api/v1/records/championships")

    if d["coverage"]["complete"]:
        assert "franchise_ranking" in d
        assert "player_ranking" in d
    else:
        assert "franchise_ranking" not in d
        assert "player_ranking" not in d
        assert "note" in d


def test_championship_totals_reconcile_with_seasons():
    """球團王朝榜的總座數必須等於總季數——對不上代表 franchise 映射漏人。"""
    d = _get("/api/v1/records/championships")
    if not d["coverage"]["complete"]:
        pytest.skip("coverage 未完整，無累計排行")

    assert sum(t["titles"] for t in d["franchise_ranking"]) == len(d["seasons"])


def test_ties_share_the_same_rank():
    """**並列排名**：同數值同名次。舊版直接 LIMIT 會把同分者任意切掉＝假排名。"""
    d = _get("/api/v1/records/championships")
    if not d["coverage"]["complete"]:
        pytest.skip("coverage 未完整")

    by_titles: dict[int, set[int]] = {}
    for t in d["franchise_ranking"]:
        by_titles.setdefault(t["titles"], set()).add(t["rk"])
    for titles, ranks in by_titles.items():
        assert len(ranks) == 1, f"{titles} 座的球團拿到不同名次 {ranks}"


def test_career_leaders_use_tie_aware_rank():
    d = _get("/api/v1/records?limit=3")

    hr = d["career_batting"]["hr"]
    assert hr and all("rk" in r and "active" in r for r in hr)
    assert hr[0]["rk"] == 1
    for a, b in zip(hr, hr[1:], strict=False):        # 值遞減、名次不遞減
        assert a["val"] >= b["val"]
        assert a["rk"] <= b["rk"]


def test_limit_applies_to_franchise_ranking():
    """`limit` 必須套用到球團王朝榜（RECORD-API1-FIX1）。

    並列排名下 limit=1 應回「並列第一的所有球團」，而不是整份五隊全回。
    """
    d = _get("/api/v1/records/championships?limit=1")
    if not d["coverage"]["complete"]:
        pytest.skip("coverage 未完整")

    fr = d["franchise_ranking"]
    assert fr, "球團榜不應為空"
    assert {t["rk"] for t in fr} == {1}, "limit=1 只該留下第一名（並列者可多列）"
    assert len(fr) < len(_get("/api/v1/records/championships?limit=10")["franchise_ranking"])


def test_active_includes_current_season_stats_source():
    """現役＝登錄名單 ∪ 本季有成績（RECORD-API1-FIX1）。

    只查 `team_roster` 會把「本季有成績但已離隊/升降不在現行名單」者誤標為非現役
    （查核者以張志豪為例）。生涯榜與冠軍榜必須共用同一份定義。
    """
    d = _get("/api/v1/records/championships?limit=50")
    if not d["coverage"]["complete"]:
        pytest.skip("coverage 未完整")

    champ = {p["pid"]: p["active"] for p in d["player_ranking"]}

    car = _get("/api/v1/records?limit=50")
    career_active = {r["pid"] for grp in car["career_batting"].values() for r in grp if r["active"]}

    # 生涯榜認定為現役者，若同時在冠軍榜上，冠軍榜也必須標現役。
    # 方向很重要：原 bug 是冠軍榜**漏標**，反向斷言恆綠、抓不到。
    overlap = career_active & champ.keys()
    if not overlap:
        pytest.skip("兩榜無現役重疊者")
    for pid in overlap:
        assert champ[pid], f"{pid} 在生涯榜為現役、冠軍榜卻標成非現役"


def test_coverage_contract_fails_closed_on_missing_year():
    """契約函式本身（不需 DB）：缺一年就必須 complete=false。"""
    full = list(range(1990, 2026))

    assert championship_coverage(full, as_of=None)["complete"] is True
    assert championship_coverage([y for y in full if y != 2013], as_of=None)["complete"] is False
    assert championship_coverage(
        [y for y in full if y != 2013], as_of=None)["missing_years"] == [2013]
