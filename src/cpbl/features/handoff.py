"""Private Pi feature publication protocol. The VPS owns the final database write."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import logging
import math
import os
import re
import stat
import tempfile
from contextlib import contextmanager
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from psycopg import sql

from cpbl.features import outcome

VERSION = 1
TAIPEI = ZoneInfo("Asia/Taipei")
MAX_RESULTS = 64 * 1024 * 1024
MAX_MANIFEST = 8192
MAX_SCHEDULE = 8 * 1024 * 1024
SCHEDULE_FIELDS = {"schedule_bytes", "schedule_sha256"}
SOURCE_ID = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}\Z")
SHA = re.compile(r"[0-9a-f]{64}\Z")
KEY = ("year", "kind_code", "game_season_code", "game_sno")

# Columns used by the existing algorithm, in the stable order used for the snapshot receipt.
INPUTS = {
    "games": (*KEY, "game_date", "home_team_code", "home_team_name", "away_team_code",
              "away_team_name", "home_score", "away_score", "home_starter_id", "away_starter_id"),
    "game_completion_evidence": ("year", "kind_code", "game_sno"),
    "game_schedule_status_revisions": (
        "year", "kind_code", "game_sno", "raw_present_status", "raw_game_result",
        "raw_game_date", "last_seen_at", "fetched_at", "payload_hash",
    ),
    "pitching_gamelog": ("year", "kind_code", "game_sno", "pitcher_acnt", "earned_runs",
                         "hits", "bb", "so", "inning_pitched_cnt", "inning_pitched_div3",
                         "visiting_home_type", "wild_pitch"),
    "pitching_seasons": ("player_id", "year", "team_id", "er", "h", "bb", "so", "ip"),
    "batting_gamelog": ("year", "kind_code", "game_sno", "visiting_home_type", "at_bats",
                        "hits", "bb", "hbp", "total_bases", "sac_fly", "sb", "cs", "errors"),
    "batting_seasons": ("year", "team_id", "ab", "h", "tb", "bb", "hbp", "sf"),
}
TEXT_COLUMNS = frozenset((
    "kind_code", "game_season_code", "home_team_code", "home_team_name",
    "away_team_code", "away_team_name",
))
INT_COLUMNS = frozenset(("year", "game_sno", "season", "home_win"))
MANIFEST_FIELDS = frozenset((
    "version", "source_id", "run_id", "as_of", "refresh_finished_at", "snapshot_at",
    "algorithm_sha256", "input_sha256", "result_sha256", "result_bytes", "row_count",
))
PI_DATABASE = "cpbl393_feature_bench"
log = logging.getLogger(__name__)


def _need(condition, reason):
    if not condition:
        raise ValueError(reason)


def algorithm_sha256():
    # The publisher runs the same version as the Pi, including the completion predicate.
    from cpbl import completion

    h = hashlib.sha256()
    for module in (outcome, completion):
        h.update(Path(module.__file__).read_bytes())
        h.update(b"\0")
    return h.hexdigest()


def run_id(source_id: str, as_of: date) -> str:
    _need(isinstance(source_id, str) and SOURCE_ID.fullmatch(source_id), "source_identity")
    return hashlib.sha256(f"cpbl-features-v1:{source_id}:{as_of.isoformat()}".encode()).hexdigest()[:32]


def _time(text) -> datetime:
    _need(isinstance(text, str), "timestamp")
    value = datetime.fromisoformat(text)
    _need(value.utcoffset() is not None, "timestamp_timezone")
    return value


def _read(path: Path, limit: int) -> bytes:
    # Open only a regular file under the fixed run path; don't follow incoming symlinks.
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), "rb") as handle:
        info = os.fstat(handle.fileno())
        _need(stat.S_ISREG(info.st_mode) and 0 < info.st_size <= limit, "file_type_or_size")
        value = handle.read(limit + 1)
        _need(len(value) == info.st_size, "file_length_changed")
        return value


def _object(value: bytes):
    def unique(pairs):
        result = {}
        for key, item in pairs:
            _need(key not in result, "duplicate_json_field")
            result[key] = item
        return result

    return json.loads(value, object_pairs_hook=unique)


def _snapshot_digest(connection):
    digest = hashlib.sha256()
    for table, names in INPUTS.items():
        columns = sql.SQL(", ").join(map(sql.Identifier, names))
        query = sql.SQL("COPY (SELECT {} FROM cpbl.{} ORDER BY {}) TO STDOUT WITH (FORMAT CSV)").format(
            columns, sql.Identifier(table), columns,
        )
        digest.update(table.encode() + b"\0")
        with connection.cursor() as cursor, cursor.copy(query) as copy:
            for data in copy:
                digest.update(data)
        digest.update(b"\0")
    return digest.hexdigest()


def _value_to_wire(value):
    if isinstance(value, (Decimal, date)):
        return str(value)
    return value


def _publish_files(root, name, blob, manifest, schedule=None):
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    _need(root.is_dir() and not root.is_symlink(), "result_root")
    target = root / name
    raw_manifest = (json.dumps(manifest, sort_keys=True) + "\n").encode()
    files = [("result.json.gz", blob), ("response.json", raw_manifest)]
    if schedule is not None:
        files.append(("schedule.json", schedule))
    if target.exists():
        _need(not target.is_symlink() and target.is_dir(), "result_path")
        _need(all(_read(target / ident, len(data)) == data for ident, data in files),
              "conflicting_daily_result")
        return
    # Atomic directory publication makes the manifest and bundle visible together.
    with tempfile.TemporaryDirectory(dir=root, prefix=".incoming-") as temporary:
        staged = Path(temporary) / name
        staged.mkdir(mode=0o700)
        for ident, data in files:
            with os.fdopen(os.open(staged / ident, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as handle:
                handle.write(data)
        # The existing target is nonempty, so rename cannot replace a concurrent result.
        staged.rename(target)


def compute(connection, freshness, result_root: Path, *, now=None, schedule=None) -> dict:
    """Freeze the Pi-owned seven-table snapshot and run the unchanged feature algorithm."""
    now = now or datetime.now(UTC)
    _need(isinstance(freshness, dict) and set(freshness) == {"source_id", "as_of", "finished_at", "ok"}
          and freshness["ok"] is True, "ingest_receipt")
    as_of = date.fromisoformat(freshness["as_of"])
    source_id = freshness["source_id"]
    name = run_id(source_id, as_of)
    finished = _time(freshness["finished_at"])
    _need(now.astimezone(TAIPEI).date() == as_of == finished.astimezone(TAIPEI).date()
          and finished <= now, "ingest_receipt_date")
    if schedule is not None:
        _schedule_rows(schedule, as_of)
    existing = result_root / name
    if existing.exists():
        manifest, _ = read_response(existing, source_id, as_of, now=now)
        _need(_time(manifest["refresh_finished_at"]) == finished, "conflicting_daily_result")
        if schedule is not None:
            _need(_read(existing / "schedule.json", MAX_SCHEDULE) == schedule, "conflicting_schedule")
        _need(("schedule_sha256" in manifest) == (schedule is not None), "schedule_mode")
        if schedule is not None:
            read_schedule(existing, manifest, as_of)
        return manifest
    with connection.transaction():
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        connection.execute("SET LOCAL TIME ZONE 'Asia/Taipei'")
        connection.execute("SET LOCAL DateStyle = 'ISO, YMD'")
        identity = connection.execute(
            "SELECT current_database(), inet_server_addr() IS NULL, CURRENT_DATE, transaction_timestamp()"
        ).fetchone()
        _need(identity is not None and identity[:3] == (PI_DATABASE, True, as_of)
              and finished <= identity[3], "private_pi_snapshot_identity")
        snapshot_at = identity[3]
        input_sha = _snapshot_digest(connection)

        @contextmanager
        def connect():
            yield connection

        rows = outcome.build_game_features(connect=connect)
    records = [[_value_to_wire(row[k]) for k in outcome.FEATURE_COLUMNS] for row in rows]
    _need(records and as_of == datetime.now(TAIPEI).date(), "empty_or_cross_day_features")
    raw = json.dumps(records, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()
    _need(len(raw) <= MAX_RESULTS, "result_size")
    blob = gzip.compress(raw, mtime=0)
    manifest = {
        "version": VERSION, "source_id": source_id, "run_id": name, "as_of": as_of.isoformat(),
        "refresh_finished_at": finished.isoformat(), "snapshot_at": snapshot_at.isoformat(),
        "algorithm_sha256": algorithm_sha256(), "input_sha256": input_sha,
        "result_sha256": hashlib.sha256(blob).hexdigest(), "result_bytes": len(blob),
        "row_count": len(records),
    }
    if schedule is not None:
        manifest.update(schedule_bytes=len(schedule), schedule_sha256=hashlib.sha256(schedule).hexdigest())
    _publish_files(result_root, name, blob, manifest, schedule)
    return manifest


def _decode_records(raw, count):
    values = _object(raw)
    _need(isinstance(values, list) and len(values) == count and count > 0, "result_row_count")
    rows = []
    keys = set()
    for cells in values:
        _need(isinstance(cells, list) and len(cells) == len(outcome.FEATURE_COLUMNS), "result_columns")
        row = dict(zip(outcome.FEATURE_COLUMNS, cells, strict=True))
        for key, value in row.items():
            if key in TEXT_COLUMNS:
                _need(value is None or isinstance(value, str), "feature_text")
            elif key in INT_COLUMNS:
                _need(type(value) is int or (key == "home_win" and value is None), "feature_integer")
            elif key == "completed":
                _need(type(value) is bool, "feature_completed")
            elif key == "game_date":
                row[key] = date.fromisoformat(value)
            elif value is not None:
                _need(type(value) in (int, float, str), "feature_number")
                number = Decimal(value) if isinstance(value, str) else value
                _need(math.isfinite(number), "nonfinite_feature")
                row[key] = number
        key = tuple(row[k] for k in KEY)
        _need(row["kind_code"] == "A" and row["game_season_code"] is not None
              and row["season"] == row["year"] and key not in keys, "invalid_or_duplicate_feature_key")
        keys.add(key)
        rows.append(row)
    return rows


def read_response(directory: Path, source_id: str, as_of: date, *, now=None, response_sha256=None):
    now = now or datetime.now(UTC)
    name = run_id(source_id, as_of)
    _need(directory.name == name and directory.is_dir() and not directory.is_symlink(), "response_path")
    response = _read(directory / "response.json", MAX_MANIFEST)
    if response_sha256 is not None:
        _need(hashlib.sha256(response).hexdigest() == response_sha256, "notification_response_digest")
    manifest = _object(response)
    _need(isinstance(manifest, dict) and set(manifest) in (MANIFEST_FIELDS, MANIFEST_FIELDS | SCHEDULE_FIELDS)
          and type(manifest["version"]) is int and manifest["version"] == VERSION
          and manifest["source_id"] == source_id and manifest["run_id"] == name
          and manifest["as_of"] == as_of.isoformat() and as_of == now.astimezone(TAIPEI).date()
          and manifest["algorithm_sha256"] == algorithm_sha256(), "response_identity")
    for key in ("input_sha256", "result_sha256"):
        _need(isinstance(manifest[key], str) and SHA.fullmatch(manifest[key]), "response_fingerprint")
    finished, snapshot = map(_time, (manifest["refresh_finished_at"], manifest["snapshot_at"]))
    _need(finished <= snapshot <= now and finished.astimezone(TAIPEI).date()
          == snapshot.astimezone(TAIPEI).date() == as_of, "response_freshness")
    count = manifest["row_count"]
    size = manifest["result_bytes"]
    _need(type(count) is int and count > 0 and type(size) is int and 0 < size <= MAX_RESULTS,
          "response_counts")
    blob = _read(directory / "result.json.gz", size)
    _need(len(blob) == size and hashlib.sha256(blob).hexdigest() == manifest["result_sha256"],
          "response_digest")
    from io import BytesIO

    with gzip.GzipFile(fileobj=BytesIO(blob)) as handle:
        contents = handle.read(MAX_RESULTS + 1)
    _need(len(contents) <= MAX_RESULTS, "decoded_size")
    return manifest, _decode_records(contents, count)


def _schedule_rows(raw, as_of):
    from cpbl.ingest.cpbl_site import validate_schedule

    _need(0 < len(raw) <= MAX_SCHEDULE, "schedule_size")
    rows = _object(raw)
    validate_schedule(rows, as_of.year, "A")
    _need(bool(rows), "empty_schedule")
    return rows


def read_schedule(directory, manifest, as_of):
    size, digest = manifest["schedule_bytes"], manifest["schedule_sha256"]
    _need(type(size) is int and 0 < size <= MAX_SCHEDULE and isinstance(digest, str)
          and SHA.fullmatch(digest), "schedule_manifest")
    raw = _read(directory / "schedule.json", size)
    _need(len(raw) == size and hashlib.sha256(raw).hexdigest() == digest, "schedule_digest")
    return _schedule_rows(raw, as_of)


def publish(connection, rows, *, schedule=None):
    """Check the complete key set and publish with the original #443 MVCC semantics."""
    if schedule is not None:
        from cpbl.ingest.cpbl_site import upsert_games

        upsert_games(schedule, connection=connection)
    keys = {tuple(row[k] for k in KEY) for row in rows}
    expected = set(connection.execute(
        "SELECT year, kind_code, game_season_code, game_sno FROM cpbl.games "
        "WHERE game_date IS NOT NULL AND kind_code = 'A'"
    ).fetchall())
    _need(expected and keys == expected and len(keys) == len(rows), "incomplete_feature_history")
    return outcome.publish_feature_rows(connection, rows, retain_other_kinds=schedule is not None)


