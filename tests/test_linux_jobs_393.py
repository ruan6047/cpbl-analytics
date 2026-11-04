"""六工作 Linux 適配的直接邊界；不使用真 DB、Redis、browser 或 ping。"""

import contextlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).parents[1]
DEAD_DSN = "postgresql://x:x@127.0.0.1:1/x"


@pytest.mark.parametrize("name", ["scrape-daily", "postseason-evening", "weekly-box-revisions",
                                  "weekly-game-pitches", "schedule-watchdog"])
def test_existing_shell_jobs_mode_delegates_before_mac_operations(tmp_path, name):
    scripts, bin_dir = tmp_path / "scripts", tmp_path / "bin"
    scripts.mkdir(); bin_dir.mkdir()
    shutil.copy2(ROOT / "scripts" / f"{name}.sh", scripts / f"{name}.sh")
    calls, forbidden = tmp_path / "calls", tmp_path / "forbidden"
    for cmd in ("uv", "docker", "ssh", "curl", "launchctl", "pmset", "python3"):
        path = bin_dir / cmd
        path.write_text('#!/bin/sh\nprintf forbidden >> "$FORBIDDEN"\nexit 97\n')
        path.chmod(0o755)
    python = bin_dir / "python"
    python.write_text('#!/bin/sh\nprintf "%s\\n" "$@" > "$CALLS"\n')
    python.chmod(0o755)
    result = subprocess.run(["bash", str(scripts / f"{name}.sh"), "--jobs"],
                            env={**os.environ, "PATH": f"{bin_dir}:/usr/bin:/bin",
                                 "DATABASE_URL": DEAD_DSN, "REFRESH_TRIGGER": "not-mac",
                                 "CALLS": str(calls), "FORBIDDEN": str(forbidden)},
                            cwd=tmp_path, text=True, capture_output=True, timeout=5)
    assert result.returncode == 0
    assert calls.read_text().splitlines() == [str(scripts / "jobs.py"), name]
    assert not forbidden.exists()


