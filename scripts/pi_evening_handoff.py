"""Connect the existing evening Box/PA entry to the scoped sender and receipt reader."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import time
from datetime import datetime

from pi_job_handoff import snapshot_rows
from psycopg import sql

from cpbl.db import conn
from cpbl.ingest import boxpa_sync, evening_receipt, postseason_evening

BOX = (*boxpa_sync.BOX_TABLES, "game_livelog_extra", "game_source_revisions")


def _need(ok, reason):
    if not ok:
        raise ValueError(reason)


def _columns(connection, table):
    return [row[0] for row in connection.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_schema='cpbl' "
        "AND table_name=%s ORDER BY ordinal_position", (table,),
    ).fetchall()]


def _box(connection, games):
    placeholders = sql.SQL(", ").join([sql.SQL("(%s,%s,%s)")] * len(games))
    base = sql.SQL("(year,kind_code,game_sno) IN ({})").format(placeholders)
    fields = {table: _columns(connection, table) for table in BOX}
    values = tuple(value for key in games for value in key)
    revision = "game_source_revisions"
    versions = snapshot_rows(connection, {revision: fields.pop(revision)},
                             where=base + sql.SQL(" AND source IN ('livelog','scoreboard')"), params=values)
    rows = snapshot_rows(connection, fields, where=base, params=values)
    for group in ("columns", "data"):
        rows[group].update(versions[group])
    return rows


def _pa(connection, key):
    scope = sql.SQL("(year,kind_code,game_sno)=(%s,%s,%s)")
    current, = connection.execute(
        sql.SQL("SELECT build_id,livelog_revision_id,tracking_revision_id FROM cpbl.game_recap_builds "
                "WHERE {} AND state='published'").format(scope), key,
    ).fetchall()
    build_id, live, tracking = current
    result = {"columns": {}, "data": {}}
    for table in boxpa_sync.PA_TABLES:
        cols = _columns(connection, table)
        where, values = (
            (sql.SQL("id=ANY(%s)"), ([live] if tracking is None else [live, tracking],))
            if table == "game_recap_source_revisions" else
            (sql.SQL("pa_row_id IN (SELECT pa_row_id FROM cpbl.game_plate_appearances WHERE build_id=%s)"),
             (build_id,)) if table == "game_pa_events" else
            (sql.SQL("build_id=%s"), (build_id,))
        )
        found = snapshot_rows(connection, {table: cols}, where=where, params=values)
        for group in result:
            result[group].update(found[group])
    return str(build_id), result


def snapshot_from_job(keys, parts, state):
    games = [(g.year, g.kind_code, g.game_sno) for g in boxpa_sync.parse_games(keys)]
    parts = parts.split(",")
    packet = {"box": None, "pa": {}, "predecessors": {}}
    builds = {}
    with conn() as c, c.transaction():
        c.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        if "box" in parts:
            packet["box"] = _box(c, games)
        if "pa" in parts:
            for y, kind, sno in games:
                name = f"{y}-{kind}-{sno}"
                builds[name], packet["pa"][name] = _pa(c, (y, kind, sno))
                prior = ((state["boxpa"].get(name) or {}).get("manifest") or {}).get("published_build_prod")
                if prior and prior != builds[name]:
                    packet["predecessors"][name] = prior
    return games, parts, packet, builds


def publication_batch(batch_id):
    _need(evening_receipt.BATCH.fullmatch(batch_id), "evening_id")
    parent = f"/incoming/evening-boxpa/{batch_id}"
    return (
        f"mkdir {parent}\n"
        f'put "snapshot.json" {parent}/.snapshot.json.upload\n'
        f"rename {parent}/.snapshot.json.upload {parent}/snapshot.json\n"
        f'put "response.json" {parent}/.response.json.upload\n'
        f"rename {parent}/.response.json.upload {parent}/response.json\n"
        f'put "notification.json" {parent}/.ready.upload\n'
        f"rename {parent}/.ready.upload /incoming/evening-boxpa-notify/{batch_id}.ready\n"
    ).encode("ascii")


def assessment_upload(batch_id):
    """Publish scoped metadata to the inbox that has no publication watcher."""
    _need(evening_receipt.BATCH.fullmatch(batch_id), "evening_id")
    parent = f"/assessment/incoming/evening-boxpa/{batch_id}"
    return (
        f"mkdir {parent}\n"
        f'put "scope.json" {parent}/.scope.json.upload\n'
        f"rename {parent}/.scope.json.upload {parent}/scope.json\n"
        f'put "response.json" {parent}/.response.json.upload\n'
        f"rename {parent}/.response.json.upload {parent}/response.json\n"
        f'put "notification.json" {parent}/.ready.upload\n'
        f"rename {parent}/.ready.upload /assessment/incoming/evening-boxpa-notify/{batch_id}.ready\n"
    ).encode("ascii")


def submit_assessment(batch, root, targets, now):
    """Notify exactly once per deterministic same-date field scope."""
    feature = batch.feature
    sender = feature.sender
    fields = {key: sorted(names) for key, names in sorted(targets.items())}
    games = [(int(year), kind, int(sno)) for year, kind, sno in (key.split("-") for key in fields)]
    parts = []
    if any(set(names) - {"signals"} for names in fields.values()):
        parts.append("results")
    if any("signals" in names for names in fields.values()):
        parts.append("signals")
    scope = evening_receipt.as_bytes({"fields": fields})
    offer = evening_receipt.make_offer(now.date(), games, parts, scope)
    name = offer["batch_id"]
    response = evening_receipt.as_bytes(offer)
    digest = hashlib.sha256(response).hexdigest()
    pending = {"offer": offer, "response_sha256": digest, "sent_at": now.isoformat()}
    directory = root / name
    if not os.path.lexists(directory):
        directory.mkdir(mode=0o700)
        sender._state(directory, "scope.json", scope.decode().rstrip("\n"))
        sender._state(directory, "response.json", response.decode().rstrip("\n"))
        feature._save(directory, "notification.json", {"version": 1, "batch_id": name, "response_sha256": digest})
        feature._save(directory, "pending.json", pending)
    sender._private(directory, directory=True)
    saved = feature._saved(directory / "pending.json")
    _need(saved is not None and all(saved.get(k) == pending[k] for k in ("offer", "response_sha256")),
          "evening_assessment_metadata_identity")
    for file, expected in (("scope.json", scope), ("response.json", response)):
        path = directory / file
        sender._private(path)
        _need(path.stat().st_size == len(expected) and path.read_bytes() == expected,
              "evening_assessment_metadata_bytes")
    marker = directory / "transport-attempt"
    if not os.path.lexists(marker):
        auth = sender._authentication(sender.IDENTITY_FILE, sender.KNOWN_HOSTS)
        with marker.open("x") as handle:
            handle.write(digest + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        transport = feature._run_native(sender._sftp_command(*auth, sender.USER), directory,
                                        {"LANG": "C", "LC_ALL": "C"}, time.monotonic() + batch.timeout,
                                        assessment_upload(name))
        batch.run.detail["evening_assessment_transport"] = {"batch_id": name, "transport": transport}
    return saved


def _out(batch):
    root = batch.run.root / "pi-handoff" / "evening-boxpa"
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    for folder in (root.parent, root):
        batch.feature.sender._private(folder, directory=True)
    return root


def prepare(batch, games, scopes, data, builds, *, result_group=False):
    feature = batch.feature
    now = datetime.now(feature.TAIPEI)
    raw = evening_receipt.as_bytes(data)
    offer = evening_receipt.make_offer(now.date(), games, scopes, raw)
    batch_id = offer["batch_id"]
    directory = _out(batch) / batch_id
    if os.path.lexists(directory):
        raise ValueError("evening_attempt_already_exists")
    directory.mkdir(mode=0o700)
    feature.sender._state(directory, "snapshot.json", raw.decode().rstrip("\n"))
    response = evening_receipt.as_bytes(offer)
    feature.sender._state(directory, "response.json", response.decode().rstrip("\n"))
    response_sha = hashlib.sha256(response).hexdigest()
    feature._save(directory, "notification.json",
                  {"version": 1, "batch_id": batch_id, "response_sha256": response_sha})
    feature._save(directory, "pending.json", {"offer": offer, "response_sha256": response_sha,
                  "sent_at": now.isoformat(), "pa_builds": builds, "initial_assessment": not result_group,
                  "result_group": result_group})
    return batch_id


def transmit(batch, batch_id):
    feature = batch.feature
    directory = _out(batch) / batch_id
    pending = feature._saved(directory / "pending.json")
    offer = pending["offer"]
    _need(offer["batch_id"] == batch_id, "evening_staged_identity")
    raw = (directory / "snapshot.json").read_bytes()
    _need(hashlib.sha256(raw).hexdigest() == offer["snapshot_sha256"]
          and hashlib.sha256((directory / "response.json").read_bytes()).hexdigest()
          == pending["response_sha256"], "evening_staged_hash")
    sender = feature.sender
    auth = sender._authentication(sender.IDENTITY_FILE, sender.KNOWN_HOSTS)
    with (directory / "transport-attempt").open("x") as marker:
        marker.write(pending["response_sha256"] + "\n")
        marker.flush()
        os.fsync(marker.fileno())
    transport = feature._run_native(sender._sftp_command(*auth, sender.USER), directory,
                                    {"LANG": "C", "LC_ALL": "C"}, time.monotonic()+batch.timeout,
                                    publication_batch(batch_id))
    batch.run.detail["evening_handoff"] = {"batch_id": batch_id, "state": "pending_receipt",
                                            "transport": transport, "snapshot_sha256": offer["snapshot_sha256"]}
    return 0 if transport["native_rc"] == 0 and not transport["timed_out"] else 69


def send(batch, keys, parts):
    state = postseason_evening.load_state(postseason_evening.state_path())
    games, scopes, data, builds = snapshot_from_job(keys, parts, state)
    return transmit(batch, prepare(batch, games, scopes, data, builds))


def read_receipt(batch, batch_id, *, assess=False, assessment=None):
    """Read one receipt via the separate pinned forced-command identity."""
    _need(evening_receipt.BATCH.fullmatch(batch_id), "evening_id")
    sender = batch.feature.sender
    identity = os.environ["CPBL_PI_EVENING_RECEIPT_IDENTITY"]
    user = os.environ["CPBL_PI_EVENING_RECEIPT_USER"]
    _need(re.fullmatch(r"[a-z][a-z0-9-]{1,63}", user) and user != sender.USER, "evening_reader_role")
    key, hosts = sender._authentication(identity, sender.KNOWN_HOSTS)
    upload = sender.IDENTITY_FILE.stat()
    reader = key.stat()
    _need((reader.st_dev, reader.st_ino) != (upload.st_dev, upload.st_ino), "evening_reader_key")
    # Reuse the original sealed client options, with a fixed point-read command instead of an SFTP batch.
    sftp = sender._sftp_command(key, hosts, user)
    _need(sftp[:5] == ["/usr/bin/sftp", "-F", "/dev/null", "-b", "-"] and sftp[5] == "-P",
          "evening_reader_transport")
    operation = assessment or ("assess" if assess else None)
    _need(operation in (None, "assess", "assess-results"), "evening_reader_operation")
    fixed_command = [operation, batch_id] if operation else [batch_id]
    command = ["/usr/bin/ssh", "-T", *sftp[1:3], "-p", *sftp[6:], *fixed_command]
    receipt = subprocess.run(command, stdin=subprocess.DEVNULL, capture_output=True, timeout=batch.timeout,
                             check=False, env={"LANG": "C", "LC_ALL": "C"})
    if receipt.returncode == 75 and not receipt.stdout:
        return None
    _need(receipt.returncode == 0 and 0 < len(receipt.stdout) <= evening_receipt.LIMIT,
          "evening_receipt_reader_failure")
    return receipt.stdout


def poll(batch):
    """One own-receipt lookup. Unknown or absent receipts leave progress intact."""
    path = postseason_evening.state_path()
    state = postseason_evening.load_state(path)
    root = _out(batch)
    known = state.get("boxpa_receipts") or {}
    for directory in sorted(root.iterdir()):
        name = directory.name
        if not evening_receipt.BATCH.fullmatch(name) or name in known:
            continue
        batch.feature.sender._private(directory, directory=True)
        pending = batch.feature._saved(directory / "pending.json")
        _need(isinstance(pending, dict) and pending["offer"]["batch_id"] == name, "evening_pending_identity")
        is_result = evening_receipt.result_parts(pending["offer"]["parts"])
        if pending.get("result_group") is True and not (directory / "transport-attempt").exists():
            continue
        received = read_receipt(batch, name)
        if received is not None:
            manifest = json.loads(received)["manifest"]
            builds = pending["pa_builds"]
            _need(all(manifest["games"].get(k, {}).get("published_build_local") == v and
                      manifest["games"].get(k, {}).get("published_build_prod") == v for k, v in builds.items()),
                  "evening_receipt_pa_build")
        updated, status = evening_receipt.advance(
            state, pending["offer"], pending["response_sha256"], received,
            datetime.fromisoformat(pending["sent_at"]), datetime.now(batch.feature.TAIPEI),
        )
        if status == "recorded":
            # Reclassify after the original record transition, then persist it and the marker together.
            now = datetime.now(batch.feature.TAIPEI)
            if not is_result:
                postseason_evening._boxpa_prepare_state(updated, now, postseason_evening._season_year(now))
            postseason_evening.save_json(path, updated)
        batch.run.detail["evening_handoff"] = {"batch_id": name, "state": status}
        if status == "waiting" and pending.get("initial_assessment") is True:
            advisory = read_receipt(batch, name, assess=True)
            if advisory is not None:
                reply = verified_assessment(batch, pending, advisory)
                batch.run.detail["evening_handoff"]["assessment"] = reply["games"]
        return status
    return "idle"

def verified_assessment(batch, pending, raw):
    offer = pending["offer"]
    reply = json.loads(raw)
    _need(set(reply) == {"version", "source_id", "as_of", "batch_id", "response_sha256", "checked_at", "games"}
          and (reply["version"], reply["source_id"], reply["as_of"], reply["batch_id"], reply["response_sha256"])
          == (1, "pi", offer["as_of"], offer["batch_id"], pending["response_sha256"]),
          "evening_assessment_binding")
    checked = datetime.fromisoformat(reply["checked_at"])
    now = datetime.now(batch.feature.TAIPEI)
    _need(checked.utcoffset() is not None and 0 <= (now-checked).total_seconds() <= batch.timeout,
          "evening_assessment_time")
    scope = {f"{y}-{k}-{n}" for y, k, n in offer["games"]}
    _need(set(reply["games"]) == scope, "evening_assessment_games")
    for result in reply["games"].values():
        missing = result.get("missing_or_unverified")
        confirmed = result.get("confirmed_missing")
        _need(set(result) == {"reuse", "missing_or_unverified", "confirmed_missing"}
              and type(result["reuse"]) is bool and type(missing) is list and type(confirmed) is list
              and result["reuse"] == (not missing)
              and set(missing) <= {"final", "www_box", "stats_tracking", "pa"}
              and set(confirmed) <= set(missing) & {"www_box", "stats_tracking"}
              and ("final" not in missing or not confirmed), "evening_assessment_result")
    return reply


def source_decision(batch, keys, action):
    """Consult only a recorded own batch. Never fetch because a version was merely unverified."""
    games = keys.split(",")
    state = postseason_evening.load_state(postseason_evening.state_path())
    known = state.get("boxpa_receipts") or {}
    candidates = []
    for batch_id in known:
        if not evening_receipt.BATCH.fullmatch(batch_id):
            raise ValueError("evening_known_batch_identity")
        folder = _out(batch) / batch_id
        batch.feature.sender._private(folder, directory=True)
        pending = batch.feature._saved(folder / "pending.json")
        if not pending:
            continue
        offer = pending["offer"]
        evening_receipt.validate_offer(offer)
        scope = {f"{y}-{k}-{n}" for y, k, n in offer["games"]}
        if set(games) <= scope:
            candidates.append(pending)
    if not candidates:
        return {"state": "no_own_assessment_scope", "games": keys}, []
    pending = max(candidates, key=lambda value: datetime.fromisoformat(value["sent_at"]))
    offer = pending["offer"]
    raw = read_receipt(batch, offer["batch_id"], assess=True)
    if raw is None:
        return {"state": "assessment_pending", "games": keys}, []
    reply = verified_assessment(batch, pending, raw)
    source = "www_box" if action == "detail" else "stats_tracking"
    selected = []
    for key in games:
        result = reply["games"][key]
        confirmed = result["confirmed_missing"]
        if source in confirmed:
            selected.append(key)
    confirmed_all = all(reply["games"][key]["reuse"] for key in games)
    return {"state": "reused_existing" if confirmed_all else "assessed",
            "batch_id": offer["batch_id"], "games": keys, "fetch_games": selected}, selected
