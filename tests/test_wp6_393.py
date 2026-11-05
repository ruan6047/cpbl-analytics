"""原WP6專用tests。pregrant可本機跑；runtime預設skip，不碰未租用資源。"""

import hashlib
import json
import os
import subprocess
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from wp6_393_support import (
    JOBS,
    TABLES,
    asset,
    checked_dsn,
    claim_case,
    compare_rows,
    comparison,
    database,
    digest,
    job_argv_ok,
    json_bytes,
    load_plan,
    original_job,
    real_prediction,
    records,
    require,
    run_job,
    transaction_game_fingerprint,
)
from wp6_393_support import (
    test_check_event as hc_event,
)


@pytest.fixture
def grant():
    if os.environ.get("CPBL_WP6_EXECUTE") != "1":
        pytest.skip("wp6_runtime_requires_one_complete_resource_grant")
    plan = load_plan()
    yield plan
    import sys
    db = sys.modules.get("cpbl.db")
    if db is not None and db._pool is not None:
        db._pool.close(); db._pool = None


def test_pregrant_guard_stops_before_private_input_or_socket(monkeypatch):
    monkeypatch.delenv("CPBL_WP6_EXECUTE", raising=False)
    monkeypatch.setattr(Path, "read_bytes", lambda *a: pytest.fail("private input opened"))
    with pytest.raises(AssertionError, match="wp6_not_granted"):
        load_plan()
    target = Path(__file__).with_name("wp6_transaction_target.py")
    import sys
    result = subprocess.run([sys.executable, str(target)], env={"PATH": os.environ.get("PATH", "")}, capture_output=True)
    assert result.returncode == 78


def test_pregrant_streamed_hash_attribution_is_not_a_fake_runtime_pass():
    before = [{"key": "[1]", "row": "old", "cells": {"score": "same", "seen_count": "one"}}]
    after = [{"key": "[1]", "row": "new", "cells": {"score": "same", "seen_count": "two"}}]
    diff = list(compare_rows(before, after, {"seen_count": "same real source re-observed"}))
    assert len(diff) == 1 and diff[0]["columns"] == ["seen_count"] and diff[0]["attributed"]
    assert diff[0]["key_sha256"] == digest(b"[1]") and "[1]" not in json.dumps(diff)
    assert not list(compare_rows(before, before, {}))
    assert list(compare_rows(before, after, {}))[0]["attributed"] is False
    assert len(TABLES) == 45 and len(JOBS) == 6
    assert job_argv_ok(["scrape-daily"])
    assert not job_argv_ok(["scrape-daily", "--date", "2026-08-01"])
    assert not job_argv_ok(["scrape-daily", "--help"])


def test_pregrant_creator_selection_binds_both_completion_cutoffs():
    from datetime import date

    document = Path(__file__).resolve().parents[1] / "ops/jobs/WP6-OPERATIONS.md"
    snippet = document.read_text().split("```python\n", 1)[1].split("\n```", 1)[0]
    cutoff = date(2026, 11, 5)
    class ConnectionBoundary:
        def execute(self, query, parameters):
            text = query.as_string()
            assert text.count("%s") == len(parameters)
            assert parameters == (2026, ["A", "D", "E", "C"], cutoff, cutoff)
            assert "PARTITION BY g.kind_code" in text and "WHERE rn=1" in text
            return SimpleNamespace(fetchall=lambda: [])
    namespace = {"connection": ConnectionBoundary(), "cutoff": cutoff}
    exec(compile(snippet, str(document), "exec"), namespace)
    assert namespace["rows"] == []


