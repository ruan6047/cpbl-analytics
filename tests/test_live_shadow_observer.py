"""OPS-LIVE-SHADOW1：隔離 observer 的安全與可重驗證據契約。"""

from __future__ import annotations

import gzip
import json
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest

from cpbl.ingest.live_shadow_observer import (
    ALLOWED_GAME_IDS,
    BudgetExceeded,
    DiskGateClosed,
    EvidenceStore,
    Observer,
    ObserverConfig,
    PersistentBudget,
    bounded_sleep_seconds,
    build_game_url,
    build_schedule_url,
    validate_target_url,
)

NOW = datetime(2026, 7, 26, 12, 0, tzinfo=UTC)


class FakeResponse:
    def __init__(self, status_code: int, body: bytes, headers: dict[str, str] | None = None):
        self.status_code = status_code
        self.content = body
        self.headers = headers or {}


class FakeClient:
    def __init__(self, outcomes: list[FakeResponse | Exception]):
        self.outcomes = list(outcomes)
        self.urls: list[str] = []

    def get(self, url: str):
        self.urls.append(url)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def config(tmp_path: Path, **overrides) -> ObserverConfig:
    values = {
        "evidence_dir": tmp_path,
        "stop_at": datetime(2026, 7, 30, 0, 0, tzinfo=timezone(timedelta(hours=8))),
        "min_free_bytes": 0,
        "min_free_ratio": 0,
        "max_evidence_bytes": 1024 * 1024,
    }
    values.update(overrides)
    return ObserverConfig(**values)


def test_url_allowlist_accepts_only_fixed_schedule_and_three_games(tmp_path: Path):
    cfg = config(tmp_path)

    schedule = build_schedule_url(cfg)
    assert validate_target_url(schedule, cfg) == "schedule"
    assert ALLOWED_GAME_IDS == ("2026-A-226", "2026-A-227", "2026-A-228")
    for game_id in ALLOWED_GAME_IDS:
        assert validate_target_url(build_game_url(game_id, cfg), cfg) == f"game:{game_id}"

    rejected = [
        "http://stats.cpbl.com.tw/api/proxy/v1/games/2026-A-226",
        "https://stats.cpbl.com.tw.evil.test/api/proxy/v1/games/2026-A-226",
        "https://stats.cpbl.com.tw/api/proxy/v1/games/2026-A-229",
        "https://stats.cpbl.com.tw/api/proxy/v1/games/2026-A-226?next=https://evil.test",
        "https://www.cpbl.com.tw/api/proxy/v1/games/2026-A-226",
        "https://stats.cpbl.com.tw/api/proxy/v1/games/schedule?kindCode=A&year=2026&month=8",
    ]
    for url in rejected:
        with pytest.raises(ValueError):
            validate_target_url(url, cfg)


def test_budget_persists_total_and_enforces_per_game_and_global_minute(tmp_path: Path):
    cfg = config(tmp_path, max_total_attempts=5, max_attempts_per_minute=3,
                 max_attempts_per_game_per_minute=2)
    budget = PersistentBudget(cfg)

    budget.consume("game:2026-A-226", NOW)
    budget.consume("game:2026-A-226", NOW + timedelta(seconds=1))
    with pytest.raises(BudgetExceeded, match="per-game"):
        budget.consume("game:2026-A-226", NOW + timedelta(seconds=2))

    budget.consume("game:2026-A-227", NOW + timedelta(seconds=3))
    with pytest.raises(BudgetExceeded, match="global-minute"):
        budget.consume("game:2026-A-228", NOW + timedelta(seconds=4))

    restarted = PersistentBudget(cfg)
    restarted.consume("game:2026-A-228", NOW + timedelta(seconds=61))
    restarted.consume("schedule", NOW + timedelta(seconds=62))
    with pytest.raises(BudgetExceeded, match="total"):
        restarted.consume("schedule", NOW + timedelta(seconds=63))


