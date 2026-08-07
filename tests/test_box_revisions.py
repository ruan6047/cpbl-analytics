from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path

import pytest

from cpbl.ingest import cpbl_gamelog
from cpbl.ingest.box_revisions import (
    pitcher_er_revision_report,
    record_box_pitching_revisions,
    revision_counts_within_days,
)

_MIGRATION = Path(__file__).parents[1] / "migrations" / "071_box_pitching_revisions.sql"

SENTINEL_YEAR = 2099
SENTINEL_KIND = "A"
SENTINEL_SNO = 999999
SENTINEL_ACNT = "9999999999"

# 讀取現有 cpbl.games 的一場真實比賽（唯讀 join 用；本卡不寫入 games）示範
# 「賽後 N 天」的計算——2018/A/1 是 2018 賽季開幕戰，game_date 穩定不變。
REAL_GAME_YEAR, REAL_GAME_KIND, REAL_GAME_SNO = 2018, "A", 1
REAL_GAME_SENTINEL_ACNT = "9999999998"


# --------------------------- 無需 DB：純函式 / 靜態檢查 ---------------------------


def test_migration_is_additive_and_scoped_to_new_table() -> None:
    sql = _MIGRATION.read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS cpbl.box_pitching_revisions" in sql
    assert "UNIQUE (year, kind_code, game_sno, pitcher_acnt, content_hash)" in sql
    assert "DROP TABLE" not in sql.upper()
    assert "ALTER TABLE cpbl.pitching_gamelog" not in sql
    assert "ALTER TABLE cpbl.game_source_revisions" not in sql


def test_record_box_pitching_revisions_skips_rows_without_pitcher_acnt() -> None:
    recorded: list[list[tuple]] = []

    class Cursor:
        def executemany(self, _sql, records):
            recorded.append(list(records))

    class Connection:
        def cursor(self):
            return Cursor()

    @contextmanager
    def fake_conn():
        yield Connection()

    import cpbl.ingest.box_revisions as mod
    orig_conn = mod.conn
    mod.conn = fake_conn
    try:
        n = record_box_pitching_revisions(2026, "A", 1, [
            {"PitcherAcnt": "0000000001", "InningPitchedCnt": 6, "InningPitchedDiv3Cnt": 0,
             "RunCnt": 1, "EarnedRunCnt": 1},
            {"PitcherAcnt": None, "InningPitchedCnt": 1},
            {},
        ])
    finally:
        mod.conn = orig_conn

    assert n == 1
    assert len(recorded[0]) == 1
    assert recorded[0][0][3] == "0000000001"


