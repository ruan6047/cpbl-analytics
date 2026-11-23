"""Validate a scoped nightly batch and expose only an exact, authenticated receipt lookup."""

import hashlib
import json
import os
import re
import sys
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from psycopg import sql

from cpbl.features.handoff import MAX_MANIFEST, SHA, SOURCE_ID, _need, _object, _read
from cpbl.ingest import boxpa_sync, evening_results_handoff, pa_snapshot_handoff, weekly_box_handoff
from cpbl.ingest.cpbl_pitch_tracking import _COLS, _FLAG_COLS
from cpbl.ingest.daily_derived_handoff import _apply
from cpbl.ingest.scoped_snapshot_receiving import MAX_SNAPSHOT

NAMESPACE = "evening-boxpa"
BATCH_ID = re.compile(r"[0-9a-f]{32}")
MAX_RECEIPT = 64 * 1024
BOX_TABLES = (*boxpa_sync.BOX_TABLES, "game_livelog_extra", "game_source_revisions")
BOX_LAYOUTS = {
    name: weekly_box_handoff.TABLES[name]
    for name in BOX_TABLES
    if name in weekly_box_handoff.TABLES
}
BOX_LAYOUTS.update({
    "pitch_tracking": (5, _COLS + ",pitch_type_pred,pitch_type_pred_v2"),
    "pitching_game_flags": (4, _FLAG_COLS + ",source_fetched_at"),
    "game_detail": (
        3, "year,kind_code,game_sno,attendance,game_time,head_umpire,first_umpire,second_umpire,"
        "third_umpire,left_umpire,right_umpire,updated_at,weather_code,weather_desc,winning_type,attendance_backend",
    ),
})
BOX_LAYOUTS["game_source_revisions"] = (
    5, BOX_LAYOUTS["game_source_revisions"][1] + ",fetched_at,last_seen_at,seen_count",
)


def batch_id(source_id, as_of, games, parts, snapshot_sha256):
    body = dict(source_id=source_id, as_of=as_of, games=games, parts=parts, snapshot_sha256=snapshot_sha256)
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
                          ).hexdigest()[:32]


def _keys(games):
    _need(isinstance(games, list) and all(isinstance(g, list) and len(g) == 3
          and type(g[0]) is int and type(g[2]) is int and g[2] > 0 and g[1] in ("A", "E", "C")
          for g in games), "evening_game_keys")
    keys = boxpa_sync.parse_games(",".join("-".join(map(str, key)) for key in games))
    _need(games == [[key.year, key.kind_code, key.game_sno] for key in sorted(keys)], "evening_sorted_scope")
    return keys


def _read_request(root: Path, source_id: str, day, name: str):
    _need(bool(BATCH_ID.fullmatch(name)) and bool(SOURCE_ID.fullmatch(source_id)), "evening_batch_identity")
    inbox = root / "incoming"
    directory = inbox / NAMESPACE / name
    notify = inbox / f"{NAMESPACE}-notify"
    _need(root.is_absolute() and directory.resolve() == directory and notify.resolve() == notify,
          "evening_inbox_path")
    response = _read(directory / "response.json", MAX_MANIFEST)
    response_sha = hashlib.sha256(response).hexdigest()
    notice = _object(_read(notify / f"{name}.ready", MAX_MANIFEST))
    _need(notice == {"version": 1, "batch_id": name, "response_sha256": response_sha}
          and type(notice["version"]) is int, "evening_notice")
    request = _object(response)
    _need(isinstance(request, dict) and set(request) == {
        "version", "source_id", "as_of", "batch_id", "games", "parts", "snapshot_sha256", "snapshot_bytes",
    } and type(request["version"]) is int and request["version"] == 1
        and (request["source_id"], request["as_of"], request["batch_id"]) == (source_id, day.isoformat(), name),
        "evening_response_identity")
    digest, parts = request["snapshot_sha256"], request["parts"]
    results = parts in evening_results_handoff.PARTS
    keys = evening_results_handoff.keys_for(request["games"]) if results else _keys(request["games"])
    _need((results or parts in (["box"], ["pa"], ["box", "pa"])) and isinstance(digest, str) and bool(SHA.fullmatch(digest))
          and name == batch_id(source_id, day.isoformat(), request["games"], parts, digest),
          "evening_scope_or_batch_hash")
    return {**request, "response_sha256": response_sha}, keys, directory


