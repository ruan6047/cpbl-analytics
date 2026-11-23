"""Publish the original evening result and signal table families in one bounded transaction."""

from datetime import datetime

from cpbl.features.handoff import _need
from cpbl.ingest import boxpa_sync, daily_current_handoff, evening_result_fields
from cpbl.ingest.daily_derived_handoff import _apply

RESULTS = {"games", "game_schedule_status_revisions", "game_source_revisions"}
SIGNALS = {"official_change_signals"}
PARTS = (["results"], ["signals"], ["results", "signals"])
KINDS = ("A", "C", "E", "F")
FINAL_FIELDS = {"present_status", "home_score", "away_score"}
REVISION_TABLES = {"game_schedule_status_revisions", "game_source_revisions"}


def keys_for(games):
    _need(isinstance(games, list) and games, "evening_results_scope")
    keys = []
    for game in games:
        _need(isinstance(game, list) and len(game) == 3
              and type(game[0]) is int and 1 <= game[0] <= 9999
              and game[1] in KINDS
              and type(game[2]) is int and 1 <= game[2] <= 999, "evening_results_game")
        keys.append(boxpa_sync.GameKey(*game))
    _need(keys == sorted(set(keys)), "evening_results_keys")
    return keys


def _layout(snapshot, keys, parts):
    _need(isinstance(snapshot, dict) and set(snapshot) == {"columns", "data"}
          and isinstance(snapshot["columns"], dict) and isinstance(snapshot["data"], dict),
          "evening_results_snapshot")
    tables = (RESULTS if "results" in parts else set()) | (SIGNALS if "signals" in parts else set())
    _need(set(snapshot["columns"]) == set(snapshot["data"]) == tables, "evening_results_tables")
    scope = {(k.year, k.kind_code, k.game_sno) for k in keys}
    actual, results, source_games, official, layout = set(), set(), set(), {}, {}
    for table in sorted(tables):
        size, header = daily_current_handoff.TABLE_LAYOUTS[table]
        columns = header.split()
        raw = snapshot["data"][table]
        _need(snapshot["columns"][table] == columns and isinstance(raw, list), "evening_results_columns")
        seen, records = set(), []
        for values in raw:
            _need(isinstance(values, list) and len(values) == len(columns), "evening_results_row")
            record = dict(zip(columns, values, strict=True))
            key = record["year"], record["kind_code"], record["game_sno"]
            identity = tuple(values[:size])
            _need(type(key[0]) is int and type(key[2]) is int and key in scope
                  and all(type(value) in (str, int) for value in identity) and identity not in seen,
                  "evening_results_row_scope")
            if table == "game_source_revisions":
                _need(record["source"] == "schedule", "evening_results_revision_source")
                source_games.add(key)
            if table in ("game_source_revisions", "game_schedule_status_revisions"):
                _need(isinstance(record["last_seen_at"], str), "evening_results_revision_time")
            if table == "official_change_signals":
                _need(key[1] in ("E", "C") and record["field"] in ("game", "date", "teams", "venue")
                      and isinstance(record["detected_at"], str)
                      and (record["resolved_at"] is None or isinstance(record["resolved_at"], str)),
                      "evening_results_signal")
            seen.add(identity)
            actual.add(key)
            records.append(record)
            if table == "games":
                results.add(key)
            if table == "game_schedule_status_revisions":
                official.setdefault(key, []).append(record["last_seen_at"])
        layout[table] = columns, size, records
    _need(actual == scope and (not tables.intersection(RESULTS) or results)
          and (not tables.intersection(SIGNALS) or layout["official_change_signals"][2])
          and results == set(official) and source_games <= results, "evening_results_observation_scope")
    return layout, results, official


def _require_fresh(connection, layout, official):
    for game, times in official.items():
        fresh = connection.execute(
            "SELECT max(last_seen_at) <= (SELECT max(value) FROM unnest(%s::timestamptz[]) AS value) "
            "FROM cpbl.game_schedule_status_revisions WHERE (year,kind_code,game_sno)=(%s,%s,%s)",
            (times, *game),
        ).fetchone()[0]
        _need(fresh is not False, "evening_results_newer_target_revision")
    for row in layout.get("official_change_signals", (None, None, []))[2]:
        fresh = connection.execute(
            "SELECT (detected_at,resolved_at) IS NOT DISTINCT FROM (%s::timestamptz,%s::timestamptz) "
            "OR greatest(detected_at,resolved_at) < greatest(%s::timestamptz,%s::timestamptz) "
            "FROM cpbl.official_change_signals WHERE (year,kind_code,game_sno,field)=(%s,%s,%s,%s)",
            (row["detected_at"], row["resolved_at"], row["detected_at"], row["resolved_at"],
             row["year"], row["kind_code"], row["game_sno"], row["field"]),
        ).fetchone()
        _need(fresh is None or fresh == (True,), "evening_results_newer_target_signal")


def _picked_fields(snapshot, keys, parts, plans):
    choices = snapshot["fields"]
    _need(isinstance(choices, dict) and set(choices) == {key.text for key in keys},
          "evening_results_selected_scope")
    for key in keys:
        fields = choices[key.text]
        _need(isinstance(fields, list) and fields == sorted(set(fields)) and bool(fields),
              "evening_results_selected_fields")
        for column in fields:
            _need(plans.get(key.text, {}).get(column) is not None
                  and ("signals" if column == "signals" else "results") in parts,
                  "evening_results_selected_field_not_authorized")
    return choices


