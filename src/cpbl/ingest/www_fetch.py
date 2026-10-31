"""WP3: manifest operations through the mature session, private text bundles for WP4.

Only the standard library is imported here. Playwright is loaded by the unchanged
_browser session when a real fetch starts. No database, parser or publication code.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib.util
import json
import logging
import math
import os
import re
import signal
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

VERSION = "393-wp3-original.1"
MANIFEST_SCHEMA = "cpbl-www-manifest/1"
BUNDLE_SCHEMA = "cpbl-www-bundle/1"
MAX_BODY_BYTES = 8 * 1024 * 1024
MAX_TOTAL_BYTES = 256 * 1024 * 1024
MAX_INDEX_BYTES = 1024 * 1024
TZ = dt.timezone(dt.timedelta(hours=8))
TOKEN_RES = {
    "A": re.compile(r"RequestVerificationToken:\s*'([^']+)'"),
    "B": re.compile(r'name="__RequestVerificationToken"[^>]*value="([^"]+)"'),
}
SECRET_HEADERS = {"cookie", "set-cookie", "authorization", "proxy-authorization"}
TOKEN_KEYS = {"requestverificationtoken", "__requestverificationtoken"}
ID_RE = re.compile(r"[A-Za-z0-9_-]{1,64}")


class ManifestError(ValueError):
    pass


class BundleError(ValueError):
    pass


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _json(raw):
    def pairs(items):
        obj = {}
        for key, value in items:
            if key in obj:
                raise ValueError("duplicate_key")
            obj[key] = value
        return obj

    return json.loads(raw, object_pairs_hook=pairs)


def _path(value):
    if not isinstance(value, str) or not value.startswith("/") or value.startswith("//"):
        raise ManifestError("relative_www_path_required")
    if any(c in value for c in "\\\r\n\x00"):
        raise ManifestError("invalid_path")
    p = urlsplit(value)
    if p.scheme or p.netloc or p.fragment:
        raise ManifestError("relative_www_path_required")
    if any(k.lower() in TOKEN_KEYS | SECRET_HEADERS for k, _ in parse_qsl(p.query)):
        raise ManifestError("secret_query_not_allowed")


def validate_manifest(m):
    if not isinstance(m, dict) or m.get("schema") != MANIFEST_SCHEMA:
        raise ManifestError("invalid_schema")
    if set(m) - {
        "schema",
        "manifest_id",
        "window",
        "min_gap_s",
        "max_requests",
        "max_duration_s",
        "requests",
    }:
        raise ManifestError("unknown_manifest_field")
    if not isinstance(m.get("manifest_id"), str) or not ID_RE.fullmatch(m["manifest_id"]):
        raise ManifestError("invalid_manifest_id")
    try:
        start, end = (dt.datetime.fromisoformat(m["window"][k]) for k in ("start", "end"))
        if start.tzinfo is None or end.tzinfo is None or start >= end:
            raise ValueError
    except (ValueError, TypeError, KeyError) as exc:
        raise ManifestError("invalid_window") from exc
    gap = m.get("min_gap_s")
    duration = m.get("max_duration_s", 300)
    if type(gap) not in (int, float) or not math.isfinite(gap) or gap < 1:
        raise ManifestError("invalid_operation_gap")
    if type(duration) not in (int, float) or not math.isfinite(duration) or duration <= 0:
        raise ManifestError("invalid_duration")
    cap = m.get("max_requests")
    reqs = m.get("requests")
    if (
        type(cap) is not int
        or not 1 <= cap <= 600
        or not isinstance(reqs, list)
        or not 1 <= len(reqs) <= cap
    ):
        raise ManifestError("invalid_operation_count")
    seen, last_page = set(), None
    for r in reqs:
        if (
            not isinstance(r, dict)
            or not isinstance(r.get("id"), str)
            or not ID_RE.fullmatch(r["id"])
            or r["id"] in seen
        ):
            raise ManifestError("invalid_request_id")
        seen.add(r["id"])
        if r.get("op") == "page":
            if set(r) - {"id", "op", "path", "wait", "require"}:
                raise ManifestError("unknown_page_field")
            _path(r.get("path"))
            if r.get("wait", "networkidle") not in {"networkidle", "domcontentloaded", "load"}:
                raise ManifestError("invalid_wait")
            if r.get("require") is not None:
                try:
                    if not isinstance(r["require"], str) or len(r["require"]) > 512:
                        raise ValueError
                    re.compile(r["require"])
                except (ValueError, re.error) as exc:
                    raise ManifestError("invalid_require") from exc
            last_page = r["id"]
        elif r.get("op") == "post":
            if (
                set(r) - {"id", "op", "page", "api", "form", "headers"}
                or r.get("page") != last_page
                or last_page is None
            ):
                raise ManifestError("post_requires_current_page")
            _path(r.get("api"))
            for field in ("form", "headers"):
                if not isinstance(r.get(field, {}), dict):
                    raise ManifestError("invalid_request_values")
                for key, value in r.get(field, {}).items():
                    if (
                        not isinstance(key, str)
                        or not key
                        or len(key) > 128
                        or any(c in key for c in "\r\n\x00")
                    ):
                        raise ManifestError("invalid_request_key")
                    token = (
                        isinstance(value, dict)
                        and set(value) == {"$token"}
                        and isinstance(value["$token"], str)
                        and value["$token"] in TOKEN_RES
                    )
                    if not token and not isinstance(value, str):
                        raise ManifestError("invalid_request_value")
                    if key.lower() in SECRET_HEADERS or (key.lower() in TOKEN_KEYS and not token):
                        raise ManifestError("literal_secret_not_allowed")
        else:
            raise ManifestError("invalid_operation")
    return m


def parse_manifest(raw):
    if len(raw) > MAX_INDEX_BYTES:
        raise ManifestError("manifest_size_limit")
    try:
        return validate_manifest(_json(raw))
    except (ValueError, TypeError) as exc:
        raise ManifestError("invalid_manifest") from exc


class OriginalSessionDriver:
    """Delegate to unchanged public session methods, including their mature recovery.

    An injected session is for offline fixtures. It is not a network substitute.
    """

    def __init__(self, source=None, *, session=None):
        self.source_sha256 = None
        if session is None:
            if os.environ.get("CPBL_SCRAPE_PROFILE"):
                raise ValueError("persistent_profile_not_allowed_on_fetcher")
            source = Path(source or Path(__file__).with_name("_browser.py"))
            self.source_sha256 = digest(source.read_bytes())
            spec = importlib.util.spec_from_file_location("cpbl_fetch_original_browser", source)
            original = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(original)
            session = original.session()
        self.session = session
        self.counts = dict.fromkeys(
            (
                "request_events",
                "response_events",
                "redirect_responses",
                "page_websocket_events",
                "context_changes_observed",
            ),
            0,
        )
        self.nav_status = None
        self.context = None
        self._observe()

    def _observe(self):
        if self.context is self.session._ctx:
            return
        if self.context is not None:
            self.counts["context_changes_observed"] += 1
            self.nav_status = None  # recovery navigation was not observed; do not invent 200
        self.context = self.session._ctx
        self.context.on("request", lambda _r: self._count("request_events"))
        self.context.on("response", self._response)
        self.session._page.on("websocket", lambda _w: self._count("page_websocket_events"))

    def _count(self, key):
        self.counts[key] += 1

    def _response(self, response):
        self._count("response_events")
        self.counts["redirect_responses"] += int(response.status in {301, 302, 303, 307, 308})
        try:
            r = response.request
            if r.is_navigation_request() and r.frame == self.session._page.main_frame:
                self.nav_status = response.status
        except Exception:
            pass  # observation cannot change the mature session's behavior

    def page(self, path, wait, require):
        self.nav_status = None
        try:
            text = self.session.page_html(path, wait=wait, require=require)
        finally:
            self._observe()
        return self.nav_status, text

    def post(self, page, api, form, headers):
        try:
            return self.session.post(page, api, form, headers=headers)
        finally:
            self._observe()

    def observation(self):
        return {**self.counts, "coverage": "SDK-visible lower bound"}

    def close(self):
        self.session.close()


def _publish(folder, index):
    fd, name = tempfile.mkstemp(prefix=".index-", dir=folder)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(name, folder / "index.json")


def _resolve(values, html):
    resolved = {}
    for key, value in values.items():
        if isinstance(value, dict):
            match = TOKEN_RES[value["$token"]].search(html)
            if match is None:
                raise ValueError("token_missing")
            value = match.group(1)
        resolved[key] = value
    return resolved


def run(
    raw,
    out,
    driver_factory=OriginalSessionDriver,
    *,
    now=lambda: dt.datetime.now(TZ),
    clock=time.monotonic,
    sleep=time.sleep,
):
    """Capture session-returned UTF-8 text, not compressed HTTP wire bytes."""
    m = parse_manifest(raw)
    folder = Path(out) / m["manifest_id"]
    if Path(out).is_symlink():
        raise ValueError("symlink_output")
    Path(out).mkdir(parents=True, exist_ok=True)
    folder.mkdir(mode=0o700)  # exclusive claim; never overwrite/replay an existing bundle
    (folder / "responses").mkdir(mode=0o700)
    index = {
        "schema": BUNDLE_SCHEMA,
        "manifest_id": m["manifest_id"],
        "manifest_sha256": digest(raw),
        "fetcher_version": VERSION,
        "host": socket.gethostname(),
        "started_at": now().isoformat(),
        "ended_at": None,
        "requests_sent": 0,
        "stopped": None,
        "complete": False,
        "entries": [],
        "observed": {},
        "close_returned": False,
        "original_browser_sha256": None,
    }
    start, end = (dt.datetime.fromisoformat(m["window"][k]) for k in ("start", "end"))
    deadline = clock() + m.get("max_duration_s", 300)
    last_start, total, html, page_path, driver = None, 0, "", None, None

    def stop(code, rid=None):
        index["stopped"] = {"signal": code, "at": rid, "ts": now().isoformat()}

    _publish(folder, index)
    try:
        for r in m["requests"]:
            if last_start is not None:
                sleep(max(0, m["min_gap_s"] - (clock() - last_start)))
            if not start <= now() < end or clock() >= deadline:
                stop("window_or_duration", r["id"])
                break
            if driver is None:
                driver = driver_factory()
                index["original_browser_sha256"] = getattr(driver, "source_sha256", None)
            row = {
                "id": r["id"],
                "op": r["op"],
                "at": now().isoformat(),
                "path" if r["op"] == "page" else "api": r.get("path", r.get("api")),
            }
            index["entries"].append(row)
            index["requests_sent"] += 1  # logical manifest calls, never a whole-browser HTTP cap
            last_start = clock()
            _publish(folder, index)
            try:
                if r["op"] == "page":
                    status, text = driver.page(
                        r["path"], r.get("wait", "networkidle"), r.get("require")
                    )
                    row["http_status"] = status
                    html, page_path = text, r["path"]
                    row["require_ok"] = bool(text) and (
                        r.get("require") is None or re.search(r["require"], text) is not None
                    )
                    accepted = row["require_ok"] and status in (None, 200)
                else:
                    form, headers = (_resolve(r.get(k, {}), html) for k in ("form", "headers"))
                    status, text = driver.post(page_path, r["api"], form, headers)
                    row["http_status"] = status
                    accepted = status == 200
                    if accepted:
                        _json(text)
                row.update(http_status=status, ms=int((clock() - last_start) * 1000))
                if not accepted:
                    stop("response_not_accepted", r["id"])
                    break
                body = text.encode("utf-8")
                if len(body) > MAX_BODY_BYTES or total + len(body) > MAX_TOTAL_BYTES:
                    stop("body_size_limit", r["id"])
                    break
                rel = f"responses/{r['id']}.body"
                fd = os.open(folder / rel, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(fd, "wb") as f:
                    f.write(body)
                total += len(body)
                row.update(body=rel, bytes=len(body), sha256=digest(body))
            except Exception as exc:
                row["error_type"] = type(exc).__name__
                stop("operation_error:" + type(exc).__name__, r["id"])
                break
            finally:
                if driver is not None:
                    index["observed"] = driver.observation()
                _publish(folder, index)
    except Exception as exc:
        stop("session_error:" + type(exc).__name__)
    finally:
        if driver is not None:
            try:
                driver.close()
                index["close_returned"] = True
            except Exception as exc:
                stop("close_error:" + type(exc).__name__)
        index["ended_at"] = now().isoformat()
        index["complete"] = (
            index["stopped"] is None
            and index["close_returned"]
            and len(index["entries"]) == len(m["requests"])
        )
        _publish(folder, index)
    return index


def read_response(folder, row):
    """Read and verify one private response, keeping replay memory bounded per operation."""
    folder = Path(folder)
    try:
        if folder.is_symlink() or (folder / "responses").is_symlink():
            raise ValueError
        rid = row["id"]
        if not isinstance(rid, str) or not ID_RE.fullmatch(rid):
            raise ValueError
        expected = f"responses/{rid}.body"
        path = folder / expected
        if (
            row["body"] != expected
            or path.is_symlink()
            or path.stat().st_size > MAX_BODY_BYTES
            or type(row["bytes"]) is not int
            or not 0 <= row["bytes"] <= MAX_BODY_BYTES
        ):
            raise ValueError
        body = path.read_bytes()
        if len(body) != row["bytes"] or digest(body) != row["sha256"]:
            raise ValueError
        return body
    except (KeyError, TypeError, ValueError, OSError) as exc:
        raise BundleError("invalid_response") from exc


def verify_bundle(folder, manifest_raw, *, require_complete=True):
    """Validate every response for WP4 without retaining the whole bundle in memory."""
    m = parse_manifest(manifest_raw)
    folder = Path(folder)
    try:
        if folder.is_symlink() or (folder / "responses").is_symlink():
            raise ValueError
        index_path = folder / "index.json"
        if index_path.is_symlink() or index_path.stat().st_size > MAX_INDEX_BYTES:
            raise ValueError
        index = _json(index_path.read_bytes())
        if not isinstance(index, dict) or set(index) - {
            "schema",
            "manifest_id",
            "manifest_sha256",
            "fetcher_version",
            "host",
            "started_at",
            "ended_at",
            "requests_sent",
            "stopped",
            "complete",
            "entries",
            "observed",
            "close_returned",
            "original_browser_sha256",
        }:
            raise ValueError
        if (
            index["schema"] != BUNDLE_SCHEMA
            or index["manifest_id"] != m["manifest_id"]
            or index["manifest_sha256"] != digest(manifest_raw)
        ):
            raise ValueError
        if type(index.get("complete")) is not bool:
            raise ValueError
        if require_complete and (
            index["complete"] is not True
            or index.get("stopped") is not None
            or index.get("close_returned") is not True
        ):
            raise ValueError
        entries = index["entries"]
        if not isinstance(entries, list) or len(entries) > len(m["requests"]):
            raise ValueError
        if type(index.get("requests_sent")) is not int or index["requests_sent"] != len(entries):
            raise ValueError
        if index.get("complete") and len(entries) != len(m["requests"]):
            raise ValueError
        total = 0
        for row, request in zip(entries, m["requests"], strict=False):
            if row["id"] != request["id"] or row["op"] != request["op"]:
                raise ValueError
            key = "path" if request["op"] == "page" else "api"
            if row[key] != request[key] or set(row) - {
                "id",
                "op",
                "at",
                "path",
                "api",
                "require_ok",
                "http_status",
                "ms",
                "body",
                "bytes",
                "sha256",
                "error_type",
            }:
                raise ValueError
            if "body" not in row:
                if index.get("complete"):
                    raise ValueError
                continue
            body = read_response(folder, row)
            body.decode("utf-8")
            total += len(body)
            del body
            if total > MAX_TOTAL_BYTES:
                raise ValueError
        return index
    except (KeyError, TypeError, ValueError, OSError) as exc:
        raise BundleError("invalid_or_incomplete_bundle") from exc


def wait_worker(child, timeout, manifest_raw=None):
    """A standard POSIX job timeout; no request interception or protocol controls."""
    try:
        child.communicate(input=manifest_raw, timeout=timeout)
        return child.returncode, False
    except subprocess.TimeoutExpired:
        os.killpg(child.pid, signal.SIGTERM)
        try:
            child.communicate(timeout=5)
            return child.returncode, True
        except subprocess.TimeoutExpired:
            os.killpg(child.pid, signal.SIGKILL)
            child.communicate(timeout=5)
            return child.returncode, True


def main(argv=None):
    ap = argparse.ArgumentParser(description="WP3 original-session raw fetcher")
    ap.add_argument("manifest", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--browser-source", type=Path, default=Path(__file__).with_name("_browser.py"))
    ap.add_argument("--_worker", action="store_true", help=argparse.SUPPRESS)
    args = ap.parse_args(argv)
    try:
        raw = (
            sys.stdin.buffer.read(MAX_INDEX_BYTES + 1)
            if args._worker
            else args.manifest.read_bytes()
        )
        m = parse_manifest(raw)
        if args.check:
            print(
                json.dumps(
                    {
                        "ok": True,
                        "manifest_id": m["manifest_id"],
                        "requests": len(m["requests"]),
                        "sha256": digest(raw),
                    }
                )
            )
            return 0
        folder = args.out / m["manifest_id"]
        if args.verify:
            index = verify_bundle(folder, raw)
        elif args._worker:
            logging.disable(logging.CRITICAL)
            index = run(raw, args.out, lambda: OriginalSessionDriver(args.browser_source))
        else:
            end = dt.datetime.fromisoformat(m["window"]["end"])
            start = dt.datetime.fromisoformat(m["window"]["start"])
            current = dt.datetime.now(TZ)
            if folder.exists() or folder.is_symlink() or not start <= current < end:
                raise ValueError("not_ready")
            timeout = min(m.get("max_duration_s", 300), (end - current).total_seconds() - 10)
            if timeout <= 0:
                raise ValueError("insufficient_exit_margin")
            if os.environ.get("CPBL_SCRAPE_PROFILE"):
                raise ValueError("persistent_profile_not_allowed_on_fetcher")
            # Standalone Pi worker needs no database/alert/cloud credentials or debug traces.
            env = {
                key: os.environ[key]
                for key in (
                    "PATH",
                    "HOME",
                    "LANG",
                    "LC_ALL",
                    "LC_CTYPE",
                    "TZ",
                    "TMPDIR",
                    "TMP",
                    "TEMP",
                    "XDG_CACHE_HOME",
                    "XDG_CONFIG_HOME",
                    "PLAYWRIGHT_BROWSERS_PATH",
                    "CPBL_SCRAPE_CHANNEL",
                    "CPBL_SCRAPE_HEADED",
                    "CPBL_SCRAPE_UA",
                )
                if key in os.environ
            }
            command = [
                sys.executable,
                "-I",
                "-B",
                str(Path(__file__).resolve()),
                str(args.manifest.resolve()),
                "--out",
                str(args.out.resolve()),
                "--browser-source",
                str(args.browser_source.resolve()),
                "--_worker",
            ]
            child = subprocess.Popen(
                command,
                env=env,
                start_new_session=True,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            rc, timed_out = wait_worker(child, timeout, raw)
            if timed_out:
                if folder.is_dir() and not folder.is_symlink():
                    path = folder / "index.json"
                    index = (
                        _json(path.read_bytes())
                        if path.exists()
                        else {
                            "schema": BUNDLE_SCHEMA,
                            "manifest_id": m["manifest_id"],
                            "manifest_sha256": digest(raw),
                            "fetcher_version": VERSION,
                            "entries": [],
                            "requests_sent": 0,
                        }
                    )
                    index.update(
                        complete=False,
                        stopped={
                            "signal": "run_timeout",
                            "at": None,
                            "ts": dt.datetime.now(TZ).isoformat(),
                        },
                        ended_at=dt.datetime.now(TZ).isoformat(),
                        close_returned=False,
                    )
                    _publish(folder, index)
                print(
                    json.dumps({"complete": False, "stopped": "run_timeout", "child_waited": True})
                )
                return 124
            if rc != 0 and not (folder / "index.json").is_file():
                print(
                    json.dumps(
                        {
                            "complete": False,
                            "stopped": "worker_failed",
                            "rc": rc,
                            "child_waited": True,
                        }
                    )
                )
                return 3
            index = verify_bundle(folder, raw, require_complete=rc == 0)
        print(
            json.dumps(
                {k: index[k] for k in ("manifest_id", "requests_sent", "complete", "stopped")}
            )
        )
        return 0 if index["complete"] else 3
    except (ManifestError, BundleError, OSError, ValueError):
        print(json.dumps({"complete": False, "stopped": "invalid_input_or_bundle"}))
        return 65


if __name__ == "__main__":
    raise SystemExit(main())
