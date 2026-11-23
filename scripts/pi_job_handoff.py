"""Opt-in sender for the existing Pi-side Linux jobs entrypoint."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import os
import time
from datetime import datetime
from pathlib import Path

from psycopg import sql

from cpbl.db import conn
from cpbl.features import handoff
from cpbl.ingest import (
    cpbl_gamelog,
    daily_derived_handoff,
    weekly_box_handoff,
    weekly_pitches_handoff,
)

NAMESPACES = {"weekly-pitches", "weekly-box", "daily-sabr", "daily-pitch-labels", "daily-current", "non-a-results", "daily-advanced", "daily-pa"}
BOX_REVISIONS = {"game_source_revisions": ("source",), "box_pitching_revisions": ("pitcher_acnt",)}


def feature_sender():
    path = Path(__file__).resolve().parents[1] / "ops/pi-fetcher/cpbl_pi_feature.py"
    spec = importlib.util.spec_from_file_location("cpbl_pi_job_feature_sender", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def publication_batch(namespace, run_id):
    if namespace not in NAMESPACES or len(run_id) != 32 or not handoff.SHA.fullmatch(run_id + "0" * 32):
        raise ValueError("invalid_pi_batch_scope")
    parent = f"/incoming/{namespace}/{run_id}"
    return (
        f"mkdir {parent}\n"
        f'put "snapshot.json" {parent}/.snapshot.json.upload\n'
        f"rename {parent}/.snapshot.json.upload {parent}/snapshot.json\n"
        f'put "response.json" {parent}/.response.json.upload\n'
        f"rename {parent}/.response.json.upload {parent}/response.json\n"
        f'put "notification.json" {parent}/.ready.upload\n'
        f"rename {parent}/.ready.upload /incoming/{namespace}-notify/{run_id}.ready\n"
    ).encode("ascii")


def snapshot_rows(connection, tables, *, where, params):
    data = {}
    for table, cols in tables.items():
        selected = sql.SQL(", ").join(map(sql.Identifier, cols))
        query = sql.SQL("SELECT {} FROM cpbl.{} WHERE {} ORDER BY {}").format(
            selected, sql.Identifier(table), where, selected,
        )
        data[table] = connection.execute(query, params).fetchall()
    return {"columns": tables, "data": data}


def box_snapshot(connection, games, started):
    placeholders = sql.SQL(", ").join([sql.SQL("(%s,%s,%s)")] * len(games))
    scope = sql.SQL("(year,kind_code,game_sno) IN ({})").format(placeholders)
    params = [value for game in games for value in game]
    columns = {}
    data = {}
    for table, (_, declaration) in weekly_box_handoff.TABLES.items():
        cols = declaration.split(",")
        if table in BOX_REVISIONS:
            cols += sorted(weekly_box_handoff.LOCAL_FIELDS)
        elif table == "game_detail":
            cols += sorted(set(cpbl_gamelog._GD_COLS.split(",")) - set(cols) | {"updated_at"})
        columns[table] = cols
        fields = sql.SQL(", ").join(map(sql.Identifier, cols))
        if table in BOX_REVISIONS:
            key = sql.SQL(", ").join(map(sql.Identifier, ("year", "kind_code", "game_sno", *BOX_REVISIONS[table])))
            query = sql.SQL(
                "SELECT DISTINCT ON ({key}) {cols} FROM cpbl.{table} WHERE {scope} "
                "AND last_seen_at >= %s ORDER BY {key}, last_seen_at DESC, id DESC",
            ).format(key=key, cols=fields, table=sql.Identifier(table), scope=scope)
            data[table] = connection.execute(query, [*params, started]).fetchall()
        else:
            query = sql.SQL("SELECT {} FROM cpbl.{} WHERE {} ORDER BY {}").format(
                fields, sql.Identifier(table), scope, fields,
            )
            data[table] = connection.execute(query, params).fetchall()
    return {"columns": columns, "data": data}


class PiJobHandoff:
    def __init__(self, run, timeout):
        self.feature = feature_sender()
        private = self.feature._private_environment()
        if private["DATABASE_URL"] != os.environ.get("DATABASE_URL"):
            raise ValueError("private_pi_database_mismatch")
        if not math.isfinite(timeout) or timeout <= self.feature.EXIT_RESERVE_SECONDS:
            raise ValueError("invalid_pi_send_timeout")
        self.run = run
        self.timeout = timeout
        self.pitches = {table: [] for table in weekly_pitches_handoff.COLUMNS}
        self.pitch_scope = []
        self.box_scope = []
        self.daily = None
        self.night_results = False

    def pitch_written(self, game, pitches, flags):
        self.pitch_scope.append(game)
        self.pitches["pitch_tracking"].extend(pitches)
        self.pitches["pitching_game_flags"].extend(flags)

    def box_written(self, year, kind, snos):
        self.box_scope.extend((year, kind, n) for n in snos)

    def daily_written(self, detail):
        self.daily = detail

    def packets(self):
        job = self.run.job
        if job == "weekly-game-pitches" and self.pitch_scope and any(self.pitches.values()):
            body = {"columns": weekly_pitches_handoff.COLUMNS, "data": self.pitches}
            yield "weekly-pitches", {"games": self.pitch_scope}, body
        elif job == "weekly-box-revisions" and self.box_scope:
            with conn() as c, c.transaction():
                c.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
                body = box_snapshot(c, self.box_scope, self.run.now)
            yield "weekly-box", {"games": self.box_scope}, body
        elif job == "scrape-daily" and self.daily is not None:
            yield from self.daily_packets()

    def daily_packets(self):
        year = self.run.now.year
        derived = self.daily["derived"]
        pitch = self.daily["pitch_type"]
        if not derived.get("skipped") and not derived["errors"] and derived.get("completed_games", 0) > 0:
            tables = {table: names.split() for table, (_, names) in daily_derived_handoff.SABR_LAYOUTS.items()}
            with conn() as c, c.transaction():
                c.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
                grouped = {table: cols for table, cols in tables.items() if "kind_code" in cols}
                year_only = {table: cols for table, cols in tables.items() if "kind_code" not in cols}
                data = snapshot_rows(c, grouped, where=sql.SQL("year=%s AND kind_code='A'"), params=(year,))
                totals = snapshot_rows(c, year_only, where=sql.SQL("year=%s"), params=(year,))
                for key in ("columns", "data"):
                    data[key].update(totals[key])
            if not all(data["data"].values()):
                raise ValueError("daily_sabr_incomplete")
            yield "daily-sabr", {"year": year, "completed_games": derived["completed_games"]}, data
        required = {f"{kind}_{stage}" for kind in ("A", "D") for stage in ("v1", "v2", "v2_recluster")}
        if not pitch.get("skipped") and not pitch["errors"] and required <= pitch.keys():
            cols = {table: names.split() for table, (_, names) in daily_derived_handoff.LABEL_LAYOUTS.items()}
            model = {"model_versions": "id task algo trained_at params cv_metrics".split()}
            with conn() as c, c.transaction():
                c.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
                data = snapshot_rows(c, cols, where=sql.SQL("year=%s AND kind_code IN ('A','D')"), params=(year,))
                versions = snapshot_rows(c, model, where=sql.SQL("id = ANY(%s)"),
                                         params=([f"pitch_type_v2_{year}{kind}" for kind in ("A", "D")],))
            if {row[1] for row in data["data"]["pitch_tracking"]} != {"A", "D"} or len(
                versions["data"]["model_versions"]
            ) != 2:
                raise ValueError("daily_pitch_label_incomplete")
            for key in ("columns", "data"):
                data[key].update(versions[key])
            yield "daily-pitch-labels", {"year": year}, data
        pa = self.daily.get("pa_observed") or {}
        if pa.get("games"):
            from pi_evening_handoff import _pa

            games = sorted({tuple(key) for key in pa["games"]})
            if any(y != year or k not in ("A", "C", "D", "E") for y, k, _ in games):
                raise ValueError("daily_pa_scope")
            packet = {"pa": {}, "predecessors": {}}
            with conn() as c, c.transaction():
                c.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
                for game in games:
                    key = "-".join(map(str, game))
                    calc, packet["pa"][key] = _pa(c, game)
                    prior = pa["predecessors"].get(key)
                    if prior is not None and prior != calc:
                        packet["predecessors"][key] = prior
            yield "daily-pa", {"games": games}, packet
        if "stats" in self.daily:
            yield from self.current_packets(year)
            advanced = self.advanced_packet(year)
            if advanced is not None:
                yield "daily-advanced", {"year": year}, advanced

    def current_packets(self, year):
        from cpbl.ingest import daily_current_handoff as contract

        def observed(value):
            if type(value) is int:
                return value > 0
            return type(value) is dict and "skipped" not in value and any(observed(v) for v in value.values())

        stats = self.daily["stats"]
        fields = [kind for kind, count in self.daily["fielding_observed"].items() if observed(count)]
        seen = {
            "pitching_current": observed(stats.get("pitching")),
            "batting_current": observed(stats.get("batting")),
            "fielding_current": bool(fields),
            "team_current": observed(stats.get("team")),
            "player_transactions": observed(self.daily["transactions"]),
            "team_standings": observed(self.daily["standings"]),
        }
        cols = {table: contract.TABLE_LAYOUTS[table][1].split() for table, wrote in seen.items() if wrote}
        packets = []
        with conn() as c, c.transaction():
            c.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            if cols:
                scoped_kinds = {"fielding_current": fields, "team_standings": ["A"],
                                "player_transactions": ["01", "02"]}
                current = snapshot_rows(c, {t: cols[t] for t in cols if t not in scoped_kinds},
                                        where=sql.SQL("year=%s"), params=(year,))
                for table, kinds in scoped_kinds.items():
                    if table not in cols:
                        continue
                    batch = snapshot_rows(c, {table: cols[table]},
                                          where=sql.SQL("year=%s AND kind_code=ANY(%s)"), params=(year, kinds))
                    for key in ("columns", "data"):
                        current[key].update(batch[key])
                if not all(current["data"].values()):
                    raise ValueError("current_observation_without_rows")
                packets.append(("daily-current", {"year": year, "tables": sorted(cols)}, current))
            seasons = self.daily["games_postseason"].get("games", {})
            candidates = {
                "D": self.daily["games_farm"],
                "E": seasons.get("E"),
                "C": seasons.get("C"),
                "F": self.daily["games_farm_final"].get("games"),
            }
            kinds = [k for k, value in candidates.items() if observed(value)]
            if kinds:
                assets = {table: contract.TABLE_LAYOUTS[table][1].split()
                          for table in ("games", "game_schedule_status_revisions", "game_source_revisions")}
                results = snapshot_rows(c, {t: assets[t] for t in assets if t != "game_source_revisions"},
                                        where=sql.SQL("year=%s AND kind_code=ANY(%s)"), params=(year, kinds))
                revisions = snapshot_rows(c, {"game_source_revisions": assets["game_source_revisions"]},
                                          where=sql.SQL("year=%s AND kind_code=ANY(%s) AND source='schedule'"),
                                          params=(year, kinds))
                for key in ("columns", "data"):
                    results[key].update(revisions[key])
                if not results["data"]["games"] or not results["data"]["game_schedule_status_revisions"]:
                    raise ValueError("non_a_schedule_observation_missing")
                packets.append(("non-a-results", {"year": year, "tables": sorted(assets)}, results))
        yield from packets

    def advanced_packet(self, year):
        from cpbl.ingest.advanced_handoff import DATA

        detail = self.daily.get("incremental_detail") or {}
        counts = [detail.get("advanced", 0), (detail.get("farm") or {}).get("advanced", 0)]
        observed_kinds = [kind for kind, value in zip(("A", "D"), counts, strict=True)
                          if type(value) is int and value > 0]
        accepted = sum(value for value in counts if type(value) is int and value > 0)
        if not observed_kinds:
            return None
        columns = [*DATA["player_stats"][1], "source_fetched_at"]
        with conn() as c, c.transaction():
            c.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            result = snapshot_rows(c, {"advanced_stats": columns},
                                   where=sql.SQL("year=%s AND kind_code=ANY(%s) AND source_fetched_at >= %s"),
                                   params=(year, observed_kinds, self.run.now))
        rows = result["data"]["advanced_stats"]
        if len(rows) != accepted:
            raise ValueError("advanced_daily_observation_count")
        grouped = {}
        for row in rows:
            values = dict(zip(columns, row, strict=True))
            fetched = values.pop("source_fetched_at")
            scope = values["kind_code"], values["role"]
            observed_at, scope_rows = grouped.setdefault(scope, (fetched, []))
            if fetched != observed_at:
                raise ValueError("advanced_mixed_scope_observation")
            scope_rows.append(values)
        # The daily worker observes scalar partials only. Full pointer promotion stays on its original path.
        return {"scopes": [{"year": year, "kind_code": kind, "dataset": "player_stats", "role": role,
                            "scope": "partial", "endpoint": "leaderboards/pr-table",
                            "source_fetched_at": fetched.isoformat(), "source_version": None, "rows": records}
                           for (kind, role), (fetched, records) in sorted(grouped.items())]}

    def send(self):
        deadline = time.monotonic() + self.timeout
        return {namespace: self.send_packet(namespace, scope, snapshot, deadline)
                for namespace, scope, snapshot in self.packets()}

    def send_packet(self, namespace, scope, snapshot, deadline):
        day = self.run.now.date()
        if day != datetime.now(self.feature.TAIPEI).date():
            raise ValueError("pi_batch_crossed_midnight")
        name = handoff.run_id("pi", day)
        encoded = json.dumps(snapshot, allow_nan=False, default=str, sort_keys=True, separators=(",", ":"))
        raw = (encoded + "\n").encode("ascii")
        if len(raw) > handoff.MAX_RESULTS:
            raise ValueError("pi_batch_size")
        receiver = json.loads(raw)
        scope = json.loads(json.dumps(scope))
        if namespace == "weekly-pitches":
            weekly_pitches_handoff.decode_snapshot(receiver, scope["games"])
        elif namespace == "weekly-box":
            weekly_box_handoff.decode_snapshot(receiver, scope["games"])
        out = self.run.root / "pi-handoff" / namespace
        out.mkdir(mode=0o700, parents=True, exist_ok=True)
        for directory in (out.parent, out):
            self.feature.sender._private(directory, directory=True)
        directory = out / name
        digest = hashlib.sha256(raw).hexdigest()
        if os.path.lexists(directory):
            self.feature.sender._private(directory, directory=True)
            receipt = self.feature._saved(directory / "sent.json")
            if (receipt and receipt["snapshot_sha256"] == digest
                    and all(receipt.get(k) == v for k, v in scope.items())):
                return {"state": "already_sent", **receipt}
            raise ValueError("pi_batch_attempt_already_started")
        directory.mkdir(mode=0o700)
        self.feature.sender._state(directory, "snapshot.json", encoded)
        response = {"version": 1, "source_id": "pi", "run_id": name, "as_of": day.isoformat(),
                    "snapshot_sha256": digest, "snapshot_bytes": len(raw), **scope}
        self.feature._save(directory, "response.json", response)
        response_sha = hashlib.sha256((directory / "response.json").read_bytes()).hexdigest()
        self.feature._save(directory, "notification.json",
                           {"version": 1, "run_id": name, "response_sha256": response_sha})
        sender = self.feature.sender
        auth = sender._authentication(sender.IDENTITY_FILE, sender.KNOWN_HOSTS)
        transport = self.feature._run_native(sender._sftp_command(*auth, sender.USER), directory,
                                             {"LANG": "C", "LC_ALL": "C"}, deadline,
                                             publication_batch(namespace, name))
        if transport["native_rc"] != 0 or transport["timed_out"]:
            raise ValueError("pi_batch_transport_failed")
        receipt = {**response, "response_sha256": response_sha, "transport": transport}
        self.feature._save(directory, "sent.json", receipt)
        return {"state": "sent", **receipt}
