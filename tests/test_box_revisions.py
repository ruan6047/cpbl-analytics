from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import date as dt_date
from pathlib import Path

import pytest

from cpbl.ingest import cpbl_gamelog
from cpbl.ingest.box_revisions import (
    pitcher_er_revision_report,
    record_box_pitching_revisions,
    revision_counts_within_days,
)

_MIGRATION = Path(__file__).parents[1] / "migrations" / "071_box_pitching_revisions.sql"
_DEDUP_FIX_MIGRATION = (
    Path(__file__).parents[1] / "migrations" / "072_box_pitching_revisions_latest_only_dedup.sql"
)

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


def test_dedup_fix_migration_drops_the_global_unique_without_touching_071() -> None:
    """BOX-REVISION-R1-001：071 是既存 migration，紅線不得修改，修法必須是新檔案。"""
    sql = _DEDUP_FIX_MIGRATION.read_text(encoding="utf-8")

    assert "DROP CONSTRAINT IF EXISTS" in sql
    assert "box_pitching_revisions_year_kind_code_game_sno_pitcher_acnt_key" in sql
    # 只拿掉全域內容去重的約束，不動主鍵、不動任何欄位、不刪表。
    assert "DROP TABLE" not in sql.upper()
    assert "DROP COLUMN" not in sql.upper()
    assert "PRIMARY KEY" not in sql
    # 071 本身內容不可被本檔改動（本測試只讀 071，改動會被 git diff 攔截，這裡
    # 額外斷言 071 仍保有原本的 UNIQUE 字面——證明「新開一支」而非回頭改舊檔）。
    original_071 = _MIGRATION.read_text(encoding="utf-8")
    assert "UNIQUE (year, kind_code, game_sno, pitcher_acnt, content_hash)" in original_071


def test_dedup_fix_migration_actually_removes_the_constraint_on_real_db(db) -> None:
    """不只看 migration 檔案字面，實測套用後約束真的不在了（072 已在本卡跑過
    `db.migrate()`，這裡是唯讀查詢確認結果，不重跑 migration 避免測試互相干擾）。
    """
    with db() as c:
        rows = c.execute(
            "SELECT conname FROM pg_constraint WHERE conrelid = 'cpbl.box_pitching_revisions'::regclass "
            "AND contype = 'u'"
        ).fetchall()
    names = {r[0] for r in rows}
    assert "box_pitching_revisions_year_kind_code_game_sno_pitcher_acnt_key" not in names, (
        "全域內容去重的 UNIQUE 約束仍在——072 migration 沒有真的套用到這個 DB"
    )


def test_record_box_pitching_revisions_skips_rows_without_pitcher_acnt() -> None:
    """自 072 起寫入是逐列 `execute`（不再是單次 `executemany`），且每列先取
    advisory lock 再寫（BOX-REVISION-R2-001）——每個有效列對應 2 次 `execute`
    呼叫（lock、upsert），不能再靠一次 batched INSERT ON CONFLICT 完成
    （見 record_box_pitching_revisions docstring）。"""
    recorded: list[tuple[str, dict]] = []

    class Cursor:
        def execute(self, sql, params):
            kind = "lock" if "pg_advisory_xact_lock" in sql else "upsert"
            recorded.append((kind, dict(params)))

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
    upserts = [p for kind, p in recorded if kind == "upsert"]
    locks = [p for kind, p in recorded if kind == "lock"]
    assert len(upserts) == 1
    assert upserts[0]["pitcher_acnt"] == "0000000001"
    # 每個有效列一定先鎖再寫，且鎖用同一個 PK 組出來的 key。
    assert len(locks) == 1
    assert locks[0]["lock_key"] == "box_pitching_revisions:2026:A:1:0000000001"
    assert recorded[0][0] == "lock", "必須先取鎖再寫，順序不能反"


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


def test_reverted_correction_a_to_b_to_a_keeps_all_three_revisions(db) -> None:
    """BOX-REVISION-R1-001 回歸測試：A→B→A 的回改（聯盟推翻後又推翻回來，或抓取
    瞬間看到中間態）第三次觀測不能因為內容等於第一次而被誤判成「沒變」。

    071 原本的全域 UNIQUE(...,content_hash) 會讓第三次觀測撞回第一列的 hash，
    只累加 seen_count、不新增列——B→A 這次真實發生的改判會從快照裡消失。
    072 拿掉那個全域約束、改成只比較「該 (場,投手) 最近一次觀測」，第三次觀測
    與最近一列（B）不同，必須新增第三列。
    """
    record_box_pitching_revisions(  # 第 1 次觀測：ER=3（A）
        SENTINEL_YEAR, SENTINEL_KIND, SENTINEL_SNO,
        [_pitcher_row(ip_cnt=6, ip_div3=0, runs=3, er=3)],
    )
    record_box_pitching_revisions(  # 第 2 次觀測：官方改判 ER=2（B）
        SENTINEL_YEAR, SENTINEL_KIND, SENTINEL_SNO,
        [_pitcher_row(ip_cnt=6, ip_div3=0, runs=3, er=2)],
    )
    record_box_pitching_revisions(  # 第 3 次觀測：官方又改回 ER=3（回到 A 的內容）
        SENTINEL_YEAR, SENTINEL_KIND, SENTINEL_SNO,
        [_pitcher_row(ip_cnt=6, ip_div3=0, runs=3, er=3)],
    )

    with db() as c:
        rows = c.execute(
            "SELECT earned_runs FROM cpbl.box_pitching_revisions "
            "WHERE year=%s AND kind_code=%s AND game_sno=%s AND pitcher_acnt=%s "
            "ORDER BY fetched_at, id",
            (SENTINEL_YEAR, SENTINEL_KIND, SENTINEL_SNO, SENTINEL_ACNT),
        ).fetchall()

    # 核心斷言：3 次觀測必須是 3 列，不能因為第 3 次內容等於第 1 次而被去重成 2 列。
    assert [r[0] for r in rows] == [3, 2, 3], (
        "A→B→A 的第三次觀測遺失——退回 BOX-REVISION-R1-001 修好之前的全域內容去重"
    )

    result = pitcher_er_revision_report(SENTINEL_YEAR, SENTINEL_KIND, SENTINEL_SNO)
    report = result["revisions"]
    assert [r["earned_runs"] for r in report] == [3, 2, 3]
    assert [r["revision_no"] for r in report] == [1, 2, 3]
    # 查核者明確要求：不能只驗「有 3 筆」，要驗第三筆 diff 的方向正確
    # （是 B→A 也就是 (2, 3)，不是隨便什麼非空 tuple、也不是 (3, 3) 這種假陽性）。
    assert report[0]["changed_fields"] == {}
    assert report[1]["changed_fields"]["earned_runs"] == (3, 2)
    assert report[2]["changed_fields"]["earned_runs"] == (2, 3)


