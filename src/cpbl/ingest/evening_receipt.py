"""Private evening batch identities and a receipt-driven state transition."""

from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from datetime import date, datetime

from cpbl.ingest import boxpa_sync, postseason_evening

BATCH = re.compile(r"[a-f0-9]{32}\Z")
SHA = re.compile(r"[a-f0-9]{64}\Z")
LIMIT = 64 * 1024
SNAPSHOT_LIMIT = 64 * 1024 * 1024
PARTS = ("box", "pa", "results", "signals")
OFFER_KEYS = {"version", "source_id", "as_of", "batch_id", "games", "parts", "snapshot_sha256", "snapshot_bytes"}
RECEIPT_KEYS = (OFFER_KEYS - {"snapshot_bytes"}) | {"response_sha256", "published_at", "rc", "manifest"}


def _need(ok, reason):
    if not ok:
        raise ValueError(reason)


def as_bytes(value):
    return json.dumps(value, allow_nan=False, default=str, sort_keys=True, separators=(",", ":")).encode() + b"\n"


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _object(raw):
    def unique(pairs):
        mapped = {}
        for key, value in pairs:
            _need(key not in mapped, "evening_duplicate_json_key")
            mapped[key] = value
        return mapped
    value = json.loads(raw, object_pairs_hook=unique)
    _need(type(value) is dict, "evening_object_required")
    return value


def _scope(games, parts):
    _need(type(parts) is list and parts and parts == [p for p in PARTS if p in parts]
          and (set(parts) <= {"box", "pa"} or set(parts) <= {"results", "signals"}), "evening_parts")
    kinds = ("A", "C", "E", "F") if "results" in parts else ("C", "E") if "signals" in parts else ("A", "C", "E")
    _need(type(games) is list and 0 < len(games) <= boxpa_sync.MAX_GAMES
          and all(type(key) is list and len(key) == 3 and type(key[0]) is int
                  and key[1] in kinds and type(key[2]) is int and key[2] > 0
                  for key in games), "evening_game_scope")
    _need(games == sorted(games) and len({tuple(key) for key in games}) == len(games), "evening_game_order")
    return [f"{y}-{kind}-{game}" for y, kind, game in games]


def result_parts(parts):
    return any(part in ("results", "signals") for part in parts)


def batch_id(offer):
    identity = {key: offer[key] for key in ("source_id", "as_of", "games", "parts", "snapshot_sha256")}
    return _sha(json.dumps(identity, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode())[:32]


def validate_offer(offer):
    _need(type(offer) is dict and set(offer) == OFFER_KEYS and type(offer["version"]) is int
          and offer["version"] == 1 and offer["source_id"] == "pi", "evening_offer_fields")
    day = date.fromisoformat(offer["as_of"])
    _need(day.isoformat() == offer["as_of"], "evening_offer_date")
    _scope(offer["games"], offer["parts"])
    _need(isinstance(offer["snapshot_sha256"], str) and SHA.fullmatch(offer["snapshot_sha256"])
          and type(offer["snapshot_bytes"]) is int and 0 < offer["snapshot_bytes"] <= SNAPSHOT_LIMIT,
          "evening_snapshot_binding")
    _need(offer["batch_id"] == batch_id(offer), "evening_batch_identity")


def make_offer(day, games, parts, snapshot_raw):
    offer = {
        "version": 1, "source_id": "pi", "as_of": day.isoformat(),
        "games": sorted(map(list, games)), "parts": list(parts),
        "snapshot_sha256": _sha(snapshot_raw), "snapshot_bytes": len(snapshot_raw),
    }
    offer["batch_id"] = batch_id(offer)
    validate_offer(offer)
    return offer


def validate_receipt(receipt, offer, response_sha):
    validate_offer(offer)
    _need(type(receipt) is dict and set(receipt) == RECEIPT_KEYS and
          all(type(receipt[k]) is type(v) and receipt[k] == v for k, v in offer.items() if k not in ("version", "snapshot_bytes"))
          and type(receipt["version"]) is int and receipt["version"] == offer["version"]
          and receipt["response_sha256"] == response_sha and SHA.fullmatch(response_sha)
          and type(receipt["rc"]) is int and receipt["rc"] == 0, "evening_receipt_binding")
    published = datetime.fromisoformat(receipt["published_at"])
    _need(published.utcoffset() is not None, "evening_receipt_time")
    manifest = receipt["manifest"]
    required = {"at", "ok", "games", "delivery_mode"}
    if result_parts(offer["parts"]):
        required.add("rows")
    _need(type(manifest) is dict and set(manifest) == required
          and ("rows" not in manifest or (type(manifest["rows"]) is dict
                                         and all(type(n) is int and n >= 0 for n in manifest["rows"].values())))
          and manifest["delivery_mode"] in ("committed", "reused_existing")
          and manifest["at"] == receipt["published_at"] and manifest["ok"] is True
          and type(manifest["games"]) is dict
          and set(manifest["games"]) == set(_scope(offer["games"], offer["parts"])),
          "evening_receipt_reconcile")
    for value in manifest["games"].values():
        _need(type(value) is dict
              and ("box" not in offer["parts"] or value.get("box_ok") is True)
              and ("results" not in offer["parts"] or value.get("results_ok") is True)
              and ("signals" not in offer["parts"] or value.get("signals_ok") is True)
              and ("pa" not in offer["parts"] or
                   (value.get("pa_ok") is True and value.get("pa_sent") is True)),
              "evening_receipt_parts")
    return published


def advance(state, offer, response_sha, received, sent_at, now):
    """Return a new state only after an exact trusted receipt. Persist it once atomically."""
    if received is None:
        return state, "waiting"
    _need(0 < len(received) <= LIMIT, "evening_receipt_size")
    receipt = _object(received)
    published = validate_receipt(receipt, offer, response_sha)
    _need(sent_at.utcoffset() is not None and now.utcoffset() is not None and sent_at <= published <= now,
          "evening_receipt_time_order")
    key = offer["batch_id"]
    previous = (state.get("boxpa_receipts") or {}).get(key)
    digest = _sha(received)
    if previous is not None:
        _need(previous == digest, "evening_receipt_changed")
        return state, "already_recorded"
    if result_parts(offer["parts"]):
        updated = deepcopy(state)
        updated.setdefault("boxpa_receipts", {})[key] = digest
        return updated, "recorded"
    keys = _scope(offer["games"], offer["parts"])
    _need(all(k in state.get("boxpa", {}) for k in keys), "evening_pending_scope_missing")
    updated = deepcopy(state)
    elapsed = (published - sent_at).total_seconds()
    result = postseason_evening.boxpa_record_sync(
        updated, published, keys, 0, receipt["manifest"], elapsed, offer["parts"],
    )
    if result != "ok":
        return state, result
    updated.setdefault("boxpa_receipts", {})[key] = digest
    return updated, "recorded"
