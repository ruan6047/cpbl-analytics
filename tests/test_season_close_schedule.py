"""#391 WP4：收官後的排程閘門（每日鏈／refresh-recent／週跑／晚間鏈）。

驗收 4（當晚切換，可重現時間證據）與 5（切換後該軍爬蟲停、非爬蟲照跑）的重播：
- 一軍：2026 台灣大賽 G6（2026-C-6，10/26 決勝）→ 同晚同步成功後重算收官 → 同晚後續喚醒 quiet；
  10/27 今日賽程檔排除 G7（2026-C-7，not_needed）。
- 二軍：2026 F G3（2026-F-3，10/02 決勝，官網原始回應）→ 23:00 起晚間鏈抓 F 一次、同步、重算收官。
  2026 F 已結束，這裡是**可重現、非實際執行**的重播（R2）。

收官判定本身另有 tests/test_season_close.py（真實列）；這裡注入的收官值與該檔真實判定結果相同。
"""

from __future__ import annotations

import json
import subprocess
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from cpbl import season_close as sc
from cpbl.ingest import daily_gate as dg
from cpbl.ingest import postseason_evening as pe

ROOT = Path(__file__).resolve().parents[1]
TPE = timezone(timedelta(hours=8))

MAJOR_CLOSED = sc.LeagueClosure("major", 2026, True, "decided", champion_team_code="AAA011",
                                decided_by=(2026, "C", 6), decided_game_date=date(2026, 10, 26),
                                not_needed_keys=frozenset({(2026, "C", 7)}), basis="§63/§60")
FARM_OPEN = sc.LeagueClosure("farm", 2026, False, "no_data", basis="farm_first_to_3", reason="no_f_rows")
FARM_CLOSED = sc.LeagueClosure("farm", 2026, True, "decided", champion_team_code="AEO022",
                               decided_by=(2026, "F", 3), decided_game_date=date(2026, 10, 2),
                               basis="farm_first_to_3")
MAJOR_ONLY = {"major": MAJOR_CLOSED, "farm": FARM_OPEN}
BOTH = {"major": MAJOR_CLOSED, "farm": FARM_CLOSED}
# 本機 games 的真實排定（2026 C6 10/26、C7 10/27）。
SCHEDULE = {date(2026, 10, 26): {"C": 1}, date(2026, 10, 27): {"C": 1}}


def _inputs(day: date, *, closed=frozenset(), last_ok=True, unsynced=False, force=False) -> dg.DayInputs:
    return dg.DayInputs(day, SCHEDULE, last_ok, "fixture", unsynced, "fixture", force, frozenset(closed))


def _no_probe():
    raise AssertionError("兩軍皆收官時不得探測 stats")


# ============================================================== 每日鏈日型

def test_without_closure_g7_day_still_wakes_the_chain():
    """對照：未收官時 10/28（昨天 10/27 有 G7 列）＝有賽型——正是收官要排除的那一列。"""
    assert dg.classify(_inputs(date(2026, 10, 28)), _no_probe).day_type == dg.FULL


def test_both_closed_skips_crawl_even_when_last_j1_failed():
    """#383 PA 對帳常態 exit 69 ⇒ 上次 J1 未成功；兩軍皆收官時不套重試、不探測。"""
    got = dg.classify(_inputs(date(2026, 10, 28), closed={"major", "farm"}, last_ok=False), _no_probe)
    assert got.day_type == dg.SKIP and got.closed_leagues == {"major", "farm"}
    assert any("兩軍皆收官" in r for r in got.reasons)


def test_both_closed_with_unsynced_writes_is_sync_only():
    got = dg.classify(_inputs(date(2026, 10, 28), closed={"major", "farm"}, unsynced=True), _no_probe)
    assert got.day_type == dg.SYNC_ONLY


def test_major_closed_g7_day_does_not_count_and_farm_still_probes():
    probed = []
    got = dg.classify(_inputs(date(2026, 10, 27), closed={"major"}),
                      lambda: probed.append(1) or dg.ProbeResult("clean"))
    assert got.day_type == dg.SKIP and probed == [1]
    assert "看 D,F" in got.reasons[1]


def test_force_full_ignores_closure():
    got = dg.classify(_inputs(date(2026, 10, 28), closed={"major", "farm"}, force=True), _no_probe)
    assert got.day_type == dg.FULL and got.closed_leagues == frozenset()


