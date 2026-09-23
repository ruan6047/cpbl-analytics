"""救援失敗改用官方逐場旗標（需求方 2026-09-23 裁定）的離線測試（無 DB 依賴）。

旗標樣本取自真實 2026-A-341（官方 3 位救援失敗，其中 2 位是中繼角色）。
"""

from __future__ import annotations

import pytest

from cpbl.models import pitcher_decisions as pd

REAL_2026_A_341_FLAGS = [
    ("0000006555", False), ("0000005788", True),                     # 客：梅賽鍶、林凱威
    ("0000002345", False), ("0000001232", True), ("0000006176", True),  # 主：鄭浩均、江忠城、余謙
    ("0000000778", False), ("0000003639", False),                     # 主：蔡齊哲、呂彥青
]


def test_official_blown_marks_every_flagged_pitcher_bs() -> None:
    assert pd.official_blown(REAL_2026_A_341_FLAGS) == {
        "0000005788": "BS", "0000001232": "BS", "0000006176": "BS"}


def test_official_blown_ignores_false_and_unknown() -> None:
    assert pd.official_blown([("p1", False), ("p2", None)]) == {}


def test_game_with_flags_uses_official_and_never_infers(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_a, **_k):
        raise AssertionError("有官方旗標的場次不得再推算")

    monkeypatch.setattr(pd, "blown", boom)
    assert pd.blown_for_game(REAL_2026_A_341_FLAGS, [{"x": 1}], [{"y": 1}]) == {
        "0000005788": "BS", "0000001232": "BS", "0000006176": "BS"}


def test_all_zero_flags_still_count_as_official(monkeypatch: pytest.MonkeyPatch) -> None:
    """整場都是 0＝官方判定本場無人救援失敗，不是「沒有官方資料」——不得退回推算。"""
    monkeypatch.setattr(pd, "blown", lambda *_a, **_k: {"p9": "BH"})
    assert pd.blown_for_game([("p1", False), ("p2", False)], [], []) == {}


def test_game_without_flags_falls_back_to_inference(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pd, "blown", lambda livelog, pitching: {"p9": "BH"})
    assert pd.blown_for_game([], [{"x": 1}], []) == {"p9": "BH"}


@pytest.mark.parametrize("base,tag,expected", [
    ("W", "BS", "W·BS"),     # 搞砸領先、球隊再超前拿勝投——舊版會把勝投整個蓋掉
    ("L", "BS", "L·BS"),
    ("SV", "BS", "BS"),
    ("HLD", "BS", "BS"),
    (None, "BS", "BS"),
    ("W", "BH", "W·BH"),     # 推算路徑（無官方旗標的場次）同一規則
])
def test_merge_keeps_win_and_loss_alongside_a_blown_save(base, tag, expected) -> None:
    dec = {"other": "SV"} | ({"p1": base} if base else {})
    merged = pd.merge_blown(dec, {"p1": tag})
    assert merged["p1"] == expected
    assert merged["other"] == "SV"          # 未涉及的投手不動
