"""#287 WP2／WP3 隔離 DB 演練（opt-in；E1、E2、E6、E7、E8）。

只連卡號隔離庫 cpbl_test_287（見 team_comparison_287_support）；⛔ 不連本機共享 cpbl、⛔ 不連生產。
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
import threading
import time
from datetime import UTC, datetime, timedelta

import psycopg
import pytest
from psycopg_pool import ConnectionPool
from team_comparison_287_support import (
    LOCAL_DB,
    connector,
    isolated_dsn,
    mutated,
    require_real_samples,
    reset_summary,
)

from cpbl import db
from cpbl.api.routers.standings import _team_scoped_metrics
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


def _payload(dsn, year, kind, cur_wrapper=None):
    with psycopg.connect(dsn) as c:
        with c.transaction():
            cur = c.cursor()
            cur.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            return reader.build_payload(cur_wrapper(cur) if cur_wrapper else cur, year, kind, now=NOW)


def _rows(dsn, year):
    with psycopg.connect(dsn) as c:
        cols = ", ".join(core.ROW_COLUMNS)
        rs = c.execute(f"SELECT {cols} FROM cpbl.team_comparison_row r JOIN cpbl.team_comparison_current c "
                       "USING (build_id) WHERE c.year = %s", (year,)).fetchall()
    return {(r[0], r[1], r[2]): dict(zip(core.ROW_COLUMNS, r, strict=True)) for r in rs}


def _pointer(dsn, year):
    with psycopg.connect(dsn) as c:
        return c.execute("SELECT build_id, pending_source_hash, pending_since, promoted_at FROM "
                         "cpbl.team_comparison_current WHERE year = %s", (year,)).fetchone()


def _builds(dsn, year):
    with psycopg.connect(dsn) as c:
        return {r[0] for r in c.execute("SELECT build_id FROM cpbl.team_comparison_build WHERE year = %s",
                                        (year,)).fetchall()}


# ------------------------------------------------------------------ 建置、冪等、E2


def test_build_is_idempotent_and_g_equals_completed_games(dsn):
    for year in (2025, 2026):
        first = _build(dsn, year)
        assert first.code == 0 and first.status == "promoted", first.message
        again = _build(dsn, year)
        assert again.code == 0 and again.status == "no_change"
        rows = _rows(dsn, year)
        season = {k[1]: r for k, r in rows.items() if k[0] == "season"}
        assert len(season) == 6 and {r["games"] for r in season.values()} == {120}
        assert all(r["null_reasons"] == {} for r in rows.values())
        assert len([k for k in rows if k[0] == "head_to_head"]) == 30


def test_immutable_triggers_reject_update_delete_truncate(dsn):
    assert _build(dsn, 2025).code == 0
    for sql in ("UPDATE cpbl.team_comparison_row SET bat_ab = bat_ab + 1",
                "DELETE FROM cpbl.team_comparison_build",
                "TRUNCATE cpbl.team_comparison_row CASCADE",
                "INSERT INTO cpbl.team_comparison_row SELECT * FROM cpbl.team_comparison_row "
                "ON CONFLICT (build_id, scope, team_code, opponent_code) DO UPDATE SET bat_ab = EXCLUDED.bat_ab"):
        with psycopg.connect(dsn) as c, pytest.raises(psycopg.errors.RestrictViolation):
            c.execute(sql)


# ------------------------------------------------------------------ E1：直接 SQL 對帳


def test_e1_season_and_h2h_counts_equal_direct_sql_sums(dsn):
    assert _build(dsn, 2025).code == 0
    rows = _rows(dsn, 2025)
    bat = ", ".join(f"sum(bg.{c})" for c in core.BAT_MAP.values())
    pit = ", ".join(f"sum(pg.{c})" for c in core.PIT_MAP.values())
    team = "CASE x.visiting_home_type WHEN '2' THEN g.home_team_code ELSE g.away_team_code END"
    opp = "CASE x.visiting_home_type WHEN '2' THEN g.away_team_code ELSE g.home_team_code END"
    with psycopg.connect(dsn) as c:
        def q(table, alias, cols, team_code, opponent):
            where = "g.year = 2025 AND g.kind_code = 'A' AND " + team.replace("x.", f"{alias}.") + " = %s"
            params = [team_code]
            if opponent:
                where += " AND " + opp.replace("x.", f"{alias}.") + " = %s"
                params.append(opponent)
            return c.execute(
                f"SELECT {cols} FROM cpbl.{table} {alias} JOIN cpbl.games g ON g.year = {alias}.year "
                f"AND g.kind_code = {alias}.kind_code AND g.game_sno = {alias}.game_sno WHERE {where}",
                params).fetchone()
        for (scope, t, o) in [("season", "AJL011", ""), ("season", "ACN011", ""),
                              ("head_to_head", "ACN011", "AJL011"), ("head_to_head", "AJL011", "ACN011")]:
            r = rows[(scope, t, o)]
            assert list(q("batting_gamelog", "bg", bat, t, o)) == [r[k] for k in core.BAT_MAP], (scope, t, o)
            got = q("pitching_gamelog", "pg", pit + ", sum(pg.inning_pitched_cnt*3 + pg.inning_pitched_div3)",
                    t, o)
            assert list(got) == [r[k] for k in core.PIT_MAP] + [r["pit_outs"]], (scope, t, o)


def test_e1_season_rates_match_team_split_endpoint_path(dsn):
    """全年 A OPS/ERA/WHIP/得失分 ↔ `/api/v1/season/team-split` 的同一聚合路徑（顯示精度內）。"""
    assert _build(dsn, 2025).code == 0
    payload = _payload(dsn, 2025, "C")
    with psycopg.connect(dsn) as c:
        split = _team_scoped_metrics(c.cursor(), 2025, None)
    for team, v in payload["scopes"]["season_a"]["teams"].items():
        m, s = v["metrics"], split[team]
        assert round(m["ops"], 3) == s["ops"]
        assert round(m["era"], 2) == s["era"]
        assert round(m["whip"], 2) == s["whip"]
        assert round(m["rf_pg"], 2) == s["rs_pg"] and round(m["ra_pg"], 2) == s["ra_pg"]
        assert v["counts"]["games"] == s["g"]


def test_e1_h2h_matches_official_standings_and_series_matches_postseason_summary(dsn, monkeypatch):
    assert _build(dsn, 2025).code == 0
    payload = _payload(dsn, 2025, "C")
    h2h = payload["scopes"]["head_to_head_a"]["teams"]
    with psycopg.connect(dsn) as c:
        official = c.execute("SELECT team_code, h2h FROM cpbl.team_standings WHERE year = 2025 AND kind_code = 'A' "
                             "AND season_code = 0 AND team_code IN ('ACN011', 'AJL011')").fetchall()
    for team, h in official:
        opp = "AJL011" if team == "ACN011" else "ACN011"
        w, t, l = (int(x) for x in h[opp].split("-"))
        cnt = h2h[team]["counts"]
        assert (cnt["wins"], cnt["ties"], cnt["losses"]) == (w, t, l)
    from cpbl.api.routers.standings import postseason_summary
    with ConnectionPool(dsn, min_size=0, max_size=2, configure=db._configure) as p:
        monkeypatch.setattr(db, "_pool", p)
        summary = postseason_summary(season=2025, kind_code="A")
    series = payload["scopes"]["series"]
    c_row = next(s for s in summary["series"] if s["kind_code"] == "C")
    wins = {c_row["team1_code"]: c_row["team1_wins"], c_row["team2_code"]: c_row["team2_wins"]}
    assert {t: v["counts"]["wins"] for t, v in series["teams"].items()} == wins
    assert series["status"] == "available" and len(series["covered_game_keys"]) == 5


# ------------------------------------------------------------------ E6：連續紀錄同 scope


def test_e6_season_streak_sequence_matches_special_records(dsn, monkeypatch):
    """全年 A 例行賽結束時連續：同一序列重算最大連勝／連敗與 special_records 一致。"""
    assert _build(dsn, 2025).code == 0
    from cpbl.models import special_records as sr
    with ConnectionPool(dsn, min_size=0, max_size=2, configure=db._configure) as p:
        monkeypatch.setattr(db, "_pool", p)
        out: dict = {}
        sr._add_streaks(2025, "A", out)
    with psycopg.connect(dsn) as c:
        with c.transaction():
            cur = c.cursor()
            cur.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            s = builder.read_source(cur, 2025)  # 以 builder 同一讀取路徑重建序列
    rows = _rows(dsn, 2025)
    for team, rec in out.items():
        seq = [(g.key, g.result_for(team)) for g in core.sort_games(s.games) if team in (g.home, g.away)]
        assert core.max_streaks(seq) == (rec["max_win_streak"], rec["max_lose_streak"]), team
        st = core.trailing_streak(seq)
        r = rows[("season", team, "")]
        assert (r["streak_result"], r["streak_len"], r["streak_through"]) == (st["result"], st["len"], st["through"])


def test_e6_2026_e_and_c_series_are_separate_scopes(dsn):
    assert _build(dsn, 2026).code == 0
    e = _payload(dsn, 2026, "E")["scopes"]["series"]
    c = _payload(dsn, 2026, "C")["scopes"]["series"]
    assert e["status"] == "available" and all(k.startswith("2026/E/") for k in e["expected_game_keys"])
    assert c["status"] == "not_started" and c["expected_game_keys"] == []
    assert e["teams"]["ACN011"]["streak"]["through"].startswith("2026/E/")


# ------------------------------------------------------------------ E7：來源修正失效、原子可見

# 真實 2025 A 第 100 場、依 hitter_acnt 排序的第一列（只做 +1／−1 單點變異並還原）
_PICK = ("SELECT hitter_acnt FROM cpbl.batting_gamelog WHERE year = 2025 AND kind_code = 'A' AND game_sno = 100 "
         "ORDER BY hitter_acnt LIMIT 1")


def _pick(dsn):
    with psycopg.connect(dsn) as c:
        return c.execute(_PICK).fetchone()[0]


def _ab_bump(dsn, delta):
    acnt = _pick(dsn)
    return ("UPDATE cpbl.batting_gamelog SET at_bats = at_bats + %s WHERE year = 2025 AND kind_code = 'A' "
            "AND game_sno = 100 AND hitter_acnt = %s", (delta, acnt))


def test_e7_box_correction_new_build_old_kept_pointer_switched_and_revert(dsn):
    first = _build(dsn, 2025)
    old_id = first.plan.build_id
    up_sql, up_p = _ab_bump(dsn, 1)
    down_sql, down_p = _ab_bump(dsn, -1)
    with mutated(dsn, up_sql, up_p, down_sql, down_p):
        second = _build(dsn, 2025)
        assert second.status == "promoted" and second.plan.build_id != old_id
        assert _builds(dsn, 2025) == {old_id, second.plan.build_id}  # 舊 build 保留
        assert _pointer(dsn, 2025)[0] == second.plan.build_id
    back = _build(dsn, 2025)  # 來源還原 ⇒ 同一 source_hash ⇒ 回到原 build_id
    assert back.status == "promoted" and back.plan.build_id == old_id
    assert _pointer(dsn, 2025)[0] == old_id and len(_builds(dsn, 2025)) == 2


def test_e7_games_change_makes_get_stale_immediately(dsn):
    assert _build(dsn, 2025).code == 0
    assert _payload(dsn, 2025, "C")["scopes"]["season_a"]["status"] == "available"
    sql = ("UPDATE cpbl.games SET away_score = away_score + %s WHERE year = 2025 AND kind_code = 'A' "
           "AND game_sno = 100")
    with mutated(dsn, sql, (1,), sql, (-1,)):
        p = _payload(dsn, 2025, "C")
        assert p["scopes"]["season_a"]["status"] == "stale"
        assert p["scopes"]["season_a"]["source"]["stale_reason"] == "games_changed"
        assert p["scopes"]["head_to_head_a"]["status"] == "stale"
        assert p["scopes"]["series"]["status"] == "available"  # 不連坐
    assert _payload(dsn, 2025, "C")["scopes"]["season_a"]["status"] == "available"


def test_e7_failed_build_rolls_back_marks_pending_and_get_is_stale(dsn, monkeypatch):
    first = _build(dsn, 2025)
    old_id = first.plan.build_id
    real = builder.write_build

    def boom(c, p):
        real(c, p)  # 列已寫入（同交易）……
        raise RuntimeError("模擬建置中途失敗")

    up_sql, up_p = _ab_bump(dsn, 1)
    down_sql, down_p = _ab_bump(dsn, -1)
    with mutated(dsn, up_sql, up_p, down_sql, down_p):
        monkeypatch.setattr(builder, "write_build", boom)
        out = _build(dsn, 2025)
        monkeypatch.setattr(builder, "write_build", real)
        assert out.code == builder.EXIT_FAILED
        ptr = _pointer(dsn, 2025)
        assert ptr[0] == old_id and ptr[1] == out.plan.source_hash and ptr[2] is not None
        assert _builds(dsn, 2025) == {old_id}  # 回滾：新 build 與列都不在
        p = _payload(dsn, 2025, "C")["scopes"]["season_a"]
        assert p["status"] == "stale" and p["source"]["stale_reason"] == "pending_rebuild"
        assert p["source"]["build_id"] == str(old_id)  # 舊版仍可讀，標待更新
    again = _build(dsn, 2025)  # 來源回到 current 同源 ⇒ 清掉 pending
    assert again.status == "no_change" and _pointer(dsn, 2025)[2] is None


def test_e7_killed_build_leaves_pointer_untouched(dsn):
    first = _build(dsn, 2025)
    old_id = first.plan.build_id
    up_sql, up_p = _ab_bump(dsn, 1)
    down_sql, down_p = _ab_bump(dsn, -1)
    code = textwrap.dedent(f"""
        import sys, time, psycopg
        from cpbl.playoffs.team_comparison import builder
        real = builder.write_build
        def slow(c, p):
            real(c, p)
            print("ROWS_WRITTEN", flush=True)
            time.sleep(60)
        builder.write_build = slow
        builder.run_build(lambda: psycopg.connect({dsn!r}), 2025)
    """)
    with mutated(dsn, up_sql, up_p, down_sql, down_p):
        proc = subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.PIPE, text=True)
        try:
            assert proc.stdout.readline().strip() == "ROWS_WRITTEN"
            proc.kill()  # SIGKILL：交易未提交
            proc.wait(timeout=10)
        finally:
            if proc.poll() is None:
                proc.kill()
        time.sleep(0.5)
        ptr = _pointer(dsn, 2025)
        assert ptr[0] == old_id
        assert _builds(dsn, 2025) == {old_id}
        # 審核 F2：強制中止後待更新標記已持久、GET 立即 stale（完整演練見 test_team_comparison_review1 E18）
        assert ptr[1] is not None and ptr[2] is not None
        assert _payload(dsn, 2025, "C")["scopes"]["season_a"]["status"] == "stale"


def test_e7_concurrent_builders_switch_at_most_once(dsn, monkeypatch):
    first = _build(dsn, 2025)
    old_id = first.plan.build_id
    up_sql, up_p = _ab_bump(dsn, 1)
    down_sql, down_p = _ab_bump(dsn, -1)
    barrier = threading.Barrier(2, timeout=30)
    real = builder.write_build

    def racing(c, p):
        barrier.wait()
        real(c, p)

    results = []
    with mutated(dsn, up_sql, up_p, down_sql, down_p):
        monkeypatch.setattr(builder, "write_build", racing)
        ts = [threading.Thread(target=lambda: results.append(_build(dsn, 2025))) for _ in range(2)]
        for t in ts:
            t.start()
        for t in ts:
            t.join(60)
        monkeypatch.setattr(builder, "write_build", real)
        statuses = sorted(r.status for r in results)
        assert statuses == ["already_current", "promoted"], [r.message for r in results]
        new_id = results[0].plan.build_id
        assert _pointer(dsn, 2025)[0] == new_id != old_id
        assert _builds(dsn, 2025) == {old_id, new_id}


def test_e7_readers_only_ever_see_old_or_new(dsn):
    first = _build(dsn, 2025)
    old_id = str(first.plan.build_id)
    seen: list[tuple[str, int]] = []
    stop = threading.Event()

    def read_loop():
        while not stop.is_set():
            p = _payload(dsn, 2025, "C")["scopes"]["season_a"]
            seen.append((p["source"]["build_id"], len(p["teams"])))

    up_sql, up_p = _ab_bump(dsn, 1)
    down_sql, down_p = _ab_bump(dsn, -1)
    t = threading.Thread(target=read_loop)
    t.start()
    try:
        with mutated(dsn, up_sql, up_p, down_sql, down_p):
            new_id = str(_build(dsn, 2025).plan.build_id)
            time.sleep(0.3)
    finally:
        stop.set()
        t.join(30)
    assert seen and {b for b, _ in seen} <= {old_id, new_id} and {n for _, n in seen} == {2}


def test_coverage_incomplete_does_not_switch_and_marks_pending(dsn):
    first = _build(dsn, 2025)
    old_id = first.plan.build_id
    with psycopg.connect(dsn) as c:
        saved = c.execute("SELECT * FROM cpbl.batting_gamelog WHERE year = 2025 AND kind_code = 'A' AND game_sno = 100 "
                          "AND visiting_home_type = '1'").fetchall()
        cols = [d.name for d in c.execute("SELECT * FROM cpbl.batting_gamelog LIMIT 0").description]
        c.execute("DELETE FROM cpbl.batting_gamelog WHERE year = 2025 AND kind_code = 'A' AND game_sno = 100 "
                  "AND visiting_home_type = '1'")
    try:
        out = _build(dsn, 2025)
        assert out.code == builder.EXIT_COVERAGE and "2025/A/100" in out.message
        ptr = _pointer(dsn, 2025)
        assert ptr[0] == old_id and ptr[2] is not None
        assert _builds(dsn, 2025) == {old_id}
    finally:
        with psycopg.connect(dsn) as c:
            c.cursor().executemany(
                f"INSERT INTO cpbl.batting_gamelog ({', '.join(cols)}) VALUES ({', '.join(['%s'] * len(cols))})",
                saved)
    assert _build(dsn, 2025).status == "no_change"


def test_promote_existing_rolls_back_to_previous_build(dsn):
    first = _build(dsn, 2025)
    up_sql, up_p = _ab_bump(dsn, 1)
    down_sql, down_p = _ab_bump(dsn, -1)
    with mutated(dsn, up_sql, up_p, down_sql, down_p):
        new = _build(dsn, 2025)
        assert _pointer(dsn, 2025)[0] == new.plan.build_id
        out = builder.run_promote_existing(connector(dsn), 2025, first.plan.build_id)
        assert out.code == 0 and _pointer(dsn, 2025)[0] == first.plan.build_id
        bad = builder.run_promote_existing(connector(dsn), 2026, first.plan.build_id)
        assert bad.code == builder.EXIT_FAILED


# ------------------------------------------------------------------ E8：GET 不重建、不讀 A gamelog


class RecordingCursor:
    def __init__(self, cur, log):
        self._cur, self._log = cur, log

    def execute(self, sql, params=None, **kw):
        self._log.append((str(sql), params))
        return self._cur.execute(sql, params, **kw)

    def __getattr__(self, name):
        return getattr(self._cur, name)


def _gamelog_kinds(log):
    kinds = []
    for sql, params in log:
        if "_gamelog" in sql:
            kinds.append(params[1] if params and len(params) > 1 else None)
    return kinds


def test_e8_get_reads_no_a_gamelog_and_cold_hot_identical(dsn):
    assert _build(dsn, 2025).code == 0
    logs = []
    for _ in range(2):  # 冷讀、熱讀
        log: list = []
        _payload(dsn, 2025, "C", cur_wrapper=lambda c, log=log: RecordingCursor(c, log))
        logs.append(log)
    assert [s for s, _ in logs[0]] == [s for s, _ in logs[1]]  # 無行程內快取：兩次查詢集合相同
    assert _gamelog_kinds(logs[0]) == ["C", "C"]  # 只讀本系列 E/C gamelog
    for sql, _ in logs[0]:
        low = sql.lower()
        assert "insert" not in low and "update " not in low and "delete" not in low
        for forbidden in ("team_current", "batting_current", "pitching_current", "fielding_current"):
            assert forbidden not in low


def test_e8_missing_summary_does_not_fall_back(dsn):
    log: list = []
    p = _payload(dsn, 2025, "C", cur_wrapper=lambda c: RecordingCursor(c, log))
    assert p["scopes"]["season_a"]["status"] == "summary_missing"
    assert p["scopes"]["head_to_head_a"]["status"] == "summary_missing"
    assert p["scopes"]["series"]["status"] == "available"  # 不連坐
    assert p["status"] == "partial"
    assert _gamelog_kinds(log) == ["C", "C"]
    assert _builds(dsn, 2025) == set()  # GET 不建置
    assert _payload(dsn, 2026, "C")["status"] == "unavailable"  # 摘要缺且本系列未開打


def test_top_level_status_on_real_data(dsn):
    for y in (2025, 2026):
        assert _build(dsn, y).code == 0
    assert _payload(dsn, 2025, "C")["status"] == "ok"
    assert _payload(dsn, 2026, "C")["status"] == "ok"  # 本系列未開打是正常狀態
    assert _payload(dsn, 2026, "E")["status"] == "ok"


def test_series_pending_source_when_one_box_missing(dsn):
    assert _build(dsn, 2025).code == 0
    with psycopg.connect(dsn) as c:
        saved = c.execute("SELECT * FROM cpbl.pitching_gamelog WHERE year = 2025 AND kind_code = 'C' AND game_sno = 5 "
                          "AND visiting_home_type = '2'").fetchall()
        cols = [d.name for d in c.execute("SELECT * FROM cpbl.pitching_gamelog LIMIT 0").description]
        c.execute("DELETE FROM cpbl.pitching_gamelog WHERE year = 2025 AND kind_code = 'C' AND game_sno = 5 "
                  "AND visiting_home_type = '2'")
    try:
        s = _payload(dsn, 2025, "C")["scopes"]["series"]
        assert s["status"] == "pending_source" and s["missing_game_keys"] == ["2025/C/5"]
        assert len(s["covered_game_keys"]) == 4
        for v in s["teams"].values():
            assert v["counts"]["games"] == 5  # 勝敗由 games 判定
            assert v["metrics"]["era"] is not None  # 只對 covered 場加總，非 0、非 null
    finally:
        with psycopg.connect(dsn) as c:
            c.cursor().executemany(
                f"INSERT INTO cpbl.pitching_gamelog ({', '.join(cols)}) VALUES ({', '.join(['%s'] * len(cols))})",
                saved)


def test_style_self_check_equals_team_style_payload(dsn, monkeypatch):
    """builder 自檢：全年 A 七軸 z／排名與球隊頁 team_style_payload 同年同隊逐值相等（只在測試用）。"""
    assert _build(dsn, 2025).code == 0 and _build(dsn, 2026).code == 0
    from cpbl.api import team_style as api_ts
    with ConnectionPool(dsn, min_size=0, max_size=2, configure=db._configure) as pool:
        monkeypatch.setattr(db, "_pool", pool)
        monkeypatch.setattr(api_ts, "conn", db.conn)
        for year, kind in ((2025, "C"), (2026, "E")):
            payload = _payload(dsn, year, kind)
            for team, v in payload["scopes"]["season_a"]["teams"].items():
                page = api_ts.team_style_payload(team)
                season = next(s for s in page["seasons"] if s["year"] == year)
                for axis, entry in v["style"].items():
                    assert round(entry["z"], 4) == season["axes"][axis]["z"], (year, team, axis)
                    assert entry["rank"] == season["axes"][axis]["rank"], (year, team, axis)
    assert reader.AXIS_SEMANTICS == api_ts.AXIS_SEMANTICS


def test_context_version_matches_overview_and_watch_for_same_live_reader(dsn):
    """S04 版本處置：第 2 區 context_version 必須等於同輪 overview 的（同一 live_reader）。"""
    assert _build(dsn, 2025).code == 0
    from cpbl.playoffs.overview import playoffs_overview
    from cpbl.playoffs.watch_reader import playoffs_watch

    def live(*a, **k):
        return None

    conn_ = connector(dsn)
    for year in (2025, 2026):
        ov = playoffs_overview(year, now=NOW, connect=conn_, live_reader=live)
        cmp_ = reader.comparison_payload(year, "C", now=NOW, connect=conn_, live_reader=live)
        wt = playoffs_watch(year, "C", now=NOW, connect=conn_, live_reader=live)
        assert cmp_["context_version"] == ov["context_version"] == wt["context_version"], year
        # 負控：不傳 live_reader 的版本不同（第 1 次合併的缺陷形狀）
        assert reader.comparison_payload(year, "C", now=NOW, connect=conn_)["context_version"] != ov["context_version"]


def test_series_status_is_s02_authority_decided_and_active(dsn):
    """審核 F1：payload 原樣帶出 S02 ``series_status``（T5 顯示條件的唯一依據）。

    真實資料：2025 C 已分勝負（decided）、2026 C 未開打（pending），與同輪 overview 的 S02 區塊一致。
    變異（標示）：把 2025/C/5 的 game_date 單點移到 as_of 之後 ⇒ 該場不算完賽、系列 3:1 未分勝負
    ⇒ S02 判 active；離開時還原。
    """
    from cpbl.playoffs.overview import playoffs_overview

    def live(*a, **k):
        return None

    for y in (2025, 2026):
        assert _build(dsn, y).code == 0
    conn_ = connector(dsn)
    for year, want in ((2025, "decided"), (2026, "pending")):
        cmp_ = reader.comparison_payload(year, "C", now=NOW, connect=conn_, live_reader=live)
        ov = playoffs_overview(year, now=NOW, connect=conn_, live_reader=live)
        assert cmp_["series_status"] == want, year
        assert ov["default_series"] == "C", year  # 同輪 overview 的 C 區塊＝同一份 S02 輸出
        assert ov["series_section"]["current"]["series_status"] == cmp_["series_status"], year

    sql = "UPDATE cpbl.games SET game_date = game_date + %s WHERE year = 2025 AND kind_code = 'C' AND game_sno = 5"
    with mutated(dsn, sql, (timedelta(days=800),), sql, (timedelta(days=-800),)):
        p = reader.comparison_payload(2025, "C", now=NOW, connect=conn_, live_reader=live)
        assert p["series_status"] == "active"
        assert len(p["scopes"]["series"]["expected_game_keys"]) == 4
    assert reader.comparison_payload(2025, "C", now=NOW, connect=conn_, live_reader=live)["series_status"] == "decided"
