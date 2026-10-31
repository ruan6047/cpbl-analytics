"""#393 WP4：虛構 bundle → 回放 session → 原 fetch_year；零官網、零 DB。"""

import hashlib
import json
import re
import shutil
from pathlib import Path

import pytest

from cpbl.ingest import _browser, _replay, cpbl_site, www_fetch

FIXTURE = Path(__file__).parent / "fixtures" / "replay_393"


@pytest.fixture
def candidate(tmp_path):
    shutil.copytree(FIXTURE, tmp_path / "candidate")
    return tmp_path / "candidate"


@pytest.fixture(autouse=True)
def isolate_replay_cache():
    _replay.replay_session.cache_clear()
    yield
    _replay.replay_session.cache_clear()


def rewrite_json(path, change):
    obj = json.loads(path.read_bytes())
    change(obj)
    path.write_text(json.dumps(obj))


def update_body(root, rid, text):
    raw = text.encode("utf-8")
    (root / f"bundle/responses/{rid}.body").write_bytes(raw)

    def update(index):
        entry = next(e for e in index["entries"] if e["id"] == rid)
        entry.update(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())

    rewrite_json(root / "bundle/index.json", update)


def activate(monkeypatch, root):
    def forbidden_browser():
        raise AssertionError("回放模式不得啟動 Playwright 或 fallback")

    monkeypatch.setattr(_browser, "_Session", forbidden_browser)
    monkeypatch.setenv("CPBL_REPLAY_MANIFEST", str(root / "manifest.json"))
    monkeypatch.setenv("CPBL_REPLAY_BUNDLE", str(root / "bundle"))


def test_bundle_reaches_existing_schedule_parser(monkeypatch):
    def forbidden_browser():
        raise AssertionError("回放模式不得啟動 Playwright 或 fallback")

    monkeypatch.setattr(_browser, "_Session", forbidden_browser)
    monkeypatch.setattr(_browser, "_session", None)
    monkeypatch.setenv("CPBL_REPLAY_MANIFEST", str(FIXTURE / "manifest.json"))
    monkeypatch.setenv("CPBL_REPLAY_BUNDLE", str(FIXTURE / "bundle"))
    expected = [{"name": "虛構"}]
    assert cpbl_site.fetch_year(2026) == expected
    assert cpbl_site.fetch_year(2026) == expected


def test_producer_unknown_page_status_is_preserved(candidate, monkeypatch):
    rewrite_json(candidate / "bundle/index.json",
                 lambda index: index["entries"][0].update(http_status=None))
    activate(monkeypatch, candidate)
    assert cpbl_site.fetch_year(2026) == [{"name": "虛構"}]
    assert _browser.session().index["entries"][0]["http_status"] is None


def test_same_request_returns_exact_raw_text(candidate):
    session = _replay.ReplaySession(candidate / "manifest.json", candidate / "bundle")
    page = (candidate / "bundle/responses/p1.body").read_bytes().decode("utf-8")
    text = (candidate / "bundle/responses/q1.body").read_bytes().decode("utf-8")
    assert session.page_html("/schedule", force=True, wait="domcontentloaded") == page
    assert session.page_html("/schedule", require=re.compile("RequestVerificationToken")) == page
    kwargs = {"headers": {"RequestVerificationToken": cpbl_site._TOKEN_RE.search(page).group(1)}}
    form = {"kindCode": "A", "location": "", "calendar": "2026/01/01"}
    assert session.post("/schedule", "/schedule/getgamedatas", form, **kwargs) == (200, text)
    assert session.post("/schedule", "/schedule/getgamedatas", form, **kwargs) == (200, text)
    (candidate / "bundle/responses/q1.body").unlink()
    with pytest.raises(_replay.ReplayError):
        session.post("/schedule", "/schedule/getgamedatas", form, **kwargs)


