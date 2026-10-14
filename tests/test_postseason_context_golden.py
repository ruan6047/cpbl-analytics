"""#283 S02 WP5：跨語言 golden。

Python 以固定輸入＋固定 now 產生 ``series_context``，與 repo 內 committed JSON
（``web/src/lib/__golden__/series-context/*.json``）逐字比對；TS 端
（``web/src/lib/postseason-context.test.ts``）讀**同一份 JSON** 驗首頁、日曆、當季戰績、單場頁的輸出。
改一邊不改另一邊會紅。重產：``CPBL_UPDATE_GOLDEN=1 uv run pytest tests/test_postseason_context_golden.py``。

案例：
- ``2026-e-decided-c-pending``：本機 DB 真實狀態（E 已決、C 已入庫未開打）。
- ``2026-e-after-e2``：真實 E1–E2（兄弟、獅各一勝），E3–E4 未完賽、C 尚未入庫。
- ``2026-c-swept-injected``：注入 C1–C4 兄弟連勝（真實事件未發生、未驗證；隊碼真實）。
- ``2025-complete``：已完成 E→C 真實年（無公告安排 ⇒ 前端不建旅程，只驗系列計數）。
- ``2026-c8-pending-injected``（再審 F1）：C1–C7 一和、各三勝，官方新增未完賽 C8（注入事件，隊碼真實）。
- ``2026-c2-live-c1-unsynced-injected``（再審 F2）：經**讀取層**（腳本化 cursor）組輸入；C1 尚未同步完賽、
  C2 唯一 live（注入事件，場次身分為 2026 真實 C1／C2）。
"""

from __future__ import annotations

import json
import os
from dataclasses import replace
from datetime import date, datetime
from pathlib import Path

import pytest
from postseason_context_inputs import (
    READER_GAME_COLS,
    READER_GAMES,
    ScriptedCursor,
    games,
    inputs,
    reader_table,
    with_result,
)

from cpbl import postseason_contract as pc

GOLDEN = Path(__file__).resolve().parents[1] / "web" / "src" / "lib" / "__golden__" / "series-context"


def _after_e2():
    gs = [g for g in games(2026) if g.kind_code == "E"]
    return [g if g.game_sno <= 2 else replace(g, completed=False, official_status="scheduled") for g in gs]


def _c_swept():
    out = []
    for g in games(2026):
        if g.kind_code == "C" and g.game_sno <= 4:
            # 兄弟每場 5:1（依真實列主客決定比分方向）
            out.append(with_result(g, 5, 1) if g.away_team_code == "ACN011" else with_result(g, 1, 5))
        else:
            out.append(g)
    return out


def _g8_pending():
    out = [g for g in games(2026) if g.kind_code == "E"]
    cs = [g for g in games(2026) if g.kind_code == "C"]
    for g, (a, h) in zip(cs, [(3, 3), (1, 2), (2, 1), (1, 2), (2, 1), (1, 2), (2, 1)], strict=True):
        out.append(with_result(g, a, h))
    out.append(replace(cs[-1], game_sno=8, game_date=date(2026, 10, 26), official_status="scheduled"))
    return out


def _c2_live_via_reader():
    t = reader_table()
    t[pc.GAMES_V2_SQL] = (READER_GAME_COLS, [*READER_GAMES, (2026, "C", 2, date(2026, 10, 18), "大巨蛋", None,
                                                              "ACN011", "AAA011", 0, 0, False)])
    now = datetime.fromisoformat("2026-10-18T18:00:00+08:00")
    return pc.read_series_inputs(ScriptedCursor(t), 2026, now=now,
                                 live_reader=lambda y, k, n, *, now: {"phase": "live"} if n == 2 else None)


CASES = {
    "2026-e-decided-c-pending": (lambda: inputs(2026), "2026-10-15T01:00:00+08:00"),
    "2026-e-after-e2": (lambda: inputs(2026, games_override=_after_e2()), "2026-10-10T23:00:00+08:00"),
    "2026-c-swept-injected": (lambda: inputs(2026, games_override=_c_swept()), "2026-10-22T09:00:00+08:00"),
    "2025-complete": (lambda: inputs(2025), "2026-10-15T01:00:00+08:00"),
    "2026-c8-pending-injected": (lambda: inputs(2026, games_override=_g8_pending()), "2026-10-26T12:00:00+08:00"),
    "2026-c2-live-c1-unsynced-injected": (_c2_live_via_reader, "2026-10-18T18:00:00+08:00"),
}


@pytest.mark.parametrize("name", sorted(CASES))
def test_series_context_matches_committed_golden(name):
    build, now = CASES[name]
    ctx = pc.compute_series_context(build(), now=datetime.fromisoformat(now))
    text = json.dumps(ctx, ensure_ascii=False, indent=1, sort_keys=True, default=str) + "\n"
    path = GOLDEN / f"{name}.json"
    if os.environ.get("CPBL_UPDATE_GOLDEN") == "1":
        path.write_text(text, encoding="utf-8")
    assert path.read_text(encoding="utf-8") == text, f"{path.name} 與 Python 輸出不一致；TS 端讀同一份"
