"""#287 正式審核退回 F1–F3 的隔離 DB 演練（opt-in；E17、E18、E19）。

只連卡號隔離庫 cpbl_test_287（見 team_comparison_287_support）；⛔ 不連本機共享 cpbl、⛔ 不連生產。

- E17（F1）：本系列統計母體含正式和局（PLAN r4 §4.6）。1990–2026 已完成的 E／C **沒有任何真實正式和局**，
  所以季後和局情境一律是對真實 S02 輸入的**標示變異（負控）**——測試名帶 ``mutation_``，⛔ 不當真實事件；
  無和局的真實資料與真實 A 和局（2025 A-225／A-233、2026 A-23／69／162）是真實樣本。
- E18（F2）：建置寫入中途 SIGKILL（非例外路徑）⇒ 指標不動、待更新標記已持久、GET 立即 ``stale``。
- E19（F3）：CLI 每個分支帶 ``--dry-run`` ⇒ 三表與 ``refresh_log`` 零變化、statement log 零寫入句。
"""

from __future__ import annotations

import dataclasses
import re
import subprocess
import sys
import textwrap
import time
import uuid
from datetime import UTC, date, datetime

import psycopg
import pytest
from team_comparison_287_support import (
    LOCAL_DB,
    connector,
    isolated_dsn,
    mutated,
    require_real_samples,
    reset_summary,
)

from cpbl import db
from cpbl import postseason_contract as pc
from cpbl.ingest import run_build_team_comparison as cli
from cpbl.playoffs.team_comparison import builder, core, reader

NOW = datetime(2026, 10, 15, 4, 0, tzinfo=UTC)


@pytest.fixture
def dsn():
    d = isolated_dsn("CPBL287_TEST_DSN", LOCAL_DB)
    require_real_samples(d)
    reset_summary(d)
    yield d
    reset_summary(d)


def _build(dsn, year):
    return builder.run_build(connector(dsn), year)


def _payload(dsn, year, kind):
    with psycopg.connect(dsn) as c:
        with c.transaction():
            cur = c.cursor()
            cur.execute(pc.READ_ONLY_TXN)
            return reader.build_payload(cur, year, kind, now=NOW)


def _ctx(dsn, year):
    with psycopg.connect(dsn) as c:
        with c.transaction():
            cur = c.cursor()
            cur.execute(pc.READ_ONLY_TXN)
            return pc.compute_series_context(pc.read_series_inputs(cur, year, now=NOW), now=NOW)


def _pointer(dsn, year):
    with psycopg.connect(dsn) as c:
        return c.execute("SELECT build_id, pending_source_hash, pending_since FROM cpbl.team_comparison_current "
                         "WHERE year = %s", (year,)).fetchone()


def _builds(dsn, year):
    with psycopg.connect(dsn) as c:
        return {r[0] for r in c.execute("SELECT build_id FROM cpbl.team_comparison_build WHERE year = %s",
                                        (year,)).fetchall()}


def _sum_box(dsn, year, kind, snos, team, table, col):
    """獨立對照：直接 SQL 逐列加總（不經 core）。主客由 games 判定。"""
    with psycopg.connect(dsn) as c:
        return c.execute(
            f"SELECT COALESCE(sum(t.{col}), 0) FROM cpbl.{table} t JOIN cpbl.games g ON g.year = t.year "
            "AND g.kind_code = t.kind_code AND g.game_sno = t.game_sno WHERE t.year = %s AND t.kind_code = %s "
            "AND t.game_sno = ANY(%s) AND t.visiting_home_type = CASE WHEN g.home_team_code = %s THEN '2' ELSE '1' END",
            (year, kind, list(snos), team)).fetchone()[0]


# 真實系列（無和局）：2025 C AJL011–ACN011 5 場、2026 E ADD011–ACN011 4 場
REAL_SERIES = [(2025, "C", ("ACN011", "AJL011"), 5), (2026, "E", ("ACN011", "ADD011"), 4)]