@pytest.mark.parametrize("change", [
    lambda i: i.update(schema="unknown"),
    lambda i: i.update(manifest_id="other"),
    lambda i: i.update(manifest_sha256="0" * 64),
    lambda i: i.update(complete=False),
    lambda i: i.update(stopped={"signal": "synthetic-stop"}),
    lambda i: i["entries"].pop(),
    lambda i: i["entries"][1].update(sha256="0" * 64),
    lambda i: i["entries"][1].update(bytes=1),
    lambda i: i["entries"][1].update(bytes=www_fetch.MAX_BODY_BYTES + 1),
    lambda i: i["entries"][1].update(body="../outside.body"),
    lambda i: i["entries"][1].update(op="page"),
    lambda i: i["entries"][1].update(api="/different"),
    lambda i: i.update(close_returned=False),
])
def test_rejects_invalid_bundle_without_fallback(candidate, monkeypatch, change):
    rewrite_json(candidate / "bundle/index.json", change)
    activate(monkeypatch, candidate)
    with pytest.raises(_replay.ReplayError):
        cpbl_site.fetch_year(2026)


@pytest.mark.parametrize("relative", ["bundle/index.json", "bundle/responses/q1.body"])
def test_missing_file_is_rejected(candidate, relative):
    (candidate / relative).unlink()
    with pytest.raises(_replay.ReplayError):
        _replay.ReplaySession(candidate / "manifest.json", candidate / "bundle")


def test_corrupt_json_is_rejected(candidate):
    (candidate / "bundle/index.json").write_text("{not-json")
    with pytest.raises(_replay.ReplayError):
        _replay.ReplaySession(candidate / "manifest.json", candidate / "bundle")


def test_body_symlink_is_rejected(candidate, tmp_path):
    path = candidate / "bundle/responses/q1.body"
    external = tmp_path / "external.body"
    path.rename(external)
    path.symlink_to(external)
    with pytest.raises(_replay.ReplayError):
        _replay.ReplaySession(candidate / "manifest.json", candidate / "bundle")


def test_total_size_limit_is_enforced(candidate, monkeypatch):
    monkeypatch.setattr(www_fetch, "MAX_TOTAL_BYTES", 1)
    with pytest.raises(_replay.ReplayError):
        _replay.ReplaySession(candidate / "manifest.json", candidate / "bundle")


@pytest.mark.parametrize("method,args,kwargs", [
    ("page_html", ("/unlisted",), {}),
    ("page_html", ("/schedule",), {"require": "absent-required-content"}),
    ("post", ("/schedule", "/schedule/getgamedatas", {"calendar": "2025/01/01"}), {}),
    ("post", ("/schedule", "/schedule/getgamedatas",
              {"calendar": "2026/01/01", "location": "", "kindCode": "A"}),
     {"headers": {"RequestVerificationToken": "wrong-synthetic-token"}}),
])
def test_unlisted_request_is_rejected_without_leaking_values(candidate, method, args, kwargs):
    session = _replay.ReplaySession(candidate / "manifest.json", candidate / "bundle")
    with pytest.raises(_replay.ReplayError) as error:
        getattr(session, method)(*args, **kwargs)
    assert "synthetic" not in str(error.value)
    assert "2025" not in str(error.value)


@pytest.mark.parametrize("variable", ["CPBL_REPLAY_MANIFEST", "CPBL_REPLAY_BUNDLE"])
def test_partial_configuration_never_reuses_browser(monkeypatch, variable):
    monkeypatch.delenv("CPBL_REPLAY_MANIFEST", raising=False)
    monkeypatch.delenv("CPBL_REPLAY_BUNDLE", raising=False)
    monkeypatch.setenv(variable, "unavailable")
    monkeypatch.setattr(_browser, "_session", object())
    with pytest.raises(_replay.ReplayError):
        _browser.session()


def test_default_browser_singleton_unchanged(monkeypatch):
    monkeypatch.delenv("CPBL_REPLAY_MANIFEST", raising=False)
    monkeypatch.delenv("CPBL_REPLAY_BUNDLE", raising=False)
    native = object()
    monkeypatch.setattr(_browser, "_session", None)
    monkeypatch.setattr(_browser, "_Session", lambda: native)
    assert _browser.session() is native
    assert _browser.session() is native


def test_existing_parser_still_rejects_success_false(candidate, monkeypatch):
    update_body(candidate, "q1", '{"Success":false,"GameDatas":"[]"}')
    activate(monkeypatch, candidate)
    with pytest.raises(RuntimeError, match="Success=false"):
        cpbl_site.fetch_year(2026)
