"""Read exact, authorized nightly fields without returning persisted values."""

import hashlib
import json
from datetime import UTC, date, datetime

from psycopg import sql

from cpbl.features.handoff import SHA, _need
from cpbl.ingest.daily_current_handoff import TABLE_LAYOUTS

GAME_COLUMNS = TABLE_LAYOUTS["games"][1].split()[4:]
SIGNAL_COLUMNS = TABLE_LAYOUTS["official_change_signals"][1].split()
STARTERS = {"home_starter_id", "away_starter_id"}


def _wire(value):
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, (tuple, list)):
        return [_wire(item) for item in value]
    return value


def value_sha256(value):
    raw = json.dumps(_wire(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def expectations(keys, expected):
    plans = {}
    for key in keys:
        plan = expected.get(key.text, {}).get("result_fields", {})
        _need(isinstance(plan, dict) and plan.keys() <= {*GAME_COLUMNS, "signals"}
              and ("signals" not in plan or key.kind_code in ("C", "E"))
              and all(value is None or (isinstance(value, str) and SHA.fullmatch(value))
                      for value in plan.values()), "evening_result_field_expectation")
        plans[key.text] = plan
    return plans


def _current(connection, key, fields):
    params = (key.year, key.kind_code, key.game_sno)
    game_fields = sorted(set(fields) - {"signals"})
    values = {}
    if game_fields:
        query = sql.SQL(
            "SELECT {} FROM cpbl.games WHERE (year,kind_code,game_sno)=(%s,%s,%s) LIMIT 2"
        ).format(sql.SQL(",").join(map(sql.Identifier, game_fields)))
        found = connection.execute(query, params).fetchall()
        if len(found) == 1:
            values.update(zip(game_fields, found[0], strict=True))
        elif not found:
            values.update(dict.fromkeys(game_fields))
    if "signals" in fields:
        query = sql.SQL(
            "SELECT {} FROM cpbl.official_change_signals "
            "WHERE (year,kind_code,game_sno)=(%s,%s,%s) ORDER BY field"
        ).format(sql.SQL(",").join(map(sql.Identifier, SIGNAL_COLUMNS)))
        values["signals"] = connection.execute(query, params).fetchall()
    return values


def assess(connection, keys, plans):
    result = {}
    for key in keys:
        fields = plans[key.text]
        current = _current(connection, key, fields)
        decisions = {}
        for field, expected in fields.items():
            decision = {"state": "unknown"}
            if field in current:
                value = current[field]
                if expected is None:
                    if field in STARTERS and isinstance(value, str) and value.strip():
                        decision["state"] = "reuse"
                else:
                    # Equality is checked before absence: a known empty signals set and a known
                    # null also prove an exact match and are not fetch authorizations.
                    if value_sha256(value) == expected:
                        decision["state"] = "reuse"
                    elif value is None or value == "" or (field == "signals" and not value):
                        decision.update(state="missing", expected_sha256=expected)
                    else:
                        decision.update(state="corrected", expected_sha256=expected)
            decisions[field] = decision
        result[key.text] = decisions
    return result
