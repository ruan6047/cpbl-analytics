"""Track only changed nightly result and signal keys until all receipts arrive."""

from pi_evening_handoff import _out, prepare, transmit
from pi_job_handoff import snapshot_rows
from psycopg import sql

from cpbl.db import conn
from cpbl.ingest import boxpa_sync, daily_current_handoff, postseason_evening

TABLES = {
    "results": ("games", "game_schedule_status_revisions", "game_source_revisions"),
    "signals": ("official_change_signals",),
}
KINDS = {"results": ("A", "C", "E", "F"), "signals": ("C", "E")}


def _filter(table):
    return sql.SQL(" AND source='schedule'") if table == "game_source_revisions" else sql.SQL("")


def _fingerprints(connection, year):
    output = {}
    for part, tables in TABLES.items():
        games = {}
        for table in tables:
            # All authoritative versions are material; volatile repeat-observation counters are not.
            query = sql.SQL(
                "SELECT year,kind_code,game_sno, md5(string_agg(payload,',' ORDER BY payload)) FROM "
                "(SELECT year,kind_code,game_sno, (to_jsonb(src) - 'id' - 'last_seen_at' - 'seen_count')::text AS "
                "payload FROM cpbl.{} src WHERE year=%s AND kind_code=ANY(%s){}) parts "
                "GROUP BY year,kind_code,game_sno",
            ).format(sql.Identifier(table), _filter(table))
            for y, kind, game, digest in connection.execute(query, (year, list(KINDS[part]))).fetchall():
                games.setdefault(f"{y}-{kind}-{game}", {})[table] = digest
        output[part] = games
    return {"year": year, "tables": output}


def _scope_packets(connection, before, after, field_scope=None):
    if before["year"] != after["year"]:
        raise ValueError("pi_night_baseline_year")
    changes = {}
    for part, old in before["tables"].items():
        current = after["tables"][part]
        if old.keys() - current.keys():
            raise ValueError("pi_night_deletion_not_representable")
        changes[part] = {key for key, value in current.items() if value != old.get(key)}
    if field_scope is not None:
        # Production may lack a field already present in the Pi database.
        planned = field_scope["fields"]
        changes = {"results": {key for key, fields in planned.items() if set(fields) - {"signals"}},
                   "signals": {key for key, fields in planned.items() if "signals" in fields}}
    overlap = changes["results"] & changes["signals"]
    chunks = [(("results", "signals"), overlap)]
    chunks.extend(((part,), keys-overlap) for part, keys in changes.items())
    for parts, names in chunks:
        keys = sorted((int(y), kind, int(game)) for y, kind, game in (k.split("-") for k in names))
        for offset in range(0, len(keys), boxpa_sync.MAX_GAMES):
            batch = keys[offset:offset+boxpa_sync.MAX_GAMES]
            locations = sql.SQL("(year,kind_code,game_sno) IN ({})").format(
                sql.SQL(", ").join([sql.SQL("(%s,%s,%s)")] * len(batch)),
            )
            params = tuple(v for key in batch for v in key)
            packet = {"columns": {}, "data": {}}
            for part in parts:
                for table in TABLES[part]:
                    cols = daily_current_handoff.TABLE_LAYOUTS[table][1].split()
                    payload = snapshot_rows(connection, {table: cols}, where=locations + _filter(table), params=params)
                    for group in packet:
                        packet[group].update(payload[group])
            yield batch, parts, packet


def after_worker(batch, *, expected):
    path = postseason_evening.state_path()
    state = postseason_evening.load_state(path)
    before = state["pi_result_baseline"]
    scope = state.get("pi_result_field_scope")
    with conn() as connection, connection.transaction():
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        after = _fingerprints(connection, before["year"])
        packets = list(_scope_packets(connection, before, after, scope))
    if not packets:
        if expected:
            raise ValueError("pi_night_unbound_result_scope")
        return None
    if scope is None:
        raise ValueError("pi_night_result_field_scope_required")
    ids = []
    for games, parts, payload in packets:
        keys = {f"{year}-{kind}-{sno}" for year, kind, sno in games}
        payload["fields"] = {key: sorted(scope["fields"][key]) for key in sorted(keys)}
        payload["assessment"] = scope["assessment"]
        ids.append(prepare(batch, games, parts, payload, {}, result_group=True))
    state["pi_result_group"] = {"batch_ids": ids, "next_baseline": after}
    postseason_evening.save_json(path, state)
    return _transmit_next(batch, ids)


def _transmit_next(batch, ids):
    root = _out(batch)
    for name in ids:
        if not (root / name / "transport-attempt").exists():
            return transmit(batch, name)
    raise ValueError("pi_night_group_has_no_unattempted_batch")


def before_worker(batch, step):
    batch.night_results = True
    path = postseason_evening.state_path()
    state = postseason_evening.load_state(path)
    group = state.get("pi_result_group")
    if group is not None:
        if set(group["batch_ids"]) <= (state.get("boxpa_receipts") or {}).keys():
            code, outcome = step("record-sync", "--code", "0", "--pi-result-group")
            return code or (0 if outcome == "synced" else 69)
        return _transmit_next(batch, group["batch_ids"])
    if "pi_result_baseline" in state:
        return after_worker(batch, expected=False)
    if (state.get("signals_unsynced") or state.get("pending_sync")
            or (state.get("last_run") or {}).get("outcome") == "changed"):
        raise ValueError("pi_night_prior_unbound_progress")
    year = postseason_evening._season_year(batch.run.now)
    with conn() as connection, connection.transaction():
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        state["pi_result_baseline"] = _fingerprints(connection, year)
    postseason_evening.save_json(path, state)
    return None
