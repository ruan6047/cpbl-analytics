"""#289 S08 WP2：watch reader 的 SQL 語意（opt-in 隔離 DB）。

只連本卡隔離資源：``CPBL289_TEST_DSN``＝容器 cpbl289-pg（127.0.0.1:55289）的 cpbl_test_289；
未設＝skip（⛔ skip 不算通過），設錯＝fail。schema 由真實 ``migrations/`` 全套建立（``db.migrate``）。
場次、box、名單皆為**合成形狀**，用來驗只有真 SQL 才看得出的事：

1. 完賽判定沿 ``completed_games_sql_with_evidence``；box 依 ``visiting_home_type`` 分客／主。
2. 保留賽以 ``orig_date`` 落入窗口；二軍 ``*022`` 場次納入；他隊場次不入。
3. 名單只取投手、角色取最新版本；名單缺 ⇒ 不列投手。
4. 查詢次數與名單投手人數無關（ANY 批次，非 N+1）。
5. 整個讀取在 READ ONLY 交易內完成（GET 不寫入）。
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, date, datetime

import pytest
from psycopg.conninfo import conninfo_to_dict
from psycopg_pool import ConnectionPool

from cpbl import db
from cpbl.playoffs import watch_reader as wrd

EXPECTED = ("127.0.0.1", "55289", "cpbl_test_289")
NOW = datetime(2026, 10, 17, 2, 0, tzinfo=UTC)  # 台北 10/17 10:00，C1 賽前
AWAY, HOME = "ACN011", "AAA011"


@pytest.fixture(scope="module")
def dsn():
    import os

    value = os.environ.get("CPBL289_TEST_DSN")
    if not value:
        pytest.skip("CPBL289_TEST_DSN 未設（#289 隔離 DB 測試為 opt-in）")
    d = conninfo_to_dict(value)
    if (d.get("host"), str(d.get("port")), d.get("dbname")) != EXPECTED:
        pytest.fail(f"CPBL289_TEST_DSN 不在 #289 隔離資源 {EXPECTED}", pytrace=False)
    return value


_RESET = """
SET session_replication_role = replica;
TRUNCATE cpbl.roster_annotation_revision, cpbl.series_roster_member, cpbl.series_roster CASCADE;
TRUNCATE cpbl.pitching_gamelog, cpbl.games, cpbl.game_schedule_status_revisions,
         cpbl.game_lineup_announcement_revisions, cpbl.game_completion_evidence;
