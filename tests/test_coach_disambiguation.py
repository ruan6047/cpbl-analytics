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


def test_strip_team_rename_keeps_role_only():
    """維基把改名寫成「A隊→B隊 職務」，職務欄殘留的隊名前綴要剝掉（純顯示，不動語意）。"""
    assert ch.strip_team_rename("La New熊隊→總教練") == "總教練"
    assert ch.strip_team_rename("統一獅隊→首席教練") == "首席教練"
    assert ch.strip_team_rename("總教練") == "總教練"


def test_strip_team_rename_yields_empty_for_pure_rename():
    """整行只有隊名沿革、沒有職務（純效力年資）→ 回空字串，由呼叫端 fallback 成 team_raw。"""
    assert ch.strip_team_rename("統一獅隊→") == ""
    assert ch.strip_team_rename("→大阪近鐵猛牛隊") == ""


def test_manual_title_override_is_recorded():
    """自動規則 fail-closed 的同名者，答案寫在人工指定表，不由程式猜。"""
    assert ch.MANUAL_PAGE_TITLES["大威"] == "大威D.W"


def test_parse_birthdate_handles_all_twbsball_formats():
    """實測 twbsball 有四種寫法；逐一寫死會漏（曾漏掉斜線與「生日」模板 → 148 列誤標待查）。"""
    assert ch.parse_birthdate("出生日期：{{BD|1961-05-14||:}}") == (1961, 5, 14)   # 洪一中
    assert ch.parse_birthdate("出生日期：{{BD|1978/8/6}}") == (1978, 8, 6)         # 彭政閔
    assert ch.parse_birthdate("出生日期：{{生日|1973/09/13}}") == (1973, 9, 13)    # 陳連宏
    assert ch.parse_birthdate("出生日期：1972年10月30日") == (1972, 10, 30)
    assert ch.parse_birthdate("查無此欄") is None


def test_short_team_name_needs_explicit_cpbl_league():
    """隊名簡稱在沒有「中華職棒」標示時不得比對——母企業旗下的別隊/同名機構會被誤掛。"""
    hoops = ch.parse_experience_row("[[富邦勇士籃球隊]]體能教練（[[2019年]]）")
    assert hoops["team_code"] is None          # 籃球隊，不是富邦悍將

    college = ch.parse_experience_row("[[中信金融管理學院]]棒球隊總教練（[[2020年]]）")
    assert college["team_code"] is None        # 大學，不是中信鯨

    pro = ch.parse_experience_row("[[中華職棒]][[富邦悍將隊]][[打擊教練]]（[[2021年]]）")
    assert pro["team_code"] == "AEO011"        # 明確標示中職 → 正常比對


def test_full_team_name_matches_without_league_tag():
    """全名本身無歧義，即使該行沒有聯盟標示也應正確對應。"""
    row = ch.parse_experience_row("[[時報鷹隊]]（[[1996年]]～[[1997年]]）")
    assert row["team_code"] == "AFF011"


def test_role_only_line_is_not_misclassified_as_player():
    """整行都是隊名＋職務（未對到中職隊）時要用整行判 phase，否則會落到預設『球員』。"""
    row = ch.parse_experience_row("獨立聯盟St. George Roadrunners總教練（[[2015年]]）")
    assert row["phase"] == "coach"


def test_experience_lines_are_deduplicated():
    """同一行同時出現在「經歷」與「年表」兩節時只取一次。"""
    wt = "==經歷==\n*[[台灣電力棒球隊]]\n==年表==\n*[[台灣電力棒球隊]]\n"
    assert ch.parse_experience_lines(wt) == ["[[台灣電力棒球隊]]"]


def test_seed_tenure_confirms_identity_without_player_birthday():
    """教練不一定當過中職球員（王建民只有大聯盟出賽），不能只靠球員生日驗證身分。

    種子名單（coaches/managers）記載了他實際在哪一隊、哪一年任職；條目若有相符的中職
    執教紀錄，即為同一人。比對要求同隊且任期涵蓋該年——只對到球隊或只對到年份都不算。
    """
    rows = [
        {"team_code": "ACN011", "from_year": 2023, "to_year": None, "pos": "投手教練"},
        {"team_code": "AEO011", "from_year": 2018, "to_year": 2019, "pos": "二軍客座投手教練"},
    ]
    assert ch.seed_confirms_identity(rows, [(2026, "ACN011")])   # 任期涵蓋 2026
    assert ch.seed_confirms_identity(rows, [(2018, "AEO011")])
    assert not ch.seed_confirms_identity(rows, [(2026, "ADD011")])  # 隊別不符
    assert not ch.seed_confirms_identity(rows, [(2015, "ACN011")])  # 年份不在任期內
    assert not ch.seed_confirms_identity(rows, [])


def test_parse_nickname_structured_field():
    """twbsball 的結構化欄位「綽號別稱」可直接採用（郭天信＝天哥／阿信）。"""
    assert ch.parse_nickname(":*綽號別稱：'''天哥'''、'''阿信'''") == (["天哥", "阿信"], "field")
    assert ch.parse_nickname(":*綽號別稱：[[金臂人]]") == (["金臂人"], "field")


def test_parse_nickname_prose_is_flagged_as_lower_confidence():
    """只寫在內文者（林智勝「大師兄」）句型鬆散、易誤抓，來源標 prose 供 needs_review。"""
    nick, src = ch.parse_nickname("'''林智勝'''，原名林智盛，外號「[[大師兄]]」，職棒時期改為現名。")
    assert nick == ["大師兄"]
    assert src == "prose"


def test_parse_nickname_absent():
    assert ch.parse_nickname("出生日期：{{BD|1990-01-01}}") is None


def test_nickname_field_label_variants():
    """欄位標籤沒有統一（實測：綽號別稱／暱稱別號／別號暱稱／暱號別號），只認一種會漏近半。"""
    for label in ("綽號別稱", "暱稱別號", "別號暱稱", "暱號別號"):
        assert ch.parse_nickname(f":*{label}：鄉長、香腸") == (["鄉長", "香腸"], "field")


def test_nickname_ignores_obsolete_prose_and_refs():
    """<ref> 註腳裝的是綽號由來（含已棄用舊稱）；「原本綽號叫 X」不得採用。

    ruan6047 指正：陳禹勳被抓成「蒼蠅」——那是他早已不用的舊稱，出現在解釋句與 ref 裡。
    """
    wt = (":*暱號別號：鄉長<ref>因以鄉民稱呼球迷</ref>、虎神"
          "<ref>原本陳禹勳的綽號叫「蒼蠅」，後來改叫「虎神」。</ref>、香腸")
    nick, src = ch.parse_nickname(wt)
    assert nick == ["鄉長", "虎神", "香腸"]
    assert "蒼蠅" not in nick
    assert src == "field"


def test_nickname_unions_field_and_prose():
    """欄位與內文取聯集：彭政閔欄位沒有他最著名的「恰恰」，該詞只在內文。"""
    wt = ":*綽號別稱：火星恰、恰哥\n他的外號「恰恰」廣為人知。"
    nick, src = ch.parse_nickname(wt)
    assert nick == ["火星恰", "恰哥", "恰恰"]
    assert src == "field+prose"


def test_nickname_strips_pipe_links():
    """[[鋒哥|抗日英雄]] 要取顯示文字，否則整串會被當成一個綽號。"""
    nick, _ = ch.parse_nickname(":*綽號別稱：[[鋒哥|抗日英雄]]、台灣巨砲")
    assert nick == ["抗日英雄", "台灣巨砲"]
