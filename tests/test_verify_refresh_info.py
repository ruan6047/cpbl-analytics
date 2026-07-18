import json
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).parents[1]


def _verify(
    payload: dict[str, object],
    *,
    now: datetime,
    expected_last_game_date: str | None = None,
    expected_completed: int | None = None,
    data_only: bool = False,
) -> subprocess.CompletedProcess[str]:
    expected_args: list[str] = []
    if expected_last_game_date is not None:
        expected_args.extend(["--expected-last-game-date", expected_last_game_date])
    if expected_completed is not None:
        expected_args.extend(["--expected-season-games-completed", str(expected_completed)])
    if data_only:
        expected_args.append("--data-only")
    return subprocess.run(
        [
            "python3",
            str(ROOT / "scripts" / "verify_refresh_info.py"),
            "--now",
            now.isoformat(),
            "--max-age-minutes",
            "15",
            *expected_args,
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


def test_real_data_freshness_metrics_must_match_local_source() -> None:
    now = datetime(2026, 7, 17, 4, 0, tzinfo=UTC)
    payload = {
        "status": "running",
        "metrics": {
            "last_refresh": (now - timedelta(minutes=2)).isoformat(),
            "last_game_date": "2026-07-15",
            "season_games_completed": 2,
        },
    }

    result = _verify(
        payload,
        now=now,
        expected_last_game_date="2026-07-16",
        expected_completed=3,
    )

    assert result.returncode != 0
    assert "data freshness mismatch" in result.stderr


def test_data_only_accepts_matching_real_metrics_before_marker_exists() -> None:
    now = datetime(2026, 7, 17, 4, 0, tzinfo=UTC)
    payload = {
        "status": "running",
        "metrics": {
            "last_game_date": "2026-07-16",
            "season_games_completed": 3,
        },
    }

    result = _verify(
        payload,
        now=now,
        expected_last_game_date="2026-07-16",
        expected_completed=3,
        data_only=True,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.startswith("OK")
