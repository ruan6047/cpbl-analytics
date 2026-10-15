"""#293 S12 WP1：季後三來源（final／box／PA）分類器。

樣本是**真實資料**：``tests/fixtures/postseason_sources_2026_real.json`` 由
``cpbl.postseason_sources.load_local_facts`` 對本機 cpbl 唯讀查出（2026 E1–E4 實際完賽場、C1 賽前），
出處與時刻記在檔內 ``_provenance``。需要「box 晚到／官方更正／對帳不等」等情境時，只在真實樣本上
改動與該情境直接相關的欄位，並在測試名稱寫明；⛔ 不宣稱這些情境在真實事件中已發生。
"""

from __future__ import annotations

import dataclasses
import inspect
import json
from datetime import date, datetime
from pathlib import Path

import pytest

from cpbl import postseason_sources as ps
from cpbl.completion import is_completed_game

FIXTURE = Path(__file__).parent / "fixtures" / "postseason_sources_2026_real.json"
TPE = ps.TAIPEI


def _real() -> dict[str, ps.LocalFacts]:
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return {k: ps.facts_from_json(v) for k, v in raw["games"].items()}


def _manifest(facts: ps.LocalFacts, at: str, *, box_ok: bool = True, pa_ok: bool | None = True) -> dict:
    """與 boxpa_sync.reconcile 的 games[key] 同形（加上 at）；計數取該場真實本機計數。"""
    return {"at": at, "box_ok": box_ok, "pa_ok": pa_ok, "pa_sent": True,
            "box": {t: {"local": n, "prod": n} for t, n in facts.box_counts.items()},
            "pa": {t: {"local": n, "prod": n} for t, n in facts.pa_counts.items()},
            "published_build_local": facts.published_build, "published_build_prod": facts.published_build}


NOW = datetime(2026, 10, 15, 12, 0, tzinfo=TPE)


def test_core_tables_match_the_daily_chain_detail_contract():
    from cpbl.ingest.run_refresh_recent import _POSTSEASON_CORE_DETAIL_TABLES
    assert ps.BOX_CORE_TABLES == _POSTSEASON_CORE_DETAIL_TABLES
    from cpbl.ingest.boxpa_sync import BOX_TABLES, PA_TABLES
    assert set(ps.BOX_ALL_TABLES) == set(BOX_TABLES) and ps.PA_TABLES == PA_TABLES


def test_real_e1_to_e4_baseline_none_reached_same_night():
    """F6 基線（真實）：E1–E4 本機 box／PA 都在賽事日 24:00 之後才到 → 同晚未達；
    本模組沒有 production 端證據（每日鏈送達不經 scoped manifest）→ unknown，不推定已送達。"""
    facts = _real()
    for key in ("2026-E-1", "2026-E-2", "2026-E-3", "2026-E-4"):
        out = ps.classify(facts[key], None, NOW)
        assert facts[key].completed
        assert out["box"].status == ps.UNKNOWN and out["box"].reason == "no_prod_evidence"
        assert out["pa"].status == ps.UNKNOWN
        assert out["box"].same_night is False, key
        assert out["pa"].same_night is False, key
    # E1 是唯一 final 在跨日 03:09 才入本機的一場（真實），其餘 final 在隔日 10:10 才入本機。
    assert facts["2026-E-1"].final_first_seen.startswith("2026-10-10T03:09")


def test_real_c1_before_first_pitch_is_pending_not_final():
    c1 = _real()["2026-C-1"]
    assert not c1.completed
    out = ps.classify(c1, None, NOW)
    assert {k: (v.status, v.reason) for k, v in out.items()} == {
        "final": (ps.PENDING, "not_final"), "box": (ps.PENDING, "not_final"), "pa": (ps.PENDING, "not_final")}
    assert all(v.same_night is None for v in out.values()), "界線（10/18 00:00）未到＝未定"
    late = ps.classify(c1, None, datetime(2026, 10, 18, 0, 0, tzinfo=TPE))
    assert all(v.same_night is False for v in late.values()), "界線已過仍未送達＝同晚未達"


@pytest.mark.parametrize(("delivered_at", "expected"), [
    ("2026-10-12T23:59:59+08:00", True),
    ("2026-10-13T00:00:00+08:00", False),
    ("2026-10-12T15:59:59+00:00", True),    # UTC 表示的 23:59:59 台北
    ("2026-10-12T16:00:00+00:00", False),   # UTC 表示的 00:00 台北
])
def test_same_night_boundary_is_taipei_midnight(delivered_at, expected):
    e4 = dataclasses.replace(_real()["2026-E-4"], box_local_at="2026-10-12T22:30:00+08:00",
                             published_at="2026-10-12T22:31:00+08:00")
    out = ps.classify(e4, _manifest(e4, delivered_at), NOW, final_prod_at="2026-10-12T22:10:00+08:00")
    assert out["box"].status == ps.DELIVERED and out["pa"].status == ps.DELIVERED
    assert out["box"].same_night is expected and out["pa"].same_night is expected
    assert out["final"].same_night is True


