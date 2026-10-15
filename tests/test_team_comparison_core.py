"""#287 WP1：隊伍比較純計算核心（無 DB）。

fixture `tests/fixtures/team_comparison_287.json` 是本機共享 cpbl 2025/2026 唯讀匯出到卡號隔離庫後
抽出的真實樣本（2025 C／2025 E／2026 E 全部場次與 box、2025 A ACN011–AJL011 24 場 box、
2025 A AJL011–AKP011 24 場只取 games）。⛔ 不自造樣本；變異只用於驗守衛（負控）。
"""

from __future__ import annotations

import copy
import json
import math
from datetime import date
from functools import cache
from pathlib import Path

import pytest

from cpbl.api.between_games import batting_rates
from cpbl.models import team_style as ts
from cpbl.playoffs.team_comparison import core

FIXTURE = Path(__file__).parent / "fixtures" / "team_comparison_287.json"


@cache
def _doc() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _games(year: int, kind: str, teams: set[str] | None = None, box_only: bool = True) -> list[core.GameRow]:
    out = []
    for y, k, sno, gd, home, away, hs, as_, has_box in _doc()["games"]:
        if y != year or k != kind or (box_only and not has_box):
            continue
        if teams and {home, away} != teams:
            continue
        out.append(core.GameRow((y, k, sno), date.fromisoformat(gd), home, away, hs, as_))
    return out


def _rows(table: str) -> list[dict]:
    doc = _doc()
    cols = doc["meta"]["bat_columns" if table == "batting" else "pit_columns"]
    acnt = "hitter_acnt" if table == "batting" else "pitcher_acnt"
    return [dict(zip(["year", "kind_code", "game_sno", acnt, *cols], r, strict=True)) for r in doc[table]]


def _index(games, bat=None, pit=None):
    return core.box_index(games, bat if bat is not None else _rows("batting"),
                          pit if pit is not None else _rows("pitching"))


def _manual_sum(games, team: str, table: str, col: str) -> int:
    """獨立對照：逐列加總（不經 core）。"""
    keys = {g.key: ("2" if g.home == team else "1") for g in games if team in (g.home, g.away)}
    return sum(r[col] for r in _rows(table)
               if (r["year"], r["kind_code"], r["game_sno"]) in keys
               and r["visiting_home_type"] == keys[(r["year"], r["kind_code"], r["game_sno"])])


# ------------------------------------------------------------------ E1：原始計數 → 率


@pytest.mark.parametrize("team", ["AJL011", "ACN011"])
def test_series_counts_equal_direct_row_sums_2025_c(team):
    games = _games(2025, "C")
    assert len(games) == 5
    t = core.aggregate(team, games, _index(games))
    for k, col in core.BAT_MAP.items():
        assert t.counts[k] == _manual_sum(games, team, "batting", col), k
    for k, col in core.PIT_MAP.items():
        assert t.counts[k] == _manual_sum(games, team, "pitching", col), k
    outs = (_manual_sum(games, team, "pitching", "inning_pitched_cnt") * 3
            + _manual_sum(games, team, "pitching", "inning_pitched_div3"))
    assert t.counts["pit_outs"] == outs
    assert t.reasons == {}
    # 勝敗由 games 比分（2025 台灣大賽：樂天 4 勝 1 敗）
    assert (t.counts["wins"], t.counts["losses"]) == ((4, 1) if team == "AJL011" else (1, 4))


def test_rates_equal_formula_recompute():
    games = _games(2025, "C")
    t = core.aggregate("AJL011", games, _index(games))
    c = t.counts
    m, why = core.metrics(c)
    assert why == {}
    obp = (c["bat_h"] + c["bat_bb"] + c["bat_hbp"]) / (c["bat_ab"] + c["bat_bb"] + c["bat_hbp"] + c["bat_sf"])
    assert m["ops"] == pytest.approx(obp + c["bat_tb"] / c["bat_ab"], abs=0)
    assert m["era"] == 27 * c["pit_er"] / c["pit_outs"]
    assert m["whip"] == 3 * (c["pit_h"] + c["pit_bb"]) / c["pit_outs"]
    bip = c["pit_bf"] - c["pit_bb"] - c["pit_hbp"] - c["pit_so"] - c["pit_hr"]
    assert m["der"] == 1 - (c["pit_h"] - c["pit_hr"]) / bip
    assert m["rf_pg"] == c["runs_for"] / c["games"]
    assert m["ra_pg"] == c["runs_against"] / c["games"]


