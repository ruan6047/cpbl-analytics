"""球種推算接進每日鏈（2026-09-23）的離線單元測試（無 DB 依賴）。

推算原本不在任何排程裡，07-08 之後的新球全是 NULL、兩個半月無人發現。這裡守住：
1. 順序：每個 kind 都是 v1 → v2 → v2 重分群（v2 讀 v1 剛寫的標籤）。
2. 失敗隔離：一段失敗只記錄、不外拋，其餘 kind 照跑（fail closed，不擋同步）。
3. 失敗看得見：main() 轉成 refresh_log ok=false、note、退出碼 69，且後續步驟照跑。
4. `fast` 模式不跑。
"""

from __future__ import annotations

import pytest

from cpbl.ingest import cpbl_gamelog
from cpbl.ingest import run_refresh_recent as rr
from cpbl.models import pitch_type, pitch_type_v2


def _patch_models(monkeypatch: pytest.MonkeyPatch, calls: list[str], fail: set[str] | None = None):
    fail = fail or set()

    def make(stage: str):
        def fn(year: int, kind: str) -> dict:
            calls.append(f"{kind}:{stage}")
            if f"{kind}:{stage}" in fail:
                raise RuntimeError(f"boom {kind} {stage}")
            return {"stage": stage}
        return fn

    monkeypatch.setattr(pitch_type, "classify", make("v1"))
    monkeypatch.setattr(pitch_type_v2, "classify_v2", make("v2"))
    monkeypatch.setattr(pitch_type_v2, "recluster_v2", make("v2_recluster"))


def test_step_runs_v1_then_v2_then_recluster_for_each_kind(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    _patch_models(monkeypatch, calls)

    out = rr._pitch_type_step(2026)

    assert calls == ["A:v1", "A:v2", "A:v2_recluster", "D:v1", "D:v2", "D:v2_recluster"]
    assert out["errors"] == []


def test_step_failure_is_recorded_and_does_not_stop_the_other_kind(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    _patch_models(monkeypatch, calls, fail={"A:v2"})

    out = rr._pitch_type_step(2026)       # 不得拋出

    assert calls == ["A:v1", "A:v2", "D:v1", "D:v2", "D:v2_recluster"]   # A 的重分群沒跑
    assert [(e["kind"], e["stage"]) for e in out["errors"]] == [("A", "v2")]


def _stub_chain(monkeypatch: pytest.MonkeyPatch, *, fast: bool, pitch_type_result: dict,
                calls: list[str], logged: dict) -> None:
    """把每日鏈其餘步驟換成替身，只留「推算結果怎麼傳遞」這條線（比照 test_standings_year_guard）。"""
    monkeypatch.setattr(rr, "_GAMELOG_GAPS", [])
    monkeypatch.setattr(rr.sys, "argv", ["cpbl-refresh-recent"] + (["fast"] if fast else []))
    for name, value in (
        ("migrate", lambda: None),
        ("scrape_games", lambda *a, **k: 0),
        ("scrape_all", lambda *a, **k: {}),
        ("scrape_standings", lambda *a, **k: {}),
        ("standings_failures", lambda: []),
        ("reset_standings_failures", lambda: None),
        ("scrape_transactions", lambda *a, **k: 0),
        ("build_championships", lambda *a, **k: 0),
        ("_incremental_detail", lambda *a, **k: {}),
        ("scrape_game_details", lambda *a, **k: 0),
        ("build_splits", lambda *a, **k: calls.append("splits") or {}),
        ("build_career", lambda *a, **k: 0),
        ("_sync_player_names", lambda: 0),
        ("_recent_counts", lambda *a, **k: []),
        ("_missing_gamelog_snos", lambda _year, _kc: []),
        ("_pa_build_step", lambda *a, **k: calls.append("pa_build") or {
            "games": 0, "actions": {}, "build_states": {}, "errors": []}),
        ("_pitch_type_step", lambda year: calls.append("pitch_type") or pitch_type_result),
        ("_log_refresh", lambda _s, _f, _t, _tot, _c, detail, ok, note:
            logged.update(ok=ok, note=note, detail=detail)),
    ):
        monkeypatch.setattr(rr, name, value)


def test_failure_is_visible_as_69_without_stopping_later_steps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    logged: dict = {}
    result = {"errors": [{"kind": "A", "stage": "v2", "error": "boom"}]}
    _stub_chain(monkeypatch, fast=False, pitch_type_result=result, calls=calls, logged=logged)

    with pytest.raises(SystemExit) as e:
        rr.main()

    assert e.value.code == cpbl_gamelog.EXIT_INCOMPLETE_SCRAPE == 69
    assert calls == ["pa_build", "pitch_type", "splits"], "推算失敗不得中止後續步驟"
    assert logged["ok"] is False
    assert "球種推算失敗：A/v2" in logged["note"]
    assert logged["detail"]["pitch_type"] == result


def test_clean_run_is_ok_and_exits_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    """負控制：推算零錯誤時 ok=True、不亮 69（69 不是隨便亮的）。"""
    calls: list[str] = []
    logged: dict = {}
    _stub_chain(monkeypatch, fast=False, pitch_type_result={"errors": []}, calls=calls, logged=logged)

    rr.main()   # 不得拋 SystemExit

    assert "pitch_type" in calls
    assert logged["ok"] is True


def test_fast_mode_skips_pitch_type(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    logged: dict = {}
    _stub_chain(monkeypatch, fast=True, pitch_type_result={"errors": [{"kind": "A", "stage": "v1", "error": "x"}]},
                calls=calls, logged=logged)

    rr.main()   # 沒跑推算，就不會因它亮 69

    assert "pitch_type" not in calls
    assert logged["ok"] is True
    assert logged["detail"]["pitch_type"] == {"skipped": True, "errors": []}