def test_budget_counts_failed_attempt_before_network_result(tmp_path: Path):
    cfg = config(tmp_path, max_total_attempts=1)
    client = FakeClient([httpx.ReadTimeout("slow"), FakeResponse(200, b"{}")])
    observer = Observer(cfg, client=client, sleep=lambda _: None)

    observer.observe(build_schedule_url(cfg), now=lambda: NOW)

    assert len(client.urls) == 1
    assert PersistentBudget(cfg).total_attempts == 1
    error_entry = json.loads(cfg.manifest_path.read_text().strip())
    assert error_entry["event_type"] == "network_error"
    assert error_entry["error_type"] == "ReadTimeout"


def test_deadline_and_stop_file_prevent_any_network_request(tmp_path: Path):
    cfg = config(tmp_path)
    client = FakeClient([FakeResponse(200, b"{}")])
    observer = Observer(cfg, client=client, sleep=lambda _: None)

    assert observer.run_cycle(now=lambda: cfg.stop_at.astimezone(UTC)) == "deadline"
    assert client.urls == []

    cfg.stop_path.touch()
    assert observer.run_cycle(now=lambda: NOW) == "kill-switch"
    assert client.urls == []


def test_idle_sleep_is_capped_at_hard_deadline(tmp_path: Path):
    cfg = config(tmp_path)
    almost_deadline = cfg.stop_at.astimezone(UTC) - timedelta(seconds=7)

    assert bounded_sleep_seconds(almost_deadline, 1800, cfg.stop_at) == 7
    assert bounded_sleep_seconds(cfg.stop_at.astimezone(UTC), 1800, cfg.stop_at) == 0


def test_shutdown_signal_prevents_network_and_cleanly_terminates_cycle(tmp_path: Path):
    cfg = config(tmp_path)
    client = FakeClient([FakeResponse(200, b"{}")])
    observer = Observer(
        cfg,
        client=client,
        sleep=lambda _: None,
        shutdown_requested=lambda: True,
    )

    assert observer.run_cycle(now=lambda: NOW) == "signal"
    assert client.urls == []
    marker = json.loads((tmp_path / "termination-signal.json").read_text())
    assert marker["reason"] == "signal"

def test_evidence_is_atomic_gzip_and_manifest_can_rebuild_raw_body(tmp_path: Path):
    cfg = config(tmp_path)
    store = EvidenceStore(cfg)
    raw = b'{"Data":{"Game":{"GameStatus":"START","Hitters":[]}}}'

    entry = store.write_response(
        template_id="game:2026-A-226",
        game_id="2026-A-226",
        status_code=200,
        latency_ms=123,
        body=raw,
        observed_at=NOW,
        monotonic_elapsed=1.25,
    )

    evidence_path = tmp_path / entry["gzip_path"]
    envelope = json.loads(gzip.decompress(evidence_path.read_bytes()))
    assert envelope["manifest_entry"]["sequence"] == 1
    assert bytes.fromhex(envelope["raw_body_hex"]) == raw
    assert envelope["manifest_entry"]["gzip_size"] == evidence_path.stat().st_size
    assert entry["raw_sha256"]
    assert entry["raw_status"] == "START"
    assert entry["key_paths"]["Data.Game.Hitters"] == {"present": True, "count": 0}
    assert not list(tmp_path.rglob("*.tmp"))
    assert json.loads(cfg.manifest_path.read_text().strip())["sequence"] == 1


def test_structural_paths_preserve_actual_per_team_partial_shape(tmp_path: Path):
    cfg = config(tmp_path)
    body = (
        b'{"Data":{"Game":{"GameStatus":"SCHEDULED",'
        b'"Home":{"Hitters":[{"Acnt":"H1"}],"Pitchers":[]},'
        b'"Visiting":{"Hitters":[],"Pitchers":[{"Acnt":"P1"}]}}}}'
    )
    entry = EvidenceStore(cfg).write_response(
        "game:2026-A-226", "2026-A-226", 200, 1, body, NOW, 1
    )

    assert entry["key_paths"]["Data.Game.Home.Hitters"]["count"] == 1
    assert entry["key_paths"]["Data.Game.Home.Pitchers"]["count"] == 0
    assert entry["key_paths"]["Data.Game.Visiting.Hitters"]["count"] == 0
    assert entry["key_paths"]["Data.Game.Visiting.Pitchers"]["count"] == 1