def test_open_kinds_and_probe_kinds_drop_closed_leagues():
    assert dg.open_kinds({"major"}) == ("D", "F")
    assert dg.open_kinds({"major"}, dg.PROBE_KINDS) == ("D",)
    assert dg.open_kinds(set(), dg.PROBE_KINDS) == dg.PROBE_KINDS


def test_stats_probe_only_asks_open_kinds():
    asked = []

    def fetch(_path, params):
        asked.append(params["kindCode"])
        return {"Data": {"Games": []}}

    out = dg.stats_probe(date(2026, 10, 28), fetch=fetch, local_lookup=lambda _g: {}, kinds=("D",))
    assert out.status == "clean" and set(asked) == {"D"}


def test_plan_lists_skipped_and_kept_steps_when_closed():
    decision = dg.Decision(dg.LIGHT, ("fixture",), closed_leagues=frozenset({"major"}))
    text = dg.render_plan(decision)
    assert "DAILY_CLOSED_LEAGUES=major" in text
    for name in ("一軍 A 賽程", "季後 E／C 賽程", "一軍增量明細"):
        assert f"[略過] {name}" in text
    for name in ("總冠軍成員重建", "補缺 gamelog", "季後 E／C 明細補齊", "備份與同步生產"):
        assert any(line.startswith("  [照跑]") and name in line for line in text.splitlines())
    assert "[略過] 戰績" not in text, "只有一軍收官時戰績／升降照抓"
    assert "[略過] 戰績" in dg.render_plan(dg.Decision(dg.LIGHT, (), closed_leagues=frozenset({"major", "farm"})))


# ============================================================== 今日賽程檔

class _TodayDB:
    def __init__(self, rows):
        self.rows, self.params = rows, None

    def execute(self, sql, params=None):
        if "present_status" in sql:
            self.params = params
            day, kinds = params
            return _Rows([r for r in self.rows if r[1] in kinds and r[3] == day])
        return _Rows([])


class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


def test_today_file_drops_g7_and_records_closed_leagues(tmp_path, monkeypatch):
    """10/27：G7（2026-C-7）在本機仍有列，收官後不是排定場；閘門只查未收官軍的賽別。"""
    db = _TodayDB([(2026, "C", 7, date(2026, 10, 27), "樂天桃園", "ACN011", "AAA011", 1)])

    @contextmanager
    def ro():
        yield db

    monkeypatch.setattr(dg, "_readonly_conn", ro)
    out = tmp_path / "today.json"
    payload = dg.write_today_schedule(out, date(2026, 10, 27), day_type="skip", stage="decide",
                                      closure=MAJOR_ONLY)
    assert payload["games"] == [] and payload["closed_leagues"] == ["major"]
    assert db.params[1] == ["D", "F"]
    # 晚間鏈讀得懂新鍵、且動作條件 quiet（不再整晚 plan → idle、每 60 分探 stats）。
    schedule, problem = pe.read_today_schedule(out)
    assert problem == "" and schedule.closed_leagues == ("major",)
    now = datetime(2026, 10, 27, 19, 0, tzinfo=TPE)
    assert pe.evening_gate(pe.empty_state(), now, schedule)[0] == "quiet"


def test_today_file_without_closure_keeps_g7_as_before(tmp_path, monkeypatch):
    db = _TodayDB([(2026, "C", 7, date(2026, 10, 27), "樂天桃園", "ACN011", "AAA011", 1)])

    @contextmanager
    def ro():
        yield db

    monkeypatch.setattr(dg, "_readonly_conn", ro)
    payload = dg.write_today_schedule(tmp_path / "t.json", date(2026, 10, 27), day_type="full",
                                      stage="decide", closure=None)
    assert [g["key"] for g in payload["games"]] == ["2026-C-7"] and payload["closed_leagues"] == []


def test_evening_reads_old_today_file_without_closed_leagues_key(tmp_path):
    path = tmp_path / "old.json"
    path.write_text(json.dumps({"schema_version": 1, "date": "2026-10-26", "stage": "decide",
                                "games": [{"key": "2026-C-6", "year": 2026, "kind_code": "C", "game_sno": 6,
                                           "game_date": "2026-10-26"}]}), encoding="utf-8")
    schedule, problem = pe.read_today_schedule(path)
    assert problem == "" and schedule.closed_leagues == ()


