"""#268 WP1：coverage 純函式與 ``postseason-series-contract/v1`` 唯讀契約。

腳本化 cursor 餵合成列（不連 DB）；SQL 語意另由 ``test_postseason_contract_isolated.py`` 在
自有隔離 Postgres 驗證。場次形狀取自 #268 反例（E4 2:8、C1 兄弟@味全），非正式資料。
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from cpbl import postseason_contract as contract
from cpbl.change_signals import signal_games
from cpbl.completion import completed_games_sql_with_evidence
from cpbl.coverage import (
    REASON_LIVE_FINAL,
    REASON_LIVE_UNOBSERVED,
    REASON_OFFICIAL_CHANGE,
    REASON_OFFICIAL_FINAL,
    REASON_PAST_NO_RESULT,
    REASON_STATUS_UNKNOWN,
    coverage_verdict,
    taipei_date,
)

# --- coverage 純函式 -----------------------------------------------------------------

_E4 = {"year": 2026, "kind_code": "E", "game_sno": 4, "game_date": "2026-10-12"}


def test_taipei_date_crosses_midnight_before_utc():
    assert taipei_date(datetime(2026, 10, 12, 16, 40, tzinfo=UTC)) == date(2026, 10, 13)
    assert taipei_date(datetime(2026, 10, 12, 15, 59, tzinfo=UTC)) == date(2026, 10, 12)
    # naive 視為 UTC，不吃執行環境時區。
    assert taipei_date(datetime(2026, 10, 12, 16, 40)) == date(2026, 10, 13)


@pytest.mark.parametrize(("status", "verdict", "reason"), [
    ("final", "pending_update", REASON_OFFICIAL_FINAL),
    ("scheduled", "pending_update", REASON_PAST_NO_RESULT),
    ("unknown", "unknown", REASON_STATUS_UNKNOWN),
    ("postponed", "covered", None),
    ("reserved", "covered", None),
])
def test_past_uncompleted_game_is_classified_by_official_status(status, verdict, reason):
    got = coverage_verdict([_E4], {(2026, "E", 4): status}, taipei_day=date(2026, 10, 13))
    assert got["status"] == verdict
    assert [g.get("reason") for g in got["pending_games"]] == ([reason] if reason else [])


def test_same_taipei_day_is_not_lagging_without_a_live_final_signal():
    """台北當天還沒過：可能仍在比賽，不能說落後。"""
    got = coverage_verdict([_E4], {(2026, "E", 4): "scheduled"}, taipei_day=date(2026, 10, 12))
    assert got["status"] == "covered"


def test_live_final_is_only_a_pending_signal():
    got = coverage_verdict([], {}, taipei_day=date(2026, 10, 12), live_final_uncompleted=[
        {"season": 2026, "kind_code": "E", "game_sno": 4, "game_date": "2026-10-12"}])
    assert got["status"] == "pending_update"
    assert got["pending_games"][0]["reason"] == REASON_LIVE_FINAL


def test_today_unobserved_is_unknown_and_pending_still_dominates():
    """今天無觀測訊號 → unknown；同時有確定待更新者 → pending_update；同一場只列一次。"""
    today = {"season": 2026, "kind_code": "E", "game_sno": 4, "game_date": "2026-10-12"}
    got = coverage_verdict([], {}, taipei_day=date(2026, 10, 12), today_unobserved=[today])
    assert got["status"] == "unknown"
    assert [(g["game_sno"], g["reason"]) for g in got["pending_games"]] == [(4, REASON_LIVE_UNOBSERVED)]

    past = {**_E4, "game_sno": 3, "game_date": "2026-10-11"}
    got = coverage_verdict([past], {(2026, "E", 3): "final"}, taipei_day=date(2026, 10, 12),
                           live_final_uncompleted=[today], today_unobserved=[today])
    assert got["status"] == "pending_update"
    assert [(g["game_sno"], g["reason"]) for g in got["pending_games"]] == [
        (3, REASON_OFFICIAL_FINAL), (4, REASON_LIVE_FINAL)]


def test_official_change_signal_is_pending_and_outranks_unobserved():
    """#268 D1：異動訊號＝確定待更新；同一場也無即時觀測時以待更新為準、只列一次；日期未知不猜。"""
    c1 = {"year": 2026, "kind_code": "C", "game_sno": 1, "game_date": "2026-10-17"}
    got = coverage_verdict([], {}, taipei_day=date(2026, 10, 17), change_signals=[c1],
                           today_unobserved=[c1])
    assert got["status"] == "pending_update"
    assert [(g["game_sno"], g["reason"]) for g in got["pending_games"]] == [(1, REASON_OFFICIAL_CHANGE)]

    undated = {**c1, "game_sno": 7, "game_date": None}
    got = coverage_verdict([_E4], {(2026, "E", 4): "final"}, taipei_day=date(2026, 10, 13),
                           change_signals=[undated])
    assert [(g["game_sno"], g["game_date"]) for g in got["pending_games"]] == [(7, None), (4, "2026-10-12")]