def read_incoming(root: Path, source_id: str, day, name: str):
    request, keys, directory = _read_request(root, source_id, day, name)
    digest = request["snapshot_sha256"]
    raw = _read(directory / "snapshot.json", MAX_SNAPSHOT)
    _need(type(request["snapshot_bytes"]) is int and len(raw) == request["snapshot_bytes"]
          and hashlib.sha256(raw).hexdigest() == digest, "evening_snapshot_digest")
    return request, keys, _object(raw)


def _prepare_box(box, keys):
    _need(isinstance(box, dict) and set(box) == {"columns", "data"}
          and set(box["columns"]) == set(box["data"]) == set(BOX_TABLES), "evening_box_tables")
    scope = {(key.year, key.kind_code, key.game_sno) for key in keys}
    result = {}
    for table, (size, header) in BOX_LAYOUTS.items():
        own = header.split(",")
        supplied = box["columns"][table]
        allowed = set(own) | ({"id"} if table == "game_source_revisions" else set())
        _need(isinstance(supplied, list) and len(set(supplied)) == len(supplied)
              and set(supplied) in (allowed, set(own)), "evening_box_columns")
        documents, used = [], set()
        _need(isinstance(box["data"][table], list), "evening_box_records")
        for row in box["data"][table]:
            _need(isinstance(row, list) and len(row) == len(supplied), "evening_box_record")
            obj = dict(zip(supplied, row, strict=True))
            game = obj["year"], obj["kind_code"], obj["game_sno"]
            natural = tuple(obj[column] for column in own[:size])
            _need(game in scope and natural not in used and all(type(value) in (int, str) for value in natural),
                  "evening_box_row_scope")
            if table == "game_source_revisions":
                _need(obj["source"] in boxpa_sync.BOX_REVISION_SOURCES, "evening_box_revision_source")
            used.add(natural)
            documents.append({name: obj[name] for name in own})
        result[table] = (own, size, documents)
    return result


def _game_count(connection, table, key):
    return connection.execute(sql.SQL(
        "SELECT count(*) FROM {} WHERE (year,kind_code,game_sno)=(%s,%s,%s)"
    ).format(sql.Identifier("cpbl", table)), (key.year, key.kind_code, key.game_sno)).fetchone()[0]


