"""救援成功改用官方（需求方 2026-09-23 裁定）的離線測試（無 DB 依賴）。

樣本皆取自真實資料：
  - 2026-A-99：官方旗標記 0000003331 救援成功，但 games.closer_id 是空的（closer_id 漏記的 3 場之一）。
  - 2023-A-189：沒有旗標、closer_id 空；規則 9.19 推算把登板第一球就被轟的分數算進登板領先
    （4 分讀成 3 分）而誤記 0000002348 救援——官方季累計他 2 次、推算 3 次。
    livelog 只留各投手首筆事件（推算只讀這些），`decide()` 結果與整場 livelog 相同。
"""

from __future__ import annotations

import pytest

from cpbl.models import pitcher_decisions as pd

REAL_2026_A_99_SAVE_FLAGS = [
    ("0000002303", False), ("0000003331", True), ("0000003639", False), ("0000005315", False),
    ("0000005604", False), ("0000006850", False), ("0000007292", False), ("0000007597", False),
]

_LL_COLS = ("main_event_no", "visiting_home_type", "pitcher_acnt", "first_base", "second_base",
            "third_base", "visiting_score", "home_score")
REAL_2023_A_189_LIVELOG = [dict(zip(_LL_COLS, r, strict=True)) for r in (
    ("0110001000", "1", "0000005731", None, None, None, 0, 0),
    ("0120001000", "2", "0000006496", None, None, None, 0, 0),
    ("0710002000", "1", "0000006127", None, None, None, 0, 4),
    ("0720001000", "2", "0000005372", None, None, None, 0, 4),
    ("0820002000", "2", "0000005555", None, None, None, 0, 4),
    ("0910002000", "1", "0000002348", None, None, None, 1, 4),   # 登板第一球即被轟
)]
_PG_COLS = ("pitcher_acnt", "visiting_home_type", "game_result", "relief_point",
            "inning_pitched_cnt", "inning_pitched_div3")
REAL_2023_A_189_PITCHING = [dict(zip(_PG_COLS, r, strict=True)) for r in (
    ("0000002348", "2", "", 0, 1, 0),
    ("0000005372", "1", "", 0, 1, 0),
    ("0000005555", "1", "", 0, 1, 0),
    ("0000005731", "2", "勝", 0, 6, 0),
    ("0000006127", "2", "", 0, 2, 0),
    ("0000006496", "1", "敗", 0, 6, 0),
)]


@pytest.mark.parametrize("flags,closer,expected", [
    (REAL_2026_A_99_SAVE_FLAGS, None, {"0000003331"}),   # closer_id 漏記，旗標補上
    ([("p1", True)], "p2", {"p1"}),                       # 兩個官方來源不一致時旗標優先
    ([("p1", False)], "p2", {"p2"}),                      # 旗標無人、closer_id 有值
    ([("p1", False), ("p2", None)], None, set()),         # 有旗標列＝官方判定無人救援
    ([], "p2", {"p2"}),                                   # 沒旗標（往年／季後）用 closer_id
    ([], None, None),                                     # 兩個官方來源都沒有 → 交給推算
])
def test_official_saves_precedence(flags, closer, expected) -> None:
    assert pd.official_saves(flags, closer) == expected


def test_no_official_source_still_infers() -> None:
    """saves=None（無官方來源）維持推算——含已知誤判，這裡釘住現況而非背書。"""
    dec = pd.decide(REAL_2023_A_189_LIVELOG, REAL_2023_A_189_PITCHING, 4, 1)
    assert dec == {"0000005731": "W", "0000006496": "L", "0000002348": "SV"}


def test_official_empty_set_suppresses_inference(monkeypatch: pytest.MonkeyPatch) -> None:
    """官方判定無人救援成功時不得再推算：同一場推算會誤記 0000002348。"""
    def boom(*_a, **_k):
        raise AssertionError("有官方來源的場次不得再推算救援成功")

    monkeypatch.setattr(pd, "_inferred_saves", boom)
    dec = pd.decide(REAL_2023_A_189_LIVELOG, REAL_2023_A_189_PITCHING, 4, 1, saves=set())
    assert dec == {"0000005731": "W", "0000006496": "L"}


def test_official_saver_replaces_the_inferred_one() -> None:
    dec = pd.decide(REAL_2023_A_189_LIVELOG, REAL_2023_A_189_PITCHING, 4, 1,
                    saves={"0000006127"})
    assert dec["0000006127"] == "SV"
    assert "0000002348" not in dec


def test_official_saver_never_overwrites_win_or_loss() -> None:
    dec = pd.decide(REAL_2023_A_189_LIVELOG, REAL_2023_A_189_PITCHING, 4, 1,
                    saves={"0000005731", "0000006496"})
    assert dec["0000005731"] == "W"
    assert dec["0000006496"] == "L"


def test_official_saver_overrides_hold() -> None:
    pitching = [{**r, "relief_point": 1} if r["pitcher_acnt"] == "0000006127" else r
                for r in REAL_2023_A_189_PITCHING]
    assert pd.decide(REAL_2023_A_189_LIVELOG, pitching, 4, 1)["0000006127"] == "HLD"
    assert pd.decide(REAL_2023_A_189_LIVELOG, pitching, 4, 1,
                     saves={"0000006127"})["0000006127"] == "SV"


def test_closer_sql_reads_flags_before_closer_id() -> None:
    """SQL 版與 `official_saves` 同一順序：coalesce(旗標救援者, closer_id)。"""
    sql = pd.official_closer_sql("g")
    assert sql.startswith("coalesce((SELECT min(sgf.pitcher_acnt) FROM cpbl.pitching_game_flags sgf ")
    assert "sgf.is_save_ok" in sql
    assert sql.endswith(", g.closer_id)")
    for col in ("year", "kind_code", "game_sno"):
        assert f"sgf.{col}=g.{col}" in sql