def test_signal_games_prefers_the_official_new_date_and_never_guesses():
    rows = [
        {"year": 2026, "kind_code": "C", "game_sno": 2, "field": "venue", "official_value": "大巨蛋",
         "local_game_date": date(2026, 10, 18)},
        {"year": 2026, "kind_code": "C", "game_sno": 2, "field": "date", "official_value": "2026-10-19",
         "local_game_date": date(2026, 10, 18)},
        {"year": 2026, "kind_code": "C", "game_sno": 3, "field": "teams", "official_value": "AAA011@ACN011",
         "local_game_date": date(2026, 10, 20)},
        {"year": 2026, "kind_code": "C", "game_sno": 5, "field": "game", "official_value": None,
         "local_game_date": None},
    ]
    assert signal_games(rows) == [
        {"year": 2026, "kind_code": "C", "game_sno": 2, "game_date": "2026-10-19"},
        {"year": 2026, "kind_code": "C", "game_sno": 3, "game_date": "2026-10-20"},
        {"year": 2026, "kind_code": "C", "game_sno": 5, "game_date": None},
    ]


def test_failed_status_lookup_never_claims_covered():
    got = coverage_verdict([_E4], None, taipei_day=date(2026, 10, 13))
    assert got["status"] == "unknown"


def test_pending_dominates_unknown_and_has_no_clock_cutoff():
    """沒有任何鐘點截止：跨日多久都照判（02:10 與 23:45 同一規則）。"""
    other = {**_E4, "game_sno": 3, "game_date": "2026-10-11"}
    got = coverage_verdict([_E4, other], {(2026, "E", 4): "final"}, taipei_day=date(2026, 10, 13))
    assert got["status"] == "pending_update"
    assert [g["game_sno"] for g in got["pending_games"]] == [3, 4]


# --- 契約 v1（腳本化 cursor） ----------------------------------------------------------

class _Cursor:
    def __init__(self, script: list):
        self._script = list(script)
        self.description = None
        self._rows: list[tuple] = []
        self.queries: list[tuple[str, object]] = []

    def execute(self, sql, params=None):
        self.queries.append((" ".join(str(sql).split()), params))
        cols, rows = self._script.pop(0)
        if isinstance(rows, Exception):
            raise rows
        self.description = [(name,) for name in cols]
        self._rows = rows

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return self._rows


_GAME_COLS = ["year", "kind_code", "game_sno", "game_date", "venue", "away_team_code",
              "home_team_code", "away_score", "home_score", "completed"]
_REV_COLS = ["year", "kind_code", "game_sno", "raw_present_status", "raw_game_result",
             "raw_game_date", "payload_hash", "fetched_at", "last_seen_at"]
_SEEN = datetime(2026, 10, 12, 14, 0, tzinfo=UTC)
_NOW = datetime(2026, 10, 13, 2, 30, tzinfo=UTC)   # 台北 10/13 10:30


def _rev(kind, sno, present, result, day):
    return (2026, kind, sno, present, result, day, f"{kind}{sno}{result}", _SEEN, _SEEN)


_SIGNAL_COLS = ["year", "kind_code", "game_sno", "field", "official_value", "detected_at",
                "local_game_date"]


def _state(games, revisions, refresh=None, now=_NOW, signals=()):
    cur = _Cursor([
        (_GAME_COLS, games),
        (["refreshed_at", "ok", "scope"],
         refresh if refresh is not None else [(datetime(2026, 10, 13, 2, 12, tzinfo=UTC), True, "recent-games")]),
        (_REV_COLS, revisions),
        (_SIGNAL_COLS, signals),
    ])
    return contract.series_state_from_cursor(cur, 2026, now=now), cur


