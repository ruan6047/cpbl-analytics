"""薄 job 接點的離線契約；不把 writer 替身當成 PostgreSQL 實測。"""

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from cpbl import db
from cpbl.ingest import _browser, _replay, cpbl_site, run_replay_games

FIXTURE = Path(__file__).parent / "fixtures" / "replay_393"
ROW = {"Year": 2026, "KindCode": "A", "GameSeasonCode": "1", "GameSno": 7,
       "GameDate": "2026-07-01", "PresentStatus": 1, "HomeScore": 3, "VisitingScore": 2}


def body(root, rows):
    raw = json.dumps({"Success": True, "GameDatas": json.dumps(rows)}).encode()
    (root / "bundle/responses/q1.body").write_bytes(raw)
    path = root / "bundle/index.json"
    index = json.loads(path.read_bytes())
    index["entries"][1].update(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
    path.write_text(json.dumps(index))


@pytest.fixture
def job(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://x:x@127.0.0.1:1/x")
    shutil.copytree(FIXTURE, tmp_path / "input")
    root = tmp_path / "input"
    body(root, [ROW])
    calls = []
    forbidden_calls = []

    def forbidden(*args, **kwargs):
        forbidden_calls.append(True)
        raise AssertionError("不得進入瀏覽器、migration 或真 DB")

    monkeypatch.setattr(_browser, "_Session", forbidden)
    monkeypatch.setattr(db, "migrate", forbidden)
    monkeypatch.setattr(db, "conn", forbidden)
    monkeypatch.setattr(cpbl_site, "conn", forbidden)
    monkeypatch.setattr(cpbl_site, "upsert_games", lambda rows: calls.append(rows) or 1)
    _replay.replay_session.cache_clear()
    args = ["--year", "2026", "--kind", "A", "--manifest", str(root / "manifest.json"),
            "--bundle", str(root / "bundle")]
    yield root, args, calls
    _replay.replay_session.cache_clear()
    assert not forbidden_calls


def test_job_delegates_one_declared_scope_to_original_writer(job, capsys):
    root, args, calls = job
    assert run_replay_games.main(args) == 0
    assert calls == [[ROW]]
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] and out["contract_passed"]
    assert (out["year"], out["kind"], out["input_count"], out["written_count"]) == (2026, "A", 1, 1)
    assert out["index_sha256"] == hashlib.sha256((root / "bundle/index.json").read_bytes()).hexdigest()
    assert "rows" not in out and "token" not in json.dumps(out).lower()


@pytest.mark.parametrize("change", ["year", "kind", "extra_kind"])
def test_scope_mismatch_stops_before_writer(job, capsys, change):
    root, args, calls = job
    if change in ("year", "kind"):
        args[args.index("--" + change) + 1] = "2025" if change == "year" else "D"
    else:
        path = root / "manifest.json"
        m = json.loads(path.read_bytes())
        m["max_requests"] = 3
        m["requests"].append({**m["requests"][1], "id": "q2",
                              "form": {"calendar": "2026/01/01", "location": "", "kindCode": "D"}})
        path.write_text(json.dumps(m))
    assert run_replay_games.main(args) == 1
    assert not calls
    assert json.loads(capsys.readouterr().out)["stage"] == "scope"


def test_corrupt_body_never_reaches_writer_or_browser(job, capsys):
    root, args, calls = job
    (root / "bundle/responses/q1.body").write_bytes(b"corrupt")
    assert run_replay_games.main(args) == 1
    assert not calls
    assert json.loads(capsys.readouterr().out)["stage"] == "bundle"


def test_payload_missing_writer_keys_is_rejected(job, capsys):
    root, args, calls = job
    body(root, [{"name": "虛構"}])
    assert run_replay_games.main(args) == 1
    assert not calls
    assert json.loads(capsys.readouterr().out)["stage"] == "parse"


def test_writer_failure_is_nonzero_and_does_not_echo_error(job, capsys, monkeypatch):
    _, args, calls = job

    def failed(rows):
        calls.append(rows)
        raise RuntimeError("private-row password=hidden postgresql://private-dsn")

    monkeypatch.setattr(cpbl_site, "upsert_games", failed)
    assert run_replay_games.main(args) == 1
    assert len(calls) == 1
    captured = capsys.readouterr()
    out = json.loads(captured.out)
    assert out["contract_passed"] and not out["ok"] and out["stage"] == "write"
    assert all(value not in captured.out + captured.err for value in ("private-row", "hidden", "private-dsn"))


@pytest.mark.parametrize("mode", ["missing_database", "dotenv"])
def test_missing_explicit_environment_stops_before_writer(job, capsys, monkeypatch, tmp_path, mode):
    _, args, calls = job
    if mode == "missing_database":
        monkeypatch.delenv("DATABASE_URL", raising=False)
    else:
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".env").write_text("dummy-private-environment")
    assert run_replay_games.main(args) == 1
    assert not calls
    assert json.loads(capsys.readouterr().out)["stage"] == "environment"


def test_bad_kind_does_not_echo_unvalidated_input(job, capsys):
    _, args, calls = job
    args[args.index("--kind") + 1] = "private-dsn-value"
    assert run_replay_games.main(args) != 0
    assert not calls
    captured = capsys.readouterr()
    assert "private-dsn-value" not in captured.out + captured.err


def test_help_needs_no_database_or_writer(job, capsys, monkeypatch):
    _, _, calls = job
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert run_replay_games.main(["--help"]) == 0
    assert not calls
    assert "--manifest" in capsys.readouterr().out
