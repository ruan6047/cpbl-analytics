"""只驗切換marker前置拒跑及明示救援；假HOME／截斷舊業務，不碰真Mac工作。"""

import importlib.util
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
SHELLS = ("scrape-daily", "postseason-evening", "weekly-box-revisions",
          "weekly-game-pitches", "schedule-watchdog", "refresh-cpbl-prod")


def marker_for(home):
    return home / "Library/Application Support/cpbl-analytics/mac-jobs-disabled"


def shell_fixture(tmp_path, name):
    fake_home = tmp_path / "home"; fake_home.mkdir()
    marker = marker_for(fake_home); marker.parent.mkdir(parents=True)
    marker.write_text(""); marker.chmod(0o600)
    scripts = tmp_path / "scripts"; scripts.mkdir()
    source = (ROOT / "scripts" / f"{name}.sh").read_text()
    # 真入口到第一個業務初始化之前的完整prefix；後面僅替換成無副作用邊界樁。
    assert source.count('REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"') == 1
    prefix = source.split('REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"', 1)[0]
    script = scripts / f"{name}.sh"
    script.write_text(prefix + "printf 'existing-flow\\n'\nexit 0\n")
    env = {"HOME": str(fake_home), "PATH": "/usr/bin:/bin", "REFRESH_TRIGGER": "manual"}
    return script, marker, env


@pytest.mark.parametrize("name", SHELLS)
def test_old_shell_refuses_cutover_but_explicit_rescue_reaches_existing_flow(tmp_path, name):
    script, marker, env = shell_fixture(tmp_path, name)
    refused = subprocess.run(["bash", str(script)], env=env, capture_output=True, text=True, timeout=5)
    assert refused.returncode == 78 and "existing-flow" not in refused.stdout
    assert "CPBL_MAC_RESCUE=1" in refused.stderr
    rescued = subprocess.run(["bash", str(script)], env={**env, "CPBL_MAC_RESCUE": "1"},
                             capture_output=True, text=True, timeout=5)
    assert rescued.returncode == 0 and rescued.stdout == "existing-flow\n"
    assert marker.exists() and not (tmp_path / "logs").exists()


def test_absent_marker_keeps_old_default_and_help_never_enters_business(tmp_path):
    script, marker, env = shell_fixture(tmp_path, "scrape-daily")
    helped = subprocess.run(["bash", str(script), "--help"], env=env,
                            capture_output=True, text=True, timeout=5)
    assert helped.returncode == 0 and "existing-flow" not in helped.stdout
    marker.unlink()
    default = subprocess.run(["bash", str(script)], env=env, capture_output=True, text=True, timeout=5)
    assert default.returncode == 0 and default.stdout == "existing-flow\n"


def test_linux_jobs_dispatch_precedes_mac_marker(tmp_path):
    script, _marker, env = shell_fixture(tmp_path, "scrape-daily")
    binaries = tmp_path / "bin"; binaries.mkdir()
    python = binaries / "python"; python.write_text("#!/bin/sh\nprintf 'linux-job\\n'\n")
    python.chmod(0o755)
    result = subprocess.run(["bash", str(script), "--jobs"],
                            env={**env, "PATH": f"{binaries}:/usr/bin:/bin"},
                            capture_output=True, text=True, timeout=5)
    assert result.returncode == 0 and result.stdout == "linux-job\n"


def test_old_alert_cli_guard_precedes_observation_and_explicit_rescue(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("cutover_alert_fixture", ROOT / "scripts/alert_watch.py")
    module = importlib.util.module_from_spec(spec)
    # 同一stdlib helper由原scripts目錄載入，業務觀測整體替為邊界樁。
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    spec.loader.exec_module(module)
    fake_home = tmp_path / "home"; fake_home.mkdir()
    marker = marker_for(fake_home); marker.parent.mkdir(parents=True); marker.write_text("")
    monkeypatch.setenv("HOME", str(fake_home)); monkeypatch.delenv("CPBL_MAC_RESCUE", raising=False)
    calls = []
    monkeypatch.setattr(module, "run_once", lambda *a, **kw: calls.append(True) or [])
    assert module.main([]) == 78 and not calls
    monkeypatch.setenv("CPBL_MAC_RESCUE", "1")
    assert module.main([]) == 0 and calls == [True]
    assert marker.exists()
