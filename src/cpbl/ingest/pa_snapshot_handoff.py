"""Bind one already-published Pi PA build to equivalent target source rows."""

from collections import defaultdict

from psycopg import sql
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from cpbl.features.handoff import _need
from cpbl.ingest import boxpa_sync, pa_build
from cpbl.ingest.daily_derived_handoff import _apply

TABLES = boxpa_sync.PA_TABLES


def _records(snapshot, key, connection):
    _need(isinstance(snapshot, dict) and set(snapshot) == {"columns", "data"}
          and set(snapshot["columns"]) == set(snapshot["data"]) == set(TABLES), "pa_snapshot_tables")
    out = {}
    for table in TABLES:
        columns = snapshot["columns"][table]
        actual = connection.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_schema='cpbl' AND table_name=%s",
            (table,),
        ).fetchall()
        _need(isinstance(columns, list) and len(set(columns)) == len(columns)
              and set(columns) == {row[0] for row in actual}, "pa_snapshot_columns")
        raw = snapshot["data"][table]
        _need(isinstance(raw, list)
              and all(isinstance(row, list) and len(row) == len(columns) for row in raw),
              "pa_snapshot_rows")
        rows = [dict(zip(columns, row, strict=True)) for row in raw]
        _need(all((row["year"], row["kind_code"], row["game_sno"]) == key for row in rows),
              "pa_snapshot_scope")
        out[table] = rows
    return out


def _insert(connection, table, rows, *, identity=None, returning=False):
    if not rows:
        return []
    target = sql.Identifier("cpbl", table)
    columns = sql.SQL(",").join(sql.Identifier(name) for name in rows[0] if name != identity)
    query = sql.SQL(
        "INSERT INTO {target} ({columns}) SELECT {columns} FROM "
        "jsonb_populate_recordset(NULL::{target},%s)"
    ).format(target=target, columns=columns)
    if returning:
        query += sql.SQL(" RETURNING pa_row_id,pa_id::text")
    cursor = connection.execute(query, (Jsonb(rows),))
    _need(cursor.rowcount == len(rows), "pa_snapshot_insert_count")
    return cursor.fetchall() if returning else []


def _fingerprints(pas, events):
    members = defaultdict(list)
    for event in sorted(events, key=lambda row: row["event_position"]):
        members[event["pa_id"]].append(event["event_fingerprint"])
    return {
        row["pa_id"]: pa_build.compute_pa_fingerprint(
            members=members[row["pa_id"]],
            hitter=row["hitter_acnt"], end_hitter=row["end_hitter_acnt"],
            start_pitcher=row["start_pitcher_acnt"], end_pitcher=row["end_pitcher_acnt"],
            result_action=row["result_action"], start_event_no=row["start_event_no"],
            end_event_no=row["end_event_no"],
        )
        for row in pas
    }


def _validate_predecessor(cur, key, expected, build, live_sha, pas, events):
    pending = cur.execute(
        "SELECT 1 FROM cpbl.game_recap_builds WHERE (year,kind_code,game_sno)=(%s,%s,%s) "
        "AND state IN ('building','reconciliation_required') LIMIT 1", key,
    ).fetchone()
    _need(pending is None, "pa_snapshot_target_pending_review")
    current = pa_build._published_build_meta(cur, *key)
    if expected is None:
        _need(current is None, "pa_snapshot_target_has_active_build")
        return
    _need(current is not None and str(current["build_id"]) == expected and expected != build["build_id"],
          "pa_snapshot_predecessor_mismatch")
    actual = cur.execute(
        "SELECT r.source_sha256, b.built_at < %s::timestamptz AS older "
        "FROM cpbl.game_recap_builds b JOIN cpbl.game_recap_source_revisions r ON r.id=b.livelog_revision_id "
        "WHERE b.build_id=%s", (build["built_at"], expected),
    ).fetchone()
    _need(actual is not None and actual["older"] and actual["source_sha256"] == live_sha
          and current["builder_version"] == build["builder_version"]
          and current["taxonomy_version"] == build["taxonomy_version"], "pa_snapshot_predecessor_drift")
    _need(_fingerprints(pas, events) == pa_build._published_pa_fingerprints(cur, *key),
          "pa_snapshot_predecessor_reconciliation_required")


