"""#365 晚間鏈常設化：賽別參數、「一晚」界線、動作條件（S1／S2；驗收 a、b、c）。

時刻與場次取 2026 真實日期（本機 ``cpbl.games``／``game_schedule_status_revisions`` 唯讀抽出，見
``tests/fixtures/evening_schedule_2026_real.json`` 的 ``_provenance``）。⛔ 不連網、不碰 DB：
DB 與 stats 的入口一律換成「一被呼叫就 raise」的樁。
"""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from cpbl.ingest import postseason_evening as pe

TPE = ZoneInfo("Asia/Taipei")


def tpe(y, m, d, hh, mm) -> datetime:
    return datetime(y, m, d, hh, mm, tzinfo=TPE)


# =========================================================== S1：晚間賽別（P-EVENING-KINDS）

def test_evening_kinds_default_is_a_e_c_and_d_is_refused():
    assert pe.parse_evening_kinds(None) == ("A", "E", "C")
    assert pe.parse_evening_kinds("") == ("A", "E", "C")
    assert pe.parse_evening_kinds("C,A") == ("A", "C"), "依 A、E、C 排序"
    for bad in ("A,D", "D", "A,A", "a", "A,E,C,F", "A,"):
        with pytest.raises(ValueError):
            pe.parse_evening_kinds(bad)


def test_cli_refuses_d_with_exit_64_before_touching_anything(monkeypatch, tmp_path):
    monkeypatch.setenv("POSTSEASON_EVENING_KINDS", "A,E,C,D")
    monkeypatch.setenv("POSTSEASON_STATE", str(tmp_path / "state.json"))
    assert pe.main(["plan"]) == 64
    assert not (tmp_path / "state.json").exists()


def test_local_sql_takes_kinds_as_a_parameter_not_a_literal(monkeypatch):
    """五段本機 SQL 改成 ``kind_code = ANY(%s)``；設定的賽別以參數送出（AGENTS.md：不拼字串）。"""
    seen: list[tuple[str, object]] = []

    class Cur:
        def fetchall(self):
            return []

    class Conn:
        def execute(self, sql, params=None):
            seen.append((sql, params))
            return Cur()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    import cpbl.db

    monkeypatch.setattr(cpbl.db, "conn", lambda: Conn())
    monkeypatch.setenv("POSTSEASON_EVENING_KINDS", "A,C")
    pe.load_local_games(2026, tpe(2026, 9, 27, 21, 0))
    pe.local_first_seen(2026)
    pe.local_signature(2026)
    pe.local_www_starts(2026)
    assert len(seen) == 5
    for sql, params in seen:
        # 只看外層賽別篩選（最後一個 FROM cpbl.… 之後）；完賽判準 helper 內部自帶的季後範圍不在本卡範圍。
        outer = sql[sql.rindex("FROM cpbl."):]
        assert "IN ('E', 'C')" not in outer and "kind_code = ANY(" in outer, outer
        flat = list(params.values()) if isinstance(params, dict) else list(params or ())
        assert ["A", "C"] in flat, (sql, params)


# =========================================================== S1：一晚界線（P-NIGHT-WINDOW）

@pytest.mark.parametrize(("at", "night"), [
    (tpe(2026, 10, 21, 18, 35), date(2026, 10, 21)),   # C4 開賽
    (tpe(2026, 10, 22, 0, 30), date(2026, 10, 21)),    # 跨過 24:00 仍屬 10-21 的夜
    (tpe(2026, 10, 22, 9, 44), date(2026, 10, 21)),
    (tpe(2026, 10, 22, 9, 45), None),                  # DAILY_GUARD 起點：不屬任何一晚
    (tpe(2026, 10, 22, 11, 59), None),
    (tpe(2026, 10, 22, 12, 0), date(2026, 10, 22)),    # BLOCK_RELEASE_AT：新的一晚
])
def test_night_of_boundaries(at, night):
    assert pe.night_of(at) == night
