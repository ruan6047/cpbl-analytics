"""#357 WP2-e：重放工具只補被吃掉的同號列；前態「逐場三態可接受」、不符不寫、寫前存復原檔。

原文 fixture 同 `test_livelog_primary_row.py`；`ledger361-2026-C-4.jsonl` 是 #361 實際交付的
ledger 中 2026-C-4 那一列（逐字複製自 `~/.wf-evidence/cpbl-analytics/361/exec-1/local/`
`ledger-cpbl-2026-10-23T123414+0000.jsonl`），其 `raw_sha256` 即本 fixture 的 sha256。
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from cpbl.ingest import livelog_replay as lr
from cpbl.ingest.cpbl_gamelog import _LL_COLS, _LL_EXTRA_COLS, _livelog_extra_rows, _livelog_rows

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "livelog_357_www"
LEDGER = FIXTURES / "ledger361-2026-C-4.jsonl"
COLS = _LL_COLS.split(",")
I_C, I_S = COLS.index("content"), COLS.index("is_special_event")
DUP = "1120021000"
# C1 回看：IsChangePlayer=1 的標記列（主審裁定比賽結束）3 場＋結束標記自佔事件號 1 場。
HIST_CHANGE = ("2018-D-110", "2019-A-39", "2020-D-84")
HIST = (*HIST_CHANGE, "2019-A-118")


@pytest.fixture
def raw_dir(tmp_path: Path) -> Path:
    d = tmp_path / "raw"
    d.mkdir()
    lines = []
    for name in ("2026-C-4.json.gz", "2026-D-118.json.gz", *(f"{n}.json.gz" for n in HIST)):
        shutil.copy(FIXTURES / name, d / name)
        lines.append(f"{hashlib.sha256((d / name).read_bytes()).hexdigest()}  {name}")
    (d / "SHA256SUMS").write_text("\n".join(lines) + "\n")
    return d


def _game(raw_dir: Path, key=(2026, "C", 4)) -> lr.RawGame:
    games, rejected = lr.load_raw_games(raw_dir)
    assert rejected == {}
    return games[key]


def _old_rows(raw: lr.RawGame) -> list[tuple]:
    """舊寫入端（後到者勝）的 DB 終態：最後一列＝標記列的轉換。"""
    rows = _livelog_rows(*raw.key, raw.livelog)
    marker = [r for r in raw.livelog if r["MainEventNo"] == DUP][-1]
    return [(*r[:I_C], marker["Content"], *r[I_C + 1:I_S], True, *r[I_S + 1:]) if r[3] == DUP else r
            for r in rows]


def _last_wins_rows(raw: lr.RawGame) -> list[tuple]:
    """舊寫入端的 DB 終態，逐欄照實：每個事件號取原文**最後一列**整列轉換（後到者勝）。"""
    last: dict[str, dict] = {}
    for r in raw.livelog:
        if r.get("MainEventNo"):
            last[r["MainEventNo"]] = r
    return [_livelog_rows(*raw.key, [r])[0] for r in last.values()]


def _key(name: str) -> tuple[int, str, int]:
    y, k, s = name.split("-")
    return int(y), k, int(s)


def _ledger() -> dict:
    return lr.load_ledgers([LEDGER])


def test_old_state_updates_last_row_and_writes_extra(raw_dir):
    raw = _game(raw_dir)
    d = lr.decide(raw, _old_rows(raw), [], {})
    assert (d.action, d.state, d.reasons) == (lr.ACTION_UPDATE_AND_EXTRA, lr.STATE_OLD, [])
    assert d.update_row[I_C].startswith("擊出左外野高飛球") and d.update_row[I_S] is False
    assert [r[5 + 8] for r in d.extra_rows] == ["比賽結束"]  # pkno 後第 8 欄＝content


def test_new_state_writes_extra_only(raw_dir):
    raw = _game(raw_dir)
    d = lr.decide(raw, _livelog_rows(*raw.key, raw.livelog), [], {})
    assert (d.action, d.state, d.update_row) == (lr.ACTION_EXTRA_ONLY, lr.STATE_NEW, None)


def test_361_state_is_accepted_via_ledger(raw_dir):
    """#361 補過：DB＝ledger new_content／new_is_special_event（真實 ledger 列）。"""
    raw = _game(raw_dir)
    row = next(iter(_ledger().values()))
    rows = [(*r[:I_C], row["new_content"], *r[I_C + 1:I_S], row["new_is_special_event"], *r[I_S + 1:])
            if r[3] == DUP else r for r in _livelog_rows(*raw.key, raw.livelog)]
    d = lr.decide(raw, rows, [], _ledger())
    assert d.action == lr.ACTION_EXTRA_ONLY and d.state in (lr.STATE_361, lr.STATE_NEW)


