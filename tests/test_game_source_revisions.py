from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path

import httpx
import pytest

from cpbl.ingest import cpbl_advanced, cpbl_gamelog, cpbl_site, run_refresh_recent
from cpbl.ingest.cpbl_advanced import AdvancedScrapeResult
from cpbl.ingest.game_source_revisions import (
    canonical_source_version,
    sanitize_detail,
)

_MIGRATION = Path(__file__).parents[1] / "migrations" / "061_game_source_revisions.sql"


def test_migration_is_additive_and_guards_revision_vocabularies() -> None:
    sql = _MIGRATION.read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS cpbl.game_source_revisions" in sql
    assert "CREATE TABLE IF NOT EXISTS cpbl.game_schedule_status_revisions" in sql
    assert "CHECK (source IN ('schedule', 'scoreboard', 'livelog', 'advanced'))" in sql
    assert "CHECK (outcome IN ('available', 'missing', 'error'))" in sql
    assert "UNIQUE (year, kind_code, game_sno, source, source_version)" in sql
    assert "UNIQUE (year, kind_code, game_season_code, game_sno, payload_hash)" in sql
    assert "DROP TABLE" not in sql.upper()
    assert "ALTER TABLE cpbl.games" not in sql


def test_source_version_is_stable_for_reordered_json_keys() -> None:
    left = {"b": [2, {"z": 1, "a": 3}], "a": "中職"}
    right = {"a": "中職", "b": [2, {"a": 3, "z": 1}]}

    assert canonical_source_version(left) == canonical_source_version(right)


def test_sanitize_detail_redacts_secret_keys_and_caps_untrusted_text() -> None:
    detail = sanitize_detail({
        "token": "should-not-survive",
        "status": 428,
        "message": "x" * 800,
        "nested": {"api_key": "hidden", "phase": "getlive"},
    })

    assert detail["token"] == "[REDACTED]"
    assert detail["nested"]["api_key"] == "[REDACTED]"
    assert detail["nested"]["phase"] == "getlive"
    assert len(detail["message"]) == 500


def test_upsert_games_records_every_raw_schedule_revision(monkeypatch: pytest.MonkeyPatch) -> None:
    recorded: list[list[dict]] = []

    class Cursor:
        def executemany(self, _sql, _records):
            return None

    class Connection:
        def cursor(self):
            return Cursor()

    @contextmanager
    def fake_conn():
        yield Connection()

    monkeypatch.setattr(cpbl_site, "conn", fake_conn)
    monkeypatch.setattr(
        cpbl_site,
        "record_schedule_revisions",
        lambda entries: recorded.append(entries),
        raising=False,
    )
    entries = [
        {
            "Year": 2026, "KindCode": "A", "GameSeasonCode": "1", "GameSno": 7,
            "GameDate": "2026-07-01", "PresentStatus": 1, "GameResult": "1",
            "HomeScore": 0, "VisitingScore": 0,
        },
        {
            "Year": 2026, "KindCode": "A", "GameSeasonCode": "1", "GameSno": 7,
            "GameDate": "2026-07-08", "PreExeDate": "2026-07-01",
            "PresentStatus": 1, "GameResult": "", "HomeScore": 3, "VisitingScore": 2,
        },
    ]

    cpbl_site.upsert_games(entries)

    assert recorded == [entries]


class _BrowserSession:
    def __init__(self, responses: list[tuple[int, str]]) -> None:
        self.responses = iter(responses)

    def page_html(self, _path: str, require=None) -> str:
        return '<input name="__RequestVerificationToken" value="review-token">'

    def post(self, *_args, **_kwargs) -> tuple[int, str]:
        return next(self.responses)


