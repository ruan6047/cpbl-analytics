"""Only the new sender boundary; synthetic files and a process double, no SFTP server."""

import base64
import datetime as dt
import fcntl
import hashlib
import importlib.util
import json
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ENTRY = ROOT / "ops/pi-fetcher/cpbl_pi_send.py"
spec = importlib.util.spec_from_file_location("pi_send_393", ENTRY)
sender = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sender)


@pytest.fixture
def inputs(tmp_path, monkeypatch):
    # Existing fixture is synthetic, never the retained real bundle.
    shutil.copytree(ROOT / "tests/fixtures/replay_393", tmp_path / "source space")
    root = tmp_path / "source space"
    for path in [root, *root.rglob("*")]:
        path.chmod(0o700 if path.is_dir() else 0o600)
    identity = tmp_path / "identity file"
    identity.write_bytes(b"NOT A KEY; sender must only stat this file")
    identity.chmod(0o600)
    blob = b"\x00\x00\x00\x0bssh-ed25519\x00\x00\x00\x20" + b"x" * 32
    pin = "SHA256:" + base64.b64encode(hashlib.sha256(blob).digest()).decode().rstrip("=")
    monkeypatch.setattr(sender, "HOST_KEY_SHA256", pin, raising=False)
    hosts = tmp_path / "known hosts"
    hosts.write_text("45.76.100.29 ssh-ed25519 " + base64.b64encode(blob).decode() + "\n")
    hosts.chmod(0o600)
    return root / "manifest.json", root / "bundle", identity, hosts


def invoke(inputs):
    manifest, bundle, identity, hosts = inputs
    return sender.send_bundle(manifest, bundle, identity_file=identity, known_hosts=hosts, timeout=30)


def test_verified_bundle_is_sent_once_with_original_identity_and_index_last(inputs, monkeypatch):
    calls, launches = [], []
    original_read = Path.read_bytes

    def no_private_key_read(path):
        assert path != inputs[2]
        return original_read(path)

    monkeypatch.setattr(Path, "read_bytes", no_private_key_read)
    # Extra local files must never be uploaded by a recursive copy/glob.
    (inputs[1] / "responses/unlisted.body").write_bytes(b"unlisted synthetic data")

    class Child:
        returncode = 0

        def communicate(self, input=None, timeout=None):
            calls.append((input, timeout))

    def launch(command, **kwargs):
        launches.append((command, kwargs))
        return Child()

    monkeypatch.setattr(subprocess, "Popen", launch)
    result = invoke(inputs)
    assert result["outcome"] == "transfer_complete"
    assert result["sftp_rc"] == 0 and result["writer_started"] is False
    assert len(calls) == 1
    index_raw = (inputs[1] / "index.json").read_bytes()
    index = json.loads(index_raw)
    target = "/incoming/" + index["manifest_id"]
    assert calls[0] == ((
        f"mkdir {target}\nmkdir {target}/responses\n"
        f'put "responses/p1.body" {target}/responses/p1.body\n'
        f'put "responses/q1.body" {target}/responses/q1.body\n'
        f'put "index.json" {target}/.index.json.upload\n'
        f"rename {target}/.index.json.upload {target}/index.json\n"
    ).encode(), 30)
    command, kwargs = launches[0]
    assert command[:9] == ["/usr/bin/sftp", "-F", "/dev/null", "-b", "-", "-P", "22", "-i", str(inputs[2])]
    assert command[-1] == "cpbl393-receiver@45.76.100.29"
    options = command[10:-1:2]
    assert "StrictHostKeyChecking=yes" in options and "IdentityAgent=none" in options
    assert f'UserKnownHostsFile="{inputs[3]}"' in options
    assert kwargs["cwd"] == inputs[1] and kwargs["start_new_session"] is True
    assert kwargs["env"] == {"LANG": "C", "LC_ALL": "C"}
    assert kwargs["stdout"] == kwargs["stderr"] == subprocess.DEVNULL
    assert result["manifest_sha256"] == hashlib.sha256(inputs[0].read_bytes()).hexdigest()
    assert result["index_sha256"] == hashlib.sha256(index_raw).hexdigest()
    assert result["file_count"] == 3 and result["child_waited"] is True
    assert "虛構" not in json.dumps(result, ensure_ascii=False)