SET session_replication_role = origin;
"""


def _games(c):
    # (kind, season_code, sno, date, away, home, away_score, home_score, delay_kind, orig_date)
    rows = [
        ("C", "0", 1, date(2026, 10, 17), AWAY, HOME, 0, 0, None, None),             # 目標場（未開打）
        ("E", "0", 3, date(2026, 10, 16), "ADD011", AWAY, 1, 5, None, None),          # D−1 完賽、客隊無 box
        ("A", "2", 274, date(2026, 10, 30), AWAY, "AEO011", 0, 0, "保留", date(2026, 10, 15)),  # D−2 保留未完
        ("D", "2", 88, date(2026, 10, 14), "AAA022", "AJL022", 3, 2, None, None),     # D−3 二軍完賽有 box
        ("A", "2", 300, date(2026, 10, 15), "ADD011", "AEO011", 2, 1, None, None),    # 他隊場次
        ("A", "2", 10, date(2026, 9, 1), AWAY, HOME, 4, 3, None, None),              # 窗口外、供最近登板
        ("A", "2", 11, date(2026, 9, 2), HOME, AWAY, 1, 0, None, None),
    ]
    for k, sc, sno, d, a, h, asc, hsc, dk, od in rows:
        c.execute("INSERT INTO cpbl.games (year, kind_code, game_season_code, game_sno, game_date, "
                  "away_team_code, home_team_code, away_score, home_score, delay_kind, orig_date) "
                  "VALUES (2026,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", (k, sc, sno, d, a, h, asc, hsc, dk, od))
    # E3：2026 季後走「官方 final 或完賽證據」；以完賽證據表示已完賽
    c.execute("INSERT INTO cpbl.game_completion_evidence (year, kind_code, game_sno, evidence_kind) "
              "VALUES (2026,'E',3,'official_box_final')")


def _scheduled_c1(c):
    """C1 官方賽程版本：PresentStatus=1、GameResult 空 ⇒ official scheduled（賽前）。"""
    c.execute("INSERT INTO cpbl.game_schedule_status_revisions (year, kind_code, game_sno, raw_present_status, "
              "raw_game_result, raw_game_date, payload_hash, raw_payload, fetched_at, last_seen_at) "
              "VALUES (2026,'C',1,1,'','2026-10-17','h-c1','{}','2026-10-16T02:10:00Z','2026-10-16T02:10:00Z')")


def _pitching(c, rows):
    for kind, sno, pid, vht, pitches, ipc, div3, er in rows:
        c.execute("INSERT INTO cpbl.pitching_gamelog (year, kind_code, game_sno, pitcher_acnt, visiting_home_type, "
                  "role_type, pitch_cnt, inning_pitched_cnt, inning_pitched_div3, earned_runs) "
                  "VALUES (2026,%s,%s,%s,%s,'中繼',%s,%s,%s,%s)", (kind, sno, pid, vht, pitches, ipc, div3, er))


def _roster(c, team, pitchers: dict[str, str], *, revision2: dict[str, str] | None = None):
    """32 人名單（前 N 人為投手）＋角色版本 1（可選版本 2）；滿足 076 的完整性約束。"""
    rid = uuid.uuid4()
    ids = list(pitchers) + [f"99{team[:3].encode().hex()[:4]}{i:04d}"[:10] for i in range(32 - len(pitchers))]
    h = hashlib.sha256(team.encode()).hexdigest()
    with c.transaction():
        c.execute("INSERT INTO cpbl.series_roster (roster_id, year, kind_code, team_code, source_url, published_date, "
                  "published_precision, observed_at, observation_basis, identity_verified_at, input_origin, raw_text, "
                  "hash_version, membership_hash, source_hash, import_check) VALUES "
                  "(%s,2026,'C',%s,'https://www.cpbl.com.tw/test','2026-10-16','date',now(),'cli_input',now(),"
                  "'pasted_text','fixture',1,%s,%s,'{}')", (rid, team, h, h))
        for i, pid in enumerate(ids):
            pos = "投手" if pid in pitchers else ("捕手", "內野手", "外野手")[i % 3]
            c.execute("INSERT INTO cpbl.series_roster_member VALUES (%s,%s,%s,%s)", (rid, pid, pos, f"球員{i}"))
        for rev, roles in ((1, pitchers), (2, revision2)):
            if roles is None:
                continue
            for pid in ids:
                c.execute("INSERT INTO cpbl.roster_annotation_revision (roster_id, revision, player_id, tactical_role, "
                          "revision_hash) VALUES (%s,%s,%s,%s,%s)",
                          (rid, rev, pid, roles.get(pid, "unclassified"), hashlib.sha256(f"{rev}".encode()).hexdigest()))


@pytest.fixture
def pool(dsn, monkeypatch):
    with ConnectionPool(dsn, min_size=0, max_size=4, timeout=5, configure=db._configure) as p:
        monkeypatch.setattr(db, "_pool", p)
        with db.conn() as c:
            assert c.execute("SELECT current_database()").fetchone()[0] == EXPECTED[2]
        db.migrate()
        with db.conn() as c:
            c.execute(_RESET)
            _games(c)
            _scheduled_c1(c)
        yield p


class CountingCursor:
    def __init__(self, cur):
        self._cur = cur
        self.n = 0

    def execute(self, *a, **kw):
        self.n += 1
        return self._cur.execute(*a, **kw)

    def __getattr__(self, name):
        return getattr(self._cur, name)


def _read():
    with db.conn() as c, c.transaction():
        cur = CountingCursor(c.cursor())
        cur.execute(wrd.READ_ONLY_TXN)
        inputs = wrd.read_watch_inputs(cur, 2026, "C", now=NOW)
        assert c.execute("SHOW transaction_read_only").fetchone()[0] == "on"
    return inputs, cur.n


def test_window_games_semantics(pool):
    inputs, _ = _read()
    keys = {(g["kind_code"], g["game_sno"]): g for g in inputs.window_games}
    assert set(keys) == {("C", 1), ("E", 3), ("A", 274), ("D", 88)}  # 他隊 A300、窗口外不入
    assert keys[("E", 3)]["completed"] is True
    assert keys[("C", 1)]["completed"] is False
    assert keys[("A", 274)]["completed"] is False  # 保留賽補賽日在未來
    w = wrd.compute_watch(inputs, now=NOW)
    days = {t["team_code"]: {d["offset"]: d["reasons"] for d in t["days"]} for t in w["teams"]}
    assert days[AWAY][1] == ["box_missing"]          # E3 完賽但 ACN011（主隊）無 box
    assert days[AWAY][2] == ["game_not_final"]       # 保留賽開賽日 10/15
    assert days[HOME][3] == ["box_missing"]          # 二軍 AAA022 客場、無 box
    assert days[HOME][0] == [] and days[AWAY][0] == []  # 目標場賽前 ⇒ 有證據的 0


def test_target_without_schedule_revision_is_unknown(pool):
    with db.conn() as c:
        c.execute("DELETE FROM cpbl.game_schedule_status_revisions")
    w = wrd.compute_watch(_read()[0], now=NOW)
    assert w["target"]["target_status"] == "unknown"
    for t in w["teams"]:
        assert next(d for d in t["days"] if d["offset"] == 0)["reasons"] == ["schedule_unavailable"]


def test_box_side_by_visiting_home_type(pool):
    with db.conn() as c:
        _pitching(c, [("E", 3, "0000000001", "2", 20, 1, 0, 0)])   # 主隊 ACN011 box
        _pitching(c, [("D", 88, "0000000002", "1", 25, 2, 0, 0)])  # 二軍客隊 AAA022 box
    inputs, _ = _read()
    w = wrd.compute_watch(inputs, now=NOW)
    days = {t["team_code"]: {d["offset"]: d["reasons"] for d in t["days"]} for t in w["teams"]}
    assert days[AWAY][1] == []        # E3 主隊＝ACN011，有 vht=2 box
    assert days[HOME][3] == []        # AAA022 客隊有 vht=1 box


def test_roster_pitchers_latest_role_and_appearances(pool):
    with db.conn() as c:
        _roster(c, AWAY, {"0000000001": "終結", "0000000003": "輪值"},
                revision2={"0000000001": "勝利組", "0000000003": "輪值"})
        _pitching(c, [("E", 3, "0000000001", "2", 20, 1, 0, 0),
                      ("A", 10, "0000000001", "1", 12, 1, 0, 1), ("A", 11, "0000000001", "2", 14, 0, 2, 0)])
    inputs, _ = _read()
    assert inputs.rosters[HOME] is None
    r = inputs.rosters[AWAY]
    assert r["annotation_version"] == 2
    assert {m["player_id"]: m["tactical_role"] for m in r["members"]} == {"0000000001": "勝利組", "0000000003": "輪值"}
    apps = inputs.appearances["0000000001"]
    assert [a.game_key for a in apps] == [(2026, "A", 10), (2026, "A", 11), (2026, "E", 3)]
    assert apps[1].outs == 2
    w = wrd.compute_watch(inputs, now=NOW)
    t = {x["team_code"]: x for x in w["teams"]}
    assert t[HOME]["pitchers"] == [] and t[HOME]["roster_status"] == "missing"
    p = {x["player_id"]: x for x in t[AWAY]["pitchers"]}
    assert p["0000000001"]["load"]["level"] == "unknown"   # D−2 保留賽未完 ⇒ 灰
    assert p["0000000001"]["load"]["metrics"]["P1"] == 20  # 已知球數仍列
    assert p["0000000001"]["consecutive_era"] is None


def test_query_count_independent_of_pitchers(pool):
    with db.conn() as c:
        _roster(c, AWAY, {"0000000001": "終結"})
    _, n_small = _read()
    with db.conn() as c:
        c.execute(_RESET)
        _games(c)
        _scheduled_c1(c)
        _roster(c, AWAY, {f"00000001{i:02d}": "勝利組" for i in range(16)})
        _roster(c, HOME, {f"00000002{i:02d}": "長中繼" for i in range(16)})
    inputs, n_large = _read()
    assert sum(len(r["members"]) for r in inputs.rosters.values() if r) == 32
    assert n_small == n_large


def test_end_to_end_read_only(pool):
    w = wrd.playoffs_watch(2026, "C", now=NOW, connect=db.conn)
    assert w["status"] == "ok" and w["publication"]["status"] == "not_published"
    assert {m["source"] for m in w["source_manifest"]} >= {"series_roster", "window_games", "lineup_announcement"}
