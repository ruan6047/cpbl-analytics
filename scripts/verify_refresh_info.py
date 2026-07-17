#!/usr/bin/env python3
"""Fail unless /api/info exposes a recent successful refresh marker."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime, timedelta


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-age-minutes", type=int, default=15)
    parser.add_argument("--now", help="ISO timestamp override for deterministic checks")
    args = parser.parse_args()

    try:
        payload = json.load(sys.stdin)
        last_refresh = datetime.fromisoformat(payload["metrics"]["last_refresh"])
        now = datetime.fromisoformat(args.now) if args.now else datetime.now(UTC)
        if last_refresh.tzinfo is None or now.tzinfo is None:
            raise ValueError("last_refresh and now must include timezone")
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
        print(f"invalid /api/info payload: {error}", file=sys.stderr)
        return 2

    if payload.get("status") != "running":
        print(f"service status is {payload.get('status')!r}", file=sys.stderr)
        return 3

    age = now - last_refresh
    max_age = timedelta(minutes=args.max_age_minutes)
    if age < timedelta(minutes=-5) or age > max_age:
        print(
            f"last_refresh is stale or invalid: value={last_refresh.isoformat()} age={age}",
            file=sys.stderr,
        )
        return 4

    print(f"OK last_refresh={last_refresh.isoformat()} age={age}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
