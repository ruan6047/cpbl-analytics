"""#237：game_live 逐球查詢的語意離線測試（無共享 DB、無網路、無環境設定）。

從 games.py 原文抽出真 SQL，於 SQLite 記憶體庫以純 synthetic 列執行；列值僅供測試，
不是正式資料。只改寫 SQLite 不支援的方言：`%s`→`?`、`ARRAY(子查詢)`→`group_concat`
（events 以 (pa_row_id, event_position) 為 WITHOUT ROWID 主鍵，串接順序即位置順序）。
查詢效能（EXPLAIN）不在此驗證，由 dispatcher 唯讀 EXPLAIN 與正式 E1 結果另行比對。
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parents[1] / "src/cpbl/api/routers/games.py"
_ARRAY_RE = re.compile(
    r"ARRAY\(SELECT event_no FROM cpbl\.game_pa_events\s+"
    r"WHERE pa_row_id=pa\.pa_row_id ORDER BY event_position\)"
)
_SQLITE_ARRAY = ("(SELECT group_concat(event_no) FROM cpbl.game_pa_events "
                 "WHERE pa_row_id=pa.pa_row_id)")

_DDL = """
CREATE TABLE cpbl.game_recap_builds (build_id TEXT PRIMARY KEY, year INT, kind_code TEXT,
    game_sno INT, state TEXT);
CREATE TABLE cpbl.game_plate_appearances (pa_row_id INTEGER PRIMARY KEY, build_id TEXT,
    pa_index INT, start_event_no INT, state TEXT);
CREATE TABLE cpbl.game_pa_events (pa_row_id INT, event_position INT, event_no INT,
    PRIMARY KEY (pa_row_id, event_position)) WITHOUT ROWID;
CREATE TABLE cpbl.game_pa_pitch_mappings (build_id TEXT, year INT, kind_code TEXT,
    game_sno INT, pitcher_acnt TEXT, pitch_cnt INT, pa_row_id INT, pitch_position INT,
    mapping_state TEXT);
CREATE TABLE cpbl.pitch_tracking (year INT, kind_code TEXT, game_sno INT, pitcher_acnt TEXT,
    hitter_acnt TEXT, inning_seq INT, pitch_cnt INT, ball_cnt INT, strike_cnt INT,
    pitch_type_pred_v2 TEXT, pitch_type_pred TEXT, tagged_pitch_type TEXT, rel_speed REAL,
    plate_loc_side REAL, plate_loc_height REAL, pitch_call TEXT, hit_exit_speed REAL,
    hit_launch_angle REAL, hit_spin_rate REAL, hit_distance REAL, hit_hang_time REAL);