@pytest.fixture
def jobs(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("cpbl_linux_jobs_test", ROOT / "scripts/jobs.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    code = tmp_path / "app"; code.mkdir()
    root = code / "logs"; root.mkdir(mode=0o700)
    monkeypatch.setattr(module, "CODE_ROOT", code)
    monkeypatch.setenv("CPBL_JOBS_STATE_DIR", str(root))
    monkeypatch.setenv("DATABASE_URL", DEAD_DSN)
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:1/0")
    monkeypatch.setenv("REFRESH_TRIGGER", "jobs")
    monkeypatch.setenv("CPBL_JOBS_API_URL", "none")
    monkeypatch.setenv("CPBL_HC_PING_KEY", "fixture-only")
    monkeypatch.setenv("CPBL_HC_API_KEY", "fixture-only")
    monkeypatch.delenv("DAILY_FORCE_FULL", raising=False)
    monkeypatch.chdir(tmp_path)
    forbidden_calls, pings = [], []

    def forbidden(*args, **kwargs):
        forbidden_calls.append(True)
        raise AssertionError("forbidden live dependency")

    from cpbl import db
    from cpbl.ingest import _browser
    monkeypatch.setattr(db, "_pool", None)
    for name in ("conn", "pool", "migrate"):
        monkeypatch.setattr(db, name, forbidden)
    monkeypatch.setattr(_browser, "_Session", forbidden)
    monkeypatch.setattr(module.alert_ping, "parse_env_file", forbidden)
    monkeypatch.setattr(module.alert_ping, "ping", lambda config, check, signal, **kw:
                        pings.append((check, signal)) or module.alert_ping.Result("ping", check, True, True))
    monkeypatch.setattr(module.alert_ping, "arm_schedule", lambda config, check, **kw:
                        module.alert_ping.Result("arm", check, True, True))
    monkeypatch.setattr(module.alert_watch, "run_command", forbidden)
    module.test_linux_probe = module.alert_watch._linux_services
    monkeypatch.setattr(module.alert_watch, "_linux_services", lambda:
                        {"postgres": "running", "redis": "running", "api": "running"})
    monkeypatch.setattr(module.alert_watch, "_linux_continuity", lambda: ["boot", "namespace"])
    for name in ("launchctl_installed", "launchctl_cpbl_labels", "last_boot_times", "notify"):
        monkeypatch.setattr(module.schedule_watch, name, forbidden)
    monkeypatch.setattr(module.alert_watch.urllib.request, "urlopen", forbidden)
    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    module.test_pings = pings
    yield module, root
    assert not forbidden_calls


def fake_module(monkeypatch, name, **attrs):
    module = SimpleNamespace(**attrs)
    parent, attr = name.rsplit(".", 1)
    package = __import__(parent, fromlist=[attr])
    monkeypatch.setitem(sys.modules, name, module)
    monkeypatch.setattr(package, attr, module, raising=False)
    return module


def test_jobs_bookends_real_owner_lock_history_and_daily_check(jobs, monkeypatch, capsys):
    module, root = jobs

    def daily(run, args):
        assert (run.lock / "pid").read_text() == str(os.getpid())
        assert os.environ["CPBL_JOBS_MODE"] == "1"
        return 0

    monkeypatch.setattr(module, "_daily", daily)
    assert module.main(["scrape-daily"]) == 0
    assert module.test_pings == [("daily", "start"), ("daily", 0)]
    assert not (root / "locks/refresh.lock").exists()
    records = [json.loads(row) for row in (root / "schedule-history/com.cpbl.scrape-daily.jsonl").read_text().splitlines()]
    assert [(r["state"], r["trigger"]) for r in records] == [("running", "jobs"), ("succeeded", "jobs")]
    assert json.loads(capsys.readouterr().out)["exit_code"] == 0


def test_busy_lock_is_not_stolen_and_interrupt_releases_only_owned_lock(jobs, monkeypatch):
    module, root = jobs
    lock = root / "locks/refresh.lock"; lock.mkdir(parents=True)
    # 部署 consumer 的空目錄 claim 與 job pid/kind 鎖同樣 busy，不被 job 寫入或刪除。
    assert module.main(["weekly-game-pitches"]) == 75
    assert not list(lock.iterdir())
    (lock / "pid").write_text("foreign")
    (lock / "kind").write_text("foreign")
    assert module.main(["weekly-game-pitches"]) == 75
    assert (lock / "pid").read_text() == "foreign"
    (lock / "pid").unlink(); (lock / "kind").unlink(); lock.rmdir()

    def interrupted(*args):
        raise module.Interrupted(143)

    monkeypatch.setattr(module, "_weekly", interrupted)
    assert module.main(["weekly-game-pitches"]) == 143
    assert not lock.exists()
    status = json.loads((root / "jobs/weekly-game-pitches.json").read_text())
    assert status["state"] == "failed" and status["exit_code"] == 143


def test_jobs_rejects_dotenv_before_business_and_help_is_zero_effect(jobs, monkeypatch, capsys):
    module, root = jobs
    assert module.main(["-hh"]) == 0
    assert not (root / "jobs").exists()
    monkeypatch.delenv("DATABASE_URL")
    assert module.main(["alert-watch"]) == 64  # 健康探測也不能退回隱式本機 DB。
    monkeypatch.setenv("DATABASE_URL", DEAD_DSN)
    (root.parent / ".env").write_text("do-not-read")
    assert module.main(["scrape-daily"]) == 64
    assert not (root / "jobs").exists()
    assert "do-not-read" not in capsys.readouterr().out


def daily_fakes(monkeypatch, calls, *, day_type="full", source_rc=0):
    def gate(argv):
        calls.append(("gate", argv[0]))
        if argv[0] == "decide":
            print(f"DAY_TYPE={day_type}\nCLOSED_LEAGUES=major,farm")
        return 0

    def recent(argv, *, jobs):
        calls.append(("recent", jobs)); return source_rc

    fake_module(monkeypatch, "cpbl.ingest.daily_gate", main=gate)
    fake_module(monkeypatch, "cpbl.ingest.run_refresh_recent", main=recent,
                _recent_counts=lambda *a: [(None, 3, 2)],
                _log_refresh=lambda *a: calls.append(("publication", a[-2])))
    fake_module(monkeypatch, "cpbl.ingest.run_build_team_comparison",
                main=lambda argv: calls.append(("team", argv)) or 0)
    fake_module(monkeypatch, "cpbl.features.run_build_features",
                main=lambda argv: calls.append(("features", argv)) or 0)


def test_daily_preserves_partial_error_and_delegates_features_without_train(jobs, monkeypatch):
    module, _ = jobs; calls = []
    daily_fakes(monkeypatch, calls, source_rc=69)
    assert module.main(["scrape-daily"]) == 69
    assert ("recent", True) in calls and ("features", ["--jobs"]) in calls
    assert ("publication", False) in calls and ("gate", "mark-synced") not in calls


def test_closed_skip_does_not_enter_any_data_step(jobs, monkeypatch):
    module, _ = jobs; calls = []
    daily_fakes(monkeypatch, calls, day_type="skip")
    assert module.main(["scrape-daily"]) == 0
    assert calls == [("gate", "decide")]


def test_weekly_closed_kind_and_partial_pitch_result_are_not_silent(jobs, monkeypatch):
    module, _ = jobs; calls = []
    monkeypatch.setattr(module, "_closed", lambda: {"major"})
    fake_module(monkeypatch, "cpbl.ingest.cpbl_pitch_tracking",
                completed_game_snos=lambda y, k, days: calls.append(k) or [1, 2],
                scrape_game_pitches=lambda games: {"games": 1, "skipped_frozen": 0, "pitches": 2})
    assert module.main(["weekly-game-pitches", "--year", "2026"]) == 69
    assert calls == ["D"]


def test_weekly_box_one_kind_failure_does_not_skip_the_other(jobs, monkeypatch):
    module, _ = jobs; calls = []
    monkeypatch.setattr(module, "_closed", lambda: set())

    def scrape(year, snos, kind, **kw):
        calls.append(kind)
        if kind == "A":
            raise RuntimeError("synthetic incomplete")
        return {"games": 1}

    fake_module(monkeypatch, "cpbl.ingest.cpbl_gamelog",
                completed_snos_within_days=lambda *a: [1], scrape_gamelogs=scrape)
    assert module.main(["weekly-box-revisions"]) == 69
    assert calls == ["A", "D"]


def test_evening_quiet_preserves_paused_flags_and_does_no_work(jobs, monkeypatch):
    module, root = jobs; calls = []
    paused = root / "starter-watch.paused-20261028"; paused.write_text("paused")

    def entry(argv, *, jobs):
        calls.append((argv, jobs)); print("quiet"); return 0

    fake_module(monkeypatch, "cpbl.ingest.postseason_evening", main=entry)
    assert module.main(["postseason-evening"]) == 0
    assert calls == [(["plan"], True)] and paused.read_text() == "paused"
    assert not (root / "starter-watch.enabled").exists()


@pytest.mark.parametrize("signal_failure", [True, False])
def test_evening_idle_settles_this_plans_signal_write_result(jobs, monkeypatch, signal_failure):
    from cpbl import change_signals, db
    from cpbl.ingest.postseason_evening import publish_signals

    module, root = jobs; calls = []
    state = {"events": {}, "signals_dirty": True, "signals_error": {"error": "previous"}}

    @contextlib.contextmanager
    def connection():
        if signal_failure:
            raise RuntimeError("fixture signal write failure")
        yield SimpleNamespace(cursor=lambda: object())

    monkeypatch.setattr(db, "conn", connection)
    monkeypatch.setattr(change_signals, "write_signals", lambda *a: False)

    def entry(argv, *, jobs):
        calls.append(argv)
        if argv == ["plan"]:
            publish_signals(state, 2026, datetime.now(module.TAIPEI), direct=True)
        print("idle")
        return 0

    fake_module(monkeypatch, "cpbl.ingest.postseason_evening", main=entry,
                load_state=lambda path: state, state_path=lambda: root / "business.json")
    assert module.main(["postseason-evening"]) == (69 if signal_failure else 0)
    status = json.loads((root / "jobs/postseason-evening.json").read_text())
    assert status["state"] == ("failed" if signal_failure else "succeeded")
    assert bool(state["signals_dirty"]) is signal_failure
    assert bool(state["signals_error"]) is signal_failure
    assert calls == [["plan"], ["boxpa-plan", "--dry"]]


def test_evening_boxpa_idle_does_not_settle_a_previous_plans_signal_error(jobs, monkeypatch):
    module, root = jobs; calls = []
    state = {"signals_error": {"error": "previous"}}

    def entry(argv, *, jobs):
        calls.append(argv); print("idle"); return 0

    fake_module(monkeypatch, "cpbl.ingest.postseason_evening", main=entry,
                load_state=lambda path: state, state_path=lambda: root / "business.json")
    assert module.main(["postseason-evening", "--stage", "boxpa"]) == 0
    assert calls == [["boxpa-plan", "--dry"]]


@pytest.mark.parametrize(("reconcile_ok", "prepare_error", "expected_code"), [
    pytest.param(True, False, 0, id="complete"), pytest.param(False, False, 68, id="mismatch"),
    pytest.param(True, True, 69, id="pa-error-still-delivers-box"),
])
def test_evening_reuses_state_machine_and_direct_reconcile_no_sync_wrapper(
    jobs, monkeypatch, reconcile_ok, prepare_error, expected_code,
):
    module, root = jobs; calls = []; parts = "box" if prepare_error else "box,pa"
    plans = iter(["detail 2026-C-2 box,pa", f"sync 2026-C-2 {parts}"])

    def entry(argv, *, jobs):
        assert jobs
        calls.append(argv[0])
        if argv[0] == "boxpa-plan":
            print("detail 2026-C-2 box,pa" if "--dry" in argv else next(plans))
        elif argv[0] == "boxpa-prepare":
            print(json.dumps({"games": 1, "errors": ["fixture-pa"] if prepare_error else []}))
        else:
            print({"plan": "scrape", "scrape": "changed", "record-sync": "synced"}.get(argv[0], "ok"))
        if argv[0] == "boxpa-record":
            calls.append(("record_code", argv[argv.index("--code") + 1]))
        return 0

    fake_module(monkeypatch, "cpbl.ingest.postseason_evening", main=entry,
                load_state=lambda path: {}, state_path=lambda: root / "business.json",
                save_json=lambda path, value: path.write_text(json.dumps(value)))
    monkeypatch.setattr(module, "_direct_boxpa", lambda keys, parts:
                        calls.append(("reconcile", keys, parts)) or {"ok": reconcile_ok, "games": {}})
    assert module.main(["postseason-evening"]) == expected_code
    assert calls == ["plan", "boxpa-plan", "scrape", "record-sync", "boxpa-plan", "boxpa-detail",
                     "boxpa-prepare", "boxpa-plan", ("reconcile", "2026-C-2", parts),
                     "boxpa-record", ("record_code", "0" if reconcile_ok else "68"), "finish"]


def test_direct_evening_record_preserves_controls_without_backup_call(jobs, monkeypatch):
    from cpbl.ingest import postseason_evening as evening
    module, root = jobs; writes = []
    state = {"events": {}, "starter_inflight": []}
    monkeypatch.setattr(evening, "_now", lambda: datetime(2026, 11, 4, 22, tzinfo=module.TAIPEI))
    monkeypatch.setattr(evening, "configured_evening_kinds", lambda: ("A",))
    monkeypatch.setattr(evening, "tm_recheck_minutes", lambda: 45)
    monkeypatch.setattr(evening, "state_path", lambda: root / "business.json")
    monkeypatch.setattr(evening, "load_state", lambda path: state)
    monkeypatch.setattr(evening, "save_json", lambda *a: None)
    monkeypatch.setattr(evening, "note_league_closed", lambda *a: [])
    monkeypatch.setattr(evening, "read_closure", lambda *a: None)
    monkeypatch.setattr(evening, "publish_signals", lambda *a, direct=False: writes.append(direct))

    def no_backup(*a):
        pytest.fail("Linux direct record must not read or run legacy backup")

    monkeypatch.setattr(evening, "_backup_record_path", no_backup)
    monkeypatch.setattr(evening, "apply_backup_record", no_backup)
    assert evening.main(["record-sync", "--code", "0"], jobs=True) == 0
    assert writes == [True] and state["pending_sync"] is False


def test_watchdog_uses_jobs_history_without_any_mac_probe(jobs, monkeypatch):
    module, root = jobs
    now = datetime(2026, 11, 4, 22, tzinfo=module.TAIPEI)
    registry = json.loads((ROOT / "scripts/schedule-registry.json").read_text())
    anchor = root / "schedule-watchdog/deployed-at.json"; anchor.parent.mkdir()
    anchor.write_text(json.dumps({"anchor_date": "2026-11-02"}))
    monkeypatch.setattr(module.schedule_watch, "probe_production", lambda *a: {"state": "disabled"})
    # 手動補跑不能充當 scheduled jobs 的成功；同週期 jobs 紀錄才採計。
    job = next(j for j in registry["jobs"] if j["label"] == "com.cpbl.scrape-daily")
    hist = root.parent / job["history_path"]; hist.parent.mkdir()
    row = {"schema_version": 1, "label": job["label"], "state": "succeeded", "trigger": "jobs",
           "started_at": "2026-11-04T10:10:00+08:00", "finished_at": "2026-11-04T10:15:00+08:00",
           "observed_at": "2026-11-04T10:15:00+08:00", "exit_code": 0}
    hist.write_text(json.dumps(row) + "\n")
    report = module.schedule_watch.evaluate_jobs(registry, root.parent, now, "none")
    daily = next(j for j in report["jobs"] if j["label"] == job["label"])
    assert next(c for c in daily["cycles"] if c["role"] == "F0")["verdict"] == "OK"
    assert not report["registry_findings"]
    row["trigger"] = "manual"; hist.write_text(json.dumps(row) + "\n")
    report = module.schedule_watch.evaluate_jobs(registry, root.parent, now, "none")
    daily = next(j for j in report["jobs"] if j["label"] == job["label"])
    assert not any(c["role"] == "F0" for c in daily["cycles"])
    assert next(c for c in daily["cycles"] if c["role"] == "F1")["verdict"] == "MISSING"


def test_linux_alert_keeps_two_observation_confirmation_and_original_checks(jobs, monkeypatch):
    module, root = jobs; aw = module.alert_watch
    now = datetime(2026, 11, 4, 12, tzinfo=module.TAIPEI)
    monkeypatch.setattr(aw, "_linux_services", lambda: {"postgres": "unreachable", "redis": "running", "api": "running"})
    with module._environment():
        one = aw.observe_jobs(now)
        two = aw.observe_jobs(now + timedelta(minutes=5))
    assert aw.services_decision(None, one, None, now)[0] is None
    assert aw.services_decision(one, two, None, now + timedelta(minutes=5))[0] == "fail"
    assert module.alert_ping.load_config(use_environment=True).source == "<protected-jobs-environment>"
    assert {module.alert_ping.CHECK_DAILY, module.alert_ping.CHECK_EVENING,
            module.alert_ping.CHECK_SERVICES, module.alert_ping.CHECK_TEST} == {"daily", "evening", "services", "test"}


@pytest.mark.parametrize("jobs_mode", [False, True])
def test_existing_daily_migration_boundary_keeps_mac_default(jobs, monkeypatch, jobs_mode):
    from cpbl.ingest import run_refresh_recent as recent
    module, _ = jobs; calls = []
    monkeypatch.setenv("DAILY_DAY_TYPE", "full"); monkeypatch.setenv("DAILY_CLOSED_LEAGUES", "")
    monkeypatch.setattr(recent, "migrate", lambda: calls.append("migrate"))
    monkeypatch.setattr(recent, "_log_refresh", lambda *a, **kw: None)

    def stop(*a, **kw):
        calls.append("business boundary"); raise RuntimeError("synthetic boundary")

    monkeypatch.setattr(recent, "scrape_games", stop)
    with pytest.raises(SystemExit):
        recent.main([], jobs=jobs_mode)
    assert calls == (["business boundary"] if jobs_mode else ["migrate", "business boundary"])


@pytest.mark.parametrize("direct", [False, True])
def test_signal_publication_uses_same_writer_and_only_mac_requires_sync(jobs, monkeypatch, direct):
    from cpbl import change_signals, db
    from cpbl.ingest import postseason_evening as evening
    module, _ = jobs

    @contextlib.contextmanager
    def connection():
        yield SimpleNamespace(cursor=lambda: object())

    monkeypatch.setattr(db, "conn", connection)
    monkeypatch.setattr(change_signals, "write_signals", lambda *a: True)
    state = {"signals_dirty": True}
    evening.publish_signals(state, 2026, datetime.now(module.TAIPEI), direct=direct)
    assert state["signals_unsynced"] is not direct and not state["signals_dirty"]


def test_jobs_www_missing_bundle_never_falls_back_to_browser(jobs, monkeypatch):
    from cpbl.ingest import _browser
    from cpbl.ingest._replay import ReplayError
    module, _ = jobs
    monkeypatch.delenv("CPBL_REPLAY_MANIFEST", raising=False)
    monkeypatch.delenv("CPBL_REPLAY_BUNDLE", raising=False)
    with module._environment(), pytest.raises(ReplayError):
        _browser.session()


def test_alert_entry_uses_linux_observer_and_existing_services_check(jobs):
    module, root = jobs
    assert module.main(["alert-watch"]) == 0
    assert module.test_pings == [("services", "success")]
    state = json.loads((root / "alert-watch/state.json").read_text())
    assert state["services"]["last_obs"]["containers"] == {
        "postgres": "running", "redis": "running", "api": "running"}


def test_linux_service_probe_is_read_only_and_closes_redis(jobs, monkeypatch):
    from cpbl import db
    module, _ = jobs; calls = []
    monkeypatch.setenv("CPBL_JOBS_API_URL", "http://fixture.invalid/api/info")

    def execute(sql):
        assert sql.startswith(("SELECT", "SET LOCAL", "SET TRANSACTION"))
        calls.append("postgres")
        return SimpleNamespace(fetchone=lambda: (1,))

    @contextlib.contextmanager
    def connect():
        yield SimpleNamespace(execute=execute)

    @contextlib.contextmanager
    def http(*a, **kw):
        calls.append("api"); yield SimpleNamespace(status=200)

    monkeypatch.setattr(db, "conn", connect)
    redis = SimpleNamespace(ping=lambda: calls.append("redis") or True,
                            close=lambda: calls.append("close redis"))
    monkeypatch.setitem(sys.modules, "redis", SimpleNamespace(Redis=SimpleNamespace(from_url=lambda *a, **kw: redis)))
    monkeypatch.setattr(module.alert_watch.urllib.request, "urlopen", http)
    assert module.test_linux_probe() == {"postgres": "running", "redis": "running", "api": "running"}
    assert calls.count("close redis") == 1 and "api" in calls


@pytest.mark.parametrize("jobs_mode", [False, True])
def test_lineup_transport_changes_but_same_payload_parser(jobs, monkeypatch, jobs_mode):
    from cpbl.ingest import _browser, cpbl_site
    _, _root = jobs; calls = []
    payload = {"BattingJson": json.dumps([{"HitterAcnt": "fixture-batter"}]),
               "PitchingJson": json.dumps([{"PitcherAcnt": "fixture-pitcher"}])}
    html = '<input name="__RequestVerificationToken" value="fixture-token">'
    client = SimpleNamespace(get=lambda *a, **kw: SimpleNamespace(text=html),
                             post=lambda *a, **kw: SimpleNamespace(headers={"content-type": "application/json"}, json=lambda: payload),
                             close=lambda: None)
    monkeypatch.setattr(cpbl_site.httpx, "Client", lambda **kw: calls.append("httpx") or client)
    replay = SimpleNamespace(page_html=lambda *a, **kw: html,
                             post=lambda *a, **kw: calls.append("replay") or (200, json.dumps(payload)))
    monkeypatch.setattr(_browser, "session", lambda: replay)
    monkeypatch.setenv("CPBL_JOBS_MODE", "1" if jobs_mode else "0")
    assert cpbl_site.lineup_acnts(2026, [1], delay=0) == ({"fixture-batter"}, {"fixture-pitcher"})
    assert calls == (["replay"] if jobs_mode else ["httpx"])
