"""Pi → VPS SFTP sender; optionally run the existing fetcher first, never a DB writer.

Default sender callers must not mutate/consume raw during transfer. Request mode
publishes delivery.json after raw wait0; metadata-only SFTP may still be active.
Neither result is VPS validation. The receiver cannot enforce write-once.
Only stdlib plus the version-pinned www_fetch module; no private key bytes are read.
"""

from __future__ import annotations

import argparse
import base64
import contextlib
import fcntl
import hashlib
import importlib.util
import io
import json
import math
import os
import re
import stat
import subprocess
import tempfile
import time
from pathlib import Path

INTERFACE = "cpbl393-sftp-drop/v1-candidate.1"
SUPPLY_VERSION = "393-pi-auto-source.1-candidate"
HOST = "45.76.100.29"
PORT = 22
USER = "cpbl393-receiver"
HOST_KEY_SHA256 = "SHA256:b8E6MnwfRRThcvrHhbLygtHZIGIav2DiI+QMsYwWCgw"
REMOTE_ROOT = "/incoming"
IDENTITY_FILE = Path("/home/ruan/.ssh/cpbl393_receiver_ed25519")
KNOWN_HOSTS = Path("/home/ruan/.ssh/cpbl393_receiver_known_hosts")
# Undeployed request-reader proposal; never reuse the upload or backup identity.
REQUEST_USER = "cpbl393-request-ro"
REQUEST_IDENTITY = Path("/home/ruan/.ssh/cpbl393_request_ed25519")
REQUEST_JOBS = frozenset({"scrape-daily", "postseason-evening", "weekly-box-revisions"})
POLL_SECONDS = 5
DISCOVERY_POLL_SECONDS = 30
COOLDOWN_SECONDS = 1200

source = Path(__file__).resolve().parents[2] / "src/cpbl/ingest/www_fetch.py"
spec = importlib.util.spec_from_file_location("cpbl_send_www_fetch", source)
fetch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fetch)


def _private(path: Path, *, directory=False):
    info = path.lstat()
    kind = stat.S_ISDIR if directory else stat.S_ISREG
    if not kind(info.st_mode) or info.st_uid != os.getuid():
        raise ValueError("private_owned_path_required")
    if stat.S_IMODE(info.st_mode) != (0o700 if directory else 0o600):
        raise ValueError("private_mode_required")


def _pinned_hosts(path: Path):
    _private(path)
    if path.stat().st_size > 16384:
        raise ValueError("invalid_known_hosts")
    rows = [row.split() for row in path.read_text().splitlines()
            if row.strip() and not row.lstrip().startswith("#")]
    if len(rows) != 1 or len(rows[0]) < 3:
        raise ValueError("single_pinned_host_required")
    host, kind, encoded = rows[0][:3]
    if host not in {HOST, f"[{HOST}]:{PORT}"} or kind != "ssh-ed25519":
        raise ValueError("wrong_host_or_key_type")
    blob = base64.b64decode(encoded, validate=True)
    prefix = b"\x00\x00\x00\x0bssh-ed25519\x00\x00\x00\x20"
    pin = "SHA256:" + base64.b64encode(hashlib.sha256(blob).digest()).decode().rstrip("=")
    if len(blob) != len(prefix) + 32 or not blob.startswith(prefix) or pin != HOST_KEY_SHA256:
        raise ValueError("wrong_host_pin")


def _authentication(identity_file, known_hosts):
    identity, hosts = Path(identity_file).absolute(), Path(known_hosts).absolute()
    if any(c in str(path) for path in (identity, hosts) for c in '\\"\r\n\x00%$'):
        raise ValueError("invalid_authentication_path")
    _private(identity)  # stat only; OpenSSH alone reads the private key
    _pinned_hosts(hosts)
    return identity, hosts


