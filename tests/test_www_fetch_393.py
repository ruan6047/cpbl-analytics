"""Offline WP3 contract tests; fixtures do not establish real-network availability."""

import datetime as dt
import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

from cpbl.ingest import www_fetch as fetch

NOW = dt.datetime(2026, 11, 1, 12, tzinfo=dt.UTC)
HTML = "<html>中文<script>const c={RequestVerificationToken:'fixture-only-token'};</script></html>"
BODY = '{"Success":true,"GameDatas":"[{\\"name\\":\\"虛構\\"}]"}'


def manifest():
    return {
        "schema": "cpbl-www-manifest/1",
        "manifest_id": "fixture-393",
        "window": {"start": "2026-11-01T11:00:00+00:00", "end": "2026-11-01T13:00:00+00:00"},
        "min_gap_s": 1.0,
        "max_requests": 2,
        "max_duration_s": 60,
        "requests": [
            {"id": "p1", "op": "page", "path": "/schedule", "require": "RequestVerificationToken"},
            {
                "id": "q1",
                "op": "post",
                "page": "p1",
                "api": "/schedule/getgamedatas",
                "form": {"calendar": "2026/01/01", "location": "", "kindCode": "A"},
                "headers": {"RequestVerificationToken": {"$token": "A"}},
            },
        ],
    }


def raw(value=None):
    return json.dumps(value or manifest(), ensure_ascii=False).encode()


class FixtureDriver:
    def __init__(self, *, text=BODY, failure=None):
        self.text, self.failure = text, failure
        self.calls, self.closed = [], False

    def page(self, path, wait, require):
        self.calls.append(("page", path, wait, require))
        return 200, HTML

    def post(self, page, api, form, headers):
        self.calls.append(("post", page, api, form, headers))
        if self.failure:
            raise self.failure("secret-fixture-value must not appear in metadata")
        return 200, self.text

    def observation(self):
        return {
            "request_events": 112,
            "response_events": 112,
            "redirect_responses": 10,
            "page_websocket_events": 0,
            "coverage": "SDK-visible lower bound",
        }

    def close(self):
        self.closed = True


def execute(tmp_path, value=None, driver=None, **kwargs):
    driver = driver or FixtureDriver()
    index = fetch.run(
        raw(value), tmp_path, lambda: driver, now=lambda: NOW, sleep=lambda _s: None, **kwargs
    )
    return index, driver, tmp_path / (value or manifest())["manifest_id"]


def test_private_raw_bundle_preserves_original_text_and_binds_manifest(tmp_path):
    index, driver, bundle = execute(tmp_path)
    verified = fetch.verify_bundle(bundle, raw())
    bodies = {row["id"]: fetch.read_response(bundle, row) for row in verified["entries"]}
    assert index["complete"] and verified == index and driver.closed
    assert bodies == {"p1": HTML.encode(), "q1": BODY.encode()}
    assert index["manifest_sha256"] == hashlib.sha256(raw()).hexdigest()
    assert index["requests_sent"] == 2
    assert index["observed"]["request_events"] == 112  # not a transport cap of two or fifty
    assert driver.calls[1][3] == {"calendar": "2026/01/01", "location": "", "kindCode": "A"}
    assert driver.calls[1][4] == {"RequestVerificationToken": "fixture-only-token"}
    serialized = json.dumps(index)
    assert "fixture-only-token" not in serialized and "headers" not in serialized
    assert bundle.stat().st_mode & 0o777 == 0o700
    assert all(p.stat().st_mode & 0o777 == 0o600 for p in bundle.rglob("*") if p.is_file())


@pytest.mark.parametrize(
    "change",
    [
        lambda m: m["requests"][0].update(path="//other.example/path"),
        lambda m: m["requests"][1].update(headers={"Cookie": "private"}),
        lambda m: m["requests"][1].update(headers={"RequestVerificationToken": "literal-secret"}),
        lambda m: m["requests"][1].update(page="missing"),
        lambda m: m.update(max_requests=True),
        lambda m: m.update(min_gap_s=float("nan")),
        lambda m: m.update(max_duration_s=0),
    ],
)
def test_invalid_manifest_is_rejected_before_any_session(change, tmp_path):
    m = manifest()
    change(m)
    with pytest.raises(fetch.ManifestError):
        fetch.run(
            raw(m), tmp_path, lambda: pytest.fail("must not create a session"), now=lambda: NOW
        )
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("damage", ["body", "size", "path", "manifest"])
def test_consumer_rejects_corrupt_or_mismatched_bundle(tmp_path, damage):
    _, _, bundle = execute(tmp_path)
    supplied = raw()
    if damage == "body":
        (bundle / "responses/q1.body").write_bytes(b"changed")
    elif damage == "manifest":
        m = manifest()
        m["requests"][1]["form"]["calendar"] = "2025/01/01"
        supplied = raw(m)
    else:
        index = json.loads((bundle / "index.json").read_bytes())
        index["entries"][1]["bytes" if damage == "size" else "body"] = (
            999 if damage == "size" else "../outside"
        )
        (bundle / "index.json").write_text(json.dumps(index))
    with pytest.raises(fetch.BundleError):
        fetch.verify_bundle(bundle, supplied)


