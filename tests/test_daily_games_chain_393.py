"""原 daily 的固定 games→features 呼叫鏈；只執行副本與入口替身。"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
REPLAY = "cpbl.ingest.run_replay_games"
FEATURES = "cpbl.features.run_build_features"
UNREACHABLE = "postgresql://x:x@127.0.0.1:1/x"


@pytest.fixture
def chain(tmp_path):
    repo, bin_dir = tmp_path / "repo", tmp_path / "bin"
    (repo / "scripts").mkdir(parents=True)
    bin_dir.mkdir()
    script = repo / "scripts/scrape-daily.sh"
    shutil.copy2(ROOT / "scripts/scrape-daily.sh", script)
    calls, forbidden = tmp_path / "calls.jsonl", tmp_path / "forbidden"
    python = bin_dir / "python"
    python.write_text(
        f"#!{sys.executable}\n"
        "import argparse, json, os, sys\n"
        "from pathlib import Path\n"
        "if sys.argv[1] == '-c':\n"
        " os.execv(sys.executable, [sys.executable, *sys.argv[1:]])\n"
        "assert sys.argv[1] == '-m'\n"
        "module, args = sys.argv[2], sys.argv[3:]\n"
        "with Path(os.environ['CALLS']).open('a') as f:\n"
        " f.write(json.dumps({'module':module,'args':args,"
        "'database_url':os.environ.get('DATABASE_URL')})+'\\n')\n"
        f"if module == '{REPLAY}':\n"
        # 真正的標準庫 HelpAction 語義；不是重新列出幾個 help 字串。
        " argparse.ArgumentParser(prog='synthetic replay').parse_known_args(args)\n"
        " rc=int(os.environ['REPLAY_RC'])\n"
        " result={'ok':rc==0,'contract_passed':rc==0,'stage':'complete' if rc==0 else 'write',"
        "'input_count':2,'written_count':1 if rc==0 else None,'parsed_sha256':'f'*64}\n"
        " if os.environ['INVALID_RECEIPT']=='1': result.update(ok=False, errors=['write'])\n"
        f"elif module == '{FEATURES}':\n"
        " rc=int(os.environ['FEATURES_RC'])\n"
        " result={'scope':'game_features','ok':rc==0,'stage':'complete' if rc==0 else 'feature_build',"
        "'row_count':5 if rc==0 else None,'errors':[] if rc==0 else ['feature_build']}\n"
        "else:\n"
        " raise AssertionError('unexpected entrypoint')\n"
        "print(json.dumps(result)); sys.exit(rc)\n"
    )
    python.chmod(0o755)
    for name in ("uv", "docker", "ssh", "curl", "psql", "pg_dump", "pg_restore",
                 "launchctl", "pmset", "python3", "date"):
        command = bin_dir / name
        command.write_text('#!/bin/sh\nprintf forbidden >> "$FORBIDDEN"\nexit 97\n')
        command.chmod(0o755)
    args = ["--year", "2026", "--kind", "A", "--manifest", str(tmp_path / "private manifest.json"),
            "--bundle", str(tmp_path / "fixed bundle")]
    env = {**os.environ, "PATH": f"{bin_dir}:/usr/bin:/bin", "DATABASE_URL": UNREACHABLE,
           "CALLS": str(calls), "FORBIDDEN": str(forbidden), "HOME": str(tmp_path / "home"),
           "REFRESH_LOCK_DIR": str(tmp_path / "refresh.lock"), "REFRESH_TRIGGER": "not-mac",
           "API_INFO_URL": "http://127.0.0.1:1/api/info", "VPS": "stub@harness.invalid"}

    def run(*, replay_rc=0, features_rc=0, replay_args=None, invalid_receipt=False):
        result = subprocess.run(
            ["/bin/bash", str(script), "--jobs-games", *(args if replay_args is None else replay_args)],
            cwd=tmp_path, env={**env, "REPLAY_RC": str(replay_rc), "FEATURES_RC": str(features_rc),
                              "INVALID_RECEIPT": str(int(invalid_receipt))},
            text=True, capture_output=True, timeout=5,
        )
        recorded = [json.loads(line) for line in calls.read_text().splitlines()] if calls.exists() else []
        return result, recorded

    yield run, args
    assert not forbidden.exists()
    assert not (tmp_path / "refresh.lock").exists() and not (repo / "logs").exists()


def test_fixed_batch_delegates_original_entries_in_order_and_preserves_scope(chain):
    run, args = chain
    result, calls = run()
    assert result.returncode == 0
    assert calls == [{"module": REPLAY, "args": args, "database_url": UNREACHABLE},
                     {"module": FEATURES, "args": ["--jobs"], "database_url": UNREACHABLE}]
    first, second = map(json.loads, result.stdout.splitlines())
    assert first["contract_passed"] and first["input_count"] == 2 and first["written_count"] == 1
    assert first["parsed_sha256"] == "f" * 64
    assert second["scope"] == "game_features" and second["row_count"] == 5


def test_replay_failure_stops_before_features_and_preserves_first_failure(chain):
    run, _ = chain
    result, calls = run(replay_rc=69)
    assert result.returncode == 69
    assert [c["module"] for c in calls] == [REPLAY]
    summary = json.loads(result.stdout)
    assert not summary["ok"] and summary["stage"] == "write"
    assert summary["written_count"] is None


def test_feature_error_keeps_nonzero_exit_and_its_errors(chain):
    run, _ = chain
    result, calls = run(features_rc=1)
    assert result.returncode == 1
    assert [c["module"] for c in calls] == [REPLAY, FEATURES]
    first, second = map(json.loads, result.stdout.splitlines())
    assert first["ok"] and not second["ok"]
    assert second["errors"] == ["feature_build"] and second["stage"] == "feature_build"


def test_replay_help_does_not_turn_into_a_feature_write(chain):
    run, _ = chain
    result, calls = run(replay_args=["--year", "2026", "--help"])
    assert result.returncode == 0
    assert [c["module"] for c in calls] == [REPLAY]
    assert result.stdout.startswith("usage: synthetic replay")


def test_argparse_clustered_help_does_not_turn_into_a_feature_write(chain):
    run, _ = chain
    result, calls = run(replay_args=["-hh"])
    assert result.returncode == 0
    assert [c["module"] for c in calls] == [REPLAY]
    assert result.stdout.startswith("usage: synthetic replay")


def test_zero_exit_with_failed_receipt_cannot_start_features(chain):
    run, _ = chain
    result, calls = run(invalid_receipt=True)
    assert result.returncode == 1
    assert [c["module"] for c in calls] == [REPLAY]
    assert json.loads(result.stdout)["errors"] == ["write"]
