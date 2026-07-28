"""VPS 隔離 raw observer；只保存官方 stats 單場 payload，不接 production data plane。

此模組刻意不讀 Settings／DATABASE_URL，也不提供可調 host、path 或 game IDs。
允許面、request budget 與截止時間皆是 OPS-LIVE-SHADOW1 T4 已核可的固定契約。
"""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import gzip
import hashlib
import io
import json
import logging
import os
import random
import shutil
import signal
import threading
import time
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx

log = logging.getLogger("cpbl.live-shadow")

ALLOWED_SCHEME = "https"
ALLOWED_HOST = "stats.cpbl.com.tw"
SCHEDULE_PATH = "/api/proxy/v1/games/schedule"
GAME_PATH_PREFIX = "/api/proxy/v1/games/"
ALLOWED_GAME_IDS = ("2026-A-226", "2026-A-227", "2026-A-228")
STOP_AT = datetime(2026, 7, 30, 0, 0, tzinfo=timezone(timedelta(hours=8)))
USER_AGENT = "cpbl-analytics-isolated-shadow/1.0 (+https://cpbl.ruan-ruan.com)"


class BudgetExceeded(RuntimeError):
    """Request hard limit 已耗盡；呼叫端必須 fail closed。"""


class DiskGateClosed(RuntimeError):
    """Evidence volume 容量不足；禁止再發 request。"""


class CycleAttemptExceeded(RuntimeError):
    """單 cycle attempt 上限。"""


class HttpClient(Protocol):
    def get(self, url: str): ...


@dataclass(frozen=True)
class ObserverConfig:
    evidence_dir: Path = Path("/evidence")
    stop_at: datetime = STOP_AT
    min_free_bytes: int = 1024**3
    min_free_ratio: float = 0.10
    max_evidence_bytes: int = 4 * 1024**3
    max_initial_requests_per_cycle: int = 4
    max_attempts_per_cycle: int = 8
    max_attempts_per_game_per_minute: int = 5
    max_attempts_per_minute: int = 18
    max_total_attempts: int = 6000
    schedule_interval_seconds: float = 600
    idle_interval_seconds: float = 1800
    observation_interval_seconds: float = 600
    pregame_interval_seconds: float = 60
    live_interval_seconds: float = 12
    max_backoff_seconds: float = 900

    def __post_init__(self) -> None:
        if self.stop_at.tzinfo is None:
            raise ValueError("stop_at must be timezone-aware")
        object.__setattr__(self, "evidence_dir", Path(self.evidence_dir))

    @property
    def raw_dir(self) -> Path:
        return self.evidence_dir / "raw"

    @property
    def manifest_path(self) -> Path:
        return self.evidence_dir / "manifest.jsonl"

    @property
    def state_path(self) -> Path:
        return self.evidence_dir / "state.json"

    @property
    def stop_path(self) -> Path:
        return self.evidence_dir / "STOP"

    @property
    def writer_lock_path(self) -> Path:
        return self.evidence_dir / ".writer.lock"

    @property
    def process_lock_path(self) -> Path:
        return self.evidence_dir / ".observer.lock"


def build_schedule_url(config: ObserverConfig) -> str:
    query = urlencode((("kindCode", "A"), ("year", "2026"), ("month", "7")))
    return f"https://{ALLOWED_HOST}{SCHEDULE_PATH}?{query}"


def build_game_url(game_id: str, config: ObserverConfig) -> str:
    if game_id not in ALLOWED_GAME_IDS:
        raise ValueError(f"game ID not allowlisted: {game_id}")
    return f"https://{ALLOWED_HOST}{GAME_PATH_PREFIX}{game_id}"