def _tie_inputs(monkeypatch, year, kind, tie_index, *, only_through_tie):
    """標示變異：把真實 S02 輸入中該 kind 第 ``tie_index`` 場改成正式和局（兩側比分都取較低方）。

    ``only_through_tie``：該 kind 在和局之後的場次改成未完成（模擬「和局當下」的 as_of）。
    gamelog 不動（仍是真實 box）。⛔ 這是負控變異，不是真實事件。
    """
    real = pc.read_series_inputs
    picked: dict = {}

    def fake(cur, y, *, now, live_reader=None):
        inputs = real(cur, y, now=now, live_reader=live_reader)
        mine = sorted((g for g in inputs.games if g.kind_code == kind), key=lambda g: (g.game_date, g.game_sno))
        target = mine[tie_index]
        later = {g.key for g in mine[tie_index + 1:]}
        out = []
        for g in inputs.games:
            if g.key == target.key:
                low = min(g.home_score, g.away_score)
                g = dataclasses.replace(g, home_score=low, away_score=low)
            elif only_through_tie and g.key in later:
                g = dataclasses.replace(g, completed=False, home_score=None, away_score=None)
            out.append(g)
        picked["tie"] = target
        picked["kept"] = list(mine[:tie_index + 1]) + ([] if only_through_tie else list(mine[tie_index + 1:]))
        return dataclasses.replace(inputs, games=out)

    monkeypatch.setattr(pc, "read_series_inputs", fake)
    return picked


# ------------------------------------------------------------------ E17：本系列母體含正式和局（F1）


@pytest.mark.parametrize(("year", "kind", "teams", "n"), REAL_SERIES)
def test_e17c_real_series_without_ties_population_equals_counted(dsn, year, kind, teams, n):
    """(c) 未改動的真實資料：§4.6 母體＝S02 counted_game_keys（無和局時兩者相同，非和局路徑不變）。"""
    ctx = _ctx(dsn, year)
    counted = [f"{k['year']}/{k['kind_code']}/{k['game_sno']}" for k in ctx["series"][kind]["counted_game_keys"]]
    pop = [core.key_str(g.key) for g in reader.series_population(ctx, year, kind, list(teams))]
    assert pop == counted and len(pop) == n
    assert all(g["result"] != "tie" for g in ctx["games"] if g["game_key"]["kind_code"] == kind)  # 真實無和局
    s = _payload(dsn, year, kind)["scopes"]["series"]
    assert s["expected_game_keys"] == counted and s["status"] == "available"
    assert s["conflict_reason"] is None


def test_e17c_real_2026_c_not_started_both_empty(dsn):
    ctx = _ctx(dsn, 2026)
    assert ctx["series"]["C"]["counted_game_keys"] == []
    teams = [t for t in ctx["series"]["C"]["series_id"]["teams"] if t]
    assert reader.series_population(ctx, 2026, "C", teams) == []
    assert _payload(dsn, 2026, "C")["scopes"]["series"]["status"] == "not_started"


@pytest.mark.parametrize(("year", "kind", "teams", "n"), REAL_SERIES)
def test_e17a_mutation_first_game_tie_is_not_not_started(dsn, monkeypatch, year, kind, teams, n):
    """(a) 標示變異：首場改正式和局且其後未完成 ⇒ S02 counted=[]，但本系列非 not_started、含該場 box。"""
    picked = _tie_inputs(monkeypatch, year, kind, 0, only_through_tie=True)
    ctx = _ctx(dsn, year)
    assert ctx["series"][kind]["counted_game_keys"] == []  # 勝場母體不含和局
    tie = picked["tie"]
    key = f"{year}/{kind}/{tie.game_sno}"
    s = _payload(dsn, year, kind)["scopes"]["series"]
    assert s["status"] == "available"  # ⛔ 不是 not_started
    assert s["expected_game_keys"] == [key] and s["covered_game_keys"] == [key] and s["missing_game_keys"] == []
    for t in teams:
        v = s["teams"][t]
        assert (v["counts"]["games"], v["counts"]["wins"], v["counts"]["losses"], v["counts"]["ties"]) == (1, 0, 0, 1)
        assert v["counts"]["bat_pa"] == _sum_box(dsn, year, kind, [tie.game_sno], t, "batting_gamelog",
                                                 "plate_appearances") > 0
        assert v["counts"]["bat_so"] == _sum_box(dsn, year, kind, [tie.game_sno], t, "batting_gamelog", "so")
        assert v["streak"] == {"result": "T", "len": 1, "through": key}
        assert v["sample"]["games"] == 1


