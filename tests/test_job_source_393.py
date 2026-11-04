"""只驗本次VPS供給接線；合成私有頁／收條，不碰真Pi、網路或DB。"""

import hashlib
import json
import os
import stat
from datetime import datetime
from pathlib import Path

import pytest


@pytest.fixture
def supply(tmp_path, monkeypatch):
    from cpbl import db
    from cpbl.ingest import _browser, _job_source, www_fetch

    state = (tmp_path / "logs").resolve(); state.mkdir(mode=0o700)
    exported = (tmp_path / "requests").resolve(); exported.mkdir(); exported.chmod(0o2750)
    native_stat = Path.stat

    def linux_export_stat(path, *args, **kwargs):
        value = native_stat(path, *args, **kwargs)
        if path == exported:
            # 純fixture模擬Linux setgid根；Mac暫存FS不保留它，不冒稱實體權限驗收。
            fields = list(value); fields[0] |= stat.S_ISGID
            return os.stat_result(fields)
        return value

    monkeypatch.setattr(Path, "stat", linux_export_stat)
    inbox = (tmp_path / "inbox").resolve(); (inbox / "incoming").mkdir(parents=True)
    for key, value in {"CPBL_JOBS_REQUESTS_ROOT": exported, "CPBL_JOBS_INBOX_ROOT": inbox,
                       "CPBL_JOBS_SOURCE_MAX_OPERATIONS": 20, "CPBL_JOBS_SOURCE_MAX_SECONDS": 60,
                       "CPBL_JOBS_MODE": 1, "REFRESH_TRIGGER": "jobs"}.items():
        monkeypatch.setenv(key, str(value))
    monkeypatch.delenv("CPBL_REPLAY_MANIFEST", raising=False)
    monkeypatch.delenv("CPBL_REPLAY_BUNDLE", raising=False)

    def forbidden(*a, **kw):
        pytest.fail("live dependency forbidden")

    monkeypatch.setattr(_browser, "_Session", forbidden)
    monkeypatch.setattr(db, "conn", forbidden)
    received, posts, mode = [], [], {"receipt": "valid"}

    def deliver(_seconds):
        pointer = exported / "scrape-daily.json"
        raw = pointer.read_bytes(); manifest = www_fetch.parse_manifest(raw)
        received.append((raw, manifest))
        serial = len(received)

        class Driver:
            def page(self, path, wait, require):
                return None, (f"<script>RequestVerificationToken: 'inline-{serial}'</script>"
                              f'<input name="__RequestVerificationToken" value="hidden-{serial}">'
                              f"getFightingScore: function() {{ RequestVerificationToken: 'score-{serial}' }}")

            def post(self, page, api, form, headers):
                posts.append((api, form, headers))
                if api in www_fetch.HTML_POST_APIS:
                    return 200, "<table>fixture</table>"
                return 200, json.dumps({"Success": True, "GameDatas": json.dumps([{"Year": 2026}])})

            def observation(self):
                return {}

            def close(self):
                pass

        index = www_fetch.run(raw, inbox / "incoming", driver_factory=Driver,
                              now=lambda: datetime.fromisoformat(manifest["window"]["start"]),
                              sleep=lambda _: None)
        folder = inbox / "incoming" / manifest["manifest_id"]
        if mode["receipt"] == "partial":
            index["complete"] = False
            (folder / "index.json").write_text(json.dumps(index))
        index_raw = (folder / "index.json").read_bytes()
        receipt = {"manifest_id": manifest["manifest_id"], "manifest_sha256": www_fetch.digest(raw),
                   "index_sha256": hashlib.sha256(index_raw).hexdigest(),
                   "raw_batch_rc": 0, "raw_batch_waited": True}
        if mode["receipt"] == "wrong-hash":
            receipt["manifest_sha256"] = "0" * 64
        (folder / "delivery.json").write_text(json.dumps(receipt))

    monkeypatch.setattr(_job_source.time, "sleep", deliver)
    return _job_source, state, exported, inbox, received, posts, mode


def test_scheduled_jobs_cannot_reuse_fixed_replay_environment(monkeypatch, tmp_path):
    from cpbl.ingest import _browser, _job_source, _replay
    from cpbl.ingest._replay import ReplayError

    monkeypatch.setenv("CPBL_JOBS_MODE", "1")
    monkeypatch.setenv("REFRESH_TRIGGER", "jobs")
    monkeypatch.setenv("CPBL_REPLAY_MANIFEST", "/fixture/old-manifest")
    monkeypatch.setenv("CPBL_REPLAY_BUNDLE", "/fixture/old-bundle")
    monkeypatch.setattr(_replay, "replay_session", lambda *a: object())
    with _job_source.job_source("scrape-daily", tmp_path) as source:
        with pytest.raises(ReplayError):
            _browser.session()
        assert source.failed and source.backend is None