def validate_target_url(url: str, config: ObserverConfig) -> str:
    """在 socket 建立前驗證 exact scheme／host／path／query。"""
    del config  # allowlist 是 versioned constant，不接受 runtime 放寬。
    parsed = urlsplit(url)
    if parsed.scheme != ALLOWED_SCHEME or parsed.hostname != ALLOWED_HOST:
        raise ValueError("URL scheme/host is not allowlisted")
    if parsed.port is not None or parsed.username is not None or parsed.password is not None:
        raise ValueError("URL authority must not contain port or credentials")
    if parsed.fragment:
        raise ValueError("URL fragment is not allowed")
    if parsed.path == SCHEDULE_PATH:
        expected = {"kindCode": ["A"], "year": ["2026"], "month": ["7"]}
        if parse_qs(parsed.query, keep_blank_values=True) != expected:
            raise ValueError("schedule query is not the fixed A/2026/7 scope")
        return "schedule"
    if parsed.query:
        raise ValueError("single-game endpoint must not contain query parameters")
    if not parsed.path.startswith(GAME_PATH_PREFIX):
        raise ValueError("URL path is not allowlisted")
    game_id = parsed.path.removeprefix(GAME_PATH_PREFIX)
    if "/" in game_id or game_id not in ALLOWED_GAME_IDS:
        raise ValueError("single-game ID is not allowlisted")
    return f"game:{game_id}"


@contextlib.contextmanager
def _file_lock(path: Path, *, nonblocking: bool = False) -> Iterator[object]:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+b")
    flags = fcntl.LOCK_EX | (fcntl.LOCK_NB if nonblocking else 0)
    try:
        fcntl.flock(handle.fileno(), flags)
        yield handle
    finally:
        with contextlib.suppress(OSError):
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


