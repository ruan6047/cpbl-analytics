"""#383 段 1 WP1-a／d：選場第四條（manifest 比對）、daily_gate 衍生訊號、PA 對帳 69 訊號。

全部無 DB（替身 conn／替身步驟）。第四條＝現行 livelog 以 builder 同一函式重算 manifest ≠ published。
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date

import pytest

from cpbl.ingest import cpbl_gamelog
from cpbl.ingest import daily_gate as dg
from cpbl.ingest import pa_build as pb
from cpbl.ingest import run_refresh_recent as rr


# ============================================================ 選場第四條（每日鏈）
class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class _StreamCursor:
    """伺服器端具名 cursor 的替身：execute 後可逐列迭代。"""

    def __init__(self, conn):
        self.conn, self.itersize = conn, None

    def execute(self, sql, params=None):
        self.conn.calls.append((sql, params))

    def __iter__(self):
        return iter(self.conn.events)


class DriftConn:
    """`_pa_manifest_drift_targets` 的替身連線：第一支查 published sha，第二支串流 livelog。"""

    def __init__(self, published_rows, events):
        self.published_rows, self.events, self.calls = published_rows, events, []
        self.cursor_kwargs = None

    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        return _Rows(self.published_rows)

    def cursor(self, **kwargs):
        self.cursor_kwargs = kwargs
        return _StreamCursor(self)


def install_drift_conn(monkeypatch, published_rows, events) -> DriftConn:
    holder = DriftConn(published_rows, events)

    @contextmanager
    def fake_conn():
        yield holder

    monkeypatch.setattr(rr, "conn", fake_conn)
    return holder


def game_events(kind: str, sno: int, n: int = 3, *, content: str = "x") -> list[dict]:
    base = {"year": 2026, "kind_code": kind, "game_sno": sno, "inning_seq": 1,
            "visiting_home_type": "1", "pitcher_acnt": "P1", "is_strike": True}
    return [{**base, "main_event_no": f"{i:010d}", "hitter_acnt": f"H{i}", "pitch_cnt": i,
             "content": content} for i in range(1, n + 1)]


def test_fourth_branch_selects_zero_of_4500_published_games_matching_current_livelog(monkeypatch) -> None:
    """共同主 PM 必驗：約 4,500 場已 published、現行 manifest＝published sha → 第四條入選數＝0。"""
    games = [("A" if i % 2 else "D", i) for i in range(1, 4501)]
    events, published = [], []
    for kind, sno in games:
        ev = game_events(kind, sno)
        events.extend(ev)
        published.append((2026, kind, sno, pb._livelog_manifest(ev)[0]))
    events.sort(key=lambda e: (e["kind_code"], e["game_sno"]))
    install_drift_conn(monkeypatch, published, events)
    selected = rr._pa_manifest_drift_targets(2026, ["A", "D"])
    assert len(selected) == 0


def test_fourth_branch_selects_games_whose_current_livelog_differs(monkeypatch) -> None:
    same, changed, unpublished = game_events("A", 1), game_events("A", 2), game_events("A", 3)
    published = [(2026, "A", 1, pb._livelog_manifest(same)[0]),
                 (2026, "A", 2, pb._livelog_manifest(changed)[0])]
    changed_now = [*changed[:1], {**changed[1], "content": "非官方 writer 改的"}, *changed[2:]]
    install_drift_conn(monkeypatch, published, [*same, *changed_now, *unpublished])
    assert rr._pa_manifest_drift_targets(2026, ["A"]) == [(2026, "A", 2)]


def test_fourth_branch_sql_uses_builder_columns_published_sha_and_streams(monkeypatch) -> None:
    holder = install_drift_conn(monkeypatch, [(2026, "A", 1, "x")], [])
    rr._pa_manifest_drift_targets(2026, ["A", "D"])
    pub_sql = " ".join(holder.calls[0][0].split())
    assert "pb.state = 'published'" in pub_sql and "sr.source_sha256" in pub_sql
    assert rr.daily_chain_completed_games_sql("g") in pub_sql
    assert f"g.game_date IS DISTINCT FROM {rr.TAIPEI_TODAY_SQL}" in pub_sql
    assert "livelog_manifest_sha256" not in pub_sql            # ⛔ 不讀寫入端 detail
    ll_sql = " ".join(holder.calls[1][0].split())
    assert f"SELECT {pb._EVENT_COLS} FROM cpbl.game_livelog" in ll_sql   # 口徑＝builder
    assert "game_livelog_extra" not in ll_sql
    assert holder.cursor_kwargs.get("name")                    # 伺服器端串流，不整季載入


def test_fourth_branch_short_circuits_without_published(monkeypatch) -> None:
    holder = install_drift_conn(monkeypatch, [], game_events("A", 1))
    assert rr._pa_manifest_drift_targets(2026, ["A"]) == []
    assert len(holder.calls) == 1
    assert rr._pa_manifest_drift_targets(2026, []) == []


def test_build_pa_daily_unions_fourth_branch(monkeypatch) -> None:
    monkeypatch.setattr(rr, "_active_kinds", lambda *_a, **_k: ["A"])
    monkeypatch.setattr(rr, "_pa_build_targets", lambda *_a, **_k: [(2026, "A", 5)])
    monkeypatch.setattr(rr, "_pa_manifest_drift_targets", lambda *_a, **_k: [(2026, "A", 2), (2026, "A", 5)])
    monkeypatch.setattr(rr, "_pa_build_coverage", lambda *_a, **_k: {})
    calls = []
    monkeypatch.setattr(rr, "build_scope", lambda *a, **k: calls.append(k) or {
        "games": 2, "actions": {}, "build_states": {}, "errors": []})
    rr._build_pa_daily(2026, [], include_farm=False)
    assert calls == [{"only_games": [(2026, "A", 2), (2026, "A", 5)]}]


def test_drift_count_is_the_same_function(monkeypatch) -> None:
    seen = []
    monkeypatch.setattr(rr, "_pa_manifest_drift_targets",
                        lambda year, kinds: seen.append((year, kinds)) or [(2026, "A", 1)] * 3)
    assert rr._pa_manifest_drift_count(2026) == 3
    assert seen == [(2026, ["A", "C", "E", "D"])]


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
    monkeypatch.setattr(rr, "_pa_manifest_drift_targets", lambda *_a, **_k: [])
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