def test_pregrant_hc_event_reentry_preserves_snapshot_and_never_calls_api(tmp_path, monkeypatch):
    import sys

    monkeypatch.setenv("CPBL_WP6_HC_EXECUTE", "1")
    original = {"schedule": "0 10 * * *", "tz": "Asia/Taipei", "grace": 60, "timeout": 3600}
    calls = []; reads = []
    def request(config, request, **kwargs):
        calls.append(request.get_method())
        if request.get_method() == "POST":
            return True, 200, "", b"{}"
        reads.append(True)
        check = {**original, "uuid": "synthetic-check", "slug": "test",
                 "update_url": "https://hc.invalid/update/synthetic-check",
                 "status": "down" if len(reads) == 2 else "up"}
        return True, 200, "", json_bytes({"checks": [check]})
    config = SimpleNamespace(slug_override="test", api_ready=True, ping_ready=True,
                             api_key="synthetic-only", api_base="https://hc.invalid/api",
                             ping_base="https://hc.invalid/ping")
    helper = SimpleNamespace(load_config=lambda **kw: calls.append("config") or config, USER_AGENT="synthetic",
        _request=request, run_id=lambda seed: "synthetic-rid",
        arm_schedule=lambda *a, **kw: SimpleNamespace(ok=True),
        ping=lambda *a, **kw: SimpleNamespace(ok=True))
    monkeypatch.setitem(sys.modules, "scripts.alert_ping", helper)
    notification = tmp_path / "notification.txt"; notification.write_bytes(b"synthetic notification")
    binding = tmp_path / "notification-binding.json"
    binding.write_bytes(json_bytes({"lease_id": "synthetic-lease", "event": "failed",
        "rid": "synthetic-rid", "check_uuid": "synthetic-check", "delivered": True,
        "artifact": {"path": str(notification), "bytes": notification.stat().st_size,
                     "sha256": digest(notification.read_bytes())}}))
    plan = {"private_root": str(tmp_path), "lease_id": "synthetic-lease",
        "limits": {"private_bytes": 1024}, "healthchecks": {"allowed_hosts": ["hc.invalid"],
        "check_uuid": "synthetic-check", "schedule": "* * * * *", "tz": "Asia/Taipei",
        "grace": 60, "max_polls": 1, "poll_seconds": 1, "notification_seconds": 1,
        "notification_bindings": {"failed": str(binding)}}}
    assert hc_event(plan, "failed")["restored"] is True
    snapshot = tmp_path / "results/hc-failed-original.private.json"
    before = snapshot.read_bytes(); before_hash = digest(before); before_calls = len(calls)
    original["grace"] = 999  # 重入若先查API／覆寫snapshot，會破壞第一次原態。
    with pytest.raises((FileExistsError, AssertionError)):
        hc_event(plan, "failed")
    assert snapshot.read_bytes() == before and digest(snapshot.read_bytes()) == before_hash
    assert len(calls) == before_calls
    marker_only = tmp_path / "marker-only/results"; marker_only.mkdir(parents=True)
    (marker_only / "hc-failed-mutation.invoked").touch()
    with pytest.raises((FileExistsError, AssertionError)):
        hc_event({**plan, "private_root": str(marker_only.parent)}, "failed")
    assert not (marker_only / "hc-failed-original.private.json").exists()
    assert len(calls) == before_calls


@pytest.mark.parametrize("job", JOBS)
def test_runtime_historical_job_real_parser_and_isolated_pg(grant, monkeypatch, job):
    require(grant["cases"][job]["argv"][0] == job, "wp6_original_job_binding")
    require(grant["cases"][job]["expected_exit"] == 0, "wp6_normal_job_not_argument_failure")
    _, result = run_job(grant, job, monkeypatch)
    boundary = result["boundary_calls"]
    require(boundary["api"] > 0 if job in ("schedule-watchdog", "alert-watch")
            else boundary["www"] + boundary["http"] > 0, "wp6_normal_job_must_reach_real_input")


# 只有原故障1–4及原變體；資料仍是真capture，只有失敗外部邊界受控注入。
@pytest.mark.parametrize("fault", ["pi-unavailable", "manifest-expired", "bundle-corrupt",
                                    "bundle-oversized", "stats-403", "stats-timeout"])
def test_runtime_original_source_faults_keep_real_job_and_pg(grant, monkeypatch, fault):
    case = grant["cases"][fault]
    require(case["expected_exit"] not in (0, 64, 75), "wp6_fault_must_not_be_argument_or_busy_failure")
    if fault.startswith("stats-"):
        require(case["stats_fault"] == fault.removeprefix("stats-"), "wp6_bound_stats_fault")
    else:
        kind = {"pi-unavailable": "unavailable", "manifest-expired": "expired",
                "bundle-corrupt": "corrupt", "bundle-oversized": "oversized"}[fault]
        require(case["www_fault"] == kind, "wp6_bound_www_fault")
    output, result = run_job(grant, fault, monkeypatch)
    if fault.startswith("stats-"):
        require(result["boundary_calls"]["stats_fault"] > 0, "wp6_real_http_boundary_not_reached")
        from cpbl import db
        with db.conn() as connection:
            count = connection.execute("SELECT count(*) FROM cpbl.game_features WHERE kind_code='A'").fetchone()[0]
        require(count > 0, "wp6_features_must_remain_available")
    else:
        require(result["boundary_calls"]["www"] > 0, "wp6_real_source_fault_boundary_not_reached")
    (output / "fault-scope.json").write_bytes(json_bytes({"fault": fault,
        "injection": "external transport/status/timeout or private corrupt copy only",
        "not_proven": ["physical Pi power loss", "native SFTP exit by this HTTP fixture"]}))


