"""VENUE-PARK1 核心行為測試（無 DB）：SQL 不變量 + `_aggregate_factors` 純函式。

SQL 不變量每條對應一個已知缺陷模式：
- 球場別名歸一（桃園/亞太副場）：漏了 → 同座球場被拆成兩場、2018–21 資料消失
- 季內配對（tv/ty 以 year+team join）：漏了 → 期望值混跨季聯盟環境，PF 失義
- kind A 限定與完成場過濾：漏了 → 混二軍/未開打 0-0 場
Python 端以手算合成資料驗 PF 公式（observed/expected、排除無基準隊、低樣本旗標）。
"""

from __future__ import annotations

from cpbl.api.routers.teams import _VENUES_DIM_SQL
from cpbl.api.routers.venues import (
    _BAT_EXTREME_SQL,
    _FACTORS_SQL,
    _PIT_EXTREME_SQL,
    FACTOR_STATS,
    MIN_POOLED_GAMES,
    MIN_SEASON_GAMES,
    _aggregate_factors,
    _canon,
)


def _norm(sql: str) -> str:
    return " ".join(sql.split())


# ---- SQL 不變量 ----

def test_factors_sql_normalizes_venue_aliases():
    sql = _norm(_FACTORS_SQL)
    assert "CASE g.venue WHEN '桃園' THEN '樂天桃園'" in sql
    assert "WHEN '亞太副場' THEN '亞太副'" in sql


def test_venue_sql_normalizes_historic_taichung_name():
    """台中與國體為同座歷史 CPBL 場地，列表與詳情不可拆成兩座。"""
    factors = _norm(_FACTORS_SQL)
    listing = _norm(_VENUES_DIM_SQL)
    assert "WHEN '台中' THEN '國體'" in factors
    assert listing.count("WHEN '台中' THEN '國體'") >= 2


def test_venue_list_sql_normalizes_historical_aliases():
    """列表與詳情必須把同座球場的歷史名稱合併，避免桃園遺失 2018–21 年份。"""
    sql = _norm(_VENUES_DIM_SQL)
    assert sql.count("CASE g.venue WHEN '桃園' THEN '樂天桃園'") >= 2
    assert sql.count("GROUP BY CASE g.venue") == 2


def test_factors_sql_matches_expected_within_season_and_team():
    # 期望值必須同季同隊配對：tv join ty 用 (year, team)
    sql = _norm(_FACTORS_SQL)
    assert "FROM tv JOIN ty USING (year, team)" in sql


def test_factors_sql_restricts_kind_a_completed():
    sql = _norm(_FACTORS_SQL)
    assert "g.kind_code = 'A'" in sql
    assert "g.home_score + g.away_score > 0" in sql


def test_extreme_sql_uses_official_career_and_min_sample():
    # 生涯口徑 year=9999；門檻參數化（不得無門檻回全表）
    bat, pit = _norm(_BAT_EXTREME_SQL), _norm(_PIT_EXTREME_SQL)
    assert "year = 9999" in bat and "plate_appearances >= %(min_pa)s" in bat
    assert "year = 9999" in pit and ">= %(min_outs)s" in pit
    # 生涯基準用主客 family（item_group_code='1'）合計，不是全 family 重複加總
    assert bat.count("item_group_code = '1'") == 1
    assert pit.count("item_group_code = '1'") == 1


def test_canon_aliases():
    assert _canon("桃園") == "樂天桃園"
    assert _canon("亞太副場") == "亞太副"
    assert _canon("台中") == "國體"
    assert _canon("大巨蛋") == "大巨蛋"


# ---- _aggregate_factors 純函式（合成資料手算對照）----

def _row(year, team, n, stats, n_else, else_stats):
    """組一列：(year, team, n, r..so, n_else, r_else..so_else)。"""
    return (year, team, n, *[stats.get(k, 0) for k in FACTOR_STATS],
            n_else, *[else_stats.get(k, 0) for k in FACTOR_STATS])


