# LIFECYCLE: standing · 常設工具——這就是給你跑的；不要刪
"""由 jobs.py 的 Pi 晚間路徑按已驗欄位補取資料，只寫 Pi 私庫與本機狀態。"""

import hashlib
import json
import os
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

from pi_evening_handoff import _need, read_receipt, submit_assessment
from psycopg import sql

from cpbl.change_signals import UPSERT_SQL
from cpbl.db import conn
from cpbl.features.handoff import SHA
from cpbl.ingest import boxpa_sync, cpbl_site, daily_current_handoff, evening_receipt
from cpbl.ingest import postseason_evening as evening

COLUMNS = daily_current_handoff.TABLE_LAYOUTS["games"][1].split()
STARTERS = {"home_starter_id", "away_starter_id"}
SCHEDULE_FIELDS = {
    "date": {"game_date", "orig_date", "delay_kind"},
    "teams": {"home_team_code", "home_team_name", "away_team_code", "away_team_name"},
    "venue": {"venue"},
}
RESULT_FIELDS = {
    "present_status", "home_score", "away_score", "winning_pitcher_id",
    "losing_pitcher_id", "closer_id", "mvp_id",
}
GAME_FIELDS = set(COLUMNS[4:])


def planned_fields(state, today=None, *, year=None):
    """Planner evidence supplies the upper bound, never permission to crawl."""
    kinds = set(state.get("scrape_kinds") or ())
    watch = state.get("starter_watch") or {}
    watch_only = set(watch.get("watch_only") or ())
    targets = defaultdict(set)
    for event in evening.open_events(state).values():
        key = event["key"]
        if key.split("-")[1] not in kinds - watch_only:
            continue
        if event["type"] == "new_game":
            targets[key].update(GAME_FIELDS)
        elif event["type"] == "final_not_ingested":
            targets[key].update(RESULT_FIELDS)
        elif event["type"] == "schedule_changed":
            for field in event.get("official") or ():
                targets[key].update(SCHEDULE_FIELDS.get(field, ()))
    checkpoints = state.get("starter_checkpoints") or {}
    for point in state.get("starter_inflight") or ():
        key = checkpoints[point]["key"]
        if key.split("-")[1] in kinds - watch_only:
            targets[key].update(STARTERS)
    for key in evening.sw.pending_keys(state):
        if key.split("-")[1] in (set(watch.get("inflight") or ()) & kinds):
            targets[key].update(STARTERS)
    farm = state.get("farm_final") or {}
    if farm.get("inflight") and today is not None and today.date == farm.get("night"):
        for game in today.games:
            if game.kind_code == evening.FARM_FINAL_KIND and game.game_date == today.date:
                targets[game.key].update(RESULT_FIELDS)
    for row in evening.signal_rows(state):
        if year is not None and row["kind_code"] in ("C", "E"):
            targets[f"{year}-{row['kind_code']}-{row['game_sno']}"].add("signals")
    return targets


def _wire(value):
    if isinstance(value, datetime):
        value = value.astimezone(UTC).isoformat()
    elif hasattr(value, "isoformat"):
        value = value.isoformat()
    elif isinstance(value, (tuple, list)):
        value = [_wire(item) for item in value]
    return value