@pytest.mark.parametrize("invalid", ["manifest", "pin", "identity_mode"])
def test_precheck_failure_never_starts_transport(inputs, monkeypatch, invalid):
    if invalid == "manifest":
        inputs[0].write_bytes(b'{"schema":"not-the-independent-manifest"}')
    elif invalid == "pin":
        monkeypatch.setattr(sender, "HOST_KEY_SHA256", "SHA256:wrong")
    else:
        inputs[2].chmod(0o644)
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: pytest.fail("no transport allowed"))
    result = invoke(inputs)
    assert result["outcome"] == "precheck_failed" and result["sftp_rc"] is None
    assert result["writer_started"] is False


@pytest.mark.parametrize("field, spelling", [
    ("known_hosts", "%h"), ("identity_file", "%h"),
    ("known_hosts", "${HOSTNAME}"), ("identity_file", "${HOSTNAME}"),
])
def test_auth_path_expansion_is_rejected_even_when_literal_file_passes_checks(
    inputs, monkeypatch, field, spelling,
):
    manifest, bundle, identity, hosts = inputs
    original = hosts if field == "known_hosts" else identity
    literal = original.with_name(spelling)
    # This literal path really exists and passes the old pin/metadata checks.
    # It is a synthetic public hosts file or NOT-A-KEY text, never a real key.
    literal.write_bytes(original.read_bytes())
    literal.chmod(0o600)
    launches = []

    class Child:
        returncode = 0

        def communicate(self, **kwargs):
            pass

    def launch(*args, **kwargs):
        launches.append(args)
        return Child()

    monkeypatch.setattr(subprocess, "Popen", launch)
    args = {"identity_file": identity, "known_hosts": hosts, field: literal}
    result = sender.send_bundle(manifest, bundle, timeout=30, **args)
    assert result["outcome"] == "precheck_failed"
    assert result["sftp_rc"] is None and not launches


def test_native_failure_is_unknown_not_collision_and_never_retried(inputs, monkeypatch):
    launches = []

    class Child:
        returncode = 255

        def communicate(self, **kwargs):
            pass

    def launch(*args, **kwargs):
        launches.append(args)
        return Child()

    monkeypatch.setattr(subprocess, "Popen", launch)
    result = invoke(inputs)
    assert len(launches) == 1
    assert result["outcome"] == "partial_or_unknown" and result["sftp_rc"] == 255
    assert result["child_waited"] is True and result["writer_started"] is False


def test_timeout_reuses_existing_worker_wait_without_resending_batch(inputs, monkeypatch):
    sent, signals = [], []

    class Child:
        pid = 123456789  # fake; killpg is replaced below
        returncode = None

        def communicate(self, input=None, timeout=None):
            sent.append(input)
            if len(sent) == 1:
                raise subprocess.TimeoutExpired("synthetic", timeout)
            self.returncode = -15

    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: Child())
    monkeypatch.setattr(sender.fetch.os, "killpg", lambda pid, sig: signals.append((pid, sig)))
    result = invoke(inputs)
    assert len(sent) == 2 and sent[0] is not None and sent[1] is None
    assert len(signals) == 1 and signals[0][0] == Child.pid
    assert result["outcome"] == "partial_or_unknown" and result["sftp_rc"] == -15
    assert result["timed_out"] is True and result["child_waited"] is True


def test_cli_failure_is_safe_json_and_nonzero_without_loading_browser_or_db(tmp_path):
    secret = "synthetic-value-must-not-echo"
    result = subprocess.run([sys.executable, "-I", "-B", str(ENTRY), "--unknown", secret],
                            capture_output=True, timeout=5)
    assert result.returncode == 1 and not result.stderr
    assert secret.encode() not in result.stdout
    assert json.loads(result.stdout)["outcome"] == "precheck_failed"
    # Valid CLI syntax also executes only precheck when files are absent.
    result = subprocess.run([sys.executable, "-I", "-B", str(ENTRY), str(tmp_path / "absent"),
                             "--bundle", str(tmp_path), "--timeout", "10"],
                            capture_output=True, timeout=5)
    assert result.returncode == 1 and not result.stderr
    assert json.loads(result.stdout)["sftp_rc"] is None


def test_sender_matches_exact_frozen_receiver_contract():
    root = ENTRY.parent / "receiver-v1-candidate"
    for line in (root / "SHA256SUMS").read_text().splitlines():
        sha, name = line.split()
        assert hashlib.sha256((root / name).read_bytes()).hexdigest() == sha
    contract = json.loads((root / "receiver-contract.json").read_bytes())
    assert contract["interface"] == sender.INTERFACE
    assert contract["endpoint"] == {"host": sender.HOST, "port": sender.PORT,
                                    "host_key_type": "ssh-ed25519",
                                    "host_key_sha256": sender.HOST_KEY_SHA256}
    assert contract["identity_proposed"]["user"] == sender.USER
    assert contract["identity_proposed"]["pi_identity_file"] == str(sender.IDENTITY_FILE)
    assert contract["identity_proposed"]["pi_known_hosts_file"] == str(sender.KNOWN_HOSTS)
    assert contract["storage_proposed"]["sftp_root"] == sender.REMOTE_ROOT