def test_gamelog_records_box_pitching_revisions_alongside_upsert(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """整合點驗證：scrape_gamelogs 抓到 PitchingJson 後同時呼叫既有 UPSERT 與新快照函式。

    掛進的實際路徑是 cpbl.ingest.cpbl_gamelog（PitchingJson 解析與
    pitching_gamelog UPSERT 都在這裡；cpbl_site.py 只有 schedule/lineup，
    不含 box 邏輯）——與卡面文字的路徑指向不同，於報告中說明。
    """
    payload = {
        "ScoreboardJson": "[]",
        "LiveLogJson": "[]",
        "BattingJson": "[]",
        "PitchingJson": json.dumps([
            {"PitcherAcnt": "0000000001", "InningPitchedCnt": 6, "InningPitchedDiv3Cnt": 0,
             "RunCnt": 1, "EarnedRunCnt": 1},
        ]),
    }

    class _BrowserSession:
        def page_html(self, _path: str, require=None) -> str:
            return '<input name="__RequestVerificationToken" value="review-token">'

        def post(self, *_args, **_kwargs) -> tuple[int, str]:
            return 200, json.dumps(payload)

    snapshot_calls: list[tuple] = []
    monkeypatch.setattr("cpbl.ingest._browser.session", lambda: _BrowserSession())
    monkeypatch.setattr(cpbl_gamelog.time, "sleep", lambda _delay: None)
    monkeypatch.setattr(cpbl_gamelog, "_upsert", lambda _table, _cols, _pk, rows: len(rows))
    monkeypatch.setattr(cpbl_gamelog, "record_source_revision", lambda **kwargs: None, raising=False)
    monkeypatch.setattr(
        cpbl_gamelog,
        "record_box_pitching_revisions",
        lambda year, kind, sno, rows: snapshot_calls.append((year, kind, sno, rows)),
    )

    cpbl_gamelog.scrape_gamelogs(2026, [7], "A", delay=0)

    assert len(snapshot_calls) == 1
    year, kind, sno, rows = snapshot_calls[0]
    assert (year, kind, sno) == (2026, "A", 7)
    assert rows[0]["PitcherAcnt"] == "0000000001"


# --------------------------- 需本機 DB ---------------------------


def _cleanup(cur) -> None:
    cur.execute(
        "DELETE FROM cpbl.box_pitching_revisions WHERE year = %s AND game_sno = %s",
        (SENTINEL_YEAR, SENTINEL_SNO),
    )
    # 唯讀借用真實比賽做 join 示範，只清自己寫入的假投手 acnt，不動其他列。
    cur.execute(
        "DELETE FROM cpbl.box_pitching_revisions WHERE pitcher_acnt = %s",
        (REAL_GAME_SENTINEL_ACNT,),
    )


@pytest.fixture()
def db():
    try:
        from cpbl.db import conn
        with conn() as c:
            _cleanup(c.cursor())
    except Exception as exc:  # noqa: BLE001 — 無 DB 時 skip（CI 無 Postgres）
        pytest.skip(f"需本機 DB：{exc}")
    yield conn
    with conn() as c:
        _cleanup(c.cursor())


def _pitcher_row(*, ip_cnt: int, ip_div3: int, runs: int, er: int) -> dict:
    return {
        "PitcherAcnt": SENTINEL_ACNT, "PitcherName": "測試投手",
        "InningPitchedCnt": ip_cnt, "InningPitchedDiv3Cnt": ip_div3,
        "RunCnt": runs, "EarnedRunCnt": er,
    }


def test_identical_content_reimport_does_not_add_rows(db) -> None:
    """冪等實測：同一份 box 內容重複匯入，不新增列（只累加 seen_count）。"""
    row = _pitcher_row(ip_cnt=6, ip_div3=0, runs=2, er=2)

    n1 = record_box_pitching_revisions(SENTINEL_YEAR, SENTINEL_KIND, SENTINEL_SNO, [row])
    n2 = record_box_pitching_revisions(SENTINEL_YEAR, SENTINEL_KIND, SENTINEL_SNO, [row])
    n3 = record_box_pitching_revisions(SENTINEL_YEAR, SENTINEL_KIND, SENTINEL_SNO, [dict(row)])

    assert (n1, n2, n3) == (1, 1, 1)  # 三次呼叫的「嘗試寫入列數」都是 1（同一投手一列）

    with db() as c:
        rows = c.execute(
            "SELECT seen_count FROM cpbl.box_pitching_revisions "
            "WHERE year=%s AND kind_code=%s AND game_sno=%s AND pitcher_acnt=%s",
            (SENTINEL_YEAR, SENTINEL_KIND, SENTINEL_SNO, SENTINEL_ACNT),
        ).fetchall()

    assert len(rows) == 1, "同內容重複匯入應只有 1 列（append-only 去重）"
    assert rows[0][0] == 3, "重複匯入應累加 seen_count 而非新增列"


def test_changed_earned_runs_creates_new_revision_and_keeps_old_row(db) -> None:
    """核心情境：官方賽後把某投手自責分從 2 改成 1——應新增一列而非覆蓋。"""
    record_box_pitching_revisions(
        SENTINEL_YEAR, SENTINEL_KIND, SENTINEL_SNO,
        [_pitcher_row(ip_cnt=6, ip_div3=0, runs=2, er=2)],
    )
    record_box_pitching_revisions(
        SENTINEL_YEAR, SENTINEL_KIND, SENTINEL_SNO,
        [_pitcher_row(ip_cnt=6, ip_div3=0, runs=2, er=1)],  # 官方改判自責分
    )

    with db() as c:
        rows = c.execute(
            "SELECT earned_runs FROM cpbl.box_pitching_revisions "
            "WHERE year=%s AND kind_code=%s AND game_sno=%s AND pitcher_acnt=%s "
            "ORDER BY fetched_at",
            (SENTINEL_YEAR, SENTINEL_KIND, SENTINEL_SNO, SENTINEL_ACNT),
        ).fetchall()

    assert [r[0] for r in rows] == [2, 1], "舊版本應保留，新版本以新列 append"


def test_report_answers_how_many_times_and_what_changed(db) -> None:
    """驗收條件的核心：能回答「某場 ER 被改過幾次、每次改了什麼」。"""
    record_box_pitching_revisions(
        SENTINEL_YEAR, SENTINEL_KIND, SENTINEL_SNO,
        [_pitcher_row(ip_cnt=6, ip_div3=0, runs=3, er=3)],
    )
    record_box_pitching_revisions(  # 內容不變，重抓一次
        SENTINEL_YEAR, SENTINEL_KIND, SENTINEL_SNO,
        [_pitcher_row(ip_cnt=6, ip_div3=0, runs=3, er=3)],
    )
    record_box_pitching_revisions(  # 官方把自責分從 3 改成 2
        SENTINEL_YEAR, SENTINEL_KIND, SENTINEL_SNO,
        [_pitcher_row(ip_cnt=6, ip_div3=0, runs=3, er=2)],
    )

    report = pitcher_er_revision_report(SENTINEL_YEAR, SENTINEL_KIND, SENTINEL_SNO)

    assert [r["earned_runs"] for r in report] == [3, 2]
    assert report[0]["revision_no"] == 1
    assert report[0]["changed_fields"] == {}
    assert report[1]["revision_no"] == 2
    assert report[1]["changed_fields"]["earned_runs"] == (3, 2)
    # game_sno=999999 不存在於 cpbl.games，join 不到 game_date 屬預期，
    # 不應讓查詢報錯——只是 days_since_game answer 不出來。
    assert report[0]["days_since_game"] is None

    counts = revision_counts_within_days(SENTINEL_YEAR, SENTINEL_KIND, SENTINEL_SNO, within_days=9999)
    # 沒有 game_date 可比對天數窗，counts 應為空（fail-closed，不猜天數）
    assert counts == {}


def test_report_computes_days_since_game_against_real_game_date(db) -> None:
    """接上真實 cpbl.games（唯讀 join）示範「賽後 N 天內改過幾次」算得出來。"""
    import datetime as dt

    record_box_pitching_revisions(
        REAL_GAME_YEAR, REAL_GAME_KIND, REAL_GAME_SNO,
        [{"PitcherAcnt": REAL_GAME_SENTINEL_ACNT, "InningPitchedCnt": 6, "InningPitchedDiv3Cnt": 0,
          "RunCnt": 1, "EarnedRunCnt": 1}],
    )
    record_box_pitching_revisions(  # 模擬官方賽後改判
        REAL_GAME_YEAR, REAL_GAME_KIND, REAL_GAME_SNO,
        [{"PitcherAcnt": REAL_GAME_SENTINEL_ACNT, "InningPitchedCnt": 6, "InningPitchedDiv3Cnt": 0,
          "RunCnt": 1, "EarnedRunCnt": 0}],
    )

    report = pitcher_er_revision_report(
        REAL_GAME_YEAR, REAL_GAME_KIND, REAL_GAME_SNO, pitcher_acnt=REAL_GAME_SENTINEL_ACNT,
    )
    expected_days = (dt.date.today() - dt.date(2018, 3, 24)).days

    assert len(report) == 2
    assert report[0]["days_since_game"] == expected_days
    assert report[1]["changed_fields"]["earned_runs"] == (1, 0)

    counts = revision_counts_within_days(
        REAL_GAME_YEAR, REAL_GAME_KIND, REAL_GAME_SNO, within_days=expected_days,
    )
    assert counts[REAL_GAME_SENTINEL_ACNT] == 1  # 這個窗內看到 1 次修正
