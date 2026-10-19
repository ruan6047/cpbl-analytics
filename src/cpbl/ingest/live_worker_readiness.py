"""live worker 原位就緒證據（#332 P3）：同程序記憶體 M1/M2＋本機原子檔＋Redis 輪次憑據。

刻意設計（⛔ 不得推出「可以拿來控制 worker」）：
- 只觀察 ``LiveGameWorker.run_cycle`` 已做的事，不改抓取、選場、轉換、鎖、TTL 或 sleep；
  所有 hook 例外都在 worker 端吞掉，只會讓本輪結論變成 unknown（observer_fault）。
- M1＝本輪開始（任何 I/O 前就寫入記憶體）、M2＝本輪結論；先更新記憶體再持久化，
  兩處持久寫入都失敗時讀取端會看到「記憶體比持久紀錄新」而判 unknown，不讓舊成功遮蓋。
- Unix socket 只接受一行 ``{"nonce": <32 hex>}``，回最新摘要並回聲 nonce；無其他指令、
  不開 port、不開新程序。檔案 0600、目錄 0700、只認本程序 euid 擁有者。
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import socket
import stat
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from cpbl.readiness_checks import (
    classify_cycle,
    inspect_partition,
    inspect_raw_game,
    inspect_snapshot,
    reconcile_snapshot,
    source_availability,
    summarize_delivery,
)

log = logging.getLogger("cpbl.liveworker.readiness")

SCHEMA_VERSION = 1
SUMMARY_LIMIT = 65_536
MAX_PARTITIONS = 6
MAX_GAMES = 8
LATEST_FILE = "latest.json"
SOCKET_FILE = "worker.sock"
FRESH_GRACE_SECONDS = 60
CYCLE_TIMEOUT_SECONDS = 120
_NONCE = re.compile(r"[0-9a-f]{32}")
_REQUEST_LIMIT = 256


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def digest(summary: dict) -> str:
    return hashlib.sha256(canonical(summary)).hexdigest()


def redis_key(prefix: str, instance: str) -> str:
    return f"{prefix.rstrip(':')}:readiness:{instance}"


def secure_dir(path: Path, *, create: bool) -> bool:
    """證據目錄須為本 euid 擁有、非 symlink、0700；不符時拒用，不修改他人目錄。"""
    try:
        if create:
            path.mkdir(mode=0o700, parents=True, exist_ok=True)
        info = os.lstat(path)
    except OSError:
        return False
    return (stat.S_ISDIR(info.st_mode) and info.st_uid == os.geteuid()
            and stat.S_IMODE(info.st_mode) & 0o077 == 0)


class _Cycle:
    """單輪觀測暫存；只由 worker 執行緒寫入。"""

    def __init__(self) -> None:
        self.partitions: dict[tuple[str, int, int], dict] = {}
        self.candidates: list[str] | None = None
        self.selected: list[str] | None = None
        self.records: dict[str, dict] = {}
        self.availability: dict[str, dict] = {}
        self.raw_games: dict[str, Any] = {}
        self.faults: list[str] = []


class LiveWorkerReadiness:
    """worker 同程序觀測者；hook 名稱對應 ``LiveGameWorker._observe`` 呼叫點。"""

    def __init__(self, *, directory: Path, redis_client: Any, prefix: str,
                 cache: Any, max_games: int,
                 clock=lambda: datetime.now(UTC)) -> None:
        self.directory = Path(directory)
        self.redis = redis_client
        self.prefix = prefix
        self.cache = cache
        self.max_games = max_games
        self.clock = clock
        self.instance = uuid4().hex
        self.pid = os.getpid()
        self._lock = threading.Lock()
        self._attempt = 0
        self._m1: dict | None = None
        self._m2: dict | None = None
        self._persist: dict[str, str] = {"file": "pending", "redis": "pending"}
        self._cycle: _Cycle | None = None
        self._server: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._stopping = threading.Event()
        self._dir_ok = False

    # ── 生命週期 ────────────────────────────────────────────────
    def start(self) -> None:
        try:
            self._start()
        except Exception:  # noqa: BLE001 — 證據元件故障不得讓 worker 起不來
            log.exception("readiness evidence start failed; reader will see unknown")

    def _start(self) -> None:
        self._dir_ok = secure_dir(self.directory, create=True)
        if not self._dir_ok:
            log.error("readiness evidence directory unsafe; socket/file disabled")
            return
        path = self.directory / SOCKET_FILE
        try:
            info = os.lstat(path)
        except FileNotFoundError:
            pass
        else:
            # 只清本 euid 遺留的 socket；其他型態或擁有者一律不動（伺服器停用＝讀取端 unknown）。
            if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.geteuid():
                log.error("readiness socket path occupied; socket disabled")
                return
            path.unlink()
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            server.bind(str(path))
            os.chmod(path, 0o600)
            server.listen(4)
            server.settimeout(0.5)
        except OSError:
            server.close()
            log.exception("readiness socket bind failed")
            return
        self._server = server
        self._thread = threading.Thread(target=self._serve, name="cpbl-readiness", daemon=True)
        self._thread.start()

    def close(self) -> None:
        try:
            self._close()
        except Exception:  # noqa: BLE001 — 結束清理不得遮蔽 worker 原本的結束路徑
            log.exception("readiness evidence close failed")

    def _close(self) -> None:
        self._stopping.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
        if self._server is not None:
            self._server.close()
            try:
                (self.directory / SOCKET_FILE).unlink()
            except OSError:
                pass

    # ── 主迴圈 hook（在 worker 主執行緒呼叫）───────────────────
    def begin_attempt(self, now: datetime) -> None:
        with self._lock:
            self._attempt += 1
            self._m1 = {"attempt": self._attempt, "started_at": _iso(now)}
        self._cycle = _Cycle()

    def end_attempt(self, result: Any, delay: int, now: datetime) -> None:
        try:
            summary = self._summarize(result, delay, now)
        except Exception as exc:  # noqa: BLE001 — 觀測失敗只能退化為 unknown
            summary = self._fallback(now, delay, f"summarize:{type(exc).__name__}")
        with self._lock:
            self._m2 = summary
            self._persist = {"file": "pending", "redis": "pending"}
        self._cycle = None
        self._write_file(summary)
        self._write_redis(summary)

    # ── run_cycle 內 hook ──────────────────────────────────────
    def mark_fault(self, name: str) -> None:
        if self._cycle is not None:
            self._cycle.faults.append(name)

    def partition_requested(self, kind: str, year: int, month: int) -> None:
        cycle = self._require()
        cycle.partitions[(kind, year, month)] = {
            "kind": kind, "year": year, "month": month, "state": "unknown",
            "reason": "partition_payload_unobserved",
        }

    def partition_payload(self, kind: str, year: int, month: int, payload: Any) -> None:
        """StatsLiveSource 壓縮 ``Games or []`` 之前的原始 JSON。"""
        cycle = self._require()
        result = inspect_partition(payload, year=year, month=month, kind=kind)
        if result["state"] != "complete":
            result["reason"] = ("partition_games_not_list" if not result["explicit_list"]
                                else "partition_rows_invalid")
        cycle.partitions[(kind, year, month)] = result

    def partition_failed(self, kind: str, year: int, month: int, error_type: str) -> None:
        cycle = self._require()
        cycle.partitions[(kind, year, month)] = {
            "kind": kind, "year": year, "month": month, "state": "unknown",
            "reason": "partition_fetch_failed", "error_type": error_type,
        }

    def candidates_selected(self, candidates: list[str], selected: list[str]) -> None:
        cycle = self._require()
        cycle.candidates = list(candidates)
        cycle.selected = list(selected)

    def game_reused_final(self, game_id: str, previous: Any) -> None:
        reasons = inspect_snapshot(previous, expected_id=game_id, now=self.clock())["reasons"]
        self._record(game_id, "incomplete" if reasons else "reused_final", "final", reasons)

    def game_payload(self, game_id: str, raw: Any) -> None:
        self._require().raw_games[game_id] = raw

    def game_moved_out(self, game_id: str) -> None:
        self._record(game_id, "moved_out_of_window", None, [])

    def game_time_unknown(self, game_id: str) -> None:
        self._record(game_id, "incomplete", None, ["detail_time_unknown"])

    def game_written(self, game_id: str, snapshot: dict) -> None:
        cycle = self._require()
        try:
            actual = self.cache.get_snapshot(*_split(game_id))
        except Exception as exc:  # noqa: BLE001 — 讀回失敗＝本場交付未證實
            self._record(game_id, "failed", snapshot.get("phase"),
                         [f"readback_error:{type(exc).__name__}"])
            return
        if not reconcile_snapshot(snapshot, actual):
            self._record(game_id, "failed", snapshot.get("phase"), ["readback_mismatch"])
            return
        reasons = inspect_snapshot(actual, expected_id=game_id, now=self.clock())["reasons"]
        reasons += inspect_raw_game(cycle.raw_games.get(game_id), snapshot)
        cycle.availability[game_id] = source_availability(snapshot)
        self._record(game_id, "incomplete" if reasons else "write_readback",
                     snapshot.get("phase"), reasons)

    def game_failed(self, game_id: str, error_type: str) -> None:
        self._record(game_id, "failed", None, [f"source_error:{error_type}"])

    # ── 內部 ──────────────────────────────────────────────────
    def _require(self) -> _Cycle:
        if self._cycle is None:
            raise RuntimeError("hook outside attempt")
        return self._cycle

    def _record(self, game_id: str, disposition: str, phase: Any, reasons: list[str]) -> None:
        cycle = self._require()
        if game_id in cycle.records:
            cycle.faults.append("duplicate_game_record")
        cycle.records[game_id] = {"game_id": game_id, "disposition": disposition,
                                  "phase": phase, "reasons": sorted(set(reasons))}

    def _fallback(self, now: datetime, delay: int, fault: str) -> dict:
        m1 = self._m1 or {}
        return {"schema_version": SCHEMA_VERSION, "instance": self.instance,
                "attempt": m1.get("attempt"), "started_at": m1.get("started_at"),
                "finished_at": _iso(now), "sleep_seconds": delay,
                "valid_until": _iso(now + timedelta(seconds=delay + FRESH_GRACE_SECONDS)),
                "legacy_state": None, "result": "unknown",
                "reasons": [f"observer_fault:{fault}"], "partitions": [], "candidate_count": None,
                "selected": [], "overflow_count": None, "games": [], "delivery": None,
                "source_availability": {"state": "unknown", "games": []}}

    def _summarize(self, result: Any, delay: int, now: datetime) -> dict:
        cycle = self._cycle or _Cycle()
        legacy = result.get("state") if isinstance(result, dict) else None
        faults = list(cycle.faults)
        partitions = sorted(cycle.partitions.values(),
                            key=lambda item: (item["kind"], item["year"], item["month"]))
        delivery = None
        games: list[dict] = []
        selected = cycle.selected or []
        overflow = None
        if legacy == "ok":
            if cycle.selected is None:
                faults.append("selection_unobserved")
            else:
                overflow = len(cycle.candidates or []) - len(selected)
                games = [cycle.records[game_id] for game_id in selected
                         if game_id in cycle.records]
                delivery = summarize_delivery(selected, games, overflow_count=overflow)
            if len(partitions) > MAX_PARTITIONS:
                faults.append("partitions_over_bound")
            if len(selected) > MAX_GAMES:
                faults.append("games_over_bound")
        # 輸出界線：6 分區／8 場（超界已記為 fault＝unknown，不靜默截斷成功）。
        partitions = partitions[:MAX_PARTITIONS]
        selected = selected[:MAX_GAMES]
        games = games[:MAX_GAMES]
        state, reasons = classify_cycle(legacy_state=legacy, partitions=partitions,
                                        delivery=delivery, games=games, faults=faults)
        m1 = self._m1 or {}
        summary = {
            "schema_version": SCHEMA_VERSION,
            "instance": self.instance,
            "attempt": m1.get("attempt"),
            "started_at": m1.get("started_at"),
            "finished_at": _iso(now),
            "sleep_seconds": delay,
            "valid_until": _iso(now + timedelta(seconds=delay + FRESH_GRACE_SECONDS)),
            "legacy_state": legacy,
            "result": state,
            "reasons": reasons,
            "partitions": partitions,
            "candidate_count": None if cycle.candidates is None else len(cycle.candidates),
            "selected": selected,
            "overflow_count": overflow,
            "games": games,
            "delivery": delivery,
            "source_availability": {
                "state": ("partial" if any(item.get("state") != "complete"
                                           for item in cycle.availability.values())
                          else "complete") if cycle.availability else "none",
                "games": [{"game_id": game_id, **cycle.availability[game_id]}
                          for game_id in selected if game_id in cycle.availability],
            },
        }
        if len(canonical(summary)) > SUMMARY_LIMIT:
            return self._fallback(now, delay, "summary_over_limit")
        return summary

    def _set_persist(self, field: str, value: str) -> None:
        with self._lock:
            self._persist[field] = value

    def _write_file(self, summary: dict) -> None:
        if not self._dir_ok:
            self._set_persist("file", "unsafe_dir")
            return
        body = canonical({"summary": summary, "digest": digest(summary)})
        target = self.directory / LATEST_FILE
        temporary = self.directory / f".{LATEST_FILE}.{self.instance}.tmp"
        try:
            descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC
                                 | getattr(os, "O_NOFOLLOW", 0), 0o600)
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(body)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, target)
        except OSError as exc:
            self._set_persist("file", f"error:{type(exc).__name__}")
            try:
                temporary.unlink()
            except OSError:
                pass
            return
        self._set_persist("file", "ok")

    def _write_redis(self, summary: dict) -> None:
        credential = {"instance": summary["instance"], "attempt": summary["attempt"],
                      "digest": digest(summary), "result": summary["result"],
                      "finished_at": summary["finished_at"],
                      "valid_until": summary["valid_until"]}
        try:
            # 新鍵、獨立 TTL；不觸碰既有 snapshot／lock／health 鍵與其 TTL。
            self.redis.set(redis_key(self.prefix, self.instance),
                           canonical(credential).decode(),
                           ex=int(summary["sleep_seconds"]) + FRESH_GRACE_SECONDS
                           + CYCLE_TIMEOUT_SECONDS)
        except Exception as exc:  # noqa: BLE001 — Redis 失敗只影響證據，不影響 worker
            self._set_persist("redis", f"error:{type(exc).__name__}")
            return
        self._set_persist("redis", "ok")

    def snapshot_for(self, nonce: str) -> dict:
        with self._lock:
            return {"schema_version": SCHEMA_VERSION, "nonce": nonce,
                    "instance": self.instance, "pid": self.pid,
                    "m1": dict(self._m1) if self._m1 else None,
                    "m2": self._m2, "persist": dict(self._persist)}

    def _serve(self) -> None:
        assert self._server is not None
        while not self._stopping.is_set():
            try:
                connection, _ = self._server.accept()
            except TimeoutError:
                continue
            except OSError:
                if self._stopping.is_set():
                    return
                continue
            with connection:
                try:
                    connection.settimeout(1.0)
                    request = b""
                    while b"\n" not in request and len(request) <= _REQUEST_LIMIT:
                        chunk = connection.recv(_REQUEST_LIMIT + 1 - len(request))
                        if not chunk:
                            break
                        request += chunk
                    line = request.split(b"\n", 1)[0]
                    if len(line) > _REQUEST_LIMIT:
                        continue
                    nonce = json.loads(line).get("nonce")
                    if not isinstance(nonce, str) or not _NONCE.fullmatch(nonce):
                        continue
                    connection.sendall(canonical(self.snapshot_for(nonce)) + b"\n")
                except Exception:  # noqa: BLE001 — 單一連線失敗不影響 worker 或下一連線
                    continue


def _split(game_id: str) -> tuple[int, str, int]:
    year, kind, sno = game_id.split("-")
    return int(year), kind, int(sno)