def test_fetch_mode_uses_original_fetcher_before_the_single_verified_send(inputs, monkeypatch, capsys):
    order = []

    def original_fetch(argv):
        order.append(("fetch", argv))
        return 0  # The synthetic fixture represents this successful worker output.

    class Child:
        returncode = 0

        def communicate(self, **kwargs):
            order.append(("send", kwargs["input"]))

    monkeypatch.setattr(sender.fetch, "main", original_fetch)
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: Child())
    manifest, bundle, identity, hosts = inputs
    # Match the manifest ID as the real original worker does.
    target = bundle.with_name(json.loads(manifest.read_bytes())["manifest_id"])
    bundle.rename(target)
    rc = sender.main([str(manifest), "--bundle", str(target), "--fetch", "--timeout", "30",
                      "--identity-file", str(identity), "--known-hosts", str(hosts)])
    assert rc == 0
    assert order[0] == ("fetch", [str(manifest), "--out", str(target.parent)])
    assert [step[0] for step in order] == ["fetch", "send"]
    result = json.loads(capsys.readouterr().out)
    assert result["fetch_rc"] == 0 and result["outcome"] == "transfer_complete"
    assert result["manifest_sha256"] == hashlib.sha256(manifest.read_bytes()).hexdigest()


@pytest.mark.parametrize("fetch_rc", [3, 65, 124])
def test_fetch_failure_never_sends_or_falls_back_to_old_bundle(inputs, monkeypatch, capsys, fetch_rc):
    manifest, bundle, identity, hosts = inputs
    target = bundle.with_name(json.loads(manifest.read_bytes())["manifest_id"])
    bundle.rename(target)
    monkeypatch.setattr(sender.fetch, "main", lambda argv: fetch_rc)
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: pytest.fail("no send after failure"))
    rc = sender.main([str(manifest), "--bundle", str(target), "--fetch", "--timeout", "30",
                      "--identity-file", str(identity), "--known-hosts", str(hosts)])
    result = json.loads(capsys.readouterr().out)
    assert rc == 1 and result["fetch_rc"] == fetch_rc
    assert result["sftp_rc"] is None and result["outcome"] == "precheck_failed"


def test_fetch_mode_refuses_mismatched_destination_before_fetch(inputs, monkeypatch, capsys):
    monkeypatch.setattr(sender.fetch, "main", lambda argv: pytest.fail("wrong manifest ID"))
    manifest, bundle, _, _ = inputs
    assert sender.main([str(manifest), "--bundle", str(bundle), "--fetch", "--timeout", "30"]) == 1
    assert json.loads(capsys.readouterr().out)["sftp_rc"] is None


def test_fetch_mode_retains_original_existing_run_refusal(inputs, monkeypatch, capsys):
    manifest, bundle, identity, hosts = inputs
    target = bundle.with_name(json.loads(manifest.read_bytes())["manifest_id"])
    bundle.rename(target)
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: pytest.fail("no child for existing run"))
    rc = sender.main([str(manifest), "--bundle", str(target), "--fetch", "--timeout", "30",
                      "--identity-file", str(identity), "--known-hosts", str(hosts)])
    result = json.loads(capsys.readouterr().out)
    assert rc == 1 and result["fetch_rc"] == 65 and result["sftp_rc"] is None


def test_changed_manifest_after_fetch_is_rejected_by_existing_bundle_gate(inputs, monkeypatch, capsys):
    manifest, bundle, identity, hosts = inputs
    target = bundle.with_name(json.loads(manifest.read_bytes())["manifest_id"])
    bundle.rename(target)

    def changed_manifest(argv):
        manifest.write_bytes(manifest.read_bytes() + b"\n")
        return 0

    monkeypatch.setattr(sender.fetch, "main", changed_manifest)
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: pytest.fail("manifest hash mismatch"))
    rc = sender.main([str(manifest), "--bundle", str(target), "--fetch", "--timeout", "30",
                      "--identity-file", str(identity), "--known-hosts", str(hosts)])
    result = json.loads(capsys.readouterr().out)
    assert rc == 1 and result["fetch_rc"] == 0 and result["sftp_rc"] is None


