"""Publish scoped daily SABR rows and observed pitch labels from a Pi snapshot."""

from pathlib import Path
from typing import LiteralString, cast

from psycopg import sql
from psycopg.types.json import Jsonb

from cpbl.features.handoff import _need
from cpbl.ingest.scoped_snapshot_receiving import read_snapshot

SABR_LAYOUTS = {
    "fielding_innings": (4, "year kind_code player_id pos outs games"),
    "catcher_runs": (3, "year kind_code player_id runs games"),
    "batter_traits": (3, "year kind_code player_id pa p_pa go fo dir_left dir_center "
                     "dir_right two_strike_pa two_strike_k two_strike_hit"),
    "pitcher_traits": (3, "year kind_code player_id bf p_pa go fo two_strike_pa two_strike_k"),
    "batter_re24": (3, "year kind_code player_id pa re24"),
    "pitcher_re24": (3, "year kind_code player_id bf re24"),
    "team_der": (2, "year team_id bf h hr bb hbp so der"),
    "batter_wsb": (2, "year player_id sb cs opp wsb"),
}
LABEL_LAYOUTS = {
    "pitch_tracking": (5, "year kind_code game_sno pitcher_acnt pitch_cnt pitch_type_pred pitch_type_pred_v2"),
}


def read_incoming(root: Path, source_id: str, day):
    manifest, snapshot = read_snapshot(
        root, "daily-sabr", source_id, day, {"year", "completed_games"},
    )
    _need(type(manifest["year"]) is int and manifest["year"] == day.year
          and type(manifest["completed_games"]) is int and manifest["completed_games"] > 0,
          "daily_sabr_coverage")
    return manifest, (manifest, decode_snapshot(snapshot, manifest["year"], SABR_LAYOUTS))


def publish(connection, data):
    from cpbl.completion import daily_chain_completed_games_sql

    manifest, rows = data
    # The repository predicate is called with a fixed alias and its built-in date expression.
    completed = cast(LiteralString, daily_chain_completed_games_sql("g"))
    query = sql.SQL("SELECT count(DISTINCT g.game_sno) FROM cpbl.games g "
                    "WHERE g.year=%s AND g.kind_code='A' AND {}").format(
        sql.SQL(completed),
    )
    count = connection.execute(query, (manifest["year"],)).fetchone()[0]
    _need(count == manifest["completed_games"], "daily_sabr_target_coverage")
    return publish_sabr(connection, rows)


def read_labels(root: Path, source_id: str, day):
    manifest, snapshot = read_snapshot(root, "daily-pitch-labels", source_id, day, {"year"})
    _need(type(manifest["year"]) is int and manifest["year"] == day.year,
          "pitch_label_year")
    _need(isinstance(snapshot, dict) and set(snapshot) == {"columns", "data"}
          and set(snapshot["columns"]) == set(snapshot["data"]) == {"pitch_tracking", "model_versions"},
          "pitch_label_tables")
    table_only = {name: {"pitch_tracking": snapshot[name]["pitch_tracking"]} for name in ("columns", "data")}
    rows = decode_snapshot(table_only, manifest["year"], LABEL_LAYOUTS)
    _, _, labels = rows["pitch_tracking"]
    _need({row["kind_code"] for row in labels} == {"A", "D"}, "pitch_label_kind_coverage")
    columns = "id task algo trained_at params cv_metrics".split()
    versions = snapshot["data"]["model_versions"]
    _need(snapshot["columns"]["model_versions"] == columns and isinstance(versions, list)
          and len(versions) == 2 and all(isinstance(row, list) and len(row) == len(columns)
                                        for row in versions), "pitch_label_versions")
    _need({row[0] for row in versions} == {f"pitch_type_v2_{day.year}{kind}" for kind in ("A", "D")}
          and all(row[1:3] == ["pitch_type", "qda-mlb-transfer-v2"] and isinstance(row[3], str)
                  and isinstance(row[4], dict) and isinstance(row[5], dict) for row in versions),
          "pitch_label_version_identity")
    return manifest, (rows, [dict(zip(columns, row, strict=True)) for row in versions])


def publish_label_batch(connection, data):
    rows, versions = data
    _, _, labels = rows["pitch_tracking"]
    # The classifier clears and recomputes the current A/D corpus; a partial handoff must not do that.
    year = labels[0]["year"]
    target_count = connection.execute(
        "SELECT count(*) FROM cpbl.pitch_tracking WHERE year=%s AND kind_code IN ('A','D')", (year,),
    ).fetchone()[0]
    _need(target_count == len(labels), "pitch_label_target_coverage")
    for row in versions:
        exists = connection.execute(
            "SELECT task,algo,trained_at <= %s::timestamptz FROM cpbl.model_versions WHERE id=%s",
            (row["trained_at"], row["id"]),
        ).fetchone()
        _need(exists is None or exists == (row["task"], row["algo"], True), "pitch_label_stale_version")
    result = publish_labels(connection, rows)
    columns = "id task algo trained_at params cv_metrics".split()
    result["model_versions"] = _apply(connection, "model_versions", columns, 1, versions, insert=True)
    return result