def read_incoming_response(root: Path, source_id: str, as_of: date, *, include_games=False):
    """Read the notified bundle for this source and Taipei date, without waiting."""
    _need(root.is_absolute(), "inbox_root")
    inbox = root / "incoming" / "features"
    name = run_id(source_id, as_of)
    directory = inbox / name
    _need(inbox.resolve() == inbox, "inbox_symlink")
    notifications = inbox.with_name("feature-notify")
    _need(notifications.resolve() == notifications, "notification_directory_symlink")
    notice = _object(_read(notifications / f"{name}.ready", MAX_MANIFEST))
    _need(isinstance(notice, dict) and set(notice) == {"version", "run_id", "response_sha256"}
          and type(notice["version"]) is int and notice["version"] == VERSION
          and notice["run_id"] == name and isinstance(notice["response_sha256"], str)
          and SHA.fullmatch(notice["response_sha256"]), "notification_identity")
    response_sha256 = notice["response_sha256"]
    manifest, rows = read_response(directory, source_id, as_of, response_sha256=response_sha256)
    _need(("schedule_sha256" in manifest) == include_games, "schedule_mode")
    schedule = read_schedule(directory, manifest, as_of) if include_games else None
    return {**manifest, "response_sha256": response_sha256}, rows, schedule


def main(argv=None):
    import psycopg
    from psycopg.conninfo import conninfo_to_dict

    parser = argparse.ArgumentParser(description=__doc__)
    command = parser.add_subparsers(dest="command", required=True).add_parser("compute")
    command.add_argument("freshness", type=Path)
    command.add_argument("result_root", type=Path)
    command.add_argument("--schedule", type=Path)
    args = parser.parse_args(argv)
    try:
        dsn = os.environ["CPBL_FEATURE_PI_DATABASE_URL"]
        params = conninfo_to_dict(dsn)
        host = params.get("host", "")
        _need(host.startswith("/") and "," not in host and params.get("dbname") == PI_DATABASE
              and set(params) <= {"host", "port", "dbname", "user", "password", "connect_timeout"}
              and not any(os.environ.get(key) for key in ("PGHOSTADDR", "PGSERVICE", "PGOPTIONS")),
              "private_pi_socket_dsn")
        schedule = _read(args.schedule, MAX_SCHEDULE) if args.schedule else None
        with psycopg.connect(dsn, autocommit=True) as connection:
            manifest = compute(connection, _object(_read(args.freshness, MAX_MANIFEST)), args.result_root, schedule=schedule)
        print(json.dumps(manifest, sort_keys=True))
        return 0
    except Exception as exc:
        log.error("Pi feature handoff failed (%s)", type(exc).__name__)
        return 78


if __name__ == "__main__":
    raise SystemExit(main())