def request_transport(monkeypatch, payload, *, rc=0):
    calls = []

    def launch(command, **kwargs):
        class Child:
            returncode = rc

            def communicate(self, input=None, timeout=None):
                calls.append((command, kwargs, input))
                parts = shlex.split(input.decode())
                if rc == 0:
                    (kwargs["cwd"] / parts[2]).write_bytes(payload)

        return Child()

    monkeypatch.setattr(subprocess, "Popen", launch)
    return calls


@pytest.fixture
def supply_inputs(inputs):
    manifest, bundle, _, _ = inputs
    parsed = json.loads(manifest.read_bytes())
    parsed["manifest_id"] = "scrape-daily-" + "a" * 20 + "-0001"
    now = dt.datetime.now(dt.UTC)
    parsed["window"] = {"start": (now - dt.timedelta(hours=1)).isoformat(),
                        "end": (now + dt.timedelta(hours=1)).isoformat()}
    raw = json.dumps(parsed).encode()
    manifest.write_bytes(raw)
    index_path = bundle / "index.json"
    index = json.loads(index_path.read_bytes())
    index.update(manifest_id=parsed["manifest_id"], manifest_sha256=hashlib.sha256(raw).hexdigest())
    index_path.write_text(json.dumps(index))
    return inputs


def test_request_reader_gets_one_fixed_job_manifest_with_separate_identity(supply_inputs, monkeypatch):
    manifest, bundle, identity, hosts = supply_inputs
    raw = manifest.read_bytes()
    calls = request_transport(monkeypatch, raw)
    result = sender.receive_request("scrape-daily", bundle, identity_file=identity,
                                    known_hosts=hosts, timeout=30)
    assert result["outcome"] == "request_received"
    assert result["manifest_sha256"] == hashlib.sha256(raw).hexdigest()
    received = Path(result["manifest_path"])
    assert received.read_bytes() == raw and received.stat().st_mode & 0o777 == 0o600
    assert received.parent.stat().st_mode & 0o777 == 0o700
    assert len(calls) == 1
    command, kwargs, batch = calls[0]
    assert command[-1] == "cpbl393-request-ro@45.76.100.29"
    assert str(identity) in command and kwargs["cwd"] == bundle
    assert shlex.split(batch.decode())[:2] == ["get", "/requests/scrape-daily.json"]
    assert result["request_sftp_rc"] == 0 and result["request_child_waited"] is True


@pytest.mark.parametrize("job", ["../secret", "alert-watch"])
def test_request_reader_rejects_path_injection_before_transport(inputs, monkeypatch, job):
    _, bundle, identity, hosts = inputs
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: pytest.fail("invalid job"))
    result = sender.receive_request(job, bundle, identity_file=identity,
                                    known_hosts=hosts, timeout=30)
    assert result["outcome"] == "precheck_failed" and result["request_sftp_rc"] is None


def test_request_transport_failure_retains_partial_and_never_retries(inputs, monkeypatch):
    _, bundle, identity, hosts = inputs
    calls = request_transport(monkeypatch, b"", rc=255)
    result = sender.receive_request("scrape-daily", bundle, identity_file=identity,
                                    known_hosts=hosts, timeout=30)
    assert len(calls) == 1 and result["outcome"] == "partial_or_unknown"
    assert result["request_sftp_rc"] == 255 and result["request_child_waited"] is True
    assert Path(result["manifest_path"]).is_file()


@pytest.mark.parametrize("payload", [b"not JSON", b"x" * (1024 * 1024 + 1)],
                         ids=["invalid-json", "oversized"])
def test_invalid_request_is_not_treated_as_a_new_bundle(inputs, monkeypatch, payload):
    _, bundle, identity, hosts = inputs
    calls = request_transport(monkeypatch, payload)
    result = sender.receive_request("scrape-daily", bundle, identity_file=identity,
                                    known_hosts=hosts, timeout=30)
    assert len(calls) == 1 and result["outcome"] == "precheck_failed"
    assert result["request_sftp_rc"] == 0 and "manifest_id" not in result