def test_361_lf_normalised_content_needs_the_ledger(raw_dir):
    """content 為 LF 正規化版（≠原文 CRLF）時，只有 ledger 能證明它是 #361 寫的。"""
    raw = _game(raw_dir)
    raw.livelog = [{**r, "Content": r["Content"] + "\r\n"} if r["MainEventNo"] == DUP
                   and "比賽結束" not in r["Content"] else r for r in raw.livelog]
    primary = next(r for r in raw.livelog if r["MainEventNo"] == DUP)["Content"]
    ledger_row = {**next(iter(_ledger().values())), "new_content": lr.crlf_to_lf(primary)}
    ledger = {(2026, "C", 4, DUP): ledger_row}
    rows = [(*r[:I_C], lr.crlf_to_lf(primary), *r[I_C + 1:I_S], False, *r[I_S + 1:])
            if r[3] == DUP else r for r in _livelog_rows(*raw.key, raw.livelog)]
    assert lr.decide(raw, rows, [], ledger).state == lr.STATE_361
    assert lr.decide(raw, rows, [], {}).action is None  # 沒 ledger＝不符


def test_ledger_disagreeing_with_raw_stops_game(raw_dir):
    raw = _game(raw_dir)
    bad = {k: {**v, "new_content": "別的內容"} for k, v in _ledger().items()}
    d = lr.decide(raw, _old_rows(raw), [], bad)
    assert d.action is None and d.reasons == ["ledger_disagrees_with_raw"]


def test_other_row_mismatch_is_not_written(raw_dir):
    raw = _game(raw_dir)
    rows = _old_rows(raw)
    rows[0] = (*rows[0][:I_C], "官方事後改過", *rows[0][I_C + 1:])
    d = lr.decide(raw, rows, [], {})
    assert d.action is None and d.reasons[0].startswith("row_mismatch")


def test_unexpected_last_content_is_not_written(raw_dir):
    raw = _game(raw_dir)
    rows = [(*r[:I_C], "不明內容", *r[I_C + 1:]) if r[3] == DUP else r for r in _old_rows(raw)]
    assert lr.decide(raw, rows, [], {}).reasons == [f"last_row_content_unexpected: {DUP}"]


def test_non_final_duplicate_group_is_a_new_shape(raw_dir):
    raw = _game(raw_dir)
    first = raw.livelog[0]
    raw.livelog = [first, {**first, "Content": "比賽暫停", "Pkno": "X"}, *raw.livelog[1:]]
    d = lr.decide(raw, _old_rows(raw), [], {})
    assert d.action is None and d.reasons[0].startswith("unexpected_dup_groups")


def test_event_set_mismatch(raw_dir):
    raw = _game(raw_dir)
    assert lr.decide(raw, _old_rows(raw)[1:], [], {}).reasons[0].startswith("event_set_mismatch")


def test_existing_extra_rows_idempotent_or_refused(raw_dir):
    raw = _game(raw_dir)
    want = _livelog_extra_rows(*raw.key, raw.livelog)
    main = _livelog_rows(*raw.key, raw.livelog)
    assert lr.decide(raw, main, want, {}).action == lr.ACTION_ALREADY
    other = [(*want[0][:6], "別的", *want[0][7:])]
    assert lr.decide(raw, main, other, {}).reasons == ["extra_rows_present_and_differ"]


def test_sha_mismatch_file_is_rejected(raw_dir):
    (raw_dir / "SHA256SUMS").write_text("0" * 64 + "  2026-C-4.json.gz\n")
    games, rejected = lr.load_raw_games(raw_dir)
    assert set(games) == set() and len(rejected) == 2 + len(HIST)
    assert set(rejected.values()) == {"sha256_missing_or_mismatch"}


