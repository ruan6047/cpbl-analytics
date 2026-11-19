"""Pi feature handoff with process doubles and no shared database or SFTP."""

import gzip
import hashlib
import importlib.util
import json
import os
import stat
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

ENTRY = Path(__file__).resolve().parents[1] / "ops/pi-fetcher/cpbl_pi_feature.py"
spec = importlib.util.spec_from_file_location("pi_feature_handoff_393", ENTRY)
pi = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pi)


def test_response_is_the_final_publication_and_run_directory_is_exclusive():
    run = "a" * 32
    root = f"/incoming/features/{run}"
    assert pi._publication_batch(run) == (
        f"mkdir {root}\n"
        f'put "result.json.gz" {root}/.result.json.gz.upload\n'
        f"rename {root}/.result.json.gz.upload {root}/result.json.gz\n"
        f'put "response.json" {root}/.response.json.upload\n'
        f"rename {root}/.response.json.upload {root}/response.json\n"
    ).encode()


@pytest.mark.parametrize("run", ["../abc", "/tmp", "A" * 32, "b" * 31])
def test_publication_cannot_escape_the_fixed_feature_path(run):
    with pytest.raises(ValueError, match="invalid_run_id"):
        pi._publication_batch(run)


@pytest.fixture
def feature_run(tmp_path, monkeypatch):
    from cpbl.features import handoff

    day = datetime.now(pi.TAIPEI).date()
    source = "test-pi"
    run = handoff.run_id(source, day)
    root = tmp_path / "features"
    root.mkdir(mode=0o700)
    executions = []

    def synthetic_result(work):
        record = {
            "year": day.year, "kind_code": "A", "game_season_code": "1", "game_sno": 1,
            "game_date": day.isoformat(), "season": day.year, "home_win": 1, "completed": True,
            "home_team_code": "A01", "away_team_code": "B01",
            "home_team_name": "Synthetic home", "away_team_name": "Synthetic away",
        }
        blob = gzip.compress(json.dumps([[
            record.get(column) for column in handoff.outcome.FEATURE_COLUMNS
        ]]).encode(), mtime=0)
        refresh = json.loads((work / "freshness.json").read_text())
        manifest = {
            "version": 1, "source_id": source, "run_id": run, "as_of": day.isoformat(),
            "refresh_finished_at": refresh["finished_at"],
            "snapshot_at": datetime.now(UTC).isoformat(),
            "input_sha256": "c" * 64, "algorithm_sha256": handoff.algorithm_sha256(),
            "result_bytes": len(blob), "result_sha256": hashlib.sha256(blob).hexdigest(),
            "row_count": 1,
        }
        handoff._publish_files(work / "result", run, blob, manifest)

    def ready(command, cwd, env, deadline, payload=None):
        if "_refresh" in command:
            stage = "refresh"
        elif "compute" in command:
            stage = "compute"
            synthetic_result(cwd)
        else:
            stage = "publish"
        executions.append((stage, cwd, payload))
        return {"native_rc": 0, "native_wait": True, "timed_out": False}

    def enter(**opts):
        return pi.run(root, source, day, 60, **opts)

    monkeypatch.setattr(pi, "_private_environment", lambda: {"LANG": "C.UTF-8"})
    monkeypatch.setattr(pi.sender, "_authentication", lambda *a: (Path("/private/key"), Path("/private/pin")))
    monkeypatch.setattr(pi, "_run_native", ready)
    return enter, executions, ready, root / run


def test_local_result_can_be_sent_once_without_refreshing_or_getting_vps_inputs(feature_run):
    enter, executions, _, work = feature_run
    ready = enter()
    assert ready["ok"] and ready["stage"] == "local_ready"
    assert [stage for stage, _, _ in executions] == ["refresh", "compute"]
    sent = enter(send=True)
    assert sent["ok"] and sent["stage"] == "published"
    stage, cwd, batch = executions[-1]
    assert stage == "publish" and cwd == work / "result" / sent["run_id"]
    assert batch == pi._publication_batch(sent["run_id"])
    assert enter(send=True)["stage"] == "already_published"
    assert [stage for stage, _, _ in executions] == ["refresh", "compute", "publish"]


def test_tampered_result_is_not_sent(feature_run):
    enter, executions, _, work = feature_run
    result = enter()
    (work / "result" / result["run_id"] / "result.json.gz").write_bytes(b"stale or incomplete")
    assert not enter(send=True)["ok"]
    assert [stage for stage, _, _ in executions] == ["refresh", "compute"]