def _sftp_command(identity, hosts, user):
    options = ["IdentitiesOnly=yes", "IdentityAgent=none", "BatchMode=yes",
               "StrictHostKeyChecking=yes", f'UserKnownHostsFile="{hosts}"',
               "GlobalKnownHostsFile=/dev/null", "HostKeyAlgorithms=ssh-ed25519",
               "UpdateHostKeys=no", "ForwardAgent=no", "ClearAllForwardings=yes",
               "ControlMaster=no", "ControlPath=none", "ProxyCommand=none",
               "ProxyJump=none", "ConnectTimeout=10", "ServerAliveInterval=10",
               "ServerAliveCountMax=3"]
    command = ["/usr/bin/sftp", "-F", "/dev/null", "-b", "-", "-P", str(PORT),
               "-i", str(identity)]
    for option in options:
        command.extend(["-o", option])
    command.append(f"{user}@{HOST}")
    return command


def receive_request(job, out, *, identity_file=REQUEST_IDENTITY,
                    known_hosts=KNOWN_HOSTS, timeout):
    """One GET of original manifest bytes; no list, retry, fallback or source fetch."""
    result = {"outcome": "precheck_failed", "request_sftp_rc": None,
              "request_child_waited": False, "request_started": False, "timed_out": False}
    child = None
    try:
        if not isinstance(job, str) or job not in REQUEST_JOBS:
            raise ValueError("invalid_job")
        if type(timeout) not in (int, float) or not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("positive_lease_timeout_required")
        identity, hosts = _authentication(identity_file, known_hosts)
        out = Path(out).absolute()
        _private(out, directory=True)
        request_dir = out / ".requests"
        request_dir.mkdir(mode=0o700, exist_ok=True)
        _private(request_dir, directory=True)
        fd, name = tempfile.mkstemp(prefix=job + "-", suffix=".json", dir=request_dir)
        os.close(fd)
        manifest = Path(name)
        result.update(job=job, manifest_path=str(manifest), outcome="partial_or_unknown")
        batch = f'get /requests/{job}.json ".requests/{manifest.name}"\n'.encode("ascii")
        child = subprocess.Popen(_sftp_command(identity, hosts, REQUEST_USER), cwd=out,
                                 env={"LANG": "C", "LC_ALL": "C"}, start_new_session=True,
                                 stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL)
        result["request_started"] = True
        rc, timed_out = fetch.wait_worker(child, timeout, batch)
        result.update(request_sftp_rc=rc, timed_out=timed_out, request_child_waited=True)
        if rc != 0 or timed_out:
            return result
        result["outcome"] = "precheck_failed"
        _private(manifest)
        with manifest.open("rb") as stream:
            raw = stream.read(fetch.MAX_INDEX_BYTES + 1)
        parsed = fetch.parse_manifest(raw)
        if not re.fullmatch(re.escape(job) + r"-[0-9a-f]{20}-[0-9]{4}", parsed["manifest_id"]):
            raise ValueError("request_job_mismatch")
        result.update(outcome="request_received", manifest_id=parsed["manifest_id"],
                      manifest_sha256=fetch.digest(raw), manifest_bytes=len(raw),
                      request_prefix=parsed["manifest_id"].rsplit("-", 1)[0],
                      request_operations=len(parsed["requests"]),
                      request_window_end=parsed["window"]["end"])
    except Exception:
        if child is not None:
            result["request_sftp_rc"] = child.returncode
    return result


