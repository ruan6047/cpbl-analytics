"""INGEST-PA-DAILY1：canonical PA build 接進每日 refresh 鏈的離線單元測試（無 DB 依賴）。

覆蓋：增量 sno 選集（當日窗∪全域缺口聯集、farm 納入/排除、kind 動態判定）、
build_scope 的 only_games=[] 陷阱（falsy 空清單會退化成全範圍查詢，見 pa_build._list_games）
的防呆、以及 fail-closed 失敗隔離（_pa_build_step 不外拋例外）。

CI 無真實 Postgres（見 .github/workflows/ci.yml），故一律 monkeypatch `conn`／
被呼叫函式，不打真實 DB（比照 tests/test_game_source_revisions.py 的既有作法）。
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date

import pytest

from cpbl.ingest import run_refresh_recent as rr


class _FakeCursor:
    def __init__(self, rows: list[tuple]) -> None:
        self._rows = rows
        self.sql: str | None = None
        self.params: tuple | None = None

    def execute(self, sql: str, params: tuple | None = None) -> _FakeCursor:
        self.sql = sql
        self.params = params
        return self

    def fetchall(self) -> list[tuple]:
        return self._rows


class _FakeConnection:
    def __init__(self, rows: list[tuple]) -> None:
        self.cursor = _FakeCursor(rows)

    def execute(self, sql: str, params: tuple | None = None) -> _FakeCursor:
        return self.cursor.execute(sql, params)


def _fake_conn_factory(rows: list[tuple]):
    holder = _FakeConnection(rows)

    @contextmanager
    def fake_conn():
        yield holder

    return fake_conn, holder


# ---------------------------------------------------------------------------
# SQL-issuing 輔助函式：空清單短路（不打 DB）＋ 使用 canonical 完成場判定
# ---------------------------------------------------------------------------
def test_active_kinds_short_circuits_on_empty_candidates_without_touching_db(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _boom():
        raise AssertionError("conn() 不應在候選 kinds 為空時被呼叫")

    monkeypatch.setattr(rr, "conn", _boom)

    assert rr._active_kinds(2026, ()) == []


def test_pa_build_targets_short_circuits_on_empty_kinds_without_touching_db(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _boom():
        raise AssertionError("conn() 不應在 kinds 為空時被呼叫")

    monkeypatch.setattr(rr, "conn", _boom)

    assert rr._pa_build_targets(2026, [], [date(2026, 8, 4), date(2026, 8, 5)]) == []


def test_pa_build_coverage_short_circuits_on_empty_kinds_without_touching_db(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _boom():
        raise AssertionError("conn() 不應在 kinds 為空時被呼叫")

    monkeypatch.setattr(rr, "conn", _boom)

    assert rr._pa_build_coverage(2026, []) == {}


def test_active_kinds_uses_canonical_completed_predicate_not_hand_rolled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GLOSSARY「完成場判定」SSoT：一律引用 completion 的每日鏈判準，不得手寫條件（#213）。"""
    fake_conn, holder = _fake_conn_factory([("A",), ("C",)])
    monkeypatch.setattr(rr, "conn", fake_conn)

    result = rr._active_kinds(2026, ("A", "C", "E"))

    assert result == ["A", "C"]
    assert rr.daily_chain_completed_games_sql() in holder.cursor.sql


def test_pa_build_targets_query_unions_day_window_and_global_gap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """驗證組出的 SQL 同時帶「當日窗」與「無 published build」兩個條件（OR 聯集）。"""
    fake_conn, holder = _fake_conn_factory([(2026, "A", 228, False)])
    monkeypatch.setattr(rr, "conn", fake_conn)
    days = [date(2026, 8, 4), date(2026, 8, 5)]

    result = rr._pa_build_targets(2026, ["A"], days)

    assert result == [(2026, "A", 228)]
    sql = holder.cursor.sql
    assert "game_date = ANY(%s)" in sql
    assert "game_recap_builds" in sql and "state = 'published'" in sql
    assert holder.cursor.params == (2026, ["A"], days)


# ---------------------------------------------------------------------------
# 當日場只收官方 final（2026-09-23；實例：09-07 20:10 賽中 refresh 發布 A/304、A/306 半場 build）
# ---------------------------------------------------------------------------
class _ScriptedConnection:
    """第一次 execute 回 targets，之後每次回 schedule 列（逐場查官方狀態）。記下每次的 SQL。"""

    def __init__(self, targets: list[tuple], schedule: dict[int, list[tuple]]) -> None:
        self._targets = targets
        self._schedule = schedule
        self.calls: list[tuple[str, tuple | None]] = []

    def execute(self, sql: str, params: tuple | None = None) -> _FakeCursor:
        self.calls.append((sql, params))
        if len(self.calls) == 1:
            return _FakeCursor(self._targets)
        assert params is not None
        return _FakeCursor(self._schedule.get(params[2], []))


