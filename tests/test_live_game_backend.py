from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from cpbl.ingest.live_game_worker import (
    LiveGameWorker,
    RedisLiveGameCache,
    StatsLiveSource,
    build_snapshot,
    next_delay_seconds,
    poll_interval_seconds,
)

T0 = datetime(2026, 7, 28, 17, 0, tzinfo=UTC)


def _team(name: str, *, score: int = 0, hitters: list[dict] | None = None,
          pitchers: list[dict] | None = None) -> dict:
    return {
        "Team": {"Code": name[:3], "Name": name},
        "Score": score,
        "Hitters": hitters or [],
        "Pitchers": pitchers or [],
        "InningScore": [],
    }


def _game(status: str, *, away: dict | None = None, home: dict | None = None,
          livelog: list[dict] | None = None) -> dict:
    return {
        "GameId": "2026-A-226",
        "GameSno": 226,
        "KindCode": "A",
        "GameStatus": status,
        "PreExeDate": "2026-07-28T18:35:00",
        "InningSeq": 1,
        "VisitingHomeType": 1,
        "Visiting": away or _team("味全龍"),
        "Home": home or _team("富邦悍將"),
        "LiveLog": livelog or [],
    }


def _starter(acnt: str, name: str) -> dict:
    return {"PitcherAcnt": acnt, "PitcherName": name, "RoleType": "先發"}


def _hitter(lineup: int, name: str) -> dict:
    return {
        "HitterAcnt": f"h{lineup}",
        "HitterName": name,
        "Lineup": lineup,
        "DefendStation": "CF",
    }


def test_scheduled_empty_payload_does_not_infer_announcements_from_clock() -> None:
    snapshot = build_snapshot(_game("SCHEDULED"), fetched_at=T0)

    assert snapshot["phase"] == "scheduled"
    assert snapshot["away"]["probable_pitcher"]["availability"] == "not_announced"
    assert snapshot["home"]["lineup"]["availability"] == "not_announced"
    assert snapshot["tracking_availability"] == "not_announced"


def test_lineup_is_independent_per_team_without_inventing_probable_pitcher() -> None:
    away = _team(
        "味全龍",
        pitchers=[_starter("p1", "伍鐸")],
        hitters=[_hitter(i, f"客隊打者{i}") for i in range(1, 10)],
    )
    home = _team("富邦悍將", hitters=[_hitter(1, "主隊第一棒")])

    snapshot = build_snapshot(_game("SCHEDULED", away=away, home=home), fetched_at=T0)

    assert snapshot["phase"] == "lineup_announced"
    assert snapshot["away"]["pitchers"] == [_starter("p1", "伍鐸")]
    assert snapshot["away"]["probable_pitcher"]["availability"] == "not_announced"
    assert snapshot["away"]["lineup"]["availability"] == "announced"
    assert len(snapshot["away"]["lineup"]["items"]) == 9
    assert snapshot["home"]["probable_pitcher"]["availability"] == "not_announced"
    assert snapshot["home"]["lineup"]["availability"] == "partial"


def test_start_zero_zero_is_live_and_zero_trackman_is_pending_not_no_equipment() -> None:
    livelog = [{
        "PitchCnt": 1,
        "PitcherAcnt": "p1",
        "HitterAcnt": "h1",
        "Content": "好球沒揮棒。",
        "Trackman": None,
    }]

    snapshot = build_snapshot(_game("START", livelog=livelog), fetched_at=T0)

    assert snapshot["phase"] == "live"
    assert snapshot["away"]["score"] == 0
    assert snapshot["home"]["score"] == 0
    assert snapshot["event_count"] == 1
    assert snapshot["tracking_availability"] == "pending"


def test_started_box_pitcher_is_not_mislabeled_as_probable_pitcher() -> None:
    """A-226～228 證實 Pitchers[] 只在 START 後出現，不能倒推成賽前公告。"""
    away = _team("味全龍", pitchers=[_starter("p1", "伍鐸")])

    snapshot = build_snapshot(_game("START", away=away), fetched_at=T0)

    assert snapshot["phase"] == "live"
    assert snapshot["away"]["pitchers"][0]["RoleType"] == "先發"
    assert snapshot["away"]["probable_pitcher"] == {
        "availability": "not_announced",
        "player_id": None,
        "name": None,
        "first_observed_at": None,
    }


def test_livelog_event_count_cannot_regress_below_last_known_good() -> None:
    previous = build_snapshot(
        _game("START", livelog=[{"PitchCnt": 1}, {"PitchCnt": 2}]),
        fetched_at=T0,
    )

    with pytest.raises(ValueError, match="LiveLog regressed from 2 to 1"):
        build_snapshot(
            _game("START", livelog=[{"PitchCnt": 1}]),
            fetched_at=datetime(2026, 7, 28, 17, 0, 12, tzinfo=UTC),
            previous=previous,
        )