def test_h2h_2025_a_matches_official_h2h_record():
    """2025 A ACN011 對 AJL011 官方 h2h（team_standings season_code 0）為 14-0-10。"""
    games = _games(2025, "A", {"ACN011", "AJL011"})
    assert len(games) == 24
    t = core.aggregate("ACN011", games, _index(games))
    assert (t.counts["wins"], t.counts["ties"], t.counts["losses"]) == (14, 0, 10)


# ------------------------------------------------------------------ E3：G11


def test_ops_is_unrounded_obp_plus_slg_not_between_games_rounding():
    """真實 2025 A 對戰樣本中找出四捨五入 OPS 與未四捨五入 OPS 不同的列，以本卡為準。"""
    games = _games(2025, "A", {"ACN011", "AJL011"})
    idx = _index(games)
    differ = 0
    for g in games:
        for team in (g.home, g.away):
            t = core.aggregate(team, [g], idx)
            c = t.counts
            ours = core.metrics(c)[0]["ops"]
            b2b3hr_tb = c["bat_tb"] - c["bat_h"]  # batting_rates 由 2B/3B/HR 推 TB；這裡讓 TB 一致
            old = batting_rates({"ab": c["bat_ab"], "h": c["bat_h"], "b2": b2b3hr_tb, "b3": 0, "hr": 0,
                                 "bb": c["bat_bb"], "hbp": c["bat_hbp"], "sf": c["bat_sf"]})["ops"]
            exact = ((c["bat_h"] + c["bat_bb"] + c["bat_hbp"])
                     / (c["bat_ab"] + c["bat_bb"] + c["bat_hbp"] + c["bat_sf"]) + c["bat_tb"] / c["bat_ab"])
            assert ours == exact
            if old is not None and round(ours, 3) != old:
                differ += 1
    assert differ > 0, "真實樣本中應存在四捨五入 OPS 與未四捨五入 OPS 顯示不同的列"


def test_era_is_total_er_over_total_outs_not_mean_of_game_era():
    games = _games(2025, "C")
    idx = _index(games)
    t = core.aggregate("ACN011", games, idx)
    total = core.metrics(t.counts)[0]["era"]
    per_game = []
    for g in games:
        c = core.aggregate("ACN011", [g], idx).counts
        per_game.append(27 * c["pit_er"] / c["pit_outs"])
    assert total == 27 * t.counts["pit_er"] / t.counts["pit_outs"]
    assert not math.isclose(total, sum(per_game) / len(per_game))


def test_core_has_no_player_rate_averaging_or_rounding():
    src = Path(core.__file__).read_text(encoding="utf-8")
    assert "round(" not in src
    assert "batting_rates" not in src


# ------------------------------------------------------------------ E4：缺值非 0


def test_missing_one_side_box_is_null_with_reason_not_zero():
    games = _games(2025, "C")
    victim = games[2]
    bat = [r for r in _rows("batting")
           if not ((r["year"], r["kind_code"], r["game_sno"]) == victim.key and r["visiting_home_type"] == "2")]
    t = core.aggregate(victim.home, games, _index(games, bat=bat))
    for k in core.BAT_KEYS:
        assert t.counts[k] is None
        assert t.reasons[k] == [f"box_missing:{core.key_str(victim.key)}"]
    for k in core.PIT_KEYS:
        assert t.counts[k] is not None  # 投手 box 仍在
    m, why = core.metrics(t.counts, t.reasons)
    assert m["ops"] is None and why["ops"] == [f"box_missing:{core.key_str(victim.key)}"]
    assert m["era"] is not None
    # 對手不受影響
    other = core.aggregate(victim.away, games, _index(games, bat=bat))
    assert other.counts["bat_ab"] is not None


def test_null_column_is_null_with_reason_not_zero():
    games = _games(2025, "C")
    pit = copy.deepcopy(_rows("pitching"))
    target = next(r for r in pit if (r["year"], r["kind_code"], r["game_sno"]) == games[0].key)
    target["earned_runs"] = None
    team = games[0].home if target["visiting_home_type"] == "2" else games[0].away
    t = core.aggregate(team, games, _index(games, pit=pit))
    assert t.counts["pit_er"] is None and t.reasons["pit_er"] == ["column_null:earned_runs"]
    m, why = core.metrics(t.counts, t.reasons)
    assert m["era"] is None and why["era"] == ["column_null:earned_runs"]
    assert m["whip"] is not None