def decode_snapshot(snapshot, year, layouts, *, require_all=True):
    _need(type(year) is int and 1 <= year <= 32767, "derived_snapshot_year")
    _need(isinstance(snapshot, dict) and set(snapshot) == {"columns", "data"}
          and isinstance(snapshot["columns"], dict) and isinstance(snapshot["data"], dict),
          "derived_snapshot_shape")
    tables = set(snapshot["data"])
    _need(tables and tables == set(snapshot["columns"]) and tables <= set(layouts)
          and (not require_all or tables == set(layouts)), "derived_snapshot_tables")
    decoded = {}
    for table in sorted(tables):
        size, names = layouts[table]
        columns = names.split()
        records = snapshot["data"][table]
        _need(snapshot["columns"][table] == columns and isinstance(records, list),
              "derived_snapshot_columns")
        keys = set()
        rows = []
        for row in records:
            _need(isinstance(row, list) and len(row) == len(columns)
                  and type(row[0]) is int and row[0] == year, "derived_snapshot_scope")
            if columns[1] == "kind_code":
                kinds = ("A", "D") if table == "pitch_tracking" else ("A",)
                _need(row[1] in kinds, "derived_snapshot_kind")
            _need(all(type(value) in (int, str) for value in row[:size]), "derived_snapshot_key")
            key = tuple(row[:size])
            _need(key not in keys, "derived_snapshot_duplicate")
            keys.add(key)
            rows.append(dict(zip(columns, row, strict=True)))
        decoded[table] = (columns, size, rows)
    return decoded


def _apply(connection, table, columns, size, rows, *, insert, write=True):
    target = sql.Identifier("cpbl", table)
    names = sql.SQL(",").join(map(sql.Identifier, columns))
    keys = sql.SQL(",").join(map(sql.Identifier, columns[:size]))
    source = sql.SQL(",").join(sql.Identifier("src", column) for column in columns)
    target_row = sql.SQL(",").join(sql.Identifier("dst", column) for column in columns)
    staging = sql.SQL("jsonb_populate_recordset(NULL::{}, %s) AS src").format(target)
    source_updates = sql.SQL(",").join(sql.Identifier("src", column) for column in columns[size:])
    updates = sql.SQL(",").join(map(sql.Identifier, columns[size:]))
    if insert:
        expression = sql.SQL(
            "INSERT INTO {target} AS dst ({names}) SELECT {source} FROM {staging} "
            "ON CONFLICT ({keys}) DO UPDATE SET ({updates})=ROW({excluded}) "
            "WHERE ROW({target_updates}) IS DISTINCT FROM ROW({excluded})"
        ).format(
            target=target, names=names, source=source, staging=staging, keys=keys, updates=updates,
            excluded=sql.SQL(",").join(sql.Identifier("excluded", column) for column in columns[size:]),
            target_updates=sql.SQL(",").join(sql.Identifier("dst", column) for column in columns[size:]),
        )
    else:
        join = sql.SQL(" AND ").join(
            sql.SQL("{}={}").format(sql.Identifier("dst", col), sql.Identifier("src", col))
            for col in columns[:size]
        )
        expression = sql.SQL(
            "UPDATE {target} AS dst SET ({updates})=ROW({source_updates}) "
            "FROM {staging} WHERE {join}"
        ).format(target=target, updates=updates, source_updates=source_updates, staging=staging, join=join)
    verify = sql.SQL(
        "SELECT count(*) FROM {staging} JOIN {target} AS dst USING ({keys}) "
        "WHERE ROW({target_row}) IS NOT DISTINCT FROM ROW({source})"
    ).format(staging=staging, target=target, keys=keys, target_row=target_row, source=source)
    count = 0
    for offset in range(0, len(rows), 500):
        payload = Jsonb(rows[offset:offset + 500])
        if write:
            connection.execute(expression, (payload,))
        count += connection.execute(verify, (payload,)).fetchone()[0]
    if write:
        _need(count == len(rows), "derived_snapshot_reconciliation")
    return count


def publish_sabr(connection, data):
    """Keep the original Mac upsert semantics for observed rows."""
    return {table: _apply(connection, table, *layout, insert=True) for table, layout in data.items()}


def publish_labels(connection, data):
    """Update existing pitch keys only; never insert or touch official measurements."""
    return {table: _apply(connection, table, *layout, insert=False) for table, layout in data.items()}
