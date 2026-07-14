"""奪冠總教練 canonical 資料集回歸測試。

紅線：冠軍歸屬。`managers.championships`（維基）漏記真正的冠軍教練，且任期年份無法決定
季中換帥年的歸屬，故以本資料集為唯一事實來源；此處守住「每個冠軍年恰一位、且球團與
championships 一致」的不變式。
"""

from __future__ import annotations

import re
from pathlib import Path

from tests.test_championships import _seed_rows as _champion_rows

_MIGRATION = Path(__file__).parents[1] / "migrations" / "054_championship_managers.sql"
_SEED_ROW = re.compile(
    r"\((\d{4}), '([^']+)',\s+'([^']+)', '([^']+)', 'verified'",
)


def _manager_rows() -> dict[int, tuple[str, str, str]]:
    sql = _MIGRATION.read_text(encoding="utf-8")
    return {
        int(year): (name, franchise, source_url)
        for year, name, franchise, source_url in _SEED_ROW.findall(sql)
    }


def test_every_championship_season_has_exactly_one_manager():
    managers = _manager_rows()

    assert sorted(managers) == sorted(_champion_rows())
    assert len(managers) == 36


def test_manager_franchise_matches_championship_franchise():
    """奪冠總教練的球團必須與該年冠軍隊的 franchise 一致，否則冠軍會歸錯隊。"""
    champions = _champion_rows()

    for year, (_name, franchise, _src) in _manager_rows().items():
        assert franchise == champions[year][2], f"{year} 球團不一致"


def test_mid_season_change_years_are_pinned():
    """季中換帥年最易出錯（多位候選），逐年釘死避免回歸。"""
    m = _manager_rows()

    assert m[2001][0] == "林易增"   # 3/20 接替林百亨
    assert m[2007][0] == "呂文生"   # 6/29 接任；大橋穰 4 月遭解任、羅國璋僅代理
    assert m[2011][0] == "呂文生"   # 任期至 2012/02/16
    assert m[2013][0] == "陳連宏"   # 代理總教練奪冠後真除
    assert m[2010][0] == "陳瑞振"   # 陳琦豐為首席教練
    assert m[2000][0] == "曾智偵"   # 竹之內雅史僅代理


def test_known_championship_totals():
    """維基欄位漏記的冠軍教練：計數必須反映實際奪冠年。"""
    counts: dict[str, int] = {}
    for name, _franchise, _src in _manager_rows().values():
        counts[name] = counts.get(name, 0) + 1

    assert counts["洪一中"] == 7      # 2006/2012/2014/2015/2017/2018/2019（維基記 0）
    assert counts["呂文生"] == 4      # 2007–2009、2011
    assert counts["古久保健二"] == 1  # 2025（維基記 0）
    assert "羅國璋" not in counts     # 首席教練／短暫代理，非冠軍總教練
    assert sum(counts.values()) == 36