def test_gamelog_records_scoreboard_available_and_livelog_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "ScoreboardJson": json.dumps([{"TeamNo": "A", "InningSeq": 1}]),
        "LiveLogJson": "[]",
        "BattingJson": "[]",
        "PitchingJson": "[]",
    }
    revisions: list[dict] = []
    session = _BrowserSession([(200, json.dumps(payload))])
    monkeypatch.setattr("cpbl.ingest._browser.session", lambda: session)
    monkeypatch.setattr(cpbl_gamelog.time, "sleep", lambda _delay: None)
    monkeypatch.setattr(cpbl_gamelog, "_upsert", lambda _table, _cols, _pk, rows: len(rows))
    monkeypatch.setattr(
        cpbl_gamelog,
        "record_source_revision",
        lambda **kwargs: revisions.append(kwargs),
        raising=False,
    )

    cpbl_gamelog.scrape_gamelogs(2026, [7], "A", delay=0)

    by_source = {revision["source"]: revision for revision in revisions}
    assert by_source["scoreboard"]["outcome"] == "available"
    assert by_source["scoreboard"]["row_count"] == 1
    assert by_source["livelog"]["outcome"] == "missing"
    assert by_source["livelog"]["row_count"] == 0


def test_gamelog_records_source_error_instead_of_treating_http_failure_as_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    revisions: list[dict] = []
    session = _BrowserSession([(428, "challenge")])
    monkeypatch.setattr("cpbl.ingest._browser.session", lambda: session)
    monkeypatch.setattr(cpbl_gamelog.time, "sleep", lambda _delay: None)
    monkeypatch.setattr(
        cpbl_gamelog,
        "record_source_revision",
        lambda **kwargs: revisions.append(kwargs),
        raising=False,
    )

    cpbl_gamelog.scrape_gamelogs(2026, [8], "A", delay=0)

    assert {(row["source"], row["outcome"], row["error_code"]) for row in revisions} == {
        ("scoreboard", "error", "http_428"),
        ("livelog", "error", "http_428"),
    }


def test_gamelog_keeps_each_embedded_source_json_outcome_independent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "ScoreboardJson": "{broken",
        "LiveLogJson": "[]",
        "BattingJson": "[]",
        "PitchingJson": "[]",
    }
    revisions: list[dict] = []
    session = _BrowserSession([(200, json.dumps(payload))])
    monkeypatch.setattr("cpbl.ingest._browser.session", lambda: session)
    monkeypatch.setattr(cpbl_gamelog.time, "sleep", lambda _delay: None)
    monkeypatch.setattr(cpbl_gamelog, "_upsert", lambda _table, _cols, _pk, rows: len(rows))
    monkeypatch.setattr(
        cpbl_gamelog,
        "record_source_revision",
        lambda **kwargs: revisions.append(kwargs),
    )

    cpbl_gamelog.scrape_gamelogs(2026, [9], "A", delay=0)

    by_source = {revision["source"]: revision for revision in revisions}
    assert by_source["scoreboard"]["outcome"] == "error"
    assert by_source["scoreboard"]["error_code"] == "invalid_source_json"
    assert by_source["livelog"]["outcome"] == "missing"


def test_advanced_result_exposes_partial_source_error_without_breaking_row_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fetch(_client, search_type: str, _kind: str, _year: int, delay: float):
        del delay
        if search_type == "batter":
            raise httpx.ConnectError("source unavailable")
        return {"0000000002": {"woba": 0.3}}

    monkeypatch.setattr(cpbl_advanced, "_fetch_leaderboards", fetch)
    monkeypatch.setattr(cpbl_advanced, "_upsert", lambda records: len(records))

    result = cpbl_advanced.scrape_advanced_result(
        2026,
        [("0000000001", "batting"), ("0000000002", "pitching")],
        delay=0,
    )

    assert result.rows == 1
    assert result.outcome == "error"
    assert result.error_codes == ("batting_http_error",)


def test_recent_refresh_records_advanced_evidence_as_not_game_level_complete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    revisions: list[dict] = []
    monkeypatch.setattr(
        run_refresh_recent,
        "record_source_revision",
        lambda **kwargs: revisions.append(kwargs),
        raising=False,
    )

    run_refresh_recent._record_advanced_revisions(
        2026,
        "A",
        [7, 8],
        AdvancedScrapeResult(rows=23, outcome="available", error_codes=()),
    )

    assert [row["game_sno"] for row in revisions] == [7, 8]
    assert all(row["source"] == "advanced" for row in revisions)
    assert all(row["detail"]["game_level_complete"] is False for row in revisions)