def _normalized_signals(records):
    values = []
    for row in sorted(records, key=lambda row: row["field"]):
        values.append([datetime.fromisoformat(row[column]) if column in ("detected_at", "resolved_at")
                       and row[column] is not None else row[column]
                       for column in evening_result_fields.SIGNAL_COLUMNS])
    return values


def _scoped_revisions(layout, choices):
    """Do not advance the official completion observation on a starter-only or venue-only batch."""
    selected = {game for game, fields in choices.items() if FINAL_FIELDS <= set(fields)}
    out = {}
    for table, (columns, count, rows) in layout.items():
        if table == "games":
            continue
        if table in REVISION_TABLES:
            rows = [r for r in rows if f"{r['year']}-{r['kind_code']}-{r['game_sno']}" in selected]
        out[table] = columns, count, rows
    return out


def _apply_fields(connection, keys, layout, choices, plans, remaining):
    counts, reused = {}, True
    game_layout = layout.get("games")
    signals = layout.get("official_change_signals", ([], 0, []))[2]
    for key in keys:
        selected = set(choices[key.text]) - {"signals"}
        values = [r for r in (game_layout[2] if game_layout else [])
                  if (r["year"], r["kind_code"], r["game_sno"]) == (key.year, key.kind_code, key.game_sno)]
        _need(bool(selected) == bool(values) and len(values) <= 1, "evening_results_field_rows")
        decisions = evening_result_fields.assess(connection, [key], {
            key.text: {name: plans[key.text][name] for name in choices[key.text]},
        })[key.text]
        _need(all(item["state"] != "unknown" for item in decisions.values()), "evening_results_field_unknown")
        for row in values:
            _need(all(evening_result_fields.value_sha256(row[name]) == plans[key.text][name] for name in selected),
                  "evening_results_field_value")
            columns = game_layout[0][:4] + sorted(selected)
            exists = connection.execute(
                "SELECT 1 FROM cpbl.games WHERE (year,kind_code,game_season_code,game_sno)=(%s,%s,%s,%s)",
                tuple(row[name] for name in game_layout[0][:4]),
            ).fetchone()
            complete = selected == set(evening_result_fields.GAME_COLUMNS)
            _need(exists is not None or complete, "evening_results_partial_missing_target_game")
            if all(decisions[name]["state"] == "reuse" for name in selected) and exists is not None:
                counts["games"] = counts.get("games", 0) + 1
            else:
                reused = False
                counts["games"] = counts.get("games", 0) + _apply(
                    connection, "games", columns, 4, [{name: row[name] for name in columns}], insert=exists is None,
                )
        own_signals = [r for r in signals
                       if (r["year"], r["kind_code"], r["game_sno"]) == (key.year, key.kind_code, key.game_sno)]
        _need(("signals" in choices[key.text]) == bool(own_signals), "evening_results_signal_rows")
        if own_signals:
            _need(evening_result_fields.value_sha256(_normalized_signals(own_signals)) == plans[key.text]["signals"],
                  "evening_results_signal_value")
    matched = {table: _apply(connection, table, *records, insert=True, write=False)
               for table, records in remaining.items()}
    if any(matched[table] != len(records[2]) for table, records in remaining.items()):
        matched = daily_current_handoff.publish(connection, remaining)
        reused = False
    counts.update(matched)
    signal_scope = {key.text: {"signals": plans[key.text]["signals"]} for key in keys
                    if "signals" in choices[key.text]}
    if signal_scope:
        observed = evening_result_fields.assess(
            connection, [key for key in keys if key.text in signal_scope], signal_scope,
        )
        _need(all(values["signals"]["state"] == "reuse" for values in observed.values()),
              "evening_results_signal_postwrite_scope")
    return counts, reused


def publish(connection, keys, parts, snapshot, *, field_plans=None):
    """No final-game requirement here: the official result packet can be what establishes final."""
    columns_data = {key: snapshot[key] for key in ("columns", "data")}
    layout, results, official = _layout(columns_data, keys, parts)
    if field_plans is not None:
        choices = _picked_fields(snapshot, keys, parts, field_plans)
        remaining = _scoped_revisions(layout, choices)
        _require_fresh(
            connection, remaining,
            {game: times for game, times in official.items()
             if FINAL_FIELDS <= set(choices[f"{game[0]}-{game[1]}-{game[2]}"])},
        )
        counts, reused = _apply_fields(connection, keys, layout, choices, field_plans, remaining)
    else:
        _require_fresh(connection, layout, official)
        counts = {table: _apply(connection, table, *records, insert=True, write=False)
                  for table, records in layout.items()}
        reused = all(counts[table] == len(records[2]) for table, records in layout.items())
        if not reused:
            counts = daily_current_handoff.publish(connection, layout)
    signal_keys = {(r["year"], r["kind_code"], r["game_sno"])
                   for r in layout.get("official_change_signals", (None, None, []))[2]}
    games = {}
    for key in keys:
        identity = key.year, key.kind_code, key.game_sno
        games[key.text] = {"results_ok": True if identity in results else None,
                           "signals_ok": True if identity in signal_keys else None}
    return {"ok": True, "games": games, "rows": counts, "delivery_mode": "reused_existing" if reused else "committed"}