def field_digest(value):
    raw = json.dumps(_wire(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(raw).hexdigest()


def checked_reply(batch, pending, raw, now):
    offer = pending["offer"]
    reply = json.loads(raw)
    _need(set(reply) == {"version", "source_id", "as_of", "batch_id", "response_sha256", "checked_at", "games"}
          and type(reply["version"]) is int
          and (reply["version"], reply["source_id"], reply["as_of"], reply["batch_id"], reply["response_sha256"])
          == (1, "pi", now.date().isoformat(), offer["batch_id"], pending["response_sha256"]),
          "evening_results_assessment_binding")
    checked = datetime.fromisoformat(reply["checked_at"])
    _need(checked.utcoffset() is not None and 0 <= (now - checked).total_seconds() <= batch.timeout,
          "evening_results_assessment_time")
    scope = {f"{y}-{k}-{n}" for y, k, n in offer["games"]}
    _need(set(reply["games"]) == scope, "evening_results_assessment_games")
    return reply


def selection(targets, reply):
    states, selected = {}, {}
    for key, fields in sorted(targets.items()):
        states[key] = {}
        for field in sorted(fields):
            spec = reply.get("games", {}).get(key, {}).get(field, {"state": "unknown"})
            status = spec.get("state")
            _need(status in ("reuse", "missing", "corrected", "unknown"), "evening_results_assessment_state")
            states[key][field] = status
            if status in ("missing", "corrected"):
                digest = spec.get("expected_sha256")
                _need(isinstance(digest, str) and SHA.fullmatch(digest), "evening_results_assessment_digest")
                selected.setdefault(key, {})[field] = digest
    return states, selected


def _accepted(batch, targets, now):
    """Only consult private, already submitted requests for these same games."""
    if not targets:
        return None
    location = os.environ.get("CPBL_PI_EVENING_RESULT_ASSESSMENT_ROOT")
    if not location:
        return None
    root = Path(location)
    batch.feature.sender._private(root, directory=True)
    candidates = []
    for item in sorted(root.iterdir()):
        if not evening_receipt.BATCH.fullmatch(item.stem) or item.suffix != ".json":
            continue
        pending = batch.feature._saved(item)
        if not pending:
            continue
        offer = pending["offer"]
        evening_receipt.validate_offer(offer)
        _need(offer["batch_id"] == item.stem
              and pending["response_sha256"] == hashlib.sha256(evening_receipt.as_bytes(offer)).hexdigest(),
              "evening_results_pending_identity")
        scope = {f"{y}-{k}-{n}" for y, k, n in offer["games"]}
        if offer["as_of"] == now.date().isoformat() and set(targets) <= scope:
            candidates.append(pending)
    if candidates:
        return max(candidates, key=lambda pending: datetime.fromisoformat(pending["sent_at"]))
    return None


def _read_schedule(state, key):
    from cpbl.ingest._browser import www_marker

    year, kind = key
    marker, source = evening.scrape_marker_args(state, kind)
    if kind == evening.FARM_FINAL_KIND:
        with www_marker(marker, "391", f"{year}/{kind}/-", card="391"):
            return cpbl_site.fetch_year(year, kind)
    if kind in ((state.get("starter_watch") or {}).get("watch_only") or ()):
        with www_marker("other", "342", f"{year}/{kind}/-", card="342"):
            return cpbl_site.fetch_year(year, kind)
    with www_marker(marker, source, f"{year}/{kind}/-"):
        return cpbl_site.fetch_year(year, kind)


def collect(selected, fetch):
    requests = defaultdict(dict)
    for key, fields in selected.items():
        year, kind, sno = key.split("-")
        requests[int(year), kind][int(sno)] = fields
    result = []
    for (year, kind), games in sorted(requests.items()):
        raw = fetch((year, kind))
        cpbl_site.validate_schedule(raw, year, kind)
        grouped = defaultdict(list)
        for item in raw:
            sno = int(item["GameSno"])
            if sno in games:
                grouped[sno].append(item)
        for sno, fields in games.items():
            rows = grouped.get(sno, [])
            if not rows or len({row["GameSeasonCode"] for row in rows}) != 1:
                continue
            primary = cpbl_site._primary_entry(rows)
            record = dict(zip(COLUMNS, cpbl_site._to_record(primary, *cpbl_site._delay_meta(rows)), strict=True))
            verified = {name: record[name] for name, digest in fields.items() if field_digest(record[name]) == digest}
            if verified:
                result.append((record, verified, rows))
    return result


def _store_games(connection, records):
    stored = {}
    for row, fields, raw in records:
        key = tuple(row[column] for column in COLUMNS[:4])
        where = sql.SQL("(year,kind_code,game_season_code,game_sno)=(%s,%s,%s,%s)")
        columns = tuple(sorted(fields))
        result = connection.execute(
            sql.SQL("UPDATE cpbl.games SET {} WHERE {}").format(
                sql.SQL(",").join(sql.SQL("{}=%s").format(sql.Identifier(name)) for name in columns), where,
            ), (*[fields[name] for name in columns], *key),
        )
        if not result.rowcount:
            # New rows need authoritative projections for the complete original insert.
            if set(fields) != GAME_FIELDS:
                continue
            cpbl_site.upsert_games(raw, connection=connection)
        else:
            cpbl_site.record_schedule_revisions(raw, connection=connection)
        year, kind, _, sno = key
        stored[f"{year}-{kind}-{sno}"] = list(columns)
    return stored


def _store_signals(connection, state, selected, year):
    """Stage only an existing official detection whose complete signal fingerprint agrees."""
    target_rows = defaultdict(list)
    first_seen = {
        (event["key"], field, value): datetime.fromisoformat(event["t1_stats_first_seen"])
        for event in (state.get("events") or {}).values()
        for field, value in (event.get("official") or {}).items()
        if event.get("t1_stats_first_seen")
    }
    for row in evening.signal_rows(state):
        key = f"{year}-{row['kind_code']}-{row['game_sno']}"
        seen = first_seen.get((key, row["field"], row["official_value"]))
        if seen is not None:
            target_rows[key].append((row, seen))
    stored = set()
    for key, expected in selected.items():
        rows = sorted(target_rows[key], key=lambda item: item[0]["field"])
        wire = [(year, row["kind_code"], row["game_sno"], row["field"],
                 row["official_value"], seen, None) for row, seen in rows]
        if not rows or field_digest(wire) != expected:
            continue
        _, kind, sno = key.split("-")
        cursor = connection.cursor()
        existing = cursor.execute(
            "SELECT year,kind_code,game_sno,field,official_value,detected_at,resolved_at "
            "FROM cpbl.official_change_signals WHERE (year,kind_code,game_sno)=(%s,%s,%s) FOR UPDATE",
            (year, kind, int(sno)),
        ).fetchall()
        if existing and field_digest(sorted(existing, key=lambda row: row[3])) != expected:
            # Never resolve an unrelated signal or replace a different recorded timestamp.
            continue
        if not existing:
            for row, seen in rows:
                cursor.execute(UPSERT_SQL, {**row, "year": year, "now": seen})
        stored.add(key)
    return stored


def acquire(batch, *, schedules):
    path = evening.state_path()
    state = evening.load_state(path)
    now = datetime.now(batch.feature.TAIPEI)
    today, _ = evening.read_today_schedule(evening.today_schedule_path())
    year = evening._season_year(now)
    if evening.sync_blocked(state, now) or evening.in_daily_guard(now):
        return "unchanged"
    targets = planned_fields(state, today, year=year)
    if not schedules:
        targets = {key: {"signals"} for key, fields in targets.items() if "signals" in fields}
    items = sorted(targets.items())
    location = os.environ.get("CPBL_PI_EVENING_RESULT_ASSESSMENT_ROOT")
    limit = boxpa_sync.MAX_GAMES
    group = 0
    if location and len(items) > limit:
        groups = (len(items) + limit - 1) // limit
        group = state.get("pi_result_assessment_group", 0) % groups
        state["pi_result_assessment_group"] = (group + 1) % groups
        evening.save_json(path, state)
    bounded = dict(items[group * limit:(group + 1) * limit])
    pending = _accepted(batch, bounded, now)
    if pending is None and bounded and location:
        pending = submit_assessment(batch, Path(location), bounded, now)
    raw = read_receipt(batch, pending["offer"]["batch_id"], assessment="assess-results") if pending else None
    reply = checked_reply(batch, pending, raw, datetime.now(batch.feature.TAIPEI)) if raw is not None else {}
    _need(not reply or reply["as_of"] == now.date().isoformat(), "evening_results_assessment_crossed_day")
    states, selected = selection(targets, {
        "games": {key: game for key, game in reply.get("games", {}).items() if key in bounded},
    })
    batch.run.detail["evening_result_source"] = {
        "state": "assessed" if raw is not None else "assessment_pending", "games": states,
    }
    if not selected:
        return "unchanged"
    attempts = state.setdefault("www_requests", {})

    def fetch(key):
        kind = key[1]
        attempts[kind] = evening._iso(now)
        for event in evening.open_events(state).values():
            if event["key"] in game_selected and event["key"].split("-")[1] == kind:
                event.setdefault("attempts", []).append(evening._iso(now))
        if kind == evening.FARM_FINAL_KIND:
            state["farm_final"].setdefault("attempts", []).append(evening._iso(now))
        evening.save_json(path, state)
        try:
            return _read_schedule(state, key)
        except Exception as exc:
            errors = [{"kind": kind, "error": str(exc)}]
            evening.note_challenge(state, now, errors)
            evening.save_json(path, state)
            raise

    game_selected = {}
    signal_selected = {}
    for key, fields in selected.items():
        game_fields = {name: digest for name, digest in fields.items() if name != "signals"}
        if game_fields:
            game_selected[key] = game_fields
        if "signals" in fields:
            signal_selected[key] = fields["signals"]
    records = collect(game_selected, fetch)
    with conn() as connection:
        verified = _store_games(connection, records)
        for key in _store_signals(connection, state, signal_selected, year):
            verified.setdefault(key, []).append("signals")
        if verified:
            # Persist the mask before the database commit, so recovery cannot send an unscoped diff.
            state["pi_result_field_scope"] = {
                "assessment": {name: reply[name] for name in ("batch_id", "response_sha256")},
                "fields": verified,
            }
            state["last_run"] = {
                "at": evening._iso(now), "action": "scrape", "outcome": "changed", "errors": [],
            }
            evening.save_json(path, state)
    batch.run.detail["evening_result_source"]["verified_fields"] = verified
    batch.run.detail["evening_result_source"]["pending_fields"] = {
        key: sorted(name for name in names if name not in verified.get(key, ()))
        for key, names in selected.items() if set(names) - set(verified.get(key, ()))
    }
    return "changed" if verified else "unchanged"
