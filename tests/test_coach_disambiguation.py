"""twbsball 消歧義頁解析：同名者選人規則（紅線：嚴禁把別人的生平掛到教練頭上）。"""

from __future__ import annotations

from cpbl.ingest import cpbl_coaches_history as ch

_DISAMBIG = """　　臺灣棒球史上曾經出現過不只一個[[路易士]]，您要找的是：

#[[中華職棒]][[統一7-ELEVEn獅隊]][[打擊教練]]的[[路易士L.S|路易士]]。
#曾經效力於[[中華職棒]]的[[路易士R.L|路易士]]。

{{Disambig}}"""

_COACH_PAGE = """==經歷==
*[[中華職棒]][[統一7-ELEVEn獅隊]][[一軍]][[打擊教練]]（[[2025年]]～）
"""

# 同名球員：生日對得上 DB，但完全沒有教練經歷
_PLAYER_PAGE = """出生日期：1982年09月02日
==經歷==
*[[中華職棒]][[中信兄弟隊]]（[[2015年]]～[[2016年]]）
"""

_PAGES = {"路易士L.S": _COACH_PAGE, "路易士R.L": _PLAYER_PAGE}


def test_detects_disambiguation_page():
    assert ch.is_disambiguation(_DISAMBIG)
    assert not ch.is_disambiguation(_COACH_PAGE)


def test_lists_same_name_candidates():
    assert ch.disambiguation_candidates("路易士", _DISAMBIG) == ["路易士L.S", "路易士R.L"]


def test_coach_experience_wins_over_birthday_match(monkeypatch):
    """**順序是紅線**：先篩「有中職教練經歷」，生日只在多位教練候選間裁決。

    反例即此測資：路易士R.L 生日對得上 DB 球員卻毫無教練經歷。若讓生日優先，就會把
    同名球員的生平掛到教練頭上（洋將譯名相同者根本是不同人）。
    """
    monkeypatch.setattr(ch, "fetch_wikitext", lambda t: _PAGES.get(t))
    monkeypatch.setattr(ch.time, "sleep", lambda _s: None)

    resolved = ch.resolve_disambiguation("路易士", _DISAMBIG, [(1982, 9, 2)])

    assert resolved is not None
    assert resolved[0] == "路易士L.S"


def test_multiple_coach_candidates_without_birthday_are_skipped(monkeypatch):
    """兩位候選都有教練經歷且生日無法裁決 → 放棄（fail-closed），不得任選其一。"""
    pages = {"大威D.D": _COACH_PAGE, "大威D.W": _COACH_PAGE}
    disambig = "[[大威D.D|大威]] [[大威D.W|大威]] {{Disambig}}"
    monkeypatch.setattr(ch, "fetch_wikitext", lambda t: pages.get(t))
    monkeypatch.setattr(ch.time, "sleep", lambda _s: None)

    assert ch.resolve_disambiguation("大威", disambig, []) is None