def _table_fingerprint(connection, table, key):
    columns = BOX_LAYOUTS[table][1].split(",")
    timestamps = {"source_fetched_at", "fetched_at", "last_seen_at", "updated_at"}
    expressions = [
        sql.SQL("extract(epoch from {})").format(sql.Identifier(column))
        if column in timestamps else sql.Identifier(column)
        for column in columns
    ]
    query = sql.SQL(
        "SELECT jsonb_build_array({columns}) AS line FROM {table} "
        "WHERE (year,kind_code,game_sno)=(%s,%s,%s) ORDER BY line"
    ).format(columns=sql.SQL(",").join(expressions), table=sql.Identifier("cpbl", table))
    digest = hashlib.sha256()
    for (line,) in connection.execute(query, (key.year, key.kind_code, key.game_sno)):
        digest.update(json.dumps(line, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode())
        digest.update(b"\n")
    return digest.hexdigest()


def _publish_box(connection, keys, prepared, result):
    revisions = prepared["game_source_revisions"][2]
    checked = {(r["year"], r["kind_code"], r["game_sno"], r["source"]) for r in revisions}
    _need(checked == {(k.year, k.kind_code, k.game_sno, s)
                     for k in keys for s in boxpa_sync.BOX_REVISION_SOURCES}, "evening_box_observation_coverage")
    current = boxpa_sync.current_source_revisions(_Reader(connection), keys)
    for key in keys:
        result[key.text]["box_revisions"] = {}
        for source in boxpa_sync.BOX_REVISION_SOURCES:
            observed = [row for row in revisions
                        if (row["year"], row["kind_code"], row["game_sno"], row["source"])
                        == (key.year, key.kind_code, key.game_sno, source)]
            latest = max(observed, key=lambda row: datetime.fromisoformat(row["last_seen_at"]))
            target = current[key.text][source]
            received = datetime.fromisoformat(latest["last_seen_at"]).timestamp()
            _need(target is None or received >= float(target[2]), "evening_box_newer_target_revision")
            result[key.text]["box_revisions"][source] = latest["source_version"]

    changed = set()
    for table, (columns, size, docs) in prepared.items():
        for key in keys:
            game = (key.year, key.kind_code, key.game_sno)
            subset = [row for row in docs if tuple(row[col] for col in ("year", "kind_code", "game_sno")) == game]
            matches = _apply(connection, table, columns, size, subset, insert=True, write=False)
            replace_extra = table == "game_livelog_extra" and _game_count(connection, table, key) != len(subset)
            if matches == len(subset) and not replace_extra:
                continue
            if table == "game_livelog_extra":
                connection.execute(
                    "DELETE FROM cpbl.game_livelog_extra WHERE (year,kind_code,game_sno)=(%s,%s,%s)", game,
                )
            _apply(connection, table, columns, size, subset, insert=True)
            changed.add(key.text)

    observed_after = boxpa_sync.current_source_revisions(_Reader(connection), keys)
    for key in keys:
        params = key.year, key.kind_code, key.game_sno
        game = result[key.text]
        for table in boxpa_sync.BOX_TABLES:
            expected = sum(tuple(row[name] for name in ("year", "kind_code", "game_sno")) == params
                           for row in prepared[table][2])
            count = _game_count(connection, table, key)
            _need(count == expected, "evening_box_scope_count")
            game["box"][table] = {"local": expected, "prod": count}
        for source, digest in game["box_revisions"].items():
            after = observed_after[key.text][source]
            _need(after is not None and after[0] == digest, "evening_box_current_revision")
            game["box_revisions"][source] = {"local": after, "prod": after}
        game["box_fingerprints"] = {table: _table_fingerprint(connection, table, key) for table in BOX_TABLES}
        game["box_ok"] = True
        game["box_mode"] = "applied_missing_or_updated" if key.text in changed else "reused_existing"
    return changed


class _Reader:
    def __init__(self, connection):
        self.connection = connection

    def read(self, query):
        return [[str(value) if value is not None else "" for value in row]
                for row in self.connection.execute(query)]


def require_final(connection, keys):
    if boxpa_sync.prod_completed(_Reader(connection), keys) != {key.text for key in keys}:
        raise boxpa_sync.SyncError(boxpa_sync.EXIT_NOT_FINAL, "evening_target_not_completed")


def publish(connection, keys, parts, snapshot):
    _need(isinstance(snapshot, dict) and set(snapshot) == {"box", "pa", "predecessors"}
          and isinstance(snapshot["pa"], dict) and isinstance(snapshot["predecessors"], dict),
          "evening_snapshot_shape")
    ids, pa = {k.text for k in keys}, snapshot["pa"]
    require_final(connection, keys)
    _need(set(pa) <= ids and set(snapshot["predecessors"]) <= set(pa)
          and bool(pa) == ("pa" in parts) and (snapshot["box"] is not None) == ("box" in parts),
          "evening_snapshot_parts")
    result = {key.text: {"box": {}, "box_ok": None, "pa": {}, "pa_ok": None, "pa_sent": False,
                         "published_build_local": None, "published_build_prod": None}
              for key in keys}
    reused = True
    if "box" in parts:
        reused = not _publish_box(connection, keys, _prepare_box(snapshot["box"], keys), result)
    for key in sorted(keys):
        if key.text not in pa:
            continue
        prepared = pa[key.text]
        previous = snapshot["predecessors"].get(key.text)
        _need(previous is None or isinstance(previous, str), "evening_predecessor_identity")
        calc_id = prepared["data"]["game_recap_builds"][0][prepared["columns"]["game_recap_builds"].index("build_id")]
        counts = pa_snapshot_handoff.verify_published(connection, key, prepared, calc_id)
        if counts is None:
            counts = pa_snapshot_handoff.publish_new(connection, key, prepared, expected_previous=previous)
            reused = False
            result[key.text]["pa_mode"] = "published"
        else:
            result[key.text]["pa_mode"] = "reused_existing"
        build = connection.execute(
            "SELECT build_id::text FROM cpbl.game_recap_builds "
            "WHERE (year,kind_code,game_sno)=(%s,%s,%s) AND state='published'",
            (key.year, key.kind_code, key.game_sno),
        ).fetchone()[0]
        cols = prepared["columns"]["game_recap_builds"]
        source_build = prepared["data"]["game_recap_builds"][0][cols.index("build_id")]
        _need(build == source_build, "evening_pa_build_reconciliation")
        result[key.text].update(
            pa={table: {"local": count, "prod": count} for table, count in counts.items()},
            pa_ok=True, pa_sent=True, published_build_local=source_build, published_build_prod=build,
        )
    return {"ok": True, "games": result, "delivery_mode": "reused_existing" if reused else "committed"}


def reuse_status(connection, keys, expected=None):
    """Assess only the authorized batch scope against its private accepted DB evidence."""
    finished = boxpa_sync.prod_completed(_Reader(connection), keys)
    revisions = boxpa_sync.current_source_revisions(_Reader(connection), keys)
    result = {}
    for key in keys:
        old = (expected or {}).get(key.text, {})
        expected_box = old.get("box_fingerprints", {})
        box = {table: _table_fingerprint(connection, table, key) for table in BOX_TABLES}
        box_versions = {kind: entry[:2] if entry else None for kind, entry in revisions[key.text].items()}
        missing = []
        if key.text not in finished:
            missing.append("final")
        if any(expected_box.get(table) != box[table] for table in BOX_TABLES
               if table not in ("pitch_tracking", "pitching_game_flags")) or any(
            not old.get("box_revisions", {}).get(kind, {}).get("prod")
            or old["box_revisions"][kind]["prod"][:2] != version for kind, version in box_versions.items()
        ):
            missing.append("www_box")
        if any(expected_box.get(table) != box[table] for table in ("pitch_tracking", "pitching_game_flags")):
            missing.append("stats_tracking")
        build = connection.execute(
            "SELECT build_id::text FROM cpbl.game_recap_builds "
            "WHERE (year,kind_code,game_sno)=(%s,%s,%s) AND state='published'",
            (key.year, key.kind_code, key.game_sno),
        ).fetchone()
        if build is None or build[0] != old.get("published_build_prod") or missing:
            missing.append("pa")
        result[key.text] = {"reuse": not missing, "missing_or_unverified": missing}
    return result


def receipt_path(root: Path, source_id: str, name: str) -> Path:
    _need(root.is_absolute() and bool(SOURCE_ID.fullmatch(source_id)) and bool(BATCH_ID.fullmatch(name)),
          "evening_receipt_identity")
    directory = root / source_id
    _need(directory.resolve() == directory, "evening_receipt_path")
    return directory / f"{name}.json"


class DispatchBlocked(ValueError):
    def __init__(self, batch_id: str, reason: str):
        super().__init__(reason)
        self.batch_id = batch_id


def pending_batches(inbox: Path, receipts: Path, source: str, now: datetime):
    """Discover the currently accepted batch IDs without replaying retained old notifications."""
    tz = ZoneInfo("Asia/Taipei")
    day = now.astimezone(tz).date()
    notify = inbox / "incoming" / f"{NAMESPACE}-notify"
    _need(inbox.is_absolute() and notify.resolve() == notify and notify.is_dir(), "evening_dispatch_notify")
    items = []
    for path in sorted(notify.glob("*.ready")):
        _need(bool(BATCH_ID.fullmatch(path.stem)) and not path.is_symlink() and path.is_file(),
              "evening_dispatch_notice_shape")
        stamp = path.lstat().st_mtime
        received = datetime.fromtimestamp(stamp, tz)
        _need(received <= now, "evening_dispatch_future_notice")
        if received.date() != day:
            continue
        request, _, _ = _read_request(inbox, source, day, path.stem)
        receipt = receipt_path(receipts, source, path.stem)
        if os.path.lexists(receipt):
            prior = read_receipt(receipts, source, path.stem)
            if prior["response_sha256"] != request["response_sha256"]:
                raise DispatchBlocked(path.stem, "evening_dispatch_receipt_conflict")
            continue
        if os.path.lexists(receipt.with_suffix(".attempt")):
            raise DispatchBlocked(path.stem, "evening_dispatch_outcome_unknown")
        priority = 0 if request["parts"] in evening_results_handoff.PARTS else 1
        items.append((priority, stamp, path.stem))
    return [name for _, _, name in sorted(items)]


def read_receipt(root: Path, authenticated_source_id: str, name: str) -> dict:
    """The caller supplies a server-side bound source, never a source chosen by the requester."""
    path = receipt_path(root, authenticated_source_id, name)
    out = _object(_read(path, MAX_RECEIPT))
    _need(isinstance(out, dict) and type(out.get("rc")) is int
          and (out.get("source_id"), out.get("batch_id"), out.get("rc")) == (authenticated_source_id, name, 0) and out.get("manifest", {}).get("ok") is True,
          "evening_receipt_identity")
    return out


def assess_own_receipt(connection, root: Path, authenticated_source_id: str, name: str) -> dict:
    """Trusted VPS-only assessment. The selected batch supplies the scope, not the caller."""
    receipt = read_receipt(root, authenticated_source_id, name)
    return reuse_status(connection, _keys(receipt["games"]), receipt["manifest"]["games"])


def sync_directory(directory: Path):
    fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def write_receipt(path: Path, response, manifest, now: datetime) -> None:
    raw = {key: response[key] for key in (
        "version", "source_id", "as_of", "batch_id", "games", "parts", "snapshot_sha256", "response_sha256",
    )}
    value = {**raw, "published_at": now.isoformat(), "rc": 0, "manifest": {**manifest, "at": now.isoformat()}}
    encoded = (json.dumps(value, sort_keys=True, ensure_ascii=False) + "\n").encode()
    _need(len(encoded) <= MAX_RECEIPT, "evening_receipt_size")
    temp = path.with_suffix(".pending-receipt")
    with temp.open("xb") as handle:
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())
    os.link(temp, path)  # Separate the private receipt from the uploader.
    temp.unlink()
    sync_directory(path.parent)


