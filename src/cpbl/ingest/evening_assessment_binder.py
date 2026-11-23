"""Automatically bind own nightly metadata to already-persisted official facts."""

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from cpbl.features.handoff import MAX_MANIFEST, _need, _object, _read
from cpbl.ingest import evening_handoff, evening_official_facts, evening_result_fields

TAIPEI = ZoneInfo("Asia/Taipei")
def read_intent(inbox, source, name, now):
    day = now.astimezone(TAIPEI).date()
    request, keys, directory = evening_handoff._read_request(inbox, source, day, name)
    _need(request["parts"] in (["results"], ["signals"], ["results", "signals"]),
          "evening_binder_parts")
    # This input cannot enter the writer; the metadata root contains no snapshot.json.
    _need(not os.path.lexists(directory / "snapshot.json"), "evening_binder_writer_payload")
    raw = _read(directory / "scope.json", MAX_MANIFEST)
    _need(type(request["snapshot_bytes"]) is int and request["snapshot_bytes"] == len(raw)
          and request["snapshot_sha256"] == hashlib.sha256(raw).hexdigest(), "evening_binder_scope_digest")
    document = _object(raw)
    _need(isinstance(document, dict) and set(document) == {"fields"}
          and isinstance(document["fields"], dict) and set(document["fields"]) == {k.text for k in keys},
          "evening_binder_scope")
    for key in keys:
        fields = document["fields"][key.text]
        _need(isinstance(fields, list) and fields and all(isinstance(field, str) for field in fields)
              and fields == sorted(set(fields))
              and set(fields) <= {*evening_result_fields.GAME_COLUMNS, "signals"}
              and all(("signals" if field == "signals" else "results") in request["parts"] for field in fields)
              and ("signals" not in fields or key.kind_code in ("C", "E")), "evening_binder_requested_fields")
    return request, keys, document["fields"]


def derive(facts_root, keys, requested, now, max_age):
    """Only the independent VPS live worker facts can authorize missing/corrected fields."""
    day = now.astimezone(TAIPEI).date()
    partitions, expected = {}, {}
    for key in keys:
        if key.year != day.year or key.kind_code not in evening_official_facts.KINDS:
            continue
        pair = key.kind_code, key.year, day.month
        if pair not in partitions:
            partitions[pair] = evening_official_facts.read_partition(facts_root, *pair, now, max_age)
        values = partitions[pair].get(key.text)
        if (not isinstance(values, dict) or set(values) != evening_official_facts.FIELDS
                or values["game_date"] != day.isoformat()
                or not all(value is None or isinstance(value, str) for value in values.values())):
            continue
        if {"home_score", "away_score"} & set(requested[key.text]):
            values = {**values, **evening_official_facts.read_final_score(facts_root, key.text, day, now, max_age)}
        expected[key.text] = {"result_fields": {
            field: evening_result_fields.value_sha256(values[field])
            if field in values and values[field] is not None and values[field] != "" else None
            for field in requested[key.text]
        }}
    return expected


def bind_one(facts_root, inbox, bindings, source, name, now, max_age, ttl):
    request, keys, fields = read_intent(inbox, source, name, now)
    result = derive(facts_root, keys, fields, now, max_age)
    if not result:
        return {"batch_id": name, "state": "awaiting_official_scope", "games": 0}
    path = evening_handoff.receipt_path(bindings, source, name)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if os.path.lexists(path):
        prior = _object(_read(path, evening_handoff.MAX_RECEIPT))
        _need(prior["response_sha256"] == request["response_sha256"], "evening_binder_prior_conflict")
        return {"batch_id": name, "state": "previously_bound", "games": len(prior["expected"])}
    content = {key: request[key] for key in ("version", "source_id", "batch_id", "as_of", "games", "parts",
                                            "response_sha256")}
    content.update(expires_at=(now + ttl).isoformat(), expected=result)
    temporary = path.with_suffix(".binding-pending")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as out:
        out.write(json.dumps(content, sort_keys=True, ensure_ascii=False) + "\n")
        out.flush()
        os.fsync(out.fileno())
    os.link(temporary, path)
    temporary.unlink()
    evening_handoff.sync_directory(path.parent)
    return {"batch_id": name, "state": "bound", "games": len(result)}


def bind_pending(inbox, bindings, facts_root, source, now, *, limit, max_age, ttl):
    _need(min(limit, max_age.total_seconds(), ttl.total_seconds()) > 0, "evening_binder_limit")
    roots = (inbox, bindings, facts_root)
    _need(all(root.is_absolute() and root.resolve() == root and root.is_dir() for root in roots)
          and len(set(roots)) == len(roots)
          and all(not a.is_relative_to(b) for a in roots for b in roots if a != b),
          "evening_binder_separate_roots")
    info = bindings.stat()
    _need(info.st_uid == os.getuid() and not (info.st_mode & 0o022), "evening_binder_output_owner")
    notify = inbox / "incoming" / f"{evening_handoff.NAMESPACE}-notify"
    _need(inbox.is_absolute() and notify.resolve() == notify and notify.is_dir(), "evening_binder_inbox")
    day = now.astimezone(TAIPEI).date()
    candidates = []
    for path in notify.glob("*.ready"):
        _need(not path.is_symlink() and path.is_file()
              and evening_handoff.BATCH_ID.fullmatch(path.stem), "evening_binder_notice_file")
        accepted = datetime.fromtimestamp(path.lstat().st_mtime, TAIPEI)
        if accepted.date() != day or accepted > now:
            continue
        if not os.path.lexists(evening_handoff.receipt_path(bindings, source, path.stem)):
            candidates.append((accepted, path.stem))
    return [bind_one(facts_root, inbox, bindings, source, name, now, max_age, ttl)
            for _, name in sorted(candidates)[:limit]]


def run_from_environment(now, *, limit, max_age, ttl):
    source = os.environ["CPBL_EVENING_RECEIPT_SOURCE_ID"]
    _need(bool(evening_handoff.SOURCE_ID.fullmatch(source)), "evening_binder_source")
    return bind_pending(
        Path(os.environ["CPBL_EVENING_RESULT_ASSESSMENT_INBOX_ROOT"]),
        Path(os.environ["CPBL_EVENING_ASSESSMENT_BINDINGS_ROOT"]),
        Path(os.environ["CPBL_EVENING_TRUSTED_FACTS_ROOT"]),
        source, now, limit=limit, max_age=timedelta(seconds=max_age), ttl=timedelta(seconds=ttl),
    )


def main(argv=None):
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--limit", required=True, type=int)
    parser.add_argument("--max-observation-age", required=True, type=int)
    parser.add_argument("--binding-ttl", required=True, type=int)
    args = parser.parse_args(argv)
    os.umask(0o077)
    for result in run_from_environment(datetime.now(TAIPEI), limit=args.limit,
                                       max_age=args.max_observation_age, ttl=args.binding_ttl):
        print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
