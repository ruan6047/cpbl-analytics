import json
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).parents[1]


def _verify(payload: dict[str, object], *, now: datetime) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "python3",
            str(ROOT / "scripts" / "verify_refresh_info.py"),
            "--now",
            now.isoformat(),
            "--max-age-minutes",
            "15",
        ],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        check=False,
    )


def test_recent_running_info_is_accepted() -> None:
    now = datetime(2026, 7, 17, 4, 0, tzinfo=UTC)
    payload = {
        "status": "running",
        "metrics": {"last_refresh": (now - timedelta(minutes=2)).isoformat()},
    }

    result = _verify(payload, now=now)

    assert result.returncode == 0
    assert result.stdout.startswith("OK")


def test_stale_refresh_is_rejected() -> None:
    now = datetime(2026, 7, 17, 4, 0, tzinfo=UTC)
    payload = {
        "status": "running",
        "metrics": {"last_refresh": (now - timedelta(hours=1)).isoformat()},
    }

    result = _verify(payload, now=now)

    assert result.returncode != 0
    assert "stale" in result.stderr