def test_contract_reports_real_c1_and_canonical_completed_keys():
    state, cur = _state(
        games=[(2026, "E", 4, date(2026, 10, 12), "洲際", "ADD011", "ACN011", 2, 8, True),
               (2026, "C", 1, date(2026, 10, 17), "大巨蛋", "ACN011", "AAA011", 0, 0, False)],
        revisions=[_rev("E", 4, 1, "0", date(2026, 10, 12)), _rev("C", 1, 1, "", date(2026, 10, 17))],
    )

    assert state["contract"] == "postseason-series-contract/v1"
    assert state["completed_keys"] == [[2026, "E", 4]]
    c1 = next(g for g in state["games"] if g["kind_code"] == "C")
    assert (c1["game_sno"], c1["away_team_code"], c1["home_team_code"]) == (1, "ACN011", "AAA011")
    assert c1["completed"] is False and c1["away_score"] is None and c1["home_score"] is None
    assert c1["official_status"] == "scheduled"
    assert state["as_of"]["coverage"] == "covered"
    assert state["as_of"]["last_completed_game_date"] == "2026-10-12"
    assert state["as_of"]["taipei_date"] == "2026-10-13"
    assert state["as_of"]["last_refresh_ok"] is True
    # 完賽判準與 postseason-summary／readers 同一支 helper，as_of 由參數注入台北日。
    assert completed_games_sql_with_evidence("g", "%(as_of)s") in contract.GAMES_SQL
    assert cur.queries[0][1] == {"year": 2026, "as_of": date(2026, 10, 13)}
    # 唯讀：四支（第四支是 #268 D1 官方異動訊號）全是 SELECT。
    assert len(cur.queries) == 4
    assert all(q.upper().startswith("SELECT") for q, _ in cur.queries)
    assert cur.queries[3][1] == {"kinds": ["E", "C"], "season": 2026}


def test_contract_marks_missing_e4_as_pending_and_never_scores_it():
    state, _ = _state(
        games=[(2026, "E", 3, date(2026, 10, 11), "洲際", "ADD011", "ACN011", 1, 5, True),
               (2026, "E", 4, date(2026, 10, 12), "洲際", "ADD011", "ACN011", 2, 8, False)],
        revisions=[_rev("E", 4, 1, "", date(2026, 10, 12))],
    )

    e4 = next(g for g in state["games"] if g["game_sno"] == 4)
    assert e4["completed"] is False and e4["home_score"] is None, "賽中／未定案比分不得送出"
    assert state["as_of"]["coverage"] == "pending_update"
    assert state["as_of"]["pending_games"][0]["game_sno"] == 4
    assert state["completed_keys"] == [[2026, "E", 3]]


def test_contract_without_c_rows_does_not_invent_any():
    state, _ = _state(
        games=[(2026, "E", 4, date(2026, 10, 12), "洲際", "ADD011", "ACN011", 2, 8, True)],
        revisions=[_rev("E", 4, 1, "0", date(2026, 10, 12))],
    )
    assert [g["kind_code"] for g in state["games"]] == ["E"]


def test_contract_degrades_to_unknown_when_side_sources_fail():
    state, _ = _state(
        games=[(2026, "E", 4, date(2026, 10, 12), "洲際", "ADD011", "ACN011", 2, 8, False)],
        revisions=RuntimeError("permission denied"),
        refresh=RuntimeError("relation cpbl.refresh_log does not exist"),
    )
    assert state["as_of"]["last_refresh_at"] is None and state["as_of"]["last_refresh_ok"] is None
    assert state["games"][0]["official_status"] == "unknown"
    assert state["as_of"]["coverage"] == "unknown"


def test_contract_reports_official_change_signals_but_never_invents_games():
    """#268 D1：官方已公布 C1、本站尚未入庫（訊號）→ coverage pending_update；games／completed_keys
    仍只出自 cpbl.games（不從訊號造 C1 列、不推場號）。訊號表讀不到 → 只少這個訊號。"""
    e4 = (2026, "E", 4, date(2026, 10, 12), "洲際", "ADD011", "ACN011", 2, 8, True)
    signal = (2026, "C", 1, "game", "2026-10-17T17:05:00", _SEEN, None)
    state, _ = _state(games=[e4], revisions=[_rev("E", 4, 1, "0", date(2026, 10, 12))], signals=[signal])

    assert [g["kind_code"] for g in state["games"]] == ["E"]
    assert state["completed_keys"] == [[2026, "E", 4]]
    assert state["as_of"]["coverage"] == "pending_update"
    assert state["as_of"]["pending_games"] == [
        {"year": 2026, "kind_code": "C", "game_sno": 1, "game_date": "2026-10-17",
         "official_status": "unknown", "reason": REASON_OFFICIAL_CHANGE}]

    failed, _ = _state(games=[e4], revisions=[_rev("E", 4, 1, "0", date(2026, 10, 12))],
                       signals=RuntimeError("relation cpbl.official_change_signals does not exist"))
    assert failed["as_of"]["coverage"] == "covered"


def test_contract_has_no_write_or_endpoint_surface():
    """契約只是函式：不得在 API 新增路由（路由快照另由 test_route_snapshot 釘住）。"""
    from cpbl.api.main import app

    assert not [r for r in app.routes if "series-contract" in getattr(r, "path", "")]
    for sql in (contract.GAMES_SQL, contract.REVISIONS_SQL, contract.REFRESH_SQL,
                contract.CHANGE_SIGNALS_SQL):
        assert not any(w in sql.upper() for w in ("INSERT", "UPDATE", "DELETE", "CREATE", "DROP"))