def test_evening_rejects_unknown_closed_league_value(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"schema_version": 1, "date": "2026-10-26", "stage": "decide", "games": [],
                                "closed_leagues": ["A"]}), encoding="utf-8")
    assert pe.read_today_schedule(path) == (None, "schedule_invalid")


def test_alert_watch_does_not_arm_for_excluded_g7_or_f_rows():
    """alert_watch 只讀今日賽程檔且只武裝 A／E／C：G7 排除後不武裝；F 夜不武裝（R4）。"""
    import importlib.util

    spec = importlib.util.spec_from_file_location("_aw_391", ROOT / "scripts" / "alert_watch.py")
    aw = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(aw)
    doc = {"schema_version": 1, "date": "2026-10-02", "stage": "decide",
           "games": [{"key": "2026-F-3", "kind_code": "F", "game_date": "2026-10-02"}], "closed_leagues": []}
    assert aw.tonight_keys(doc, date(2026, 10, 2)) == []


# ============================================================== cpbl-refresh-recent

def _chain(monkeypatch, closed: str | None):
    from test_live_postseason_journey import _stub_chain

    from cpbl.ingest import run_refresh_recent as rr

    scrape_calls: list[tuple] = []
    stat_kinds: list[tuple] = []
    logged: dict = {}
    calls: list[str] = []
    _stub_chain(monkeypatch, lambda *a: scrape_calls.append(a) or {a[0]: 0}, logged, calls)
    monkeypatch.setattr(rr, "scrape_all", lambda *a, kinds=("A", "D"): stat_kinds.append(kinds) or {})
    monkeypatch.setattr(rr, "scrape_standings", lambda *a: calls.append("standings") or {})
    monkeypatch.setattr(rr, "scrape_transactions", lambda *a: calls.append("transactions") or 0)
    monkeypatch.setattr(rr, "build_championships", lambda: calls.append("championships") or 0)
    monkeypatch.delenv(dg.FORCE_ENV, raising=False)
    if closed is None:
        monkeypatch.delenv(dg.CLOSED_ENV, raising=False)
    else:
        monkeypatch.setenv(dg.CLOSED_ENV, closed)
    return rr, scrape_calls, stat_kinds, logged, calls


def test_refresh_recent_major_closed_skips_major_crawl_only(monkeypatch):
    rr, scrape_calls, stat_kinds, logged, calls = _chain(monkeypatch, "major")
    rr.main()
    assert scrape_calls == [(2026, 2026, "D"), (2026, 2026, "F")], "一軍 A 與季後 E／C 不爬"
    assert stat_kinds == [("D",)]
    assert {"standings", "transactions", "championships", "pa_build"} <= set(calls)
    assert any(c.startswith("detail:E,C") for c in calls), "R3：已完賽場的季後明細補齊保留"
    assert logged["detail"]["closed_leagues"] == "major" and logged["ok"] is True


def test_refresh_recent_both_closed_crawls_nothing_but_runs_non_crawl_steps(monkeypatch):
    rr, scrape_calls, stat_kinds, logged, calls = _chain(monkeypatch, "major,farm")
    rr.main()
    assert scrape_calls == [] and stat_kinds == []
    assert "standings" not in calls and "transactions" not in calls
    assert {"championships", "pa_build"} <= set(calls)
    assert logged["ok"] is True and logged["detail"]["games"] == {"skipped": "已收官（#391）"}


def test_refresh_recent_without_closure_is_unchanged_plus_f(monkeypatch):
    rr, scrape_calls, stat_kinds, logged, calls = _chain(monkeypatch, None)
    rr.main()
    assert scrape_calls == [(2026, 2026), (2026, 2026, "D"), (2026, 2026, "F"),
                            (2026, 2026, "E"), (2026, 2026, "C")]
    assert stat_kinds == [("A", "D")]


def test_refresh_recent_force_full_ignores_closed_env(monkeypatch):
    rr, scrape_calls, *_ = _chain(monkeypatch, "major,farm")
    monkeypatch.setenv(dg.FORCE_ENV, "1")
    rr.main()
    assert (2026, 2026) in scrape_calls