class AssessmentExpired(ValueError):
    """An accepted assessment binding is no longer authority to act."""


def _initial_assessment_binding(binding_root: Path, inbox: Path, source: str, batch_id: str, now: datetime):
    """An uploader request is identity evidence; only the server binding grants the lookup scope."""
    binding = _object(_read(receipt_path(binding_root, source, batch_id), MAX_RECEIPT))
    _need(isinstance(binding, dict) and set(binding) == {
        "version", "source_id", "batch_id", "as_of", "games", "parts", "response_sha256", "expires_at", "expected",
    } and type(binding["version"]) is int and binding["version"] == 1
        and (binding["source_id"], binding["batch_id"]) == (source, batch_id),
        "evening_initial_binding_identity")
    day = date.fromisoformat(binding["as_of"])
    expires = datetime.fromisoformat(binding["expires_at"])
    _need(expires.utcoffset() is not None, "evening_initial_binding_timezone")
    if day != now.astimezone(ZoneInfo("Asia/Taipei")).date() or now >= expires:
        raise AssessmentExpired("evening_initial_binding_expired")
    request, keys, _ = _read_request(inbox, source, day, batch_id)
    _need(all(request[name] == binding[name] for name in ("games", "parts", "response_sha256")),
          "evening_initial_binding_scope")
    expected = binding["expected"]
    _need(isinstance(expected, dict) and expected.keys() <= {key.text for key in keys}
          and all(isinstance(value, dict) for value in expected.values()), "evening_initial_expected_scope")
    return request, keys, expected