@pytest.mark.parametrize(("year", "kind", "teams", "n"), REAL_SERIES)
def test_e17b_mutation_middle_game_tie_stays_in_population(dsn, monkeypatch, year, kind, teams, n):
    """(b) 標示變異：中間一場改正式和局 ⇒ 仍在 expected／covered、計數與分母，連續紀錄在該場中斷。"""
    mid = n // 2
    picked = _tie_inputs(monkeypatch, year, kind, mid, only_through_tie=False)
    ctx = _ctx(dsn, year)
    tie = picked["tie"]
    tie_key = f"{year}/{kind}/{tie.game_sno}"
    counted = [f"{k['year']}/{k['kind_code']}/{k['game_sno']}" for k in ctx["series"][kind]["counted_game_keys"]]
    assert tie_key not in counted  # S02 勝場母體排除和局
    s = _payload(dsn, year, kind)["scopes"]["series"]
    games = picked["kept"]
    keys = [f"{year}/{kind}/{g.game_sno}" for g in games]
    assert s["expected_game_keys"] == keys and s["covered_game_keys"] == keys and tie_key in keys
    snos = [g.game_sno for g in games]
    for t in teams:
        v = s["teams"][t]
        res = []
        for g in games:
            if g.key == tie.key:
                res.append("T")
                continue
            us, them = ((g.home_score, g.away_score) if g.home_team_code == t else (g.away_score, g.home_score))
            res.append("W" if us > them else "L")
        assert v["counts"]["games"] == n and v["counts"]["ties"] == 1
        assert (v["counts"]["wins"], v["counts"]["losses"]) == (res.count("W"), res.count("L"))
        assert v["counts"]["bat_pa"] == _sum_box(dsn, year, kind, snos, t, "batting_gamelog", "plate_appearances")
        assert v["counts"]["pit_er"] == _sum_box(dsn, year, kind, snos, t, "pitching_gamelog", "earned_runs")
        last, ln = res[-1], 0  # 獨立重算結尾連續段：和局中斷
        for r in reversed(res):
            if r != last:
                break
            ln += 1
        assert v["streak"] == {"result": last, "len": ln, "through": keys[-1]}
        assert ln <= n - 1 - mid  # 不跨過和局


def test_e17_mutation_end_to_end_db_first_game_tie(dsn):
    """(a) 經真實 GET 讀取入口的 DB 變異版：2026 E 第 1 場比分改成相等（離開即還原）。"""
    q = "SELECT home_score, away_score FROM cpbl.games WHERE year = 2026 AND kind_code = 'E' AND game_sno = 1"
    with psycopg.connect(dsn) as c:
        hs, as_ = c.execute(q).fetchone()
    low = min(hs, as_)
    sql = "UPDATE cpbl.games SET home_score = %s, away_score = %s WHERE year = 2026 AND kind_code = 'E' AND game_sno = 1"
    with mutated(dsn, sql, (low, low), sql, (hs, as_)):
        p = reader.comparison_payload(2026, "E", now=NOW, connect=connector(dsn))
        s = p["scopes"]["series"]
        assert "2026/E/1" in s["expected_game_keys"] and len(s["expected_game_keys"]) == 4
        assert all(v["counts"]["ties"] == 1 and v["counts"]["games"] == 4 for v in s["teams"].values())
    with psycopg.connect(dsn) as c:
        assert c.execute(q).fetchone() == (hs, as_)


