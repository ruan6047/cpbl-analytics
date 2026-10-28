"""#357 B1：同一事件號多筆時，主列以外的同號列寫進附加表 `game_livelog_extra`。

被修的形狀見 `test_livelog_primary_row.py`：每場最後事件號下 PLAY 之後跟一筆結束標記。
今日切片（PR #362）只留主列、標記列不入庫；本檔驗「標記列（及任何其他同號列）不再被吃掉」。

fixture 與 `test_livelog_primary_row.py` 共用（#357 研究 2 的 www 原文，sha256 已在該檔釘死）。
紅綠紀錄見 `~/.wf-evidence/cpbl-analytics/357/exec-wp2/`。
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import psycopg
import pytest

from cpbl.ingest import cpbl_gamelog
from cpbl.ingest.cpbl_gamelog import _LL_COLS, _LL_EXTRA_COLS, _livelog_extra_rows, _livelog_rows

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "livelog_357_www"

# (檔名, 重複的事件號, 原文標記 content, 原文標記 Pkno)
CASES = [
    ("2026-C-4.json.gz", "1120021000", "比賽結束"),
    ("2026-D-118.json.gz", "0720019000", "主審裁定比賽結束"),
    ("2026-D-163.json.gz", "0720032000", "主審裁定比賽結束"),
]

_XCOLS = _LL_EXTRA_COLS.split(",")
_X_EVENT, _X_SEQ, _X_PKNO = (_XCOLS.index(c) for c in ("main_event_no", "dup_seq", "pkno"))
_X_CONTENT, _X_SPECIAL = _XCOLS.index("content"), _XCOLS.index("is_special_event")


def _load(name: str) -> list[dict]:
    return json.loads(json.loads(gzip.decompress((FIXTURES / name).read_bytes()))["LiveLogJson"])


def _ident(name: str) -> tuple[int, str, int]:
    year, kind, sno = name.removesuffix(".json.gz").split("-")
    return int(year), kind, int(sno)


@pytest.mark.parametrize(("name", "dup", "marker"), CASES)
def test_marker_row_goes_to_extra_table(name, dup, marker):
    """舊行為（今日切片）丟掉標記列；新行為把它寫進附加表，dup_seq＝原文同號組位置。"""
    raw = _load(name)
    raw_marker = [r for r in raw if r.get("MainEventNo") == dup][1]
    extra = _livelog_extra_rows(*_ident(name), raw)
    assert [(r[_X_EVENT], r[_X_SEQ], r[_X_CONTENT]) for r in extra] == [(dup, 1, marker)]
    assert extra[0][_X_PKNO] == raw_marker["Pkno"]
    assert extra[0][_X_SPECIAL] is True  # 原文標記列 IsSpecialEvent="1"


@pytest.mark.parametrize(("name", "_dup", "_marker"), CASES)
def test_same_number_conservation(name, _dup, _marker):
    """主表列＋附加列＝原文帶事件號的列數；兩表的鍵各自唯一、且主表鍵不出現重複號。"""
    raw = _load(name)
    main = _livelog_rows(*_ident(name), raw)
    extra = _livelog_extra_rows(*_ident(name), raw)
    assert len(main) + len(extra) == sum(1 for r in raw if r.get("MainEventNo"))
    assert len({r[:5] for r in extra}) == len(extra)
    assert len({r[:4] for r in main}) == len(main)


@pytest.mark.parametrize(("name", "_dup", "_marker"), CASES)
def test_extra_fields_equal_main_conversion(name, _dup, _marker):
    """附加列除了鍵外的欄位，與主表對同一原文列的轉換逐欄相同（共用 `_livelog_fields`）。"""
    raw = _load(name)
    ident = _ident(name)
    for row in _livelog_extra_rows(*ident, raw):
        src = next(r for r in raw if r.get("Pkno") == row[_X_PKNO])
        assert row[6:] == _livelog_rows(*ident, [src])[0][4:]
    assert len(_XCOLS) == len(_LL_COLS.split(",")) + 2


def test_marker_before_play_extra_has_seq_zero():
    """非預期形狀①：標記在 PLAY 之前——主列仍是 PLAY，標記以 dup_seq=0 進附加表。"""
    name, dup, marker = CASES[0]
    raw = _load(name)
    i = next(k for k, r in enumerate(raw) if r.get("MainEventNo") == dup)
    swapped = raw[:i] + [raw[i + 1], raw[i]] + raw[i + 2:]
    extra = _livelog_extra_rows(*_ident(name), swapped)
    assert [(r[_X_SEQ], r[_X_CONTENT]) for r in extra] == [(0, marker)]


def test_group_of_only_markers_keeps_second_in_extra():
    """非預期形狀②：全組都是標記——主列取第一筆，第二筆進附加表（不丟）。"""
    name, dup, _marker = CASES[1]
    raw = _load(name)
    m = next(r for r in raw if r.get("MainEventNo") == dup and r["Content"] == "主審裁定比賽結束")
    data = [r for r in raw if r.get("MainEventNo") != dup] + [m, {**m, "Content": "比賽結束", "Pkno": "X"}]
    extra = _livelog_extra_rows(*_ident(name), data)
    assert [(r[_X_SEQ], r[_X_CONTENT], r[_X_PKNO]) for r in extra] == [(1, "比賽結束", "X")]


def test_no_duplicates_no_extra_rows():
    name, dup, _marker = CASES[0]
    raw = [r for r in _load(name) if not (r.get("MainEventNo") == dup and r["Content"] == "比賽結束")]
    assert _livelog_extra_rows(*_ident(name), raw) == []


# ── 寫入端接線：解析成功才「先刪後寫」，壞 JSON 不碰既有附加列 ─────────────────────────
def _payload(livelog: list[dict] | str) -> dict:
    ll = livelog if isinstance(livelog, str) else json.dumps(livelog, ensure_ascii=False)
    return {"ScoreboardJson": "[]", "LiveLogJson": ll, "BattingJson": "[]", "PitchingJson": "[]"}


@pytest.fixture
def scrape_harness(monkeypatch):
    calls: list[tuple] = []
    payloads: dict[int, dict] = {}

    class _Session:
        def page_html(self, *_a, **_k):
            return '<input name="__RequestVerificationToken" value="tok" />'

        def post(self, _path, _endpoint, data, **_k):
            return 200, json.dumps(payloads[int(data["GameSno"])])

    monkeypatch.setattr("cpbl.ingest._browser.session", lambda: _Session())
    monkeypatch.setattr(cpbl_gamelog.time, "sleep", lambda _d: None)
    monkeypatch.setattr(cpbl_gamelog, "_upsert", lambda _t, _c, _pk, rows: len(rows))
    monkeypatch.setattr(cpbl_gamelog, "record_source_revision", lambda **_k: None)
    monkeypatch.setattr(cpbl_gamelog, "record_box_pitching_revisions", lambda *_a: None)
    def _write(y, k, s, data, *, replace_extra):
        extra = cpbl_gamelog._livelog_extra_rows(y, k, s, data) if replace_extra else []
        if replace_extra:
            calls.append((y, k, s, extra))
        return len(cpbl_gamelog._livelog_rows(y, k, s, data)), len(extra)

    monkeypatch.setattr(cpbl_gamelog, "_write_livelog", _write)
    return calls, payloads


def test_scrape_writes_extra_rows_per_game(scrape_harness):
    calls, payloads = scrape_harness
    payloads[4] = _payload(_load("2026-C-4.json.gz"))
    out = cpbl_gamelog.scrape_gamelogs(2026, [4], "C", delay=0)
    assert out["livelog_extra"] == 1
    assert [(y, k, s, [r[_X_CONTENT] for r in rows]) for y, k, s, rows in calls] == [
        (2026, "C", 4, ["比賽結束"])]


def test_scrape_clears_extra_rows_when_source_has_no_duplicates(scrape_harness):
    """原文已無同號多筆（官方事後刪列）也要呼叫：先刪後寫才不會留下殘列。"""
    calls, payloads = scrape_harness
    raw = [r for r in _load("2026-C-4.json.gz") if r["Content"] != "比賽結束"]
    payloads[4] = _payload(raw)
    cpbl_gamelog.scrape_gamelogs(2026, [4], "C", delay=0)
    assert calls == [(2026, "C", 4, [])]


@pytest.mark.parametrize(("name", "want"), [("2019-A-118.json.gz", "0920001000"),
                                             ("2026-C-4.json.gz", None)])
def test_scrape_records_standalone_marker_in_revision_detail(scrape_harness, monkeypatch, name, want):
    """C1 回看：寫入端在 livelog revision detail 記「末組只有標記」的事件號（否則 null）。"""
    _calls, payloads = scrape_harness
    seen: list[dict] = []
    monkeypatch.setattr(cpbl_gamelog, "record_source_revision", lambda **k: seen.append(k))
    payloads[4] = _payload(_load(name))
    cpbl_gamelog.scrape_gamelogs(2026, [4], "C", delay=0)
    detail = next(k["detail"] for k in seen if k["source"] == "livelog")
    assert "standalone_end_marker" in detail and detail["standalone_end_marker"] == want


def test_scrape_leaves_extra_rows_alone_on_bad_livelog_json(scrape_harness):
    calls, payloads = scrape_harness
    payloads[4] = _payload("{broken")
    out = cpbl_gamelog.scrape_gamelogs(2026, [4], "C", delay=0, allow_partial=True)
    assert out["failed"] == [4]
    assert calls == []


# ── DB：先刪後寫同一交易（隔離庫；DB 不可達時 skip）──────────────────────────────────
_SENTINEL = (1900, "Z", 357)


def test_write_livelog_replaces_extra_rows_in_db():
    """`_write_livelog` 在隔離庫：殘列被清、標記列寫入；原文無同號組時附加表清空。"""
    from cpbl.db import conn

    name, _dup, _marker = CASES[0]
    data = _load(name)
    rows = [(*_SENTINEL, *r[3:]) for r in _livelog_extra_rows(*_ident(name), data)]
    stale = (*_SENTINEL, "0000000001", 3, "STALE", *rows[0][6:])

    def _wipe(c):
        for t in ("game_livelog", "game_livelog_extra"):
            c.execute(f"DELETE FROM cpbl.{t} WHERE year=%s AND kind_code=%s AND game_sno=%s", _SENTINEL)

    try:
        with conn() as c:
            _wipe(c)
            c.execute(f"INSERT INTO cpbl.game_livelog_extra ({_LL_EXTRA_COLS}) "
                      f"VALUES ({','.join(['%s'] * len(_XCOLS))})", stale)
    except (psycopg.Error, Exception) as exc:  # noqa: BLE001 — 無 DB／無 079 的環境
        pytest.skip(f"DB 不可用：{type(exc).__name__}")
    try:
        n_main, n_extra = cpbl_gamelog._write_livelog(*_SENTINEL, data, replace_extra=True)
        assert n_extra == 1 and n_main == len(_livelog_rows(*_SENTINEL, data))
        with conn() as c:
            got = c.execute(
                "SELECT main_event_no, dup_seq, pkno, content FROM cpbl.game_livelog_extra "
                "WHERE year=%s AND kind_code=%s AND game_sno=%s ORDER BY 1, 2", _SENTINEL).fetchall()
        assert got == [(rows[0][_X_EVENT], 1, rows[0][_X_PKNO], "比賽結束")]
        no_dup = [r for r in data if r["Content"] != "比賽結束"]
        assert cpbl_gamelog._write_livelog(*_SENTINEL, no_dup, replace_extra=True)[1] == 0
        with conn() as c:
            n = c.execute("SELECT count(*) FROM cpbl.game_livelog_extra "
                          "WHERE year=%s AND kind_code=%s AND game_sno=%s", _SENTINEL).fetchone()[0]
        assert n == 0
    finally:
        with conn() as c:
            _wipe(c)