def test_ledger_loader_rejects_bad_rows(tmp_path):
    row = json.loads(LEDGER.read_text())
    bad = tmp_path / "bad.jsonl"
    bad.write_text(json.dumps({**row, "new_sha256": "0" * 64}, ensure_ascii=False) + "\n")
    with pytest.raises(ValueError, match="new_sha256"):
        lr.load_ledgers([bad])
    dup = tmp_path / "dup.jsonl"
    dup.write_text(LEDGER.read_text() * 2)
    with pytest.raises(ValueError, match="PK 重複"):
        lr.load_ledgers([dup])


def test_cli_apply_requires_restore_out(raw_dir):
    with pytest.raises(SystemExit) as e:
        lr.main(["--raw-dir", str(raw_dir), "--apply"])
    assert e.value.code == 2


# ── DB：dry-run 不寫、apply 寫＋復原檔、重跑冪等（隔離庫哨兵 year=1900）────────────────
@pytest.fixture
def sentinel(tmp_path: Path):
    from cpbl.db import conn

    d = tmp_path / "raw1900"
    d.mkdir()
    shutil.copy(FIXTURES / "2026-C-4.json.gz", d / "1900-C-4.json.gz")
    (d / "SHA256SUMS").write_text(
        f"{hashlib.sha256((d / '1900-C-4.json.gz').read_bytes()).hexdigest()}  1900-C-4.json.gz\n")
    raw = lr.load_raw_games(d)[0][(1900, "C", 4)]
    try:
        with conn() as c:
            for t in ("game_livelog", "game_livelog_extra"):
                c.execute(f"DELETE FROM cpbl.{t} WHERE year=1900")
            c.cursor().executemany(
                f"INSERT INTO cpbl.game_livelog ({_LL_COLS}) VALUES ({','.join(['%s'] * 31)})",
                _old_rows(raw))
    except Exception as exc:  # noqa: BLE001 — 無 DB 的環境
        pytest.skip(f"DB 不可用：{type(exc).__name__}")
    yield d, conn
    with conn() as c:
        for t in ("game_livelog", "game_livelog_extra"):
            c.execute(f"DELETE FROM cpbl.{t} WHERE year=1900")


# ── C1 回看 ② 舊前態整列比對（IsChangePlayer=1 的標記列）────────────────────────────
I_CP = COLS.index("is_change_player")


@pytest.mark.parametrize("name", HIST_CHANGE)
def test_old_state_with_change_player_marker_updates_whole_row(raw_dir, name):
    raw = _game(raw_dir, _key(name))
    rows = _last_wins_rows(raw)
    final = max(r[3] for r in rows)
    got = next(r for r in rows if r[3] == final)
    assert got[I_CP] is True and got[I_C] == "主審裁定比賽結束"  # 前提：DB 末列＝標記列整列
    d = lr.decide(raw, rows, [], {})
    assert (d.action, d.state, d.reasons) == (lr.ACTION_UPDATE_AND_EXTRA, lr.STATE_OLD, [])
    want = next(r for r in _livelog_rows(*raw.key, raw.livelog) if r[3] == final)
    assert d.update_row == want and d.update_row[I_CP] is False


def test_old_state_requires_whole_row_equal_to_last_raw_row(raw_dir):
    """負控：末列是標記、但另一欄（球數）和原文同號組最後一列不同 → 不寫。"""
    raw = _game(raw_dir, _key("2018-D-110"))
    i_pc = COLS.index("pitch_cnt")
    rows = _last_wins_rows(raw)
    final = max(r[3] for r in rows)
    rows = [(*r[:i_pc], (r[i_pc] or 0) + 1, *r[i_pc + 1:]) if r[3] == final else r for r in rows]
    d = lr.decide(raw, rows, [], {})
    assert d.action is None and d.reasons == [f"last_row_content_unexpected: {final}"]


# ── C1 回看 ③ no_duplicate 也比對最後事件號 ─────────────────────────────────────────
def test_standalone_marker_game_is_no_duplicate(raw_dir):
    raw = _game(raw_dir, _key("2019-A-118"))
    d = lr.decide(raw, _livelog_rows(*raw.key, raw.livelog), [], {})
    assert (d.action, d.reasons) == (lr.ACTION_NO_DUP, [])