REAL_A_TIES = [(2025, 225), (2025, 233), (2026, 23), (2026, 69), (2026, 162)]


def test_e17_real_a_ties_counted_and_break_streaks(dsn):
    """真實 A 和局（2025 A-233 0:0 靠完賽證據）：進 G 與 ties、連續紀錄在該場中斷。"""
    for year in (2025, 2026):
        assert _build(dsn, year).code == 0
    for year, sno in REAL_A_TIES:
        with psycopg.connect(dsn) as c:
            with c.transaction():
                cur = c.cursor()
                cur.execute(pc.READ_ONLY_TXN)
                src = builder.read_source(cur, year)
                rows = {r["team_code"]: r for r in reader._rows(
                    cur, "SELECT r.* FROM cpbl.team_comparison_row r JOIN cpbl.team_comparison_current c "
                    "USING (build_id) WHERE c.year = %s AND r.scope = 'season'", (year,))}
        g = next(g for g in src.games if g.key == (year, "A", sno))  # 和局在 builder 母體內
        assert g.home_score == g.away_score
        for team in (g.home, g.away):
            mine = core.sort_games([x for x in src.games if team in (x.home, x.away)])
            seq = [(x.key, x.result_for(team)) for x in mine]
            assert rows[team]["ties"] == sum(1 for _, r in seq if r == "T")
            assert rows[team]["games"] == len(seq)
            i = next(j for j, (k, _) in enumerate(seq) if k == g.key)
            assert core.trailing_streak(seq[:i + 1])["result"] == "T"
            if i + 1 < len(seq) and seq[i + 1][1] != "T":
                assert core.trailing_streak(seq[:i + 2])["len"] == 1  # 和局後重新起算


# ------------------------------------------------------------------ E18：強制中止留待更新（F2）

_PICK = ("SELECT hitter_acnt FROM cpbl.batting_gamelog WHERE year = 2025 AND kind_code = 'A' AND game_sno = 100 "
         "ORDER BY hitter_acnt LIMIT 1")


def _ab_bump(dsn, delta):
    with psycopg.connect(dsn) as c:
        acnt = c.execute(_PICK).fetchone()[0]
    return ("UPDATE cpbl.batting_gamelog SET at_bats = at_bats + %s WHERE year = 2025 AND kind_code = 'A' "
            "AND game_sno = 100 AND hitter_acnt = %s", (delta, acnt))


def test_e18_sigkill_mid_write_leaves_pending_and_get_stale_then_rebuild_clears(dsn):
    first = _build(dsn, 2025)
    old_id = first.plan.build_id
    old_fp = first.plan.games_fingerprint
    assert _pointer(dsn, 2025)[2] is None
    code = textwrap.dedent(f"""
        import time, psycopg
        from cpbl.playoffs.team_comparison import builder
        real = builder.write_build
        def slow(c, p):
            real(c, p)
            print("ROWS_WRITTEN", p.source_hash, flush=True)
            time.sleep(60)
        builder.write_build = slow
        builder.run_build(lambda: psycopg.connect({dsn!r}), 2025)
    """)
    up_sql, up_p = _ab_bump(dsn, 1)
    down_sql, down_p = _ab_bump(dsn, -1)
    with mutated(dsn, up_sql, up_p, down_sql, down_p):  # 只改 box：games 指紋不變（審核 F2 情境）
        proc = subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.PIPE, text=True)
        try:
            tag, new_hash = proc.stdout.readline().split()
            assert tag == "ROWS_WRITTEN"
            proc.kill()  # SIGKILL：善後分支不會執行、交易未提交
            proc.wait(timeout=10)
        finally:
            if proc.poll() is None:
                proc.kill()
        time.sleep(0.5)
        ptr = _pointer(dsn, 2025)
        assert ptr[0] == old_id  # 指標不動
        assert ptr[1] == new_hash and ptr[2] is not None  # 待更新標記已持久
        assert _builds(dsn, 2025) == {old_id}  # 回滾：新 build 不在
        p = _payload(dsn, 2025, "C")["scopes"]["season_a"]
        assert p["source"]["games_fingerprint"] == old_fp  # games 指紋確實沒變
        assert p["status"] == "stale" and p["source"]["stale_reason"] == "pending_rebuild"
        assert p["source"]["build_id"] == str(old_id)
        again = _build(dsn, 2025)  # 再次正常建置 ⇒ 切換並清除
        assert again.status == "promoted" and again.plan.source_hash == new_hash
        ptr = _pointer(dsn, 2025)
        assert ptr[0] == again.plan.build_id and ptr[1] is None and ptr[2] is None
        assert _payload(dsn, 2025, "C")["scopes"]["season_a"]["status"] == "available"
    back = _build(dsn, 2025)
    assert back.plan.build_id == old_id and _pointer(dsn, 2025)[2] is None