def test_completion_receipt_is_a_separate_metadata_batch_after_raw_wait(inputs, monkeypatch):
    _, bundle, identity, hosts = inputs
    raw_result = {"outcome": "transfer_complete", "sftp_rc": 0, "child_waited": True,
                  "manifest_id": "fixture-393", "manifest_sha256": "a" * 64,
                  "index_sha256": "b" * 64}
    calls = []

    def launch(command, **kwargs):
        class Child:
            returncode = 0

            def communicate(self, input=None, timeout=None):
                calls.append((command, input))
                first, last = input.decode().splitlines()
                local = kwargs["cwd"] / shlex.split(first)[1]
                receipt = json.loads(local.read_bytes())
                assert receipt == {"manifest_id": "fixture-393", "manifest_sha256": "a" * 64,
                                   "index_sha256": "b" * 64, "raw_batch_rc": 0,
                                   "raw_batch_waited": True}
                assert shlex.split(first)[2] == "/incoming/fixture-393/.delivery.json.upload"
                assert last == ("rename /incoming/fixture-393/.delivery.json.upload "
                                "/incoming/fixture-393/delivery.json")

        return Child()

    monkeypatch.setattr(subprocess, "Popen", launch)
    result = sender.publish_transfer_receipt(bundle, raw_result, identity_file=identity,
                                             known_hosts=hosts, timeout=30)
    assert len(calls) == 1 and calls[0][0][-1] == "cpbl393-receiver@45.76.100.29"
    assert result["receipt_published"] is True and result["receipt_sftp_rc"] == 0
    assert result["receipt_child_waited"] is True and result["receipt_bytes"] < 1024


@pytest.mark.parametrize("change", [
    {"sftp_rc": 255}, {"sftp_rc": None}, {"child_waited": False},
    {"outcome": "partial_or_unknown"},
])
def test_completion_receipt_cannot_certify_failed_or_unwaited_raw(inputs, monkeypatch, change):
    _, bundle, identity, hosts = inputs
    raw_result = {"outcome": "transfer_complete", "sftp_rc": 0, "child_waited": True,
                  "manifest_id": "fixture-393", "manifest_sha256": "a" * 64,
                  "index_sha256": "b" * 64, **change}
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: pytest.fail("raw not complete"))
    result = sender.publish_transfer_receipt(bundle, raw_result, identity_file=identity,
                                             known_hosts=hosts, timeout=30)
    assert result["receipt_published"] is False and result["receipt_sftp_rc"] is None


def test_request_cli_runs_get_fetch_raw_wait_then_receipt_without_manual_bundle(supply_inputs, monkeypatch, capsys):
    manifest, source_bundle, identity, hosts = supply_inputs
    out = source_bundle.parent / "new-out"
    out.mkdir(mode=0o700)
    events = []
    raw = manifest.read_bytes()

    def original_fetch(argv):
        events.append("fetch")
        assert Path(argv[0]).read_bytes() == raw
        shutil.copytree(source_bundle, out / json.loads(raw)["manifest_id"])
        return 0

    def launch(command, **kwargs):
        class Child:
            returncode = 0

            def communicate(self, input=None, timeout=None):
                text = input.decode()
                if text.startswith("get "):
                    assert command[-1] == "cpbl393-request-ro@45.76.100.29"
                    events.append("get")
                    (kwargs["cwd"] / shlex.split(text)[2]).write_bytes(raw)
                elif text.startswith("mkdir "):
                    events.append("raw_wait")
                else:
                    assert events == ["get", "fetch", "raw_wait"]
                    events.append("receipt")

        return Child()

    monkeypatch.setattr(sender.fetch, "main", original_fetch)
    monkeypatch.setattr(subprocess, "Popen", launch)
    rc = sender.main(["--request-job", "scrape-daily", "--out", str(out), "--timeout", "30",
                      "--request-identity-file", str(identity), "--identity-file", str(identity),
                      "--known-hosts", str(hosts)])
    result = json.loads(capsys.readouterr().out)
    assert rc == 0 and events == ["get", "fetch", "raw_wait", "receipt"]
    assert result["outcome"] == "transfer_complete" and result["receipt_published"] is True
    assert result["request_sftp_rc"] == result["sftp_rc"] == result["receipt_sftp_rc"] == 0
    assert result["request_manifest_sha256"] == result["manifest_sha256"]


def test_expired_downloaded_request_does_not_start_browser_or_send_old_data(supply_inputs, monkeypatch, capsys):
    manifest, bundle, identity, hosts = supply_inputs
    out = bundle.parent / "new-out"
    out.mkdir(mode=0o700)
    parsed = json.loads(manifest.read_bytes())
    parsed["window"] = {"start": "2000-01-01T00:00:00+00:00",
                        "end": "2000-01-01T00:01:00+00:00"}
    calls = request_transport(monkeypatch, json.dumps(parsed).encode())
    rc = sender.main(["--request-job", "scrape-daily", "--out", str(out), "--timeout", "30",
                      "--request-identity-file", str(identity), "--identity-file", str(identity),
                      "--known-hosts", str(hosts)])
    result = json.loads(capsys.readouterr().out)
    assert rc == 1 and result["fetch_rc"] == 65 and len(calls) == 1
    assert result["request_sftp_rc"] == 0 and result["sftp_rc"] is None