def test_crash_after_raw_rename_recovers_orphan_without_sequence_regression(tmp_path: Path):
    cfg = config(tmp_path)
    store = EvidenceStore(cfg)

    with pytest.raises(RuntimeError, match="simulated-crash"):
        store.write_response(
            template_id="game:2026-A-226",
            game_id="2026-A-226",
            status_code=200,
            latency_ms=10,
            body=b'{"Data":{"Game":{"GameStatus":"SCHEDULED"}}}',
            observed_at=NOW,
            monotonic_elapsed=1,
            after_rename=lambda: (_ for _ in ()).throw(RuntimeError("simulated-crash")),
        )

    assert not cfg.manifest_path.exists()
    recovered = EvidenceStore(cfg)
    assert recovered.recover_orphans() == 1
    first = json.loads(cfg.manifest_path.read_text().strip())
    assert first["sequence"] == 1
    assert first["recovered_after_crash"] is True

    second = recovered.write_response(
        template_id="game:2026-A-227",
        game_id="2026-A-227",
        status_code=200,
        latency_ms=11,
        body=b'{"Data":{"Game":{"GameStatus":"START"}}}',
        observed_at=NOW + timedelta(seconds=1),
        monotonic_elapsed=2,
    )
    assert second["sequence"] == 2
    assert [json.loads(line)["sequence"] for line in cfg.manifest_path.read_text().splitlines()] == [1, 2]


def test_corrupt_orphan_fails_closed_instead_of_advancing_manifest(tmp_path: Path):
    cfg = config(tmp_path)
    store = EvidenceStore(cfg)
    raw_dir = cfg.raw_dir
    raw_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / "000000000001-deadbeef.json.gz").write_bytes(b"not-gzip")

    with pytest.raises(ValueError, match="corrupt orphan"):
        store.recover_orphans()
    assert not cfg.manifest_path.exists()


def test_disk_gate_closes_on_free_space_or_application_ceiling(tmp_path: Path):
    cfg = config(tmp_path, min_free_bytes=100, min_free_ratio=0.10, max_evidence_bytes=10)
    store = EvidenceStore(cfg, disk_usage=lambda _: (1000, 950, 50))
    with pytest.raises(DiskGateClosed, match="free-space"):
        store.ensure_capacity(1)

    store = EvidenceStore(cfg, disk_usage=lambda _: (1000, 100, 900))
    with pytest.raises(DiskGateClosed, match="evidence-ceiling"):
        store.ensure_capacity(11)


def test_redirect_is_recorded_but_never_followed_or_retried(tmp_path: Path):
    cfg = config(tmp_path)
    client = FakeClient([FakeResponse(302, b"redirect", {"location": "https://evil.test"})])
    observer = Observer(cfg, client=client, sleep=lambda _: None)

    result = observer.observe(build_game_url("2026-A-226", cfg), now=lambda: NOW)

    assert result["status_code"] == 302
    assert result["retry_after_seconds"] is None
    assert len(client.urls) == 1


def test_429_honors_retry_after_without_same_cycle_retry(tmp_path: Path):
    cfg = config(tmp_path)
    client = FakeClient([FakeResponse(429, b"busy", {"retry-after": "120"}), FakeResponse(200, b"{}")])
    observer = Observer(cfg, client=client, sleep=lambda _: None)

    result = observer.observe(build_schedule_url(cfg), now=lambda: NOW)

    assert result["retry_after_seconds"] == 120
    assert len(client.urls) == 1