def test_concurrent_writes_to_same_pk_do_not_create_duplicate_versions(db) -> None:
    """BOX-REVISION-R2-001 回歸測試（交易級 probe）：兩個交易「同時」對同一
    (year, kind_code, game_sno, pitcher_acnt) 寫入同一份新內容，advisory lock
    序列化後只能產生 1 筆新版本，不是 2 筆重複版本。

    重現查核詞點名的競態：
        交易 A：讀最近列 = X，touched 空 → INSERT X
        交易 B：讀最近列 = X，touched 空 → INSERT X     ← 重複版本（未修好前）
    用 `threading.Barrier` 讓兩條真實執行緒（各自從連線池借一條連線，模擬兩個
    獨立行程/交易）盡量同時呼叫 `record_box_pitching_revisions`，斷言最終只有
    1 筆新版本而非 2 筆——如果 advisory lock 沒生效，這裡在多次重跑下會間歇性
    看到 3 列（原本 1 列 + 兩個交易各自插入 1 列）而不是穩定的 2 列。
    """
    import threading

    # 先寫一個「舊版本」當最近一列，兩個交易都要把它改成同一個新值 ER=1。
    record_box_pitching_revisions(
        SENTINEL_YEAR, SENTINEL_KIND, SENTINEL_SNO,
        [_pitcher_row(ip_cnt=6, ip_div3=0, runs=4, er=4)],
    )

    barrier = threading.Barrier(2)
    errors: list[BaseException] = []

    def _write() -> None:
        try:
            barrier.wait(timeout=5)
            record_box_pitching_revisions(
                SENTINEL_YEAR, SENTINEL_KIND, SENTINEL_SNO,
                [_pitcher_row(ip_cnt=6, ip_div3=0, runs=4, er=1)],
            )
        except BaseException as exc:  # noqa: BLE001 — 蒐集例外供斷言，不吞掉
            errors.append(exc)

    threads = [threading.Thread(target=_write) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert not errors, f"併發寫入不應拋例外（含 deadlock）：{errors}"

    with db() as c:
        rows = c.execute(
            "SELECT earned_runs FROM cpbl.box_pitching_revisions "
            "WHERE year=%s AND kind_code=%s AND game_sno=%s AND pitcher_acnt=%s "
            "ORDER BY fetched_at, id",
            (SENTINEL_YEAR, SENTINEL_KIND, SENTINEL_SNO, SENTINEL_ACNT),
        ).fetchall()

    assert [r[0] for r in rows] == [4, 1], (
        f"應該恰好 2 筆（原本的 4、新的 1），實際 {[r[0] for r in rows]}——"
        "多於 2 筆代表 advisory lock 沒有擋住併發重複寫入"
    )


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

    result = pitcher_er_revision_report(SENTINEL_YEAR, SENTINEL_KIND, SENTINEL_SNO)
    report = result["revisions"]

    # BOX-REVISION-R1-002：限制文字必須隨資料一起回傳，不能只活在 Runbook 裡。
    assert result["caveat"], "caveat 不可為空——消費者拿到數字時必須同時拿到限制"
    assert "零觀測不代表" in result["caveat"]

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
    """接上真實 cpbl.games（唯讀 join）示範「賽後 N 天內改過幾次」算得出來。

    `expected_days` 刻意用 DB 端同一條「轉台北曆日再相減」算式重新算一次，而不是
    Python `datetime.date.today()`——DB session 是 UTC、本機在台北 00:00–08:00
    執行測試時兩者曆日會差一天（與 completion.py 記載的 D7 同一類問題），混用會
    讓這個測試在台北凌晨變成間歇性失敗，不是本卡要驗的東西。
    """
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
    )["revisions"]
    with db() as c:
        expected_days = c.execute(
            "SELECT (now() AT TIME ZONE 'Asia/Taipei')::date - %s::date",
            (dt_date(2018, 3, 24),),
        ).fetchone()[0]

    assert len(report) == 2
    assert report[0]["days_since_game"] == expected_days
    assert report[1]["changed_fields"]["earned_runs"] == (1, 0)

    counts = revision_counts_within_days(
        REAL_GAME_YEAR, REAL_GAME_KIND, REAL_GAME_SNO, within_days=expected_days,
    )
    assert counts[REAL_GAME_SENTINEL_ACNT] == 1  # 這個窗內看到 1 次修正
