"""首頁每日入口聚合契約（API-DAILY-SUMMARY1）。

邊界情境（休兵日、延賽、刷新落後、pending、unknown、source_error）以腳本化 cursor
餵假列驗證，不寫 DB（本卡 db_scope=read）；另有一組整合測試打本機真實 DB。
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from cpbl.api.main import app
from cpbl.api.routers import daily
from cpbl.api.routers.daily import refresh_status

_GAME_COLS = ["season", "kind_code", "game_sno", "game_date", "venue",
              "away_team_code", "away_team_name", "away_score",
              "home_team_code", "home_team_name", "home_score",
              "has_score", "delay_kind", "orig_date"]
_TODAY = date.today()


def _game(sno: int, day: date, *, home: int | None = None, away: int | None = None,
          kind: str = "A", delay: str | None = None, orig: date | None = None) -> tuple:
    """一列 cpbl.games。home 給值＝DB 裡有比分（未必等於已完成，見保留賽測試）。"""
    return (2026, kind, sno, day, "洲際", "ADD011", "統一7-ELEVEn獅", away or 0,
            "ACN011", "中信兄弟", home or 0, home is not None, delay, orig)


class _Cursor:
    """腳本化 cursor：依 execute 出現順序回下一組 (description, rows)。

    refresh_log 那一輪允許以 Exception 代替 rows，模擬缺表 → source_error。
    """

    def __init__(self, script: list):
        self._script = list(script)
        self.description = None
        self._rows: list[tuple] = []
        self.queries: list[str] = []

    def execute(self, sql, params=None):
        self.queries.append(" ".join(str(sql).split()))
        cols, rows = self._script.pop(0)
        if isinstance(rows, Exception):
            raise rows
        self.description = [(name,) for name in cols]
        self._rows = rows

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return self._rows


class _Conn:
    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self):
        return self._cursor

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _run(monkeypatch, script, *, artifact=None, query="") -> tuple[dict, _Cursor]:
    cursor = _Cursor(script)
    monkeypatch.setattr(daily, "conn", lambda: _Conn(cursor))
    monkeypatch.setattr(daily, "_pregame_source",
                        lambda: artifact or (None, {"status": "artifact_missing",
                                                    "reason": "測試未載入 artifact",
                                                    "trained_through": None, "signals": None}))
    response = TestClient(app).get(f"/api/v1/daily/summary{query}")
    assert response.status_code == 200
    return response.json(), cursor


def _script(*, latest: date | None, next_day: date | None, scoped: int, games: list[tuple],
            unresolved: list[tuple] | None = None, refresh=("ok",)) -> list:
    refresh_rows: object
    if refresh == ("ok",):
        refresh_rows = [(datetime.now(UTC) - timedelta(hours=2), True, "recent-games")]
    else:
        refresh_rows = refresh
    return [
        (["latest", "next", "scoped"], [(latest, next_day, scoped)]),
        (_GAME_COLS, games),
        (_GAME_COLS, unresolved or []),
        (["refreshed_at", "ok", "scope"], refresh_rows),
    ]


# --- 純函式：refresh 狀態字彙 -------------------------------------------------

def test_refresh_status_without_any_log_is_unknown_not_fresh():
    """**紅線**：沒有刷新紀錄＝沒有證據，必須 fail closed 為 unknown，不得預設新鮮。"""
    assert refresh_status(None, None, datetime.now(UTC)) == ("unknown", None)


def test_refresh_status_marks_failed_run_even_when_recent():
    now = datetime.now(UTC)
    status, hours = refresh_status(now - timedelta(hours=1), False, now)
    assert status == "failed"
    assert hours == 1.0


def test_refresh_status_flips_to_stale_after_threshold():
    now = datetime.now(UTC)
    assert refresh_status(now - timedelta(hours=23), True, now)[0] == "fresh"
    assert refresh_status(now - timedelta(hours=25), True, now)[0] == "stale"


# --- 契約：語意紅線 -----------------------------------------------------------

def test_unplayed_games_never_report_zero_zero(monkeypatch):
    """**紅線**：未開打場次的比分必須是 null。DB 的 0–0 是佔位，不是賽果。"""
    body, _ = _run(monkeypatch, _script(
        latest=_TODAY - timedelta(days=1), next_day=_TODAY + timedelta(days=4), scoped=2,
        games=[_game(1, _TODAY - timedelta(days=1), home=2, away=1),
               _game(2, _TODAY + timedelta(days=4))],
    ))

    played = body["latest_game_day"]["games"][0]
    upcoming = body["next_slate"]["games"][0]
    assert (played["home_score"], played["away_score"], played["completed"]) == (2, 1, True)
    assert upcoming["home_score"] is None and upcoming["away_score"] is None
    assert upcoming["completed"] is False


def test_rest_day_keeps_latest_result_and_reports_distance(monkeypatch):
    """休兵日：不是「今天沒比賽」的空白，而是最近比賽日 + 幾天後的下一批。"""
    body, _ = _run(monkeypatch, _script(
        latest=_TODAY - timedelta(days=1), next_day=_TODAY + timedelta(days=4), scoped=2,
        games=[_game(1, _TODAY - timedelta(days=1), home=5, away=3),
               _game(2, _TODAY + timedelta(days=4))],
    ))

    assert body["latest_game_day"]["game_date"] == (_TODAY - timedelta(days=1)).isoformat()
    assert body["next_slate"]["days_from_as_of"] == 4
    assert body["availability"]["schedule"]["status"] == "available"
    assert body["availability"]["results"]["status"] == "available"


def test_postponed_game_moved_forward_is_a_scheduled_game_not_a_result(monkeypatch):
    """延賽：官網把場次改到新日期並保留 orig_date；它屬於下一批賽事，比分仍是 null。"""
    new_day = _TODAY + timedelta(days=7)
    body, _ = _run(monkeypatch, _script(
        latest=_TODAY - timedelta(days=2), next_day=new_day, scoped=2,
        games=[_game(1, _TODAY - timedelta(days=2), home=1, away=0),
               _game(2, new_day, delay="延賽", orig=_TODAY - timedelta(days=30))],
    ))

    game = body["next_slate"]["games"][0]
    assert game["delay_kind"] == "延賽"
    assert game["orig_date"] == (_TODAY - timedelta(days=30)).isoformat()
    assert game["home_score"] is None


def test_future_dated_game_with_a_score_is_never_the_latest_game_day(monkeypatch):
    """**紅線**：二軍保留賽在 cpbl.games 帶著比分卻排在未來的補賽時段（全史 4 筆，
    如 D#117 game_date=2026-08-30／orig_date=2026-06-14）。只看「比分 > 0」會讓
    最近比賽日跳到未來；日期不在未來才是可證明的判準。"""
    suspended = _TODAY + timedelta(days=44)
    body, _ = _run(monkeypatch, _script(
        latest=_TODAY - timedelta(days=1), next_day=suspended, scoped=2,
        games=[_game(1, _TODAY - timedelta(days=1), home=2, away=1),
               _game(2, suspended, home=1, away=4, kind="D", delay="保留",
                     orig=_TODAY - timedelta(days=33))],
    ))

    assert body["latest_game_day"]["game_date"] < body["scope"]["as_of"]
    held = body["next_slate"]["games"][0]
    assert held["completed"] is False
    assert held["home_score"] is None and held["away_score"] is None
    assert held["delay_kind"] == "保留"


def test_unresolved_past_game_is_flagged_unknown_not_silently_dropped(monkeypatch):
    """刷新落後／延賽未更新：過去日期仍 0–0 → 列為 unknown 的 fail-fast 訊號，
    且不得混進最近比賽日的賽果。"""
    stale_day = _TODAY - timedelta(days=3)
    body, _ = _run(monkeypatch, _script(
        latest=_TODAY - timedelta(days=1), next_day=_TODAY + timedelta(days=1), scoped=3,
        games=[_game(1, _TODAY - timedelta(days=1), home=4, away=2),
               _game(2, _TODAY + timedelta(days=1))],
        unresolved=[_game(3, stale_day, delay="延賽")],
    ))

    unresolved = body["freshness"]["unresolved_games"]
    assert len(unresolved) == 1
    assert unresolved[0]["status"] == "unknown"
    assert unresolved[0]["home_score"] is None
    assert [g["game_sno"] for g in body["latest_game_day"]["games"]] == [1]


def test_refresh_log_missing_table_degrades_to_source_error(monkeypatch):
    """refresh_log 尚未 migrate：freshness 顯示 source_error，賽事資料照常回傳。"""
    body, _ = _run(monkeypatch, _script(
        latest=_TODAY - timedelta(days=1), next_day=_TODAY + timedelta(days=1), scoped=2,
        games=[_game(1, _TODAY - timedelta(days=1), home=3, away=2),
               _game(2, _TODAY + timedelta(days=1))],
        refresh=RuntimeError("relation cpbl.refresh_log does not exist"),
    ))

    assert body["freshness"]["last_refresh"]["status"] == "source_error"
    assert body["freshness"]["last_refresh"]["at"] is None
    assert body["latest_game_day"]["games"]


def test_never_refreshed_is_unknown_and_does_not_claim_freshness(monkeypatch):
    body, _ = _run(monkeypatch, _script(
        latest=_TODAY - timedelta(days=1), next_day=None, scoped=1,
        games=[_game(1, _TODAY - timedelta(days=1), home=3, away=2)],
        refresh=[],
    ))

    assert body["freshness"]["last_refresh"]["status"] == "unknown"


# --- 契約：availability 正交 --------------------------------------------------

def test_availability_axes_are_independent(monkeypatch):
    """賽程／結果／賽前模型各自有 status 與 reason，不共用同一句文案。"""
    body, _ = _run(monkeypatch, _script(
        latest=_TODAY - timedelta(days=1), next_day=_TODAY + timedelta(days=1), scoped=2,
        games=[_game(1, _TODAY - timedelta(days=1), home=1, away=0),
               _game(2, _TODAY + timedelta(days=1))],
    ))

    availability = body["availability"]
    assert set(availability) == {"schedule", "results", "pregame_model"}
    assert availability["schedule"]["status"] == "available"
    assert availability["pregame_model"]["status"] == "artifact_missing"
    assert availability["pregame_model"]["reason"]


def test_season_complete_is_distinct_from_missing_schedule(monkeypatch):
    """有賽程但沒有未來場次＝球季結束，與「查不到賽程」必須是不同的 status。"""
    done, _ = _run(monkeypatch, _script(
        latest=_TODAY - timedelta(days=1), next_day=None, scoped=140,
        games=[_game(1, _TODAY - timedelta(days=1), home=1, away=0)],
    ))
    empty, _ = _run(monkeypatch, _script(latest=None, next_day=None, scoped=0, games=[]))

    assert done["availability"]["schedule"]["status"] == "season_complete"
    assert done["next_slate"] is None
    assert empty["availability"]["schedule"]["status"] == "source_missing"
    assert empty["availability"]["results"]["status"] == "source_missing"
    assert empty["latest_game_day"] is None


def test_preseason_reports_not_started_instead_of_empty(monkeypatch):
    body, _ = _run(monkeypatch, _script(
        latest=None, next_day=_TODAY + timedelta(days=2), scoped=120,
        games=[_game(1, _TODAY + timedelta(days=2))],
    ))

    assert body["availability"]["results"]["status"] == "not_started"
    assert body["latest_game_day"] is None
    assert body["next_slate"]["games"]


# --- 契約：賽前模型不阻塞賽程 -------------------------------------------------

def _fake_artifact(monkeypatch, rows):
    """假 artifact：model.predict 回固定機率；load_outcome_rows 回指定的 game_features 列。"""
    class _Model:
        def predict(self, rows):
            return [0.25 + 0.1 * index for index in range(len(rows))]

    monkeypatch.setattr(daily, "load_outcome_rows", lambda completed_only=True: rows)
    return {"trained_through": 2025, "signals": {"strength": "winrate_diff",
                                                 "suppression": "starter_era_diff"},
            "model": _Model()}


def test_pregame_matches_games_by_season_and_sno_only(monkeypatch):
    """**紅線**：game_features 只有一軍例行賽，(season, game_sno) 才是唯一鍵。
    同號的二軍場次不得吃到一軍的機率。"""
    OutcomeRow = pytest.importorskip("cpbl.models.outcome_simple").OutcomeRow
    rows = [OutcomeRow(season=2026, game_date=_TODAY, home_win=0,
                       features={"winrate_diff": 0.1, "starter_era_diff": -0.5},
                       game_sno=211, home="中信兄弟", away="統一7-ELEVEn獅")]
    artifact = _fake_artifact(monkeypatch, rows)

    result = daily._pregame_by_game(artifact, [
        {"season": 2026, "game_sno": 211, "kind_code": "A"},
        {"season": 2026, "game_sno": 211, "kind_code": "D"},  # 同號二軍場次
    ])

    assert set(result) == {(2026, 211)}
    assert result[(2026, 211)]["home_win_probability"] == 0.25


def test_pregame_signal_direction_follows_model_orientation(monkeypatch):
    """訊號方向由模型的 ORIENT 決定：ERA 差是越低越有利主隊，不可一律「高＝好」。"""
    OutcomeRow = pytest.importorskip("cpbl.models.outcome_simple").OutcomeRow
    rows = [OutcomeRow(season=2026, game_date=_TODAY, home_win=0,
                       features={"winrate_diff": 0.1, "starter_era_diff": -0.5},
                       game_sno=211, home="中信兄弟", away="統一7-ELEVEn獅")]
    artifact = _fake_artifact(monkeypatch, rows)

    signals = daily._pregame_by_game(
        artifact, [{"season": 2026, "game_sno": 211, "kind_code": "A"}])[(2026, 211)]["signals"]

    assert signals["strength"] == {"key": "winrate_diff", "raw": 0.1,
                                   "direction": "higher_favors_home"}
    assert signals["suppression"]["direction"] == "lower_favors_home"


def test_missing_artifact_still_returns_schedule_without_fake_probability(monkeypatch):
    """**紅線**：模型缺席時回賽程，pregame 為 artifact_missing，且不補 50% 假數字。"""
    body, _ = _run(monkeypatch, _script(
        latest=_TODAY - timedelta(days=1), next_day=_TODAY + timedelta(days=1), scoped=2,
        games=[_game(1, _TODAY - timedelta(days=1), home=1, away=0),
               _game(2, _TODAY + timedelta(days=1))],
    ))

    pregame = body["next_slate"]["games"][0]["pregame"]
    assert pregame["status"] == "artifact_missing"
    assert pregame["home_win_probability"] is None


def test_postseason_game_is_unsupported_by_the_regular_season_model(monkeypatch):
    """game_features 只有一軍例行賽；季後賽場次必須說 unsupported，不可外插。"""
    artifact = ({"trained_through": 2025, "signals": {"strength": "winrate_diff"}, "model": None},
                {"status": "available", "reason": None, "trained_through": 2025,
                 "signals": {"strength": "winrate_diff"}})
    monkeypatch.setattr(daily, "_pregame_by_game", lambda *_: {})
    body, _ = _run(monkeypatch, _script(
        latest=_TODAY - timedelta(days=1), next_day=_TODAY + timedelta(days=1), scoped=2,
        games=[_game(1, _TODAY - timedelta(days=1), home=1, away=0),
               _game(2, _TODAY + timedelta(days=1), kind="C")],
    ), artifact=artifact)

    assert body["next_slate"]["games"][0]["pregame"]["status"] == "unsupported"


def test_game_without_features_is_no_features_not_fifty_percent(monkeypatch):
    artifact = ({"trained_through": 2025, "signals": {"strength": "winrate_diff"}, "model": None},
                {"status": "available", "reason": None, "trained_through": 2025,
                 "signals": {"strength": "winrate_diff"}})
    monkeypatch.setattr(daily, "_pregame_by_game", lambda *_: {})
    body, _ = _run(monkeypatch, _script(
        latest=_TODAY - timedelta(days=1), next_day=_TODAY + timedelta(days=1), scoped=2,
        games=[_game(1, _TODAY - timedelta(days=1), home=1, away=0),
               _game(2, _TODAY + timedelta(days=1))],
    ), artifact=artifact)

    pregame = body["next_slate"]["games"][0]["pregame"]
    assert pregame["status"] == "no_features"
    assert pregame["home_win_probability"] is None


def test_home_payload_never_exposes_model_interval(monkeypatch):
    """§5.1：區間不進首頁（退到賽事頁／方法頁，且固定稱模型敏感度區間）。"""
    body, _ = _run(monkeypatch, _script(
        latest=_TODAY - timedelta(days=1), next_day=_TODAY + timedelta(days=1), scoped=2,
        games=[_game(1, _TODAY - timedelta(days=1), home=1, away=0),
               _game(2, _TODAY + timedelta(days=1))],
    ))

    assert "interval" not in repr(body)


# --- 契約：唯讀與查詢預算 -----------------------------------------------------

def test_summary_is_read_only_and_within_query_budget(monkeypatch):
    """§8.4：聚合取代十餘組請求；本端點固定 4 次唯讀查詢，且不得出現寫入。"""
    _, cursor = _run(monkeypatch, _script(
        latest=_TODAY - timedelta(days=1), next_day=_TODAY + timedelta(days=1), scoped=2,
        games=[_game(1, _TODAY - timedelta(days=1), home=1, away=0),
               _game(2, _TODAY + timedelta(days=1))],
    ))

    assert len(cursor.queries) == 4
    assert all(q.lstrip().upper().startswith(("SELECT", "WITH")) for q in cursor.queries)
    forbidden = ("INSERT", "UPDATE", "DELETE", "CREATE", "DROP", "ALTER")
    assert not any(word in q.upper() for q in cursor.queries for word in forbidden)


def test_scope_echoes_year_and_kind_range(monkeypatch):
    """年份與 kind 範圍必須明確：A 層級含季後 E／C。"""
    body, _ = _run(monkeypatch, _script(
        latest=_TODAY - timedelta(days=1), next_day=None, scoped=1,
        games=[_game(1, _TODAY - timedelta(days=1), home=1, away=0)],
    ), query="?season=2026&kind_code=A")

    assert body["scope"] == {"season": 2026, "kind_code": "A", "kinds": ["A", "E", "C"],
                             "as_of": _TODAY.isoformat()}


# --- 整合：本機真實 DB --------------------------------------------------------

def _live(query: str = "") -> dict:
    try:
        response = TestClient(app).get(f"/api/v1/daily/summary{query}")
    except Exception as exc:  # noqa: BLE001 — 無 DB 時跳過（CI 無 Postgres）
        pytest.skip(f"需本機 DB：{exc}")
    if response.status_code != 200:
        pytest.skip(f"需本機 DB（{response.status_code}）")
    return response.json()


@pytest.mark.parametrize("kind_code", ["A", "D"])
def test_live_latest_game_day_is_never_in_the_future(kind_code):
    """**紅線**（真實資料）：二軍保留賽帶比分卻排在未來，最近比賽日不得跳過去。"""
    body = _live(f"?kind_code={kind_code}")
    if body["latest_game_day"] is None:
        pytest.skip(f"本機 DB 的 {kind_code} 無已完成場次")

    assert body["latest_game_day"]["game_date"] <= body["scope"]["as_of"]
    if body["next_slate"] is not None:
        assert body["latest_game_day"]["game_date"] <= body["next_slate"]["game_date"]


def test_live_summary_matches_contract_shape():
    body = _live()

    assert set(body) == {"scope", "latest_game_day", "next_slate", "freshness", "availability"}
    assert set(body["availability"]) == {"schedule", "results", "pregame_model"}
    for day in (body["latest_game_day"], body["next_slate"]):
        if day is not None:
            assert day["games"], "有比賽日就必須有場次，不得回空陣列"


def test_live_latest_game_day_only_contains_finished_games():
    body = _live()
    if body["latest_game_day"] is None:
        pytest.skip("本機 DB 無已完成場次")

    for game in body["latest_game_day"]["games"]:
        assert game["completed"] is True
        assert game["home_score"] is not None and game["away_score"] is not None


def test_live_next_slate_is_not_in_the_past():
    body = _live()
    if body["next_slate"] is None:
        pytest.skip("本機 DB 無未來場次")

    assert body["next_slate"]["days_from_as_of"] >= 0
    assert body["next_slate"]["game_date"] >= body["scope"]["as_of"]
    for game in body["next_slate"]["games"]:
        assert game["completed"] is False
        assert game["pregame"]["status"] in {"available", "artifact_missing", "unsupported",
                                             "no_features", "error"}
