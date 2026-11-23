"""Publish only the daily table/season scope explicitly supplied by the original producer."""

from pathlib import Path

from cpbl.features.handoff import _need
from cpbl.ingest.cpbl_transactions import LEVEL_KINDS
from cpbl.ingest.daily_derived_handoff import _apply
from cpbl.ingest.scoped_snapshot_receiving import read_snapshot

TABLE_LAYOUTS = {
    "pitching_current": (2,
        "year player_id name team_code era ip g gs w l whip k9 fip era_plus sv hld so cg sho pa np "
        "h hr bb ibb hbp wp bk r er go ao goao",
    ),
    "batting_current": (2,
        "year player_id name team_code pa avg obp slg ops hr ops_plus k_pct bb_pct g ab r h b2 b3 "
        "rbi bb so sb cs tb gidp sh sf ibb hbp go ao goao",
    ),
    "fielding_current": (4,
        "year kind_code player_id pos name team_code g tc po a e dp tp pb cs sba fpct",
    ),
    "team_current": (2,
        "year team_code name bat_avg bat_obp bat_slg bat_ops bat_hr pit_era pit_whip",
    ),
    "team_standings": (4,
        "year kind_code season_code team_code team_name rank g w t l win_pct gb elim home_record "
        "away_record streak last10 h2h updated_at",
    ),
    "player_transactions": (4,
        "year acnt trans_date kind_code name team_name reason updated_at",
    ),
    "games": (4,
        "year kind_code game_season_code game_sno game_date present_status venue home_team_code "
        "home_team_name away_team_code away_team_name home_score away_score home_starter_id "
        "away_starter_id winning_pitcher_id losing_pitcher_id closer_id mvp_id delay_kind orig_date",
    ),
    "official_change_signals": (4,
        "year kind_code game_sno field official_value detected_at resolved_at",
    ),
    "game_source_revisions": (5,
        "year kind_code game_sno source source_version outcome row_count error_code detail "
        "fetched_at last_seen_at seen_count",
    ),
    "game_schedule_status_revisions": (5,
        "year kind_code game_season_code game_sno payload_hash raw_present_status raw_game_result "
        "raw_game_date raw_pre_exe_date raw_payload fetched_at last_seen_at seen_count",
    ),
}
CURRENT_TABLES = {"batting_current", "pitching_current", "fielding_current", "team_current",
                  "team_standings", "player_transactions"}
RESULT_TABLES = {"games", "game_schedule_status_revisions", "game_source_revisions", "official_change_signals"}


def _decode(snapshot, declared, year, allowed, *, non_a):
    _need(isinstance(snapshot, dict) and set(snapshot) == {"columns", "data"}
          and isinstance(declared, list) and declared == sorted(set(declared)) and bool(declared)
          and set(declared) == set(snapshot["columns"]) == set(snapshot["data"])
          and set(declared) <= allowed, "current_snapshot_tables")
    out = {}
    for table in declared:
        n, header = TABLE_LAYOUTS[table]
        cols = header.split()
        rows = snapshot["data"][table]
        _need(snapshot["columns"][table] == cols and isinstance(rows, list), "current_snapshot_columns")
        keys, records = set(), []
        for row in rows:
            _need(isinstance(row, list) and len(row) == len(cols)
                  and type(row[0]) is int and row[0] == year, "current_snapshot_year_scope")
            payload = dict(zip(cols, row, strict=True))
            if "kind_code" in payload:
                if table == "player_transactions":
                    kinds = LEVEL_KINDS
                else:
                    kinds = ("D", "E", "C", "F") if non_a else ("A", "D", "E", "C")
                _need(payload["kind_code"] in kinds, "current_snapshot_kind_scope")
            if table == "game_source_revisions":
                _need(payload["source"] == "schedule", "current_snapshot_schedule_source")
            key = tuple(row[:n])
            _need(all(type(value) in (str, int) for value in key) and key not in keys, "current_snapshot_key")
            keys.add(key)
            records.append(payload)
        out[table] = (cols, n, records)
    return out


def _read(root, source_id, day, name, allowed, *, non_a=False):
    manifest, snapshot = read_snapshot(root, name, source_id, day, {"year", "tables"})
    _need(type(manifest["year"]) is int and manifest["year"] == day.year, "current_snapshot_batch_year")
    return manifest, _decode(snapshot, manifest["tables"], day.year, allowed, non_a=non_a)


def read_current(root: Path, source_id: str, day):
    return _read(root, source_id, day, "daily-current", CURRENT_TABLES)


def read_results(root: Path, source_id: str, day):
    return _read(root, source_id, day, "non-a-results", RESULT_TABLES, non_a=True)


def publish(connection, data):
    return {table: _apply(connection, table, *data[table], insert=True)
            for table in TABLE_LAYOUTS if table in data}
