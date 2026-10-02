"""當季衍生重建接進每日鏈（#222）的離線單元測試（無 DB 依賴）。

DER／wSB／守備局數／捕手失分／選手特性／RE24 原本只由手動 cpbl-build-sabr 建，2026 列停在
約 07-05。這裡守住：
1. 當季入口以當年、A、同一份完賽場清單呼叫各 builder；wSB 係數 span＝2018-(year-1)；
   RE24 不傳 span（沿用生產矩陣 span）。
2. 各 builder 失敗互不連坐；fielding_innings 失敗則不寫 catcher_runs；完賽清單為空不覆寫。
3. main() 把錯誤轉成 refresh_log ok=false＋note＋69，後續步驟照跑；fast 不跑；季外 skipped。
4. 完賽清單 SQL 由 helper 產生；DER／wSB 單年只刪寫該年；RE24／traits 預設選場不變。
"""

from __future__ import annotations

from contextlib import contextmanager

import pytest

from cpbl.completion import daily_chain_completed_games_sql
from cpbl.ingest import cpbl_gamelog
from cpbl.ingest import run_refresh_recent as rr
from cpbl.models import sabr
from tests.test_refresh_pitch_type_step import _stub_chain

SNOS = [1, 2, 5]
LEGACY_SNO_SQL = ("SELECT DISTINCT game_sno FROM cpbl.game_livelog "
                  "WHERE year=%s AND kind_code=%s ORDER BY game_sno")


# ───────────────────────── 當季入口：呼叫參數與失敗隔離

def _patch_builders(monkeypatch: pytest.MonkeyPatch, calls: list, fail: set[str] | None = None,
                    snos: list[int] | None = None) -> None:
    fail = fail or set()

    def make(name: str):
        def fn(*args, **kwargs):
            calls.append((name, args, kwargs))
            if name in fail:
                raise RuntimeError(f"boom {name}")
            return {"ok": name}
        return fn

    for name in ("build_team_der", "build_wsb", "build_fielding_innings",
                 "build_catcher_runs", "build_traits", "build_re24"):
        monkeypatch.setattr(sabr, name, make(name))
    monkeypatch.setattr(sabr, "completed_livelog_snos",
                        lambda year, kind: list(SNOS if snos is None else snos))