@pytest.mark.parametrize("raw_status", ["SUSPENDED", "RESERVED", None])
def test_live_livelog_cannot_regress_when_source_leaves_live_phase(
    raw_status: str | None,
) -> None:
    previous = build_snapshot(
        _game("START", livelog=[{"PitchCnt": 1}, {"PitchCnt": 2}]),
        fetched_at=T0,
    )
    current = _game(raw_status or "START")
    if raw_status is None:
        current.pop("GameStatus")

    with pytest.raises(ValueError, match="LiveLog regressed from 2 to 0"):
        build_snapshot(
            current,
            fetched_at=datetime(2026, 7, 28, 17, 0, 12, tzinfo=UTC),
            previous=previous,
        )


def test_finished_trackman_is_available_and_unknown_status_fails_closed() -> None:
    tracked = [{
        "PitchCnt": 1,
        "PitcherAcnt": "p1",
        "Trackman": {"Pitch": {"Release": {"RelSpeed": 150.0}}},
    }]
    finished = build_snapshot(_game("FINISHED", livelog=tracked), fetched_at=T0)
    unknown = build_snapshot(_game("SUSPENDED"), fetched_at=T0)

    assert finished["phase"] == "final"
    assert finished["tracking_availability"] == "available"
    assert "Trackman" not in finished["livelog"][0]
    assert unknown["phase"] == "unknown"
    assert unknown["raw_status"] == "SUSPENDED"


def test_lineup_first_observed_time_survives_later_snapshots() -> None:
    away = _team("味全龍", hitters=[_hitter(1, "客隊第一棒")])
    first = build_snapshot(_game("SCHEDULED", away=away), fetched_at=T0)
    later = build_snapshot(
        _game("SCHEDULED", away=away),
        fetched_at=datetime(2026, 7, 28, 17, 10, tzinfo=UTC),
        previous=first,
    )

    assert later["away"]["lineup"]["first_observed_at"] == T0.isoformat()
    assert later["source"]["fetched_at"] != T0.isoformat()


# ── 官方既有欄位保留（LIVE-SNAPSHOT-FIELDS1）────────────────────────────────
# fixture 是生產真實 payload，不是手寫 mock。父卡與 FIX1 的漏網全出於手寫 mock 比
# 真實資料更完整／更乾淨（自行補 ErrorCnt、把 RunBattedINCnt 拼成 RunBattedIncnt），
# 等於用對契約的想像驗證對契約的實作。

_FIXTURE = Path(__file__).parent / "fixtures" / "stats_game_2026-A-234.json"


def _real_game() -> dict:
    return json.loads(_FIXTURE.read_text(encoding="utf-8"))


def test_team_hits_and_errors_come_from_official_team_level_fields() -> None:
    """記分板 E 曾恆為 0；官方 Home.ErrorCnt=1，snapshot 必須帶出真值。"""
    snapshot = build_snapshot(_real_game(), fetched_at=T0)

    assert snapshot["away"]["hits"] == 7
    assert snapshot["away"]["errors"] == 0
    assert snapshot["home"]["hits"] == 7
    assert snapshot["home"]["errors"] == 1
    # 逐局 H/E 只有主站 box/getlive 有；stats 的 InningScore 僅 {Seq, Score}，
    # 不得由總計回填成逐局值。
    assert all(set(row) <= {"Seq", "Score"} for row in snapshot["home"]["inning_score"])


def test_decisions_and_game_facts_are_preserved_from_official_payload() -> None:
    snapshot = build_snapshot(_real_game(), fetched_at=T0)
    decisions = snapshot["decisions"]

    assert decisions["winning_pitcher"] == {"player_id": "0000006906", "name": "艾菩樂"}
    assert decisions["losing_pitcher"] == {"player_id": "0000005731", "name": "布雷克"}
    assert decisions["closer"] == {"player_id": "0000000941", "name": "陳冠宇"}
    assert decisions["mvp"]["yearly_count"] == 1
    assert snapshot["venue"] == "亞太主"
    assert [u["name"] for u in snapshot["umpires"]][:2] == ["劉世偉", "王俊宏"]
    # 官方權威旗標，取代由 tracking_count 推測球場有無設備。
    assert snapshot["skip_trackman"] is False
    assert snapshot["home"]["record"] == {"w": 8, "l": 9, "t": 0}


