"""奪冠總教練 canonical 資料集回歸測試。

紅線：冠軍歸屬。`managers.championships`（維基）漏記真正的冠軍教練，且任期年份無法決定
季中換帥年的歸屬，故以本資料集為唯一事實來源；此處守住「每個冠軍年恰一位、且球團與
championships 一致」的不變式。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

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


def _award_winners() -> dict[int, str]:
    """DB 內的年度最佳總教練得獎者（player_awards）。無 DB 時回 None 供跳過。"""
    from cpbl.db import conn

    with conn() as c:
        rows = c.execute(
            "SELECT a.year, p.name FROM cpbl.player_awards a "
            "JOIN cpbl.players p ON p.id = a.player_id "
            "WHERE a.award = '年度最佳總教練'"
        ).fetchall()
    return {int(year): name for year, name in rows}


def test_award_winners_agree_with_canonical_managers():
    """**第三來源交叉驗證**：年度最佳總教練得獎者必須等於該年 canonical 冠軍教練。

    此獎為票選榮銜、**不是**冠軍歸屬的來源（非球員出身教練無 player_id 故缺 2024/25，
    且票選理論上可頒給非冠軍教練），但 2000–2023 實測 24/24 與 canonical 一致，是獨立
    於「維基任期 × twbsball 職稱」之外的驗證訊號——尤其守住季中換帥年。
    缺獎項資料的年份自然跳過（該獎本就不是來源，不得據以推翻 canonical）。

    需本機 DB；CI 無 Postgres 故跳過（push 前本機 pytest 會跑到）。
    """
    try:
        awards = _award_winners()
    except Exception as exc:  # noqa: BLE001 - 無 DB/表未建時跳過而非失敗
        pytest.skip(f"需本機 DB：{exc}")

    if not awards:
        pytest.skip("player_awards 無年度最佳總教練資料")

    managers = _manager_rows()
    mismatched = {
        year: (winner, managers[year][0])
        for year, winner in awards.items()
        if year in managers and managers[year][0] != winner
    }
    assert not mismatched, f"得獎者與 canonical 冠軍教練不符：{mismatched}"