def test_request_for_another_job_is_rejected_after_download(inputs, monkeypatch):
    manifest, bundle, identity, hosts = inputs
    request_transport(monkeypatch, manifest.read_bytes())  # fixture-393, not scrape-daily-...
    result = sender.receive_request("scrape-daily", bundle, identity_file=identity,
                                    known_hosts=hosts, timeout=30)
    assert result["request_sftp_rc"] == 0 and result["outcome"] == "precheck_failed"
    assert "manifest_id" not in result


def test_sender_binds_downloaded_request_hash_before_any_raw_transfer(inputs, monkeypatch):
    manifest, bundle, identity, hosts = inputs
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: pytest.fail("request hash changed"))
    result = sender.send_bundle(manifest, bundle, identity_file=identity, known_hosts=hosts,
                                timeout=30, expected_manifest_sha256="0" * 64)
    assert result["outcome"] == "precheck_failed" and result["sftp_rc"] is None


def test_failed_metadata_publication_retains_receipt_without_retry(inputs, monkeypatch):
    _, bundle, identity, hosts = inputs
    raw_result = {"outcome": "transfer_complete", "sftp_rc": 0, "child_waited": True,
                  "manifest_id": "fixture-393", "manifest_sha256": "a" * 64,
                  "index_sha256": "b" * 64}
    calls = []

    class Child:
        returncode = 255

        def communicate(self, **kwargs):
            calls.append(kwargs)

    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: Child())
    result = sender.publish_transfer_receipt(bundle, raw_result, identity_file=identity,
                                             known_hosts=hosts, timeout=30)
    assert len(calls) == 1 and result["receipt_published"] is False
    assert result["receipt_sftp_rc"] == 255 and result["receipt_child_waited"] is True
    assert Path(result["receipt_path"]).is_file() and raw_result["sftp_rc"] == 0


def test_three_job_workers_share_one_nonblocking_lock_before_any_transport(inputs, monkeypatch, capsys):
    _, bundle, _, hosts = inputs
    lock = bundle / ".worker.lock"
    lock.write_bytes(b"")
    lock.chmod(0o600)
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: pytest.fail("worker already active"))
    with lock.open("r+") as held:
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert sender.main(["--request-job", "postseason-evening", "--out", str(bundle),
                            "--timeout", "30", "--known-hosts", str(hosts)]) == 0
    assert json.loads(capsys.readouterr().out)["outcome"] == "busy"


def test_global_cooldown_and_unknown_exit_block_all_three_jobs(inputs, monkeypatch, capsys):
    _, bundle, _, hosts = inputs
    until = int(time.time()) + 1200
    cooldown = bundle / ".cooldown-until"
    cooldown.write_text(str(until) + "\n")
    cooldown.chmod(0o600)
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: pytest.fail("cooldown forbids activity"))
    assert sender.main(["--request-job", "scrape-daily", "--out", str(bundle),
                        "--timeout", "30", "--known-hosts", str(hosts)]) == 0
    assert json.loads(capsys.readouterr().out)["outcome"] == "cooldown"
    blocked = bundle / ".blocked"
    blocked.write_text("raw_exit_unknown\n")
    blocked.chmod(0o600)
    assert sender.main(["--request-job", "weekly-box-revisions", "--out", str(bundle),
                        "--timeout", "30", "--known-hosts", str(hosts)]) == 1
    assert json.loads(capsys.readouterr().out)["outcome"] == "blocked"


def test_failed_fetch_claim_is_not_retried_after_cooldown(supply_inputs, monkeypatch, capsys):
    manifest, bundle, identity, hosts = supply_inputs
    out = bundle.parent / "worker-state"
    out.mkdir(mode=0o700)
    parsed = json.loads(manifest.read_bytes())
    reads, fetches = [], []

    def receive(*args, **kwargs):
        reads.append(args)
        return {"outcome": "request_received", "job": "scrape-daily",
                "manifest_path": str(manifest), "manifest_id": parsed["manifest_id"],
                "manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
                "request_sftp_rc": 0, "request_child_waited": True}

    def failed_fetch(argv):
        fetches.append(argv)
        return 3

    monkeypatch.setattr(sender, "receive_request", receive)
    monkeypatch.setattr(sender.fetch, "main", failed_fetch)
    argv = ["--request-job", "scrape-daily", "--out", str(out), "--timeout", "30",
            "--identity-file", str(identity), "--known-hosts", str(hosts)]
    before = int(time.time())
    assert sender.main(argv) == 1
    assert json.loads(capsys.readouterr().out)["fetch_rc"] == 3
    assert int((out / ".cooldown-until").read_text()) >= before + 1200
    assert sender.main(argv) == 0
    assert json.loads(capsys.readouterr().out)["outcome"] == "cooldown"
    assert len(reads) == len(fetches) == 1
    (out / ".cooldown-until").write_text("0\n")  # expire only this synthetic state
    assert sender.main(argv) == 0
    assert json.loads(capsys.readouterr().out)["outcome"] == "already_attempted"
    assert len(reads) == 2 and len(fetches) == 1