def test_429_blocks_following_cycle_until_retry_after(tmp_path: Path):
    cfg = config(tmp_path)
    client = FakeClient([
        FakeResponse(429, b"busy", {"retry-after": "120"}),
        FakeResponse(200, b"{}"),
        FakeResponse(200, b"{}"),
        FakeResponse(200, b"{}"),
    ])
    observer = Observer(cfg, client=client, sleep=lambda _: None)

    assert observer.run_cycle(now=lambda: NOW) == "ok"
    assert len(client.urls) == 4
    assert observer.run_cycle(now=lambda: NOW + timedelta(seconds=30)) == "ok"
    assert len(client.urls) == 4


def test_start_raw_status_selects_twelve_second_interval_without_time_inference(tmp_path: Path):
    cfg = config(tmp_path)
    start = b'{"Data":{"Game":{"GameStatus":"START","PreExeDate":"2026-07-28T18:35:00+08:00"}}}'
    client = FakeClient([
        FakeResponse(200, b'{"Data":{"Games":[]}}'),
        FakeResponse(200, start),
        FakeResponse(200, start),
        FakeResponse(200, start),
    ])
    observer = Observer(cfg, client=client, sleep=lambda _: None)

    assert observer.run_cycle(now=lambda: NOW) == "ok"
    assert observer.next_interval_seconds == 12


def test_finished_games_are_persisted_and_skipped_from_next_cycle(tmp_path: Path):
    cfg = config(tmp_path)
    schedule = b'{"Data":{"Games":[{"GameStatus":"SCHEDULED","PreExeDate":"2026-07-29T18:35:00+08:00"}]}}'
    finished = b'{"Data":{"Game":{"GameStatus":"FINISHED"}}}'
    scheduled = b'{"Data":{"Game":{"GameStatus":"SCHEDULED","PreExeDate":"2026-07-29T18:35:00+08:00"}}}'
    client = FakeClient([
        FakeResponse(200, schedule),
        FakeResponse(200, finished),
        FakeResponse(200, finished),
        FakeResponse(200, scheduled),
        FakeResponse(200, schedule),
        FakeResponse(200, scheduled),
        FakeResponse(200, finished),
        FakeResponse(200, finished),
    ])
    observer = Observer(cfg, client=client, sleep=lambda _: None)

    assert observer.run_cycle(now=lambda: NOW) == "ok"
    state = json.loads(cfg.state_path.read_text())
    assert state["terminal_game_ids"] == ["2026-A-226", "2026-A-227"]

    assert observer.run_cycle(now=lambda: NOW + timedelta(seconds=61)) == "ok"
    assert client.urls[4:] == [build_game_url("2026-A-228", cfg)]


def test_terminal_games_remain_skipped_after_observer_restart(tmp_path: Path):
    cfg = config(tmp_path)
    cfg.state_path.write_text(json.dumps({
        "attempts_total": 0,
        "recent_attempts": [],
        "terminal_game_ids": ["2026-A-226", "2026-A-227"],
    }))
    schedule = b'{"Data":{"Games":[{"GameStatus":"SCHEDULED","PreExeDate":"2026-07-29T18:35:00+08:00"}]}}'
    scheduled = b'{"Data":{"Game":{"GameStatus":"SCHEDULED","PreExeDate":"2026-07-29T18:35:00+08:00"}}}'
    client = FakeClient([
        FakeResponse(200, schedule),
        FakeResponse(200, scheduled),
        FakeResponse(200, scheduled),
        FakeResponse(200, scheduled),
    ])

    observer = Observer(cfg, client=client, sleep=lambda _: None)
    assert observer.run_cycle(now=lambda: NOW) == "ok"

    assert client.urls == [build_schedule_url(cfg), build_game_url("2026-A-228", cfg)]
    assert json.loads(cfg.state_path.read_text())["terminal_game_ids"] == [
        "2026-A-226", "2026-A-227",
    ]


