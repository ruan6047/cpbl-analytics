from __future__ import annotations

from cpbl.ingest.cpbl_coaches_history import (
    parse_birthdate,
    parse_experience_lines,
    parse_experience_row,
)


def test_parse_birthdate():
    wt1 = "出生日期：1979年01月22日"
    assert parse_birthdate(wt1) == (1979, 1, 22)

    wt2 = "出生日期：[[1979年]]01月22日"
    assert parse_birthdate(wt2) == (1979, 1, 22)

    wt3 = "出生日期：[[1979年]][[1月22日]]"
    assert parse_birthdate(wt3) == (1979, 1, 22)

    wt4 = "沒有出生日期資料"
    assert parse_birthdate(wt4) is None

    wt5 = "出生日期：{{BD|1972-10-30||:}}"
    assert parse_birthdate(wt5) == (1972, 10, 30)

    wt6 = "出生日期：{{BD|1972年10月30日|...}}"
    assert parse_birthdate(wt6) == (1972, 10, 30)


def test_parse_experience_lines():
    wt = """
有些無關的文字
==經歷==
:*[[中華職棒]][[中信兄弟隊]]（2014年～2017年）
:*[[中華職棒]][[中信兄弟隊]][[總教練]]（2020年～2023年）
==個人年表==
這個章節不應該被當成經歷 bullet points
"""
    lines = parse_experience_lines(wt)
    assert len(lines) == 2
    assert lines[0] == "[[中華職棒]][[中信兄弟隊]]（2014年～2017年）"
    assert lines[1] == "[[中華職棒]][[中信兄弟隊]][[總教練]]（2020年～2023年）"


def test_parse_experience_row_coach():
    line = "[[中華職棒]][[中信兄弟隊]][[總教練]]（[[2020年]]12月07日～[[2023年]]05月10日）"
    res = parse_experience_row(line)
    assert res is not None
    assert res["phase"] == "coach"
    assert res["league"] == "中華職棒"
    assert res["team_code"] == "ACN011"
    assert res["team_raw"] == "中信兄弟隊"
    assert res["pos"] == "總教練"
    assert res["from_year"] == 2020
    assert res["to_year"] == 2023


def test_parse_experience_row_ongoing():
    line = "[[中華職棒]][[富邦悍將隊]]執行副領隊（[[2025年]]11月06日～）"
    res = parse_experience_row(line)
    assert res is not None
    assert res["phase"] == "other"
    assert res["league"] == "中華職棒"
    assert res["team_code"] == "AEO011"
    assert res["team_raw"] == "富邦悍將隊"
    assert res["pos"] == "執行副領隊"
    assert res["from_year"] == 2025
    assert res["to_year"] is None


def test_parse_experience_row_player():
    line = "[[日本職棒]][[阪神虎隊]]（[[2003年]]～[[2013年]]）"
    res = parse_experience_row(line)
    assert res is not None
    assert res["phase"] == "player"
    assert res["league"] == "日本職棒"
    assert res["team_code"] is None
    assert res["team_raw"] == "阪神虎隊"
    assert res["pos"] == "阪神虎隊"
    assert res["from_year"] == 2003
    assert res["to_year"] == 2013


def test_parse_experience_row_amateur():
    line = "[[國立臺灣體育運動大學棒球隊]]客座[[打擊教練]]（[[2024年]]04月13日～[[2024年]]10月）"
    res = parse_experience_row(line)
    assert res is not None
    assert res["phase"] == "coach" # since it has "打擊教練" it classifies as coach, which is correct!
    assert res["league"] is None
    assert res["team_code"] is None
    assert res["team_raw"] == "國立臺灣體育運動大學棒球隊"
    assert res["pos"] == "客座打擊教練"
    assert res["from_year"] == 2024
    assert res["to_year"] == 2024


def test_coach_profile_api_returns_history():
    from fastapi.testclient import TestClient

    from cpbl.api.main import app

    client = TestClient(app)
    response = client.get("/api/v1/people/coach/丘昌榮")
    assert response.status_code == 200
    data = response.json()
    assert "history" in data
    history = data["history"]
    assert len(history) > 0
    first_item = history[0]
    assert "phase" in first_item
    assert "team_raw" in first_item
    assert "pos" in first_item
    assert "from_year" in first_item


def test_player_career_api_returns_coach_history():
    from fastapi.testclient import TestClient

    from cpbl.api.main import app

    client = TestClient(app)
    response = client.get("/api/v1/players/0000000797/career")
    assert response.status_code == 200
    data = response.json()
    assert "coach_history" in data
    assert len(data["coach_history"]) > 0


def test_parse_experience_row_narrative():
    line = "2019年 --12月16日，球團宣布2020年新球季將擔任中信兄弟一軍總教練，並同時宣告預計採用全本土教練組成教練團…"
    res = parse_experience_row(line)
    assert res is not None
    assert res["phase"] == "note"


def test_parse_experience_row_foreign_collision():
    line = "[[日本職棒]][[東北樂天金鷲隊]]二軍[[監督]]（[[2016年]]～[[2017年]]）"
    res = parse_experience_row(line)
    assert res is not None
    assert res["team_code"] is None
    assert res["team_raw"] == "東北樂天金鷲隊"


def test_parse_experience_row_historical_mapping():
    line = "[[中華職棒]][[兄弟象隊]]（[[1992年]]～[[1999年]]）"
    res = parse_experience_row(line)
    assert res is not None
    assert res["team_code"] == "ACN011"
    assert res["team_raw"] == "兄弟象隊"