def test_one_local_reentry_never_retries_an_uncertain_publish(feature_run, monkeypatch):
    enter, executions, ready, _ = feature_run

    def uncertain(command, cwd, env, deadline, payload=None):
        if payload is not None:
            executions.append(("publish", cwd, payload))
            return {"native_rc": 1, "native_wait": True, "timed_out": False}
        if "compute" in command and not any(stage == "compute" for stage, _, _ in executions):
            executions.append(("compute", cwd, None))
            return {"native_rc": 78, "native_wait": True, "timed_out": False}
        return ready(command, cwd, env, deadline, payload)

    monkeypatch.setattr(pi, "_run_native", uncertain)
    assert enter(send=True)["stage"] == "compute"
    assert enter(send=True)["stage"] == "publish"
    assert enter(send=True)["stage"] == "publish_active"
    assert [stage for stage, _, _ in executions] == ["refresh", "compute", "compute", "publish"]


def test_private_socket_only_and_no_ambient_postgres_routing(tmp_path, monkeypatch):
    monkeypatch.setenv("PGHOSTADDR", "127.0.0.1")
    monkeypatch.setenv("DATABASE_URL", "not the private dsn")
    monkeypatch.setenv("CPBL_FEATURE_PI_DATABASE_URL", "postgresql://private@invalid/cpbl393_feature_bench")
    with pytest.raises(ValueError, match="private_pi_socket_dsn_required"):
        pi._private_environment()
    private = tmp_path.resolve()
    private.chmod(0o700)
    socket_path = private / ".s.PGSQL.5432"
    original_lstat = Path.lstat

    def staged_socket(path):
        if path == socket_path:
            return SimpleNamespace(st_mode=stat.S_IFSOCK | 0o700, st_uid=os.getuid())
        return original_lstat(path)

    monkeypatch.setattr(Path, "lstat", staged_socket)
    dsn = f"dbname=cpbl393_feature_bench host='{private}'"
    monkeypatch.setenv("CPBL_FEATURE_PI_DATABASE_URL", dsn)
    env = pi._private_environment()
    assert env["DATABASE_URL"] == env["CPBL_FEATURE_PI_DATABASE_URL"] == dsn
    assert "PGHOSTADDR" not in env


def test_private_refresh_reuses_schedule_and_box_ingest_and_rejects_box_gaps(tmp_path, monkeypatch):
    from cpbl.ingest import cpbl_gamelog, cpbl_site, run_refresh_recent

    day = datetime.now(pi.TAIPEI).date()
    calls = []
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATABASE_URL", "fixture unix socket dsn")
    monkeypatch.setattr(pi, "_private_environment", lambda: {"DATABASE_URL": "fixture unix socket dsn"})

    def schedule(first, last, kind):
        calls.append(("schedule", first, last, kind))
        return {day.year: 5}

    def boxes(year, snos, kind):
        calls.append(("box", year, snos, kind))
        return {"target": len(snos), "games": len(snos), "failed": []}

    monkeypatch.setattr(cpbl_site, "scrape_games", schedule)
    monkeypatch.setattr(cpbl_gamelog, "scrape_gamelogs", boxes)
    monkeypatch.setattr(run_refresh_recent, "_completed_snos", lambda *a: [3, 5])
    monkeypatch.setattr(run_refresh_recent, "_missing_gamelog_snos", lambda *a: [3, 2])
    monkeypatch.setattr(run_refresh_recent, "_detail_gaps", lambda *a: {})
    pi._local_refresh(day, None, None)
    assert calls == [("schedule", day.year, day.year, "A"), ("box", day.year, [2, 3, 5], "A")]
    monkeypatch.setattr(run_refresh_recent, "_detail_gaps", lambda *a: {2: ["pitching_gamelog"]})
    with pytest.raises(ValueError, match="gamelog_refresh_incomplete"):
        pi._local_refresh(day, None, None)


def test_response_manifest_replacement_is_not_sent_even_if_result_bytes_match(feature_run):
    enter, executions, _, work = feature_run
    result = enter()
    path = work / "result" / result["run_id"] / "response.json"
    replaced = json.loads(path.read_text())
    replaced["input_sha256"] = "d" * 64
    path.write_text(json.dumps(replaced))
    assert not enter(send=True)["ok"]
    assert [stage for stage, _, _ in executions] == ["refresh", "compute"]