def publish_transfer_receipt(bundle, raw_result, *, identity_file=IDENTITY_FILE,
                             known_hosts=KNOWN_HOSTS, timeout):
    """Publish raw-stop evidence after its native wait, not after all SFTP activity."""
    result = {"receipt_published": False, "receipt_sftp_rc": None,
              "receipt_child_waited": False, "receipt_started": False, "receipt_timed_out": False}
    child = None
    try:
        if (raw_result.get("outcome") != "transfer_complete"
                or type(raw_result.get("sftp_rc")) is not int or raw_result["sftp_rc"] != 0
                or raw_result.get("child_waited") is not True):
            raise ValueError("raw_native_wait_required")
        mid = raw_result["manifest_id"]
        if not isinstance(mid, str) or not fetch.ID_RE.fullmatch(mid):
            raise ValueError("invalid_manifest_id")
        if type(timeout) not in (int, float) or not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("positive_lease_timeout_required")
        identity, hosts = _authentication(identity_file, known_hosts)
        bundle = Path(bundle).absolute()
        _private(bundle, directory=True)
        receipt = {key: raw_result[key] for key in (
            "manifest_id", "manifest_sha256", "index_sha256",
        )}
        for key in ("manifest_sha256", "index_sha256"):
            if not isinstance(receipt[key], str) or not re.fullmatch("[0-9a-f]{64}", receipt[key]):
                raise ValueError("invalid_hash")
        receipt.update(raw_batch_rc=0, raw_batch_waited=True)
        raw = json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode("ascii")
        fd, name = tempfile.mkstemp(prefix=".delivery-", suffix=".json", dir=bundle)
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
        result.update(receipt_path=name, receipt_bytes=len(raw), receipt_sha256=fetch.digest(raw))
        target = f"{REMOTE_ROOT}/{mid}"
        batch = (f'put "{Path(name).name}" {target}/.delivery.json.upload\n'
                 f"rename {target}/.delivery.json.upload {target}/delivery.json\n").encode("ascii")
        child = subprocess.Popen(_sftp_command(identity, hosts, USER), cwd=bundle,
                                 env={"LANG": "C", "LC_ALL": "C"}, start_new_session=True,
                                 stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL)
        result["receipt_started"] = True
        rc, timed_out = fetch.wait_worker(child, timeout, batch)
        result.update(receipt_sftp_rc=rc, receipt_timed_out=timed_out,
                      receipt_child_waited=True, receipt_published=rc == 0 and not timed_out)
    except Exception:
        if child is not None:
            result["receipt_sftp_rc"] = child.returncode
    return result