def test_e18_pending_marked_before_write_transaction_opens(dsn, monkeypatch):
    """順序：待更新標記先提交，寫入交易才開始（另一連線在寫入當下就看得到已提交的標記）。"""
    assert _build(dsn, 2025).code == 0
    seen = {}
    real = builder.write_build

    def spy(c, p):
        with psycopg.connect(dsn) as other:
            seen["pending"] = other.execute("SELECT pending_source_hash FROM cpbl.team_comparison_current "
                                            "WHERE year = 2025").fetchone()[0]
        real(c, p)

    up_sql, up_p = _ab_bump(dsn, 1)
    down_sql, down_p = _ab_bump(dsn, -1)
    with mutated(dsn, up_sql, up_p, down_sql, down_p):
        monkeypatch.setattr(builder, "write_build", spy)
        out = _build(dsn, 2025)
        assert out.status == "promoted" and seen["pending"] == out.plan.source_hash
        assert _pointer(dsn, 2025)[2] is None  # 切換同交易清除
    monkeypatch.setattr(builder, "write_build", real)
    assert _build(dsn, 2025).status == "promoted"


def test_e18_premark_failure_aborts_without_writing(dsn, monkeypatch):
    first = _build(dsn, 2025)

    def boom(*a, **k):
        raise psycopg.OperationalError("模擬標記寫入失敗")

    up_sql, up_p = _ab_bump(dsn, 1)
    down_sql, down_p = _ab_bump(dsn, -1)
    with mutated(dsn, up_sql, up_p, down_sql, down_p):
        monkeypatch.setattr(builder, "mark_pending_before_write", boom)
        out = _build(dsn, 2025)
        assert out.code == builder.EXIT_FAILED and "未寫入" in out.message
        assert _builds(dsn, 2025) == {first.plan.build_id}
        assert _pointer(dsn, 2025)[0] == first.plan.build_id


# ------------------------------------------------------------------ E19：--dry-run 不寫（F3）

_WRITE_RE = re.compile(r"^\s*(INSERT|UPDATE|DELETE|TRUNCATE|ALTER|CREATE|DROP|MERGE|COPY)\b", re.I)


class _RecCur:
    def __init__(self, cur, log):
        self._cur, self._log = cur, log

    def execute(self, sql, params=None, **kw):
        self._log.append(str(sql))
        return self._cur.execute(sql, params, **kw)

    def executemany(self, sql, seq, **kw):
        self._log.append(str(sql))
        return self._cur.executemany(sql, seq, **kw)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return self._cur.__exit__(*exc)

    def __getattr__(self, name):
        return getattr(self._cur, name)


class _RecConn:
    """包住 psycopg 連線，記錄經 ``execute``／``executemany`` 送出的每一句（in-process statement log）。"""

    def __init__(self, c, log):
        self._c, self._log = c, log

    def execute(self, sql, params=None, **kw):
        self._log.append(str(sql))
        return self._c.execute(sql, params, **kw)

    def cursor(self, *a, **kw):
        return _RecCur(self._c.cursor(*a, **kw), self._log)

    def __enter__(self):
        self._c.__enter__()
        return self

    def __exit__(self, *exc):
        return self._c.__exit__(*exc)

    def __getattr__(self, name):
        return getattr(self._c, name)


