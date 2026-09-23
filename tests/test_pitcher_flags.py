"""逐場逐投手官方旗標（migration 073，2026-09-23）的離線測試（無 DB 依賴）。

樣本取自**真實** payload：stats.cpbl `/api/proxy/v1/games/2026-A-341`（2026-09-23 抓取）的
`Pitchers[]`，只留本功能用到的欄位。這場官方給 3 位救援失敗，其中 2 位 RoleType=中繼——
正是推算（只記最後一任）與官方判定分歧的形狀。
"""

from __future__ import annotations

import pytest

from cpbl.ingest import cpbl_pitch_tracking as pt

REAL_2026_A_341 = {
    "LiveLog": [],
    "Visiting": {"Pitchers": [
        {"PitcherAcnt": "0000006555", "PitcherName": "梅賽鍶", "RoleType": "先發",
         "IsSaveOK": "0", "IsSaveFail": "0", "ReliefPointCnt": 0},
        {"PitcherAcnt": "0000005788", "PitcherName": "林凱威", "RoleType": "最後一任",
         "IsSaveOK": "0", "IsSaveFail": "1", "ReliefPointCnt": 0},
    ]},
    "Home": {"Pitchers": [
        {"PitcherAcnt": "0000002345", "PitcherName": "鄭浩均", "RoleType": "先發",
         "IsSaveOK": "0", "IsSaveFail": "0", "ReliefPointCnt": 0},
        {"PitcherAcnt": "0000001232", "PitcherName": "江忠城", "RoleType": "中繼",
         "IsSaveOK": "0", "IsSaveFail": "1", "ReliefPointCnt": 0},
        {"PitcherAcnt": "0000006176", "PitcherName": "余謙", "RoleType": "中繼",
         "IsSaveOK": "0", "IsSaveFail": "1", "ReliefPointCnt": 0},
        {"PitcherAcnt": "0000000778", "PitcherName": "蔡齊哲", "RoleType": "中繼",
         "IsSaveOK": "0", "IsSaveFail": "0", "ReliefPointCnt": 0},
        {"PitcherAcnt": "0000003639", "PitcherName": "呂彥青", "RoleType": "最後一任",
         "IsSaveOK": "0", "IsSaveFail": "0", "ReliefPointCnt": 0},
    ]},
}


def _by_acnt(rows: list[tuple]) -> dict[str, tuple]:
    return {r[3]: r for r in rows}


def test_parses_every_pitcher_of_both_sides() -> None:
    rows = pt.parse_pitcher_flags(REAL_2026_A_341, 2026, "A", 341)

    assert len(rows) == 7
    assert {r[:3] for r in rows} == {(2026, "A", 341)}


def test_string_zero_is_false_not_truthy() -> None:
    """⚠️ 官方旗標是字串：以 truthy 判斷會把 '0' 當成真，每位後援都變成同時成功又失敗。"""
    rows = _by_acnt(pt.parse_pitcher_flags(REAL_2026_A_341, 2026, "A", 341))

    fails = {acnt for acnt, r in rows.items() if r[5] is True}
    assert fails == {"0000005788", "0000001232", "0000006176"}   # 林凱威、江忠城、余謙
    assert all(r[4] is False for r in rows.values())             # 本場無救援成功
    assert rows["0000006555"][5] is False                        # 先發：'0' → False


def test_blown_save_can_belong_to_a_middle_reliever() -> None:
    """官方判定的救援失敗含「中繼」角色——推算規則只記最後一任，這正是要收官方值的理由。"""
    rows = _by_acnt(pt.parse_pitcher_flags(REAL_2026_A_341, 2026, "A", 341))

    assert rows["0000001232"][6] == "中繼" and rows["0000001232"][5] is True


@pytest.mark.parametrize("raw", ["Y", "", None, True, False, "2"])
def test_unknown_flag_values_are_none_not_guessed(raw) -> None:
    game = {"Home": {"Pitchers": [{"PitcherAcnt": "p1", "IsSaveOK": raw, "IsSaveFail": raw}]}}
    (row,) = pt.parse_pitcher_flags(game, 2026, "A", 1)
    assert row[4] is None and row[5] is None


def test_row_without_pitcher_acnt_is_skipped() -> None:
    game = {"Home": {"Pitchers": [{"PitcherName": "無 acnt", "IsSaveOK": "1"}]}}
    assert pt.parse_pitcher_flags(game, 2026, "A", 1) == []


def test_game_path_collects_flags_from_the_same_request(monkeypatch: pytest.MonkeyPatch) -> None:
    """同一個單場請求同時寫逐球與旗標：不多打 API。"""
    requests: list[tuple] = []
    captured: list[tuple] = []

    def fake_fetch(client, year, kind, sno):
        requests.append((year, kind, sno))
        return REAL_2026_A_341

    def fake_upsert_flags(rows):
        captured.extend(rows)
        return len(rows)

    monkeypatch.setattr(pt, "_fetch_game", fake_fetch)
    monkeypatch.setattr(pt, "_upsert_pitcher_flags", fake_upsert_flags)
    monkeypatch.setattr(pt.time, "sleep", lambda s: None)

    out = pt.scrape_game_pitches([(2026, "A", 341)], delay=0)

    assert requests == [(2026, "A", 341)]
    assert out["pitcher_flags"] == 7 and len(captured) == 7


def test_empty_pitchers_do_not_open_a_db_connection(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom():
        raise AssertionError("沒有旗標列時不得開 DB 連線")

    monkeypatch.setattr(pt, "conn", boom)
    assert pt._upsert_pitcher_flags([]) == 0
