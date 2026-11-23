"""Publish the original weekly Box observation with target-owned revision IDs."""

from collections import defaultdict
from pathlib import Path

from cpbl.features.handoff import SHA, _need
from cpbl.ingest import cpbl_gamelog as gamelog
from cpbl.ingest.box_revisions import record_box_pitching_revisions
from cpbl.ingest.daily_derived_handoff import _apply
from cpbl.ingest.game_source_revisions import (
    canonical_source_version,
    record_source_revision,
    sanitize_detail,
)
from cpbl.ingest.scoped_snapshot_receiving import read_snapshot

TABLES = {
    "game_scoreboard": (5, gamelog._SB_COLS),
    "game_livelog": (4, gamelog._LL_COLS),
    "game_livelog_extra": (5, gamelog._LL_EXTRA_COLS),
    "batting_gamelog": (4, gamelog._BBOX_COLS),
    "pitching_gamelog": (4, gamelog._PBOX_COLS),
    "game_detail": (3, gamelog._GD_WX_COLS),
    "game_source_revisions": (
        5, "year,kind_code,game_sno,source,source_version,outcome,row_count,error_code,detail",
    ),
    "box_pitching_revisions": (
        4, "year,kind_code,game_sno,pitcher_acnt,inning_pitched_cnt,inning_pitched_div3,"
        "runs,earned_runs,content_hash,raw_payload",
    ),
}
REVISIONS = {"game_source_revisions", "box_pitching_revisions"}
LOCAL_FIELDS = {"id", "fetched_at", "last_seen_at", "seen_count"}


def read_incoming(root: Path, source_id: str, day):
    manifest, snapshot = read_snapshot(root, "weekly-box", source_id, day, {"games"})
    return manifest, decode_snapshot(snapshot, manifest["games"])


def decode_snapshot(snapshot, scope):
    games = set()
    for key in scope:
        _need(isinstance(key, list) and len(key) == 3 and type(key[0]) is int
              and key[1] in ("A", "D") and type(key[2]) is int and key[2] > 0, "weekly_box_game")
        games.add(tuple(key))
    _need(games and len(games) == len(scope), "weekly_box_scope")
    _need(isinstance(snapshot, dict) and set(snapshot) == {"columns", "data"}
          and isinstance(snapshot["columns"], dict) and isinstance(snapshot["data"], dict)
          and set(snapshot["columns"]) == set(snapshot["data"]) == set(TABLES), "weekly_box_tables")
    prepared = {}
    for table, (size, declaration) in TABLES.items():
        columns = [column.strip() for column in declaration.split(",")]
        observed = snapshot["columns"][table]
        rows = snapshot["data"][table]
        allowed = set(columns)
        if table in REVISIONS:
            allowed |= LOCAL_FIELDS
        elif table == "game_detail":
            # The weekly getlive job owns weather/decision only; HTML fields belong to a different writer.
            allowed |= set(gamelog._GD_COLS.split(",")) | {"updated_at"}
        _need(isinstance(observed, list) and len(set(observed)) == len(observed)
              and set(observed) == allowed
              and isinstance(rows, list), "weekly_box_columns")
        data, keys = [], set()
        for row in rows:
            _need(isinstance(row, list) and len(row) == len(observed), "weekly_box_row")
            record = dict(zip(observed, row, strict=True))
            key = tuple(record[column] for column in columns[:size])
            _need(all(type(value) in (str, int) for value in key) and key[:3] in games
                  and key not in keys, "weekly_box_row_scope")
            keys.add(key)
            data.append({column: record[column] for column in columns})
        prepared[table] = (columns, size, data)
    return games, prepared


def _revision_input(games, prepared):
    observed = {}
    for row in prepared["game_source_revisions"][2]:
        game = (row["year"], row["kind_code"], row["game_sno"])
        label = (*game, row["source"])
        _need(row["source"] in ("scoreboard", "livelog") and row["outcome"] in ("available", "missing")
              and isinstance(row["source_version"], str) and bool(SHA.fullmatch(row["source_version"]))
              and type(row["row_count"]) is int
              and (row["row_count"] > 0 if row["outcome"] == "available" else row["row_count"] == 0)
              and row["error_code"] is None and isinstance(row["detail"], dict)
              and label not in observed, "weekly_box_source_observation")
        observed[label] = row
    _need(set(observed) == {(*game, name) for game in games for name in ("scoreboard", "livelog")},
          "weekly_box_source_coverage")
    pitcher_obs = defaultdict(list)
    for row in prepared["box_pitching_revisions"][2]:
        raw = row["raw_payload"]
        _need(isinstance(raw, dict) and raw.get("PitcherAcnt") == row["pitcher_acnt"]
              and canonical_source_version(sanitize_detail(raw)) == row["content_hash"],
              "weekly_box_pitcher_payload")
        pitcher_obs[(row["year"], row["kind_code"], row["game_sno"])].append(raw)
    return observed, pitcher_obs


def publish(connection, data):
    """Apply the scoped main/extra pair and revisions in the caller's transaction."""
    games, prepared = data
    observed, pitcher_obs = _revision_input(games, prepared)
    livelog_games = {k[:3] for k, row in observed.items() if k[3] == "livelog" and row["row_count"] > 0}
    extra = prepared["game_livelog_extra"][2]
    _need(all((row["year"], row["kind_code"], row["game_sno"]) in livelog_games for row in extra),
          "weekly_box_extra_without_source")
    for game in sorted(livelog_games):
        connection.execute(
            "DELETE FROM cpbl.game_livelog_extra WHERE (year,kind_code,game_sno)=(%s,%s,%s)", game,
        )
    counts = {table: _apply(connection, table, *prepared[table], insert=True)
              for table in TABLES if table not in REVISIONS}
    for row in observed.values():
        record_source_revision(**row, connection=connection)
        _need(connection.execute(
            "SELECT outcome,row_count,error_code FROM cpbl.game_source_revisions "
            "WHERE (year,kind_code,game_sno,source,source_version)=(%s,%s,%s,%s,%s)",
            tuple(row[k] for k in ("year", "kind_code", "game_sno", "source", "source_version")),
        ).fetchone() == (row["outcome"], row["row_count"], row["error_code"]), "weekly_box_source_reconciliation")
    counts["game_source_revisions"] = len(observed)
    counts["box_pitching_revisions"] = sum(
        record_box_pitching_revisions(*game, rows, connection=connection)
        for game, rows in sorted(pitcher_obs.items())
    )
    for row in prepared["box_pitching_revisions"][2]:
        _need(connection.execute(
            "SELECT content_hash,inning_pitched_cnt,inning_pitched_div3,runs,earned_runs "
            "FROM cpbl.box_pitching_revisions WHERE (year,kind_code,game_sno,pitcher_acnt)=(%s,%s,%s,%s) "
            "ORDER BY fetched_at DESC,id DESC LIMIT 1",
            tuple(row[k] for k in ("year", "kind_code", "game_sno", "pitcher_acnt")),
        ).fetchone() == tuple(row[k] for k in (
            "content_hash", "inning_pitched_cnt", "inning_pitched_div3", "runs", "earned_runs",
        )), "weekly_box_pitcher_reconciliation")
    return counts
