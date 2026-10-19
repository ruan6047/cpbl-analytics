"""內部同容器就緒探針；stdout 僅安全 JSON，公開 API 不使用本入口。"""
from __future__ import annotations

import argparse
import json
import os
import secrets
import socket
import stat
import subprocess
import sys
import time
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from cpbl.readiness_checks import instant

_EXIT_CODES = {"ready": 0, "not_ready": 1, "unknown": 2}
# 預留 interpreter／輸出與父程序處理餘裕；子程序只做本次探針，不是 worker。
_CHILD_TIMEOUT = 9.0
_STDOUT_LIMIT = 131_072
_DB_POOL_TIMEOUT = 3.0
_GAMES_QUERY = (
    "SELECT year, kind_code, game_season_code, game_sno, game_date, home_team_code, "
    "away_team_code, home_score, away_score FROM cpbl.games LIMIT 0"
)


def report(target: str, result: str, reasons: list[str], **fields: Any) -> dict:
    return {"schema_version": 1, "target": target, "ready": result == "ready",
            "checked_at": datetime.now(UTC).isoformat(), "result": result,
            "reasons": sorted(set(reasons)), **fields}


def _expected_database(dsn: str) -> tuple[str, str] | None:
    from psycopg.conninfo import conninfo_to_dict

    try:
        values = conninfo_to_dict(dsn)
    except Exception:  # noqa: BLE001 — 不把含憑證的 parser 錯誤外傳
        return None
    if values.get("service") or not values.get("user") or not values.get("dbname"):
        return None
    return values["user"], values["dbname"]


def _timeout(exc: Exception) -> bool:
    # psycopg pool/query 和 redis-py 的 timeout 不全部繼承 builtin TimeoutError。
    return isinstance(exc, TimeoutError) or type(exc).__name__ in {
        "PoolTimeout", "QueryCanceled", "TimeoutError",
    }


def _redis_client(url: str):
    import redis

    client = redis.Redis.from_url(url, decode_responses=False,
                                  socket_connect_timeout=1, socket_timeout=1)
    # 避免 PING 的通用 bool decoder 把任意 truthy 替身誤當協定 PONG。
    client.set_response_callback("PING", lambda response: response)
    return client


@contextmanager
def _db_connection():
    # 有界取得連線：池等待逾時歸 db_timeout（unknown），Redis 結果仍可回報。
    from cpbl.db import pool

    with pool().connection(timeout=_DB_POOL_TIMEOUT) as connection:
        yield connection


def check_api(config, *, connect=None, redis_factory=None) -> dict:
    """實際身份與代表結構查詢；由有總期限的 child 呼叫。"""
    fields = getattr(config, "model_fields_set", set())
    database = {"state": "unknown", "identity_match": None, "games_shape": None}
    redis_state = {"state": "unknown", "pong": None}
    reasons = []
    if "database_url" not in fields or not config.database_url:
        reasons.append("db_config_missing")
    else:
        expected = _expected_database(config.database_url)
        if expected is None:
            reasons.append("db_identity_unknown")
        else:
            try:
                if connect is None:
                    connect = _db_connection
                with connect() as connection:
                    connection.execute("SET LOCAL statement_timeout = '1500ms'")
                    actual = connection.execute("SELECT current_user, current_database()").fetchone()
                    database["identity_match"] = actual is not None and tuple(actual) == expected
                    if database["identity_match"]:
                        connection.execute(_GAMES_QUERY)
                        database.update(state="ok", games_shape=True)
                    else:
                        database["state"] = "error"
                        reasons.append("db_identity_mismatch")
            except Exception as exc:  # noqa: BLE001 — 依賴邊界，只回安全分類
                database["state"] = "unknown" if _timeout(exc) else "error"
                reasons.append("db_timeout" if _timeout(exc) else "db_query_failed")
    if "redis_url" not in fields or not config.redis_url:
        reasons.append("redis_config_missing")
    else:
        client = None
        try:
            client = (redis_factory or _redis_client)(config.redis_url)
            pong = client.execute_command("PING")
            redis_state["pong"] = (type(pong) is bytes and pong == b"PONG") or (
                type(pong) is str and pong == "PONG")
            redis_state["state"] = "ok" if redis_state["pong"] else "error"
            if not redis_state["pong"]:
                reasons.append("redis_invalid_pong")
        except Exception as exc:  # noqa: BLE001 — 不外傳連線網址或錯誤本文
            redis_state["state"] = "unknown" if _timeout(exc) else "error"
            reasons.append("redis_timeout" if _timeout(exc) else "redis_connection_failed")
        finally:
            if client is not None:
                try:
                    client.close()
                except Exception:  # noqa: BLE001 — 清理失敗不冒充 ready
                    redis_state["state"] = "error"
                    reasons.append("redis_close_failed")
    states = {database["state"], redis_state["state"]}
    result = "not_ready" if "error" in states else "unknown" if "unknown" in states else "ready"
    return report("api", result, reasons, dependencies={"database": database, "redis": redis_state})