def _assessment_scope(root, source, batch_id, now):
    try:
        receipt = read_receipt(root, source, batch_id)
    except FileNotFoundError:
        bindings = os.environ.get("CPBL_EVENING_ASSESSMENT_BINDINGS_ROOT")
        inbox = os.environ.get("CPBL_EVENING_ASSESSMENT_INBOX_ROOT")
        if not bindings or not inbox:
            raise
        request, keys, expected = _initial_assessment_binding(Path(bindings), Path(inbox), source, batch_id, now)
        return request, keys, expected, True
    return receipt, _keys(receipt["games"]), receipt["manifest"]["games"], False


def assessment(root, source, batch_id):
    from cpbl.db import conn

    _need(bool(os.environ.get("DATABASE_URL")), "evening_assessment_dsn_required")
    now = datetime.now().astimezone()
    subject, keys, expected, initial = _assessment_scope(root, source, batch_id, now)
    parts = subject["parts"]
    _need(parts not in evening_results_handoff.PARTS, "evening_results_assessment_not_applicable")
    allowed = {"final"}
    if "box" in parts:
        allowed.update(("www_box", "stats_tracking"))
    if "pa" in parts:
        allowed.add("pa")
    with conn() as c, c.transaction():
        c.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        advisory = reuse_status(c, keys, expected)
        for key in keys:
            result = advisory[key.text]
            missing = [item for item in result["missing_or_unverified"] if item in allowed]
            proof = expected.get(key.text, {}).get("box") or {}

            def should_exist(table):
                if not initial and table != "pitch_tracking":
                    return True
                count = proof.get(table, {}).get("prod", 0)
                return type(count) is int and count > 0

            confirmed = []
            if "final" not in missing:
                if "www_box" in missing and any(
                    should_exist(table) and _game_count(c, table, key) == 0
                    for table in boxpa_sync.BOX_TABLES if table not in ("pitch_tracking", "pitching_game_flags")
                ):
                    confirmed.append("www_box")
                if "stats_tracking" in missing and any(
                    should_exist(table) and _game_count(c, table, key) == 0
                    for table in ("pitch_tracking", "pitching_game_flags")
                ):
                    confirmed.append("stats_tracking")
            result.update(reuse=not missing, missing_or_unverified=missing, confirmed_missing=confirmed)
    return {
        "version": 1, "source_id": source, "as_of": subject["as_of"], "batch_id": batch_id,
        "response_sha256": subject["response_sha256"], "checked_at": now.isoformat(), "games": advisory,
    }