def test_null_role_type_only_nulls_starter_share():
    games = _games(2025, "C")
    pit = copy.deepcopy(_rows("pitching"))
    target = next(r for r in pit if (r["year"], r["kind_code"], r["game_sno"]) == games[0].key)
    target["role_type"] = None
    team = games[0].home if target["visiting_home_type"] == "2" else games[0].away
    t = core.aggregate(team, games, _index(games, pit=pit))
    raw, why = core.style_raw(t.counts, t.reasons)
    assert raw["starter_share"] is None and why["starter_share"] == ["column_null:role_type"]
    assert raw["kpct"] is not None and t.counts["pit_outs"] is not None


def test_unknown_visiting_home_type_nulls_both_sides():
    games = _games(2025, "C")
    bat = copy.deepcopy(_rows("batting"))
    next(r for r in bat if (r["year"], r["kind_code"], r["game_sno"]) == games[1].key)["visiting_home_type"] = "9"
    idx = _index(games, bat=bat)
    for team in (games[1].home, games[1].away):
        counts, reasons = idx[(games[1].key, team)]
        assert all(counts[k] is None for k in core.BOX_KEYS)
        assert reasons["bat_ab"] == ["column_null:visiting_home_type"]


def test_zero_denominator_is_null_not_zero():
    counts = {k: 0 for k in core.COUNT_KEYS}
    m, why = core.metrics(counts)
    assert all(v is None for v in m.values())
    assert all(why[k] == ["zero_denominator"] for k in core.METRIC_KEYS)


def test_coverage_reports_missing_games():
    games = _games(2025, "C")
    pit = [r for r in _rows("pitching") if (r["year"], r["kind_code"], r["game_sno"]) != games[4].key]
    cov = core.coverage(games, _index(games, pit=pit))
    assert cov["expected_games"] == 5 and cov["covered_games"] == 4
    assert {m["game_key"] for m in cov["missing"]} == {core.key_str(games[4].key)}


def test_series_box_only_over_covered_games():
    games = _games(2025, "C")
    pit = [r for r in _rows("pitching") if (r["year"], r["kind_code"], r["game_sno"]) != games[4].key]
    bat = [r for r in _rows("batting") if (r["year"], r["kind_code"], r["game_sno"]) != games[4].key]
    covered = [g.key for g in games[:4]]
    t = core.aggregate("AJL011", games, _index(games, bat=bat, pit=pit), box_games=covered)
    assert t.counts["games"] == 5  # 勝敗由 games 判定，不受 box 缺漏影響
    assert t.counts["bat_ab"] == _manual_sum(games[:4], "AJL011", "batting", "at_bats")
    assert t.reasons == {}


# ------------------------------------------------------------------ E6：連續紀錄同 scope


def test_e_and_c_streaks_are_independent_for_same_team():
    """2025 樂天：E 以三連勝晉級（L W W W），C 前兩戰連勝。C 第 2 戰後本系列連續＝2 連勝，
    若跨賽別串接會變成 5 連勝——本卡 scope 不跨賽別（G09）。"""
    e, c = _games(2025, "E"), _games(2025, "C")
    se = core.aggregate("AJL011", e, _index(e)).sequence
    sc = core.aggregate("AJL011", c[:2], _index(c)).sequence
    assert {k[1] for k, _ in se} == {"E"} and {k[1] for k, _ in sc} == {"C"}
    assert core.trailing_streak(se) == {"result": "W", "len": 3, "through": "2025/E/4"}
    assert core.trailing_streak(sc) == {"result": "W", "len": 2, "through": "2025/C/2"}
    assert core.trailing_streak(se + sc)["len"] == 5  # 負控：跨賽別串接的錯誤結果


def test_tie_breaks_streak_on_real_sequence():
    games = _games(2025, "A", {"AJL011", "AKP011"}, box_only=False)
    assert len(games) == 24
    seq = [(g.key, g.result_for("AJL011")) for g in core.sort_games(games)]
    assert [r for _, r in seq].count("T") == 1
    i = next(i for i, (_, r) in enumerate(seq) if r == "T")
    st = core.trailing_streak(seq[: i + 1])
    assert st["result"] == "T" and st["len"] == 1
    if i + 1 < len(seq):
        after = core.trailing_streak(seq[: i + 2])
        assert after["len"] == 1  # 和局之後重新起算