def test_bounded_service_counts_unavailable_reads_and_stops_at_read_limit(inputs, monkeypatch, capsys):
    _, out, _, _ = inputs
    tick = [0.0]
    calls = []
    monkeypatch.setattr(sender.time, "monotonic", lambda: tick[0])
    monkeypatch.setattr(sender.time, "sleep", lambda delay: tick.__setitem__(0, tick[0] + delay))

    def unavailable(args, **kwargs):
        calls.append((args, kwargs))
        return 1, {"outcome": "partial_or_unknown", "request_started": True,
                   "request_sftp_rc": 1, "request_child_waited": True, "timed_out": False}

    monkeypatch.setattr(sender, "_run_once", unavailable)
    rc = sender.main(["--serve-job", "scrape-daily", "--out", str(out), "--timeout", "30",
                      "--max-seconds", "100", "--discovery-seconds", "100",
                      "--max-reads", "3", "--max-operations", "10"])
    result = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert rc == 75 and len(calls) == 3
    assert result["outcome"] == "read_budget_exhausted" and result["request_clients"] == 3
    assert result["raw_clients"] == result["receipt_clients"] == 0


def test_bounded_service_never_adopts_a_different_run_prefix(inputs, monkeypatch, capsys):
    _, out, _, _ = inputs
    prefix = "scrape-daily-" + "a" * 20
    another = "scrape-daily-" + "b" * 20
    end = (dt.datetime.now(dt.UTC) + dt.timedelta(seconds=90)).isoformat()
    rows = [
        (0, {"outcome": "transfer_complete", "request_prefix": prefix,
             "request_window_end": end, "request_started": True, "raw_started": True,
             "request_child_waited": True,
             "receipt_started": True, "request_operations": 2, "operations_reserved": 2}),
        (0, {"outcome": "already_attempted", "request_prefix": prefix,
             "request_window_end": end, "request_started": True, "request_child_waited": True,
             "operations_reserved": 2}),
        (0, {"outcome": "prefix_changed", "request_prefix": another,
             "request_window_end": end, "request_started": True}),
    ]
    seen = []
    monkeypatch.setattr(sender.time, "sleep", lambda delay: None)

    def next_batch(args, *, expected_prefix=None):
        assert args.timeout == 30  # discovery only narrows the GET, not later data/receipt work
        if expected_prefix is None:
            assert 0 < args.request_timeout <= 20
        else:
            assert args.serve_deadline_epoch == dt.datetime.fromisoformat(end).timestamp()
        seen.append(expected_prefix)
        return rows.pop(0)

    monkeypatch.setattr(sender, "_run_once", next_batch)
    rc = sender.main(["--serve-job", "scrape-daily", "--out", str(out), "--timeout", "30",
                      "--max-seconds", "100", "--discovery-seconds", "30",
                      "--max-reads", "5", "--max-operations", "4"])
    result = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert rc == 76 and seen == [None, prefix, prefix]
    assert result["outcome"] == "prefix_changed" and result["batches_delivered"] == 1
    assert result["raw_clients"] == result["receipt_clients"] == 1
    assert result["operations_reserved"] == 2


def test_attempt_operation_budget_survives_a_new_worker_process(inputs):
    _, out, _, _ = inputs
    prefix = "scrape-daily-" + "a" * 20
    assert sender._claim_attempt(out, prefix + "-0001", "a" * 64, 2, 2) == (True, 2)
    assert sender._claim_attempt(out, prefix + "-0001", "a" * 64, 2, 2) == (False, 2)
    with pytest.raises(ValueError, match="operation_budget"):
        sender._claim_attempt(out, prefix + "-0002", "b" * 64, 1, 2)


