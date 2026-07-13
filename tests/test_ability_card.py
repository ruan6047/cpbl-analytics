"""ABILITY-2 核心行為測試（無 DB）：SQL 不變量斷言 + `_ability_card` 綜合組成邏輯。

SQL 端（percent_rank/年代校正）依賴 PostgreSQL 無法離線執行，故以「產生的 SQL 必須
含關鍵結構」做回歸防線——這些結構每一條都對應一個已知缺陷或紅線：
kind_code='A'（本季守備母體混二軍 bug）、PARTITION BY IS NULL（缺值列拿最高 PR bug）、
k_pr AS weapon_pr（舊 GREATEST 武器軸 ~50 數學下限）、÷該年聯盟均值（跨年代可比性紅線）。
Python 端用 fake cursor 直測權重重正規化與退回行為。
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from cpbl.api.routers.ability import _ability_card, _bat_ability_sql, _pit_ability_sql


def _norm(sql: str) -> str:
    return " ".join(sql.split())


# ---- SQL 不變量：本季母體過濾 ----


def test_season_fielding_pool_excludes_farm():
    # 舊 bug：fielding_current 未過濾 kind_code='A'，2026 混入二軍列灌水母體
    sql = _norm(_bat_ability_sql("season"))
    assert "FROM cpbl.fielding_current WHERE year=%(yr)s AND kind_code='A'" in sql


# ---- SQL 不變量：NULL 列隔離於 percent_rank 之外 ----


@pytest.mark.parametrize("scope", ["career", "season"])
def test_wsb_null_rows_isolated_from_percent_rank(scope):
    # 缺 wSB 機會的列若進排序，NULL 排最後會拿到 ~100 PR
    sql = _norm(_bat_ability_sql(scope))
    assert (
        "CASE WHEN wsb IS NOT NULL THEN percent_rank() OVER "
        "(PARTITION BY (wsb IS NULL) ORDER BY wsb) END wsb_pr" in sql
    )


@pytest.mark.parametrize("scope", ["career", "season"])
@pytest.mark.parametrize("col", ["gb", "fb"])
def test_pitch_style_null_rows_isolated_from_percent_rank(scope, col):
    sql = _norm(_pit_ability_sql(scope))
    assert (
        f"CASE WHEN {col} IS NOT NULL THEN percent_rank() OVER "
        f"(PARTITION BY ({col} IS NULL) ORDER BY {col}) END {col}_pr" in sql
    )


# ---- SQL 不變量：三振固定軸（武器軸下限修正） ----


@pytest.mark.parametrize("scope", ["career", "season"])
def test_weapon_axis_is_fixed_strikeout(scope):
    # 舊版 GREATEST(k,gb,fb)：gb/fb 互為倒數 → PR 互補 → max 恆 ≥~50，半個刻度永不使用
    sql = _norm(_pit_ability_sql(scope))
    assert "k_pr AS weapon_pr" in sql
    assert "GREATEST" not in sql.upper()
    # 風格（weapon_type）僅供 signature 徽章，總評重排不含 gb_pr/fb_pr
    ov = sql.split(" ov AS ")[1]
    assert "gb_pr" not in ov.split("FROM pr")[0]


# ---- SQL 不變量：生涯年代校正、本季不校正 ----


def test_batter_career_rates_era_adjusted_by_year_league_mean():
    sql = _norm(_bat_ability_sql("career"))
    assert "JOIN lg l USING (year)" in sql  # 逐年聯盟均值 CTE
    for m in ("l.contact", "l.power", "l.eye", "l.speed", "l.obp", "l.slg"):
        assert f"/NULLIF({m},0)" in sql, f"生涯 {m} 未除以該年聯盟均值"
    # 守備同樣校正（守位×年均值；聯盟 K 升→滾進球減，範圍值跨年代不可比）
    assert "JOIN pos_lg l USING (pos, year)" in sql


def test_batter_season_rates_not_era_adjusted():
    # 本季為單一年母體，不需（也不可）再除年均值
    sql = _norm(_bat_ability_sql("season"))
    assert "JOIN lg" not in sql


def test_pitcher_career_rates_era_adjusted_and_fip_calibrated():
    sql = _norm(_pit_ability_sql("career"))
    assert "JOIN lg l USING (year)" in sql
    for m in ("l.k", "l.bb9", "l.hr9", "l.era"):
        assert f"/NULLIF({m},0)" in sql, f"生涯 {m} 未除以該年聯盟均值"
    assert "l.era - l.fipc0" in sql  # FIP 常數逐年校準到該年聯盟 ERA
    # 續航刻意不校正：IP/G、登板數＝真實負荷，跨年代差異是事實非尺度偏差
    assert "CASE WHEN gs*2 >= g THEN ip/NULLIF(g,0) ELSE g::float END stamina" in sql


def test_career_pool_excludes_partial_coverage_metrics():
    # 紅線：2018+/2026-only 數據不入生涯 PR 母體（同池不同人組成不同即失去可比性）
    for sql in (_bat_ability_sql("career"), _pit_ability_sql("career")):
        assert "catcher_runs" not in sql
        assert "advanced_stats" not in sql


# ---- `_ability_card` 組成邏輯（fake cursor 回放） ----


class _Cur:
    """依 execute 順序回放 (欄名列表, 單列) 的最小 cursor 假件。"""

    def __init__(self, results):
        self._results = list(results)
        self.executed: list[str] = []
        self._cur = None

    def execute(self, sql, params=None):
        self.executed.append(sql)
        self._cur = self._results.pop(0)

    @property
    def description(self):
        return [SimpleNamespace(name=n) for n in self._cur[0]]

    def fetchone(self):
        return self._cur[1]


_BAT_COLS = ["contact", "power", "eye", "speed", "defense", "wsb",
             "contact_pr", "power_pr", "eye_pr", "speed_pr", "defense_pr", "wsb_pr",
             "is_catcher", "ov_pr"]
_PIT_COLS = ["weapon", "control", "hr_suppress", "command", "stamina", "fip",
             "weapon_pr", "control_pr", "hr_suppress_pr", "command_pr", "stamina_pr", "fip_pr",
             "is_starter", "ov_pr", "weapon_type"]


def _bat_row(**over):
    r = {"contact": 0.82, "power": 0.15, "eye": 0.08, "speed": 0.1, "defense": 2.5, "wsb": 0.002,
         "contact_pr": 0.70, "power_pr": 0.60, "eye_pr": 0.50, "speed_pr": 0.40,
         "defense_pr": 0.55, "wsb_pr": 0.80, "is_catcher": False, "ov_pr": 0.55}
    r.update(over)
    return [r[c] for c in _BAT_COLS]


def _pit_row(**over):
    r = {"weapon": 5.0, "control": 2.5, "hr_suppress": 0.8, "command": 3.5, "stamina": 6.0,
         "fip": 3.8, "weapon_pr": 0.20, "control_pr": 0.75, "hr_suppress_pr": 0.60,
         "command_pr": 0.50, "stamina_pr": 0.65, "fip_pr": 0.70,
         "is_starter": True, "ov_pr": 0.58, "weapon_type": "滾地"}
    r.update(over)
    return [r[c] for c in _PIT_COLS]


def _axis(card, key):
    return next(a for a in card["axes"] if a["key"] == key)


def test_speed_axis_blends_wsb_60_raw_40():
    card = _ability_card(_Cur([(_BAT_COLS, _bat_row())]), "P1", "batting", "career", 2026)
    speed = _axis(card, "speed")
    assert [(c["label"], c["weight"]) for c in speed["components"]] == [
        ("盜壘得分價值 wSB", 60), ("盜壘＋三壘打", 40)]
    assert speed["pr"] == round(0.6 * 80 + 0.4 * 40)


def test_speed_axis_falls_back_to_raw_rate_when_wsb_missing():
    # 缺 wSB → 權重重正規化為粗率 100%（方法說明已揭露此可比性邊界）
    card = _ability_card(_Cur([(_BAT_COLS, _bat_row(wsb=None, wsb_pr=None))]),
                         "P1", "batting", "career", 2026)
    speed = _axis(card, "speed")
    assert [(c["label"], c["weight"]) for c in speed["components"]] == [("盜壘＋三壘打", 100)]
    assert speed["pr"] == 40


def test_career_card_never_reads_season_only_advanced_stats():
    cur = _Cur([(_BAT_COLS, _bat_row())])
    card = _ability_card(cur, "P1", "batting", "career", 2026)
    assert len(cur.executed) == 1 and card["has_advanced"] is False


def test_pitcher_weapon_axis_stays_k_for_groundball_style():
    # 低 K 滾地投手：三振軸誠實落底（不被舊 GREATEST 拉抬），風格保留於徽章
    card = _ability_card(_Cur([(_PIT_COLS, _pit_row())]), "P1", "pitching", "career", 2026)
    weapon = _axis(card, "weapon")
    assert weapon["label"] == "三振" and weapon["pr"] == 20
    assert card["signature"] == "滾地"


def test_command_axis_blends_era_and_fip_evenly():
    card = _ability_card(_Cur([(_PIT_COLS, _pit_row())]), "P1", "pitching", "career", 2026)
    command = _axis(card, "command")
    assert [(c["label"], c["weight"]) for c in command["components"]] == [("ERA", 50), ("FIP", 50)]
    assert command["pr"] == round(0.5 * 50 + 0.5 * 70)


def test_no_qualifying_row_returns_unavailable():
    card = _ability_card(_Cur([(_BAT_COLS, None)]), "P1", "batting", "career", 2026)
    assert card == {"available": False, "role": "batting", "scope": "career"}