def send_bundle(manifest, bundle, *, identity_file=IDENTITY_FILE,
                known_hosts=KNOWN_HOSTS, timeout, expected_manifest_sha256=None):
    """One native batch, no recursive copy/retry/resume/delete or remote command."""
    result = {"interface": INTERFACE, "outcome": "precheck_failed", "sftp_rc": None,
              "writer_started": False, "child_waited": False, "raw_started": False,
              "timed_out": False}
    child = None
    try:
        if type(timeout) not in (int, float) or not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("positive_lease_timeout_required")
        bundle = Path(bundle).absolute()
        identity, hosts = _authentication(identity_file, known_hosts)
        _private(bundle, directory=True)
        _private(bundle / "responses", directory=True)
        _private(bundle / "index.json")
        with Path(manifest).open("rb") as stream:
            raw = stream.read(fetch.MAX_INDEX_BYTES + 1)
        if expected_manifest_sha256 is not None and fetch.digest(raw) != expected_manifest_sha256:
            raise ValueError("request_manifest_changed")
        index = fetch.verify_bundle(bundle, raw, require_complete=True)
        index_raw = (bundle / "index.json").read_bytes()
        if json.loads(index_raw) != index:
            raise ValueError("index_changed")
        for row in index["entries"]:
            _private(bundle / row["body"])
        target = f"{REMOTE_ROOT}/{index['manifest_id']}"
        lines = [f"mkdir {target}", f"mkdir {target}/responses"]
        for row in index["entries"]:
            lines.append(f'put "{row["body"]}" {target}/{row["body"]}')
        lines.extend([f'put "index.json" {target}/.index.json.upload',
                      f"rename {target}/.index.json.upload {target}/index.json"])
        # All batch paths are generated from verify_bundle's bounded safe IDs.
        # cwd carries the local path as argv metadata, never interpolated syntax.
        batch = ("\n".join(lines) + "\n").encode("ascii")
        command = _sftp_command(identity, hosts, USER)
        result.update(manifest_id=index["manifest_id"], manifest_sha256=fetch.digest(raw),
                      index_sha256=fetch.digest(index_raw),
                      body_bytes=sum(row["bytes"] for row in index["entries"]),
                      file_count=len(index["entries"]) + 1)
        result["outcome"] = "partial_or_unknown"
        child = subprocess.Popen(command, cwd=bundle, env={"LANG": "C", "LC_ALL": "C"},
                                 start_new_session=True, stdin=subprocess.PIPE,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        result["raw_started"] = True
        rc, timed_out = fetch.wait_worker(child, timeout, batch)
        result.update(sftp_rc=rc, timed_out=timed_out, child_waited=True)
        if rc == 0 and not timed_out:
            result["outcome"] = "transfer_complete"
    except Exception:
        # No exception text, stdout/stderr, argv, key, raw text or form values in logs.
        # An unknown launch/exit/ack remains unknown; never assert collision or rollback.
        if child is not None:
            result["sftp_rc"] = child.returncode
    return result


@contextlib.contextmanager
def _request_lock(out):
    _private(out, directory=True)
    fd = os.open(out / ".worker.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != 0o600):
            raise ValueError("private_lock_required")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
        else:
            yield True
    finally:
        os.close(fd)


def _state(out, name, text):
    path = out / name
    if os.path.lexists(path):
        _private(path)
    fd, tmp = tempfile.mkstemp(prefix=".state-", dir=out)
    with os.fdopen(fd, "w", encoding="ascii") as stream:
        stream.write(text + "\n")
    os.replace(tmp, path)


def _source_gap(out):
    path = out / ".last-source-end"
    if not os.path.lexists(path):
        return
    _private(path)
    if path.stat().st_size > 32:
        raise ValueError("invalid_source_clock")
    previous = float(path.read_text(encoding="ascii"))
    if not math.isfinite(previous) or previous < 0:
        raise ValueError("invalid_source_clock")
    delay = previous + 1 - time.time()
    if delay > 1:
        raise ValueError("source_clock_moved_backward")
    if delay > 0:
        time.sleep(delay)


def _claim_attempt(out, mid, sha, operations, limit):
    prefix, number = mid.rsplit("-", 1)
    root = out / ".attempts"
    root.mkdir(mode=0o700, exist_ok=True)
    _private(root, directory=True)
    folder = root / prefix
    folder.mkdir(mode=0o700, exist_ok=True)
    _private(folder, directory=True)
    reserved, previous = 0, None
    for path in folder.iterdir():
        _private(path)
        if not re.fullmatch("[0-9]{4}", path.name) or path.stat().st_size > 80:
            raise ValueError("invalid_attempt_record")
        saved = path.read_text(encoding="ascii").splitlines()
        if len(saved) != 2 or not re.fullmatch("[0-9a-f]{64}", saved[0]) or saved[1] not in {"1", "2"}:
            raise ValueError("invalid_attempt_record")
        reserved += int(saved[1])
        if path.name == number:
            previous = saved
    if previous is not None:
        if previous != [sha, str(operations)]:
            raise ValueError("attempt_manifest_changed")
        return False, reserved
    if operations not in (1, 2) or reserved + operations > limit:
        raise ValueError("operation_budget_exhausted")
    fd = os.open(folder / number, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="ascii") as stream:
        stream.write(f"{sha}\n{operations}\n")
    return True, reserved + operations


def _block_unknown(out, result):
    for started, waited, native_rc, stage in (
        ("request_started", "request_child_waited", "request_sftp_rc", "request"),
        ("raw_started", "child_waited", "sftp_rc", "raw"),
        ("receipt_started", "receipt_child_waited", "receipt_sftp_rc", "receipt"),
    ):
        if result.get(started) and (result.get(waited) is not True
                                   or type(result.get(native_rc)) is not int):
            _state(out, ".blocked", stage + "_exit_unknown")


def _arguments(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path, nargs="?")
    parser.add_argument("--bundle", type=Path)
    parser.add_argument("--request-job", help="GET one proposed /requests/<job>.json, then fetch/send")
    parser.add_argument("--serve-job", help="Bounded repeated batches for one job/prefix")
    parser.add_argument("--out", type=Path, help="Existing private output root for request mode")
    parser.add_argument("--max-seconds", type=float)
    parser.add_argument("--discovery-seconds", type=float)
    parser.add_argument("--max-reads", type=int)
    parser.add_argument("--max-operations", type=int)
    parser.add_argument("--request-identity-file", type=Path, default=REQUEST_IDENTITY)
    parser.add_argument("--fetch", action="store_true",
                        help="Run the unchanged original fetcher once before sending its new bundle")
    parser.add_argument("--identity-file", type=Path, default=IDENTITY_FILE)
    parser.add_argument("--known-hosts", type=Path, default=KNOWN_HOSTS)
    parser.add_argument("--timeout", type=float, required=True,
                        help="Work seconds from the lease, plus existing TERM/KILL wait (up to 10s)")
    try:
        with contextlib.redirect_stderr(io.StringIO()):
            args = parser.parse_args(argv)
    except SystemExit as exc:
        if exc.code == 0:
            return 0
        print(json.dumps({"interface": INTERFACE, "outcome": "precheck_failed",
                          "sftp_rc": None, "writer_started": False}))
        return 1
    return args


def _transport_timeout(args, request):
    if request is None:
        return args.timeout
    end = fetch.dt.datetime.fromisoformat(request["request_window_end"]).timestamp()
    end = min(end, getattr(args, "serve_deadline_epoch", end))
    return min(args.timeout, end - time.time() - 10)


def _execute(args, *, expected_prefix=None, operation_limit=600):
    result = {"interface": INTERFACE, "outcome": "precheck_failed", "fetch_rc": None,
              "sftp_rc": None, "writer_started": False, "child_waited": False}
    request = None
    if args.request_job is not None:
        result["supply_version"] = SUPPLY_VERSION
        if args.manifest is not None or args.bundle is not None or args.out is None or args.fetch:
            return 1, result
        request = receive_request(args.request_job, args.out,
                                  identity_file=args.request_identity_file,
                                  known_hosts=args.known_hosts,
                                  timeout=getattr(args, "request_timeout", args.timeout))
        _block_unknown(args.out, request)
        if request["outcome"] != "request_received":
            return 1, {**result, **request}
        args.manifest = Path(request["manifest_path"])
        args.bundle = args.out / request["manifest_id"]
        args.fetch = True
        result.update(request_sftp_rc=request["request_sftp_rc"],
                      request_child_waited=request["request_child_waited"],
                      request_started=request.get("request_started", False))
    elif args.manifest is None or args.bundle is None or args.out is not None:
        return 1, result
    if args.fetch:
        try:
            if not math.isfinite(args.timeout) or args.timeout <= 0:
                raise ValueError("positive_lease_timeout_required")
            with args.manifest.open("rb") as stream:
                raw = stream.read(fetch.MAX_INDEX_BYTES + 1)
            manifest = fetch.parse_manifest(raw)
            if request is not None and fetch.digest(raw) != request["manifest_sha256"]:
                raise ValueError("request_manifest_changed")
            if args.bundle.name != manifest["manifest_id"]:
                raise ValueError("bundle_must_match_original_manifest_id")
            if request is not None:
                prefix = manifest["manifest_id"].rsplit("-", 1)[0]
                result.update(manifest_id=manifest["manifest_id"], request_prefix=prefix,
                              request_operations=len(manifest["requests"]),
                              request_window_start=manifest["window"]["start"],
                              request_window_end=manifest["window"]["end"])
                request["request_window_end"] = manifest["window"]["end"]
                if expected_prefix is not None and prefix != expected_prefix:
                    return 0, {**result, "outcome": "prefix_changed"}
                _source_gap(args.out)
                start, end = (fetch.dt.datetime.fromisoformat(manifest["window"][k])
                              for k in ("start", "end"))
                current = fetch.dt.datetime.now(fetch.TZ)
                if not start <= current < end:
                    return 1, {**result, "outcome": "outside_window", "fetch_rc": 65}
                available = getattr(args, "serve_deadline_epoch", end.timestamp()) - current.timestamp()
                work = min(manifest.get("max_duration_s", 300), end.timestamp() - current.timestamp() - 10)
                if work <= 0 or work + 10 > available:
                    return 1, {**result, "outcome": "window_budget_exhausted"}
                claimed, reserved = _claim_attempt(args.out, manifest["manifest_id"],
                                                    fetch.digest(raw), len(manifest["requests"]),
                                                    operation_limit)
                result["operations_reserved"] = reserved
                if not claimed or os.path.lexists(args.bundle):
                    return 0, {**result, "outcome": "already_attempted"}
            # The mature CLI owns its existing window, collision and worker-wait
            # behaviour. Do not reuse an old bundle after any fetch failure.
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                result["fetch_started"] = True
                result["fetch_rc"] = fetch.main([
                    str(args.manifest), "--out", str(args.bundle.parent),
                ])
            if request is not None:
                _state(args.out, ".last-source-end", f"{time.time():.6f}")
        except (OSError, ValueError):
            pass
        if result["fetch_rc"] != 0:
            if request is not None and result.get("fetch_started"):
                _state(args.out, ".cooldown-until", str(int(time.time()) + COOLDOWN_SECONDS))
            return 1, result
    timeout = _transport_timeout(args, request)
    if timeout <= 0:
        return 1, {**result, "outcome": "window_budget_exhausted"}
    context = result
    result = send_bundle(args.manifest, args.bundle, identity_file=args.identity_file,
                         known_hosts=args.known_hosts, timeout=timeout,
                         expected_manifest_sha256=request["manifest_sha256"] if request else None)
    if args.fetch:
        result["fetch_rc"] = 0
    if request is not None:
        result.update({key: context[key] for key in (
            "request_started", "request_prefix", "request_operations", "request_window_end",
            "operations_reserved", "fetch_started",
            "supply_version",
        ) if key in context})
        result.update(request_job=request["job"], request_sftp_rc=request["request_sftp_rc"],
                      request_child_waited=request["request_child_waited"],
                      request_manifest_sha256=request["manifest_sha256"])
        if result["outcome"] == "transfer_complete":
            timeout = _transport_timeout(args, request)
            if timeout > 0:
                result.update(publish_transfer_receipt(args.bundle, result,
                                                       identity_file=args.identity_file,
                                                       known_hosts=args.known_hosts, timeout=timeout))
            if not result.get("receipt_published", False):
                result["outcome"] = "partial_or_unknown"
        _block_unknown(args.out, result)
    return (0 if result["outcome"] == "transfer_complete" else 1), result


def _run_once(args, *, expected_prefix=None):
    failed = {"interface": INTERFACE, "supply_version": SUPPLY_VERSION,
              "outcome": "precheck_failed", "writer_started": False}
    if args.request_job is None or args.out is None:
        return _execute(args)
    args.out = args.out.absolute()
    limit = args.max_operations if args.max_operations is not None else 600
    if not 1 <= limit <= 600:
        return 1, failed
    try:
        with _request_lock(args.out) as acquired:
            if not acquired:
                return 0, {**failed, "outcome": "busy"}
            blocked = args.out / ".blocked"
            if os.path.lexists(blocked):
                _private(blocked)
                return 1, {**failed, "outcome": "blocked"}
            cooldown = args.out / ".cooldown-until"
            if os.path.lexists(cooldown):
                _private(cooldown)
                if cooldown.stat().st_size > 32:
                    raise ValueError("invalid_cooldown")
                until = int(cooldown.read_text(encoding="ascii"))
                if until < 0:
                    raise ValueError("invalid_cooldown")
                if until > time.time():
                    return 0, {**failed, "outcome": "cooldown", "cooldown_until": until}
            try:
                return _execute(args, expected_prefix=expected_prefix, operation_limit=limit)
            except Exception:
                _state(args.out, ".blocked", "local_error")
                return 1, {**failed, "outcome": "blocked"}
    except Exception:
        return 1, failed


def _serve(args):
    result = {"interface": INTERFACE, "supply_version": SUPPLY_VERSION, "stage": "service",
              "job": args.serve_job if args.serve_job in REQUEST_JOBS else None,
              "outcome": "precheck_failed", "poll_attempts": 0, "request_clients": 0,
              "raw_clients": 0, "receipt_clients": 0, "batches_delivered": 0,
              "operations_reserved": None, "writer_started": False}
    if (args.serve_job not in REQUEST_JOBS or args.request_job is not None
            or args.manifest is not None or args.bundle is not None or args.fetch or args.out is None
            or args.max_seconds is None or not math.isfinite(args.max_seconds) or args.max_seconds <= 10
            or args.discovery_seconds is None or not math.isfinite(args.discovery_seconds)
            or not 0 < args.discovery_seconds <= args.max_seconds
            or args.max_reads is None or args.max_reads <= 0
            or args.max_operations is None or not 1 <= args.max_operations <= 600
            or not math.isfinite(args.timeout) or args.timeout <= 0):
        return 1, result
    outer = time.monotonic() + args.max_seconds
    discovery = time.monotonic() + args.discovery_seconds
    active = outer
    prefix = None
    deadline_epoch = time.time() + args.max_seconds
    source_deadline_epoch = deadline_epoch
    while result["poll_attempts"] < args.max_reads:
        deadline = min(outer, discovery if prefix is None else active)
        remaining = deadline - time.monotonic()
        if remaining <= 10:
            return 75, {**result, "outcome": "window_closed"}
        one = argparse.Namespace(**vars(args))
        one.request_job = args.serve_job
        one.serve_job = None
        one.serve_deadline_epoch = source_deadline_epoch
        one.request_timeout = min(args.timeout, remaining - 10)
        rc, row = _run_once(one, expected_prefix=prefix)
        result["poll_attempts"] += 1
        for flag, counter in (("request_started", "request_clients"),
                              ("raw_started", "raw_clients"), ("receipt_started", "receipt_clients")):
            result[counter] += int(row.get(flag) is True)
        result["last_outcome"] = row["outcome"]
        print(json.dumps({"stage": "poll", "poll": result["poll_attempts"], **row}))
        incoming_prefix = row.get("request_prefix")
        if incoming_prefix is not None:
            if prefix is not None and incoming_prefix != prefix:
                return 76, {**result, "outcome": "prefix_changed"}
            prefix = incoming_prefix
            result["request_prefix"] = prefix
            end = fetch.dt.datetime.fromisoformat(row["request_window_end"]).timestamp()
            source_deadline_epoch = min(source_deadline_epoch, end)
            active = min(active, time.monotonic() + max(0, end - time.time()))
            result["operations_reserved"] = row.get("operations_reserved", result["operations_reserved"])
        if row["outcome"] == "transfer_complete":
            result["batches_delivered"] += 1
        elif row["outcome"] in {"cooldown", "prefix_changed"}:
            return (76 if row["outcome"] == "prefix_changed" else 75), {**result, "outcome": row["outcome"]}
        elif row["outcome"] == "outside_window":
            if fetch.dt.datetime.fromisoformat(row["request_window_end"]).timestamp() <= time.time():
                return 75, {**result, "outcome": "window_closed"}
        elif row.get("request_started") and row.get("request_child_waited") is not True:
            return 1, {**result, "outcome": "exit_unknown"}
        elif row.get("request_sftp_rc") not in (None, 0) and row.get("request_child_waited") is True:
            # Native rc cannot distinguish a withdrawn slot, auth or transport
            # error. Never claim "missing"/job success from it or start WWW.
            if prefix is not None:
                return 75, {**result, "outcome": "request_unavailable"}
        elif rc != 0:
            return 1, {**result, "outcome": row["outcome"]}
        if result["poll_attempts"] >= args.max_reads:
            break
        interval = DISCOVERY_POLL_SECONDS if prefix is None else POLL_SECONDS
        remaining = min(outer, discovery if prefix is None else active) - time.monotonic()
        if remaining > 0:
            time.sleep(min(interval, remaining))
    return 75, {**result, "outcome": "read_budget_exhausted"}


def main(argv=None):
    args = _arguments(argv)
    if isinstance(args, int):
        return args
    if args.serve_job is None and (
        args.max_seconds is not None or args.discovery_seconds is not None or args.max_reads is not None
        or (args.request_job is None and args.max_operations is not None)
    ):
        print(json.dumps({"interface": INTERFACE, "outcome": "precheck_failed", "sftp_rc": None,
                          "writer_started": False}))
        return 1
    rc, result = _serve(args) if args.serve_job is not None else _run_once(args)
    print(json.dumps(result))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
