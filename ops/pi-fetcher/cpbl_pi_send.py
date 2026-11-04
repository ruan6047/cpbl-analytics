"""Pi → VPS SFTP sender; optionally run the existing fetcher first, never a DB writer.

Producer and consumer must not mutate/consume this run during transfer. SFTP rc0
is transfer completion only. The receiver cannot enforce write-once on its owner.
Only stdlib plus the unchanged www_fetch module; no private key bytes are read.
"""

from __future__ import annotations

import argparse
import base64
import contextlib
import hashlib
import importlib.util
import io
import json
import math
import os
import stat
import subprocess
from pathlib import Path

INTERFACE = "cpbl393-sftp-drop/v1-candidate.1"
HOST = "45.76.100.29"
PORT = 22
USER = "cpbl393-receiver"
HOST_KEY_SHA256 = "SHA256:b8E6MnwfRRThcvrHhbLygtHZIGIav2DiI+QMsYwWCgw"
REMOTE_ROOT = "/incoming"
IDENTITY_FILE = Path("/home/ruan/.ssh/cpbl393_receiver_ed25519")
KNOWN_HOSTS = Path("/home/ruan/.ssh/cpbl393_receiver_known_hosts")

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


def send_bundle(manifest, bundle, *, identity_file=IDENTITY_FILE,
                known_hosts=KNOWN_HOSTS, timeout):
    """One native batch, no recursive copy/retry/resume/delete or remote command."""
    result = {"interface": INTERFACE, "outcome": "precheck_failed", "sftp_rc": None,
              "writer_started": False, "child_waited": False, "timed_out": False}
    child = None
    try:
        if type(timeout) not in (int, float) or not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("positive_lease_timeout_required")
        bundle = Path(bundle).absolute()
        identity, hosts = Path(identity_file).absolute(), Path(known_hosts).absolute()
        # OpenSSH expands % tokens and ${ENV} in BOTH identity and known-hosts
        # paths, even when quoted. Reject expansion/config escapes before stat
        # so Python validates the same literal paths that OpenSSH will use.
        if any(c in str(path) for path in (identity, hosts) for c in '\\"\r\n\x00%$'):
            raise ValueError("invalid_authentication_path")
        _private(identity)  # metadata only: only OpenSSH may read private key bytes
        _pinned_hosts(hosts)
        _private(bundle, directory=True)
        _private(bundle / "responses", directory=True)
        _private(bundle / "index.json")
        with Path(manifest).open("rb") as stream:
            raw = stream.read(fetch.MAX_INDEX_BYTES + 1)
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
        command.append(f"{USER}@{HOST}")
        result.update(manifest_id=index["manifest_id"], manifest_sha256=fetch.digest(raw),
                      index_sha256=fetch.digest(index_raw),
                      body_bytes=sum(row["bytes"] for row in index["entries"]),
                      file_count=len(index["entries"]) + 1)
        result["outcome"] = "partial_or_unknown"
        child = subprocess.Popen(command, cwd=bundle, env={"LANG": "C", "LC_ALL": "C"},
                                 start_new_session=True, stdin=subprocess.PIPE,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
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


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--bundle", type=Path, required=True)
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
    if args.fetch:
        result = {"interface": INTERFACE, "outcome": "precheck_failed", "fetch_rc": None,
                  "sftp_rc": None, "writer_started": False, "child_waited": False}
        try:
            if not math.isfinite(args.timeout) or args.timeout <= 0:
                raise ValueError("positive_lease_timeout_required")
            with args.manifest.open("rb") as stream:
                raw = stream.read(fetch.MAX_INDEX_BYTES + 1)
            manifest = fetch.parse_manifest(raw)
            if args.bundle.name != manifest["manifest_id"]:
                raise ValueError("bundle_must_match_original_manifest_id")
            # The mature CLI owns its existing window, collision and worker-wait
            # behaviour. Do not reuse an old bundle after any fetch failure.
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                result["fetch_rc"] = fetch.main([
                    str(args.manifest), "--out", str(args.bundle.parent),
                ])
        except (OSError, ValueError):
            pass
        if result["fetch_rc"] != 0:
            print(json.dumps(result))
            return 1
    result = send_bundle(args.manifest, args.bundle, identity_file=args.identity_file,
                         known_hosts=args.known_hosts, timeout=args.timeout)
    if args.fetch:
        result["fetch_rc"] = 0
    print(json.dumps(result))
    return 0 if result["outcome"] == "transfer_complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