_REPLY_LIMIT = 131_072
_SOCKET_TIMEOUT = 1.5
_REREAD_DELAY = 2.0


def _owned(path: Path, kind) -> os.stat_result | None:
    """只信本 euid 擁有、0600、型態正確的證據；不跟隨 symlink。"""
    try:
        info = os.lstat(path)
    except OSError:
        return None
    if not kind(info.st_mode) or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o600:
        return None
    return info


def _ask_socket(path: Path, nonce: str) -> bytes:
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.settimeout(_SOCKET_TIMEOUT)
    deadline = time.monotonic() + _SOCKET_TIMEOUT
    try:
        client.connect(str(path))
        client.sendall(json.dumps({"nonce": nonce}).encode() + b"\n")
        reply = b""
        while not reply.endswith(b"\n"):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError
            client.settimeout(remaining)
            chunk = client.recv(65_536)
            if not chunk:
                break
            reply += chunk
            if len(reply) > _REPLY_LIMIT:
                raise ValueError("reply_over_limit")
        return reply
    finally:
        client.close()


def _match(record: Any, summary: dict, expected_digest: str) -> str:
    if not isinstance(record, dict):
        return "invalid"
    attempt = record.get("attempt")
    if record.get("instance") != summary["instance"] or type(attempt) is not int:
        return "older"
    if attempt > summary["attempt"]:
        return "newer"
    if attempt < summary["attempt"]:
        return "older"
    return "match" if record.get("digest") == expected_digest else "invalid"


def _read_file(directory: Path, summary: dict, expected_digest: str, digest) -> str:
    from cpbl.ingest.live_worker_readiness import LATEST_FILE, SUMMARY_LIMIT

    path = directory / LATEST_FILE
    info = _owned(path, stat.S_ISREG)
    if info is None:
        return "missing"
    if info.st_size > SUMMARY_LIMIT + 1024:
        return "invalid"
    try:
        stored = json.loads(path.read_bytes())
        persisted = stored["summary"]
        if digest(persisted) != stored["digest"]:
            return "invalid"
    except (OSError, ValueError, KeyError, TypeError):
        return "invalid"
    return _match({**persisted, "digest": stored["digest"]}, summary, expected_digest)


def _read_redis(client, prefix: str, summary: dict, expected_digest: str) -> str:
    from cpbl.ingest.live_worker_readiness import redis_key

    try:
        raw = client.get(redis_key(prefix, summary["instance"]))
    except Exception:  # noqa: BLE001 — Redis 讀取失敗不外傳錯誤本文
        return "error"
    if raw is None:
        return "missing"
    try:
        return _match(json.loads(raw), summary, expected_digest)
    except (ValueError, TypeError):
        return "invalid"


def _worker_view(directory: Path, client, prefix: str, ask) -> dict:
    """一次讀取：socket（新 nonce）→ 本機檔 → Redis；回 view 或不一致原因。"""
    from cpbl.ingest.live_worker_readiness import SOCKET_FILE, digest

    path = directory / SOCKET_FILE
    if _owned(path, stat.S_ISSOCK) is None:
        return {"reason": "worker_socket_unavailable"}
    nonce = secrets.token_hex(16)
    try:
        reply = json.loads(ask(path, nonce))
    except Exception:  # noqa: BLE001 — 失聯、逾時或壞回覆皆不能推定存活
        return {"reason": "worker_unreachable"}
    if not isinstance(reply, dict) or reply.get("nonce") != nonce:
        return {"reason": "worker_nonce_mismatch"}
    m1, m2 = reply.get("m1"), reply.get("m2")
    if reply.get("schema_version") != 1 or not isinstance(reply.get("instance"), str):
        return {"reason": "worker_reply_invalid"}
    if not isinstance(m2, dict):
        return {"reason": "no_completed_attempt", "final": True}
    if (m2.get("schema_version") != 1 or m2.get("instance") != reply["instance"]
            or type(m2.get("attempt")) is not int or not isinstance(m1, dict)
            or type(m1.get("attempt")) is not int or m1["attempt"] < m2["attempt"]
            or m1["attempt"] > m2["attempt"] + 1):
        return {"reason": "worker_reply_invalid", "final": True}
    expected = digest(m2)
    evidence = {"file": _read_file(directory, m2, expected, digest),
                "redis": _read_redis(client, prefix, m2, expected)}
    if "newer" in evidence.values():
        return {"reason": "evidence_cross_round", "evidence": evidence}
    if "match" not in evidence.values():
        return {"reason": "evidence_persist_stale", "evidence": evidence}
    return {"reply": reply, "evidence": evidence}