def test_pf_math_hand_computed():
    # 隊 X：在 v 打 10 場共 20 HR；其他球場 50 場 50 HR（場均 1.0）→ exp 10
    # 隊 Y：在 v 打 10 場共 10 HR；其他球場 40 場 80 HR（場均 2.0）→ exp 20
    # observed=30, expected=30 → PF=1.0（控制隊伍組成：Y 本來就會打更多 HR）
    rows = [
        _row(2024, "X", 10, {"hr": 20}, 50, {"hr": 50}),
        _row(2024, "Y", 10, {"hr": 10}, 40, {"hr": 80}),
    ]
    out = _aggregate_factors(rows)
    s = out["seasons"][0]
    assert s["games"] == 10 and isinstance(s["games"], int)   # 20 隊-場 = 10 場
    assert s["eligible_team_games"] == 20
    assert s["factors"]["hr"]["observed"] == 30.0
    assert s["factors"]["hr"]["expected"] == 30.0
    assert s["factors"]["hr"]["pf"] == 1.0


def test_pf_excludes_team_without_elsewhere_baseline():
    # n_else=0 的隊-季（整季只在此場打）無法估基準 → 排除於 obs/exp 並記數，不硬湊；
    # 但 games（實際場次）仍含被排除方的比賽
    rows = [
        _row(2024, "X", 10, {"hr": 20}, 50, {"hr": 50}),
        _row(2024, "Z", 6, {"hr": 99}, 0, {}),
    ]
    out = _aggregate_factors(rows)
    s = out["seasons"][0]
    assert out["excluded_team_games"] == 6
    assert s["excluded_team_games"] == 6 and s["eligible_team_games"] == 10
    assert s["games"] == 8               # (10+6) 隊-場 = 8 場實際比賽
    assert s["factors"]["hr"]["observed"] == 20.0   # Z 未混入


def test_games_stays_integer_when_one_side_of_a_game_is_excluded():
    # 查核退回缺陷重現：一場比賽只有單方有其他球場基準（另一方 n_else=0）。
    # 舊實作 games=隊-場/2=0.5，違反「場次」語意；修正後 games=1（整數）、
    # 估計基礎以 eligible_team_games=1 明示
    rows = [
        _row(2024, "X", 1, {"hr": 1}, 30, {"hr": 30}),   # 有基準
        _row(2024, "Z", 1, {"hr": 2}, 0, {}),            # 同一場的對手，被排除
    ]
    out = _aggregate_factors(rows)
    s = out["seasons"][0]
    assert s["games"] == 1 and isinstance(s["games"], int)
    assert s["eligible_team_games"] == 1 and s["excluded_team_games"] == 1
    assert out["pooled"]["games"] == 1 and isinstance(out["pooled"]["games"], int)


def test_pooled_sums_obs_exp_across_seasons_not_average_of_pf():
    # 2023：obs 10 / exp 5（PF 2.0，樣本小）；2024：obs 100 / exp 100（PF 1.0）
    # 合併必須 = 110/105 ≈ 1.048，而不是 (2.0+1.0)/2 = 1.5
    rows = [
        _row(2023, "X", 4, {"hr": 10}, 40, {"hr": 50}),     # exp = 4×50/40 = 5
        _row(2024, "X", 50, {"hr": 100}, 50, {"hr": 100}),  # exp = 50×100/50 = 100
    ]
    out = _aggregate_factors(rows)
    pooled = out["pooled"]["factors"]["hr"]
    assert pooled["observed"] == 110.0 and pooled["expected"] == 105.0
    assert pooled["pf"] == 1.048


def test_low_sample_flags_keyed_on_eligible_team_games():
    # 10 隊-場 < 2×30 → 單季 low；也 < 2×60 → 合併 low
    rows = [_row(2024, "X", 10, {"hr": 5}, 50, {"hr": 50})]
    out = _aggregate_factors(rows)
    assert out["seasons"][0]["low_sample"] is True
    assert out["pooled"]["low_sample"] is True
    # 估計基礎達門檻即不掛 low（60 隊-場 = 門檻 30 場的 2 倍）
    rows = [_row(2024, "X", 30, {"hr": 5}, 30, {"hr": 5}),
            _row(2024, "Y", 30, {"hr": 5}, 30, {"hr": 5})]
    out = _aggregate_factors(rows)
    assert out["seasons"][0]["low_sample"] is False
    assert MIN_SEASON_GAMES == 30 and MIN_POOLED_GAMES == 60   # 門檻改動需連動文件
