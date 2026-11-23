"""Publish one opt-in daily batch of exact, already-calculated PA builds."""

from pathlib import Path

from cpbl.features.handoff import _need
from cpbl.ingest import boxpa_sync, evening_handoff, pa_snapshot_handoff
from cpbl.ingest.scoped_snapshot_receiving import read_snapshot


def read_incoming(root: Path, source_id: str, day):
    manifest, packet = read_snapshot(root, "daily-pa", source_id, day, {"games"})
    raw = manifest["games"]
    _need(isinstance(raw, list) and raw, "daily_pa_scope")
    keys = []
    for record in raw:
        _need(isinstance(record, list) and len(record) == 3 and type(record[0]) is int
              and record[0] == day.year and record[1] in ("A", "C", "D", "E")
              and type(record[2]) is int and 1 <= record[2] <= 999, "daily_pa_game")
        keys.append(boxpa_sync.GameKey(*record))
    _need(keys == sorted(set(keys)), "daily_pa_order")
    _need(isinstance(packet, dict) and set(packet) == {"pa", "predecessors"}
          and isinstance(packet["pa"], dict) and set(packet["pa"]) == {key.text for key in keys}
          and isinstance(packet["predecessors"], dict)
          and set(packet["predecessors"]) <= set(packet["pa"])
          and all(isinstance(value, str) for value in packet["predecessors"].values()),
          "daily_pa_packet")
    return manifest, (keys, packet)


def publish(connection, data):
    keys, packet = data
    evening_handoff.require_final(connection, keys)
    totals = {"games": 0}
    for key in keys:
        snapshot = packet["pa"][key.text]
        _need(isinstance(snapshot, dict) and isinstance(snapshot.get("columns"), dict)
              and isinstance(snapshot.get("data"), dict), "daily_pa_build_snapshot")
        columns = snapshot["columns"]["game_recap_builds"]
        rows = snapshot["data"]["game_recap_builds"]
        _need(len(rows) == 1, "daily_pa_build")
        build = rows[0][columns.index("build_id")]
        counts = pa_snapshot_handoff.verify_published(connection, key, snapshot, build)
        if counts is None:
            counts = pa_snapshot_handoff.publish_new(connection, key, snapshot,
                                                     expected_previous=packet["predecessors"].get(key.text))
        totals["games"] += 1
        for table, count in counts.items():
            totals[table] = totals.get(table, 0) + count
    return totals