def test_runtime_transaction_sigterm_native_cid_and_real_rollback(grant):
    spec = grant["native"]["transaction-sigterm"]
    require(os.environ.get("CPBL_WP6_NATIVE_EXECUTE") == "1", "wp6_native_not_granted")
    require(len(spec["cid"]) == 64, "wp6_bound_target_cid")
    ready = Path(grant["private_root"]) / spec["ready_file"]
    deadline = time.monotonic() + spec["signal_wait_seconds"]
    while not ready.exists() and time.monotonic() < deadline:
        time.sleep(0.2)
    require(ready.exists(), "wp6_no_transaction_ready")
    before = json.loads(ready.read_bytes())
    require(before["target_cid"] == spec["cid"] and before["transaction_assigned"]
            and before["lease_id"] == grant["lease_id"]
            and before["ready_before_commit"] and before["input_sha256"] == grant["input_sha256"],
            "wp6_actual_transaction_binding")
    projection = '{"Id":{{json .Id}},"Image":{{json .Image}},"Hostname":{{json .Config.Hostname}},"Lease":{{json (index .Config.Labels "cpbl.wp6.lease")}}}'
    checked = subprocess.run(["docker", "--context", spec["docker_context"], "inspect", "--format", projection, spec["cid"]],
                             capture_output=True, timeout=spec["client_seconds"])
    require(checked.returncode == 0, "wp6_native_target_inspect")
    target = json.loads(checked.stdout)
    require(target["Id"] == spec["cid"] and target["Lease"] == grant["lease_id"]
            and target["Image"] == spec["image_id"] and target["Hostname"] == spec["hostname"], "wp6_native_namespace")
    def games_snapshot():
        h = hashlib.sha256(); count = 0
        for row in records(grant, "games"):
            h.update(json_bytes(row)); count += 1
        return count, h.hexdigest()
    before_games = games_snapshot()
    with database(grant) as connection:
        committed = transaction_game_fingerprint(connection, grant["cases"]["transaction-sigterm"]["transaction_key"])
    require(list(committed) != before["uncommitted_game_fingerprint"],
            "wp6_transaction_needs_observable_true_input_change")
    command = ["docker", "--context", spec["docker_context"], "kill", "--signal=TERM", spec["cid"]]
    sent = subprocess.run(command, capture_output=True, timeout=spec["client_seconds"])
    require(sent.returncode == 0, "wp6_term_request_failed")
    waited = subprocess.run(["docker", "--context", spec["docker_context"], "wait", spec["cid"]],
                            capture_output=True, timeout=spec["client_seconds"])
    require(waited.returncode == 0 and waited.stdout.strip() == b"143", "wp6_native_target_wait143")
    with database(grant) as connection:
        active = connection.execute("SELECT count(*) FROM pg_stat_activity WHERE pid=%s",
                                    (before["pg_backend_pid"],)).fetchone()[0]
    require(active == 0, "wp6_pg_backend_not_exited")
    output = Path(grant["private_root"]) / "results/transaction-sigterm"
    require(games_snapshot() == before_games, "wp6_actual_transaction_rollback_no_reason_exemption")
    require(not (output / "app/logs/locks/refresh.lock").exists(), "wp6_owned_lock_not_released")
    (output / "signal-evidence.json").write_bytes(json_bytes({"term_client_rc": 0,
        "wait_client_rc": 0, "job_native_exit": 143, "pg_backend_gone": True, "lock_released": True,
        "games_count": before_games[0], "games_sha256_before_after": before_games[1]}))