def test_entry_calls_every_builder_for_current_year_with_completed_games(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list = []
    _patch_builders(monkeypatch, calls)

    out = sabr.build_current_season(2026)

    assert calls == [
        ("build_team_der", (2026,), {}),
        ("build_wsb", ("2018-2025", 2026), {}),
        ("build_fielding_innings", (2026, "A", SNOS), {}),
        ("build_catcher_runs", (2026, "A", SNOS), {}),
        ("build_traits", (2026, "A", SNOS), {}),
        ("build_re24", (2026, "A"), {"snos": SNOS}),   # 不傳 span
    ]
    assert out["errors"] == [] and out["completed_games"] == 3


@pytest.mark.parametrize("failing", ["build_team_der", "build_wsb", "build_traits", "build_re24"])
def test_one_builder_failure_does_not_stop_the_others(
    monkeypatch: pytest.MonkeyPatch, failing: str,
) -> None:
    calls: list = []
    _patch_builders(monkeypatch, calls, fail={failing})

    out = sabr.build_current_season(2026)      # 不得拋出

    assert len(calls) == 6, "其餘 builder 照跑"
    assert [e["builder"] for e in out["errors"]] == [
        failing.removeprefix("build_").replace("wsb", "batter_wsb")]


def test_fielding_failure_skips_catcher_runs(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list = []
    _patch_builders(monkeypatch, calls, fail={"build_fielding_innings"})

    out = sabr.build_current_season(2026)

    names = [c[0] for c in calls]
    assert "build_catcher_runs" not in names
    assert {"build_traits", "build_re24"} <= set(names)
    assert [e["builder"] for e in out["errors"]] == ["fielding_innings"]


def test_no_completed_livelog_games_does_not_overwrite(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list = []
    _patch_builders(monkeypatch, calls, snos=[])

    out = sabr.build_current_season(2026)

    assert [c[0] for c in calls] == ["build_team_der", "build_wsb"]
    assert [e["builder"] for e in out["errors"]] == ["completed_games"]


# ───────────────────────── 假連線：捕捉 SQL 與參數

class _Cur:
    def __init__(self, log: list, results: list) -> None:
        self.log, self.results, self.rowcount = log, results, 0

    def execute(self, sql, params=None):
        self.log.append((sql, params))
        return self

    def executemany(self, sql, rows):
        self.log.append((sql, list(rows)))

    def fetchall(self):
        return self.results.pop(0) if self.results else []


def _fake_conn(monkeypatch: pytest.MonkeyPatch, results: list) -> list:
    log: list = []
    cur = _Cur(log, results)

    class _Conn:
        def cursor(self):
            return cur

        def execute(self, sql, params=None):
            return cur.execute(sql, params)

    @contextmanager
    def conn():
        yield _Conn()

    monkeypatch.setattr(sabr, "conn", conn)
    return log


def test_completed_snos_sql_comes_from_daily_chain_helper(monkeypatch: pytest.MonkeyPatch) -> None:
    log = _fake_conn(monkeypatch, [[(3,), (7,)]])

    assert sabr.completed_livelog_snos(2026) == [3, 7]
    sql, params = log[0]
    assert daily_chain_completed_games_sql("g") in sql
    assert params == (2026, "A")


def test_team_der_single_year_only_deletes_and_inserts_that_year(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = [(2025, "ACN", 5000, 1100, 90, 400, 50, 900),
            (2026, "ACN", 4000, 900, 80, 300, 40, 700)]
    log = _fake_conn(monkeypatch, [rows])

    sabr.build_team_der(2026)

    deletes = [e for e in log if e[0].startswith("DELETE")]
    assert deletes == [("DELETE FROM cpbl.team_der WHERE year=%s", (2026,))]
    inserted = next(e[1] for e in log if e[0].startswith("INSERT"))
    assert [r[0] for r in inserted] == [2026]


def test_wsb_single_year_only_deletes_and_inserts_that_year(monkeypatch: pytest.MonkeyPatch) -> None:
    coeff = [("run_sb", 0.2), ("run_cs", -0.4)]
    rows = [(2025, "p1", 10, 2, 100), (2026, "p1", 5, 1, 50), (2026, "p2", 0, 0, 80)]
    log = _fake_conn(monkeypatch, [coeff, rows])

    sabr.build_wsb("2018-2025", 2026)

    deletes = [e for e in log if e[0].startswith("DELETE")]
    assert deletes == [("DELETE FROM cpbl.batter_wsb WHERE year=%s", (2026,))]
    inserted = next(e[1] for e in log if e[0].startswith("INSERT"))
    assert {r[0] for r in inserted} == {2026}
    assert abs(sum(r[5] for r in inserted)) < 0.02, "聯盟加總≈0（只用該年聯盟率）"


def test_wsb_without_year_keeps_full_rewrite(monkeypatch: pytest.MonkeyPatch) -> None:
    log = _fake_conn(monkeypatch, [[("run_sb", 0.2), ("run_cs", -0.4)], [(2025, "p1", 1, 0, 9)]])

    sabr.build_wsb("2018-2025")

    assert [e[0] for e in log if e[0].startswith("DELETE")] == ["DELETE FROM cpbl.batter_wsb"]


def test_re24_default_game_selection_is_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    re_rows = [("___", 0, 0.5)]
    log = _fake_conn(monkeypatch, [re_rows, []])

    sabr.build_re24(2026)

    assert (LEGACY_SNO_SQL, (2026, "A")) in log


def test_re24_with_snos_skips_livelog_wide_selection(monkeypatch: pytest.MonkeyPatch) -> None:
    log = _fake_conn(monkeypatch, [[("___", 0, 0.5)]])
    monkeypatch.setattr(sabr, "_load_game", lambda cur, y, k, s: [])

    out = sabr.build_re24(2026, snos=[4])

    assert all(e[0] != LEGACY_SNO_SQL for e in log)
    assert out["halves"] == 0


def test_traits_filters_games_only_when_given(monkeypatch: pytest.MonkeyPatch) -> None:
    log = _fake_conn(monkeypatch, [])
    sabr.build_traits(2026)
    assert not any("game_sno = ANY" in e[0] for e in log)

    log = _fake_conn(monkeypatch, [])
    sabr.build_traits(2026, "A", [1, 2])
    inserts = [e for e in log if e[0].startswith("INSERT")]
    assert len(inserts) == 2
    assert all("game_sno = ANY(%(snos)s)" in sql and p["snos"] == [1, 2] for sql, p in inserts)


# ───────────────────────── 每日鏈：skipped、fail-closed、69

def test_step_skips_when_no_completed_major_league_game(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rr, "_active_kinds", lambda year, kinds: [])
    monkeypatch.setattr(sabr, "build_current_season",
                        lambda year: pytest.fail("季外不得重建"))

    out = rr._derived_step(2026)

    assert out["errors"] == [] and "skipped" in out


def test_step_runs_entry_for_current_year_and_never_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rr, "_active_kinds", lambda year, kinds: ["A"])
    seen: list[int] = []
    monkeypatch.setattr(sabr, "build_current_season", lambda year: seen.append(year) or {"errors": []})
    assert rr._derived_step(2026) == {"errors": []} and seen == [2026]

    def boom(year):
        raise RuntimeError("db down")
    monkeypatch.setattr(sabr, "build_current_season", boom)
    assert rr._derived_step(2026)["errors"] == [{"builder": "setup", "error": "db down"}]


def test_derived_failure_is_visible_as_69_without_stopping_later_steps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    logged: dict = {}
    result = {"errors": [{"builder": "re24", "error": "boom"}]}
    _stub_chain(monkeypatch, fast=False, pitch_type_result={"errors": []}, calls=calls,
                logged=logged, derived_result=result)

    with pytest.raises(SystemExit) as e:
        rr.main()

    assert e.value.code == cpbl_gamelog.EXIT_INCOMPLETE_SCRAPE == 69
    assert calls == ["pa_build", "pitch_type", "derived", "splits"]
    assert logged["ok"] is False
    assert "當季衍生重建失敗：re24" in logged["note"]
    assert logged["detail"]["derived"] == result


def test_fast_mode_skips_derived(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    logged: dict = {}
    _stub_chain(monkeypatch, fast=True, pitch_type_result={"errors": []}, calls=calls,
                logged=logged, derived_result={"errors": [{"builder": "x", "error": "x"}]})

    rr.main()

    assert "derived" not in calls
    assert logged["ok"] is True
    assert logged["detail"]["derived"] == {"skipped": True, "errors": []}
