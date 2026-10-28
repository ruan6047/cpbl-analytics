"""#357 B1：`/api/v1/games/{sno}/live` 的 DB 路徑合併附加表，與原文／48 小時快照同形。

排序鍵 (main_event_no::bigint, 同號內序號)；附加列只帶主表欄位（回應形狀不變）。
紅綠紀錄見 `~/.wf-evidence/cpbl-analytics/357/exec-wp2/`。
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import pytest

from cpbl.api.routers import games
from cpbl.ingest.cpbl_gamelog import _LL_COLS, _LL_EXTRA_COLS, _livelog_extra_rows, _livelog_rows

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "livelog_357_www" / "2026-C-4.json.gz"
DUP = "1120021000"
PLAY = "擊出左外野高飛球，一壘安打 。1分打點。 二壘跑者岳政華回本壘得分。"


def _raw() -> list[dict]:
    return json.loads(json.loads(gzip.decompress(FIXTURE.read_bytes()))["LiveLogJson"])


def _as_dicts(cols: str, rows: list[tuple]) -> list[dict]:
    names = cols.split(",")
    return [dict(zip(names, r, strict=True)) for r in rows]


def test_merge_matches_raw_order_and_keeps_main_columns():
    raw = _raw()
    main = _as_dicts(_LL_COLS, _livelog_rows(2026, "C", 4, raw))
    extra = _as_dicts(_LL_EXTRA_COLS, _livelog_extra_rows(2026, "C", 4, raw))
    merged = games.merge_livelog_rows(sorted(main, key=lambda r: r["main_event_no"]), extra)
    assert [(r["main_event_no"], r["content"]) for r in merged] == [
        (r["MainEventNo"], r["Content"]) for r in raw]
    assert merged[-2]["content"] == PLAY and merged[-1]["content"] == "比賽結束"
    assert all(list(r) == _LL_COLS.split(",") for r in merged)


def test_merge_marker_before_play_uses_seq():
    """主列的同號位置＝附加列沒佔用的最小值：標記 dup_seq=0 時主列排在它後面。"""
    main = [{"main_event_no": "0000000002", "content": "PLAY"},
            {"main_event_no": "0000000001", "content": "A"}]
    extra = [{"main_event_no": "0000000002", "dup_seq": 0, "pkno": "P", "content": "比賽結束"}]
    merged = games.merge_livelog_rows(main, extra)
    assert [r["content"] for r in merged] == ["A", "比賽結束", "PLAY"]
    assert "dup_seq" not in merged[1] and "pkno" not in merged[1]


def test_merge_without_extra_is_identity():
    main = [{"main_event_no": "0000000001"}]
    assert games.merge_livelog_rows(main, []) is main


# ── DB 路徑：真的走 game_live()（隔離庫；DB 不可達時 skip）────────────────────────────
_KEY = (1900, "A", 357)


def test_game_live_db_path_returns_marker_after_play():
    from cpbl.db import conn

    raw = _raw()
    main = [(*_KEY, *r[3:]) for r in _livelog_rows(2026, "C", 4, raw)]
    extra = [(*_KEY, *r[3:]) for r in _livelog_extra_rows(2026, "C", 4, raw)]
    try:
        with conn() as c:
            for t in ("game_livelog", "game_livelog_extra"):
                c.execute(f"DELETE FROM cpbl.{t} WHERE year=%s AND kind_code=%s AND game_sno=%s", _KEY)
            c.cursor().executemany(
                f"INSERT INTO cpbl.game_livelog ({_LL_COLS}) VALUES ({','.join(['%s'] * 31)})", main)
            c.cursor().executemany(
                f"INSERT INTO cpbl.game_livelog_extra ({_LL_EXTRA_COLS}) "
                f"VALUES ({','.join(['%s'] * 33)})", extra)
    except Exception as exc:  # noqa: BLE001 — 無 DB／無 079 的環境
        pytest.skip(f"DB 不可用：{type(exc).__name__}")
    try:
        log = games.game_live(_KEY[2], season=_KEY[0], kind_code=_KEY[1])["livelog"]
        assert len(log) == len(raw)
        assert [(r["main_event_no"], r["content"]) for r in log[-2:]] == [(DUP, PLAY), (DUP, "比賽結束")]
        assert list(log[-1]) == list(log[0])
    finally:
        with conn() as c:
            for t in ("game_livelog", "game_livelog_extra"):
                c.execute(f"DELETE FROM cpbl.{t} WHERE year=%s AND kind_code=%s AND game_sno=%s", _KEY)