def test_timeout_retains_completed_prefix_and_does_not_retry_or_log_exception(tmp_path):
    index, driver, bundle = execute(tmp_path, driver=FixtureDriver(failure=TimeoutError))
    assert not index["complete"] and index["stopped"]["signal"] == "operation_error:TimeoutError"
    assert len(driver.calls) == 2 and driver.closed
    assert "secret-fixture-value" not in (bundle / "index.json").read_text()
    assert (bundle / "responses/p1.body").read_bytes() == HTML.encode()
    with pytest.raises(fetch.BundleError):
        fetch.verify_bundle(bundle, raw())
    verified = fetch.verify_bundle(bundle, raw(), require_complete=False)
    bodies = {
        row["id"]: fetch.read_response(bundle, row) for row in verified["entries"] if "body" in row
    }
    assert bodies == {"p1": HTML.encode()}


def test_oversized_response_stops_with_raw_prefix_intact(tmp_path, monkeypatch):
    monkeypatch.setattr(fetch, "MAX_BODY_BYTES", len(HTML.encode()) + 1)
    index, driver, bundle = execute(tmp_path, driver=FixtureDriver(text='"' + "x" * 500 + '"'))
    assert not index["complete"] and index["stopped"]["signal"] == "body_size_limit"
    assert not (bundle / "responses/q1.body").exists() and driver.closed


def test_existing_bundle_is_never_overwritten_or_restarted(tmp_path):
    _, _, bundle = execute(tmp_path)
    original = (bundle / "index.json").read_bytes()
    with pytest.raises(FileExistsError):
        fetch.run(raw(), tmp_path, lambda: pytest.fail("must not start"), now=lambda: NOW)
    assert (bundle / "index.json").read_bytes() == original


def test_wait_that_crosses_window_does_not_start_next_operation(tmp_path):
    seconds = [0]

    def sleep(_s):
        seconds[0] += 7200

    index = fetch.run(
        raw(),
        tmp_path,
        lambda: FixtureDriver(),
        now=lambda: NOW + dt.timedelta(seconds=seconds[0]),
        clock=lambda: 0,
        sleep=sleep,
    )
    assert not index["complete"] and index["requests_sent"] == 1


def test_check_is_zero_network_and_does_not_create_outputs(tmp_path, monkeypatch, capsys):
    path = tmp_path / "manifest.json"
    path.write_bytes(raw())
    monkeypatch.setattr(fetch, "OriginalSessionDriver", lambda *a: pytest.fail("no browser"))
    assert fetch.main([str(path), "--out", str(tmp_path / "out"), "--check"]) == 0
    assert json.loads(capsys.readouterr().out)["ok"] and not (tmp_path / "out").exists()


def test_original_session_adapter_preserves_text_and_mature_retry_behavior():
    source = Path(__file__).resolve().parents[1] / "src/cpbl/ingest/_browser.py"
    spec = importlib.util.spec_from_file_location("original_browser_fixture_393", source)
    original = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(original)

    class Context:
        def on(self, *_args):
            pass

        def close(self):
            pass

    class Page:
        def __init__(self):
            self.posts, self.navigations, self.scripts = 0, [], []

        def on(self, *_args):
            pass

        def goto(self, url, **_kwargs):
            self.navigations.append(url)

        def wait_for_timeout(self, _ms):
            pass

        def content(self):
            return HTML

        def evaluate(self, script, values):
            self.posts += 1
            self.scripts.append(script)
            assert values["headers"]["RequestVerificationToken"] == "fixture-only-token"
            return {"status": 428 if self.posts == 1 else 200, "text": BODY}

    s = original._Session.__new__(original._Session)
    s._page = Page()
    s._ctx = Context()
    s._loaded = None
    s._defer_marks = False
    s._browser = None
    s._pw = type("PW", (), {"stop": lambda self: None})()
    adapter = fetch.OriginalSessionDriver(session=s)
    assert adapter.page("/schedule", "networkidle", "RequestVerificationToken")[1] == HTML
    assert adapter.post(
        "/schedule",
        "/schedule/getgamedatas",
        {"kindCode": "A"},
        {"RequestVerificationToken": "fixture-only-token"},
    ) == (200, BODY)
    assert s._page.posts == 2 and s._page.scripts == [original._JS_POST, original._JS_POST]
    assert (
        len(s._page.navigations) == 2
    )  # mature internal recovery is retained, not a new outer retry
    adapter.close()


