"""#383 段 1 WP1-a／d：選場第四條（manifest 比對）、daily_gate 衍生訊號、PA 對帳 69 訊號。

全部無 DB（替身 conn／替身步驟）。第四條的判準在純函式 `manifest_drift_selected`；SQL 只預篩。
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date

import pytest

from cpbl.ingest import cpbl_gamelog
from cpbl.ingest import daily_gate as dg
from cpbl.ingest import run_refresh_recent as rr


# ============================================================ 選場第四條（每日鏈）
class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class _TargetsConn:
    def __init__(self, rows):
        self.rows, self.calls = rows, []

    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        return _Rows(self.rows if len(self.calls) == 1 else [])


def _targets_with(monkeypatch, rows):
    holder = _TargetsConn(rows)

    @contextmanager
    def fake_conn():
        yield holder

    monkeypatch.setattr(rr, "conn", fake_conn)
    return rr._pa_build_targets(2026, ["A", "D"], [date(2026, 10, 27), date(2026, 10, 28)]), holder


def test_fourth_branch_selects_zero_of_4500_published_games_without_manifest(monkeypatch) -> None:
    """PM 指定大量形狀：4,500 場已 published、最新 revision 沒有 manifest → 第四條入選數＝0。"""
    rows = [(2026, "A" if i % 2 else "D", i, False, False, f"pub{i:04d}", None) for i in range(4500)]
    selected, holder = _targets_with(monkeypatch, rows)
    assert len(selected) == 0
    assert len(holder.calls) == 1


def test_fourth_branch_selects_recorded_mismatch_only(monkeypatch) -> None:
    rows = [
        (2026, "A", 1, False, False, "pubA", "newA"),   # 有 manifest 且不符 → 入選
        (2026, "A", 2, False, False, "same", "same"),   # 有 manifest 且相符 → 不入選
        (2026, "A", 3, False, False, "pubC", None),     # 沒有 manifest → 不入選
        (2026, "A", 4, False, False, None, "newD"),     # 沒有 published → 不由第四條入選
        (2026, "A", 5, False, True, "pubE", None),      # 前三條命中 → 照舊入選
    ]
    selected, _ = _targets_with(monkeypatch, rows)
    assert selected == [(2026, "A", 1), (2026, "A", 5)]


def test_fourth_branch_sql_reads_recorded_manifest_from_latest_available_revision(monkeypatch) -> None:
    _sel, holder = _targets_with(monkeypatch, [])
    sql = " ".join(holder.calls[0][0].split())
    assert "detail ->> 'livelog_manifest_sha256'" in sql
    assert "gs.source = 'livelog' AND gs.outcome = 'available'" in sql
    assert "ORDER BY gs.last_seen_at DESC, gs.id DESC LIMIT 1" in sql
    assert "t.published_sha IS NOT NULL AND t.recorded_manifest IS NOT NULL" in sql
    assert holder.calls[0][1] == (2026, ["A", "D"], [date(2026, 10, 27), date(2026, 10, 28)])


@pytest.mark.parametrize("rec,pub,want", [
    (None, None, False), (None, "a", False), ("a", None, False), ("a", "a", False), ("a", "b", True)])
def test_manifest_drift_predicate(rec, pub, want) -> None:
    assert rr.manifest_drift_selected(rec, pub) is want


# ============================================================ daily_gate 衍生訊號
def test_drift_signal_shapes() -> None:
    assert dg.pa_manifest_drift_signal(lambda: 0).fired is False
    assert dg.pa_manifest_drift_signal(lambda: 3).fired is True

    def boom():
        raise RuntimeError("db down")

    sig = dg.pa_manifest_drift_signal(boom)
    assert sig.key == "pa_manifest_drift" and sig.fired is None


def test_drift_signal_alone_runs_full_derived_set() -> None:
    signals = [dg.DerivedSignal("j4_box", False), dg.pa_manifest_drift_signal(lambda: 1)]
    steps, _ = dg.derived_decision(signals, {"pa_build", "splits"})
    assert steps == {"pa_build", "splits"}


# ============================================================ 69 訊號
def test_alert_note_lists_game_conditions_and_days() -> None:
    note = rr._pa_alert_note([{"game": "2026/A/276", "days": 3, "failed": ["4_box", "5_score"]},
                              {"game": "2026/D/117", "days": 0, "failed": []}])
    assert note == "PA 對帳待收尾：2026/A/276(4_box,5_score;3天)；2026/D/117(未評估;0天)"


def test_step_attaches_count_alert_when_only_coverage_counts(monkeypatch) -> None:
    monkeypatch.setattr(rr, "_build_pa_daily", lambda *_a, **_k: {
        "games": 0, "actions": {}, "build_states": {}, "errors": [],
        "coverage": {"A": {"completed": 9, "published": 9, "gap": 0,
                           "reconciliation_outstanding": 2, "oldest_days": 5}}})
    out = rr._pa_build_step(2026, [date(2026, 10, 28)], include_farm=True)
    assert out["reconciliation_alerts"] == [{"game": "2026/A（2 場）", "days": 5, "failed": []}]


def test_build_pa_daily_queries_alerts_only_when_outstanding(monkeypatch) -> None:
    monkeypatch.setattr(rr, "_active_kinds", lambda *_a, **_k: ["A"])
    monkeypatch.setattr(rr, "_pa_build_targets", lambda *_a, **_k: [])
    calls = []
    monkeypatch.setattr(rr, "_pa_reconciliation_alerts",
                        lambda y, k: calls.append((y, k)) or [{"game": "2026/A/1", "days": 1,
                                                               "failed": ["4_box"]}])
    monkeypatch.setattr(rr, "_pa_build_coverage", lambda *_a, **_k: {
        "A": {"gap": 0, "reconciliation_outstanding": 0}})
    assert "reconciliation_alerts" not in rr._build_pa_daily(2026, [], include_farm=False)
    assert calls == []
    monkeypatch.setattr(rr, "_pa_build_coverage", lambda *_a, **_k: {
        "A": {"gap": 0, "reconciliation_outstanding": 1}})
    out = rr._build_pa_daily(2026, [], include_farm=False)
    assert out["reconciliation_alerts"][0]["failed"] == ["4_box"] and calls == [(2026, ["A"])]


def _stub_main(monkeypatch, pa_result: dict, logged: list) -> None:
    monkeypatch.setattr(rr.sys, "argv", ["cpbl-refresh-recent"])
    monkeypatch.setattr(rr, "_GAMELOG_GAPS", [])
    monkeypatch.delenv(dg.DAY_TYPE_ENV, raising=False)
    stubs = {
        "migrate": lambda: [], "scrape_games": lambda *a, **k: 0, "scrape_all": lambda *a, **k: {},
        "scrape_standings": lambda *a, **k: {}, "standings_failures": lambda: [],
        "reset_standings_failures": lambda: None, "scrape_transactions": lambda *a, **k: 0,
        "build_championships": lambda: None, "_incremental_detail": lambda *a, **k: {},
        "_missing_gamelog_snos": lambda *a, **k: [], "_livelog_check_step": lambda: {"errors": []},
        "_pa_build_step": lambda *a, **k: pa_result,
        "_pitch_type_step": lambda *a, **k: {"errors": []}, "_derived_step": lambda *a, **k: {"errors": []},
        "build_splits": lambda *a, **k: {}, "build_career": lambda *a, **k: {},
        "_sync_player_names": lambda: 0, "_recent_counts": lambda *a, **k: [],
        "_log_refresh": lambda *a, **k: logged.append((a, k)),
    }
    for name, value in stubs.items():
        monkeypatch.setattr(rr, name, value)


def test_main_exits_69_with_note_when_pa_alerts(monkeypatch) -> None:
    logged: list = []
    _stub_main(monkeypatch, {"errors": [], "reconciliation_alerts": [
        {"game": "2026/A/276", "days": 2, "failed": ["4_box"]}]}, logged)
    with pytest.raises(SystemExit) as exc:
        rr.main()
    assert exc.value.code == cpbl_gamelog.EXIT_INCOMPLETE_SCRAPE == 69
    (_args, kw), = logged
    assert kw["ok"] is False and "PA 對帳待收尾：2026/A/276(4_box;2天)" in kw["note"]


def test_main_stays_ok_without_pa_alerts(monkeypatch) -> None:
    logged: list = []
    _stub_main(monkeypatch, {"errors": []}, logged)
    rr.main()
    (_args, kw), = logged
    assert kw["ok"] is True