def publish_new(connection, game: boxpa_sync.GameKey, snapshot, *, expected_previous: str | None = None):
    """Import a build, or atomically replace an explicitly pinned equivalent predecessor."""
    key = (game.year, game.kind_code, game.game_sno)
    prepared = _records(snapshot, key, connection)
    revisions, builds, pas, events, mappings = (prepared[name] for name in TABLES)
    _need(len(builds) == 1 and builds[0]["state"] == "published" and pas, "pa_snapshot_published")
    build = builds[0]
    _need(build.get("builder_version") == pa_build.BUILDER_VERSION
          and not build["validation_summary"].get("invariant_violations"), "pa_snapshot_builder")
    src = {row["id"]: row for row in revisions}
    expected_source = {"livelog": build["livelog_revision_id"]}
    if build["tracking_revision_id"] is not None:
        expected_source["tracking"] = build["tracking_revision_id"]
    _need(len(src) == len(revisions) == len(expected_source)
          and all(type(row["id"]) is int and row["parser_version"] == pa_build.PARSER_VERSION
                  and expected_source.get(row["source_kind"]) == row["id"] for row in revisions),
          "pa_snapshot_source_keys")
    parents = {row["pa_row_id"]: row["pa_id"] for row in pas}
    _need(len(parents) == len(pas) == len(set(parents.values()))
          and all(row["build_id"] == build["build_id"] for row in pas)
          and all(parents.get(row["pa_row_id"]) == row["pa_id"] for row in events + mappings)
          and all(row["source_revision_id"] == expected_source.get("tracking")
                  and row["build_id"] == build["build_id"] for row in mappings), "pa_snapshot_child_keys")

    cur = connection.cursor(row_factory=dict_row)
    pa_build.lock_game_for_build(cur, *key)
    _validate_predecessor(
        cur, key, expected_previous, build, src[expected_source["livelog"]]["source_sha256"], pas, events,
    )
    observed = {
        "livelog": pa_build._livelog_manifest(pa_build._fetch_events(cur, *key)),
        "tracking": pa_build._tracking_manifest(pa_build._fetch_pitches(cur, *key)),
    }
    for kind, identity in expected_source.items():
        row = src[identity]
        _need(observed[kind] == (row["source_sha256"], row["row_count"], row["max_source_key"]),
              "pa_snapshot_target_source_drift")
    _need("tracking" in expected_source or observed["tracking"][1] == 0, "pa_snapshot_target_tracking_drift")

    remap = {}
    for kind, identity in expected_source.items():
        digest, count, last = observed[kind]
        remap[identity] = pa_build.upsert_source_revision(
            cur, year=game.year, kind=game.kind_code, game=game.game_sno,
            source_kind=kind, sha256=digest, row_count=count, max_source_key=last,
        )
    build["livelog_revision_id"] = remap[build["livelog_revision_id"]]
    if build["tracking_revision_id"] is not None:
        build["tracking_revision_id"] = remap[build["tracking_revision_id"]]
    if expected_previous is not None:
        changed = cur.execute(
            "UPDATE cpbl.game_recap_builds SET state='superseded' WHERE build_id=%s AND state='published'",
            (expected_previous,),
        ).rowcount
        _need(changed == 1, "pa_snapshot_predecessor_update")
    _insert(connection, "game_recap_builds", builds)
    ids = _insert(connection, "game_plate_appearances", pas, identity="pa_row_id", returning=True)
    by_pa = {pa_id: identity for identity, pa_id in ids}
    _need(set(by_pa) == set(parents.values()), "pa_snapshot_target_parent_ids")
    for row in events + mappings:
        row["pa_row_id"] = by_pa[row["pa_id"]]
    for row in mappings:
        row["source_revision_id"] = remap[row["source_revision_id"]]
    _insert(connection, "game_pa_events", events, identity="id")
    _insert(connection, "game_pa_pitch_mappings", mappings, identity="id")
    _need(connection.execute(boxpa_sync.closure_violations_sql([game])).fetchone() is None,
          "pa_snapshot_target_scope_closure")
    return {table: len(rows) for table, rows in prepared.items()}



