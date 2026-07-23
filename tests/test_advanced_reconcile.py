"""INGEST-ADV-RECONCILE1：進階快照拆分／晉升／gating 契約。

DB-free 單元測試（fetch 拆分、驗證、gating SQL）＋ 需本機 DB 的 lifecycle 測試（sentinel year 2099，
測完清理）。無 DB 時 lifecycle 測試 skip（比照 test_records_api）。
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from cpbl.ingest import advanced_snapshot as snap
from cpbl.ingest import cpbl_advanced as ca
from cpbl.ingest.advanced_snapshot import RunSpec, ValidationReport

SENTINEL_YEAR = 2099
MOIERMAN = "0000007790"


# ----------------------------- DB-free -----------------------------

def test_gating_predicate_binds_scope_and_source_run() -> None:
    g = snap.gating_predicate("a", "player_stats")
    assert "a.source_run_id" in g
    assert "s.dataset = 'player_stats'" in g
    assert "a.role" in g and "current_run_id" in g


def test_stat_upsert_sql_carries_provenance_columns() -> None:
    sql = ca._stat_upsert_sql()
    for col in ("source_run_id", "source_fetched_at", "last_seen_at", "metrics"):
        assert col in sql
    assert "ON CONFLICT (year, kind_code, acnt, role)" in sql


def test_pitch_type_fetch_keeps_both_pitch_types(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = [
        {"Player": {"Acnt": MOIERMAN}, "PitchType": "breakingball", "Pitches": 758,
         "Kph": 135.9, "KphMax": 150.0, "SpinRate": 1977.5, "SpinRateMax": 2100.0, "Throws": "R"},
        {"Player": {"Acnt": MOIERMAN}, "PitchType": "fastball", "Pitches": 428,
         "Kph": 146.3, "KphMax": 155.0, "SpinRate": 2326.9, "SpinRateMax": 2500.0, "Throws": "R"},
        {"Player": {"Acnt": ""}, "PitchType": "fastball", "Pitches": 1},          # 空 acnt → skip
        {"Player": {"Acnt": "0000000002"}, "PitchType": None, "Pitches": 1},      # 空球種 → skip
        {"Player": {"Acnt": MOIERMAN}, "PitchType": "fastball", "Pitches": 999},  # 重複 key → skip
    ]
    monkeypatch.setattr(ca, "_leaderboard_rows", lambda *a, **k: rows)
    res = ca._fetch_pitch_type(None, "pitcher", "A", 2026, delay=0)
    by_pt = {r[1]: r for r in res.rows}
    assert set(by_pt) == {"fastball", "breakingball"}
    assert by_pt["breakingball"][2] == 758 and by_pt["fastball"][2] == 428  # 球數不互相覆寫
    assert res.report.accepted_rows == 2
    assert res.report.empty_id_rows == 2
    assert res.report.duplicate_key_rows == 1


def test_merge_scalar_excludes_pitch_tracking_and_counts_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def fake_rows(_client, lb, _params):
        calls.append(lb)
        if lb == "pr-table":
            return [{"Player": {"Acnt": "0000000001"}, "Woba": 0.35, "Pa": 100},
                    {"Player": {"Acnt": ""}, "Woba": 0.1}]  # 空 acnt
        return [{"Player": {"Acnt": "0000000001"}, "Ev": 140.0}]

    monkeypatch.setattr(ca, "_leaderboard_rows", fake_rows)
    res = ca._merge_scalar(None, "batter", "A", 2026, delay=0)
    assert "pitch-tracking" not in calls  # scalar 不含 pitch-tracking
    assert set(res.data) == {"0000000001"}
    assert res.data["0000000001"]["woba"] == 0.35 and res.data["0000000001"]["ev"] == 140.0
    assert res.report.empty_id_rows == 1


def test_league_summary_fetch_parses_categories_and_pitch_type(monkeypatch: pytest.MonkeyPatch) -> None:
    lb = {
        "BattedBall": [{"Player": None, "Bbe": 8939, "Gbp": 0.46}],
        "PitchTracking": [{"Player": None, "PitchType": "fastball", "Pitches": 5000, "Kph": 145.0},
                          {"Player": None, "PitchType": "breakingball", "Pitches": 4000}],
    }
    monkeypatch.setattr(ca, "_summary_dict", lambda *a, **k: lb)
    res = ca._fetch_league_summary(None, "A", 2026, delay=0)
    keys = {(cat, pt) for cat, pt, _m, _p in res.rows}
    assert keys == {("BattedBall", ""), ("PitchTracking", "fastball"), ("PitchTracking", "breakingball")}
    assert res.report.accepted_rows == 3


def test_validate_flags_floor_dup_and_ratio() -> None:
    spec = RunSpec(2026, "A", "player_stats", "batting")
    r = snap.validate(spec, ValidationReport(accepted_rows=5, duplicate_key_rows=2), prior=None)
    assert "row_count_below_floor" in r.errors and "duplicate_natural_key" in r.errors
    r2 = snap.validate(spec, ValidationReport(accepted_rows=40), prior=200)
    assert "retain_ratio_regression" in r2.errors
    r3 = snap.validate(spec, ValidationReport(accepted_rows=160), prior=161)
    assert r3.ok


# --------------------------- 需本機 DB ---------------------------

def _cleanup(cur, year: int) -> None:
    for t in ("advanced_pitch_type_stats", "advanced_league_summary", "advanced_stats"):
        cur.execute(f"DELETE FROM cpbl.{t} WHERE year=%s", (year,))
    cur.execute("DELETE FROM cpbl.advanced_snapshot_state WHERE year=%s", (year,))
    cur.execute("DELETE FROM cpbl.advanced_ingest_runs WHERE year=%s", (year,))


@pytest.fixture()
def db():
    try:
        from cpbl.db import conn
        with conn() as c:
            _cleanup(c.cursor(), SENTINEL_YEAR)
    except Exception as exc:  # noqa: BLE001 — 無 DB 時 skip（CI 無 Postgres）
        pytest.skip(f"需本機 DB：{exc}")
    yield conn
    with conn() as c:
        _cleanup(c.cursor(), SENTINEL_YEAR)


def test_full_promote_removes_contamination_and_passes_audit(db) -> None:
    conn = db
    spec = RunSpec(SENTINEL_YEAR, "A", "player_stats", "batting")
    now = datetime.now(UTC)
    # 污染 legacy 列（source_run_id NULL、不在官方 canonical 集合）
    with conn() as c:
        c.execute(
            "INSERT INTO cpbl.advanced_stats (year,kind_code,acnt,role,metrics) "
            "VALUES (%s,'A','9999999999','batting','{\"woba\":0.9}'::jsonb)", (SENTINEL_YEAR,))

    # 直接測晉升/gating（驗證另有 DB-free 測試涵蓋）；floor 對小樣本不適用故略過 validate。
    report = ValidationReport(observed_rows=1, accepted_rows=1)
    run_id = snap.open_run(spec, "full", "test", now, observed_rows=1)

    def stage(cur, rid):
        cur.execute(ca._stat_upsert_sql(),
                    ca._record({"woba": 0.3}, SENTINEL_YEAR, "0000000001", "batting", "A")
                    + (rid, now, now))

    snap.promote_full(spec, run_id, stage, report)

    with conn() as c:
        cur = c.cursor()
        # pointer 建立且 audit 乾淨
        assert snap.current_run_id(spec) == run_id
        assert snap.pointer_audit() == []
        # 污染列已刪、canonical 列在
        acnts = {r[0] for r in cur.execute(
            "SELECT acnt FROM cpbl.advanced_stats WHERE year=%s AND role='batting'",
            (SENTINEL_YEAR,)).fetchall()}
        assert acnts == {"0000000001"}
        # gating：canonical 可見
        gate = snap.gating_predicate("a", "player_stats")
        vis = {r[0] for r in cur.execute(
            f"SELECT acnt FROM cpbl.advanced_stats a WHERE a.year=%s AND a.role='batting' AND {gate}",
            (SENTINEL_YEAR,)).fetchall()}
        assert vis == {"0000000001"}


def test_partial_refresh_keeps_pointer_and_visibility(db) -> None:
    conn = db
    spec = RunSpec(SENTINEL_YEAR, "A", "player_stats", "batting")
    now = datetime.now(UTC)
    report = ValidationReport(observed_rows=1, accepted_rows=1)
    run_id = snap.open_run(spec, "full", "test", now, observed_rows=1)
    snap.promote_full(spec, run_id, lambda cur, rid: cur.execute(
        ca._stat_upsert_sql(),
        ca._record({"woba": 0.3}, SENTINEL_YEAR, "0000000001", "batting", "A") + (rid, now, now)),
        report)

    # partial：更新已觀測 acnt 的值，掛在現行 pointer 底下，不動 pointer
    n = ca._upsert([ca._record({"woba": 0.4}, SENTINEL_YEAR, "0000000001", "batting", "A")])
    assert n == 1
    with conn() as c:
        cur = c.cursor()
        assert snap.current_run_id(spec) == run_id  # pointer 不變
        row = cur.execute(
            "SELECT (metrics->>'woba')::float, source_run_id FROM cpbl.advanced_stats "
            "WHERE year=%s AND acnt='0000000001' AND role='batting'", (SENTINEL_YEAR,)).fetchone()
        assert row[0] == 0.4 and row[1] == run_id  # 值刷新、仍掛現行 pointer → 可見
        assert snap.pointer_audit() == []
