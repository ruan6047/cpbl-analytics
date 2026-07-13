from __future__ import annotations

from cpbl.api.routers.players import _coach_linkage_ambiguous


def test_guard_blocks_real_name_collision():
    # 同名且該名字確實有教練/總教練紀錄：觸發守門
    assert _coach_linkage_ambiguous(name_match_count=2, has_coach_records=True) is True


def test_guard_not_triggered_for_non_coach_name_collision():
    # 同名但從未在 coaches/managers 出現：不應誤掛警示（D2）
    assert _coach_linkage_ambiguous(name_match_count=8, has_coach_records=False) is False


def test_guard_not_triggered_for_unique_name():
    assert _coach_linkage_ambiguous(name_match_count=1, has_coach_records=True) is False