def _fsync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with tmp.open("wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
        _fsync_dir(path.parent)
    finally:
        with contextlib.suppress(FileNotFoundError):
            tmp.unlink()


def _load_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return dict(default)
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError(f"invalid state object: {path}")
    return loaded


def _save_state(config: ObserverConfig, state: dict[str, Any]) -> None:
    payload = json.dumps(state, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    _atomic_write(config.state_path, payload)


class PersistentBudget:
    """跨 container restart 保留 attempt total 與最近一分鐘窗口。"""

    def __init__(self, config: ObserverConfig):
        self.config = config
        config.evidence_dir.mkdir(parents=True, exist_ok=True)

    @property
    def total_attempts(self) -> int:
        with _file_lock(self.config.writer_lock_path):
            return int(_load_json(self.config.state_path, {}).get("attempts_total", 0))

    def consume(self, template_id: str, observed_at: datetime) -> int:
        if observed_at.tzinfo is None:
            raise ValueError("attempt timestamp must be timezone-aware")
        epoch = observed_at.timestamp()
        with _file_lock(self.config.writer_lock_path):
            state = _load_json(self.config.state_path, {})
            total = int(state.get("attempts_total", 0))
            if total >= self.config.max_total_attempts:
                raise BudgetExceeded("total request budget exhausted")
            recent = [
                item for item in state.get("recent_attempts", [])
                if float(item.get("at", 0)) > epoch - 60
            ]
            if len(recent) >= self.config.max_attempts_per_minute:
                raise BudgetExceeded("global-minute request budget exhausted")
            if template_id.startswith("game:"):
                per_game = sum(item.get("template_id") == template_id for item in recent)
                if per_game >= self.config.max_attempts_per_game_per_minute:
                    raise BudgetExceeded("per-game request budget exhausted")
            recent.append({"at": epoch, "template_id": template_id})
            total += 1
            state["attempts_total"] = total
            state["recent_attempts"] = recent
            _save_state(self.config, state)
            return total


class PersistentTerminalGames:
    """只依 single-game exact FINISHED 保存不再輪詢的 allowlisted game IDs。"""

    def __init__(self, config: ObserverConfig):
        self.config = config

    @staticmethod
    def _validated_ids(value: Any) -> frozenset[str]:
        if value is None:
            return frozenset()
        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
            raise ValueError("terminal_game_ids must be a list of strings")
        ids = frozenset(value)
        if any(game_id not in ALLOWED_GAME_IDS for game_id in ids):
            raise ValueError("terminal_game_ids contains a non-allowlisted game")
        if value != sorted(ids):
            raise ValueError("terminal_game_ids must be sorted and unique")
        return ids

    @property
    def ids(self) -> frozenset[str]:
        with _file_lock(self.config.writer_lock_path):
            state = _load_json(self.config.state_path, {})
            ids = self._validated_ids(state.get("terminal_game_ids"))
            if "terminal_game_ids" not in state:
                state["terminal_game_ids"] = []
                _save_state(self.config, state)
            return ids

    def mark(self, game_id: str) -> None:
        if game_id not in ALLOWED_GAME_IDS:
            raise ValueError("terminal game is not allowlisted")
        with _file_lock(self.config.writer_lock_path):
            state = _load_json(self.config.state_path, {})
            ids = set(self._validated_ids(state.get("terminal_game_ids")))
            ids.add(game_id)
            state["terminal_game_ids"] = sorted(ids)
            _save_state(self.config, state)


def _gzip(payload: bytes) -> bytes:
    buffer = io.BytesIO()
    with gzip.GzipFile(fileobj=buffer, mode="wb", mtime=0) as archive:
        archive.write(payload)
    return buffer.getvalue()


def _structural_paths(value: Any, path: str = "", out: dict[str, dict[str, Any]] | None = None):
    """記錄來源結構，不把任何 key 推論成產品語意。"""
    out = out if out is not None else {}
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else str(key)
            if isinstance(child, list):
                out[child_path] = {"present": True, "count": len(child)}
                if child:
                    _structural_paths(child[0], f"{child_path}[0]", out)
            elif isinstance(child, dict):
                out[child_path] = {"present": True, "count": len(child)}
                _structural_paths(child, child_path, out)
            else:
                out[child_path] = {"present": True, "count": None}
    return out


def _inspect_body(body: bytes) -> tuple[Any, dict[str, dict[str, Any]], list[str]]:
    try:
        payload = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None, {}, []
    paths = _structural_paths(payload)
    raw_status: Any = None
    source_times: list[str] = []
    if isinstance(payload, dict):
        data = payload.get("Data")
        if isinstance(data, dict):
            game = data.get("Game")
            if isinstance(game, dict):
                raw_status = game.get("GameStatus")
                if game.get("PreExeDate") is not None:
                    source_times.append(str(game["PreExeDate"]))
            games = data.get("Games")
            if raw_status is None and isinstance(games, list):
                raw_status = sorted({
                    str(item.get("GameStatus")) for item in games
                    if isinstance(item, dict)
                    and item.get("GameId") in ALLOWED_GAME_IDS
                    and item.get("GameStatus") is not None
                })
            if isinstance(games, list):
                source_times.extend(
                    str(item["PreExeDate"])
                    for item in games
                    if isinstance(item, dict)
                    and item.get("GameId") in ALLOWED_GAME_IDS
                    and item.get("PreExeDate") is not None
                )
    return raw_status, paths, sorted(set(source_times))


class EvidenceStore:
    def __init__(
        self,
        config: ObserverConfig,
        *,
        disk_usage: Callable[[Path], tuple[int, int, int]] = shutil.disk_usage,
    ):
        self.config = config
        self.disk_usage = disk_usage
        config.raw_dir.mkdir(parents=True, exist_ok=True)

    def _used_bytes(self) -> int:
        return sum(path.stat().st_size for path in self.config.raw_dir.glob("*.json.gz"))

    def ensure_capacity(self, incoming_bytes: int) -> None:
        total, _used, free = self.disk_usage(self.config.evidence_dir)
        ratio = free / total if total else 0
        if free < self.config.min_free_bytes or ratio < self.config.min_free_ratio:
            raise DiskGateClosed("free-space gate closed")
        if self._used_bytes() + incoming_bytes > self.config.max_evidence_bytes:
            raise DiskGateClosed("evidence-ceiling gate closed")

    def _reserve_sequence(self) -> int:
        state = _load_json(self.config.state_path, {})
        sequence = int(state.get("next_sequence", 1))
        state["next_sequence"] = sequence + 1
        _save_state(self.config, state)
        return sequence

    def _append_manifest(self, entry: dict[str, Any]) -> None:
        line = json.dumps(entry, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        with self.config.manifest_path.open("ab") as handle:
            handle.write(line.encode())
            handle.flush()
            os.fsync(handle.fileno())

    def write_response(
        self,
        template_id: str,
        game_id: str | None,
        status_code: int,
        latency_ms: int,
        body: bytes,
        observed_at: datetime,
        monotonic_elapsed: float,
        *,
        run_id: str = "test-run",
        after_rename: Callable[[], None] | None = None,
    ) -> dict[str, Any]:
        raw_sha = hashlib.sha256(body).hexdigest()
        raw_status, key_paths, source_times = _inspect_body(body)
        with _file_lock(self.config.writer_lock_path):
            sequence = self._reserve_sequence()
            filename = f"{sequence:012d}-{raw_sha[:16]}.json.gz"
            relative_path = f"raw/{filename}"
            entry: dict[str, Any] = {
                "schema_version": 1,
                "run_id": run_id,
                "sequence": sequence,
                "observed_at_utc": observed_at.astimezone(UTC).isoformat(),
                "observed_at_asia_taipei": observed_at.astimezone(
                    timezone(timedelta(hours=8))
                ).isoformat(),
                "monotonic_elapsed": monotonic_elapsed,
                "template_id": template_id,
                "game_id": game_id,
                "status_code": status_code,
                "latency_ms": latency_ms,
                "raw_status": raw_status,
                "source_schedule_times": source_times,
                "key_paths": key_paths,
                "raw_sha256": raw_sha,
                "gzip_path": relative_path,
            }
            envelope = {
                "schema_version": 1,
                "manifest_entry": entry,
                "raw_body_hex": body.hex(),
            }
            compressed = b""
            for _ in range(4):
                envelope["manifest_entry"] = entry
                compressed = _gzip(
                    json.dumps(envelope, ensure_ascii=False, separators=(",", ":")).encode()
                )
                if entry.get("gzip_size") == len(compressed):
                    break
                entry["gzip_size"] = len(compressed)
            self.ensure_capacity(len(compressed))
            target = self.config.evidence_dir / relative_path
            _atomic_write(target, compressed)
            if after_rename:
                after_rename()
            self._append_manifest(entry)
            return entry

    def write_error(
        self,
        template_id: str,
        error: Exception,
        observed_at: datetime,
        monotonic_elapsed: float,
        *,
        run_id: str,
    ) -> dict[str, Any]:
        """無 HTTP response 的 network error 仍須留下 attempt 證據。"""
        with _file_lock(self.config.writer_lock_path):
            sequence = self._reserve_sequence()
            entry = {
                "schema_version": 1,
                "event_type": "network_error",
                "run_id": run_id,
                "sequence": sequence,
                "observed_at_utc": observed_at.astimezone(UTC).isoformat(),
                "observed_at_asia_taipei": observed_at.astimezone(
                    timezone(timedelta(hours=8))
                ).isoformat(),
                "monotonic_elapsed": monotonic_elapsed,
                "template_id": template_id,
                "error_type": type(error).__name__,
            }
            self._append_manifest(entry)
            return entry

    def _manifest_sequences(self) -> tuple[set[int], int]:
        if not self.config.manifest_path.exists():
            return set(), 0
        sequences: list[int] = []
        for line in self.config.manifest_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                sequences.append(int(json.loads(line)["sequence"]))
        if sequences != sorted(sequences) or len(sequences) != len(set(sequences)):
            raise ValueError("manifest sequence is not strictly monotonic")
        return set(sequences), sequences[-1] if sequences else 0

    def recover_orphans(self) -> int:
        recovered = 0
        with _file_lock(self.config.writer_lock_path):
            known, last_sequence = self._manifest_sequences()
            for path in sorted(self.config.raw_dir.glob("*.json.gz")):
                try:
                    envelope = json.loads(gzip.decompress(path.read_bytes()))
                    entry = dict(envelope["manifest_entry"])
                    raw = bytes.fromhex(envelope["raw_body_hex"])
                    if hashlib.sha256(raw).hexdigest() != entry["raw_sha256"]:
                        raise ValueError("raw checksum mismatch")
                    sequence = int(entry["sequence"])
                except Exception as exc:
                    raise ValueError(f"corrupt orphan evidence: {path.name}") from exc
                if sequence in known:
                    continue
                if sequence <= last_sequence:
                    raise ValueError("orphan sequence would regress manifest")
                entry["recovered_after_crash"] = True
                self._append_manifest(entry)
                known.add(sequence)
                last_sequence = sequence
                recovered += 1
        return recovered

    def write_termination(self, reason: str, observed_at: datetime) -> None:
        marker = self.config.evidence_dir / f"termination-{reason}.json"
        if marker.exists():
            return
        payload = json.dumps({
            "reason": reason,
            "observed_at_utc": observed_at.astimezone(UTC).isoformat(),
        }, sort_keys=True).encode()
        with contextlib.suppress(OSError):
            _atomic_write(marker, payload)

    def build_export_manifest(self) -> dict[str, Any]:
        files = []
        for path in sorted(self.config.raw_dir.glob("*.json.gz")):
            try:
                envelope = json.loads(gzip.decompress(path.read_bytes()))
                raw = bytes.fromhex(envelope["raw_body_hex"])
                if hashlib.sha256(raw).hexdigest() != envelope["manifest_entry"]["raw_sha256"]:
                    raise ValueError("raw checksum mismatch")
            except Exception as exc:
                raise ValueError(f"cannot export corrupt evidence: {path.name}") from exc
            files.append({
                "path": str(path.relative_to(self.config.evidence_dir)),
                "size": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            })
        manifest_bytes = self.config.manifest_path.read_bytes() if self.config.manifest_path.exists() else b""
        combined = hashlib.sha256()
        combined.update(hashlib.sha256(manifest_bytes).digest())
        for item in files:
            combined.update(bytes.fromhex(item["sha256"]))
        export = {
            "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
            "manifest_entries": len(manifest_bytes.splitlines()),
            "files": files,
            "total_checksum": combined.hexdigest(),
        }
        _atomic_write(
            self.config.evidence_dir / "export-manifest.json",
            json.dumps(export, sort_keys=True, indent=2).encode(),
        )
        return export


def _retry_after_seconds(headers: Any, observed_at: datetime) -> int:
    value = headers.get("retry-after") if headers is not None else None
    if not value:
        return 60
    try:
        return max(60, int(value))
    except ValueError:
        try:
            parsed = datetime.strptime(value, "%a, %d %b %Y %H:%M:%S GMT").replace(tzinfo=UTC)
            return max(60, int((parsed - observed_at.astimezone(UTC)).total_seconds()))
        except ValueError:
            return 60


def _parse_source_time(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone(timedelta(hours=8)))
    return parsed


def _choose_interval(
    results: list[dict[str, Any]], observed_at: datetime, config: ObserverConfig
) -> float:
    statuses: set[str] = set()
    source_times: list[datetime] = []
    for result in results:
        raw_status = result.get("raw_status")
        if isinstance(raw_status, str):
            statuses.add(raw_status)
        elif isinstance(raw_status, list):
            statuses.update(str(item) for item in raw_status)
        for value in result.get("source_schedule_times") or []:
            parsed = _parse_source_time(str(value))
            if parsed is not None:
                source_times.append(parsed)
    if "START" in statuses:
        return config.live_interval_seconds
    future_deltas = [
        (source_time.astimezone(UTC) - observed_at.astimezone(UTC)).total_seconds()
        for source_time in source_times
        if source_time.astimezone(UTC) >= observed_at.astimezone(UTC)
    ]
    if future_deltas:
        nearest = min(future_deltas)
        if nearest <= 90 * 60:
            return config.pregame_interval_seconds
        if nearest <= 30 * 60 * 60:
            return config.observation_interval_seconds
        return config.idle_interval_seconds
    return config.observation_interval_seconds


def bounded_sleep_seconds(observed_at: datetime, desired: float, stop_at: datetime) -> float:
    """睡眠不得跨過硬截止時間，避免 idle interval 延後 clean exit。"""
    remaining = (stop_at.astimezone(UTC) - observed_at.astimezone(UTC)).total_seconds()
    return max(0.0, min(desired, remaining))


class Observer:
    def __init__(
        self,
        config: ObserverConfig,
        *,
        client: HttpClient | None = None,
        sleep: Callable[[float], None] = time.sleep,
        jitter: Callable[[float, float], float] = random.uniform,
        shutdown_requested: Callable[[], bool] = lambda: False,
    ):
        self.config = config
        self.client = client or httpx.Client(
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            timeout=httpx.Timeout(connect=5, read=15, write=15, pool=5),
            follow_redirects=False,
        )
        self.sleep = sleep
        self.jitter = jitter
        self.shutdown_requested = shutdown_requested
        self.store = EvidenceStore(config)
        self.budget = PersistentBudget(config)
        self.terminal_games = PersistentTerminalGames(config)
        self.run_id = uuid.uuid4().hex
        self.started_monotonic = time.monotonic()
        self._cycle_attempts = 0
        self._last_schedule_epoch = 0.0
        self._next_interval = config.observation_interval_seconds
        self._retry_not_before_epoch = 0.0
        self._consecutive_failure_cycles = 0

    @property
    def next_interval_seconds(self) -> float:
        return self._next_interval

    def _stop_reason(self, observed_at: datetime) -> str | None:
        if self.shutdown_requested():
            return "signal"
        if observed_at.astimezone(UTC) >= self.config.stop_at.astimezone(UTC):
            return "deadline"
        if self.config.stop_path.exists():
            return "kill-switch"
        if self.budget.total_attempts >= self.config.max_total_attempts:
            return "budget"
        try:
            self.store.ensure_capacity(0)
        except DiskGateClosed:
            return "disk-gate"
        return None

    def _attempt(self, url: str, template_id: str, now: Callable[[], datetime]):
        if self._cycle_attempts >= self.config.max_attempts_per_cycle:
            raise CycleAttemptExceeded("cycle attempt budget exhausted")
        observed_at = now()
        reason = self._stop_reason(observed_at)
        if reason:
            raise BudgetExceeded(reason)
        self.budget.consume(template_id, observed_at)
        self._cycle_attempts += 1
        started = time.monotonic()
        try:
            response = self.client.get(url)
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            self.store.write_error(
                template_id,
                exc,
                observed_at,
                time.monotonic() - self.started_monotonic,
                run_id=self.run_id,
            )
            return None, exc, observed_at
        latency_ms = max(0, round((time.monotonic() - started) * 1000))
        game_id = template_id.removeprefix("game:") if template_id.startswith("game:") else None
        entry = self.store.write_response(
            template_id=template_id,
            game_id=game_id,
            status_code=int(response.status_code),
            latency_ms=latency_ms,
            body=bytes(response.content),
            observed_at=observed_at,
            monotonic_elapsed=time.monotonic() - self.started_monotonic,
            run_id=self.run_id,
        )
        return (response, entry), None, observed_at

    def observe(self, url: str, *, now: Callable[[], datetime] = lambda: datetime.now(UTC)):
        template_id = validate_target_url(url, self.config)
        if self._cycle_attempts >= self.config.max_attempts_per_cycle:
            raise CycleAttemptExceeded("cycle attempt budget exhausted")
        last_error: Exception | None = None
        for retry in range(2):
            try:
                observed, error, observed_at = self._attempt(url, template_id, now)
            except (BudgetExceeded, CycleAttemptExceeded):
                if last_error is not None:
                    return {"status_code": None, "error": type(last_error).__name__}
                raise
            if error is not None:
                last_error = error
                if retry == 0:
                    self.sleep(self.jitter(30, 120))
                    continue
                return {"status_code": None, "error": type(error).__name__}
            response, entry = observed
            status = int(response.status_code)
            result = dict(entry)
            result["retry_after_seconds"] = None
            if status == 429:
                result["retry_after_seconds"] = _retry_after_seconds(response.headers, observed_at)
                self._retry_not_before_epoch = max(
                    self._retry_not_before_epoch,
                    min(
                        self.config.stop_at.timestamp(),
                        observed_at.timestamp() + result["retry_after_seconds"],
                    ),
                )
                return result
            if 500 <= status <= 599 and retry == 0:
                self.sleep(self.jitter(30, 120))
                continue
            return result
        raise AssertionError("unreachable")

    def run_cycle(self, *, now: Callable[[], datetime] = lambda: datetime.now(UTC)) -> str:
        observed_at = now()
        reason = self._stop_reason(observed_at)
        if reason:
            self.store.write_termination(reason, observed_at)
            return reason
        self._cycle_attempts = 0
        if observed_at.timestamp() < self._retry_not_before_epoch:
            return "ok"
        terminal_game_ids = self.terminal_games.ids
        urls = [
            build_game_url(game_id, self.config)
            for game_id in ALLOWED_GAME_IDS
            if game_id not in terminal_game_ids
        ]
        if observed_at.timestamp() - self._last_schedule_epoch >= self.config.schedule_interval_seconds:
            urls.insert(0, build_schedule_url(self.config))
            self._last_schedule_epoch = observed_at.timestamp()
        results: list[dict[str, Any]] = []
        cycle_failed = False
        for url in urls[:self.config.max_initial_requests_per_cycle]:
            try:
                result = self.observe(url, now=now)
                results.append(result)
                status = result.get("status_code")
                template_id = result.get("template_id")
                if (
                    status == 200
                    and result.get("raw_status") == "FINISHED"
                    and isinstance(template_id, str)
                    and template_id.startswith("game:")
                ):
                    self.terminal_games.mark(template_id.removeprefix("game:"))
                cycle_failed = cycle_failed or status is None or status == 429 or status >= 500
            except (BudgetExceeded, CycleAttemptExceeded, DiskGateClosed) as exc:
                reason = str(exc)
                self.store.write_termination(reason, now())
                return reason
        self._next_interval = _choose_interval(results, observed_at, self.config)
        if cycle_failed:
            self._consecutive_failure_cycles += 1
            failure_backoff = min(
                self.config.max_backoff_seconds,
                30 * (2 ** (self._consecutive_failure_cycles - 1)),
            )
            self._next_interval = max(self._next_interval, failure_backoff)
        else:
            self._consecutive_failure_cycles = 0
        return "ok"

    def run_forever(self) -> str:
        try:
            process_lock = _file_lock(self.config.process_lock_path, nonblocking=True)
            with process_lock:
                self.store.recover_orphans()
                while True:
                    result = self.run_cycle()
                    if result != "ok":
                        self.store.build_export_manifest()
                        return result
                    now_epoch = datetime.now(UTC).timestamp()
                    retry_wait = max(0, self._retry_not_before_epoch - now_epoch)
                    interval = max(self._next_interval, retry_wait)
                    interval += self.jitter(0, min(5, interval * 0.05))
                    interval = bounded_sleep_seconds(datetime.now(UTC), interval, self.config.stop_at)
                    self.sleep(interval)
        except BlockingIOError:
            log.error("另一個 observer instance 已持有 process lock")
            return "lock-held"


def main() -> None:
    parser = argparse.ArgumentParser(description="isolated CPBL live raw observer")
    parser.add_argument("--evidence-dir", type=Path, default=Path("/evidence"))
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--export", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    config = ObserverConfig(evidence_dir=args.evidence_dir)
    shutdown = threading.Event()

    def request_shutdown(_signum: int, _frame: Any) -> None:
        shutdown.set()

    signal.signal(signal.SIGTERM, request_shutdown)
    signal.signal(signal.SIGINT, request_shutdown)
    observer = Observer(
        config,
        sleep=shutdown.wait,
        shutdown_requested=shutdown.is_set,
    )
    if args.export:
        print(json.dumps(observer.store.build_export_manifest(), indent=2, sort_keys=True))
        return
    result = observer.run_cycle() if args.once else observer.run_forever()
    log.info("observer stopped: %s", result)


if __name__ == "__main__":
    main()