def test_missing_team_and_decision_fields_stay_none_instead_of_zero() -> None:
    """缺資料與「值為零」必須可區分，否則記分板會把未知寫成 0。"""
    snapshot = build_snapshot(_game("SCHEDULED"), fetched_at=T0)

    assert snapshot["away"]["hits"] is None
    assert snapshot["away"]["errors"] is None
    assert snapshot["away"]["record"] == {"w": None, "l": None, "t": None}
    assert snapshot["decisions"] == {
        "winning_pitcher": None, "losing_pitcher": None, "closer": None, "mvp": None,
    }
    assert snapshot["venue"] is None
    assert snapshot["umpires"] == []
    assert snapshot["skip_trackman"] is None


def test_batter_aliases_all_resolve_against_the_real_payload() -> None:
    """alias 必須對得上真實欄位；拼錯不得再靜默通過（打點／觸身／盜壘曾整欄空白）。

    前端 snake() 的等價實作——與 web/src/lib/live-game.ts 同一套規則。
    """
    def snake(key: str) -> str:
        key = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", key)
        key = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", key)
        return key.lower()

    game = _real_game()
    produced = {snake(k) for side in ("Visiting", "Home")
                for row in game[side]["Hitters"] for k in row}
    # stats 站實際供應這些欄位，前端 alias 的 key 必須落在其中
    for key in ("run_batted_in_cnt", "hit_by_pitch_cnt", "steal_base_ok_cnt",
                "hitting_cnt", "hit_cnt", "score_cnt"):
        assert key in produced, f"{key} 不在真實 payload 中"
    # 這三個是主站 box/getlive 專有，stats 站永遠不會有 —— 賽中算不出滿貫／致勝打點
    for key in ("grand_slam_homerun_cnt", "game_winning_rbi_cnt", "hitter_uniform_no"):
        assert key not in produced


class _Cache:
    def __init__(self, *, lock: bool = True, killed: bool = False) -> None:
        self.lock = lock
        self.killed = killed
        self.released = 0
        self.items: dict[tuple[int, str, int], dict] = {}
        self.source_errors: list[tuple[int, str, int, str, str]] = []

    def acquire_lock(self) -> bool:
        return self.lock

    def is_killed(self) -> bool:
        return self.killed

    def release_lock(self) -> None:
        self.released += 1

    def get_snapshot(self, year: int, kind: str, sno: int) -> dict | None:
        return self.items.get((year, kind, sno))

    def set_snapshot(self, snapshot: dict) -> None:
        game_id = snapshot["game_id"].split("-")
        self.items[(int(game_id[0]), game_id[1], int(game_id[2]))] = snapshot

    def record_source_error(self, year: int, kind: str, sno: int, *,
                            observed_at: datetime, error_type: str) -> None:
        self.source_errors.append((year, kind, sno, observed_at.isoformat(), error_type))


def _schedule(game_id: str, status: str, starts_at: str) -> dict:
    year, kind, sno = game_id.split("-")
    return {
        "GameId": game_id,
        "GameSno": int(sno),
        "KindCode": kind,
        "GameStatus": status,
        "PreExeDate": starts_at,
        "Year": int(year),
    }


def test_worker_respects_disable_and_distributed_lock() -> None:
    calls: list[str] = []
    disabled = LiveGameWorker(
        cache=_Cache(),
        fetch_schedule=lambda *_: calls.append("schedule") or [],
        fetch_game=lambda game_id: calls.append(game_id) or {},
        enabled=False,
    )
    locked = LiveGameWorker(
        cache=_Cache(lock=False),
        fetch_schedule=lambda *_: calls.append("schedule") or [],
        fetch_game=lambda game_id: calls.append(game_id) or {},
    )
    killed = LiveGameWorker(
        cache=_Cache(killed=True),
        fetch_schedule=lambda *_: calls.append("schedule") or [],
        fetch_game=lambda game_id: calls.append(game_id) or {},
    )

    assert disabled.run_cycle(datetime(2026, 7, 28, 8, 0, tzinfo=UTC))["state"] == "disabled"
    assert locked.run_cycle(datetime(2026, 7, 28, 8, 0, tzinfo=UTC))["state"] == "locked"
    assert killed.run_cycle(datetime(2026, 7, 28, 8, 0, tzinfo=UTC))["state"] == "killed"
    assert calls == []