def test_no_duplicate_final_row_mismatch_is_refused(raw_dir):
    raw = _game(raw_dir, _key("2019-A-118"))
    rows = [(*r[:I_C], "官方事後改過", *r[I_C + 1:]) if r[3] == "0920001000" else r
            for r in _livelog_rows(*raw.key, raw.livelog)]
    d = lr.decide(raw, rows, [], {})
    assert d.action is None and d.reasons == ["row_mismatch: 0920001000"]


def test_db_apply_old_change_player_state_rewrites_whole_row(tmp_path):
    """DB：2018-D-110 舊前態 apply 後主表末列整列＝原文主列（含 is_change_player=false）。"""
    from cpbl.db import conn

    d = tmp_path / "raw1900"
    d.mkdir()
    shutil.copy(FIXTURES / "2018-D-110.json.gz", d / "1900-D-110.json.gz")
    (d / "SHA256SUMS").write_text(
        f"{hashlib.sha256((d / '1900-D-110.json.gz').read_bytes()).hexdigest()}  1900-D-110.json.gz\n")
    raw = lr.load_raw_games(d)[0][(1900, "D", 110)]
    try:
        with conn() as c:
            for t in ("game_livelog", "game_livelog_extra"):
                c.execute(f"DELETE FROM cpbl.{t} WHERE year=1900")
            c.cursor().executemany(
                f"INSERT INTO cpbl.game_livelog ({_LL_COLS}) VALUES ({','.join(['%s'] * 31)})",
                _last_wins_rows(raw))
    except Exception as exc:  # noqa: BLE001 — 無 DB 的環境
        pytest.skip(f"DB 不可用：{type(exc).__name__}")
    try:
        res = lr.run(d, [], apply=True, restore_out=tmp_path / "restore.jsonl")
        assert res["applied"] == 1 and res["refused"] == []
        want = {r[3]: r for r in _livelog_rows(*raw.key, raw.livelog)}
        with conn() as c:
            got = c.execute(f"SELECT {_LL_COLS} FROM cpbl.game_livelog WHERE year=1900").fetchall()
        assert {r[3]: tuple(r) for r in got} == want
        rec = json.loads((tmp_path / "restore.jsonl").read_text())
        assert rec["old_main_row"][I_CP] is True
    finally:
        with conn() as c:
            for t in ("game_livelog", "game_livelog_extra"):
                c.execute(f"DELETE FROM cpbl.{t} WHERE year=1900")


def test_db_dry_run_then_apply_then_idempotent(sentinel, tmp_path):
    d, conn = sentinel
    dry = lr.run(d, [], apply=False, restore_out=None)
    assert dry["actions"] == {lr.ACTION_UPDATE_AND_EXTRA: 1} and dry["applied"] == 0
    with conn() as c:
        assert c.execute("SELECT content FROM cpbl.game_livelog WHERE year=1900 AND main_event_no=%s",
                         (DUP,)).fetchone()[0] == "比賽結束"
    restore = tmp_path / "restore.jsonl"
    applied = lr.run(d, [], apply=True, restore_out=restore)
    assert applied["applied"] == 1 and applied["recheck_failed"] == []
    with conn() as c:
        content, special = c.execute(
            "SELECT content, is_special_event FROM cpbl.game_livelog WHERE year=1900 AND main_event_no=%s",
            (DUP,)).fetchone()
        extra = c.execute(f"SELECT {_LL_EXTRA_COLS} FROM cpbl.game_livelog_extra WHERE year=1900").fetchall()
    assert content.startswith("擊出左外野高飛球") and special is False
    assert [r[13] for r in extra] == ["比賽結束"]
    rec = json.loads(restore.read_text())
    assert rec["old_main_row"][I_C] == "比賽結束" and rec["old_extra_rows"] == []
    again = lr.run(d, [], apply=True, restore_out=restore)
    assert again["actions"] == {lr.ACTION_ALREADY: 1} and again["applied"] == 0
    assert len(restore.read_text().splitlines()) == 1  # 冪等重跑不再寫復原檔