def test_standard_worker_deadline_terminates_owned_process_only():
    child = subprocess.Popen(
        [sys.executable, "-I", "-B", "-c", "import time;time.sleep(20)"],
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    rc, timed_out = fetch.wait_worker(child, 0.05)
    assert timed_out and rc != 0 and child.poll() is not None


def test_consumer_rejects_symlink_and_secret_metadata(tmp_path):
    _, _, bundle = execute(tmp_path)
    index_path = bundle / "index.json"
    index = json.loads(index_path.read_bytes())
    index["headers"] = {"RequestVerificationToken": "synthetic-not-real"}
    index_path.write_text(json.dumps(index))
    with pytest.raises(fetch.BundleError):
        fetch.verify_bundle(bundle, raw())
    index.pop("headers")
    index_path.write_text(json.dumps(index))
    # Replace only the fixture's own response, preserving its original bytes separately.
    body = bundle / "responses/q1.body"
    saved = bundle / "responses/saved.body"
    body.rename(saved)
    body.symlink_to(saved)
    with pytest.raises(fetch.BundleError):
        fetch.verify_bundle(bundle, raw())


def cli_source(tmp_path, *, hang=False, check_env=False):
    source = tmp_path / "synthetic_session.py"
    source.write_text(
        "import time\n"
        + ("import os\nassert 'DATABASE_URL' not in os.environ\n" if check_env else "")
        + "class Events:\n def on(self,*a): pass\n"
        "class Session:\n _ctx=Events()\n _page=Events()\n"
        f" def page_html(self,*a,**k): {'time.sleep(20);' if hang else ''}return {HTML!r}\n"
        f" def post(self,*a,**k): return 200,{BODY!r}\n"
        " def close(self): pass\n"
        "def session(): return Session()\n"
    )
    return source


def live_window_manifest(duration=10):
    m = manifest()
    current = dt.datetime.now(dt.UTC)
    m["window"] = {
        "start": (current - dt.timedelta(minutes=1)).isoformat(),
        "end": (current + dt.timedelta(minutes=2)).isoformat(),
    }
    m["max_duration_s"] = duration
    return m


def test_standalone_cli_produces_verifiable_bundle_without_cpbl_or_network(tmp_path):
    m = live_window_manifest()
    path = tmp_path / "manifest.json"
    path.write_bytes(raw(m))
    source = cli_source(tmp_path, check_env=True)
    entry = Path(__file__).resolve().parents[1] / "ops/pi-fetcher/cpbl_pi_fetch.py"
    out = tmp_path / "private-out"
    command = [
        sys.executable,
        "-I",
        "-B",
        str(entry),
        str(path),
        "--out",
        str(out),
        "--browser-source",
        str(source),
    ]
    result = subprocess.run(command, capture_output=True, timeout=15)
    assert result.returncode == 0, result.stdout
    assert json.loads(result.stdout)["complete"]
    index = fetch.verify_bundle(out / m["manifest_id"], raw(m))
    assert fetch.read_response(out / m["manifest_id"], index["entries"][1]) == BODY.encode()
    assert "fixture-only-token" not in result.stdout.decode() and not result.stderr


def test_standalone_cli_timeout_keeps_partial_index(tmp_path):
    m = live_window_manifest(0.7)
    path = tmp_path / "manifest.json"
    path.write_bytes(raw(m))
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            fetch.__file__,
            str(path),
            "--out",
            str(tmp_path / "out"),
            "--browser-source",
            str(cli_source(tmp_path, hang=True)),
        ],
        capture_output=True,
        timeout=12,
    )
    assert result.returncode == 124 and json.loads(result.stdout)["stopped"] == "run_timeout"
    index = json.loads((tmp_path / "out" / m["manifest_id"] / "index.json").read_bytes())
    assert not index["complete"] and index["stopped"]["signal"] == "run_timeout"


def test_worker_uses_frozen_manifest_bytes_not_mutable_input_path(tmp_path):
    m = live_window_manifest()
    nonexistent = tmp_path / "source-manifest-no-longer-present.json"
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            fetch.__file__,
            str(nonexistent),
            "--out",
            str(tmp_path / "out"),
            "--browser-source",
            str(cli_source(tmp_path)),
            "--_worker",
        ],
        input=raw(m),
        capture_output=True,
        timeout=10,
    )
    assert result.returncode == 0
    assert (
        fetch.verify_bundle(tmp_path / "out" / m["manifest_id"], raw(m))["manifest_sha256"]
        == hashlib.sha256(raw(m)).hexdigest()
    )
