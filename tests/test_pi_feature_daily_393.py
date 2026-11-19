"""Verify the owned service lifetime without starting PostgreSQL or SFTP."""

import importlib.util
import signal
from pathlib import Path
from types import SimpleNamespace

import pytest

_path = Path(__file__).resolve().parents[1] / "ops/pi-fetcher/cpbl_pi_feature_daily.py"
_spec = importlib.util.spec_from_file_location("private_daily", _path)
daily = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(daily)


@pytest.mark.parametrize("feature_rc", [0, 78])
def test_feature_service_reaps_its_pg_even_when_feature_command_fails(tmp_path, monkeypatch, feature_rc):
    data, socket = tmp_path / "pgdata", tmp_path / "socket"
    calls = []

    class Process:
        def poll(self):
            return None

        def send_signal(self, sig):
            calls.append(sig)

        def wait(self, timeout):
            calls.append("wait")
            return 0

    def execute(args, **kwargs):
        if isinstance(args[0], Path) and args[0].name == "pg_isready":
            return SimpleNamespace(returncode=0)
        calls.append(args)
        return SimpleNamespace(returncode=feature_rc)

    monkeypatch.setattr(daily, "_owned_settings", lambda: (data, socket))
    monkeypatch.setenv("CPBL_FEATURE_PI_PG_BIN", "/private/bin")
    monkeypatch.setenv("CPBL_FEATURE_PI_OUT", "/private/out")
    monkeypatch.setattr(daily.os, "umask", lambda _mode: None)
    monkeypatch.setattr(daily.signal, "signal", lambda *_args: None)
    monkeypatch.setattr(daily.subprocess, "Popen", lambda *_a, **_kw: Process())
    monkeypatch.setattr(daily.subprocess, "run", execute)
    assert daily.main() == feature_rc
    assert calls[0][-3:] == ["--source-once", "--send", "--notify"]
    assert calls[0][calls[0].index("--source-id") + 1] == "pi"
    assert calls[1:] == [signal.SIGINT, "wait"]
