"""Receive and publish the fixed Pi team-comparison snapshot."""
import hashlib
from pathlib import Path

from psycopg.types.json import Jsonb

from cpbl.features.handoff import MAX_MANIFEST, SHA, _need, _object, _read, run_id
from cpbl.playoffs.team_comparison import sync

MAX_SNAPSHOT = 64 * 1024 * 1024


def read_incoming(root: Path, source_id: str, day):
    key = run_id(source_id, day)
    directory = root / "incoming" / "team-comparison" / key
    notify = root / "incoming" / "team-comparison-notify"
    _need(root.is_absolute() and directory.resolve() == directory and notify.resolve() == notify,
          "summary_inbox_path")
    notice = _object(_read(notify / f"{key}.ready", MAX_MANIFEST))
    _need(isinstance(notice, dict) and set(notice) == {"version", "run_id", "response_sha256"}
          and type(notice["version"]) is int and notice["version"] == 1 and notice["run_id"] == key,
          "summary_notice_identity")
    response = _read(directory / "response.json", MAX_MANIFEST)
    response_sha = hashlib.sha256(response).hexdigest()
    _need(notice["response_sha256"] == response_sha, "summary_response_digest")
    manifest = _object(response)
    _need(isinstance(manifest, dict) and set(manifest) == {
        "version", "source_id", "run_id", "as_of", "snapshot_sha256", "snapshot_bytes",
    } and type(manifest["version"]) is int and manifest["version"] == 1
          and manifest["source_id"] == source_id and manifest["run_id"] == key
          and manifest["as_of"] == day.isoformat(), "summary_response_identity")
    size, digest = manifest["snapshot_bytes"], manifest["snapshot_sha256"]
    _need(type(size) is int and 0 < size <= MAX_SNAPSHOT and isinstance(digest, str) and SHA.fullmatch(digest),
          "summary_snapshot_limit")
    raw = _read(directory / "snapshot.json", size)
    _need(len(raw) == size and hashlib.sha256(raw).hexdigest() == digest, "summary_snapshot_digest")
    snapshot = _object(raw)
    _need(isinstance(snapshot, dict) and set(snapshot) == {"columns", "data"}
          and isinstance(snapshot["columns"], dict) and not sync.column_drift(snapshot["columns"]),
          "summary_snapshot_columns")
    doc = snapshot["data"]
    _need(isinstance(doc, dict) and set(doc) == {"builds", "rows", "current"}, "summary_snapshot_tables")
    for name, cols, keys in (
        ("builds", sync.BUILD_COLUMNS, ("build_id",)),
        ("rows", sync.ROW_COLUMNS, ("build_id", "scope", "team_code", "opponent_code")),
        ("current", sync.CURRENT_COLUMNS, ("year", "kind_code")),
    ):
        records = doc[name]
        _need(isinstance(records, list) and all(isinstance(row, dict) and set(row) == set(cols)
                                                for row in records), "summary_snapshot_rows")
        _need(len({tuple(row[k] for k in keys) for row in records}) == len(records), "summary_duplicate_keys")
    source = sync.normalize(doc)
    _need(source.builds and source.current and not sync.self_check(source), "summary_snapshot_self_check")
    return {**manifest, "response_sha256": response_sha}, source


class _TransactionReader:
    def __init__(self, connection):
        self.connection = connection

    def read(self, sql):
        return self.connection.execute(sql).fetchone()[0]


def publish(connection, source):
    """Use the original plan and writes, with validation and reconciliation before commit."""
    from psycopg import sql

    reader = _TransactionReader(connection)
    # Preserve the lock order in the original payload (build, rows, then current).
    tables = sql.SQL(", ").join(sql.Identifier("cpbl", name) for name in sync.TABLE_COLUMNS)
    connection.execute(sql.SQL("LOCK TABLE {} IN SHARE ROW EXCLUSIVE MODE").format(tables))
    if sync.column_drift(_object(reader.read(sync.COLUMNS_SQL).encode())):
        raise sync.SyncError(sync.EXIT_NO_TABLE, "summary_target_columns")
    target = sync.read_target(reader)
    plan = sync.plan(source, target)
    if plan.state == "reject":
        raise sync.SyncError(sync.EXIT_REJECT, "summary_conflicting_target")
    for key, existing in target.current.items():
        incoming = source.current[key]
        current_at, incoming_at = existing["promoted_at"], incoming["promoted_at"]
        pending_at, incoming_pending = existing["pending_since"], incoming["pending_since"]
        if (incoming_at < current_at
                or (incoming_at == current_at and incoming["build_id"] != existing["build_id"])
                or (pending_at and (incoming_pending or incoming_at) < pending_at)):
            raise sync.SyncError(sync.EXIT_REJECT, "summary_stale_current")
    if plan.state == "insert-pending":
        connection.execute("CREATE TEMP TABLE _tc_sync_payload (doc jsonb NOT NULL) ON COMMIT DROP")
        connection.execute("INSERT INTO _tc_sync_payload (doc) VALUES (%s)", (Jsonb(sync.payload(source, plan)),))
        connection.execute(sync.apply_statements(), prepare=False)
    if not sync.reconcile(source, sync.read_target(reader))[0]:
        raise sync.SyncError(sync.EXIT_RECONCILE, "summary_reconcile_failed")
    return plan.state