_DIGEST_SQL = {
    t: f"SELECT count(*), md5(COALESCE(string_agg(x::text, '|' ORDER BY x::text), '')) FROM cpbl.{t} x"
    for t in ("team_comparison_build", "team_comparison_row", "team_comparison_current", "refresh_log")
}


def _digest(dsn):
    with psycopg.connect(dsn) as c:
        return {t: c.execute(sql).fetchone() for t, sql in _DIGEST_SQL.items()}


def _run_cli(dsn, monkeypatch, argv):
    log: list[str] = []
    monkeypatch.setattr(db, "conn", lambda: _RecConn(psycopg.connect(dsn), log))
    code = cli.main(argv)
    return code, log


def _assert_no_write(log):
    writes = [s for s in log if _WRITE_RE.match(s)]
    assert log and writes == [], writes


def test_e19_recorder_negative_control_sees_writes(dsn, monkeypatch):
    """負控：同一錄製器在非 dry-run 下必須抓到寫入句，否則「零寫入」是空證據。"""
    code, log = _run_cli(dsn, monkeypatch, ["--year", "2025"])
    assert code == 0 and any(_WRITE_RE.match(s) for s in log)


def test_e19_dry_run_build_first_time(dsn, monkeypatch, capsys):
    before = _digest(dsn)
    code, log = _run_cli(dsn, monkeypatch, ["--year", "2025", "--dry-run"])
    assert code == 0 and "TEAM_COMPARISON_BUILD=dry_run" in capsys.readouterr().out
    _assert_no_write(log)
    assert _digest(dsn) == before


def test_e19_dry_run_build_with_changed_source(dsn, monkeypatch, capsys):
    assert _build(dsn, 2025).code == 0
    up_sql, up_p = _ab_bump(dsn, 1)
    down_sql, down_p = _ab_bump(dsn, -1)
    with mutated(dsn, up_sql, up_p, down_sql, down_p):
        before = _digest(dsn)
        code, log = _run_cli(dsn, monkeypatch, ["--year", "2025", "--dry-run", "--record-failure"])
        assert code == 0 and "TEAM_COMPARISON_BUILD=dry_run" in capsys.readouterr().out
        _assert_no_write(log)
        assert _digest(dsn) == before and _pointer(dsn, 2025)[2] is None  # 也不預先標待更新


def test_e19_dry_run_no_op_keeps_pending(dsn, monkeypatch, capsys):
    assert _build(dsn, 2025).code == 0
    assert builder.mark_pending(connector(dsn), 2025, "e19" * 8 + "0" * 40)  # 測試前置：讓 no-op 分支有東西可清
    before = _digest(dsn)
    code, log = _run_cli(dsn, monkeypatch, ["--year", "2025", "--dry-run"])
    assert code == 0 and "TEAM_COMPARISON_BUILD=no_change" in capsys.readouterr().out
    _assert_no_write(log)
    assert _digest(dsn) == before and _pointer(dsn, 2025)[1] == "e19" * 8 + "0" * 40


def test_e19_dry_run_promote_existing(dsn, monkeypatch, capsys):
    first = _build(dsn, 2025)
    up_sql, up_p = _ab_bump(dsn, 1)
    down_sql, down_p = _ab_bump(dsn, -1)
    with mutated(dsn, up_sql, up_p, down_sql, down_p):
        new = _build(dsn, 2025)
    before = _digest(dsn)
    code, log = _run_cli(dsn, monkeypatch,
                         ["--year", "2025", "--dry-run", "--promote-existing", str(first.plan.build_id)])
    assert code == 0 and "TEAM_COMPARISON_BUILD=dry_run" in capsys.readouterr().out
    _assert_no_write(log)
    assert _digest(dsn) == before and _pointer(dsn, 2025)[0] == new.plan.build_id


