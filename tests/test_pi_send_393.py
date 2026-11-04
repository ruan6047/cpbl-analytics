"""Only the new sender boundary; synthetic files and a process double, no SFTP server."""

import base64
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
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
