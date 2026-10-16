"""#288 S07 WP-K3 逐場焦點 adapter 的 SQL 語意：只在**自行擁有的隔離 Postgres**（``CPBL_ISOLATED_TEST_DSN``）執行。

比照 ``test_playoffs_overview_isolated.py``：未設 DSN 即 skip；該庫已有 ``cpbl.games`` 即拒跑；結束時 DROP 自建
schema。⛔ 絕不在共用本機庫或正式庫建表寫列。

驗只有真 SQL 才看得出來的事：

1. S02 inputs 與五表投影在**同一個 REPEATABLE READ READ ONLY 交易**（同 snapshot），五表各 1 支查詢。
2. 列以**打亂順序**寫入後，回傳列序＝單場端點的 ORDER BY（scoreboard／livelog 唯一序、batting 以 PA／AB 排、
   pitching 以局數排；平手的相對順序兩邊同樣未定義，只驗排序性質）。
3. 真實 E1 投影（``web/src/lib/__fixtures__/game-highlights_2026E.json`` 的 input，前端黃金測試用同一份）
   寫進去再讀出來，欄位與值原樣（decisions 由注入的函式提供、只對資料到齊的場呼叫）。
4. 缺任一表的場 ⇒ ``pending``；表不存在 ⇒ 例外（router 轉 503，前端顯示待更新）。
"""

from __future__ import annotations

import json
import os
import random
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path

import pytest
from postseason_context_inputs import YEARS
from test_playoffs_overview_isolated import _DDL, _NOW, _T0, MVP

from cpbl.playoffs import series_highlights as sh

GOLD = json.loads((Path(__file__).resolve().parents[1] / "web" / "src" / "lib" / "__fixtures__"
                   / "game-highlights_2026E.json").read_text("utf-8"))
E1 = GOLD["input"]


def _type(values) -> str:
    vs = [v for v in values if v is not None]
    if vs and all(isinstance(v, bool) for v in vs):
        return "boolean"
    if vs and all(isinstance(v, int) and not isinstance(v, bool) for v in vs):
        return "integer"
    if vs and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in vs):
        return "real"
    return "text"


def _ddl(table: str, cols: tuple[str, ...], rows: list[dict], extra: str = "") -> str:
    defs = ", ".join(f"{c} {_type(r.get(c) for r in rows)}" for c in cols)
    return f"CREATE TABLE cpbl.{table} (year int, kind_code text, game_sno int, {defs}{extra});"


@pytest.fixture(scope="module")
def dsn():
    value = os.environ.get("CPBL_ISOLATED_TEST_DSN")
    if not value:
        pytest.skip("未設 CPBL_ISOLATED_TEST_DSN（自行擁有的隔離 Postgres）")
    import psycopg

    with psycopg.connect(value, autocommit=True) as c:
        if c.execute("SELECT to_regclass('cpbl.games')").fetchone()[0] is not None:
            pytest.fail("隔離庫已有 cpbl.games：拒絕在疑似真實資料庫上建表寫列")
        c.execute(_DDL)
        try:
            c.execute("ALTER TABLE cpbl.games ADD COLUMN away_starter_id text, ADD COLUMN home_starter_id text")
            c.execute(_ddl("game_scoreboard", sh.SCOREBOARD_COLS, E1["scoreboard"]))
            c.execute(_ddl("game_livelog", sh.LIVELOG_COLS, E1["livelog"]))
            c.execute(_ddl("batting_gamelog", sh.BATTING_COLS, E1["batting"],
                           ", plate_appearances int, at_bats int"))
            c.execute(_ddl("pitching_gamelog", sh.PITCHING_COLS, E1["pitching"]))
            for kind, sno, seg, day, away, home, a, h, done in YEARS["2026"]["games"]:
                if kind == "C" and sno > 2:
                    continue
                starters = (E1["game"]["away_starter_id"], E1["game"]["home_starter_id"]) if (kind, sno) == ("E", 1) \
                    else (None, None)
                c.execute("INSERT INTO cpbl.games VALUES (2026,%s,%s,%s,%s,'測試',%s,%s,%s,%s,%s,%s,%s)",
                          (kind, seg, sno, day, MVP.get(sno) if kind == "E" else None, away, home, a, h, *starters))
                seen = _T0 + timedelta(days=sno - 4)
                c.execute(
                    "INSERT INTO cpbl.game_schedule_status_revisions (year, kind_code, game_sno, "
                    "raw_present_status, raw_game_result, raw_game_date, raw_payload, payload_hash, "
                    "fetched_at, last_seen_at) VALUES (2026,%s,%s,1,%s,%s,'{\"IsPlayBall\":\"N\"}',%s,%s,%s)",
                    (kind, sno, "0" if done else "", day, f"h{kind}{sno}", seen, seen))
            for st, tc, w, l, t in YEARS["2026"]["official"]:  # noqa: E741
                c.execute("INSERT INTO cpbl.team_standings VALUES (2026,'A',%s,%s,0,%s,%s,%s)", (st, tc, w, l, t))
            rnd = random.Random(288)

            def put(table, cols, rows, sno, extra=()):
                shuffled = list(enumerate(rows))
                rnd.shuffle(shuffled)
                for i, r in shuffled:
                    vals = [r.get(col) for col in cols] + [f(i, len(rows)) for f in extra]
                    names = ", ".join((*cols, *("plate_appearances", "at_bats")[:len(extra)]))
                    c.execute(f"INSERT INTO cpbl.{table} (year, kind_code, game_sno, {names}) "  # noqa: S608
                              f"VALUES (2026,'E',%s,{', '.join(['%s'] * len(vals))})", (sno, *vals))

            # E1：真實投影，全部表到齊；batting 以合成 PA（同隊內遞減）讓 ORDER BY 唯一地還原原始列序
            put("game_scoreboard", sh.SCOREBOARD_COLS, E1["scoreboard"], 1)
            put("game_livelog", sh.LIVELOG_COLS, E1["livelog"], 1)
            put("batting_gamelog", sh.BATTING_COLS, E1["batting"], 1, extra=(lambda i, n: n - i, lambda i, n: 0))
            put("pitching_gamelog", sh.PITCHING_COLS, E1["pitching"], 1)
            # E2：只有 scoreboard／livelog／batting（缺 pitching）⇒ pending；E3、E4：全缺 ⇒ pending
            put("game_scoreboard", sh.SCOREBOARD_COLS, E1["scoreboard"][:2], 2)
            put("game_livelog", sh.LIVELOG_COLS, E1["livelog"][:3], 2)
            put("batting_gamelog", sh.BATTING_COLS, E1["batting"][:2], 2, extra=(lambda i, n: n - i, lambda i, n: 0))
            yield value
        finally:
            c.execute("DROP SCHEMA cpbl CASCADE")