def _scripted(monkeypatch: pytest.MonkeyPatch, targets: list[tuple],
              schedule: dict[int, list[tuple]]) -> _ScriptedConnection:
    holder = _ScriptedConnection(targets, schedule)

    @contextmanager
    def fake_conn():
        yield holder

    monkeypatch.setattr(rr, "conn", fake_conn)
    return holder


# 取自 `_OFFICIAL_STATUS_BY_RAW`：(PresentStatus, GameResult)。欄位順序＝`rr._SCHEDULE_COLS`。
def _sched(present: int, result: str) -> tuple:
    return (present, result, date(2026, 9, 7), None, f"h{present}{result}",
            "2026-09-07T20:00:00+08:00", "2026-09-07T20:05:00+08:00")


def test_drop_unfinished_same_day_keeps_only_official_final() -> None:
    rows = [(2026, "A", 1, True), (2026, "A", 2, True), (2026, "A", 3, True),
            (2026, "A", 4, False)]
    phases = {(2026, "A", 1): "final", (2026, "A", 2): "scheduled"}  # 3 查無 → 視同非 final

    kept, dropped = rr._drop_unfinished_same_day(rows, phases)

    assert kept == [(2026, "A", 1), (2026, "A", 4)]      # 非當日場不看狀態
    assert dropped == [(2026, "A", 2), (2026, "A", 3)]


@pytest.mark.parametrize("schedule,expected", [
    ([_sched(1, "0")], [(2026, "A", 304)]),   # final → 建
    ([_sched(1, "")], []),                    # scheduled（賽中還沒寫結果）→ 不建
    ([_sched(1, "2")], []),                   # reserved（保留賽當日）→ 不建
    ([], []),                                 # 查無排程列 → unknown → 不建（fail closed）
])
def test_same_day_game_is_built_only_when_officially_final(
    monkeypatch: pytest.MonkeyPatch, schedule: list[tuple], expected: list[tuple],
) -> None:
    holder = _scripted(monkeypatch, [(2026, "A", 304, True)], {304: schedule})

    assert rr._pa_build_targets(2026, ["A"], [date(2026, 9, 6), date(2026, 9, 7)]) == expected
    target_sql, _ = holder.calls[0]
    assert f"(g.game_date = {rr.TAIPEI_TODAY_SQL}) AS same_day" in target_sql
    status_sql, params = holder.calls[1]
    assert "game_schedule_status_revisions" in status_sql
    assert rr.OFFICIAL_SCHEDULE_ORDER_BY in status_sql      # 選列規則只有一份，不得另寫
    assert params == (2026, "A", 304)


def test_past_games_do_not_query_official_status(monkeypatch: pytest.MonkeyPatch) -> None:
    """非當日場行為不變：不查排程列（歷史場多半沒有狀態修訂，查了會全變 unknown）。"""
    holder = _scripted(monkeypatch, [(2026, "A", 300, False), (2026, "D", 90, False)], {})

    assert rr._pa_build_targets(2026, ["A", "D"], [date(2026, 9, 6), date(2026, 9, 7)]) == [
        (2026, "A", 300), (2026, "D", 90)]
    assert len(holder.calls) == 1


def test_pa_build_coverage_computes_gap_per_kind(monkeypatch: pytest.MonkeyPatch) -> None:
    # DATA-PA-REBUILD-GAP1 Q3：查詢多回 reconciliation_outstanding／oldest_days 兩欄，
    # 兩者的行為守衛在 tests/test_pa_accept_reconciliation.py，此處只釘 gap 的算法不變。
    fake_conn, _ = _fake_conn_factory([("A", 234, 229, 0, 0), ("D", 164, 155, 0, 0)])
    monkeypatch.setattr(rr, "conn", fake_conn)

    coverage = rr._pa_build_coverage(2026, ["A", "D"])

    assert coverage == {
        "A": {"completed": 234, "published": 229, "gap": 5,
              "reconciliation_outstanding": 0, "oldest_days": 0},
        "D": {"completed": 164, "published": 155, "gap": 9,
              "reconciliation_outstanding": 0, "oldest_days": 0},
    }


# ---------------------------------------------------------------------------
# _build_pa_daily：candidate kind 組成（一軍恆試／二軍依 include_farm）＋ 空清單防呆
# ---------------------------------------------------------------------------
def test_build_pa_daily_always_tries_major_kinds_and_gates_farm_by_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen_candidates: list[tuple[str, ...]] = []

    def fake_active_kinds(_year, candidate_kinds):
        seen_candidates.append(candidate_kinds)
        return []

    monkeypatch.setattr(rr, "_active_kinds", fake_active_kinds)
    monkeypatch.setattr(rr, "_pa_build_targets", lambda *_a, **_k: [])
    monkeypatch.setattr(rr, "_pa_build_coverage", lambda *_a, **_k: {})

    def _boom_build_scope(*_a, **_k):
        raise AssertionError("build_scope 不應在無目標場次時被呼叫")

    monkeypatch.setattr(rr, "build_scope", _boom_build_scope)

    rr._build_pa_daily(2026, [date(2026, 8, 4), date(2026, 8, 5)], include_farm=False)
    rr._build_pa_daily(2026, [date(2026, 8, 4), date(2026, 8, 5)], include_farm=True)

    assert seen_candidates[0] == ("A", "C", "E")            # 二軍不納入
    assert seen_candidates[1] == ("A", "C", "E", "D")        # 二軍納入