def check_worker(config, *, ask=None, redis_factory=None, clock=None, sleep=None) -> dict:
    """worker 原位證據：存活＋新 nonce、最新 attempt 優先、持久證據至少一處與記憶體一致。"""
    if not getattr(config, "live_game_worker_enabled", False):
        return report("worker", "not_ready", ["worker_disabled"])
    if not getattr(config, "redis_url", None):
        return report("worker", "unknown", ["redis_config_missing"])
    from cpbl.ingest.live_worker_readiness import (
        CYCLE_TIMEOUT_SECONDS,
        FRESH_GRACE_SECONDS,
        secure_dir,
    )

    directory = Path(config.live_worker_readiness_dir)
    if not secure_dir(directory, create=False):
        return report("worker", "unknown", ["evidence_dir_unavailable"])
    clock = clock or (lambda: datetime.now(UTC))
    client = None
    try:
        client = (redis_factory or _redis_client)(config.redis_url)
        view = _worker_view(directory, client, config.live_game_cache_prefix, ask or _ask_socket)
        if "reply" not in view and not view.get("final") and view["reason"].startswith("evidence_"):
            # 跨輪讀回不一致只在 2s 後重讀一次；仍不一致＝unknown，不接受舊成功窗口。
            (sleep or time.sleep)(_REREAD_DELAY)
            view = _worker_view(directory, client, config.live_game_cache_prefix,
                                ask or _ask_socket)
    finally:
        if client is not None:
            try:
                client.close()
            except Exception:  # noqa: BLE001
                pass
    if "reply" not in view:
        return report("worker", "unknown", [view["reason"]],
                      worker={"evidence": view.get("evidence")})
    reply = view["reply"]
    m1, m2 = reply["m1"], reply["m2"]
    now = clock()
    reasons = list(m2.get("reasons") or [])
    result = m2.get("result")
    finished = instant(m2.get("finished_at"))
    valid_until = instant(m2.get("valid_until"))
    sleep_seconds = m2.get("sleep_seconds")
    in_progress = m1["attempt"] == m2["attempt"] + 1
    started = instant(m1.get("started_at"))
    if (result not in _EXIT_CODES or finished is None or valid_until is None
            or type(sleep_seconds) is not int or sleep_seconds < 0
            or valid_until != finished + timedelta(seconds=sleep_seconds + FRESH_GRACE_SECONDS)
            or finished > now or (in_progress and (started is None or started > now))):
        result, reasons = "unknown", ["worker_summary_invalid"]
    elif in_progress and now - started > timedelta(seconds=CYCLE_TIMEOUT_SECONDS):
        result, reasons = "unknown", ["cycle_timeout"]
    elif now > valid_until:
        result, reasons = "unknown", ["evidence_stale"]
    summary = {key: m2.get(key) for key in (
        "attempt", "started_at", "finished_at", "sleep_seconds", "valid_until", "legacy_state",
        "partitions", "candidate_count", "selected", "overflow_count", "games", "delivery",
        "source_availability")}
    return report("worker", result, reasons, worker={
        "instance": reply["instance"], "in_progress": in_progress,
        "current_attempt_started_at": m1.get("started_at") if in_progress else None,
        "evidence": view["evidence"], "persist": reply.get("persist"), **summary})


def _child(target: str) -> None:
    try:
        if target == "api":
            from cpbl.config import settings
            value = check_api(settings)
        else:
            from cpbl.config import settings
            value = check_worker(settings)
        code = _EXIT_CODES[value["result"]]
    except Exception:  # noqa: BLE001 — 設定載入亦可能包含敏感錯誤本文
        value = report(target, "unknown", ["probe_failed"])
        code = 3
    print(json.dumps(value, ensure_ascii=False, separators=(",", ":")))
    raise SystemExit(code)


def _run(target: str) -> tuple[dict, int]:
    try:
        completed = subprocess.run(
            [sys.executable, "-c", f"from cpbl.readiness import _child; _child({target!r})"],
            capture_output=True, text=True, timeout=_CHILD_TIMEOUT, check=False,
        )
    except subprocess.TimeoutExpired:
        # subprocess.run 已 kill/wait 本次 child；不接觸現役 worker。
        return report(target, "unknown", ["probe_timeout"]), 2
    if len(completed.stdout.encode()) > _STDOUT_LIMIT:
        raise ValueError("probe_output_limit")
    return json.loads(completed.stdout), completed.returncode


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError("invalid_arguments")


def main(argv: list[str] | None = None, *, runner=None) -> int:
    target = "unknown"
    try:
        parser = _Parser(description="Internal CPBL readiness probe", add_help=False)
        parser.add_argument("--target", required=True, choices=("api", "worker"))
        args = parser.parse_args(argv)
        target = args.target
        value, code = (runner or _run)(target)
        if (not isinstance(value, dict) or value.get("schema_version") != 1
                or value.get("target") != target
                or instant(value.get("checked_at")) is None
                or not isinstance(value.get("reasons"), list)
                or any(not isinstance(reason, str) for reason in value.get("reasons", []))
                or value.get("result") not in _EXIT_CODES
                or value.get("ready") is not (value["result"] == "ready")
                or code != _EXIT_CODES[value["result"]] and not (
                    code == 3 and value["result"] == "unknown")):
            raise ValueError("invalid_result")
    except Exception:  # noqa: BLE001 — CLI 邊界保證錯誤也只有去敏 JSON
        value, code = report(target, "unknown", ["probe_failed"]), 3
    print(json.dumps(value, ensure_ascii=False, separators=(",", ":")))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
