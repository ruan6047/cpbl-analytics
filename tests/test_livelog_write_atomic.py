"""#357 WP2 審核 1 項 1：每場 livelog 的主表更新與附加表替換必須在**同一交易**。

走正式寫入路徑 `scrape_gamelogs`（每日鏈、每週 box 重抓、單場 CLI 共用）、真的寫隔離庫；
只把官網連線、revision 紀錄與逐投手快照換成替身。負控：附加列寫入失敗 → 兩表都不變。
哨兵場次 1900-C-4（原文取 2026-C-4），DB 不可達時 skip。
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import pytest

from cpbl.ingest import cpbl_gamelog
from cpbl.ingest.cpbl_gamelog import _LL_COLS, _LL_EXTRA_COLS, _livelog_rows

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "livelog_357_www"
KEY = (1900, "C", 4)
DUP = "1120021000"
COLS = _LL_COLS.split(",")
I_C, I_S = COLS.index("content"), COLS.index("is_special_event")


def _raw() -> list[dict]:
    return json.loads(json.loads(gzip.decompress((FIXTURES / "2026-C-4.json.gz").read_bytes()))["LiveLogJson"])


def _snapshot(conn) -> tuple[list, list]:
    with conn() as c:
        main = c.execute(f"SELECT {_LL_COLS} FROM cpbl.game_livelog WHERE year=%s AND kind_code=%s "
                         "AND game_sno=%s ORDER BY main_event_no", KEY).fetchall()
        extra = c.execute(f"SELECT {_LL_EXTRA_COLS} FROM cpbl.game_livelog_extra WHERE year=%s "
                          "AND kind_code=%s AND game_sno=%s ORDER BY main_event_no, dup_seq", KEY).fetchall()
    return main, extra


def _wipe(c) -> None:
    for t in ("game_livelog", "game_livelog_extra"):
        c.execute(f"DELETE FROM cpbl.{t} WHERE year=%s AND kind_code=%s AND game_sno=%s", KEY)


@pytest.fixture
def db(monkeypatch):
    from cpbl.db import conn

    raw = _raw()
    # 前態＝修正前寫入端：最後一列被標記覆蓋、附加表空。
    old = [(*KEY, *r[3:I_C], "比賽結束", *r[I_C + 1:I_S], True, *r[I_S + 1:]) if r[3] == DUP
           else (*KEY, *r[3:]) for r in _livelog_rows(*KEY, raw)]
    try:
        with conn() as c:
            _wipe(c)
            c.execute("SELECT 1 FROM cpbl.game_livelog_extra LIMIT 0")
            c.cursor().executemany(
                f"INSERT INTO cpbl.game_livelog ({_LL_COLS}) VALUES ({','.join(['%s'] * 31)})", old)
    except Exception as exc:  # noqa: BLE001 — 無 DB／無 079 的環境
        pytest.skip(f"DB 不可用：{type(exc).__name__}")

    class _Session:
        def page_html(self, *_a, **_k):
            return '<input name="__RequestVerificationToken" value="tok" />'

        def post(self, *_a, **_k):
            return 200, json.dumps({"ScoreboardJson": "[]", "LiveLogJson": json.dumps(raw, ensure_ascii=False),
                                    "BattingJson": "[]", "PitchingJson": "[]"})

    monkeypatch.setattr("cpbl.ingest._browser.session", lambda: _Session())
    monkeypatch.setattr(cpbl_gamelog.time, "sleep", lambda _d: None)
    monkeypatch.setattr(cpbl_gamelog, "record_source_revision", lambda **_k: None)
    monkeypatch.setattr(cpbl_gamelog, "record_box_pitching_revisions", lambda *_a: None)
    yield conn
    with conn() as c:
        _wipe(c)


def test_extra_write_failure_leaves_both_tables_unchanged(db, monkeypatch):
    before = _snapshot(db)
    real = cpbl_gamelog._livelog_extra_rows

    def broken(*a):  # dup_seq=NULL → NOT NULL 違反，附加列 INSERT 必失敗
        return [(*r[:4], None, *r[5:]) for r in real(*a)]

    monkeypatch.setattr(cpbl_gamelog, "_livelog_extra_rows", broken)
    out = cpbl_gamelog.scrape_gamelogs(*KEY[:1], [KEY[2]], KEY[1], delay=0, allow_partial=True)
    assert out["failed"] == [KEY[2]]
    after = _snapshot(db)
    assert after == before, "附加列失敗時主表不得已提交"
    assert next(r for r in after[0] if r[3] == DUP)[I_C] == "比賽結束"


def test_normal_write_updates_main_and_extra_together(db):
    out = cpbl_gamelog.scrape_gamelogs(*KEY[:1], [KEY[2]], KEY[1], delay=0)
    assert out["failed"] == [] and out["livelog_extra"] == 1
    main, extra = _snapshot(db)
    assert next(r for r in main if r[3] == DUP)[I_C].startswith("擊出左外野高飛球")
    assert [r[_LL_EXTRA_COLS.split(",").index("content")] for r in extra] == ["比賽結束"]