def result_assessment(source: str, name: str):
    from cpbl.db import conn
    from cpbl.ingest import evening_result_fields

    now = datetime.now().astimezone()
    binding, keys, plans = result_binding(source, name, now)
    _need(bool(os.environ.get("DATABASE_URL")), "evening_assessment_dsn_required")
    with conn() as connection, connection.transaction():
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        fields = evening_result_fields.assess(connection, keys, plans)
    return {"version": 1, "source_id": source, "as_of": binding["as_of"], "batch_id": name,
            "response_sha256": binding["response_sha256"], "checked_at": now.isoformat(), "games": fields}


def result_binding(source: str, name: str, now: datetime):
    from cpbl.ingest import evening_result_fields

    roots = [os.environ.get(key) for key in ("CPBL_EVENING_ASSESSMENT_BINDINGS_ROOT",
                                            "CPBL_EVENING_RESULT_ASSESSMENT_INBOX_ROOT")]
    if not all(roots):
        raise FileNotFoundError("evening_result_assessment_not_bound")
    binding, keys, expected = _initial_assessment_binding(
        Path(roots[0]), Path(roots[1]), source, name, now,
    )
    _need(binding["parts"] in evening_results_handoff.PARTS, "evening_result_assessment_parts")
    plans = evening_result_fields.expectations(keys, expected)
    _need(all(all(("signals" if field == "signals" else "results") in binding["parts"] for field in plan)
              for plan in plans.values()), "evening_result_assessment_field_parts")
    return binding, keys, plans


def main(argv=None) -> int:
    """Forced-command candidate. Source and receipt root come from trusted server configuration."""
    args = sys.argv[1:] if argv is None else argv
    operation = args[0] if len(args) == 2 else None
    if (len(args) != 1 and operation not in ("assess", "assess-results")) or not BATCH_ID.fullmatch(args[-1]):
        return 64
    try:
        root = Path(os.environ["CPBL_EVENING_RECEIPT_ROOT"])
        source = os.environ["CPBL_EVENING_RECEIPT_SOURCE_ID"]
        if operation == "assess-results":
            receipt = result_assessment(source, args[-1])
        elif operation == "assess":
            receipt = assessment(root, source, args[-1])
        else:
            receipt = read_receipt(root, source, args[0])
    except FileNotFoundError:
        return 75
    except AssessmentExpired:
        return 75 if operation == "assess-results" else 74
    except (OSError, KeyError, ValueError):
        return 74
    print(json.dumps(receipt, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