def test_only_exact_successful_single_game_finished_status_is_terminal(tmp_path: Path):
    cfg = config(tmp_path)
    schedule_finished = b'{"Data":{"Games":[{"GameStatus":"FINISHED"}]}}'
    finished = b'{"Data":{"Game":{"GameStatus":"FINISHED"}}}'
    start = b'{"Data":{"Game":{"GameStatus":"START"}}}'
    scheduled = b'{"Data":{"Game":{"GameStatus":"SCHEDULED"}}}'
    client = FakeClient([
        FakeResponse(200, schedule_finished),
        FakeResponse(302, finished),
        FakeResponse(200, start),
        FakeResponse(200, scheduled),
    ])
    observer = Observer(cfg, client=client, sleep=lambda _: None)

    assert observer.run_cycle(now=lambda: NOW) == "ok"

    assert json.loads(cfg.state_path.read_text())["terminal_game_ids"] == []


@pytest.mark.parametrize(
    "terminal_game_ids",
    [
        "2026-A-226",
        ["2026-A-226", 227],
        ["2026-A-999"],
        ["2026-A-226", "2026-A-226"],
        ["2026-A-227", "2026-A-226"],
    ],
)
def test_invalid_persisted_terminal_game_ids_fail_closed(
    tmp_path: Path,
    terminal_game_ids: object,
):
    cfg = config(tmp_path)
    cfg.state_path.write_text(json.dumps({
        "attempts_total": 0,
        "recent_attempts": [],
        "terminal_game_ids": terminal_game_ids,
    }))
    observer = Observer(cfg, client=FakeClient([]), sleep=lambda _: None)

    with pytest.raises(ValueError, match="terminal_game_ids"):
        observer.run_cycle(now=lambda: NOW)


def test_marking_terminal_game_preserves_existing_persistent_state(tmp_path: Path):
    cfg = config(tmp_path)
    original_state = {
        "attempts_total": 17,
        "recent_attempts": [{"epoch": NOW.timestamp(), "template_id": "schedule"}],
        "next_sequence": 42,
        "terminal_game_ids": ["2026-A-226"],
        "future_compatible_field": {"keep": True},
    }
    cfg.state_path.write_text(json.dumps(original_state))
    observer = Observer(cfg, client=FakeClient([]), sleep=lambda _: None)

    observer.terminal_games.mark("2026-A-227")

    state = json.loads(cfg.state_path.read_text())
    assert state == {
        **original_state,
        "terminal_game_ids": ["2026-A-226", "2026-A-227"],
    }


def test_5xx_retries_only_once_and_persists_both_attempts(tmp_path: Path):
    cfg = config(tmp_path)
    sleeps: list[float] = []
    client = FakeClient([FakeResponse(503, b"first"), FakeResponse(502, b"second"),
                         FakeResponse(200, b"third")])
    observer = Observer(cfg, client=client, sleep=sleeps.append, jitter=lambda _a, _b: 30)

    result = observer.observe(build_game_url("2026-A-226", cfg), now=lambda: NOW)

    assert result["status_code"] == 502
    assert len(client.urls) == 2
    assert sleeps == [30]
    assert PersistentBudget(cfg).total_attempts == 2
    assert len(cfg.manifest_path.read_text().splitlines()) == 2


def test_cycle_attempt_cap_stops_before_ninth_attempt(tmp_path: Path):
    cfg = config(tmp_path, max_attempts_per_cycle=8)
    client = FakeClient([FakeResponse(503, b"fail") for _ in range(12)])
    observer = Observer(cfg, client=client, sleep=lambda _: None, jitter=lambda _a, _b: 30)

    observer.run_cycle(now=lambda: NOW)

    assert len(client.urls) <= 8


def test_export_manifest_verifies_every_raw_checksum(tmp_path: Path):
    cfg = config(tmp_path)
    store = EvidenceStore(cfg)
    store.write_response("schedule", None, 200, 5, b'{"Data":{"Games":[]}}', NOW, 1)

    export = store.build_export_manifest()

    assert export["files"][0]["sha256"]
    assert export["total_checksum"]
    assert export["manifest_entries"] == 1