def test_final_first_then_box_missing_keeps_box_and_pa_pending_independently():
    """主風險「final 先到造成假齊備」：final 已送達不讓 box／PA 變成完整。
    樣本＝真實 E4，只把 livelog 列數改成 0、拿掉 published（模擬 box 尚未抓到的時點）。"""
    e4 = _real()["2026-E-4"]
    early = dataclasses.replace(e4, box_counts={**e4.box_counts, "game_livelog": 0},
                                published_build=None, published_at=None)
    out = ps.classify(early, None, NOW, final_prod_at="2026-10-12T22:10:00+08:00")
    assert out["final"].status == ps.DELIVERED
    assert out["box"] == ps.SourceStatus(ps.PENDING, "local_box_incomplete:game_livelog", None, None, False)
    assert out["pa"].status == ps.PENDING and out["pa"].reason == "no_local_published_build"


def test_box_delivered_while_pa_pending_only_pa_waits():
    """只有真正依賴 PA 的讀取面等 PA：box 對帳通過、PA 尚無 published → box delivered／PA pending。"""
    e4 = _real()["2026-E-4"]
    no_pa = dataclasses.replace(e4, published_build=None, published_at=None)
    m = _manifest(no_pa, "2026-10-12T22:40:00+08:00", pa_ok=None)
    out = ps.classify(no_pa, m, NOW, final_prod_at="2026-10-12T22:10:00+08:00")
    assert out["box"].status == ps.DELIVERED and out["box"].same_night is True
    assert out["pa"].status == ps.PENDING and out["pa"].reason == "no_local_published_build"


def test_tracking_late_pitch_tracking_zero_is_not_a_box_gap():
    """逐球官方可能 0 球：pitch_tracking=0 不算 box 缺；但對帳仍比列數。"""
    e4 = _real()["2026-E-4"]
    zero = dataclasses.replace(e4, box_counts={**e4.box_counts, "pitch_tracking": 0})
    out = ps.classify(zero, _manifest(zero, "2026-10-12T22:40:00+08:00"), NOW)
    assert out["box"].status == ps.DELIVERED


def test_reconcile_mismatch_retries_once_then_conflict():
    e4 = _real()["2026-E-4"]
    m = _manifest(e4, "2026-10-12T22:40:00+08:00", box_ok=False, pa_ok=False)
    first = ps.classify(e4, m, NOW)
    assert (first["box"].status, first["box"].reason) == (ps.PENDING, "reconcile_mismatch_retrying")
    final = ps.classify(e4, m, NOW, retries_exhausted=True)
    assert final["box"].status == ps.CONFLICT and final["pa"].status == ps.CONFLICT


def test_official_correction_keeps_pa_pending_even_if_published_synced():
    e4 = dataclasses.replace(_real()["2026-E-4"], reconciliation_outstanding=1)
    out = ps.classify(e4, _manifest(e4, "2026-10-12T22:40:00+08:00"), NOW)
    assert out["box"].status == ps.DELIVERED
    assert (out["pa"].status, out["pa"].reason) == (ps.PENDING, "official_correction_pending")


def test_local_changed_after_sync_is_pending_again():
    e4 = _real()["2026-E-4"]
    m = _manifest(e4, "2026-10-12T22:40:00+08:00")
    grown = dataclasses.replace(e4, box_counts={**e4.box_counts, "game_livelog": 356})
    assert ps.classify(grown, m, NOW)["box"].reason == "local_changed_since_sync"
    rebuilt = dataclasses.replace(e4, published_build="00000000-0000-0000-0000-000000000000")
    assert ps.classify(rebuilt, m, NOW)["pa"].reason == "local_changed_since_sync"


# ------------------------------------------------------------------ G03：只有 cpbl.completion 算完賽

@pytest.mark.parametrize("case", ["nonzero_score", "date_passed", "refresh_succeeded"])
def test_g03_false_completions_are_not_final(case):
    """G03：非零比分、時間已過、refresh 成功都不等於完賽。

    * 分類器只吃 ``LocalFacts.completed``（沒有比分、refresh 欄位可讀）；
    * ``completed`` 由 :func:`load_local_facts` 以 ``completed_games_sql_with_evidence`` 產生；
      2026 季後（official_required）時比分與日期都不構成完賽。"""
    fields = {f.name for f in dataclasses.fields(ps.LocalFacts)}
    assert not fields & {"home_score", "away_score", "refresh_ok", "present_status"}
    assert "refresh_log" not in inspect.getsource(ps)
    loader = inspect.getsource(ps.load_local_facts)
    assert "completed_games_sql_with_evidence" in loader and "home_score" not in loader
    score = (3, 2) if case == "nonzero_score" else (0, 0)
    as_of = date(2026, 10, 20) if case in ("date_passed", "nonzero_score") else date(2026, 10, 17)
    assert is_completed_game(*score, date(2026, 10, 17), as_of, official_required=True) is False
    c1 = _real()["2026-C-1"]
    assert ps.classify(c1, None, NOW)["final"].reason == "not_final"


def test_loader_against_local_db_matches_real_fixture_shape():
    """有本機 DB 時：loader 對 E1–E4 讀出的已完賽／到齊事實與快照一致（E 系列已結束、不再變動）。"""
    try:
        from cpbl.db import conn
        with conn() as c:
            c.execute("SET TRANSACTION READ ONLY")
            live = ps.load_local_facts(c.cursor(), [(2026, "E", n) for n in (1, 2, 3, 4)])
    except Exception as exc:  # noqa: BLE001 — 無 DB 時照既有慣例 skip
        pytest.skip(f"本機 DB 不可用：{type(exc).__name__}")
    snap = _real()
    for key, facts in live.items():
        assert facts.completed and facts.box_counts == snap[key].box_counts, key
        assert facts.published_build == snap[key].published_build, key