def test_refresh_recent_rejects_bad_closed_env(monkeypatch):
    rr, scrape_calls, *_ = _chain(monkeypatch, "A")
    with pytest.raises(SystemExit) as exc:
        rr.main()
    assert exc.value.code == 64 and scrape_calls == []


def test_refresh_recent_f_failure_is_69_not_a_hard_stop(monkeypatch):
    def scrape(*a):
        if a[2:] == ("F",):
            raise RuntimeError("getgamedatas HTTP 428")
        return {a[0]: 0}

    from test_live_postseason_journey import _stub_chain

    from cpbl.ingest import run_refresh_recent as rr

    logged: dict = {}
    _stub_chain(monkeypatch, scrape, logged, [], kinds_setting="")
    monkeypatch.delenv(dg.CLOSED_ENV, raising=False)
    with pytest.raises(SystemExit) as exc:
        rr.main()
    assert exc.value.code == 69 and logged["ok"] is False and "二軍總冠軍賽" in logged["note"]


def test_incremental_detail_skips_closed_league(monkeypatch):
    from cpbl.ingest import run_refresh_recent as rr

    touched = []
    monkeypatch.setattr(rr, "_farm_detail", lambda *a, **k: touched.append("farm") or {})
    monkeypatch.setattr(rr, "_completed_snos", lambda *a, **k: touched.append("major") or [])
    monkeypatch.setattr(rr, "_refresh_pitches", lambda *a, **k: touched.append("pitches") or {})
    out = rr._incremental_detail(2026, [date(2026, 10, 28)], major=False, farm_open=False)
    assert touched == [] and out["skipped"].startswith("一軍已收官")


# ============================================================== 週跑

@pytest.mark.parametrize("script", ["weekly-box-revisions.sh", "weekly-game-pitches.sh"])
def test_weekly_scripts_skip_closed_kinds(script):
    text = (ROOT / "scripts" / script).read_text(encoding="utf-8")
    assert "python -m cpbl.season_close closed-leagues" in text
    loop = text[text.index("CLOSED_LEAGUES=") : text.index("done", text.index("for KIND in A D"))]
    assert "A:*,major,*|D:*,farm,*)" in loop and "continue" in loop


@pytest.mark.parametrize(("closed", "ran"), [("", ["A", "D"]), ("major", ["D"]), ("major,farm", [])])
def test_weekly_skip_pattern_behaviour(closed, ran):
    """同一段 case 樣式以真 bash 執行（不跑腳本其餘部分：它會取鎖並爬）。"""
    snippet = ('CLOSED_LEAGUES="$1"; for KIND in A D; do case "${KIND}:,${CLOSED_LEAGUES}," in '
               "A:*,major,*|D:*,farm,*) continue ;; esac; echo $KIND; done")
    out = subprocess.run(["/bin/bash", "-c", snippet, "_", closed], capture_output=True, text=True, check=True)
    assert out.stdout.split() == ran


# ============================================================== 晚間鏈：當晚切換

def _sched(day: str, keys: list[str], closed: tuple[str, ...] = ()) -> pe.TodaySchedule:
    games = []
    for key in keys:
        y, k, s = key.split("-")
        games.append(pe.ScheduledGame(int(y), k, int(s), day))
    return pe.TodaySchedule(day, tuple(games), closed)


def test_decision_night_switches_after_sync():
    """2026-10-26：C6 結果同步成功（實際 17:42:30 exit=0）→ 重算收官 → 同晚後續喚醒 quiet；決勝場 box／PA 待辦照醒。"""
    sched = _sched("2026-10-26", ["2026-C-6"])
    state = pe.empty_state()
    before = datetime(2026, 10, 26, 17, 40, tzinfo=TPE)
    assert pe.evening_gate(state, before, sched)[0] == "run"
    synced = datetime(2026, 10, 26, 17, 42, 30, tzinfo=TPE)
    assert pe.record_sync(state, synced, 0) == "synced"
    assert pe.note_league_closed(state, synced, MAJOR_ONLY) == ["major"]
    later = datetime(2026, 10, 26, 17, 45, tzinfo=TPE)
    assert pe.evening_gate(state, later, sched)[0] == "quiet"
    # 決勝場 box／PA 尚未送達（實際 18:03 box／PA 同步）：待辦照常讓鏈醒。
    state["boxpa"] = {"2026-C-6": {"state": "pending", "game_date": "2026-10-26"}}
    decision, why, kinds = pe.evening_gate(state, later, sched)
    assert decision == "run" and "boxpa_open" in why and kinds == ("C",)