def test_e19_dry_run_record_failure_on_failed_promote(dsn, monkeypatch, capsys):
    assert _build(dsn, 2025).code == 0
    before = _digest(dsn)
    code, log = _run_cli(dsn, monkeypatch, ["--year", "2025", "--dry-run", "--record-failure",
                                            "--promote-existing", str(uuid.UUID(int=287))])
    assert code == builder.EXIT_FAILED and "不寫 refresh_log" in capsys.readouterr().err
    _assert_no_write(log)
    assert _digest(dsn) == before


def test_e19_dry_run_record_failure_on_coverage_incomplete(dsn, monkeypatch, capsys):
    assert _build(dsn, 2025).code == 0
    where = "year = 2025 AND kind_code = 'A' AND game_sno = 100 AND visiting_home_type = '1'"
    with psycopg.connect(dsn) as c:
        saved = c.execute(f"SELECT * FROM cpbl.batting_gamelog WHERE {where}").fetchall()
        cols = [d.name for d in c.execute("SELECT * FROM cpbl.batting_gamelog LIMIT 0").description]
        c.execute(f"DELETE FROM cpbl.batting_gamelog WHERE {where}")
    try:
        before = _digest(dsn)
        code, log = _run_cli(dsn, monkeypatch, ["--year", "2025", "--dry-run", "--record-failure"])
        err = capsys.readouterr().err
        assert code == builder.EXIT_COVERAGE and "不寫 refresh_log" in err
        _assert_no_write(log)
        assert _digest(dsn) == before and _pointer(dsn, 2025)[2] is None
    finally:
        with psycopg.connect(dsn) as c:
            c.cursor().executemany(
                f"INSERT INTO cpbl.batting_gamelog ({', '.join(cols)}) VALUES ({', '.join(['%s'] * len(cols))})",
                saved)


def test_e19_dry_run_missing_tables_branch(dsn, monkeypatch, capsys):
    """缺表分支：以不存在的 regclass 名稱讓真實存在性查詢回 false（標示變異；不改隔離庫 schema）。"""
    monkeypatch.setattr(builder, "TABLES_EXIST_SQL",
                        "SELECT to_regclass('cpbl.team_comparison_build_absent_287') IS NOT NULL")
    before = _digest(dsn)
    code, log = _run_cli(dsn, monkeypatch, ["--year", "2025", "--dry-run", "--record-failure"])
    assert code == builder.EXIT_NO_TABLES and "no_tables" in capsys.readouterr().err
    _assert_no_write(log)
    assert _digest(dsn) == before


def test_e17_unit_population_skips_non_pair_and_incomplete():
    """純函式：非兩隊同 kind 完賽場與未完成場不入母體；和局入母體（ctx 只構造 S02 欄位形狀，非資料樣本）。"""
    def g(sno, d, away, home, a, h, done=True, kind="C"):
        return {"game_key": {"year": 2025, "kind_code": kind, "game_sno": sno}, "official_game_sno": sno,
                "game_date": d, "completed": done, "away_team_code": away, "home_team_code": home,
                "away_score": a, "home_score": h}
    ctx = {"games": [g(2, "2025-10-19", "B", "A", 1, 1), g(1, "2025-10-18", "A", "B", 3, 0),
                     g(3, "2025-10-20", "A", "Z", 2, 1), g(4, "2025-10-21", "A", "B", None, None, done=False),
                     g(9, "2025-10-10", "A", "B", 5, 4, kind="E")]}
    pop = reader.series_population(ctx, 2025, "C", ["A", "B"])
    assert [p.key for p in pop] == [(2025, "C", 1), (2025, "C", 2)]
    assert pop[1].home_score == pop[1].away_score
    assert reader.series_population(ctx, 2025, "C", ["A"]) == []
    assert isinstance(pop[0].game_date, date)
