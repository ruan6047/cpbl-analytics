"""Minimal trusted observations retained from the live worker's existing schedule GET."""

import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from cpbl.features.handoff import _need, _object, _read
from cpbl.ingest.postseason_evening import parse_stats_games
from cpbl.readiness_checks import identity, inspect_partition

PARTITION_LIMIT = 1024 * 1024
ORIGIN = "vps-live-worker-existing-stats-schedule"
KINDS = ("A", "C", "E")  # The existing live worker does not request F.
FIELDS = {"game_date", "home_team_code", "away_team_code", "venue"}


def _path(root: Path, kind: str, year: int, month: int):
    _need(root.is_absolute() and root.resolve() == root and root.is_dir()
          and kind in KINDS and 1 <= month <= 12 and 2026 <= year <= 9999, "evening_facts_root")
    return root / f"{year}-{kind}-{month:02d}.json"


def project(kind, year, month, payload, observed_at):
    rows = payload.get("Data") if isinstance(payload, dict) else None
    rows = rows.get("Games") if isinstance(rows, dict) else None
    if not isinstance(rows, list):
        raise ValueError("evening_facts_list")
    _need(inspect_partition(payload, year=year, month=month, kind=kind)["state"] == "complete",
          "evening_facts_list")
    facts, ambiguous = {}, set()
    observed = parse_stats_games(rows, year, (kind,))
    for game in observed:
        if not game.game_date or not game.game_date.startswith(f"{year}-{month:02d}-"):
            continue
        entry = {
            "game_date": game.game_date, "home_team_code": game.home_code,
            "away_team_code": game.away_code, "venue": game.venue,
        }
        if game.key in facts and facts[game.key] != entry:
            ambiguous.add(game.key)
        facts[game.key] = entry
    return {"version": 1, "origin": ORIGIN, "kind": kind, "year": year, "month": month,
            "observed_at": observed_at.astimezone(UTC).isoformat(),
            "games": {key: entry for key, entry in facts.items() if key not in ambiguous}}


def _save(root, target, value):
    info = root.stat()
    _need(info.st_uid == os.getuid() and not (info.st_mode & 0o022), "evening_facts_owner")
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    _need(len(raw) <= PARTITION_LIMIT, "evening_facts_bytes")
    with tempfile.NamedTemporaryFile(dir=root, prefix=".facts-", delete=False) as out:
        temporary = Path(out.name)
        try:
            out.write(raw)
            out.flush()
            os.fsync(out.fileno())
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)


def writer(root: Path, *, clock=None):
    """A callback on the existing successful HTTP response, with no HTTP client of its own."""
    clock = clock or (lambda: datetime.now(UTC))

    def retain(kind, year, month, payload):
        target = _path(root, kind, year, month)
        _save(root, target, project(kind, year, month, payload, clock()))

    return retain


def _score_path(root, game_id):
    _need(root.is_absolute() and root.resolve() == root and root.is_dir()
          and identity(game_id) is not None, "evening_score_facts_path")
    return root / f"final-score-{game_id}.json"


def _matches_game(game_id, raw):
    key = identity(game_id)
    return (key is not None and isinstance(raw, dict) and identity(raw.get("GameId")) == key
            and (raw.get("KindCode"), raw.get("GameSno")) == key[1:]
            and type(raw.get("GameSno")) is int)


def final_score_fields(game_id, raw):
    """No inference from pitch order, inning totals, a score being non-zero or Redis phase."""
    if not _matches_game(game_id, raw) or raw.get("GameStatus") != "FINISHED":
        return None
    observed = raw.get("PreExeDate")
    if not isinstance(observed, str):
        return None
    try:
        instant = datetime.fromisoformat(observed)
    except ValueError:
        return None
    local = instant.astimezone(ZoneInfo("Asia/Taipei")) if instant.tzinfo else instant
    scores = {}
    for side, field in (("Home", "home_score"), ("Visiting", "away_score")):
        team = raw.get(side)
        value = team.get("Score") if isinstance(team, dict) else None
        if type(value) is not int or value < 0:
            return None
        scores[field] = value
    return {"game_date": local.date().isoformat(), **scores}


def final_score_writer(root: Path, *, clock=None):
    clock = clock or (lambda: datetime.now(UTC))

    def retain(game_id, raw):
        if not _matches_game(game_id, raw):
            return
        value = final_score_fields(game_id, raw)
        # A newer same-game observation without final scores supersedes our previous proof.
        _save(root, _score_path(root, game_id), {
            "version": 1, "origin": "vps-live-worker-existing-stats-game",
            "status": "FINISHED" if value is not None else "unproven",
            "game_id": game_id, "observed_at": clock().astimezone(UTC).isoformat(),
            "values": value if value is not None else {},
        })

    return retain


def _read_owned(path, limit):
    owner = int(os.environ.get("CPBL_EVENING_TRUSTED_FACTS_UID", str(os.getuid())))
    info = path.parent.stat()
    _need(info.st_uid == owner and not (info.st_mode & 0o022), "evening_facts_reader_owner")
    info = path.lstat()
    _need(info.st_uid == owner and not (info.st_mode & 0o022), "evening_facts_file_owner")
    return _object(_read(path, limit))


def read_final_score(root, game_id, day, now, max_age):
    try:
        value = _read_owned(_score_path(root, game_id), PARTITION_LIMIT)
    except FileNotFoundError:
        return {}
    _need(isinstance(value, dict) and type(value.get("version")) is int
          and (value["version"], value.get("origin"), value.get("game_id"))
          == (1, "vps-live-worker-existing-stats-game", game_id)
          and value.get("status") in ("FINISHED", "unproven"), "evening_score_facts_identity")
    if value["status"] == "unproven":
        return {}
    observed = datetime.fromisoformat(value["observed_at"])
    fields = value["values"]
    if (observed.utcoffset() is None or not now - max_age <= observed <= now
            or fields.get("game_date") != day.isoformat()):
        return {}
    _need(set(fields) == {"game_date", "home_score", "away_score"}
          and all(type(fields[name]) is int and fields[name] >= 0 for name in ("home_score", "away_score")),
          "evening_score_facts_fields")
    return {key: fields[key] for key in ("home_score", "away_score")}


def read_partition(root: Path, kind, year, month, now, max_age):
    try:
        value = _read_owned(_path(root, kind, year, month), PARTITION_LIMIT)
    except FileNotFoundError:
        return {}
    _need(isinstance(value, dict) and set(value) == {
        "version", "origin", "kind", "year", "month", "observed_at", "games",
    } and type(value["version"]) is int and value["version"] == 1
        and (value["origin"], value["kind"], value["year"], value["month"]) == (ORIGIN, kind, year, month)
        and isinstance(value["games"], dict), "evening_facts_identity")
    observed = datetime.fromisoformat(value["observed_at"])
    if observed.utcoffset() is None or not now - max_age <= observed <= now:
        return {}
    return value["games"]
