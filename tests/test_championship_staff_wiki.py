"""#470 冠軍隊年教練團 wikitext 解析（純函式；片段取自 2026-11-29 抓取的原文）。"""

from __future__ import annotations

from cpbl.ingest.championship_staff_wiki import (
    career_lines,
    league_year_mentioned,
    parse_tw_team_year,
    parse_zh_template,
)


def _by(people):
    return {p.name: p for p in people}


def test_tw_layered_roster_2023():
    wt = (":*一軍教練團：[[葉君璋]]（[[總教練]]）、[[黃煚隆]]、[[塞曼G.T|塞　曼]]、[[張泰山]]、"
          "[[張建銘(1980)|張建銘]]、[[王昊|王　昊]]\n"
          ":*二軍教練團：[[張家浩]]（[[總教練]]）、[[高須洋介]]、賈　西\n"
          ":*投　手：[[王維中]]\n")
    p = _by(parse_tw_team_year(wt))
    assert p["張泰山"].level == "一軍" and p["張泰山"].wiki_title == "張泰山"
    assert p["塞曼"].wiki_title == "塞曼G.T"
    assert p["張建銘"].notes == []  # 消歧義括號不當附註
    assert p["張家浩"].level == "二軍" and p["張家浩"].title == "總教練"
    assert p["賈西"].wiki_title is None
    assert "王維中" not in p  # 球員區塊不抽


def test_tw_manager_line_arrows_and_skip_executives_2007():
    wt = ("*領　隊：[[某甲]]\n"
          "*總教練：[[大橋穰]](至4月)-->[[羅國璋]](代理，4到6月)-->呂文生(6月起)\n"
          "*教　練：[[吳俊良]]、[[羅國璋]]、[[羅敏卿]](二軍教練)\n")
    p = _by(parse_tw_team_year(wt))
    assert "某甲" not in p
    assert p["大橋穰"].manager_line and any("至4月" in n for n in p["大橋穰"].notes)
    assert p["羅國璋"].level == "未分層" and p["羅國璋"].manager_line
    assert p["羅敏卿"].level == "二軍"


def test_tw_table_1999_and_line_note_2001():
    wt99 = ("| valign=\"top\" | '''總教練'''\n*85 [[徐生明]]\n'''教練'''\n*21 [[劉志昇]]\n"
            "| valign=\"top\" | '''投手'''\n*11 [[金德七]]\n")
    p = _by(parse_tw_team_year(wt99))
    assert set(p) == {"徐生明", "劉志昇"} and p["徐生明"].manager_line
    wt01 = "*教練團：[[榊原良行]]，王光輝，[[劉義傳]]，吳思賢。(王光輝與劉義傳仍兼任球員)\n"
    p = _by(parse_tw_team_year(wt01))
    assert any("兼任球員" in n for n in p["王光輝"].notes)
    assert not p["榊原良行"].notes


def test_tw_stops_before_other_unit_2016():
    wt = (":*一軍：[[葉君璋]]（[[總教練]]）、[[張家浩]]\n:*二軍：[[許國隆]]（[[總教練]]）\n"
          ":*[[義守大學棒球隊]]：[[曾智偵]]（[[總教練]]）、[[蕭任汶]]\n")
    assert set(_by(parse_tw_team_year(wt))) == {"葉君璋", "張家浩", "許國隆"}


def test_zh_template_separators_and_link_en():
    wt = ("| list1 = 1 [[某球員]] <br />總教練 24 [[林威助]]<br />  打擊教練 6 "
          "{{Link-en|塔克·威爾森|Tack Wilson|威爾森}}{{!w}}投手教練 37 [[傑夫·安德拉|飛　勇]] {{!}} "
          "外野教練 71 [[胡長豪]]{{!w}}牛棚教練92 [[黃亦志]]{{!w}}打擊教練 65 [[王峻杰|王峻-{杰}-]]\n"
          "*首席教練 77 [[蔡榮宗]]\n|below = x")
    z = {p.name: p.title for p in parse_zh_template(wt)}
    assert "某球員" not in z
    assert z == {"林威助": "總教練", "威爾森": "打擊教練", "飛勇": "投手教練", "胡長豪": "外野教練",
                 "黃亦志": "牛棚教練", "王峻杰": "打擊教練", "蔡榮宗": "首席教練"}


def test_league_year_and_career_lines():
    assert league_year_mentioned("…中華職棒34年…", 2023) == "職棒34年"
    assert league_year_mentioned("職棒十五年", 2004) == "職棒十五年"
    assert league_year_mentioned("職棒元年", 1990) == "職棒元年"
    assert league_year_mentioned("味全龍隊的職棒十五年", 2023) is None  # 頁名球隊年次不算
    wt = (":*[[中華職棒]][[味全龍隊]][[內野教練]]（[[2023年]]04月～[[2024年]]12月）\n"
          ":*[[中華職棒]][[味全龍隊]][[客座教練]]（[[2022年]]01月）\n"
          "[[Category:味全龍隊教練]]\n")
    assert career_lines(wt, ("味全",), 2023) == ["中華職棒味全龍隊內野教練（2023年04月～2024年12月）"]
