"""未定案場次的官方狀態與維護者計數（`cpbl.api.unresolved`）。

腳本化 cursor 餵假列，不碰 DB——這一層的整個價值是「三種讀法只有一種要人行動」，
而那個判斷是純邏輯，必須在 CI（無 DB）跑得到。
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from fastapi.testclient import TestClient

from cpbl.api.main import app
from cpbl.api.routers import info
from cpbl.api.unresolved import pending_result_count, statuses_for

_GAME_COLS = ["season", "kind_code", "game_sno"]
_REVISION_COLS = ["year", "kind_code", "game_sno", "raw_present_status", "raw_game_result",
                  "raw_game_date", "fetched_at", "last_seen_at"]
_SEEN = datetime(2026, 8, 10, 2, 10, tzinfo=UTC)


def _revision(sno: int, present: int, result: str | None, *, kind: str = "A") -> tuple:
    return (2026, kind, sno, present, result, date(2026, 8, 9), _SEEN, _SEEN)


class _Cursor:
    """依 execute 出現順序回下一組 (description, rows)；rows 為 Exception 則拋出。"""

    def __init__(self, script: list):
        self._script = list(script)
        self.description = None
        self._rows: list[tuple] = []
        self.queries: list[str] = []

    def execute(self, sql, params=None):
        self.queries.append(" ".join(str(sql).split()))
        cols, rows = self._script.pop(0)
        if isinstance(rows, Exception):
            raise rows
        self.description = [(name,) for name in cols]
        self._rows = rows

    def fetchall(self):
        return self._rows


def test_only_officially_finished_games_count_as_pending_results():
    """**紅線**：只數「官方說打完了、我們卻還是 0–0」那一種。

    延賽與保留是官方已宣告的狀態，資料沒有落後、沒有人需要做事；把它們加進同一個
    數字會讓一個本該恆為 0 的健康指標長期非零——這個專案已經有「告警響了兩個半月
    無人讀」的前例，一個永遠不是 0 的數字就是下一個。
    """
    cursor = _Cursor([
        (_GAME_COLS, [(2026, "A", 1), (2026, "A", 2), (2026, "D", 3), (2026, "A", 4)]),
        (_REVISION_COLS, [
            _revision(1, 1, "0"),            # 官方已完成 → 真的落後
            _revision(2, 1, "1"),            # 延賽
            _revision(3, 1, "2", kind="D"),  # 保留
            _revision(4, 1, None),           # 官方那邊也還沒有結果
        ]),
    ])

    assert pending_result_count(cursor) == 1


def test_pending_count_uses_the_taipei_day_boundary():
    """新程式碼的日界一律台北（`completion.TAIPEI_TODAY_SQL`）：DB 跑 UTC，
    `CURRENT_DATE` 在台北 00:00–08:00 會指到前一天，讓窗口整整差一日。"""
    cursor = _Cursor([(_GAME_COLS, []), ])

    pending_result_count(cursor)

    assert "Asia/Taipei" in cursor.queries[0]
    assert "CURRENT_DATE" not in cursor.queries[0]


def test_no_unresolved_games_means_no_second_query():
    """常態是 0 筆未定案：那時不得再查一次官方排程歷程。"""
    cursor = _Cursor([(_GAME_COLS, [])])

    assert pending_result_count(cursor) == 0
    assert len(cursor.queries) == 1


def test_missing_revisions_table_degrades_to_no_evidence():
    """**紅線**：排程歷程讀不到時整批視為無證據（回空），不得把缺表讀成「都沒問題」
    以外的任何宣稱；呼叫端據此退回 unknown／不計入。"""
    cursor = _Cursor([(_REVISION_COLS, RuntimeError("relation does not exist"))])

    assert statuses_for(cursor, [{"season": 2026, "kind_code": "A", "game_sno": 1}]) == {}


class _Conn:
    """`with conn() as c: c.cursor()` 的最小替身；本檔的 info 測試不碰 DB。"""

    def cursor(self):
        return _Cursor([])

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _stub_info_db(monkeypatch) -> None:
    # 既有 info 測試的同一招：max(game_date) 必須回 None，回純量會讓 isoformat() 炸掉。
    monkeypatch.setattr(info, "_scalar",
                        lambda sql, params=(): None if "max(" in sql else 1)
    monkeypatch.setattr(info, "conn", lambda: _Conn())


def test_info_exposes_pending_results(monkeypatch):
    _stub_info_db(monkeypatch)
    monkeypatch.setattr(info, "pending_result_count", lambda cursor: 3)

    body = TestClient(app).get("/api/info").json()

    assert body["metrics"]["results_pending"] == 3


def test_info_omits_the_metric_rather_than_claiming_zero(monkeypatch):
    """**紅線**：算不出來時整格缺席。`0` 的意思是「查過，沒有落後」，不可以拿來表達
    「查不到」——`/api/info` 是主站看板的資料來源，假的健康值比沒有值更糟。
    整支端點也不得因此掉成 maintenance：這一格是附加訊號，不是可用性判準。"""
    _stub_info_db(monkeypatch)

    def boom(cursor):
        raise RuntimeError("relation cpbl.game_schedule_status_revisions does not exist")

    monkeypatch.setattr(info, "pending_result_count", boom)

    body = TestClient(app).get("/api/info").json()

    assert body["status"] == "running"
    assert "results_pending" not in body["metrics"]


@pytest.mark.parametrize("present,result,expected", [
    (1, "0", "final"),
    (1, "1", "postponed"),
    (1, "2", "reserved"),
    (1, None, "scheduled"),
])
def test_statuses_for_maps_each_observed_combination(present, result, expected):
    cursor = _Cursor([(_REVISION_COLS, [_revision(7, present, result)])])

    statuses = statuses_for(cursor, [{"season": 2026, "kind_code": "A", "game_sno": 7}])

    assert statuses == {(2026, "A", 7): expected}