@pytest.mark.parametrize("fault", ["scheduler-stopped", "deployment-recreated"])
def test_runtime_original_native_lifecycle_fault_evidence_and_pg(grant, monkeypatch, fault):
    # 原WP5執行既有精確動作，本test不造部署器或啟動未知命令。
    spec = grant["native"][fault]
    before = json.loads(asset(grant, spec["before"]).read_bytes())
    after = json.loads(asset(grant, spec["after"]).read_bytes())
    wait_raw = asset(grant, spec["native_wait"]).read_text().strip()
    require(before["Id"] == spec["old_cid"] and before["Image"] == spec["image_id"], "wp6_native_before")
    require(before["Lease"] == grant["lease_id"] and after["Lease"] == grant["lease_id"], "wp6_native_lease")
    require(before["State"]["Running"] is True, "wp6_original_native_was_running")
    require(wait_raw in {"0", "143", "137"}, "wp6_known_native_exit_required")
    if fault == "scheduler-stopped":
        require(after["Id"] == before["Id"] and after["State"]["Running"] is False, "wp6_scheduler_not_stopped")
    else:
        require(after["Id"] != before["Id"] and after["Image"] == before["Image"]
                and after["State"]["Running"] is True, "wp6_recreate_must_be_real")
        active_work = json.loads(asset(grant, spec["active_work"]).read_bytes())
        require(active_work.get("state") == "running" and active_work.get("exit_code") is None
                and active_work.get("label") in {"com.cpbl." + name for name in JOBS[:4]},
                "wp6_recreate_must_interrupt_real_work")
    output = Path(grant["private_root"]) / "results" / fault; output.mkdir(parents=True, exist_ok=True)
    if fault == "scheduler-stopped":
        output, _ = run_job(grant, fault, monkeypatch)
    else:
        claim_case(output)
        comparison(grant, grant["cases"][fault], output)
    (output / "native-fault-result.json").write_bytes(json_bytes({"fault": fault,
        "before_sha256": spec["before"]["sha256"], "after_sha256": spec["after"]["sha256"],
        "wait_sha256": spec["native_wait"]["sha256"], "native_exit_known": True}))


@pytest.mark.parametrize("scenario", ["trainer-not-run", "trainer-failed"])
def test_runtime_original_trainer_decoupling_real_feature_api_artifact(grant, monkeypatch, scenario):
    checked_dsn(grant)
    from cpbl.config import settings
    from cpbl.features import outcome as feature_builder
    from cpbl.models import outcome_simple
    from cpbl.models import run_train_outcome_simple as trainer

    artifact = asset(grant, grant["artifact"])
    monkeypatch.setattr(settings, "artifact_dir", artifact.parent)
    monkeypatch.setattr(settings, "database_url", os.environ["CPBL_ISOLATED_TEST_DSN"])
    # load_outcome_rows函式本身不替換；trainer真入口先從租用PG選列。
    require(trainer.load_outcome_rows is outcome_simple.load_outcome_rows, "wp6_real_trainer_loader")
    failure_seen = []
    def injected_failure(*args, **kwargs):
        require(args and len(args[0]) > 0, "wp6_trainer_must_load_real_rows_before_fault")
        failure_seen.append(True); raise RuntimeError("wp6_injected_before_fit_backtest")
    monkeypatch.setattr(trainer, "walk_forward_backtest", injected_failure)
    monkeypatch.setattr(trainer, "train_final_model", lambda *a, **kw: pytest.fail("real training forbidden"))
    if scenario == "trainer-failed":
        # 真入口/真PG選列後，只有backtest邊界注入失敗，不實訓、不假造模型。
        with pytest.raises(RuntimeError, match="wp6_injected_before_fit_backtest"):
            trainer.main([])
        require(failure_seen == [True], "wp6_trainer_failure_not_reached")
    monkeypatch.setattr(trainer, "main", lambda *a, **kw: pytest.fail("job must not invoke trainer"))
    require(grant["cases"][scenario]["argv"] == ["scrape-daily"], "wp6_decoupling_uses_daily")
    built = []; materialize = feature_builder.materialize
    def observed_build():
        count = materialize()
        built.append(count)
        return count
    monkeypatch.setattr(feature_builder, "materialize", observed_build)
    output, _ = run_job(grant, scenario, monkeypatch)
    require(len(built) == 1 and type(built[0]) is int and built[0] > 0, "wp6_real_feature_build_required")
    marker = output / "app/logs/daily-sync-marker.json"
    require(marker.is_file(), "wp6_real_publish_marker_required")
    published = json.loads(marker.read_bytes())
    require(published.get("synced_at") and "write_counter" in published, "wp6_publish_marker_contract")
    result = real_prediction(grant, monkeypatch, output)
    (output / "real-api-result.json").write_bytes(json_bytes({"scenario": scenario,
        "feature_build_rows": built[0], "publish_marker_sha256": digest(marker.read_bytes()), **result}))