def test_max_streaks_matches_special_records_rule():
    seq = [((2025, "A", n), r) for n, r in enumerate("WWLTWWWLLT", start=1)]
    assert core.max_streaks(seq) == (3, 2)
    assert core.trailing_streak(seq) == {"result": "T", "len": 1, "through": "2025/A/10"}


# ------------------------------------------------------------------ E5：共享尺度與方向


def test_shared_scale_expands_and_never_clips():
    assert core.shared_scale([0.70, 0.72, None], [0.53, 0.80]) == {"min": 0.53, "max": 0.80}
    assert core.shared_scale([None], [None]) is None
    assert {d["key"]: d["higher_is_better"] for d in core.METRIC_DEFS} == {
        "ops": True, "rf_pg": True, "ra_pg": False, "era": False, "whip": False, "der": True}


# ------------------------------------------------------------------ 球風（沿凍結公式）


def test_style_raw_reuses_frozen_formulas():
    games = _games(2025, "C")
    c = core.aggregate("ACN011", games, _index(games)).counts
    raw, why = core.style_raw(c)
    assert why == {}
    agg = {"pa": c["bat_pa"], "ab": c["bat_ab"], "h": c["bat_h"], "singles": c["bat_1b"], "tb": c["bat_tb"],
           "sh": c["bat_sh"], "sf": c["bat_sf"], "bb": c["bat_bb"], "hbp": c["bat_hbp"], "so": c["bat_so"],
           "sb": c["bat_sb"], "cs": c["bat_cs"], "outs": c["pit_outs"], "starter_outs": c["pit_starter_outs"],
           "pa_against": c["pit_bf"], "h_a": c["pit_h"], "hr_a": c["pit_hr"], "bb_a": c["pit_bb"],
           "hbp_a": c["pit_hbp"], "so_a": c["pit_so"]}
    assert raw == ts.raw_axes(agg)


def test_season_style_none_when_any_component_unknown():
    assert core.season_style({"A": {"x": 1.0}, "B": {"x": None}}) is None


# ------------------------------------------------------------------ 雜湊


def test_rows_digest_is_order_independent_and_content_sensitive():
    games = _games(2025, "C")
    idx = _index(games)
    rows = [core.row_from_totals("season", t, "", core.aggregate(t, games, idx)) for t in ("ACN011", "AJL011")]
    d = core.rows_digest(rows)
    assert d == core.rows_digest(list(reversed(rows)))
    mutated = copy.deepcopy(rows)
    mutated[0]["bat_ab"] += 1
    assert core.rows_digest(mutated) != d
    assert core.games_fingerprint(2025, games) == core.games_fingerprint(2025, list(reversed(games)))


# ------------------------------------------------------------------ E2：G10 與 D3 的程式掃描


def test_g10_no_current_snapshot_tables_and_d3_no_report_background():
    """本卡模組不得讀 team_current／*_current 半季快照（G10），也不得 import 舊報告背景計算（D3）。"""
    import ast
    import re

    pkg = Path(core.__file__).parent
    files = sorted(pkg.glob("*.py"))
    assert {f.name for f in files} >= {"core.py", "builder.py", "reader.py", "sync.py"}
    for f in files:
        src = f.read_text(encoding="utf-8")
        tree = ast.parse(src)
        # 只掃程式裡的字串常值（SQL 在這裡）；docstring 裡的「⛔ 不讀 team_current」是說明不是讀取。
        docs = {id(n.body[0].value) for n in ast.walk(tree)
                if isinstance(n, ast.Module | ast.FunctionDef | ast.ClassDef) and n.body
                and isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant)}
        literals = " ".join(n.value for n in ast.walk(tree)
                            if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docs)
        tables = (set(re.findall(r"cpbl\.([a-z_]+_current)\b", literals))
                  | set(re.findall(r"\b((?:team|batting|pitching|fielding)_current)\b", literals)))
        tables -= {"team_comparison_current"}
        assert not tables, (f.name, tables)
        assert "team_comparison_current" in literals or f.name in ("core.py", "__init__.py"), f.name
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                imported |= {f"{node.module}.{a.name}" for a in node.names} | {node.module or ""}
            elif isinstance(node, ast.Import):
                imported |= {a.name for a in node.names}
            elif isinstance(node, ast.Name | ast.Attribute):
                name = node.id if isinstance(node, ast.Name) else node.attr
                assert name != "team_background", f.name
        assert not {m for m in imported if m.startswith("cpbl.reports")}, (f.name, imported)
