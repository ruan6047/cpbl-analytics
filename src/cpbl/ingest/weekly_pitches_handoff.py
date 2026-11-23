"""Receive one scoped Pi weekly pitch snapshot and publish its observed keys."""

from pathlib import Path

from psycopg import sql
from psycopg.types.json import Jsonb

from cpbl.features.handoff import _need
from cpbl.ingest import cpbl_pitch_tracking as pitch
from cpbl.ingest.scoped_snapshot_receiving import read_snapshot

COLUMNS = {
    "pitch_tracking": tuple(pitch._COLS.split(",")),
    "pitching_game_flags": tuple(pitch._FLAG_COLS.split(",")),
}
KEY_SIZE = {"pitch_tracking": 5, "pitching_game_flags": 4}


def read_incoming(root: Path, source_id: str, day):
    manifest, snapshot = read_snapshot(root, "weekly-pitches", source_id, day, {"games"})
    return manifest, decode_snapshot(snapshot, manifest["games"])


def decode_snapshot(snapshot, selected_games):
    _need(isinstance(selected_games, list) and selected_games, "weekly_pitches_scope")
    games = set()
    for game in selected_games:
        _need(isinstance(game, list) and len(game) == 3 and type(game[0]) is int
              and 1 <= game[0] <= 32767 and game[1] in ("A", "D")
              and type(game[2]) is int and game[2] > 0, "weekly_pitches_game_key")
        identity = tuple(game)
        _need(identity not in games and not pitch.is_frozen(*identity), "weekly_pitches_game_scope")
        games.add(identity)
    _need(isinstance(snapshot, dict) and set(snapshot) == {"columns", "data"}
          and snapshot["columns"] == {table: list(cols) for table, cols in COLUMNS.items()}
          and isinstance(snapshot["data"], dict) and set(snapshot["data"]) == set(COLUMNS),
          "weekly_pitches_columns")
    data = {}
    for table, columns in COLUMNS.items():
        records = snapshot["data"][table]
        _need(isinstance(records, list), "weekly_pitches_rows")
        keyed = {}
        for row in records:
            _need(isinstance(row, list) and len(row) == len(columns)
                  and type(row[0]) is int and isinstance(row[1], str) and type(row[2]) is int
                  and tuple(row[:3]) in games
                  and isinstance(row[3], str) and bool(row[3])
                  and (table != "pitch_tracking" or type(row[4]) is int), "weekly_pitches_row_scope")
            identity = tuple(row[:KEY_SIZE[table]])
            _need(identity not in keyed, "weekly_pitches_duplicate_key")
            keyed[identity] = tuple(row)
        data[table] = keyed
    return data


def publish(connection, data):
    """Reuse the original upserts without touching Mac-derived columns or unobserved rows."""
    pitch._upsert(list(data["pitch_tracking"].values()), connection=connection)
    pitch._upsert_pitcher_flags(list(data["pitching_game_flags"].values()), connection=connection)
    counts = {}
    for table, columns in COLUMNS.items():
        expected = list(data[table].values())
        column_ids = [sql.Identifier(column) for column in columns]
        query = sql.SQL(
            "SELECT count(*) FROM jsonb_populate_recordset(NULL::{table}, %s) AS src "
            "JOIN {table} AS dst USING ({keys}) "
            "WHERE ROW({target}) IS NOT DISTINCT FROM ROW({source})"
        ).format(
            table=sql.Identifier("cpbl", table),
            keys=sql.SQL(",").join(column_ids[:KEY_SIZE[table]]),
            target=sql.SQL(",").join(sql.Identifier("dst", column) for column in columns),
            source=sql.SQL(",").join(sql.Identifier("src", column) for column in columns),
        )
        # PostgreSQL casts official JSON numbers to the same types as the original insert
        # before comparing (for example, original TrackMan float to PostgreSQL real).
        count = 0
        for offset in range(0, len(expected), 500):
            batch = [dict(zip(columns, row, strict=True)) for row in expected[offset:offset + 500]]
            count += connection.execute(query, (Jsonb(batch),)).fetchone()[0]
        _need(count == len(expected), "weekly_pitches_reconciliation")
        counts[table] = count
    return counts
