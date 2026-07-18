#!/usr/bin/env python3
"""Fail unless /api/info exposes a recent successful refresh marker."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-age-minutes", type=int, default=15)
    parser.add_argument("--now", help="ISO timestamp override for deterministic checks")
    parser.add_argument("--data-only", action="store_true")
    parser.add_argument("--expected-last-game-date")
    parser.add_argument("--expected-season-games-completed", type=int)
    args = parser.parse_args()

    try:
        payload = json.load(sys.stdin)
        metrics = payload["metrics"]
        now = datetime.fromisoformat(args.now) if args.now else datetime.now(timezone.utc)  # noqa: UP017
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
        print(f"invalid /api/info payload: {error}", file=sys.stderr)
        return 2

    if payload.get("status") != "running":
        print(f"service status is {payload.get('status')!r}", file=sys.stderr)
        return 3

    mismatches = []
    if (
        args.expected_last_game_date is not None
        and metrics.get("last_game_date") != args.expected_last_game_date
    ):
        mismatches.append(
            f"last_game_date expected={args.expected_last_game_date} actual={metrics.get('last_game_date')}"
        )
    if (
        args.expected_season_games_completed is not None
        and metrics.get("season_games_completed") != args.expected_season_games_completed
    ):
        mismatches.append(
            "season_games_completed "
            f"expected={args.expected_season_games_completed} actual={metrics.get('season_games_completed')}"
        )
    if mismatches:
        print(f"data freshness mismatch: {'; '.join(mismatches)}", file=sys.stderr)
        return 5

    if not args.data_only:
        try:
            last_refresh = datetime.fromisoformat(metrics["last_refresh"])
            if last_refresh.tzinfo is None or now.tzinfo is None:
                raise ValueError("last_refresh and now must include timezone")
        except (KeyError, TypeError, ValueError) as error:
            print(f"invalid /api/info payload: {error}", file=sys.stderr)
            return 2

        age = now - last_refresh
        max_age = timedelta(minutes=args.max_age_minutes)
        if age < timedelta(minutes=-5) or age > max_age:
            print(
                f"last_refresh is stale or invalid: value={last_refresh.isoformat()} age={age}",
                file=sys.stderr,
            )
            return 4
        refresh_summary = f" last_refresh={last_refresh.isoformat()} age={age}"
    else:
        refresh_summary = ""

    print(
        "OK"
        f" last_game_date={metrics.get('last_game_date')}"
        f" season_games_completed={metrics.get('season_games_completed')}"
        f"{refresh_summary}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
