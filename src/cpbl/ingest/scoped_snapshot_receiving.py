"""Read a fixed JSON snapshot and its last-written notice from the private inbox."""

import hashlib
from pathlib import Path

from cpbl.features.handoff import MAX_MANIFEST, _need, _object, _read, run_id

MAX_SNAPSHOT = 64 * 1024 * 1024


def read_snapshot(root: Path, namespace: str, source_id: str, day, scope_fields: set[str]):
    key = run_id(source_id, day)
    directory = root / "incoming" / namespace / key
    notify = root / "incoming" / f"{namespace}-notify"
    _need(root.is_absolute() and directory.resolve() == directory and notify.resolve() == notify,
          "scoped_snapshot_inbox_path")
    notice = _object(_read(notify / f"{key}.ready", MAX_MANIFEST))
    response = _read(directory / "response.json", MAX_MANIFEST)
    response_sha = hashlib.sha256(response).hexdigest()
    _need(notice == {"version": 1, "run_id": key, "response_sha256": response_sha}
          and type(notice["version"]) is int, "scoped_snapshot_notice")
    manifest = _object(response)
    _need(isinstance(manifest, dict) and set(manifest) == scope_fields | {
        "version", "source_id", "run_id", "as_of", "snapshot_sha256", "snapshot_bytes",
    } and type(manifest["version"]) is int and manifest["version"] == 1
        and (manifest["source_id"], manifest["run_id"], manifest["as_of"])
        == (source_id, key, day.isoformat()), "scoped_snapshot_identity")
    raw = _read(directory / "snapshot.json", MAX_SNAPSHOT)
    _need(type(manifest["snapshot_bytes"]) is int and manifest["snapshot_bytes"] == len(raw)
          and manifest["snapshot_sha256"] == hashlib.sha256(raw).hexdigest(), "scoped_snapshot_digest")
    return {**manifest, "response_sha256": response_sha}, _object(raw)
