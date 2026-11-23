"""Boundary regressions for the Pi's nightly field-scoped acquisition."""

import importlib
import json
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

NOW = datetime(2026, 11, 23, 22, 0, tzinfo=ZoneInfo("Asia/Taipei"))
KEY = "2026-E-4"
BATCH = "a" * 32
RESPONSE = "c" * 64



@pytest.fixture
def source(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    return importlib.import_module("pi_night_source")


def raw_game(number, **updates):
    row = {"Year": "2026", "KindCode": "E", "GameSeasonCode": "E", "GameSno": str(number),
           "GameDate": "2026/11/23", "HomeScore": "7", "VisitingScore": "2",
           "HomePitcherAcnt": "known-home", "VisitingPitcherAcnt": "confirmed-away"}
    return {**row, **updates}


def test_normal_entry_does_not_call_the_original_kind_scrape(monkeypatch, source):
    jobs = importlib.import_module("jobs")
    run = SimpleNamespace(detail={})
    pi = SimpleNamespace(night_results=True)
    calls = []

    def acquire(batch, *, schedules):
        calls.append((batch, schedules))
        return "unchanged"

    def step(name):
        assert name == "boxpa-plan"
        return 0, "idle"

    monkeypatch.setattr(source, "acquire", acquire)
    monkeypatch.setattr("pi_night_results.after_worker", lambda *args, **kwargs: None)
    assert jobs._evening_active(run, source.evening, step, "scrape", pi_batch=pi) == 0
    assert calls == [(pi, True)]


def test_reused_and_unknown_never_fetch(monkeypatch, tmp_path, source):
    path = tmp_path / "state.json"
    source.evening.save_json(path, source.evening.empty_state())
    monkeypatch.setenv("POSTSEASON_STATE", str(path))
    monkeypatch.setattr(source.evening, "read_today_schedule", lambda *_: (None, None))
    monkeypatch.setattr(source, "datetime", SimpleNamespace(now=lambda _: NOW))
    monkeypatch.setattr(source, "planned_fields", lambda *args, **kw: {KEY: source.STARTERS | {"home_score"}})
    connection = SimpleNamespace(run=SimpleNamespace(detail={}), feature=SimpleNamespace(TAIPEI=NOW.tzinfo))
    monkeypatch.setattr(source, "_accepted", lambda *_: None)
    monkeypatch.setattr(source, "_read_schedule", lambda *_: pytest.fail("unscoped source acquisition"))
    monkeypatch.setattr(source, "conn", lambda: pytest.fail("unscoped DB write"))
    assert source.acquire(connection, schedules=True) == "unchanged"
    assert connection.run.detail["evening_result_source"]["games"][KEY]["home_score"] == "unknown"

    pending = {"offer": {"batch_id": BATCH}}
    monkeypatch.setattr(source, "_accepted", lambda *_: pending)
    monkeypatch.setattr(source, "read_receipt", lambda *a, **k: b"pinned-response")
    monkeypatch.setattr(source, "checked_reply", lambda *_: {
        "as_of": NOW.date().isoformat(), "games": {KEY: {field: {"state": "reuse"} for field in ("home_score", *source.STARTERS)}},
    })
    assert source.acquire(connection, schedules=True) == "unchanged"
    assert set(connection.run.detail["evening_result_source"]["games"][KEY].values()) == {"reuse"}


def test_only_confirmed_game_fields_are_projected(source):
    wanted = {KEY: {"home_starter_id", "away_starter_id", "home_score", "away_score"}}
    proof = {"games": {KEY: {
        "home_starter_id": {"state": "reuse"},
        "away_starter_id": {"state": "missing", "expected_sha256": source.field_digest("confirmed-away")},
        "home_score": {"state": "corrected", "expected_sha256": source.field_digest(7)},
        "away_score": {"state": "unknown"},
    }}}
    _, selected = source.selection(wanted, proof)
    expected = {"away_starter_id": "confirmed-away", "home_score": 7}
    calls = []

    def fetch(key):
        calls.append(key)
        return [raw_game(4), raw_game(5, HomeScore="99")]

    (record, fields, rows), = source.collect(selected, fetch)
    assert calls == [(2026, "E")]
    assert record["game_sno"] == 4
    assert fields == expected and len(rows) == 1

    changed_since_assessment = source.collect(selected, lambda _: [raw_game(4, HomeScore="8")])
    assert changed_since_assessment[0][1] == {"away_starter_id": "confirmed-away"}


def test_reply_is_bound_to_own_batch_and_hash(source):
    batch = SimpleNamespace(timeout=30)
    offer = {"batch_id": BATCH, "games": [[2026, "E", 4]]}
    value = {"version": 1, "source_id": "pi", "as_of": NOW.date().isoformat(), "batch_id": BATCH,
             "response_sha256": RESPONSE, "games": {KEY: {}}, "checked_at": NOW.isoformat()}
    pending = {"offer": offer, "response_sha256": RESPONSE}
    assert source.checked_reply(batch, pending, json.dumps(value), NOW) == value
    for name, wrong in (("batch_id", "b" * 32), ("response_sha256", "e" * 64), ("source_id", "other")):
        with pytest.raises(ValueError, match="assessment_binding"):
            source.checked_reply(batch, pending, json.dumps({**value, name: wrong}), NOW)


def test_signal_only_matches_full_fingerprint_without_www(monkeypatch, tmp_path, source):
    path = tmp_path / "state.json"
    state = source.evening.empty_state()
    state["detected_changes"] = [{"key": KEY, "field": "venue", "official_value": "新莊"}]
    state["events"] = {"schedule_changed:" + KEY: {
        "key": KEY, "type": "schedule_changed", "state": "open", "official": {"venue": "新莊"},
        "t1_stats_first_seen": NOW.isoformat(),
    }}
    source.evening.save_json(path, state)
    expected = source.field_digest([(2026, "E", 4, "venue", "新莊", NOW.astimezone(UTC).isoformat(), None)])
    statements = []

    class Cursor:
        def execute(self, command, params):
            statements.append((command, params))
            return self

        def fetchall(self):
            return []

    @contextmanager
    def connect():
        yield SimpleNamespace(cursor=Cursor)

    batch = SimpleNamespace(run=SimpleNamespace(detail={}), feature=SimpleNamespace(TAIPEI=NOW.tzinfo))
    monkeypatch.setenv("POSTSEASON_STATE", str(path))
    monkeypatch.setattr(source.evening, "_season_year", lambda _: 2026)
    monkeypatch.setattr(source.evening, "read_today_schedule", lambda *_: (None, None))
    monkeypatch.setattr(source, "conn", connect)
    monkeypatch.setattr(source, "_accepted", lambda *_: {"offer": {"batch_id": BATCH}})
    monkeypatch.setattr(source, "read_receipt", lambda *a, **k: b"pinned-response")
    monkeypatch.setattr(source, "checked_reply", lambda *_: {
        "batch_id": BATCH, "response_sha256": RESPONSE,
        "as_of": datetime.now(NOW.tzinfo).date().isoformat(),
        "games": {KEY: {"signals": {"state": "missing", "expected_sha256": expected}}},
    })
    monkeypatch.setattr(source, "_read_schedule", lambda *_: pytest.fail("signal triggered WWW"))
    assert source.acquire(batch, schedules=False) == "changed"
    assert statements[-1][1]["official_value"] == "新莊"
    assert source.evening.load_state(path)["pi_result_field_scope"]["fields"] == {KEY: ["signals"]}


def test_first_wakeup_sends_only_metadata_then_point_reads_without_resending(monkeypatch, tmp_path, source):
    wire = importlib.import_module("pi_evening_handoff")
    state = tmp_path / "state.json"
    root = tmp_path / "outgoing"
    root.mkdir(mode=0o700)
    source.evening.save_json(state, source.evening.empty_state())
    monkeypatch.setenv("POSTSEASON_STATE", str(state))
    monkeypatch.setenv("CPBL_PI_EVENING_RESULT_ASSESSMENT_ROOT", str(root))
    monkeypatch.setattr(source, "datetime", SimpleNamespace(now=lambda _: NOW))
    monkeypatch.setattr(source.evening, "read_today_schedule", lambda *_: (None, None))
    monkeypatch.setattr(source, "planned_fields", lambda *_, **__: {KEY: {"home_starter_id", "venue"}})
    monkeypatch.setattr(source, "_read_schedule", lambda *_: pytest.fail("no trusted decision yet"))
    traces = []

    def store(folder, filename, text):
        (folder / filename).write_text(text + "\n")

    def save(folder, filename, payload):
        (folder / filename).write_bytes(source.evening_receipt.as_bytes(payload))

    def send(_cmd, folder, _env, _deadline, instructions):
        staged = json.loads((folder / "scope.json").read_bytes())
        assert staged == {"fields": {KEY: ["home_starter_id", "venue"]}}
        offer = json.loads((folder / "response.json").read_bytes())
        assert offer["snapshot_sha256"] == source.hashlib.sha256((folder / "scope.json").read_bytes()).hexdigest()
        assert instructions == wire.assessment_upload(offer["batch_id"])
        assert b"snapshot.json" not in instructions and b"/assessment/incoming/" in instructions
        assert instructions.decode().splitlines()[-1].endswith(offer["batch_id"] + ".ready")
        traces.append(("submit", offer["batch_id"]))
        return {"native_wait": True, "native_rc": 0, "timed_out": False}

    def read(_batch, name, *, assessment):
        assert assessment == "assess-results"
        traces.append(("read", name))
        return None

    def private(path, *, directory=False):
        assert path.is_dir() if directory else path.is_file()

    identity = SimpleNamespace(IDENTITY_FILE="test-key", KNOWN_HOSTS="test-pin", USER="uploader",
                               _private=private, _state=store, _authentication=lambda *_: ("key", "pin"),
                               _sftp_command=lambda *_: ["fixture-only"])
    batch = SimpleNamespace(timeout=30, run=SimpleNamespace(detail={}),
                            feature=SimpleNamespace(TAIPEI=NOW.tzinfo, sender=identity, _save=save,
                                                    _saved=lambda p: json.loads(p.read_bytes()), _run_native=send))
    monkeypatch.setattr(source, "read_receipt", read)
    for _ in range(2):
        assert source.acquire(batch, schedules=True) == "unchanged"
    ident = traces[0][1]
    assert traces == [("submit", ident), ("read", ident), ("read", ident)]