def test_worker_caches_only_observation_window_and_never_overwrites_on_error() -> None:
    now = datetime(2026, 7, 28, 8, 0, tzinfo=UTC)  # 台北 16:00
    rows = [
        _schedule("2026-A-226", "SCHEDULED", "2026-07-28T18:35:00"),
        _schedule("2026-A-227", "SCHEDULED", "2026-07-30T18:35:00"),
        _schedule("2026-A-228", "POSTPONED", "2026-07-28T18:35:00"),
    ]
    cache = _Cache()
    old = build_snapshot(_game("SCHEDULED"), fetched_at=T0)
    old["game_id"] = "2026-A-226"
    cache.set_snapshot(old)

    def fetch_game(game_id: str) -> dict:
        if game_id == "2026-A-226":
            raise httpx.ReadTimeout("source timeout")
        if game_id == "2026-A-228":
            game = _game("POSTPONED")
            game["GameId"] = game_id
            game["GameSno"] = 228
            return game
        raise AssertionError(f"unexpected fetch {game_id}")

    worker = LiveGameWorker(
        cache=cache,
        fetch_schedule=lambda year, month: rows,
        fetch_game=fetch_game,
    )

    result = worker.run_cycle(now)

    assert result["state"] == "ok"
    assert result["selected"] == 2
    assert result["errors"] == 1
    assert result["cached"] == 1
    assert cache.get_snapshot(2026, "A", 226) == old
    assert cache.source_errors == [
        (2026, "A", 226, now.isoformat(), "ReadTimeout"),
    ]
    assert cache.get_snapshot(2026, "A", 228)["phase"] == "postponed"
    assert cache.released == 1


def test_worker_updates_snapshot_and_preserves_first_observed() -> None:
    now = datetime(2026, 7, 28, 8, 0, tzinfo=UTC)
    cache = _Cache()
    away = _team("味全龍", pitchers=[_starter("p1", "伍鐸")])
    first = build_snapshot(_game("SCHEDULED", away=away), fetched_at=T0)
    cache.set_snapshot(first)
    row = _schedule("2026-A-226", "START", "2026-07-28T18:35:00")

    worker = LiveGameWorker(
        cache=cache,
        fetch_schedule=lambda year, month: [row],
        fetch_game=lambda game_id: _game("START", away=away),
    )

    result = worker.run_cycle(now)
    current = cache.get_snapshot(2026, "A", 226)

    assert result["cached"] == 1
    assert result["phases"] == {"live": 1}
    assert result["games"] == [{
        "game_id": "2026-A-226",
        "phase": "live",
        "raw_status": "START",
        "away_probable": "not_announced",
        "home_probable": "not_announced",
        "away_lineup": "not_announced",
        "home_lineup": "not_announced",
        "event_count": 0,
        "tracking_count": 0,
    }]
    assert current["phase"] == "live"
    assert current["away"]["probable_pitcher"]["first_observed_at"] is None
    assert cache.released == 1


def test_worker_keeps_last_known_good_when_livelog_temporarily_regresses() -> None:
    now = datetime(2026, 7, 28, 10, 0, tzinfo=UTC)
    cache = _Cache()
    previous = build_snapshot(
        _game("START", livelog=[{"PitchCnt": 1}, {"PitchCnt": 2}]),
        fetched_at=T0,
    )
    cache.set_snapshot(previous)

    worker = LiveGameWorker(
        cache=cache,
        fetch_schedule=lambda *_: [
            _schedule("2026-A-226", "START", "2026-07-28T18:35:00"),
        ],
        fetch_game=lambda _game_id: _game("START", livelog=[{"PitchCnt": 1}]),
    )

    result = worker.run_cycle(now)

    assert result["cached"] == 0
    assert result["errors"] == 1
    assert cache.get_snapshot(2026, "A", 226) == previous


def test_worker_does_not_refetch_game_after_final_snapshot_is_cached() -> None:
    now = datetime(2026, 7, 28, 14, 0, tzinfo=UTC)
    cache = _Cache()
    final = build_snapshot(_game("FINISHED"), fetched_at=T0)
    cache.set_snapshot(final)
    fetched: list[str] = []

    worker = LiveGameWorker(
        cache=cache,
        fetch_schedule=lambda *_: [
            _schedule("2026-A-226", "FINISHED", "2026-07-28T18:35:00"),
        ],
        fetch_game=lambda game_id: fetched.append(game_id) or _game("FINISHED"),
    )

    result = worker.run_cycle(now)

    assert fetched == []
    assert result["cached"] == 0
    assert result["skipped_final"] == 1
    assert cache.get_snapshot(2026, "A", 226) == final


def test_poll_interval_is_adaptive_but_bounded() -> None:
    now = datetime(2026, 7, 28, 8, 0, tzinfo=UTC)

    assert poll_interval_seconds(now=now, phases={"live"}, next_start=None) == 12
    assert poll_interval_seconds(
        now=now, phases={"scheduled"},
        next_start=datetime(2026, 7, 28, 9, 0, tzinfo=UTC),
    ) == 60
    assert poll_interval_seconds(
        now=now, phases={"scheduled"},
        next_start=datetime(2026, 7, 29, 8, 0, tzinfo=UTC),
    ) == 600
    assert poll_interval_seconds(now=now, phases=set(), next_start=None) == 1800