def test_build_pa_daily_never_calls_build_scope_with_empty_only_games(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """關鍵陷阱防呆：pa_build.build_scope 的 only_games=[]（空清單非 None）
    會被其內部 `if only_games:` 判 falsy、退化成「全範圍」查詢（見 pa_build._list_games）。
    本函式必須在目標清單為空時完全不呼叫 build_scope，而非傳空清單過去。
    """
    monkeypatch.setattr(rr, "_active_kinds", lambda *_a, **_k: ["A"])
    monkeypatch.setattr(rr, "_pa_build_targets", lambda *_a, **_k: [])
    monkeypatch.setattr(rr, "_pa_build_coverage", lambda *_a, **_k: {"A": {"completed": 5, "published": 5, "gap": 0}})

    calls = []
    monkeypatch.setattr(rr, "build_scope", lambda *a, **k: calls.append((a, k)))

    result = rr._build_pa_daily(2026, [date(2026, 8, 4), date(2026, 8, 5)], include_farm=False)

    assert calls == []
    assert result["games"] == 0
    assert result["actions"] == {}
    assert result["errors"] == []
    assert result["kinds"] == ["A"]
    assert result["coverage"] == {"A": {"completed": 5, "published": 5, "gap": 0}}


def test_build_pa_daily_calls_build_scope_with_only_games_when_targets_exist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    targets = [(2026, "A", 228), (2026, "A", 233)]
    monkeypatch.setattr(rr, "_active_kinds", lambda *_a, **_k: ["A"])
    monkeypatch.setattr(rr, "_pa_build_targets", lambda *_a, **_k: targets)
    monkeypatch.setattr(rr, "_pa_build_coverage", lambda *_a, **_k: {"A": {"completed": 234, "published": 234, "gap": 0}})

    calls = []
    monkeypatch.setattr(
        rr, "build_scope",
        lambda *a, **k: calls.append((a, k)) or {"games": 2, "actions": {"publish": 2}, "build_states": {"published": 2}, "errors": []},
    )

    result = rr._build_pa_daily(2026, [date(2026, 8, 4), date(2026, 8, 5)], include_farm=False)

    assert len(calls) == 1
    args, kwargs = calls[0]
    assert args == (2026, 2026, ["A"])
    assert kwargs == {"only_games": targets}
    assert result["games"] == 2
    assert result["kinds"] == ["A"]


# ---------------------------------------------------------------------------
# _pa_build_step：fail-closed 邊界（build 失敗必須被吞、不得外拋阻斷 main() 其餘步驟）
# ---------------------------------------------------------------------------
def test_pa_build_step_is_fail_closed_when_build_pa_daily_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _explode(*_a, **_k):
        raise RuntimeError("boom: DB 斷線")

    monkeypatch.setattr(rr, "_build_pa_daily", _explode)

    # 不應拋出——這是「build 失敗不得擋主流程」的核心契約
    result = rr._pa_build_step(2026, [date(2026, 8, 4), date(2026, 8, 5)], include_farm=True)

    assert "error" in result
    assert "boom" in result["error"]


def test_pa_build_step_surfaces_reconciliation_required_without_raising(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """reconciliation_required 是正常（非例外）結果，但驗收要求「記入 detail 與 stdout log」。"""
    clean_result = {
        "games": 1, "actions": {"reconcile": 1},
        "build_states": {"reconciliation_required": 1}, "errors": [],
        "kinds": ["A"], "coverage": {"A": {"completed": 5, "published": 4, "gap": 1}},
    }
    monkeypatch.setattr(rr, "_build_pa_daily", lambda *_a, **_k: clean_result)

    result = rr._pa_build_step(2026, [date(2026, 8, 4), date(2026, 8, 5)], include_farm=True)

    assert result is clean_result  # 原樣回傳供 caller 塞進 refresh_log detail
    assert result["build_states"]["reconciliation_required"] == 1
    assert result["coverage"]["A"]["gap"] == 1


def test_pa_build_step_returns_result_unchanged_on_clean_zero_gap_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clean_result = {
        "games": 0, "actions": {}, "build_states": {}, "errors": [],
        "kinds": ["A"], "coverage": {"A": {"completed": 234, "published": 234, "gap": 0}},
    }
    monkeypatch.setattr(rr, "_build_pa_daily", lambda *_a, **_k: clean_result)

    result = rr._pa_build_step(2026, [date(2026, 8, 4), date(2026, 8, 5)], include_farm=True)

    assert result is clean_result
