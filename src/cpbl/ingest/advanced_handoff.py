"""Apply exact advanced scopes with target-owned runs and the original promotion contract."""

from datetime import datetime
from pathlib import Path

from cpbl.features.handoff import _need
from cpbl.ingest import advanced_snapshot as snap
from cpbl.ingest.cpbl_advanced import _STAT_BASE_COLS
from cpbl.ingest.daily_derived_handoff import _apply
from cpbl.ingest.scoped_snapshot_receiving import read_snapshot

DATA = {
    "player_stats": (4, _STAT_BASE_COLS),
    "pitch_type_stats": (5, "year kind_code role acnt pitch_type pitches kph kph_max spin_rate spin_rate_max "
                           "throws source_payload".split()),
    "league_summary": (4, "year kind_code category pitch_type metrics source_payload".split()),
}
ENDPOINTS = {
    "player_stats": {"leaderboards/pr-table+exit-velocity+batted-ball", "leaderboards/pr-table"},
    "pitch_type_stats": {"leaderboards/pitch-tracking"},
    "league_summary": {"leaderboards/summary"},
}


def read_incoming(root: Path, source_id: str, day):
    manifest, snapshot = read_snapshot(root, "daily-advanced", source_id, day, {"year"})
    _need(type(manifest["year"]) is int and manifest["year"] == day.year, "advanced_batch_year")
    _need(isinstance(snapshot, dict) and set(snapshot) == {"scopes"}
          and isinstance(snapshot["scopes"], list) and bool(snapshot["scopes"]), "advanced_batch_scope")
    decoded, used = [], set()
    for entry in snapshot["scopes"]:
        _need(isinstance(entry, dict) and set(entry) == {
            "year", "kind_code", "dataset", "role", "scope", "endpoint", "source_fetched_at", "source_version",
            "rows",
        }, "advanced_scope_shape")
        year, kind, dataset, role = (entry[key] for key in ("year", "kind_code", "dataset", "role"))
        mode, endpoint, version = (entry[key] for key in ("scope", "endpoint", "source_version"))
        _need(type(year) is int and year == day.year and kind in ("A", "D", "C", "E")
              and dataset in DATA and role in ("", "batting", "pitching")
              and ((dataset == "league_summary") == (role == ""))
              and (dataset != "pitch_type_stats" or role == "pitching")
              and (mode == "full" or (mode == "partial" and dataset == "player_stats"))
              and endpoint in ENDPOINTS[dataset] and (version is None or isinstance(version, str)),
              "advanced_scope_identity")
        spec = snap.RunSpec(year, kind, dataset, role)
        _need(spec not in used, "advanced_scope_duplicate")
        used.add(spec)
        fetched = datetime.fromisoformat(entry["source_fetched_at"])
        _need(fetched.utcoffset() is not None, "advanced_source_time")
        n, cols = DATA[dataset]
        rows = entry["rows"]
        _need(isinstance(rows, list) and rows, "advanced_scope_no_rows")
        keys = set()
        for row in rows:
            _need(isinstance(row, dict) and set(row) == set(cols)
                  and type(row["year"]) is int and (row["year"], row["kind_code"]) == (year, kind)
                  and row.get("role", role) == role, "advanced_row_scope")
            key = tuple(row[name] for name in cols[:n])
            _need(all(type(v) in (str, int) for v in key) and key not in keys, "advanced_row_key")
            keys.add(key)
        decoded.append((spec, mode, endpoint, fetched, version, rows))
    return manifest, decoded


def publish(connection, data):
    connection.execute("LOCK TABLE cpbl.advanced_snapshot_state IN SHARE ROW EXCLUSIVE MODE")
    counts = {}
    cur = connection.cursor()
    for spec, mode, endpoint, fetched, version, rows in data:
        target = cur.execute(
            "SELECT current_run_id,source_fetched_at,row_count FROM cpbl.advanced_snapshot_state "
            "WHERE (year,kind_code,dataset,role)=(%s,%s,%s,%s)",
            (spec.year, spec.kind_code, spec.dataset, spec.role),
        ).fetchone()
        _need(target is None or fetched >= target[1], "advanced_receipt_stale")
        table = snap.DATASET_TABLE[spec.dataset].split(".")[1]
        n, logical_columns = DATA[spec.dataset]
        columns = [*logical_columns, "source_run_id", "source_fetched_at", "last_seen_at"]

        def stage(_cursor, run_id):
            bound = [dict(row, source_run_id=run_id, source_fetched_at=fetched.isoformat(),
                          last_seen_at=fetched.isoformat()) for row in rows]
            return _apply(connection, table, columns, n, bound, insert=True)

        if mode == "partial":
            total = stage(cur, target[0] if target else None)
        else:
            report = snap.ValidationReport(observed_rows=len(rows), accepted_rows=len(rows))
            _need(snap.validate(spec, report, prior=target[2] if target else None).ok, "advanced_scope_floor")
            run_id = snap.open_run_on_cursor(cur, spec, "full", endpoint, fetched,
                                            observed_rows=len(rows), source_version=version)
            snap.promote_full_on_cursor(cur, spec, run_id, stage, report)
            total = len(rows)
        counts[f"{spec.year}-{spec.kind_code}-{spec.dataset}-{spec.role}"] = total
    return counts
