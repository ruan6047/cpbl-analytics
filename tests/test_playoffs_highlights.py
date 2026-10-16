"""#288 S07 WP-K3 逐場焦點精簡數據 adapter（``cpbl.playoffs.series_highlights``）純函式／組裝。

場次取 2026 真實 E1–E4、C1–C7（``tests/fixtures/postseason_real_years.json``）；五表列是合成值，只驗母體、
資料到齊判斷、列序原樣與查詢數。焦點規則本身在前端（``web/src/lib/game-highlights.ts`` 的黃金測試）。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from postseason_context_inputs import NOW_2026, games, inputs

from cpbl import postseason_contract as pc
from cpbl.playoffs import series_highlights as sh

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def ctx():
    return pc.compute_series_context(inputs(2026, games_override=games(2026)), now=NOW_2026)


def _rows(snos, *, drop=None):
    """每場每表一列（第二列標序）；drop=(表, sno) 拿掉某場某表。"""
    out = {name: {} for name in sh.TABLE_SQL}
    for s in snos:
        for name in sh.TABLE_SQL:
            if drop and (name, s) in drop:
                continue
            out[name][s] = [{"seq": 1, "sno": s}] if name == "game" else [{"seq": 1}, {"seq": 2}]
    return out


def test_population_is_completed_games_of_that_series_only(ctx):
    p = sh.compute_payload(ctx, "E", _rows([1, 2, 3, 4]), {1: {"P": "W"}})
    assert p["contract"] == "playoffs-highlights/v1" and p["series"] == "E" and p["status"] == "ok"
    assert [g["series_game_no"] for g in p["games"]] == [1, 2, 3, 4]
    assert all(g["game_key"]["kind_code"] == "E" for g in p["games"])
    assert p["context_version"] == ctx["context_version"]
    c = sh.compute_payload(ctx, "C", _rows([1, 2, 3, 4]), {})
    assert c["status"] == "no_completed_games" and c["games"] == []       # C 尚未開打：不列未完賽場


def test_input_passes_rows_through_in_order_with_decisions(ctx):
    p = sh.compute_payload(ctx, "E", _rows([1, 2, 3, 4]), {1: {"0000005604": "W"}})
    g1 = p["games"][0]
    assert g1["data_status"] == "ok"
    assert set(g1["input"]) == {"game", "scoreboard", "livelog", "batting", "pitching", "decisions"}
    assert [r["seq"] for r in g1["input"]["livelog"]] == [1, 2]            # 列序原樣（規則依列序判斷）
    assert g1["input"]["game"] == {"seq": 1, "sno": 1}
    assert g1["input"]["decisions"] == {"0000005604": "W"}
    assert p["games"][1]["input"]["decisions"] == {}


@pytest.mark.parametrize("table", ["game", "scoreboard", "livelog", "batting", "pitching"])
def test_any_missing_table_means_pending_without_input(ctx, table):
    p = sh.compute_payload(ctx, "E", _rows([1, 2, 3, 4], drop={(table, 3)}), {})
    g3 = next(g for g in p["games"] if g["series_game_no"] == 3)
    assert (g3["data_status"], g3["input"]) == ("pending", None)
    assert all(g["data_status"] == "ok" for g in p["games"] if g["series_game_no"] != 3)


def test_projection_columns_match_frontend_input_type():
    """後端投影欄位＝前端 HighlightInput 讀的欄位（兩邊同步；規則讀到新欄位時兩邊一起改）。"""
    ts = (ROOT / "web" / "src" / "lib" / "game-highlights.ts").read_text(encoding="utf-8")
    body = ts[ts.index("export function buildHighlights"):]
    read = set(re.findall(r"\b(?:g|r|row|cur|lastScore|fast|e|x|\(cur as StatRow\))\.(\w+)", body))
    projected = set(sh.GAME_COLS) | set(sh.SCOREBOARD_COLS) | set(sh.LIVELOG_COLS) | set(sh.BATTING_COLS) | set(
        sh.PITCHING_COLS)
    ignore = {"length", "text", "team", "push", "filter", "find", "some", "every", "map", "slice", "indexOf",
              "split", "includes", "isK", "onBase", "retired", "pitcher", "hitter", "inning", "half", "count",
              "name", "get", "set", "has", "matchAll", "match"}
    assert read - ignore <= projected, sorted(read - ignore - projected)
    # visiting_score／home_score 以 r[post] 間接讀取：必須在投影內
    assert {"visiting_score", "home_score"} <= set(sh.LIVELOG_COLS)


def test_order_by_matches_single_game_live_endpoint():
    games_py = (ROOT / "src" / "cpbl" / "api" / "routers" / "games.py").read_text(encoding="utf-8")
    for live_order, sql in [
        ("ORDER BY visiting_home_type, inning_seq", sh.SCOREBOARD_SQL),
        ("ORDER BY main_event_no", sh.LIVELOG_SQL),
        ("ORDER BY visiting_home_type, plate_appearances DESC NULLS LAST, at_bats DESC NULLS LAST", sh.BATTING_SQL),
        ("ORDER BY visiting_home_type, inning_pitched_cnt DESC NULLS LAST", sh.PITCHING_SQL),
    ]:
        assert live_order in games_py
        cols = live_order.removeprefix("ORDER BY ").split(", ")
        assert ("ORDER BY t.game_sno, " + ", ".join("t." + c for c in cols)) in sql


class _Cur:
    def __init__(self):
        self.calls = []
        self.description = [("_game_sno",), ("x",)]

    def execute(self, sql, params=None):
        self.calls.append((sql, params))

    def fetchall(self):
        return [(1, "a"), (2, "b")]


def test_read_rows_is_one_query_per_table_regardless_of_games():
    cur = _Cur()
    out = sh.read_rows(cur, 2026, "E", [1, 2, 3, 4, 5, 6, 7])
    assert len(cur.calls) == 5
    assert all(p == {"year": 2026, "kind": "E", "snos": [1, 2, 3, 4, 5, 6, 7]} for _, p in cur.calls)
    assert out["livelog"] == {1: [{"x": "a"}], 2: [{"x": "b"}]}
    assert sh.read_rows(_Cur(), 2026, "E", []) == {name: {} for name in sh.TABLE_SQL}


def test_sql_is_parameterized_and_read_only():
    for sql in sh.TABLE_SQL.values():
        assert "%(year)s" in sql and "%(kind)s" in sql and "%(snos)s" in sql
        assert not re.search(r"\b(INSERT|UPDATE|DELETE|TRUNCATE)\b", sql, re.I)