def verify_published(connection, game: boxpa_sync.GameKey, snapshot, build_id: str):
    """Return counts only when the same published build and all of its bound rows already match."""
    key = game.year, game.kind_code, game.game_sno
    cur = connection.cursor(row_factory=dict_row)
    pa_build.lock_game_for_build(cur, *key)
    current = pa_build._published_build_meta(cur, *key)
    if current is None or str(current["build_id"]) != build_id:
        return None
    prepared = _records(snapshot, key, connection)
    revisions, builds, pas, events, mappings = (prepared[name] for name in TABLES)
    _need(len(builds) == 1 and builds[0]["build_id"] == build_id and builds[0]["state"] == "published",
          "pa_reuse_build_identity")
    build = builds[0]
    measured = {
        "livelog": pa_build._livelog_manifest(pa_build._fetch_events(cur, *key)),
        "tracking": pa_build._tracking_manifest(pa_build._fetch_pitches(cur, *key)),
    }
    ids = {}
    for row in revisions:
        kind = row["source_kind"]
        revision = current.get(f"{kind}_revision_id")
        expected = (row["source_sha256"], row["row_count"], row["max_source_key"])
        target = connection.execute(
            "SELECT source_sha256,row_count,max_source_key FROM cpbl.game_recap_source_revisions WHERE id=%s",
            (revision,),
        ).fetchone()
        _need(target == measured.get(kind) == expected, "pa_reuse_source_drift")
        ids[row["id"]] = revision
    build["livelog_revision_id"] = ids[build["livelog_revision_id"]]
    if build["tracking_revision_id"] is not None:
        build["tracking_revision_id"] = ids[build["tracking_revision_id"]]

    pa_ids = dict(connection.execute(
        "SELECT pa_id::text,pa_row_id FROM cpbl.game_plate_appearances WHERE build_id=%s", (build_id,),
    ).fetchall())
    _need(set(pa_ids) == {row["pa_id"] for row in pas}, "pa_reuse_parent_scope")
    for row in pas + events + mappings:
        row["pa_row_id"] = pa_ids[row["pa_id"]]
    for row in mappings:
        row["source_revision_id"] = ids[row["source_revision_id"]]
    layout = {
        "game_recap_builds": (("build_id",), builds),
        "game_plate_appearances": (("pa_row_id",), pas),
        "game_pa_events": (("pa_row_id", "event_position"), events),
        "game_pa_pitch_mappings": (("build_id", "pitcher_acnt", "pitch_cnt"), mappings),
    }
    for name, (keys, rows) in layout.items():
        if not rows:
            continue
        columns = list(keys) + [field for field in rows[0] if field not in keys and field != "id"]
        expected = [{field: row[field] for field in columns} for row in rows]
        _need(_apply(connection, name, columns, len(keys), expected, insert=True, write=False) == len(rows),
              "pa_reuse_row_drift")
    event_count = connection.execute(
        "SELECT count(*) FROM cpbl.game_pa_events e JOIN cpbl.game_plate_appearances p USING (pa_row_id) "
        "WHERE p.build_id=%s", (build_id,),
    ).fetchone()[0]
    map_count = connection.execute(
        "SELECT count(*) FROM cpbl.game_pa_pitch_mappings WHERE build_id=%s", (build_id,),
    ).fetchone()[0]
    _need((event_count, map_count) == (len(events), len(mappings)), "pa_reuse_child_scope")
    return {table: len(rows) for table, rows in prepared.items()}
