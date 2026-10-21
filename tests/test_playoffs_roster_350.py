"""#350：名單 API 唯讀擴充——野手守位、主守位、DH 先發、打擊 line 補 tb／hbp／sf。

純組裝以構造輸入測；DH 先發 SQL 的語意（首個有守位碼事件、PH／缺守位 ⇒ unknown、場次限定）
以 VALUES 取代實表、在唯讀交易內跑真 SQL（無 DB ⇒ skip；⛔ 寫入任何表）。
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from cpbl.playoffs import roster_reader as rr
from cpbl.playoffs.roster_reader import RosterInputs, compute_roster

NOW = datetime(2026, 10, 21, 2, 0, tzinfo=UTC)
AWAY, HOME = "AAA011", "ACN011"
BAT, PIT = "0000007079", "0000000002"


def _ctx(games=()):
    return {"context_version": "ctx", "as_of": {},
            "series": {"C": {"series_id": {"year": 2026, "kind_code": "C", "teams": [AWAY, HOME]}}},
            "games": list(games)}


def _game(sno, no, completed=True):
    return {"game_key": {"year": 2026, "kind_code": "C", "game_sno": sno}, "series_game_no": no,
            "completed": completed, "away_team_code": AWAY, "home_team_code": HOME}


def _roster():
    return {"roster_id": "r1", "published_date": "2026-10-16", "source_url": None, "annotation_version": 1,
            "members": [{"player_id": BAT, "announced_name": "劉俊緯", "official_position": "內野手",
                         "tactical_role": None},
                        {"player_id": PIT, "announced_name": "投手02", "official_position": "投手",
                         "tactical_role": None}]}


def _inputs(games=(), **kw) -> RosterInputs:
    return RosterInputs(year=2026, series="C", context=_ctx(games), rosters={AWAY: _roster(), HOME: None},
                        team_names={AWAY: "味全"}, **kw)


def _m(out, pid):
    return next(m for t in out["teams"] for m in t["members"] if m["player_id"] == pid)


# —— 主守位 ——————————————————————————————————————————————————————————————


def test_positions_sorted_by_games_and_primary_tie_breaks_by_field_order():
    rows = [{"pos": "三壘手", "g": 4}, {"pos": "二壘手", "g": 2}, {"pos": "一壘手", "g": 4}, {"pos": "捕手", "g": 0}]
    positions, primary = rr.positions_of(rows)
    assert positions == [{"pos": "一壘手", "g": 4}, {"pos": "三壘手", "g": 4}, {"pos": "二壘手", "g": 2}]
    assert primary == "一壘手"                       # 同分依 捕手→一壘→…→右外，0G 不列
    assert rr.positions_of([]) == ([], None)          # 無一軍守備紀錄 ⇒ ⛔ 猜守位


def test_background_carries_fielder_fields_and_pitcher_does_not():
    i = _inputs(positions={BAT: [{"pos": "三壘手", "g": 11}, {"pos": "游擊手", "g": 35}]},
                dh={BAT: {"dh": 4, "unknown": 0}})
    out = compute_roster(i, now=NOW)
    b = _m(out, BAT)["background"]
    assert b["primary_position"] == "游擊手" and [p["pos"] for p in b["positions"]] == ["游擊手", "三壘手"]
    assert (b["dh_starts"], b["dh_starts_unknown"]) == (4, 0)
    p = _m(out, PIT)["background"]
    assert not {"positions", "primary_position", "dh_starts", "dh_starts_unknown"} & p.keys()


@pytest.mark.parametrize("dh", [3, 4, 5])
def test_background_dh_starts_passes_raw_count_around_threshold(dh):
    """門檻（例行賽 ≥4）只住前端常數；後端原樣給場數，3／4／5 都不截斷。"""
    out = compute_roster(_inputs(dh={BAT: {"dh": dh, "unknown": 1}}), now=NOW)
    b = _m(out, BAT)["background"]
    assert (b["dh_starts"], b["dh_starts_unknown"]) == (dh, 1)


# —— 本系列 DH ————————————————————————————————————————————————————————————


def test_series_without_completed_games_is_null():
    out = compute_roster(_inputs([_game(1, 1, completed=False)]), now=NOW)
    assert _m(out, BAT)["series"] is None


@pytest.mark.parametrize("dh", [0, 1])
def test_series_dh_starts_around_threshold(dh):
    full = {"away": {"batting", "pitching"}, "home": {"batting", "pitching"}}
    i = _inputs([_game(1, 1)], series_counts={}, series_box={1: full},
                series_dh={BAT: {"dh": dh, "unknown": 0}} if dh else {})
    s = _m(compute_roster(i, now=NOW), BAT)["series"]
    assert (s["dh_starts"], s["dh_starts_unknown"]) == (dh, 0)
    assert "dh_starts" not in _m(compute_roster(i, now=NOW), PIT)["series"]


def test_series_batting_source_pending_makes_dh_unknown_not_zero():
    i = _inputs([_game(1, 1)], series_counts={}, series_box={1: {"away": {"pitching"}, "home": {"pitching"}}},
                series_dh={})
    s = _m(compute_roster(i, now=NOW), BAT)["series"]
    assert s["pending"] is True and s["dh_starts"] is None       # ⛔ 當成 0


# —— line 補欄 ——————————————————————————————————————————————————————————————


def test_batting_line_new_counts_recompute_existing_rates():
    c = {"pa": 210, "ab": 180, "h": 54, "bb": 20, "hbp": 4, "sf": 3, "tb": 83, "hr": 6}
    line = rr.batting_line(c)
    assert (line["tb"], line["hbp"], line["sf"]) == (83, 4, 3)
    obp = (line["h"] + line["bb"] + line["hbp"]) / (line["ab"] + line["bb"] + line["hbp"] + line["sf"])
    assert round(obp, 3) == line["obp"] and round(line["tb"] / line["ab"], 3) == line["slg"]


def test_existing_line_keys_and_values_unchanged():
    """契約只加不改：既有鍵與值不變。"""
    c = {"pa": 4, "ab": 3, "h": 1, "bb": 1, "hbp": 0, "sf": 0, "tb": 4, "hr": 1}
    old = {"pa": 4, "ab": 3, "h": 1, "hr": 1, "bb": 1, "avg": 0.333, "obp": 0.5, "slg": 1.333, "ops": 1.833}
    line = rr.batting_line(c)
    assert {k: line[k] for k in old} == old and set(line) - set(old) == {"tb", "hbp", "sf"}


# —— DH 先發 SQL 語意（唯讀，VALUES 取代實表） ——————————————————————————————————


_BOX = ("(VALUES (2026, 'A', 1, 'P1', '先發'), (2026, 'A', 2, 'P1', '先發'), (2026, 'A', 3, 'P1', '先發'),"
        " (2026, 'A', 4, 'P1', '先發'), (2026, 'A', 5, 'P1', '替補'), (2026, 'A', 6, 'P1', '先發'), (2026, 'A', 7, 'P1', '先發'),"
        " (2026, 'C', 9, 'P1', '先發')) AS b(year, kind_code, game_sno, hitter_acnt, role_type)")
# 場 1：先有空守位碼事件、再 DH ⇒ DH；場 2：首事件 3B、後來 DH ⇒ 非 DH；場 3：首事件 PH ⇒ unknown；
# 場 4：先發但無任何守位碼 ⇒ unknown；場 5：替補 DH 不算先發；場 6：同場兩個事件字串序 ⇒ 取較小者 DH；
# 場 7：DH 後換到右外 ⇒ DH；場 9（C）：只在本系列範圍計。
_LOG = ("(VALUES (2026, 'A', 1, '0110001000', NULL, 'P1'), (2026, 'A', 1, '0110002000', 'DH', 'P1'),"
        " (2026, 'A', 2, '0110001000', '3B', 'P1'), (2026, 'A', 2, '0510001000', 'DH', 'P1'),"
        " (2026, 'A', 3, '0110001000', 'PH', 'P1'), (2026, 'A', 4, '0110001000', '', 'P1'),"
        " (2026, 'A', 5, '0710001000', 'DH', 'P1'), (2026, 'A', 6, '0310001000', 'LF', 'P1'),"
        " (2026, 'A', 6, '0110003000', 'DH', 'P1'), (2026, 'A', 7, '0110001000', 'DH', 'P1'),"
        " (2026, 'A', 7, '0910001000', 'RF', 'P1'), (2026, 'C', 9, '0110001000', 'DH', 'P1'))"
        " AS l(year, kind_code, game_sno, main_event_no, defend_station_code, hitter_acnt)")


def _run_dh(monkeypatch, kind, snos):
    from cpbl.db import conn

    sql = rr.DH_STARTS_SQL.replace("cpbl.batting_gamelog b", _BOX).replace("cpbl.game_livelog l", _LOG)
    assert "cpbl." not in sql                      # 兩張實表都已換掉，下方只讀 VALUES
    monkeypatch.setattr(rr, "DH_STARTS_SQL", sql)
    try:
        with conn() as c, c.transaction():
            cur = c.cursor()
            cur.execute(rr.READ_ONLY_TXN)
            return rr.read_dh_starts(cur, 2026, kind, ["P1", "P2"], snos)
    except Exception as exc:  # noqa: BLE001 — 無 DB 時跳過（CI 無 Postgres）
        pytest.skip(f"需本機 DB：{exc}")


def test_dh_sql_first_coded_event_rules_on_real_postgres(monkeypatch):
    assert _run_dh(monkeypatch, "A", None) == {"P1": {"dh": 3, "unknown": 2}}   # 場 1、6、7 為 DH；場 3、4 unknown


def test_dh_sql_series_scope_limited_to_given_snos(monkeypatch):
    assert _run_dh(monkeypatch, "C", [9]) == {"P1": {"dh": 1, "unknown": 0}}
    assert _run_dh(monkeypatch, "C", [8]) == {}                     # 無先發 ⇒ 不在結果（呼叫端視為 0）
