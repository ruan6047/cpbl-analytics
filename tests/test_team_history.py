"""隊史年表解析（twbsball 分類:職棒球隊年表）。"""

from __future__ import annotations

from cpbl.ingest.cpbl_team_history import (
    _split_names,
    parse_awards,
    parse_name_changes,
    parse_season,
    parse_staff,
    parse_team,
)


def test_season_from_cpbl_era():
    assert parse_season("味全龍隊/味全龍隊的職棒元年") == 1990
    assert parse_season("味全龍隊/味全龍隊的職棒六年") == 1995
    assert parse_season("統一7-ELEVEn獅隊/統一7-ELEVEn獅隊的職棒三十年") == 2019
    assert parse_season("兄弟象隊/兄弟象隊的業餘三年") is None    # 中職成立前，不屬職棒年份
    assert parse_season("三商虎隊隊史") is None                    # 總覽頁無年度


def test_team_from_page_title():
    assert parse_team("味全龍隊/味全龍隊的職棒六年") == "AAA011"
    assert parse_team("La New熊隊/La New熊隊的職棒七年") == "AJL011"   # 收斂到現行 franchise


def test_split_names_respects_parentheses():
    """括號註記本身含逗號（「季後，10月26日」），直接用逗號切會把整筆弄丟。"""
    assert _split_names("潘傑楷(季後，10月26日)、王鏡銘(8月20日)") == [
        ("潘傑楷", "季後，10月26日"), ("王鏡銘", "8月20日")]


def test_split_names_handles_missing_separator_and_arrow():
    """原文偶爾漏分隔符（「郭泰源（總教練）高政華」），季中換人寫成箭頭。"""
    assert _split_names("郭泰源（總教練）高政華") == [("郭泰源", "總教練"), ("高政華", None)]
    assert _split_names("黃煚隆→林瑋恩", split_arrow=True) == [("黃煚隆", None), ("林瑋恩", "接替前任")]
    # 改名欄的「舊-->新」是同一人，**不可**切開（切了會讓改名解析全滅——實測踩過）
    assert _split_names("薛惟中-->薛种帷") == [("薛惟中-->薛种帷", None)]


def test_staff_roles_are_verbatim_early_format():
    """早期只有「總教練」與「教練」兩級（ruan6047 指正）——不得腦補成助理教練／投手教練。"""
    wt = "==球隊人員==\n*總教練：田宮謙次郎\n*教　練：中村典夫、成田幸洋\n*投　手：黃平洋\n==年度戰績==\n"
    staff = parse_staff(wt)

    assert ("總教練", "田宮謙次郎", "", None) in staff
    assert ("教練", "中村典夫", "", None) in staff
    assert all(r[0] in ("總教練", "教練", "領隊", "副領隊") for r in staff)
    assert all(r[1] != "黃平洋" for r in staff)      # 逐年陣容屬次級來源，不收


def test_staff_modern_format_with_level():
    """近年格式：職稱標在括號內、且分一二軍。"""
    wt = ("==球隊陣容==\n*教練團成員：\n"
          ":*一軍教練團：黃甘霖（總教練）、高政華\n"
          ":*二軍教練團：高志綱（總教練）、林岳平\n==年度戰績==\n")
    staff = parse_staff(wt)

    assert ("總教練", "黃甘霖", "一軍", "總教練") in staff
    assert ("教練", "林岳平", "二軍", None) in staff


def test_name_changes_and_awards():
    wt = ("==球隊異動==\n*更改姓名：薛惟中-->薛种帷、潘彥廷-->潘傑楷(季後，10月26日)\n"
          "==獲獎紀錄==\n*一軍\n:*陳韻文獲得救援王\n*二軍\n:*林祐樂獲選金手套獎\n==年度大事紀==\n")

    assert parse_name_changes(wt) == [("薛惟中", "薛种帷", None),
                                      ("潘彥廷", "潘傑楷", "季後，10月26日")]
    assert ("二軍", "林祐樂", "金手套獎") in parse_awards(wt)
