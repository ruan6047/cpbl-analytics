"""#357 WP2-c：livelog 兩支機械檢查（正控／負控）＋每日鏈告警接線。

DB 段用隔離庫的哨兵場次（year=1900），DB 不可達時 skip；每日鏈接線段不碰 DB。
正控＝修正前形狀（最後一列是結束標記、附加表空）必須報出；負控＝修正後形狀必須通過。
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import pytest

from cpbl.ingest import livelog_checks
from cpbl.ingest import run_refresh_recent as rr
from cpbl.ingest.cpbl_gamelog import (
    _LL_COLS,
    _LL_EXTRA_COLS,
    LIVELOG_WRITTEN,
    _livelog_extra_rows,
    _livelog_rows,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "livelog_357_www"
YEAR = 1900
GAMES = {(YEAR, "A", 1): "2026-C-4.json.gz", (YEAR, "D", 2): "2026-D-118.json.gz"}


def _raw(name: str) -> list[dict]:
    return json.loads(json.loads(gzip.decompress((FIXTURES / name).read_bytes()))["LiveLogJson"])


def _event_rows(name: str) -> int:
    return sum(1 for r in _raw(name) if r.get("MainEventNo"))


def _seed(c, key, name: str, *, fixed: bool) -> None:
    """fixed=False：修正前（舊寫入端後到者勝：最後一列＝標記、無附加列）。"""
    raw = _raw(name)
    main = [(*key, *r[3:]) for r in _livelog_rows(2026, "C", 4, raw)]
    if not fixed:
        last_no = max(r[3] for r in main)
        marker = next(r for r in raw if r["MainEventNo"] == last_no and "比賽結束" in r["Content"])
        i_c = _LL_COLS.split(",").index("content")
        main = [(*r[:i_c], marker["Content"], *r[i_c + 1:]) if r[3] == last_no else r for r in main]
    c.cursor().executemany(
        f"INSERT INTO cpbl.game_livelog ({_LL_COLS}) VALUES ({','.join(['%s'] * 31)})", main)
    if fixed:
        extra = [(*key, *r[3:]) for r in _livelog_extra_rows(2026, "C", 4, raw)]
        c.cursor().executemany(
            f"INSERT INTO cpbl.game_livelog_extra ({_LL_EXTRA_COLS}) VALUES ({','.join(['%s'] * 33)})",
            extra)


def _wipe(c) -> None:
    for t in ("game_livelog", "game_livelog_extra"):
        c.execute(f"DELETE FROM cpbl.{t} WHERE year=%s", (YEAR,))


@pytest.fixture
def db():
    from cpbl.db import conn

    try:
        with conn() as c:
            _wipe(c)
            c.execute("SELECT 1 FROM cpbl.game_livelog_extra LIMIT 0")
    except Exception as exc:  # noqa: BLE001 — 無 DB／無 079 的環境
        pytest.skip(f"DB 不可用：{type(exc).__name__}")
    yield conn
    with conn() as c:
        _wipe(c)


def _run(**kw):
    return livelog_checks.run_checks(year=YEAR, **kw)


def test_positive_control_pre_fix_shape_is_reported(db):
    with db() as c:
        for key, name in GAMES.items():
            _seed(c, key, name, fixed=False)
    expected = {k: _event_rows(n) for k, n in GAMES.items()}
    res = _run(expected=expected)
    assert res["last_event"]["games"] == 2 and res["last_event"]["violations"] == 2
    assert res["last_event"]["by_scope"] == {"1900/A": {"games": 1, "violations": 1},
                                             "1900/D": {"games": 1, "violations": 1}}
    assert res["conservation"]["violations"] == 2  # 主表少一列（標記被吃掉）、附加表空
    assert not res["ok"]


def test_negative_control_fixed_shape_passes(db):
    with db() as c:
        for key, name in GAMES.items():
            _seed(c, key, name, fixed=True)
    res = _run(expected={k: _event_rows(n) for k, n in GAMES.items()})
    assert res["last_event"]["violations"] == 0 and res["conservation"]["violations"] == 0
    assert res["conservation"]["unverifiable"] == 0 and res["ok"]


def test_unverifiable_is_not_a_pass_when_required(db):
    with db() as c:
        _seed(c, (YEAR, "A", 1), GAMES[(YEAR, "A", 1)], fixed=True)
    assert _run()["conservation"]["unverifiable"] == 1
    assert _run()["ok"]  # 預設只列出
    assert not _run(require_verifiable=True)["ok"]


def test_orphan_extra_row_is_a_violation(db):
    with db() as c:
        _seed(c, (YEAR, "A", 1), GAMES[(YEAR, "A", 1)], fixed=True)
        c.execute("UPDATE cpbl.game_livelog_extra SET main_event_no='9999999999' WHERE year=%s", (YEAR,))
    res = _run(expected={(YEAR, "A", 1): _event_rows(GAMES[(YEAR, "A", 1)])})
    assert [v["reason"] for v in res["conservation"]["violation_games"]] == ["orphan_extra_rows"]


def test_games_scope_reports_missing_game(db):
    with db() as c:
        _seed(c, (YEAR, "A", 1), GAMES[(YEAR, "A", 1)], fixed=True)
    res = livelog_checks.run_checks(games={(YEAR, "A", 1), (YEAR, "A", 9)},
                                    expected={(YEAR, "A", 1): _event_rows(GAMES[(YEAR, "A", 1)]),
                                              (YEAR, "A", 9): 10})
    assert res["last_event"]["games"] == 1
    assert res["conservation"]["violation_games"] == [
        {"game": "1900-A-9", "reason": "game_missing_from_livelog"}]


def test_cli_exit_code_follows_result(db, capsys):
    with db() as c:
        _seed(c, (YEAR, "A", 1), GAMES[(YEAR, "A", 1)], fixed=False)
    with pytest.raises(SystemExit) as e:
        livelog_checks.main(["--year", str(YEAR)])
    assert e.value.code == 1
    assert '"violations": 1' in capsys.readouterr().out


# ── 每日鏈接線（不碰 DB）──────────────────────────────────────────────────────────
def test_daily_step_is_noop_without_written_games(monkeypatch):
    monkeypatch.setattr(livelog_checks, "run_checks", lambda **_k: pytest.fail("不該查 DB"))
    LIVELOG_WRITTEN.clear()
    assert rr._livelog_check_step() == {"games": 0, "errors": []}


def test_daily_step_checks_only_written_games_and_reports_errors(monkeypatch):
    seen = {}

    def fake(**kw):
        seen.update(kw)
        return {"last_event": {"games": 1, "violations": 1,
                               "violation_games": [{"game": "2026-A-1", "main_event_no": "9", "content": "比賽結束"}]},
                "conservation": {"games": 1, "violations": 0, "unverifiable": 0, "violation_games": []},
                "ok": False}

    monkeypatch.setattr(livelog_checks, "run_checks", fake)
    LIVELOG_WRITTEN.clear()
    LIVELOG_WRITTEN[(2026, "A", 1)] = 300
    try:
        out = rr._livelog_check_step()
    finally:
        LIVELOG_WRITTEN.clear()
    assert seen == {"games": {(2026, "A", 1)}, "expected": {(2026, "A", 1): 300}}
    assert out["errors"] == [{"check": "last_event", "game": "2026-A-1", "reason": "end_marker_is_last_event"}]


def test_daily_step_failure_is_fail_closed(monkeypatch):
    def boom(**_k):
        raise RuntimeError("db down")

    monkeypatch.setattr(livelog_checks, "run_checks", boom)
    LIVELOG_WRITTEN.clear()
    LIVELOG_WRITTEN[(2026, "A", 1)] = 300
    try:
        out = rr._livelog_check_step()
    finally:
        LIVELOG_WRITTEN.clear()
    assert out["errors"] == [{"game": "setup", "reason": "db down"}]


def test_main_turns_livelog_errors_into_69(monkeypatch):
    """main() 結清：livelog 檢查有 errors → refresh_log ok=false、note 帶場次、退出碼 69。"""
    logged = {}
    _stub_main(monkeypatch, logged,
               livelog={"games": 1, "errors": [{"check": "last_event", "game": "2026-A-1",
                                                "reason": "end_marker_is_last_event"}]})
    with pytest.raises(SystemExit) as e:
        rr.main()
    assert e.value.code == rr.EXIT_INCOMPLETE_SCRAPE
    assert logged["ok"] is False and "livelog 檢查未過：2026-A-1(end_marker_is_last_event)" in logged["note"]
    assert logged["detail"]["livelog_check"]["games"] == 1


def test_main_clean_livelog_check_exits_zero(monkeypatch):
    logged = {}
    _stub_main(monkeypatch, logged, livelog={"games": 3, "errors": []})
    rr.main()
    assert logged["ok"] is True


def _stub_main(monkeypatch, logged, *, livelog):
    from datetime import date

    class _Today(date):
        @classmethod
        def today(cls):
            return date(2026, 10, 1)

    monkeypatch.setattr(rr, "date", _Today)
    monkeypatch.setattr(rr, "_GAMELOG_GAPS", [])
    monkeypatch.setattr(rr.sys, "argv", ["cpbl-refresh-recent", "fast"])
    monkeypatch.setenv("DAILY_DAY_TYPE", "full")
    stubs = {
        "migrate": lambda: None,
        "scrape_games": lambda *a, **k: {},
        "_postseason_games_step": lambda *a, **k: {"games": {}, "errors": []},
        "scrape_all": lambda *a, **k: {},
        "scrape_standings": lambda *a, **k: {},
        "standings_failures": lambda: [],
        "scrape_transactions": lambda *a, **k: 0,
        "build_championships": lambda: None,
        "_missing_gamelog_snos": lambda *a, **k: [],
        "_pa_build_step": lambda *a, **k: {"games": 0, "actions": {}, "build_states": {}, "errors": []},
        "build_splits": lambda *a, **k: {},
        "build_career": lambda *a, **k: {},
        "_sync_player_names": lambda: 0,
        "_recent_counts": lambda *a, **k: [],
        "_livelog_check_step": lambda: livelog,
        "_log_refresh": lambda scope, frm, to, total, done, detail, *, ok, note: logged.update(
            detail=detail, ok=ok, note=note),
    }
    for name, value in stubs.items():
        monkeypatch.setattr(rr, name, value)