"""

# 全為 synthetic：同一 sno=2、同一投手 p1 橫跨 A／E／C／他年，驗 game key 隔離。
_BUILDS = [
    ("bA", 2026, "A", 2, "published"),
    ("bE", 2026, "E", 2, "published"),
    ("bE_old", 2026, "E", 2, "superseded"),
    ("bC_old", 2026, "C", 2, "superseded"),   # C 無 published build
    ("bE25", 2025, "E", 2, "published"),
]
_PAS = [  # (pa_row_id, build_id, pa_index, start_event_no, state)；插入順序刻意打亂
    (1, "bA", 1, 10, "ready"),
    (2, "bE", 2, 30, "ready"),
    (3, "bE", 1, 20, "ready"),
    (4, "bE", 3, 40, "unreliable"),
    (5, "bE_old", 1, 20, "ready"),
    (6, "bC_old", 1, 50, "ready"),
    (7, "bE25", 1, 60, "ready"),
]
_EVENTS = [(1, 1, 10), (1, 2, 11), (2, 1, 30), (3, 1, 20), (3, 2, 21), (3, 3, 22),
           (4, 1, 40), (5, 1, 20), (6, 1, 50), (7, 1, 60)]
_MAPPINGS = [  # (build_id, year, kind, sno, pitcher, pitch_cnt, pa_row_id, position, state)
    ("bA", 2026, "A", 2, "p1", 1, 1, 1, "mapped"),
    ("bE", 2026, "E", 2, "p1", 3, 2, 1, "mapped"),
    ("bE", 2026, "E", 2, "p1", 2, 3, 2, "mapped"),
    ("bE", 2026, "E", 2, "p1", 1, 3, 1, "mapped"),
    ("bE", 2026, "E", 2, "p1", 4, 4, 1, "mapped"),   # PA 非 ready
    ("bE", 2026, "E", 2, "p1", 5, 2, 2, "failed"),   # mapping 失敗
    ("bE", 2026, "E", 2, "p1", 6, 5, 1, "mapped"),   # build 不一致：PA 屬 bE_old
    ("bE_old", 2026, "E", 2, "p1", 1, 5, 1, "mapped"),
    ("bE_old", 2026, "E", 2, "p1", 2, 5, 2, "mapped"),
    ("bC_old", 2026, "C", 2, "p1", 1, 6, 1, "mapped"),
    ("bE25", 2025, "E", 2, "p1", 1, 7, 1, "mapped"),
]
_PITCHES = [  # (year, kind, sno, pitcher, pitch_cnt, pitch_type_pred_v2, pitch_type_pred)
    (2026, "A", 2, "p1", 1, None, "FB"),
    (2026, "E", 2, "p1", 1, None, "FB"),
    (2026, "E", 2, "p1", 2, "SL", "FB"),
    (2026, "E", 2, "p1", 3, None, "CH"),
    (2026, "E", 2, "p1", 4, None, "FB"),
    (2026, "E", 2, "p1", 5, None, "FB"),
    (2026, "E", 2, "p1", 6, None, "FB"),
    (2026, "E", 2, "p1", 7, None, "FB"),   # 無 mapping
    (2026, "C", 2, "p1", 1, None, "FB"),
    (2025, "E", 2, "p1", 1, None, "CU"),
]


def _tracking_sql() -> str:
    """games.py 內唯一同時讀 pitch_tracking 與 mapping 的 SQL 字串（真查詢原文）。"""
    code = _SRC.read_text(encoding="utf-8")
    blocks = [b for b in re.findall(r'"""(.*?)"""', code, flags=re.S)
              if "cpbl.game_pa_pitch_mappings" in b and "cpbl.pitch_tracking" in b]
    assert len(blocks) == 1
    return blocks[0]


@pytest.fixture
def db():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("ATTACH DATABASE ':memory:' AS cpbl")
    c.executescript(_DDL)
    c.executemany("INSERT INTO cpbl.game_recap_builds VALUES (?,?,?,?,?)", _BUILDS)
    c.executemany("INSERT INTO cpbl.game_plate_appearances VALUES (?,?,?,?,?)", _PAS)
    c.executemany("INSERT INTO cpbl.game_pa_events VALUES (?,?,?)", _EVENTS)
    c.executemany("INSERT INTO cpbl.game_pa_pitch_mappings VALUES (?,?,?,?,?,?,?,?,?)",
                  _MAPPINGS)
    c.executemany(
        "INSERT INTO cpbl.pitch_tracking (year, kind_code, game_sno, pitcher_acnt, pitch_cnt,"
        " pitch_type_pred_v2, pitch_type_pred) VALUES (?,?,?,?,?,?,?)",
        _PITCHES,
    )
    yield c
    c.close()


def _run(db: sqlite3.Connection, year: int, kind: str, sno: int) -> list[tuple]:
    sql, n = _ARRAY_RE.subn(_SQLITE_ARRAY, _tracking_sql())
    assert n == 1
    if sqlite3.sqlite_version_info < (3, 35, 0):  # 舊 SQLite 不認 MATERIALIZED（語意不變）
        sql = sql.replace("AS MATERIALIZED", "AS")
    rows = db.execute(sql.replace("%s", "?"), (year, kind, sno) * 2).fetchall()
    return [(r["main_event_no"], [int(x) for x in str(r["main_event_nos"]).split(",")],
             r["pitcher_acnt"], r["pitch_cnt"], r["pitch_type_pred"]) for r in rows]


def test_postseason_e_only_published_ready_mapped_in_pa_order(db) -> None:
    # superseded 映射不重複、PA 非 ready／mapping 失敗／build 不一致／無 mapping 皆排除
    assert _run(db, 2026, "E", 2) == [
        (20, [20, 21, 22], "p1", 1, "FB"),
        (20, [20, 21, 22], "p1", 2, "SL"),
        (30, [30], "p1", 3, "CH"),
    ]


def test_same_sno_regular_and_other_year_isolated(db) -> None:
    assert _run(db, 2026, "A", 2) == [(10, [10, 11], "p1", 1, "FB")]
    assert _run(db, 2025, "E", 2) == [(60, [60], "p1", 1, "CU")]


def test_missing_published_build_returns_empty(db) -> None:
    assert _run(db, 2026, "C", 2) == []   # 只有 superseded
    assert _run(db, 2026, "E", 99) == []  # 無任何 build


def test_republish_switches_to_new_current_build_only(db) -> None:
    db.execute("UPDATE cpbl.game_recap_builds SET state='superseded' WHERE build_id='bE'")
    db.execute("UPDATE cpbl.game_recap_builds SET state='published' WHERE build_id='bE_old'")
    # bE 的 cnt=6 mapping 指向 bE_old 的 PA，但 mapping.build_id 仍是 bE → 不一致排除
    assert _run(db, 2026, "E", 2) == [
        (20, [20], "p1", 1, "FB"),
        (20, [20], "p1", 2, "SL"),
    ]


def test_plan_shape_guard_pins_published_build_first() -> None:
    """結構守門（非行為測試）：防回退成 pt／mapping 驅動的形狀；效能另以 EXPLAIN 補證。"""
    code = _SRC.read_text(encoding="utf-8")
    sql = _tracking_sql()
    flat = " ".join(sql.split())
    assert "WITH pub AS MATERIALIZED ( SELECT build_id FROM cpbl.game_recap_builds" in flat
    assert "WHERE year=%s AND kind_code=%s AND game_sno=%s AND state='published' )" in flat
    assert "ON mapping.build_id=pub.build_id" in flat
    assert flat.count("%s") == 6
    tail = code[code.index(sql) + len(sql):]
    assert re.match(r'"""\s*,\s*\(season, kind_code, game_sno\) \* 2,\s*\)', tail)