@pytest.mark.parametrize("event", ["failed", "interrupted", "silent"])
def test_runtime_original_three_test_check_events(grant, event):
    if os.environ.get("CPBL_WP6_HC_EXECUTE") != "1":
        pytest.skip("wp6_hc_requires_same_grant_test_check_scope")
    result = hc_event(grant, event)
    output = Path(grant["private_root"]) / "results"; output.mkdir(exist_ok=True)
    (output / ("hc-" + event + ".json")).write_bytes(json_bytes(result))


@pytest.mark.parametrize("control", ["closed-paused", "open", "checkpoints-enabled", "watch-enabled"])
def test_runtime_original_season_and_starter_controls(grant, monkeypatch, control):
    from cpbl import season_close
    from cpbl.features import outcome as feature_builder
    from cpbl.ingest import starter_checkpoints, starter_watch

    with original_job(grant, control, monkeypatch) as (jobs, case, output, intents, trace):
        checkpoint_calls, watch_calls = [], []
        built = []; materialize = feature_builder.materialize
        def observed_build():
            count = materialize(); built.append(count)
            return count
        monkeypatch.setattr(feature_builder, "materialize", observed_build)
        record_attempt = starter_checkpoints.record_attempt
        record_watch = starter_watch.record_fetch
        def checkpoint_observer(checkpoints, ids, *args, **kwargs):
            ids = list(ids)
            if ids:
                checkpoint_calls.append(True)
            return record_attempt(checkpoints, ids, *args, **kwargs)
        def watch_observer(state, now, kinds, *args, **kwargs):
            kinds = list(kinds)
            if kinds:
                watch_calls.append(True)
            return record_watch(state, now, kinds, *args, **kwargs)
        monkeypatch.setattr(starter_checkpoints, "record_attempt", checkpoint_observer)
        monkeypatch.setattr(starter_watch, "record_fetch", watch_observer)
        closure = season_close.league_closure()
        if control == "closed-paused":
            require(case["argv"] == ["scrape-daily"], "wp6_closed_uses_daily")
            require(set(season_close.closed_leagues(closure)) == {"major", "farm"}, "wp6_real_2026_closure")
            require(not starter_checkpoints.flag_path().exists() and not starter_watch.flag_path().exists(),
                    "wp6_starters_must_stay_paused")
            for stem in ("postseason-starter-checkpoints", "starter-watch"):
                names = [Path(item["destination"]) for item in case["state"]
                         if item["destination"].startswith(stem)
                         and item["destination"].endswith(".paused-20261028")]
                require(len(names) == 1 and (output / "app/logs" / names[0]).is_file(),
                        "wp6_original_paused_names_required")
        else:
            require(case["environment"]["CPBL_SEASON_CLOSE"] == "open", "wp6_open_only_test_context")
            require(not season_close.closed_leagues(closure), "wp6_open_override")
            if control == "checkpoints-enabled":
                require(starter_checkpoints.flag_path().exists(), "wp6_private_checkpoint_flag")
            if control == "watch-enabled":
                require(starter_watch.flag_path().exists(), "wp6_private_watch_flag")
        claim_case(output)
        rc = jobs.main(case["argv"])
        require(rc == case["expected_exit"], "wp6_control_job_exit")
        if control == "closed-paused":
            require(trace["www"] == 0 and trace["http"] == 0, "wp6_closed_must_not_crawl")
            require((output / "app/logs/daily-sync-marker.json").is_file(), "wp6_closed_publish_marker")
            require(len(built) == 1 and type(built[0]) is int and built[0] > 0,
                    "wp6_closed_real_feature_build")
        if control == "checkpoints-enabled":
            require(checkpoint_calls, "wp6_checkpoint_real_branch_not_reached")
        if control == "watch-enabled":
            require(watch_calls, "wp6_watch_real_branch_not_reached")
        comparison(grant, case, output)
