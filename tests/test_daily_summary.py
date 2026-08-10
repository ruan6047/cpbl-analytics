"""首頁每日入口聚合契約（API-DAILY-SUMMARY1）。

邊界情境（休兵日、延賽、刷新落後、pending、unknown、source_error）以腳本化 cursor
餵假列驗證，不寫 DB（本卡 db_scope=read）；另有一組整合測試打本機真實 DB。
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

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


def _snapshot(sno: int, phase: str, *, away: int = 0, home: int = 0, inning: int | None = None,
              half: str = "2", outs: int | None = None, bases: tuple[bool, bool, bool] = (),
              events: int = 0, fetched_at: datetime | None = None,
              freshness: str = "fresh", source_status: str = "ok",
              decisions: dict | None = None, starts_at: str | None = None) -> dict:
    """一份 canonical live snapshot（`live_cache.public_snapshot` 之後的公開形狀）。"""
    first, second, third = (bases or (False, False, False))
    log = [{"OutCnt": outs, "FirstBase": "王一" if first else None,
            "SecondBase": "李二" if second else None, "ThirdBase": "張三" if third else None}]
    return {
        "game_id": f"2026-A-{sno}", "game_sno": sno, "kind_code": "A",
        "phase": phase, "raw_status": phase.upper(),
        "starts_at": starts_at or f"2026-08-07T18:{35 if sno % 2 else 5:02d}:00+08:00",
        "inning": inning if inning is not None else 1,
        "half": half,
        "away": {"score": away}, "home": {"score": home},
        "livelog": log if events else [],
        "event_count": events,
        "freshness": freshness,
        "stale_after_seconds": 45 if phase == "live" else (None if phase == "final" else 1200),
        "source_status": source_status,
        "source": {"fetched_at": (fetched_at or datetime.now(UTC)).isoformat()},
        "decisions": decisions,
    }


def _run(monkeypatch, script, *, artifact=None, query="", snapshots=None,
         now=None, today_local=None) -> tuple[dict, _Cursor]:
    cursor = _Cursor(script)
    monkeypatch.setattr(daily, "conn", lambda: _Conn(cursor))
    # 時鐘與容器本地日可注入：本機跑在台北時區，不注入就永遠測不到「容器 UTC、
    # 台北凌晨」——而那正是唯一會出錯的情境。
    if now is not None:
        monkeypatch.setattr(daily, "_now", lambda: now)
    if today_local is not None:
        monkeypatch.setattr(daily, "_today_local", lambda: today_local)
    # 契約測試一律與本機 Redis 隔離：`snapshots=None`＝未設定 REDIS_URL（本機／CI 預設），
    # 要驗即時態就明著給一組假 snapshot。開發者本機恰好有 Redis 時測試不得跟著變。
    monkeypatch.setattr(daily.settings, "redis_url",
                        "redis://test/0" if snapshots is not None else None)
    monkeypatch.setattr(daily, "get_public_live_snapshot",
                        lambda season, kind, sno: (snapshots or {}).get(sno))
    monkeypatch.setattr(daily, "_pregame_source",
                        lambda: artifact or (None, {"status": "unavailable",
                                                    "reason": "測試未載入 artifact",
                                                    "fault": "artifact_missing",
                                                    "serving_version": None,
                                                    "backtest_version": None,
                                                    "backtest_deployable": None,
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


def test_latest_game_day_keeps_same_day_postponed_games_without_a_makeup_date(monkeypatch):
    """局部因雨延賽：同一天一場打完、兩場延賽而**補賽日尚未公布**。

    官網的流程是先宣告延賽、補賽日之後才公布；在那段空窗裡場次仍掛在原定日
    （`game_date == orig_date`，實測 2026-08-09 sno 254／255）。那一天於是既是最近比賽日
    （有一場賽果）又帶著兩場沒打的比賽——這是本卡 spec 當初只涵蓋「已改期」那一半所
    留下的缺口（改期後的延賽屬下一批賽事，見上一個測試）。

    **兩場必須留在 `latest_game_day`**（需求方 2026-08-10 裁定）：它們的日期不在 `as_of`
    之後，進不了 `next_slate`；而 `freshness.unresolved_games` 是維護者訊號、首頁不渲染。
    濾掉等於首頁宣稱那天只有一場比賽。比分仍為 null，狀態由呈現端依 `delay_kind` 標示。
    """
    day = _TODAY - timedelta(days=1)
    body, _ = _run(monkeypatch, _script(
        latest=day, next_day=_TODAY + timedelta(days=1), scoped=4,
        games=[_game(1, day, home=10, away=2),
               _game(2, day, delay="延賽", orig=day),
               _game(3, day, delay="延賽", orig=day),
               _game(4, _TODAY + timedelta(days=1))],
        unresolved=[_game(2, day, delay="延賽", orig=day),
                    _game(3, day, delay="延賽", orig=day)],
    ))

    games = body["latest_game_day"]["games"]
    assert [g["game_sno"] for g in games] == [1, 2, 3]
    assert [g["completed"] for g in games] == [True, False, False]
    for postponed in games[1:]:
        assert postponed["delay_kind"] == "延賽"
        assert postponed["home_score"] is None and postponed["away_score"] is None
    # 未改期的延賽也不得混進下一批賽事——那會讓它取得賽前機率欄位。
    assert [g["game_sno"] for g in body["next_slate"]["games"]] == [4]


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
    # 模型層級狀態用 serving 字彙（serving_current／serving_previous／unavailable）；
    # 逐場欄位另有自己的字彙，兩者刻意不共用（ML-OUTCOME-SIMPLE-LEAK2 紅線 5）。
    assert availability["pregame_model"]["status"] == "unavailable"
    assert availability["pregame_model"]["fault"] == "artifact_missing"
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


# --- 契約：今日賽事三態（UX-HOME-LIVE-STRIP1）---------------------------------
#
# 十種情境的後端側；呈現端的擇一渲染、兩階降級與輪詢節奏在
# `web/src/lib/daily-summary.test.ts`（同一份 payload 形狀）。


def _today_script(games: list[tuple], *, latest=None, next_day=None) -> list:
    """今天有場次的一組腳本；latest 預設昨天、next 預設今天。"""
    return _script(
        latest=latest if latest is not None else _TODAY - timedelta(days=1),
        next_day=next_day if next_day is not None else _TODAY,
        scoped=len(games) + 1,
        games=[_game(90, _TODAY - timedelta(days=1), home=4, away=2), *games],
    )


def test_rest_day_has_no_today_block_at_all(monkeypatch):
    """情境 1｜今天無場次：`today` 必須是 None，不得回空陣列。

    空陣列會被呈現端讀成「有今日賽事區塊、只是沒有比賽」＝驗收條件禁止的空容器。
    """
    body, _ = _run(monkeypatch, _script(
        latest=_TODAY - timedelta(days=1), next_day=_TODAY + timedelta(days=3), scoped=2,
        games=[_game(1, _TODAY - timedelta(days=1), home=2, away=1),
               _game(2, _TODAY + timedelta(days=3))],
    ), snapshots={})

    assert body["today"] is None


def test_today_before_lineup_is_not_started(monkeypatch):
    """情境 2｜賽前（未達 lineup）：`started` 為假，主位仍該留在上一個比賽日。"""
    body, _ = _run(monkeypatch, _today_script([_game(247, _TODAY), _game(248, _TODAY)]),
                   snapshots={247: _snapshot(247, "scheduled"),
                              248: _snapshot(248, "probable_announced")})

    assert body["today"]["started"] is False
    assert [g["live"]["phase"] for g in body["today"]["games"]] == \
        ["scheduled", "probable_announced"]


def test_single_lineup_announcement_flips_the_day_boundary(monkeypatch):
    """情境 3｜任一場 lineup_announced 觸發切換。**單邊打線公布即算**——worker 的
    `_phase` 已把「任一隊 lineup availability ≠ not_announced」判為 lineup_announced，
    這裡不再加第二套判準。"""
    body, _ = _run(monkeypatch, _today_script([_game(247, _TODAY), _game(248, _TODAY)]),
                   snapshots={247: _snapshot(247, "scheduled"),
                              248: _snapshot(248, "lineup_announced")})

    assert body["today"]["started"] is True


def test_live_game_exposes_only_the_facts_the_card_shows(monkeypatch):
    """情境 4｜單場 live：局數／比分／壘包／出局數／最後更新齊備，且**沒有任何 WP 欄位**、
    沒有逐球與球數。"""
    body, _ = _run(monkeypatch, _today_script([_game(247, _TODAY)]),
                   snapshots={247: _snapshot(247, "live", away=3, home=4, inning=5,
                                             half="2", outs=1, bases=(True, False, True),
                                             events=180)})

    live = body["today"]["games"][0]["live"]
    assert (live["inning"], live["half"], live["outs"]) == (5, "2", 1)
    assert live["bases"] == {"first": True, "second": False, "third": True}
    assert (live["away_score"], live["home_score"]) == (3, 4)
    assert live["fetched_at"] and live["freshness"] == "fresh"
    assert live["stale_after_seconds"] == 45
    assert live["interrupt"] == "none"
    # **紅線**：本卡不得引入任何 WP／WPA／leverage 欄位（場中 WP 修復是另一張卡）。
    for banned in ("wp", "wpa", "leverage", "win_prob", "ball_cnt", "strike_cnt", "livelog"):
        assert banned not in live, f"live view 不得帶 {banned}"


def test_three_concurrent_live_games_are_all_returned(monkeypatch):
    """情境 5｜三場 live：聯盟結構上限就是 3，全部回傳，不截斷、不摺疊。"""
    games = [_game(sno, _TODAY) for sno in (247, 248, 249)]
    body, _ = _run(monkeypatch, _today_script(games), snapshots={
        sno: _snapshot(sno, "live", away=1, home=2, inning=3, outs=0, events=60)
        for sno in (247, 248, 249)
    })

    assert [g["game_sno"] for g in body["today"]["games"]] == [247, 248, 249]
    assert body["today"]["live_source"] == {"status": "ok", "reason": None,
                                            "snapshots": 3, "games": 3}


def test_unstarted_game_placeholder_inning_is_never_reported(monkeypatch):
    """**紅線**：worker 對未開打場次仍回 `inning=1`，只判 truthy 會讓首頁顯示「▲ 1 局」。"""
    body, _ = _run(monkeypatch, _today_script([_game(247, _TODAY)]),
                   snapshots={247: _snapshot(247, "lineup_announced", inning=1, events=0)})

    live = body["today"]["games"][0]["live"]
    assert live["inning"] is None and live["half"] is None
    assert live["bases"] is None and live["outs"] is None


def test_final_game_carries_official_decisions_the_same_night(monkeypatch):
    """情境 9｜final 當晚：官方 MVP／勝投直接來自 snapshot `decisions`，不等隔日爬蟲。"""
    decisions = {"winning_pitcher": {"player_id": "AAA", "name": "投手甲"},
                 "losing_pitcher": None, "closer": None,
                 "mvp": {"player_id": "BBB", "name": "打者乙", "yearly_count": 3}}
    body, _ = _run(monkeypatch, _today_script([_game(247, _TODAY)]),
                   snapshots={247: _snapshot(247, "final", away=2, home=6, inning=9,
                                             events=300, freshness="final",
                                             decisions=decisions)})

    game = body["today"]["games"][0]
    assert body["today"]["started"] is True
    assert game["live"]["decisions"]["mvp"]["name"] == "打者乙"
    assert (game["live"]["away_score"], game["live"]["home_score"]) == (2, 6)
    # DB 仍是 0–0（隔日爬蟲才補），比分只能來自 snapshot——這正是 16 小時盲區的修法。
    assert game["completed"] is False and game["home_score"] is None


def test_started_games_lose_the_pregame_field_entirely(monkeypatch):
    """**紅線**（fail closed）：已開打場次連 `pregame` 欄位都不存在，呈現端沒有素材
    可以把賽前勝率畫回一場 5 局下的比賽旁邊。

    同時釘住日界線與「已開打」是**兩個**判準：`lineup_announced` 會把主區塊移到今天，
    但那一場仍是賽前態，賽前卡必須留著。"""
    artifact = ({"trained_through": 2025, "signals": {"strength": "winrate_diff"}, "model": None},
                {"status": "serving_current", "reason": None, "trained_through": 2025,
                 "signals": {"strength": "winrate_diff"}, "degradation": None})
    monkeypatch.setattr(daily, "_pregame_by_game", lambda *_: {})
    body, _ = _run(monkeypatch, _today_script([_game(247, _TODAY), _game(248, _TODAY),
                                              _game(249, _TODAY)]),
                   artifact=artifact,
                   snapshots={247: _snapshot(247, "live", inning=5, events=99),
                              248: _snapshot(248, "lineup_announced"),
                              249: _snapshot(249, "final", away=1, home=0, events=280)})

    underway, upcoming, done = body["today"]["games"]
    assert "pregame" not in underway
    assert "pregame" not in done
    assert upcoming["pregame"]["status"] == "no_features"
    assert body["today"]["started"] is True


def test_reserved_game_is_started_and_loses_its_pregame_probability(monkeypatch):
    """裁定 1｜保留賽＝**已開賽後中止**（GLOSSARY：官網 GameResult=2），與延賽不同。

    兩個後果：(a) 那是今天發生的事，日界線該切到今天；(b) 它已經開打，賽前機率必須跟
    live／final 一樣被收掉——一場 3:2 中止的比賽旁邊掛賽前勝率是同一個誤導的另一種樣子。
    """
    artifact = ({"trained_through": 2025, "signals": {"strength": "winrate_diff"}, "model": None},
                {"status": "serving_current", "reason": None, "trained_through": 2025,
                 "signals": {"strength": "winrate_diff"}, "degradation": None})
    monkeypatch.setattr(daily, "_pregame_by_game", lambda *_: {})
    body, _ = _run(monkeypatch, _today_script([_game(247, _TODAY), _game(248, _TODAY)]),
                   artifact=artifact,
                   snapshots={247: _snapshot(247, "reserved", away=3, home=2, inning=5,
                                             events=140),
                              248: _snapshot(248, "postponed")})

    reserved, postponed = body["today"]["games"]
    assert body["today"]["started"] is True, "保留賽是今天發生的事，主區塊該切過來"
    assert "pregame" not in reserved
    assert (reserved["live"]["away_score"], reserved["live"]["home_score"]) == (3, 2)
    # 延賽根本沒開打：不觸發日界線，賽前欄位照掛（呈現端自己不畫）。
    assert postponed["live"]["phase"] == "postponed"
    assert postponed["pregame"]["status"] == "no_features"


def test_postponed_alone_does_not_move_the_main_block(monkeypatch):
    """全場延賽的日子沒有任何新賽況可看，主位必須留在上一個比賽日。"""
    body, _ = _run(monkeypatch, _today_script([_game(247, _TODAY), _game(248, _TODAY)]),
                   snapshots={247: _snapshot(247, "postponed"),
                              248: _snapshot(248, "postponed")})

    assert body["today"]["started"] is False


def test_worker_unavailable_degrades_silently_and_signals_the_maintainer(monkeypatch):
    """情境 8｜worker 不可用：`started` 為假（訪客面因此退回純日期版面），
    `live_source` 留給維護者訊號，且**不宣稱** Redis 或 worker 壞掉——API 這一側
    分不出「Redis 不通」「worker 沒跑」「不在抓取窗口」，講死任何一個都超出證據。"""
    body, _ = _run(monkeypatch, _today_script([_game(247, _TODAY), _game(248, _TODAY)]),
                   snapshots={})

    today = body["today"]
    assert today["started"] is False
    assert today["live_source"]["status"] == "unavailable"
    assert today["live_source"]["snapshots"] == 0
    assert today["live_source"]["games"] == 2
    assert all(g["live"] is None for g in today["games"])


def test_partial_snapshots_are_reported_as_partial_not_ok(monkeypatch):
    body, _ = _run(monkeypatch, _today_script([_game(247, _TODAY), _game(248, _TODAY)]),
                   snapshots={247: _snapshot(247, "live", inning=2, events=30)})

    assert body["today"]["live_source"]["status"] == "partial"


def test_live_source_disabled_when_redis_not_configured(monkeypatch):
    """本機／CI 預設沒有 REDIS_URL。這與「有設定但拿不到資料」是不同的狀態，
    判別碼不得共用（blueprint §8.1：不同語意不共用同一句空態）。"""
    body, _ = _run(monkeypatch, _today_script([_game(247, _TODAY)]))

    assert body["today"]["live_source"]["status"] == "disabled"
    assert body["today"]["games"][0]["live"] is None


def test_live_source_reason_never_leaks_implementation_vocabulary():
    """**紅線**：`reason` 是訪客也收得到的 payload，不得出現元件名、環境變數名或成因
    宣稱。要分辨「未啟用」與「啟用了但拿不到」看的是 `status` 這個機器可讀的判別碼。

    窮舉四種輸入組合，而不是只抽驗異常那一支——上一版的斷言只蓋到 `unavailable`，
    而洩漏實作字彙的其實是沒被蓋到的 `disabled` 分支。
    """
    banned = ("Redis", "REDIS", "redis", "worker", "Worker", "當機", "掛掉", "錯誤", "URL")
    cases = [(False, 0, 3), (True, 3, 3), (True, 0, 3), (True, 1, 3), (True, 0, 0)]
    reasons = [daily.live_source_status(*case)[1] for case in cases]

    assert any(reason for reason in reasons), "至少要有一種情形給得出 reason，否則本測試空轉"
    for reason in reasons:
        for word in banned:
            assert word not in (reason or ""), f"reason 洩漏實作字彙 {word}：{reason}"


def test_today_query_is_scoped_to_the_requested_season():
    """**回歸**：`as_of` 是外部給的日期，不像 latest／next 那樣自帶球季。

    `latest_day`／`next_day` 是在 season 範圍內推導出來的，所以「只用日期查」隱含就選中
    了正確的球季；`as_of` 沒有這個保護。少了 season 條件，`?season=2020` 會讓 today 區塊
    裝進今天的 2026 場次，與同一份 response 的 `scope.season` 自相矛盾。

    本測試釘的是查詢本身（腳本化 cursor 不會真的過濾），因為缺陷在 SQL 而不在後續邏輯。
    """
    import inspect

    source = inspect.getsource(daily.daily_summary)
    per_day = source[source.index("WHERE g.kind_code = ANY(%s) AND g.game_date = ANY(%s)"):]
    per_day = per_day[:per_day.index("ORDER BY")]

    assert "g.year = %s" in per_day, "逐日場次查詢必須帶 season 條件（as_of 不自帶球季）"


def test_live_source_status_separates_no_games_from_unavailable(monkeypatch):
    """裁決 B｜「今天沒有場次」與「今日即時來源不可用」必須是兩個可分辨的狀態。

    後端這一側的分界是 `today` 本身：今天沒有排定場次時整塊為 None（呈現端據此說
    「今日無賽程」），有場次卻一份快照都拿不到才是 `unavailable`。兩者在訪客面都會
    退回純日期版面，長得一模一樣——分辨得靠這裡的結構差異，不能靠畫面。
    """
    rest_day, _ = _run(monkeypatch, _script(
        latest=_TODAY - timedelta(days=1), next_day=_TODAY + timedelta(days=3), scoped=2,
        games=[_game(1, _TODAY - timedelta(days=1), home=2, away=1),
               _game(2, _TODAY + timedelta(days=3))],
    ), snapshots={})
    source_down, _ = _run(monkeypatch, _today_script([_game(247, _TODAY), _game(248, _TODAY)]),
                          snapshots={})

    assert rest_day["today"] is None
    assert source_down["today"]["live_source"]["status"] == "unavailable"


def test_db_completed_today_game_counts_as_started_without_any_snapshot(monkeypatch):
    """情境 10 的另一半｜隔日爬蟲補完後 worker 早已不再供該場：DB 有比分即算已開始，
    賽前機率同樣不得回來。"""
    body, _ = _run(monkeypatch, _script(
        latest=_TODAY, next_day=_TODAY + timedelta(days=1), scoped=2,
        games=[_game(247, _TODAY, home=6, away=2), _game(250, _TODAY + timedelta(days=1))],
    ), snapshots={})

    game = body["today"]["games"][0]
    assert body["today"]["started"] is True
    assert game["completed"] is True and game["home_score"] == 6
    assert "pregame" not in game


def test_today_block_is_independent_of_latest_and_next_day(monkeypatch):
    """情境 10｜跨日回退：今天的場次早已入庫（latest=今天、next=明天）時，
    `today` 仍必須出現——它既不是「最近比賽日」也不是「下一批」。"""
    body, _ = _run(monkeypatch, _script(
        latest=_TODAY, next_day=_TODAY + timedelta(days=1), scoped=3,
        games=[_game(247, _TODAY, home=3, away=1), _game(250, _TODAY + timedelta(days=1))],
    ), snapshots={})

    assert body["today"]["game_date"] == _TODAY.isoformat()
    assert [g["game_sno"] for g in body["today"]["games"]] == [247]
    assert body["next_slate"]["game_date"] == (_TODAY + timedelta(days=1)).isoformat()


# --- 契約：今日區塊走台北日界（追加裁定 A）-----------------------------------

def test_taipei_today_crosses_the_day_before_utc_does():
    """純函式：台北比 UTC 早 8 小時，故 UTC 的 16:00 起就已經是台北的隔天。"""
    assert daily.taipei_today(datetime(2026, 8, 7, 18, 0, tzinfo=UTC)) == date(2026, 8, 8)
    assert daily.taipei_today(datetime(2026, 8, 7, 15, 59, tzinfo=UTC)) == date(2026, 8, 7)
    # 台北 00:00 整（UTC 前一日 16:00）已算新的一天。
    assert daily.taipei_today(datetime(2026, 8, 7, 16, 0, tzinfo=UTC)) == date(2026, 8, 8)


def test_today_block_uses_taipei_day_when_container_clock_is_utc(monkeypatch):
    """**回歸**（追加裁定 A）：容器 TZ 未設（生產實測落後台北 8 小時）時，台北凌晨
    `date.today()` 會回前一天，於是首頁把**昨天**標成「今日賽事」。

    情境：UTC 2026-08-07 18:00 ＝ 台北 2026-08-08 02:00。容器本地日還是 08-07，
    但「今日賽事」必須是台北的 08-08。

    同一份 response 裡 `as_of` 仍是容器本地日——那是刻意的，不是漏改：`as_of` 屬
    upper bound 用法，DATA-TZ-BOUNDARY1 盤點後明確擱置到 REMEDY1 Phase 2
    （見 `cpbl.completion` 模組註解與 `daily.taipei_today` 的說明）。
    """
    utc_now = datetime(2026, 8, 7, 18, 0, tzinfo=UTC)
    container_day, taipei_day = date(2026, 8, 7), date(2026, 8, 8)
    body, _ = _run(monkeypatch, _script(
        latest=date(2026, 8, 6), next_day=taipei_day, scoped=3,
        games=[_game(240, date(2026, 8, 6), home=4, away=2),
               _game(246, container_day, home=1, away=0),   # UTC 的「今天」
               _game(247, taipei_day), _game(248, taipei_day)],
    ), snapshots={}, now=utc_now, today_local=container_day)

    assert body["today"]["game_date"] == "2026-08-08", "今日區塊必須用台北日"
    assert [g["game_sno"] for g in body["today"]["games"]] == [247, 248]
    assert 246 not in [g["game_sno"] for g in body["today"]["games"]], \
        "UTC 的『今天』（台北的昨天）不得被當成今日賽事"
    # as_of 語意一字不改——兩個日界並存是本卡的刻意設計。
    assert body["scope"]["as_of"] == "2026-08-07"


def test_today_block_is_unchanged_when_container_runs_taipei(monkeypatch):
    """對照組：容器本來就在台北時區時，兩個日界重合，行為與修改前完全相同。
    這也是為什麼本機審不出上面那個缺陷。"""
    taipei_now = datetime(2026, 8, 8, 2, 0, tzinfo=ZoneInfo("Asia/Taipei"))
    same_day = date(2026, 8, 8)
    body, _ = _run(monkeypatch, _script(
        latest=date(2026, 8, 7), next_day=same_day, scoped=2,
        games=[_game(240, date(2026, 8, 7), home=4, away=2), _game(247, same_day)],
    ), snapshots={}, now=taipei_now, today_local=same_day)

    assert body["today"]["game_date"] == body["scope"]["as_of"] == "2026-08-08"


# --- 純函式：live view 與來源狀態 ---------------------------------------------

def test_live_source_status_never_claims_health_it_cannot_observe():
    assert daily.live_source_status(False, 0, 3)[0] == "disabled"
    assert daily.live_source_status(True, 3, 3) == ("ok", None)
    assert daily.live_source_status(True, 0, 3)[0] == "unavailable"
    assert daily.live_source_status(True, 1, 3)[0] == "partial"
    # 今天沒有場次時「零份快照」不是異常。
    assert daily.live_source_status(True, 0, 0) == ("ok", None)


def test_live_interrupt_is_two_staged_and_fails_closed():
    """兩階降級的後端側。首屏只有這一格可用（呈現端在 SSR 不能碰瀏覽器時鐘）。"""
    stage = lambda age: daily.live_interrupt("live", age, 45, "fresh", "ok")  # noqa: E731
    assert stage(10) == "none"
    assert stage(60) == "degraded"
    assert stage(179) == "degraded"
    assert stage(181) == "blackout"
    # 無 fetched_at＝無從證明新鮮 → fail closed 收掉數字。
    assert stage(None) == "blackout"
    # 來源自陳錯誤即使很新也算一階。
    assert daily.live_interrupt("live", 5, 45, "fresh", "error") == "degraded"
    # final 是不可變快照，不因時間經過被誤標。
    assert daily.live_interrupt("final", 86_400, None, "final", "ok") == "none"
    # 賽前場次不套 3 分鐘黑幕（後端門檻 20 分鐘，卡上也沒有會變的數字）。
    assert daily.live_interrupt("lineup_announced", 300, 1200, "fresh", "ok") == "none"


def test_live_view_reads_bases_from_the_last_event_only_while_live():
    log = [{"OutCnt": 0, "FirstBase": None, "SecondBase": None, "ThirdBase": None},
           {"OutCnt": 2, "FirstBase": "王一", "SecondBase": None, "ThirdBase": "張三"}]
    live = daily.live_view({**_snapshot(1, "live", inning=7, events=2), "livelog": log})

    assert live["outs"] == 2
    assert live["bases"] == {"first": True, "second": False, "third": True}

    final = daily.live_view({**_snapshot(1, "final", inning=9, events=2), "livelog": log})
    assert final["bases"] is None and final["outs"] is None


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

    assert set(body) == {"scope", "today", "latest_game_day", "next_slate",
                         "freshness", "availability"}
    assert set(body["availability"]) == {"schedule", "results", "pregame_model"}
    for day in (body["latest_game_day"], body["next_slate"]):
        if day is not None:
            assert day["games"], "有比賽日就必須有場次，不得回空陣列"


def test_live_latest_game_day_games_are_either_results_or_scoreless():
    """最近比賽日**可以**含未完成場次（局部因雨延賽、補賽日未定時仍掛原定日），但每一
    場都必須落在兩種形狀之一，不得有第三種：

    - 完成場：雙方比分都在（那才是「最近比賽日」成立的理由，故至少要有一場）；
    - 未完成場：比分一律 null，且日期不在未來。

    舊版斷言「每一場都 completed」在本機 DB 遇到局部延賽日必紅（2026-08-09），而那個
    形狀是真實且合法的資料，不是缺陷。
    """
    body = _live()
    if body["latest_game_day"] is None:
        pytest.skip("本機 DB 無已完成場次")

    games = body["latest_game_day"]["games"]
    assert any(g["completed"] for g in games), "最近比賽日至少要有一場賽果，否則它不該是最近比賽日"
    for game in games:
        if game["completed"]:
            assert game["home_score"] is not None and game["away_score"] is not None
        else:
            assert game["home_score"] is None and game["away_score"] is None
            assert game["game_date"] <= body["scope"]["as_of"]


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
        # serving 狀態語彙屬模型層級，不得外洩到逐場欄位。
        assert not game["pregame"]["status"].startswith("serving_")