def test_league_closed_state_only_counts_for_the_same_night():
    state = pe.empty_state()
    pe.note_league_closed(state, datetime(2026, 10, 26, 17, 42, tzinfo=TPE), MAJOR_ONLY)
    next_night = _sched("2027-03-20", ["2027-A-1"])
    assert pe.evening_gate(state, datetime(2027, 3, 20, 18, 0, tzinfo=TPE), next_night)[0] == "run"


def test_without_closure_note_the_decision_night_keeps_running():
    state = pe.empty_state()
    synced = datetime(2026, 10, 26, 17, 42, 30, tzinfo=TPE)
    pe.record_sync(state, synced, 0)
    assert pe.note_league_closed(state, synced, None) == []
    assert pe.evening_gate(state, datetime(2026, 10, 26, 17, 45, tzinfo=TPE),
                           _sched("2026-10-26", ["2026-C-6"]))[0] == "run"


# ============================================================== 晚間鏈：二軍 F 夜抓（R2，可重現重播）

F_NIGHT = _sched("2026-10-02", ["2026-F-3"])


@pytest.mark.parametrize(("hh", "mm", "due", "why"), [
    (22, 59, False, "before_23"), (23, 0, True, "farm_final_23"), (23, 40, True, "farm_final_23")])
def test_farm_final_due_from_2300(hh, mm, due, why):
    assert pe.farm_final_due(pe.empty_state(), datetime(2026, 10, 2, hh, mm, tzinfo=TPE), F_NIGHT) == (due, why)


def test_farm_final_not_due_without_f_or_when_closed_or_done():
    at = datetime(2026, 10, 2, 23, 5, tzinfo=TPE)
    assert pe.farm_final_due(pe.empty_state(), at, _sched("2026-10-02", ["2026-A-300"])) == (False, "no_f_tonight")
    closed = _sched("2026-10-02", ["2026-F-3"], ("farm",))
    assert pe.farm_final_due(pe.empty_state(), at, closed) == (False, "farm_closed")
    state = pe.empty_state()
    pe.mark_farm_final_inflight(state, at)
    assert pe.record_farm_final(state, at, errors=[], changed=True) == "changed" and state["pending_sync"]
    assert pe.farm_final_due(state, at + timedelta(minutes=30), F_NIGHT) == (False, "done_tonight")


def test_farm_final_failures_cool_down_and_cap():
    state = pe.empty_state()
    at = datetime(2026, 10, 2, 23, 0, tzinfo=TPE)
    for i in range(pe.WWW_MAX_ATTEMPTS):
        t = at + timedelta(minutes=21 * i)
        assert pe.farm_final_due(state, t, F_NIGHT)[0] is True
        pe.mark_farm_final_inflight(state, t)
        assert pe.record_farm_final(state, t, errors=[{"kind": "F", "error": "HTTP 500"}], changed=False) == "failed"
        if i < pe.WWW_MAX_ATTEMPTS - 1:
            assert pe.farm_final_due(state, t + timedelta(minutes=5), F_NIGHT) == (False, "cooldown")
    assert pe.farm_final_due(state, at + timedelta(hours=3), F_NIGHT) == (False, "attempts_exhausted")


def test_farm_final_yields_to_daily_chain_and_db_lookup_fallback():
    state = pe.empty_state()
    guard = datetime(2026, 10, 3, 9, 50, tzinfo=TPE)
    assert pe.farm_final_due(state, guard, None, db_lookup=lambda n: True) == (False, "outside_night")
    early = datetime(2026, 10, 3, 1, 0, tzinfo=TPE)     # 仍屬 10/02 那一晚
    assert pe.farm_final_due(state, early, None, db_lookup=lambda n: n == date(2026, 10, 2)) == (True, "farm_final_23")

    def boom(_n):
        raise RuntimeError("db down")

    assert pe.farm_final_due(state, early, None, db_lookup=boom) == (False, "schedule_lookup_error")