def test_existing_schedule_parser_gets_new_exact_bundle_after_delivery(supply):
    from cpbl.ingest import _browser, cpbl_site, www_fetch

    bridge, state, exported, _inbox, received, posts, _mode = supply
    with bridge.job_source("scrape-daily", state) as source:
        assert cpbl_site.fetch_year(2026, "A") == [{"Year": 2026}]
        assert source.backend.operations == 3 and not source.failed
        assert _browser.session() is source.backend
        assert (exported / "scrape-daily.json").read_bytes() == received[-1][0]
        assert (exported / "scrape-daily.json").stat().st_mode & 0o777 == 0o640
    assert len(received) == 2 and received[0][1]["manifest_id"] != received[1][1]["manifest_id"]
    for raw, manifest in received:
        original = state / "source" / manifest["manifest_id"] / "manifest.json"
        assert original.read_bytes() == raw
        assert b"inline-" not in raw and b"hidden-" not in raw
        assert original.stat().st_mode & 0o777 == 0o600
        assert www_fetch.digest(raw) == hashlib.sha256(raw).hexdigest()
    assert posts[0][2]["RequestVerificationToken"] == "inline-2"  # 不是caller舊頁inline-1。
    assert not (exported / "scrape-daily.json").exists()


@pytest.mark.parametrize("failure", ["wrong-hash", "partial"])
def test_receipt_or_bundle_failure_stops_without_republishing(supply, failure):
    from cpbl.ingest._replay import ReplayError

    bridge, state, _exported, _inbox, received, _posts, mode = supply
    mode["receipt"] = failure
    with bridge.job_source("scrape-daily", state) as source:
        session = bridge.active_session()
        with pytest.raises(ReplayError):
            session.page_html("/schedule")
        with pytest.raises(ReplayError):
            session.page_html("/schedule", force=True)
        assert source.failed
    assert len(received) == 1


def test_missing_receipt_times_out_and_old_bundle_is_not_selected(supply, monkeypatch):
    from cpbl.ingest._replay import ReplayError

    bridge, state, _exported, inbox, received, _posts, _mode = supply
    stale = inbox / "incoming/old-run"; stale.mkdir()
    (stale / "delivery.json").write_text('{"manifest_id":"old-run"}')
    clock = [0.0]
    monkeypatch.setattr(bridge.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(bridge.time, "sleep", lambda _: clock.__setitem__(0, 100.0))
    with bridge.job_source("scrape-daily", state) as source:
        with pytest.raises(ReplayError):
            bridge.active_session().page_html("/schedule")
        assert source.failed
    assert not received
    assert len(list((state / "source").glob("*/manifest.json"))) == 1


def test_budget_counts_page_and_post_before_publishing_next_batch(supply, monkeypatch):
    from cpbl.ingest import cpbl_site
    from cpbl.ingest._replay import ReplayError

    bridge, state, _exported, _inbox, received, _posts, _mode = supply
    monkeypatch.setenv("CPBL_JOBS_SOURCE_MAX_OPERATIONS", "1")
    with bridge.job_source("scrape-daily", state) as source:
        with pytest.raises(ReplayError):
            cpbl_site.fetch_year(2026, "A")
        assert source.failed and source.backend.operations == 1
    assert len(received) == 1


def test_quiet_context_does_not_create_or_export_a_manifest(supply):
    bridge, state, exported, _inbox, received, _posts, _mode = supply
    with bridge.job_source("postseason-evening", state) as source:
        assert source.backend is None
    assert not list(exported.iterdir()) and not (state / "source").exists() and not received


def test_manual_fixed_replay_is_still_explicit_and_does_no_supply(monkeypatch):
    from cpbl.ingest import _browser, _replay

    monkeypatch.setenv("CPBL_JOBS_MODE", "1"); monkeypatch.setenv("REFRESH_TRIGGER", "manual")
    monkeypatch.setenv("CPBL_REPLAY_MANIFEST", "/fixture/original")
    monkeypatch.setenv("CPBL_REPLAY_BUNDLE", "/fixture/bundle")
    expected = object()
    monkeypatch.setattr(_replay, "replay_session", lambda *a: expected)
    assert _browser.session() is expected


def test_html_reply_uses_fixed_wp3_compatibility_without_reformatting(supply):
    bridge, state, _exported, _inbox, received, _posts, _mode = supply
    with bridge.job_source("scrape-daily", state):
        session = bridge.active_session()
        session.page_html("/standings/season")
        assert session.post("/standings/season", "/standings/seasonaction", {},
                            {"RequestVerificationToken": "inline-1"}) == (200, "<table>fixture</table>")
    assert len(received) == 2


def test_function_token_keeps_its_anchor_and_refreshes_only_in_pi_page(supply):
    from cpbl.ingest.cpbl_fighting import OPTS_PATH

    bridge, state, _exported, _inbox, received, posts, _mode = supply
    assert bridge._TOKEN_FOR_API[OPTS_PATH] == "getSelectOpts"
    path = "/team/fighting?Acnt=fixture"
    with bridge.job_source("scrape-daily", state):
        session = bridge.active_session()
        session.page_html(path, require="getFightingScore: function")
        assert session.post(path, "/team/getfightingscore", {},
                            {"RequestVerificationToken": "score-1"})[0] == 200
    assert received[-1][1]["requests"][1]["headers"] == {
        "RequestVerificationToken": {"$token": "getFightingScore"}}
    assert posts[-1][2]["RequestVerificationToken"] == "score-2"