class _Redis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.set_calls: list[tuple[str, int | None, bool]] = []
        self.eval_calls: list[tuple[str, str]] = []

    def set(self, key: str, value: str, *, ex: int | None = None, nx: bool = False):
        self.set_calls.append((key, ex, nx))
        if nx and key in self.values:
            return False
        self.values[key] = value
        return True

    def get(self, key: str):
        return self.values.get(key)

    def delete(self, key: str):
        return self.values.pop(key, None) is not None

    def eval(self, script: str, numkeys: int, key: str, token: str):
        self.eval_calls.append((key, token))
        if self.values.get(key) == token:
            del self.values[key]
            return 1
        return 0


def test_redis_cache_uses_ttl_and_token_checked_lock_release() -> None:
    client = _Redis()
    cache = RedisLiveGameCache(client, prefix="test:live", snapshot_ttl_seconds=120,
                               lock_ttl_seconds=45, token_factory=lambda: "owner-1")
    snapshot = build_snapshot(_game("START"), fetched_at=T0)

    assert cache.acquire_lock() is True
    assert cache.acquire_lock() is False
    cache.set_snapshot(snapshot)
    assert cache.get_snapshot(2026, "A", 226)["phase"] == "live"
    assert ("test:live:2026:A:226", 120, False) in client.set_calls

    cache.release_lock()
    assert client.eval_calls == [("test:live:lock", "owner-1")]
    assert "test:live:lock" not in client.values

    client.values["test:live:kill"] = "1"
    assert cache.is_killed() is True


def test_redis_cache_tracks_source_error_without_discarding_last_success() -> None:
    client = _Redis()
    cache = RedisLiveGameCache(client, prefix="test:live")
    snapshot = build_snapshot(
        _game("START", livelog=[{"PitchCnt": 1}]),
        fetched_at=T0,
    )
    cache.set_snapshot(snapshot)

    cache.record_source_error(
        2026, "A", 226,
        observed_at=datetime(2026, 7, 28, 17, 0, 12, tzinfo=UTC),
        error_type="ReadTimeout",
    )

    failed = cache.get_snapshot(2026, "A", 226)
    assert failed["event_count"] == 1
    assert failed["source"]["last_error_type"] == "ReadTimeout"
    assert failed["source"]["last_error_at"] == "2026-07-28T17:00:12+00:00"

    cache.set_snapshot(snapshot)
    assert "last_error_at" not in cache.get_snapshot(2026, "A", 226)["source"]


def test_stats_source_uses_only_verified_stats_endpoints() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/games/schedule"):
            return httpx.Response(200, json={"Data": {"Games": [{"GameId": "2026-A-226"}]}})
        return httpx.Response(200, json={"Data": {"Game": _game("START")}})

    source = StatsLiveSource(client=httpx.Client(transport=httpx.MockTransport(handler)))
    try:
        schedule = source.fetch_schedule(2026, 7)
        game = source.fetch_game("2026-A-226")
    finally:
        source.close()

    assert schedule == [{"GameId": "2026-A-226"}]
    assert game["GameStatus"] == "START"
    assert requests[0].url.host == "stats.cpbl.com.tw"
    assert str(requests[0].url.params) == "kindCode=A&year=2026&month=7"
    assert requests[1].url.path == "/api/proxy/v1/games/2026-A-226"


def test_loop_delay_has_bounded_jitter_and_exponential_backoff() -> None:
    assert next_delay_seconds({"state": "ok", "next_poll_seconds": 60}, failures=0,
                              jitter=lambda: 0.9) == 54
    assert next_delay_seconds({"state": "ok", "next_poll_seconds": 60}, failures=0,
                              jitter=lambda: 1.1) == 66
    assert next_delay_seconds({"state": "locked"}, failures=0, jitter=lambda: 1.0) == 5
    assert next_delay_seconds({"state": "error"}, failures=1, jitter=lambda: 1.0) == 5
    assert next_delay_seconds({"state": "error"}, failures=8, jitter=lambda: 1.0) == 300


def test_cached_snapshot_is_json_not_pickle() -> None:
    client = _Redis()
    cache = RedisLiveGameCache(client, prefix="test:live")
    cache.set_snapshot(build_snapshot(_game("START"), fetched_at=T0))

    raw = client.values["test:live:2026:A:226"]
    assert json.loads(raw)["raw_status"] == "START"