@pytest.mark.parametrize("failure", ["wait", "exit_code"])
def test_unknown_native_request_exit_blocks_later_activity(inputs, monkeypatch, capsys, failure):
    _, out, identity, hosts = inputs
    launches = []

    class Child:
        returncode = None

        def communicate(self, **kwargs):
            if failure == "wait":
                raise RuntimeError("synthetic native wait failure")

    def launch(*args, **kwargs):
        launches.append(args)
        return Child()

    monkeypatch.setattr(subprocess, "Popen", launch)
    argv = ["--request-job", "scrape-daily", "--out", str(out), "--timeout", "30",
            "--request-identity-file", str(identity), "--known-hosts", str(hosts)]
    assert sender.main(argv) == 1
    first = json.loads(capsys.readouterr().out)
    assert first["request_sftp_rc"] is None
    assert first["request_child_waited"] is (failure != "wait")
    assert (out / ".blocked").is_file()
    assert sender.main(argv) == 1 and len(launches) == 1
    assert json.loads(capsys.readouterr().out)["outcome"] == "blocked"


def test_next_worker_waits_one_second_after_previous_source_return(inputs, monkeypatch):
    _, out, _, _ = inputs
    ended = out / ".last-source-end"
    ended.write_text("100.25\n")
    ended.chmod(0o600)
    sleeps = []
    monkeypatch.setattr(sender.time, "time", lambda: 100.5)
    monkeypatch.setattr(sender.time, "sleep", sleeps.append)
    sender._source_gap(out)
    assert sleeps == [0.75]


def test_single_batch_mode_does_not_silently_ignore_service_time_limits(inputs, monkeypatch, capsys):
    _, out, identity, hosts = inputs
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: pytest.fail("invalid service flags"))
    assert sender.main(["--request-job", "scrape-daily", "--out", str(out), "--timeout", "30",
                        "--max-seconds", "30", "--request-identity-file", str(identity),
                        "--known-hosts", str(hosts)]) == 1
    assert json.loads(capsys.readouterr().out)["outcome"] == "precheck_failed"


def test_discovery_stops_on_ssh_failure_instead_of_repeating_auth_attempts(inputs, monkeypatch, capsys):
    _, out, _, _ = inputs
    calls = []

    def failed_connection(args, **kwargs):
        calls.append(args)
        return 1, {"outcome": "partial_or_unknown", "request_started": True,
                   "request_sftp_rc": 255, "request_child_waited": True}

    monkeypatch.setattr(sender, "_run_once", failed_connection)
    monkeypatch.setattr(sender.time, "sleep", lambda delay: None)
    rc = sender.main(["--serve-job", "scrape-daily", "--out", str(out), "--timeout", "30",
                      "--max-seconds", "100", "--discovery-seconds", "100",
                      "--max-reads", "3", "--max-operations", "10"])
    result = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert rc == 1 and len(calls) == 1
    assert result["outcome"] == "request_failed" and result["request_clients"] == 1


def test_discovery_stops_when_timed_out_client_exits_one_after_term(inputs, monkeypatch, capsys):
    _, out, identity, hosts = inputs
    launches, signals, sleeps = [], [], []

    class Child:
        pid = 123456789  # killpg is replaced; no real process is launched or signalled.
        returncode = None

        def __init__(self):
            self.waits = 0

        def communicate(self, input=None, timeout=None):
            self.waits += 1
            if self.waits == 1:
                raise subprocess.TimeoutExpired("synthetic SFTP", timeout)
            assert input is None
            self.returncode = 1  # The real timeout helper must preserve this native exit.

    def launch(*args, **kwargs):
        child = Child()
        launches.append(child)
        return child

    monkeypatch.setattr(subprocess, "Popen", launch)
    monkeypatch.setattr(sender.fetch.os, "killpg", lambda pid, sig: signals.append((pid, sig)))
    monkeypatch.setattr(sender.time, "sleep", sleeps.append)
    rc = sender.main(["--serve-job", "scrape-daily", "--out", str(out), "--timeout", "30",
                      "--max-seconds", "100", "--discovery-seconds", "100",
                      "--max-reads", "3", "--max-operations", "10",
                      "--request-identity-file", str(identity), "--known-hosts", str(hosts)])
    rows = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert rc == 1 and len(launches) == 1 and len(signals) == 1 and not sleeps
    assert rows[0]["request_sftp_rc"] == 1 and rows[0]["request_child_waited"] is True
    assert rows[0]["timed_out"] is True
    assert rows[-1]["outcome"] == "request_failed" and rows[-1]["request_clients"] == 1
    assert rows[-1]["raw_clients"] == rows[-1]["receipt_clients"] == 0
    assert not (out / ".blocked").exists()  # Known exit; the unknown-exit policy is unchanged.