def test_farm_night_replay_cli(tmp_path, monkeypatch, capsys):
    """2026-10-02 晚：F G3 已在本機（每日鏈 10:10 抓到賽程）。23:00 plan → scrape（只抓 F、www 標記 card=391）
    → changed → record-sync 0 → 重算收官（二軍 decided）→ 23:30 plan quiet。今日賽程檔只放 F 列（只驗 F 路徑）。"""
    from cpbl.ingest import run_refresh_recent as rr

    today = tmp_path / "today.json"
    today.write_text(json.dumps({"schema_version": 1, "date": "2026-10-02", "stage": "after_scrape",
                                 "games": [{"key": "2026-F-3", "year": 2026, "kind_code": "F", "game_sno": 3,
                                            "game_date": "2026-10-02"}], "closed_leagues": []}), encoding="utf-8")
    monkeypatch.setenv(pe.TODAY_SCHEDULE_ENV, str(today))
    monkeypatch.setenv("POSTSEASON_STATE", str(tmp_path / "state.json"))
    monkeypatch.setenv("POSTSEASON_STATUS", str(tmp_path / "last.json"))
    monkeypatch.setenv("POSTSEASON_YEAR", "2026")
    monkeypatch.setenv("POSTSEASON_STARTER_FLAG", str(tmp_path / "no-starter-flag"))
    monkeypatch.setenv("POSTSEASON_STARTER_WATCH_FLAG", str(tmp_path / "no-watch-flag"))
    monkeypatch.delenv(pe.EVENING_KINDS_ENV, raising=False)
    sig = {"F": "before"}
    fetched = []

    def fake_step(year):
        from cpbl.ingest import _browser

        fetched.append((year, dict(_browser._MARKER)))
        sig["F"] = "after"
        return {"games": {2026: 3}, "errors": []}

    monkeypatch.setattr(rr, "_farm_final_games_step", fake_step)
    monkeypatch.setattr(pe, "local_signature", lambda year, kinds=None: sig["F"] if kinds == ("F",) else "same")
    monkeypatch.setattr(pe, "load_local_games", lambda *a, **k: {})
    monkeypatch.setattr(pe, "local_first_seen", lambda *a, **k: {})
    monkeypatch.setattr(pe, "publish_signals", lambda *a, **k: None)
    monkeypatch.setattr(pe, "stats_probe", lambda *a, **k: (_ for _ in ()).throw(AssertionError("F 不探 stats")))

    def run(cmd: list[str], at: datetime) -> str:
        monkeypatch.setattr(pe, "_now", lambda: at)
        assert pe.main(cmd) == 0
        return capsys.readouterr().out.strip().splitlines()[-1]

    assert run(["plan"], datetime(2026, 10, 2, 22, 55, tzinfo=TPE)) == "quiet"
    assert run(["plan"], datetime(2026, 10, 2, 23, 0, 5, tzinfo=TPE)) == "scrape"
    assert run(["scrape"], datetime(2026, 10, 2, 23, 0, 40, tzinfo=TPE)) == "changed"
    assert fetched == [(2026, fetched[0][1])]
    marker = fetched[0][1]
    assert (marker["card"], marker["src"], marker["kind"], marker["game"]) == ("391", "391", "event", "2026/F/-")
    monkeypatch.setattr(pe, "read_closure", lambda now=None: {"major": MAJOR_CLOSED.__class__(
        "major", 2026, False, "undecided", basis="x"), "farm": FARM_CLOSED})
    assert run(["record-sync", "--code", "0"], datetime(2026, 10, 2, 23, 3, tzinfo=TPE)) == "synced"
    state = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    assert state["league_closed"]["night"] == "2026-10-02" and state["league_closed"]["leagues"] == ["farm"]
    assert run(["plan"], datetime(2026, 10, 2, 23, 30, tzinfo=TPE)) == "quiet"
    assert fetched and len(fetched) == 1


def test_www_marker_card_391_only_accepts_f():
    from cpbl.ingest import _browser as br

    with br.www_marker("event", "391", "2026/F/-", card="391"):
        assert br._MARKER["card"] == "391"
    for bad in ("2026/C/-", "2026/A/1"):
        with pytest.raises(ValueError):
            with br.www_marker("event", "391", bad, card="391"):
                pass
    with pytest.raises(ValueError):
        with br.www_marker("event", "293", "2026/F/-"):
            pass