@contextmanager
def _connect(dsn):
    import psycopg

    with psycopg.connect(dsn) as c:
        c.execute("SET TIME ZONE 'Asia/Taipei'")
        c.commit()
        yield c


class _Spy:
    def __init__(self, cur, seen):
        self._cur, self._seen = cur, seen

    def __getattr__(self, name):
        return getattr(self._cur, name)

    def execute(self, sql, params=None):
        if sql in sh.TABLE_SQL.values():
            self._cur.execute("SELECT current_setting('transaction_isolation'), "
                              "current_setting('transaction_read_only'), pg_current_snapshot()::text")
            self._seen.append((sql, self._cur.fetchone()))
        return self._cur.execute(sql, params)


@contextmanager
def _spy_connect(dsn, seen):
    with _connect(dsn) as c:
        real_cursor = c.cursor
        c.cursor = lambda *a, **kw: _Spy(real_cursor(*a, **kw), seen)  # type: ignore[method-assign]
        yield c


def test_single_read_only_transaction_five_queries_and_rows_round_trip(dsn):
    seen: list = []
    calls: list = []

    def decisions_for(year, kind, sno):
        calls.append((year, kind, sno))
        return {"0000005604": "W", "0000005731": "L", "0000003639": "SV"}

    p = sh.series_highlights(2026, "E", now=_NOW, connect=lambda: _spy_connect(dsn, seen), decisions_for=decisions_for)
    assert len(seen) == 5 and {s for s, _ in seen} == set(sh.TABLE_SQL.values())
    assert len({ident for _, ident in seen}) == 1 and seen[0][1][:2] == ("repeatable read", "on")
    assert calls == [(2026, "E", 1)]                                   # 只對資料到齊的場取 decisions

    assert p["contract"] == "playoffs-highlights/v1" and p["status"] == "ok"
    assert [(g["series_game_no"], g["data_status"]) for g in p["games"]] == [
        (1, "ok"), (2, "pending"), (3, "pending"), (4, "pending")]
    got = p["games"][0]["input"]
    assert got["game"] == E1["game"]
    assert got["scoreboard"] == E1["scoreboard"]                       # 打亂寫入 ⇒ ORDER BY 還原
    assert got["livelog"] == E1["livelog"]
    assert got["batting"] == E1["batting"]
    # pitching：同隊同局數的相對順序兩邊都未定義 ⇒ 比集合＋排序性質
    assert sorted(map(json.dumps, got["pitching"])) == sorted(map(json.dumps, E1["pitching"]))
    keys = [(r["visiting_home_type"], -(r["inning_pitched_cnt"] or 0)) for r in got["pitching"]]
    assert keys == sorted(keys)
    assert got["decisions"] == {"0000005604": "W", "0000005731": "L", "0000003639": "SV"}
    assert p["games"][1]["input"] is None


def test_c_without_completed_games_and_missing_table_raises(dsn, monkeypatch):
    c = sh.series_highlights(2026, "C", now=_NOW, connect=lambda: _connect(dsn), decisions_for=lambda *a: {})
    assert c["status"] == "no_completed_games" and c["games"] == []
    monkeypatch.setitem(sh.TABLE_SQL, "livelog", sh.LIVELOG_SQL.replace("cpbl.game_livelog", "cpbl.livelog_missing"))
    with pytest.raises(Exception):  # noqa: B017 — router 轉 503；前端逐場焦點顯示待更新
        sh.series_highlights(2026, "E", now=_NOW, connect=lambda: _connect(dsn), decisions_for=lambda *a: {})
