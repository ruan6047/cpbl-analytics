"""#237 Phase B：2026+ 季後 E／C 的 live worker 與每日鏈 producer（純單元，零 I/O）。

資料來源標示（測試值不得被誤讀成官方擷取）：
- RECORDED：轉錄自 stats.cpbl 2026-10-09 18:20:52（台北）唯讀觀測
  ``/private/tmp/cpbl-237-repair-20261009/stats-live-contract/observation.json``
  （sha256 dbfb47db6189558f6624e99ae30876f4d50e4a77de6af76a18c4ea39b14ea83a）：
  E 四場的 GameId／KindCode／GameSno／PreExeDate／GameStatus／隊伍／比分／局數；C 為 200＋空清單。
- SYNTHETIC：觀測只記錄「WinningPitcher／LoserPitcher 非空」，未記錄其值，故投手 Acnt／姓名
  是測試自造；FINISHED、身分錯置、來源失敗等情境也都是自造。
Redis、HTTP、DB 一律用 fake／MockTransport，不連任何外部。
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta, timezone

import httpx
import pytest

from cpbl.ingest.live_game_worker import (
    LiveGameWorker,
    RedisLiveGameCache,
    StatsLiveSource,
    build_snapshot,
)

TPE = timezone(timedelta(hours=8))
# RECORDED：觀測時刻
OBSERVED_AT = datetime(2026, 10, 9, 18, 20, 52, tzinfo=TPE)

_LION = {"Code": "ADD011", "Name": "統一7-ELEVEn獅"}
_BROTHERS = {"Code": "ACN011", "Name": "中信兄弟"}


def _e_row(sno: int, starts: str, status: str, away: dict, home: dict,
           score: tuple[int, int] = (0, 0), inning: int = 1) -> dict:
    """RECORDED schedule 列（只取觀測檔有的欄位）。"""
    return {
        "GameId": f"2026-E-{sno}", "KindCode": "E", "GameSno": sno,
        "PreExeDate": starts, "GameStatus": status, "SkipTrackman": False,
        "InningSeq": inning, "VisitingHomeType": 1,
        "Visiting": {"Team": dict(away), "Score": score[0]},
        "Home": {"Team": dict(home), "Score": score[1]},
        "WinningPitcher": None, "LoserPitcher": None, "Closer": None,
    }


def _recorded_e_schedule() -> list[dict]:
    return [
        _e_row(1, "2026-10-09T17:05:00", "START", _LION, _BROTHERS, (0, 3), 5),
        _e_row(2, "2026-10-10T17:05:00", "SCHEDULED", _BROTHERS, _LION),
        _e_row(3, "2026-10-11T17:05:00", "SCHEDULED", _LION, _BROTHERS),
        _e_row(4, "2026-10-12T18:35:00", "SCHEDULED", _LION, _BROTHERS),
    ]


# SYNTHETIC：賽中責任投手（觀測只知道「非空」）
_PITCHER_OF_RECORD_W = {"Acnt": "SYN0000001", "Name": "合成勝方責任投手"}
_PITCHER_OF_RECORD_L = {"Acnt": "SYN0000002", "Name": "合成敗方責任投手"}


def _e1_detail(status: str = "START") -> dict:
    """E1 單場 detail：身分／比分／局數 RECORDED，責任投手 SYNTHETIC。"""
    row = _e_row(1, "2026-10-09T17:05:00", status, _LION, _BROTHERS, (0, 3), 5)
    row["Field"] = {"Abbe": "洲際"}
    row["LiveLog"] = []
    row["WinningPitcher"] = dict(_PITCHER_OF_RECORD_W)
    row["LoserPitcher"] = dict(_PITCHER_OF_RECORD_L)
    row["MVP"] = None
    return row


def _detail_from_row(row: dict) -> dict:
    detail = dict(row)
    detail["LiveLog"] = []
    return detail


def _a_row(sno: int, starts: str, year: int = 2026) -> dict:
    return {"GameId": f"{year}-A-{sno}", "KindCode": "A", "GameSno": sno,
            "PreExeDate": starts, "GameStatus": "SCHEDULED",
            "Visiting": {"Team": dict(_LION), "Score": 0},
            "Home": {"Team": dict(_BROTHERS), "Score": 0}}


class _Cache:
    def __init__(self) -> None:
        self.items: dict[tuple[int, str, int], dict] = {}
        self.source_errors: list[tuple[int, str, int, str]] = []
        self.released = 0

    def is_killed(self) -> bool:
        return False

    def acquire_lock(self) -> bool:
        return True

    def release_lock(self) -> None:
        self.released += 1

    def get_snapshot(self, year: int, kind: str, sno: int) -> dict | None:
        return self.items.get((year, kind, sno))

    def set_snapshot(self, snapshot: dict) -> None:
        y, k, s = snapshot["game_id"].split("-")
        self.items[(int(y), k, int(s))] = snapshot

    def record_source_error(self, year: int, kind: str, sno: int, *,
                            observed_at: datetime, error_type: str) -> None:
        self.source_errors.append((year, kind, sno, error_type))


class _Source:
    """記錄每次呼叫；schedule 依 kind 回傳，detail 只對已知 GameId 回傳。"""

    def __init__(self, schedules: dict[str, list[dict] | Exception],
                 details: dict[str, dict]) -> None:
        self.schedules = schedules
        self.details = details
        self.schedule_calls: list[tuple] = []
        self.game_calls: list[str] = []

    def fetch_schedule(self, year: int, month: int, kind_code: str = "A") -> list[dict]:
        self.schedule_calls.append((year, month, kind_code))
        value = self.schedules.get(kind_code, [])
        if isinstance(value, Exception):
            raise value
        return [dict(r) for r in value]

    def fetch_game(self, game_id: str) -> dict:
        self.game_calls.append(game_id)
        if game_id not in self.details:
            raise AssertionError(f"不得請求 schedule 未回傳的 GameId：{game_id}")
        return json.loads(json.dumps(self.details[game_id]))


def _worker(source: _Source, cache: _Cache, **kw) -> LiveGameWorker:
    return LiveGameWorker(cache=cache, fetch_schedule=source.fetch_schedule,
                          fetch_game=source.fetch_game, **kw)


# ═══════════════════════════════ worker：A 既有行為 ═══════════════════════════════


def test_default_worker_stays_a_only_with_two_arg_schedule_calls() -> None:
    """預設不開季後：只以 (year, month) 呼叫（舊 2-arg callable 不會被傳第三個參數），結果形狀不變。"""
    calls: list[tuple] = []
    worker = LiveGameWorker(
        cache=_Cache(),
        fetch_schedule=lambda year, month: calls.append((year, month)) or [],
        fetch_game=lambda game_id: pytest.fail(f"unexpected fetch {game_id}"),
    )

    result = worker.run_cycle(OBSERVED_AT)

    assert calls == [(2026, 10)]
    assert result["state"] == "ok"
    assert "schedule_errors" not in result and "rejected_rows" not in result


def test_postseason_kinds_reject_non_postseason_codes() -> None:
    for bad in (("A",), ("D",), ("E", "F")):
        with pytest.raises(ValueError):
            LiveGameWorker(cache=_Cache(), fetch_schedule=lambda *a: [],
                           fetch_game=lambda g: {}, postseason_kinds=bad)


# ═══════════════════════════ worker：E／C 實際觀測情境 ═══════════════════════════


def test_recorded_e_schedule_caches_only_window_games_and_c_empty_is_ok() -> None:
    schedule = _recorded_e_schedule()
    source = _Source(
        {"A": [], "E": schedule, "C": []},
        {"2026-E-1": _e1_detail("START"), "2026-E-2": _detail_from_row(schedule[1])},
    )
    cache = _Cache()

    result = _worker(source, cache, postseason_kinds=("E", "C")).run_cycle(OBSERVED_AT)

    assert result["state"] == "ok"
    assert source.schedule_calls == [(2026, 10, "A"), (2026, 10, "E"), (2026, 10, "C")]
    # 觀測窗（-8h～+30h）內只有 E1、E2；E3／E4 與任何 C ID 都不得被請求
    assert source.game_calls == ["2026-E-1", "2026-E-2"]
    assert set(cache.items) == {(2026, "E", 1), (2026, "E", 2)}
    assert result["schedule_errors"] == [] and result["rejected_rows"] == 0
    e1 = cache.items[(2026, "E", 1)]
    assert (e1["phase"], e1["raw_status"], e1["kind_code"]) == ("live", "START", "E")
    assert (e1["away"]["score"], e1["home"]["score"], e1["inning"]) == (0, 3, 5)
    assert cache.items[(2026, "E", 2)]["phase"] == "scheduled"
    assert result["next_poll_seconds"] == 12  # 有 live 場 → 沿用既有 12 秒


def test_live_pitcher_of_record_is_not_published_as_decision() -> None:
    """2026-E-1 START 時官方頂層 WinningPitcher／LoserPitcher 非空——那是責任投手，不是勝敗投。"""
    live = build_snapshot(_e1_detail("START"), fetched_at=OBSERVED_AT)
    scheduled = build_snapshot(_e1_detail("SCHEDULED"), fetched_at=OBSERVED_AT)
    unknown = build_snapshot(_e1_detail("SUSPENDED_SYN"), fetched_at=OBSERVED_AT)

    for snap, phase in ((live, "live"), (scheduled, "scheduled"), (unknown, "unknown")):
        assert snap["phase"] == phase
        assert snap["decisions"] == {
            "winning_pitcher": None, "losing_pitcher": None, "closer": None, "mvp": None,
        }


def test_final_postseason_keeps_official_decisions() -> None:
    final = build_snapshot(_e1_detail("FINISHED"), fetched_at=OBSERVED_AT)

    assert final["phase"] == "final"
    assert final["decisions"]["winning_pitcher"] == {"player_id": "SYN0000001", "name": "合成勝方責任投手"}
    assert final["decisions"]["losing_pitcher"] == {"player_id": "SYN0000002", "name": "合成敗方責任投手"}


@pytest.mark.parametrize("game_id,kind", [("2026-A-360", "A"), ("2025-E-1", "E"), ("2026-D-1", "D")])
def test_decision_withholding_does_not_touch_a_d_or_older_seasons(game_id: str, kind: str) -> None:
    raw = _e1_detail("START")
    raw["GameId"], raw["KindCode"] = game_id, kind

    snap = build_snapshot(raw, fetched_at=OBSERVED_AT)

    assert snap["phase"] == "live"
    assert snap["decisions"]["winning_pitcher"] == {"player_id": "SYN0000001", "name": "合成勝方責任投手"}


# ═══════════════════════════ worker：身分／cache 隔離 ═══════════════════════════


def test_schedule_rows_with_foreign_identity_are_dropped_before_any_request() -> None:
    e1 = _recorded_e_schedule()[0]
    foreign_kind = dict(e1, GameId="2026-C-1")          # E 請求卻回 C 的 ID
    foreign_year = dict(e1, GameId="2025-E-1")          # 跨年
    mislabeled = dict(e1, GameId="2026-E-9", KindCode="A")
    malformed = dict(e1, GameId="E-1")
    source = _Source({"E": [foreign_kind, foreign_year, mislabeled, malformed], "C": []}, {})
    cache = _Cache()

    result = _worker(source, cache, postseason_kinds=("E", "C")).run_cycle(OBSERVED_AT)

    assert source.game_calls == []
    assert cache.items == {}
    assert result["rejected_rows"] == 4


def test_detail_identity_mismatch_never_writes_another_games_key() -> None:
    e1 = _recorded_e_schedule()[0]
    wrong = _e1_detail("START")
    wrong["GameId"], wrong["KindCode"] = "2026-A-1", "A"   # 來源回錯場
    source = _Source({"E": [e1]}, {"2026-E-1": wrong})
    cache = _Cache()

    result = _worker(source, cache, postseason_kinds=("E",)).run_cycle(OBSERVED_AT)

    assert cache.items == {}
    assert cache.source_errors == [(2026, "E", 1, "ValueError")]
    assert result["errors"] == 1


def test_redis_keys_are_isolated_by_kind() -> None:
    class _Redis:
        def __init__(self) -> None:
            self.store: dict[str, str] = {}

        def set(self, key, value, **_kw):
            self.store[key] = value
            return True

        def get(self, key):
            return self.store.get(key)

        def delete(self, key):
            self.store.pop(key, None)

    client = _Redis()
    cache = RedisLiveGameCache(client)
    a = build_snapshot(dict(_e1_detail("START"), GameId="2026-A-1", KindCode="A"), fetched_at=OBSERVED_AT)
    e = build_snapshot(_e1_detail("START"), fetched_at=OBSERVED_AT)
    cache.set_snapshot(a)
    cache.set_snapshot(e)

    assert set(client.store) == {"cpbl:live:2026:A:1", "cpbl:live:2026:E:1"}
    assert cache.get_snapshot(2026, "E", 1)["kind_code"] == "E"
    assert cache.get_snapshot(2026, "A", 1)["kind_code"] == "A"
    assert cache.get_snapshot(2026, "C", 1) is None


# ═══════════════════════════ worker：來源失敗有界 ═══════════════════════════


def test_postseason_schedule_failure_is_bounded_and_does_not_block_a() -> None:
    a = _a_row(360, "2026-10-09T18:35:00")
    source = _Source(
        {"A": [a], "E": httpx.ConnectTimeout("syn timeout"), "C": []},
        {"2026-A-360": _detail_from_row(a)},
    )
    cache = _Cache()

    result = _worker(source, cache, postseason_kinds=("E", "C")).run_cycle(OBSERVED_AT)

    assert result["state"] == "ok"
    assert set(cache.items) == {(2026, "A", 360)}
    assert result["schedule_errors"] == [
        {"kind": "E", "year": 2026, "month": 10, "error_type": "ConnectTimeout"},
    ]
    assert (2026, 10, "C") in source.schedule_calls, "E 失敗不得連坐 C"
    assert cache.released == 1


def test_a_candidates_are_not_starved_by_postseason_rows() -> None:
    a = _a_row(360, "2026-10-09T18:35:00")
    schedule = _recorded_e_schedule()
    source = _Source({"A": [a], "E": schedule},
                     {"2026-A-360": _detail_from_row(a), "2026-E-1": _e1_detail()})
    cache = _Cache()

    _worker(source, cache, postseason_kinds=("E",), max_games_per_cycle=1).run_cycle(OBSERVED_AT)

    assert source.game_calls == ["2026-A-360"]


def test_postseason_schedule_is_not_requested_before_2026() -> None:
    source = _Source({"A": [], "E": [], "C": []}, {})

    _worker(source, _Cache(), postseason_kinds=("E", "C")).run_cycle(
        datetime(2025, 10, 9, 18, 0, tzinfo=TPE))

    assert source.schedule_calls == [(2025, 10, "A")]


def test_final_postseason_snapshot_is_not_refetched() -> None:
    e1 = _recorded_e_schedule()[0]
    source = _Source({"E": [e1]}, {})
    cache = _Cache()
    cache.set_snapshot(build_snapshot(_e1_detail("FINISHED"), fetched_at=OBSERVED_AT))

    result = _worker(source, cache, postseason_kinds=("E",)).run_cycle(OBSERVED_AT)

    assert source.game_calls == []
    assert result["skipped_final"] == 1


def test_stats_source_passes_kind_code_and_c_empty_list() -> None:
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(dict(request.url.params))
        return httpx.Response(200, json={"Data": {"Games": []}})

    source = StatsLiveSource(client=httpx.Client(transport=httpx.MockTransport(handler)))
    try:
        assert source.fetch_schedule(2026, 10, "C") == []
        assert source.fetch_schedule(2026, 10) == []
    finally:
        source.close()

    assert seen == [
        {"kindCode": "C", "year": "2026", "month": "10"},
        {"kindCode": "A", "year": "2026", "month": "10"},
    ]


# ═══════════════════════════ 每日鏈 producer ═══════════════════════════


def test_postseason_step_scrapes_e_and_c_and_bounds_failure() -> None:
    from cpbl.ingest import run_refresh_recent as rr

    calls: list[tuple] = []

    def scrape(start: int, end: int, kind: str) -> dict[int, int]:
        calls.append((start, end, kind))
        if kind == "E":
            raise RuntimeError("syn getgamedatas HTTP 428")
        return {start: 0}  # C：官方回空清單 → 0 列，不是錯誤

    out = rr._postseason_games_step(2026, ("E", "C"), scrape)

    assert calls == [(2026, 2026, "E"), (2026, 2026, "C")]
    assert out["games"] == {"C": {2026: 0}}
    assert out["errors"] == [{"kind": "E", "error": "syn getgamedatas HTTP 428"}]


@pytest.mark.parametrize("year,kinds", [(2025, ("E", "C")), (2026, ())])
def test_postseason_step_is_a_noop_before_2026_or_when_not_enabled(year, kinds) -> None:
    from cpbl.ingest import run_refresh_recent as rr

    out = rr._postseason_games_step(year, kinds, lambda *a: pytest.fail(f"unexpected {a}"))

    assert out == {"games": {}, "errors": []}


def test_postseason_step_rejects_non_postseason_kind() -> None:
    from cpbl.ingest import run_refresh_recent as rr

    with pytest.raises(ValueError):
        rr._postseason_games_step(2026, ("D",), lambda *a: pytest.fail(f"unexpected {a}"))


@pytest.mark.parametrize("raw,expected", [
    ("", ()), (None, ()), ("E", ("E",)), ("E,C", ("E", "C")), (" C , E ", ("C", "E")),
])
def test_parse_postseason_kinds_accepts_only_e_c(raw, expected) -> None:
    from cpbl.config import parse_postseason_kinds

    assert parse_postseason_kinds(raw) == expected


@pytest.mark.parametrize("raw", ["A", "D", "e", "E,E", "E;C", "E,F"])
def test_parse_postseason_kinds_fails_loudly(raw) -> None:
    from cpbl.config import parse_postseason_kinds

    with pytest.raises(ValueError):
        parse_postseason_kinds(raw)


def test_settings_default_keeps_both_entrypoints_off(monkeypatch: pytest.MonkeyPatch) -> None:
    from cpbl.config import Settings

    monkeypatch.delenv("LIVE_GAME_POSTSEASON_KINDS", raising=False)
    monkeypatch.delenv("REFRESH_POSTSEASON_KINDS", raising=False)
    fresh = Settings(_env_file=None)
    assert (fresh.live_game_postseason_kinds, fresh.refresh_postseason_kinds) == ("", "")

    monkeypatch.setenv("LIVE_GAME_POSTSEASON_KINDS", "E,C")
    monkeypatch.setenv("REFRESH_POSTSEASON_KINDS", "E")
    opted = Settings(_env_file=None)
    assert (opted.live_game_postseason_kinds, opted.refresh_postseason_kinds) == ("E,C", "E")


def _stub_chain(monkeypatch: pytest.MonkeyPatch, scrape, logged: dict, calls: list[str],
                kinds_setting: str = "E,C") -> None:
    from cpbl.ingest import run_refresh_recent as rr

    monkeypatch.setattr(rr.settings, "refresh_postseason_kinds", kinds_setting)

    class _Today(date):
        @classmethod
        def today(cls) -> date:
            return date(2026, 10, 10)

    monkeypatch.setattr(rr, "date", _Today)
    monkeypatch.setattr(rr, "_GAMELOG_GAPS", [])
    monkeypatch.setattr(rr.sys, "argv", ["cpbl-refresh-recent", "fast"])
    for name, value in (
        ("migrate", lambda: None),
        ("scrape_games", scrape),
        ("scrape_all", lambda *a, **k: {}),
        ("scrape_standings", lambda *a, **k: {}),
        ("standings_failures", lambda: []),
        ("reset_standings_failures", lambda: None),
        ("scrape_transactions", lambda *a, **k: 0),
        ("build_championships", lambda *a, **k: 0),
        ("scrape_game_details", lambda *a, **k: 0),
        ("build_splits", lambda *a, **k: {}),
        ("build_career", lambda *a, **k: 0),
        ("_sync_player_names", lambda: 0),
        ("_recent_counts", lambda *a, **k: []),
        ("_missing_gamelog_snos", lambda _year, _kc: []),
        ("_pa_build_step", lambda *a, **k: calls.append("pa_build") or {
            "games": 0, "actions": {}, "build_states": {}, "errors": []}),
        ("_log_refresh", lambda _s, _f, _t, _tot, _c, detail, ok, note:
            logged.update(ok=ok, note=note, detail=detail)),
    ):
        monkeypatch.setattr(rr, name, value)


def test_daily_chain_default_setting_is_exactly_a_and_d(monkeypatch: pytest.MonkeyPatch) -> None:
    """反例（預設）：未設定時每日鏈只呼叫原本的 A、D，不碰 E／C。"""
    from cpbl.ingest import run_refresh_recent as rr

    scrape_calls: list[tuple] = []
    logged: dict = {}
    _stub_chain(monkeypatch, lambda *a: scrape_calls.append(a) or {a[0]: 0}, logged, [],
                kinds_setting="")

    rr.main()

    assert scrape_calls == [(2026, 2026), (2026, 2026, "D")]
    assert logged["ok"] is True
    assert logged["detail"]["games_postseason"] == {"games": {}, "errors": []}


def test_daily_chain_bad_setting_fails_before_any_write(monkeypatch: pytest.MonkeyPatch) -> None:
    from cpbl.ingest import run_refresh_recent as rr

    touched: list[str] = []
    _stub_chain(monkeypatch, lambda *a: touched.append("scrape") or {}, {}, [], kinds_setting="A")
    monkeypatch.setattr(rr, "migrate", lambda: touched.append("migrate"))

    with pytest.raises(ValueError):
        rr.main()
    assert touched == []


def test_daily_chain_keeps_a_d_calls_and_adds_postseason(monkeypatch: pytest.MonkeyPatch) -> None:
    from cpbl.ingest import run_refresh_recent as rr

    scrape_calls: list[tuple] = []
    logged: dict = {}
    calls: list[str] = []
    _stub_chain(monkeypatch, lambda *a: scrape_calls.append(a) or {a[0]: 0}, logged, calls)

    rr.main()  # 不得拋 SystemExit

    # A 仍是原本的 2-arg 呼叫、D 原樣，季後只多 E／C 兩次
    assert scrape_calls == [(2026, 2026), (2026, 2026, "D"), (2026, 2026, "E"), (2026, 2026, "C")]
    assert logged["ok"] is True and logged["note"] is None
    assert logged["detail"]["games_postseason"] == {"games": {"E": {2026: 0}, "C": {2026: 0}},
                                                    "errors": []}


def test_daily_chain_postseason_failure_is_visible_but_not_blocking(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from cpbl.ingest import cpbl_gamelog
    from cpbl.ingest import run_refresh_recent as rr

    def scrape(*a):
        if a[2:] == ("C",):
            raise RuntimeError("syn C failure")
        return {a[0]: 0}

    logged: dict = {}
    calls: list[str] = []
    _stub_chain(monkeypatch, scrape, logged, calls)

    with pytest.raises(SystemExit) as e:
        rr.main()

    assert e.value.code == cpbl_gamelog.EXIT_INCOMPLETE_SCRAPE == 69
    assert "pa_build" in calls, "季後失敗不得中止後續步驟"
    assert logged["ok"] is False
    assert logged["note"] == "季後賽程更新失敗：C"
    assert logged["detail"]["games_postseason"]["errors"] == [{"kind": "C", "error": "syn C failure"}]


def test_hypothetical_c_row_is_cached_under_its_own_kind_key() -> None:
    """HYPOTHETICAL：官方 C 至今只回空清單（2026-10-09 18:20），以下 C 列全為合成，
    只用來證明「若日後 schedule 真的回 C 列」時 cache key 與 E 隔離；⛔ 不代表 C 的 ID／編號規則。"""
    hypo_c = dict(_e_row(1, "2026-10-09T18:35:00", "SCHEDULED", _LION, _BROTHERS),
                  GameId="2026-C-1", KindCode="C")
    e1 = _recorded_e_schedule()[0]
    source = _Source({"E": [e1], "C": [hypo_c]},
                     {"2026-E-1": _e1_detail("START"), "2026-C-1": _detail_from_row(hypo_c)})
    cache = _Cache()

    _worker(source, cache, postseason_kinds=("E", "C")).run_cycle(OBSERVED_AT)

    assert set(cache.items) == {(2026, "E", 1), (2026, "C", 1)}
    assert cache.items[(2026, "C", 1)]["kind_code"] == "C"
    assert cache.items[(2026, "E", 1)]["home"]["score"] == 3


# ═══════════════════════════ 正式入口 CLI：設定 → worker 實際傳遞 ═══════════════════════════


class _FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.closed = False

    def set(self, key, value, nx=False, ex=None):
        if nx and key in self.store:
            return False
        self.store[key] = value
        return True

    def get(self, key):
        return self.store.get(key)

    def delete(self, key):
        self.store.pop(key, None)

    def eval(self, _script, _n, key, token):
        if self.store.get(key) == token:
            self.store.pop(key)
            return 1
        return 0

    def close(self):
        self.closed = True


def _run_worker_cli(monkeypatch: pytest.MonkeyPatch, kinds_setting: str,
                    schedules: dict[str, list[dict]]) -> tuple[list[tuple], _FakeRedis, list[str]]:
    from cpbl.ingest import run_live_game_worker as rlw

    calls: list[tuple] = []
    redis_client = _FakeRedis()
    opened: list[str] = []

    class _FakeStatsSource:
        def __init__(self) -> None:
            opened.append("source")

        def fetch_schedule(self, year, month, kind_code="A"):
            calls.append((year, month, kind_code))
            return [dict(r) for r in schedules.get(kind_code, [])]

        def fetch_game(self, game_id):
            calls.append(("game", game_id))
            if game_id == "2026-E-1":
                return _e1_detail("START")
            raise AssertionError(f"unexpected fetch {game_id}")

        def close(self):
            opened.append("closed")

    def _from_url(*_a, **_k):
        opened.append("redis")
        return redis_client

    class _Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return OBSERVED_AT.astimezone(tz)

    monkeypatch.setattr(rlw.settings, "live_game_worker_enabled", True)
    monkeypatch.setattr(rlw.settings, "redis_url", "redis://fake-not-connected")
    monkeypatch.setattr(rlw.settings, "live_game_postseason_kinds", kinds_setting)
    monkeypatch.setattr(rlw.redis.Redis, "from_url", staticmethod(_from_url))
    monkeypatch.setattr(rlw, "StatsLiveSource", _FakeStatsSource)
    monkeypatch.setattr(rlw, "datetime", _Clock)
    monkeypatch.setattr(rlw.signal, "signal", lambda *_a: None)
    rlw.main(["--once"])
    return calls, redis_client, opened


def test_worker_cli_default_setting_is_a_only(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    """反例（預設）：正式入口未設定時只抓 A，E 即使官方有列也不會有 snapshot。"""
    calls, redis_client, _ = _run_worker_cli(monkeypatch, "", {"E": _recorded_e_schedule()})

    assert calls == [(2026, 10, "A")]
    assert "cpbl:live:2026:E:1" not in redis_client.store
    out = json.loads(capsys.readouterr().out)
    assert "schedule_errors" not in out


def test_worker_cli_opt_in_passes_e_c_through_to_cache(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    calls, redis_client, _ = _run_worker_cli(monkeypatch, "E,C", {"E": _recorded_e_schedule()[:1], "C": []})

    assert calls == [(2026, 10, "A"), (2026, 10, "E"), (2026, 10, "C"), ("game", "2026-E-1")]
    snap = json.loads(redis_client.store["cpbl:live:2026:E:1"])
    assert (snap["phase"], snap["kind_code"], snap["home"]["score"]) == ("live", "E", 3)
    assert snap["decisions"]["winning_pitcher"] is None
    assert not any(key.startswith("cpbl:live:2026:C:") for key in redis_client.store)
    assert "cpbl:live:lock" not in redis_client.store, "lock 須釋放"
    out = json.loads(capsys.readouterr().out)
    assert out["schedule_errors"] == [] and out["cached"] == 1


def test_worker_cli_bad_setting_fails_before_opening_connections(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValueError):
        _run_worker_cli(monkeypatch, "A,E", {})


# ═══════════════════════ /live：DB 無列＋E snapshot（gap report 缺口） ═══════════════════════


class _NoRowsCursor:
    description: list = []

    def execute(self, *_a, **_k):
        return self

    def fetchall(self):
        return []

    def fetchone(self):
        return (False,)


class _NoRowsConn:
    def cursor(self):
        return _NoRowsCursor()


def test_live_endpoint_returns_e_snapshot_when_games_table_has_no_row(monkeypatch: pytest.MonkeyPatch) -> None:
    """producer→API 銜接：cpbl.games 無 2026-E-1 列時 /live 仍回 snapshot（game=null）。

    只證後端回應；前端 applyLiveSnapshot 由 game=null 合成 game 的頁面殼層不在本測試。
    pitcher_decisions／pitch_type_live 以替身隔離（它們各自查 DB／模型樣本，非本缺口）。
    """
    from contextlib import contextmanager

    from cpbl.api import live_cache
    from cpbl.api.routers import games

    @contextmanager
    def _conn():
        yield _NoRowsConn()

    snap = live_cache.public_snapshot(
        build_snapshot(_e1_detail("START"), fetched_at=OBSERVED_AT),
        now=OBSERVED_AT + timedelta(seconds=5), live_stale_after_seconds=45,
    )
    monkeypatch.setattr(games, "conn", _conn)
    monkeypatch.setattr(games, "get_public_live_snapshot",
                        lambda year, kind, sno: snap if (year, kind, sno) == (2026, "E", 1) else None)
    monkeypatch.setattr(games.pitcher_decisions, "game_decisions", lambda *_a: {})
    monkeypatch.setattr(games.pitch_type_live, "annotate", lambda s, _y: s)

    body = games.game_live(1, season=2026, kind_code="E")

    assert body["game"] is None
    live = body["live_snapshot"]
    assert (live["game_id"], live["phase"], live["freshness"]) == ("2026-E-1", "live", "fresh")
    assert (live["away"]["score"], live["home"]["score"], live["inning"]) == (0, 3, 5)
    assert live["decisions"]["winning_pitcher"] is None
    assert games.game_live(1, season=2026, kind_code="A")["live_snapshot"] is None


def test_observed_at_constant_matches_recorded_utc() -> None:
    """釘住轉錄時刻：18:20:52+08 = 10:20:52Z（避免日後改 TZ 讓觀測窗測試靜默換義）。"""
    assert OBSERVED_AT.astimezone(UTC) == datetime(2026, 10, 9, 10, 20, 52, tzinfo=UTC)
