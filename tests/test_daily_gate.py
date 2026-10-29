"""#364（#343 WP1）：J1 日型閘門＋VPS 訓練閘門的驗收 (a)–(e)。

零網路、零 DB：本機 DB 以假連線（依 SQL 片段分派）代替、stats 以假 fetch 代替、shell 鏈以
PATH 假樁代替。樣本日期與賽程列數是 2026 真實資料（本機 ``cpbl.games`` 2026-10-23 唯讀查詢
凍結於下方 ``REAL_2026_SCHEDULE``／``REAL_2026_LOCAL_GAMES``；查詢與結果見 #364 執行報告）。
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from cpbl.ingest import daily_gate as dg
from cpbl.ingest import postseason_evening as pe

ROOT = Path(__file__).parents[1]
TPE = timezone(timedelta(hours=8))

# 本機 cpbl.games（2026，kind A/D/E/C）在樣本日期前後的真實列數（2026-10-23 唯讀查詢）。
# 未列出的日期＝0 列：07-20、08-10、10-07、10-08、10-14、10-15。
REAL_2026_SCHEDULE: dict[date, dict[str, int]] = {
    date(2026, 7, 21): {"A": 2, "D": 2},
    date(2026, 8, 11): {"A": 2, "D": 2},
    date(2026, 10, 9): {"E": 1},
    date(2026, 10, 10): {"E": 1},
    date(2026, 10, 11): {"E": 1},
    date(2026, 10, 12): {"E": 1},
    date(2026, 10, 17): {"C": 1},
    date(2026, 10, 18): {"C": 1},
    date(2026, 10, 20): {"C": 1},
    date(2026, 10, 21): {"C": 1},
}
# 同一查詢：2026-10-08～10-22 的本機場次（探測窗口比對用）。
REAL_2026_LOCAL_GAMES = {
    "2026-E-1": "2026-10-09", "2026-E-2": "2026-10-10", "2026-E-3": "2026-10-11",
    "2026-E-4": "2026-10-12", "2026-C-1": "2026-10-17", "2026-C-2": "2026-10-18",
    "2026-C-3": "2026-10-20", "2026-C-4": "2026-10-21",
}


def _stats_row(key: str, day: str, status: str = "FINISHED") -> dict:
    year, kind, sno = key.split("-")
    return {"GameId": key, "KindCode": kind, "GameSno": int(sno), "GameStatus": status,
            "PreExeDate": f"{day}T18:35:00", "Home": {"Code": "AAA011"},
            "Visiting": {"Code": "ACN011"}, "Field": {"Abbe": "洲際"}}


def _fake_fetch(games: dict[str, str], calls: list | None = None):
    """stats 賽程 API 假樁：依 kindCode／year／month 回傳 games 中符合的列。"""
    def fetch(path: str, params: dict) -> dict:
        if calls is not None:
            calls.append(dict(params))
        rows = [_stats_row(k, d) for k, d in games.items()
                if k.split("-")[1] == params["kindCode"] and d[:4] == params["year"]
                and int(d[5:7]) == int(params["month"])]
        return {"Data": {"Games": rows}}
    return fetch


class FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return list(self._rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None


class FakeDB:
    """依 SQL 片段分派的假連線。任何沒認得的 SQL 一律炸（不讓測試靜默通過）。"""

    def __init__(self, *, schedule=None, local_games=None, write_counter=0, season_rows=None,
                 today_rows=None):
        self.schedule = schedule or REAL_2026_SCHEDULE
        self.local_games = local_games if local_games is not None else REAL_2026_LOCAL_GAMES
        self.write_counter = write_counter
        self.season_rows = season_rows or []
        self.today_rows = today_rows or []
        self.statements: list[str] = []

    def execute(self, sql: str, params=None):
        self.statements.append(sql)
        if sql.startswith("SET TRANSACTION READ ONLY"):
            return FakeResult([])
        if "pg_stat_user_tables" in sql:
            return FakeResult([(self.write_counter,)])
        if "GROUP BY game_date, kind_code" in sql:
            days, kinds = params
            return FakeResult([(d, k, n) for d in days for k, n in (self.schedule.get(d) or {}).items()
                               if k in kinds])
        if "unnest" in sql:
            return FakeResult([(int(k.split("-")[0]), k.split("-")[1], int(k.split("-")[2]),
                                date.fromisoformat(d)) for k, d in self.local_games.items()])
        if "GROUP BY g.year" in sql:
            return FakeResult(self.season_rows)
        if "present_status" in sql:
            return FakeResult(self.today_rows)
        raise AssertionError(f"FakeDB 不認得這句 SQL：{sql[:120]}")


@pytest.fixture
def fake_db(monkeypatch):
    db = FakeDB()

    @contextmanager
    def ro():
        db.execute("SET TRANSACTION READ ONLY")
        yield db

    monkeypatch.setattr(dg, "_readonly_conn", ro)
    return db


def _history(path: Path, records: list[tuple[str, str]]) -> Path:
    """[(started_at, state)] → 假歷史（running 列＋終態列，與 refresh_status.py 同形）。"""
    lines = []
    for started, state in records:
        lines.append({"label": "com.cpbl.scrape-daily", "state": "running", "trigger": "launchd",
                      "started_at": started, "finished_at": None})
        if state != "running":
            lines.append({"label": "com.cpbl.scrape-daily", "state": state, "trigger": "launchd",
                          "started_at": started, "finished_at": started,
                          "exit_code": 0 if state == "succeeded" else 69})
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in lines), encoding="utf-8")
    return path


def _ok_history(tmp_path: Path, day: date, *, previous_state: str = "succeeded") -> Path:
    prev = day - timedelta(days=1)
    return _history(tmp_path / "history.jsonl",
                    [(f"{prev - timedelta(days=1)}T10:10:01+0800", "succeeded"),
                     (f"{prev}T10:10:01+0800", previous_state)])


def _inputs(day: date, *, last_ok=True, unsynced=False, force=False) -> dg.DayInputs:
    return dg.DayInputs(day, REAL_2026_SCHEDULE, last_ok, "fixture", unsynced, "fixture", force)


def _probe_real(day: date):
    games = {k: d for k, d in REAL_2026_LOCAL_GAMES.items()}
    return lambda: dg.stats_probe(day, fetch=_fake_fetch(games),
                                  local_lookup=lambda _g: REAL_2026_LOCAL_GAMES)


# ============================================================== (a) 日型判定：2026 真實日期

@pytest.mark.parametrize(("day", "expected"), [
    (date(2026, 10, 8), dg.SKIP),    # 甲型：10-07、10-08 皆無
    (date(2026, 10, 15), dg.SKIP),   # 甲型：10-14、10-15 皆無（10-17 C1 在探測窗口內且本機已有）
    (date(2026, 7, 21), dg.LIGHT),   # 乙型：07-20 無、07-21 A2 D2
    (date(2026, 8, 11), dg.LIGHT),   # 乙型：08-10 無、08-11 A2 D2
    (date(2026, 10, 21), dg.FULL),   # 有賽型：10-20 C1
])
def test_a_day_type_on_real_2026_dates(day: date, expected: str) -> None:
    decision = dg.classify(_inputs(day), _probe_real(day))
    assert decision.day_type == expected, decision.reasons


def test_a_0811_with_previous_day_failure_is_still_light_and_records_why(tmp_path: Path) -> None:
    """08-11 樣本「含前日失敗」：08-10 的 J1 失敗。今天有賽本就乙型；失敗必須讀得出來。"""
    history = _ok_history(tmp_path, date(2026, 8, 11), previous_state="failed")
    ok, detail = dg.last_j1_status(history, before=datetime(2026, 8, 11, 10, 10, tzinfo=TPE))
    assert ok is False and "failed" in detail
    decision = dg.classify(dg.DayInputs(date(2026, 8, 11), REAL_2026_SCHEDULE, ok, detail, False, ""),
                           _probe_real(date(2026, 8, 11)))
    assert decision.day_type == dg.LIGHT


def test_a_jia_day_after_failed_j1_runs_as_light_retry() -> None:
    """§3.2「甲型但上次 J1 失敗 → 依乙型跑（兼任重試）」：以 10-08 真實賽程＋假失敗。"""
    probe_called = []
    decision = dg.classify(_inputs(date(2026, 10, 8), last_ok=False),
                           lambda: probe_called.append(1) or dg.ProbeResult("clean"))
    assert decision.day_type == dg.LIGHT
    assert probe_called == []          # 已確定乙型就不打 stats


def test_a_jia_day_with_unsynced_local_writes_is_sync_only() -> None:
    decision = dg.classify(_inputs(date(2026, 10, 15), unsynced=True), _probe_real(date(2026, 10, 15)))
    assert decision.day_type == dg.SYNC_ONLY


def test_a_unknown_sync_marker_fails_closed_to_sync_only() -> None:
    decision = dg.classify(_inputs(date(2026, 10, 15), unsynced=None), _probe_real(date(2026, 10, 15)))
    assert decision.day_type == dg.SYNC_ONLY


@pytest.mark.parametrize(("stats_games", "expected_detail"), [
    ({**REAL_2026_LOCAL_GAMES, "2026-C-5": "2026-10-13"}, "新場次 2026-C-5"),
    ({**REAL_2026_LOCAL_GAMES, "2026-E-4": "2026-10-13"}, "日期異動 2026-E-4"),
    ({**REAL_2026_LOCAL_GAMES, "2026-D-300": "2026-10-14"}, "新場次 2026-D-300"),   # D 也探測
])
def test_a_probe_finds_new_games_and_upgrades_to_light(stats_games, expected_detail) -> None:
    day = date(2026, 10, 8)
    probe = lambda: dg.stats_probe(day, fetch=_fake_fetch(stats_games),  # noqa: E731
                                   local_lookup=lambda _g: REAL_2026_LOCAL_GAMES)
    decision = dg.classify(_inputs(day), probe)
    assert decision.day_type == dg.LIGHT
    assert any(expected_detail in d for d in decision.probe.detail), decision.probe


def test_a_probe_failure_fails_closed_to_light() -> None:
    def broken(path, params):
        raise TimeoutError("stats down")
    decision = dg.classify(_inputs(date(2026, 10, 8)),
                           lambda: dg.stats_probe(date(2026, 10, 8), fetch=broken,
                                                  local_lookup=lambda _g: {}))
    assert decision.day_type == dg.LIGHT and decision.probe.status == "unavailable"


def test_a_probe_queries_all_four_kinds_across_month_boundary() -> None:
    calls: list[dict] = []
    dg.stats_probe(date(2026, 10, 28), fetch=_fake_fetch({}, calls), local_lookup=lambda _g: {})
    assert {(c["kindCode"], c["month"]) for c in calls} == {
        (k, m) for k in ("A", "D", "E", "C") for m in ("10", "11")}


def test_a_probe_parser_matches_postseason_parser_on_e_c_rows() -> None:
    """parse_probe_rows 只放寬賽別；E／C 輸出必須與既有 parse_stats_games 逐筆相同。"""
    rows = [_stats_row(k, d) for k, d in REAL_2026_LOCAL_GAMES.items()]
    rows += [{"GameId": "2026-C-9", "KindCode": "E", "GameSno": 9},     # 身分不一致 → 略過
             {"GameId": "bad", "KindCode": "C", "GameSno": "x"}]
    assert dg.parse_probe_rows(rows, 2026, ("E", "C")) == pe.parse_stats_games(rows, 2026)


def test_a_last_j1_status_treats_dangling_running_as_failure(tmp_path: Path) -> None:
    history = _history(tmp_path / "h.jsonl", [("2026-10-13T10:10:01+0800", "succeeded"),
                                              ("2026-10-14T10:10:01+0800", "running")])
    ok, _ = dg.last_j1_status(history)
    assert ok is False
    ok, _ = dg.last_j1_status(history, exclude_started_at="2026-10-14T10:10:01+0800")
    assert ok is True                    # 排除本次自己那列 running


def test_a_last_j1_skipped_counts_as_success(tmp_path: Path) -> None:
    history = _history(tmp_path / "h.jsonl", [("2026-10-14T10:10:01+0800", "skipped")])
    assert dg.last_j1_status(history)[0] is True


def test_a_unsynced_writes_compares_marker_with_counter(tmp_path: Path) -> None:
    marker = tmp_path / "m.json"
    assert dg.unsynced_writes(marker, 10)[0] is None
    marker.write_text(json.dumps({"write_counter": 10, "synced_at": "x"}), encoding="utf-8")
    assert dg.unsynced_writes(marker, 10)[0] is False
    assert dg.unsynced_writes(marker, 11)[0] is True
    assert dg.unsynced_writes(marker, None)[0] is None


# ============================================================== (b) --plan 步驟清單 ＝ §3.2 表

PLAN_TABLE = {
    # PLAN-r5 §3.2 表「跑什麼」逐列＋§3.2.3：跑／略過。KEEP（表未列、維持現況）與 COND 另列。
    # 衍生步驟（PA build、球種、當季衍生、分項＋生涯、改名同步）在乙型／甲型只同步一律是 COND
    # （§3.2.3 來源訊號），⛔ 不得因日型直接列為「略過」。
    dg.FULL: {
        "run": {"ad_games", "ec_games", "season_stats", "standings", "transactions", "championships",
                "incremental", "missing_gamelog", "postseason_detail", "pa_build", "pitch_type",
                "derived", "splits", "name_sync", "team_comparison", "backup", "sync", "freshness"},
        "cond": {"build_features", "train_outcome", "train_simple"},   # 4/4 套 §3.5 訓練閘門
        "skip": {"status_skipped"},
    },
    dg.LIGHT: {
        "run": {"ad_games", "ec_games", "season_stats", "standings", "transactions", "missing_gamelog",
                "incremental", "backup", "sync", "freshness"},
        "cond": set(dg.DERIVED_STEPS),   # §3.2.3
        "skip": {"build_features", "train_outcome", "train_simple", "status_skipped"},
        "keep": {"championships", "postseason_detail", "team_comparison"},
    },
    dg.SYNC_ONLY: {
        "run": {"backup", "sync", "freshness"},
        "cond": set(dg.DERIVED_STEPS),   # §3.2.3（不爬；J3／J4 訊號）
        "keep": {"team_comparison"},
        "skip": ({k for k, _ in dg.STEPS} - {"backup", "sync", "freshness", "team_comparison"}
                 - set(dg.DERIVED_STEPS)),
    },
    dg.SKIP: {
        "run": {"status_skipped"},
        "skip": {k for k, _ in dg.STEPS} - {"status_skipped"},
    },
}


@pytest.mark.parametrize("day_type", list(PLAN_TABLE))
def test_b_plan_steps_match_section_3_2_table(day_type: str) -> None:
    by_action: dict[str, set[str]] = {}
    for key, _name, action, _note in dg.plan_steps(day_type):
        by_action.setdefault(action, set()).add(key)
    expected = PLAN_TABLE[day_type]
    assert by_action.get(dg.RUN, set()) == expected["run"]
    assert by_action.get(dg.SKIP_STEP, set()) == expected["skip"]
    assert by_action.get(dg.COND, set()) == expected.get("cond", set())
    assert by_action.get(dg.KEEP, set()) == expected.get("keep", set())


def test_b_force_full_plan_has_no_gated_steps() -> None:
    actions = {key: action for key, _n, action, _no in dg.plan_steps(dg.FULL, force=True)}
    assert actions["build_features"] == actions["train_outcome"] == actions["train_simple"] == dg.RUN


@pytest.mark.parametrize(("day", "label", "must_run", "must_skip"), [
    ("2026-10-08", "甲型（skip）", ["狀態寫「成功、skipped=true」"], ["A／D 賽程", "正式站整庫備份", "同步（migration"]),
    ("2026-10-15", "甲型（skip）", ["狀態寫「成功、skipped=true」"], ["A／D 賽程", "正式站整庫備份"]),
    ("2026-07-21", "乙型（light）", ["A／D 賽程", "季累計", "補缺 gamelog", "同步（migration"],
     ["cpbl-build-features", "4/4 cpbl-train-outcome"]),
    ("2026-08-11", "乙型（light）", ["A／D 賽程", "戰績", "升降", "同步（migration"],
     ["4/4 cpbl-train-outcome-simple"]),
    ("2026-10-21", "有賽型（full）", ["A／D 賽程", "PA build", "分項", "同步（migration"], []),
])
def test_b_refresh_recent_plan_cli_prints_steps_for_real_dates(
        day, label, must_run, must_skip, fake_db, monkeypatch, tmp_path, capsys) -> None:
    """``cpbl-refresh-recent --plan --date`` 的實際入口（假 DB／假 stats／假歷史）。"""
    from cpbl.ingest import run_refresh_recent as rr

    target = date.fromisoformat(day)
    previous = "failed" if day == "2026-08-11" else "succeeded"
    history = _ok_history(tmp_path, target, previous_state=previous)
    marker = tmp_path / "marker.json"
    marker.write_text(json.dumps({"write_counter": 0, "synced_at": "x"}), encoding="utf-8")
    monkeypatch.setattr(dg, "_local_lookup_db", lambda games, d: REAL_2026_LOCAL_GAMES)
    monkeypatch.setattr(pe, "_httpx_fetch", lambda timeout: _fake_fetch(REAL_2026_LOCAL_GAMES))
    monkeypatch.delenv(dg.FORCE_ENV, raising=False)
    monkeypatch.setattr(sys, "argv", ["cpbl-refresh-recent", "--plan", "--date", day,
                                      "--history", str(history), "--sync-marker", str(marker)])
    with pytest.raises(SystemExit) as exit_info:
        rr.main()
    out = capsys.readouterr().out
    assert exit_info.value.code == 0
    assert f"日型：{label}" in out, out
    lines = out.splitlines()
    for name in must_run:
        assert any(line.startswith("  [跑]") and name in line for line in lines), (name, out)
    for name in must_skip:
        assert any(line.startswith("  [略過]") and name in line for line in lines), (name, out)
    if "乙型" in label:   # §3.2.3：衍生步驟是條件，不是略過
        for name in ("PA build", "球種推算整季重算", "當季衍生", "分項", "改名同步"):
            assert any(line.startswith("  [條件]") and name in line and "§3.2.3" in line
                       for line in lines), (name, out)
    # 唯讀：只碰 SELECT／pg_stat，從不寫
    assert not [s for s in fake_db.statements if s.split()[0].upper() in ("INSERT", "UPDATE", "DELETE")]


# ============================================================== shell 假樁共用

def _executable(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def _run_daily(tmp_path: Path, *, gate_type: str, extra_env: dict | None = None):
    """跑真 scrape-daily.sh：uv／docker／refresh-cpbl-prod.sh 皆為記錄型假樁。"""
    repo, fake_bin, calls = tmp_path / "repo", tmp_path / "bin", tmp_path / "calls.log"
    (repo / "scripts").mkdir(parents=True)
    for name in ("scrape-daily.sh", "refresh_status.py"):
        (repo / "scripts" / name).write_bytes((ROOT / "scripts" / name).read_bytes())
    _executable(fake_bin / "docker", "#!/bin/sh\nprintf 'cpbl-analytics-db-1\\n'\n")
    _executable(fake_bin / "uv", f"""#!/bin/sh
case "$*" in
  *"daily_gate decide"*) echo "REASON=fixture"; echo "CLOSED_LEAGUES=$STUB_CLOSED"; echo "DAY_TYPE={gate_type}" ;;
  *"daily_gate mark-synced"*) echo "mark-synced" >> "{calls}" ;;
  *"daily_gate today-schedule"*) echo "today-schedule $*" >> "{calls}"; [ "$STUB_TODAY_FAIL" = 1 ] && exit 1 ;;
  *cpbl-refresh-recent*) echo "refresh-recent DAILY_DAY_TYPE=$DAILY_DAY_TYPE" >> "{calls}"
                         echo "refresh-closed DAILY_CLOSED_LEAGUES=$DAILY_CLOSED_LEAGUES" >> "{calls}" ;;
  *cpbl-build-team-comparison*) echo "team-comparison" >> "{calls}" ;;
  *) echo "uv $*" >> "{calls}" ;;
esac
""")
    # 同步樁：被呼叫就在 backups/ 生一個新備份檔（模擬 2/4），並記下日型與逃生閥。
    _executable(repo / "scripts" / "refresh-cpbl-prod.sh", f"""#!/bin/sh
mkdir -p "{tmp_path}/backups"
: > "{tmp_path}/backups/cpbl-$(date +%s).dump"
echo "sync DAILY_DAY_TYPE=$DAILY_DAY_TYPE DAILY_FORCE_FULL=${{DAILY_FORCE_FULL:-}}" >> "{calls}"
""")
    env = {"PATH": f"{fake_bin}:/usr/bin:/bin", "HOME": str(tmp_path), "REFRESH_TRIGGER": "launchd",
           "REFRESH_LOCK_DIR": str(tmp_path / "lock"), "SYNC_PROD": "1", **(extra_env or {})}
    result = subprocess.run(["/bin/bash", str(repo / "scripts" / "scrape-daily.sh")], cwd=repo,
                            env=env, text=True, capture_output=True, check=False)
    status = json.loads((repo / "logs" / "last-status.json").read_text(encoding="utf-8"))
    log_lines = calls.read_text(encoding="utf-8").splitlines() if calls.exists() else []
    return result, status, log_lines, repo


def _load_schedule_watch():
    spec = importlib.util.spec_from_file_location("_sw_364", ROOT / "scripts" / "schedule_watch.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _daily_job(day: date) -> dict:
    return {"label": "com.cpbl.scrape-daily", "cadence": {"kind": "daily", "hour": 10, "minute": 10},
            "history_path": "logs/schedule-history/com.cpbl.scrape-daily.jsonl",
            "effective_from": day.isoformat(), "history_from": day.isoformat()}


# ============================================================== (c) 甲型：不備份、skipped、不 MISSING

def test_c_jia_day_writes_no_backup_and_succeeded_skipped_status(tmp_path: Path) -> None:
    result, status, calls, repo = _run_daily(tmp_path, gate_type="skip")

    assert result.returncode == 0, result.stderr
    assert not (tmp_path / "backups").exists() or not list((tmp_path / "backups").iterdir())
    assert not [c for c in calls if c.startswith(("sync", "refresh-recent", "team-comparison",
                                                  "mark-synced"))], calls
    assert status["state"] == "succeeded" and status["ok"] is True and status["exit_code"] == 0
    assert status["skipped"] is True and status["skip_reason"] and status["day_type"] == "skip"
    assert status["sync_attempted"] is False
    history = [json.loads(line) for line in (repo / "logs" / "schedule-history"
               / "com.cpbl.scrape-daily.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [h["state"] for h in history] == ["running", "succeeded"]
    assert history[-1]["skipped"] is True and "skipped" in history[-1]["note"]


@pytest.mark.parametrize("closed", ["major", "major,farm", ""])
def test_c_scrape_daily_forwards_closed_leagues_to_refresh(tmp_path: Path, closed: str) -> None:
    """#391：decide 印的 CLOSED_LEAGUES 原樣交給 cpbl-refresh-recent（空＝未收官）。"""
    result, _status, calls, _repo = _run_daily(tmp_path, gate_type="light", extra_env={"STUB_CLOSED": closed})
    assert result.returncode == 0, result.stderr
    assert f"refresh-closed DAILY_CLOSED_LEAGUES={closed}" in calls


def test_c_scrape_daily_force_full_never_forwards_closure(tmp_path: Path) -> None:
    result, _status, calls, _repo = _run_daily(tmp_path, gate_type="light",
                                               extra_env={"STUB_CLOSED": "major,farm", "DAILY_FORCE_FULL": "1"})
    assert result.returncode == 0, result.stderr
    assert "refresh-closed DAILY_CLOSED_LEAGUES=" in calls


def test_c_checker_reports_ok_for_skipped_day(tmp_path: Path) -> None:
    _result, _status, _calls, repo = _run_daily(tmp_path, gate_type="skip")
    check = subprocess.run([sys.executable, str(repo / "scripts" / "refresh_status.py"), "check"],
                           cwd=repo, text=True, capture_output=True, check=False)
    assert check.returncode == 0 and check.stdout.startswith("OK"), check.stdout


def test_c_schedule_watch_does_not_report_missing_for_consecutive_skipped_days(tmp_path: Path) -> None:
    """假歷史：連三個甲型日（10-13～10-15）都由真 refresh_status.py finish --skipped 寫入。"""
    repo = tmp_path / "repo"
    (repo / "logs").mkdir(parents=True)
    helper = ROOT / "scripts" / "refresh_status.py"
    days = [date(2026, 10, 13), date(2026, 10, 14), date(2026, 10, 15)]
    for day in days:
        started = f"{day}T10:10:01+0800"
        common = ["--status", "logs/last-status.json", "--scheduled-status",
                  "logs/last-launchd-status.json", "--trigger", "launchd", "--log", "logs/x.log",
                  "--started-at", started, "--sync-enabled", "1"]
        subprocess.run([sys.executable, str(helper), "start", *common], cwd=repo, check=True)
        subprocess.run([sys.executable, str(helper), "finish", *common,
                        "--finished-at", f"{day}T10:11:00+0800", "--scrape-code", "0",
                        "--sync-attempted", "0", "--day-type", "skip", "--skipped", "1",
                        "--skip-reason", "昨今皆無"], cwd=repo, check=True)
    # 回放：observed_at 是 writer 的真實寫入時刻（今天），schedule_watch 會排除「now 之後才寫下」
    # 的列；把它改成該列描述的時刻，才是那三天當下看得到的歷史。其餘欄位原樣保留。
    hist = repo / "logs" / "schedule-history" / "com.cpbl.scrape-daily.jsonl"
    records = [json.loads(line) for line in hist.read_text(encoding="utf-8").splitlines()]
    for record in records:
        record["observed_at"] = record["finished_at"] or record["started_at"]
    hist.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records), encoding="utf-8")
    assert [r["state"] for r in records] == ["running", "succeeded"] * 3
    assert all(r["skipped"] for r in records if r["state"] == "succeeded")
    watch = _load_schedule_watch()
    now = datetime(2026, 10, 15, 12, 0, tzinfo=TPE)
    result = watch.evaluate_job(_daily_job(days[0]), now, repo, lookback=14, anchor=days[0])
    verdicts = {c["verdict"] for c in result["cycles"]}
    assert verdicts == {"OK"}, result
    assert not result["findings"], result["findings"]


def test_c_missing_record_is_still_missing_control(tmp_path: Path) -> None:
    """負控：真的沒跑的那天仍判 MISSING——證明上一條不是因為判定器失靈才綠。"""
    repo = tmp_path / "repo"
    (repo / "logs" / "schedule-history").mkdir(parents=True)
    (repo / "logs" / "schedule-history" / "com.cpbl.scrape-daily.jsonl").write_text("", encoding="utf-8")
    watch = _load_schedule_watch()
    now = datetime(2026, 10, 15, 12, 0, tzinfo=TPE)
    result = watch.evaluate_job(_daily_job(date(2026, 10, 13)), now, repo, lookback=14,
                                anchor=date(2026, 10, 13))
    assert "MISSING" in {c["verdict"] for c in result["cycles"]}


@pytest.mark.parametrize(("gate_type", "writes_today_file"), [
    ("light", True), ("full", True), ("sync_only", False),
])
def test_c_other_day_types_route_through_refresh_and_sync(tmp_path, gate_type, writes_today_file) -> None:
    """light／full／sync_only 都進 cpbl-refresh-recent（sync_only 在程式內不爬、只做 §3.2.3 衍生），
    之後同步並記同步標記；只有爬過賽程的日型覆寫今日賽程檔。"""
    result, status, calls, _repo = _run_daily(tmp_path, gate_type=gate_type)
    assert result.returncode == 0, result.stderr
    assert status["skipped"] is False and status["day_type"] == gate_type
    refresh = calls.index(f"refresh-recent DAILY_DAY_TYPE={gate_type}")
    sync = next(i for i, c in enumerate(calls) if c.startswith(f"sync DAILY_DAY_TYPE={gate_type}"))
    assert refresh < sync and "mark-synced" in calls[sync:], calls
    assert "team-comparison" in calls
    assert any(c.startswith("today-schedule") for c in calls) is writes_today_file


def test_c_gate_failure_falls_back_to_full_chain(tmp_path: Path) -> None:
    result, status, calls, _repo = _run_daily(tmp_path, gate_type="garbage")
    assert result.returncode == 0
    assert status["day_type"] == "full" and status["skipped"] is False
    assert "refresh-recent DAILY_DAY_TYPE=full" in calls


# ============================================================== (e) DAILY_FORCE_FULL=1

def test_e_force_full_overrides_jia_day_in_daily_chain(tmp_path: Path) -> None:
    result, status, calls, _repo = _run_daily(tmp_path, gate_type="skip",
                                              extra_env={"DAILY_FORCE_FULL": "1"})
    assert result.returncode == 0
    assert status["day_type"] == "full" and status["skipped"] is False
    assert "refresh-recent DAILY_DAY_TYPE=full" in calls
    assert "sync DAILY_DAY_TYPE=full DAILY_FORCE_FULL=1" in calls
    assert list((tmp_path / "backups").iterdir())


def test_e_force_full_in_classifier() -> None:
    decision = dg.classify(_inputs(date(2026, 10, 8), force=True),
                           lambda: pytest.fail("強制完整鏈不得打 stats"))
    assert decision.day_type == dg.FULL


@pytest.mark.parametrize("day_type", ["light", "sync_only"])
def test_e_force_full_makes_refresh_recent_ignore_gating(monkeypatch, day_type) -> None:
    """``DAILY_FORCE_FULL=1`` 時 cpbl-refresh-recent 不認 DAILY_DAY_TYPE（無訊號也全跑衍生、照爬）。"""
    from cpbl.ingest import run_refresh_recent as rr

    ran: list[str] = []
    _stub_refresh_main(monkeypatch, rr, ran)
    monkeypatch.setenv(dg.DAY_TYPE_ENV, day_type)
    monkeypatch.setenv(dg.FORCE_ENV, "1")
    rr.main()
    assert _DERIVED_RAN <= set(ran) and "log:full" in ran


def _stub_refresh_main(monkeypatch, rr, ran: list[str], *, new_pitches: int = 0,
                       games_written: int = 0, weekly=None, backfill_snos=(), pa_build=None) -> None:
    """main() 的對外出口全換成記錄型替身；衍生步驟被呼叫就記進 ``ran``。

    ``weekly``：§3.2.3 訊號 3／4 的替身（預設兩者皆 False）；傳 callable 則用它（可接真函式＋假 DB）。
    ``pa_build``：傳入則 ``_pa_build_step`` 用真函式、其下層換成假已發布集合（(f) 用）。
    """
    monkeypatch.setattr(rr.sys, "argv", ["cpbl-refresh-recent"])
    monkeypatch.setattr(rr, "_GAMELOG_GAPS", [])
    stubs = {
        "migrate": lambda: [], "scrape_games": lambda *a, **k: 0, "scrape_all": lambda *a, **k: {},
        "scrape_standings": lambda *a, **k: {}, "standings_failures": lambda: [],
        "reset_standings_failures": lambda: None, "scrape_transactions": lambda *a, **k: 0,
        "build_championships": lambda: None,
        "_incremental_detail": lambda *a, **k: {
            "gamelog": {"games": games_written}, "pitches": {"pitches": new_pitches}, "farm": {}},
        "_missing_gamelog_snos": lambda year, kind="A": list(backfill_snos) if kind == "A" else [],
        "scrape_gamelogs": lambda year, snos, kind="A", **k: (
            ran.append(f"backfill:{kind}:{','.join(map(str, snos))}")
            or {"target": len(snos), "games": len(snos), "failed": [], "failures": []}),
        "scrape_game_details": lambda *a, **k: 1,
        "_pitch_type_step": lambda *a, **k: ran.append("pitch_type") or {"errors": []},
        "_derived_step": lambda *a, **k: ran.append("derived") or {"errors": []},
        "build_splits": lambda *a, **k: ran.append("splits") or {},
        "build_career": lambda *a, **k: ran.append("career") or {},
        "_sync_player_names": lambda: ran.append("name_sync") or 0,
        "_recent_counts": lambda *a, **k: [],
        "_log_refresh": lambda *a, **k: ran.append(f"log:{a[5].get('day_type')}"),
        # #383：選場第四條的 manifest 漂移計數（衍生訊號）；替身＝0 場，不打 DB。
        "_pa_manifest_drift_count": lambda year: 0,
    }
    if pa_build is None:
        stubs["_pa_build_step"] = lambda *a, **k: ran.append("pa_build") or {"errors": []}
    else:
        published, completed = pa_build

        def build_scope(y0, y1, kinds, only_games):
            ran.append("pa_build")
            for game in only_games:
                published.add(game)
            return {"games": len(only_games), "actions": {}, "errors": [],
                    "build_states": {f"{y}-{k}-{s}": "published" for y, k, s in only_games}}

        stubs.update({
            "_active_kinds": lambda year, kinds: ["A"],
            # 與真 SQL 同語意的假集合：當日窗（此處無）∪ 全域缺口（完成但無 published）
            "_pa_build_targets": lambda year, kinds, days: sorted(completed - published),
            "_pa_manifest_drift_targets": lambda year, kinds: [],   # #383 第四條：替身＝無漂移
            "build_scope": build_scope,
            "_pa_build_coverage": lambda year, kinds: {
                "A": {"gap": len(completed - published), "reconciliation_outstanding": 0}},
        })
    for name, value in stubs.items():
        monkeypatch.setattr(rr, name, value)
    monkeypatch.setattr(dg, "weekly_signals", weekly or (lambda *a, **k: [
        dg.DerivedSignal("j3_pitches", False, "fixture"), dg.DerivedSignal("j4_box", False, "fixture")]))


_REAL_WEEKLY_SIGNALS = dg.weekly_signals   # 替身會蓋掉 dg.weekly_signals，先留真函式
_DERIVED_RAN = {"pa_build", "pitch_type", "derived", "splits", "career", "name_sync"}


def _run_main(monkeypatch, day_type: str | None, **kw) -> list[str]:
    from cpbl.ingest import run_refresh_recent as rr

    ran: list[str] = []
    _stub_refresh_main(monkeypatch, rr, ran, **kw)
    monkeypatch.delenv(dg.FORCE_ENV, raising=False)
    if day_type is None:
        monkeypatch.delenv(dg.DAY_TYPE_ENV, raising=False)
    else:
        monkeypatch.setenv(dg.DAY_TYPE_ENV, day_type)
    rr.main()
    return ran


def test_light_day_with_no_source_signal_skips_all_derived_steps(monkeypatch) -> None:
    ran = _run_main(monkeypatch, "light")
    assert not _DERIVED_RAN & set(ran), ran
    assert "log:light" in ran


@pytest.mark.parametrize("kw", [{"new_pitches": 12}, {"games_written": 1}])
def test_light_day_with_any_j1_signal_runs_same_set_as_full_chain(monkeypatch, kw) -> None:
    gated = set(_run_main(monkeypatch, "light", **kw)) & _DERIVED_RAN
    full = set(_run_main(monkeypatch, None, **kw)) & _DERIVED_RAN
    assert gated == full == _DERIVED_RAN


def test_unknown_signal_fails_open(monkeypatch) -> None:
    weekly = lambda *a, **k: [dg.DerivedSignal("j3_pitches", None, "讀不到"),  # noqa: E731
                              dg.DerivedSignal("j4_box", False, "")]
    assert set(_run_main(monkeypatch, "light", weekly=weekly)) & _DERIVED_RAN == _DERIVED_RAN


def test_sync_only_never_scrapes(monkeypatch) -> None:
    from cpbl.ingest import run_refresh_recent as rr

    ran: list[str] = []
    _stub_refresh_main(monkeypatch, rr, ran)
    boom = lambda *a, **k: pytest.fail("甲型只同步不得爬")  # noqa: E731
    for name in ("scrape_games", "scrape_all", "scrape_standings", "scrape_transactions",
                 "_incremental_detail", "_missing_gamelog_snos", "build_championships"):
        monkeypatch.setattr(rr, name, boom)
    monkeypatch.delenv(dg.FORCE_ENV, raising=False)
    monkeypatch.setenv(dg.DAY_TYPE_ENV, "sync_only")
    rr.main()
    assert "log:sync_only" in ran and not _DERIVED_RAN & set(ran)


def test_full_day_runs_every_refresh_step(monkeypatch) -> None:
    ran = _run_main(monkeypatch, None)
    assert _DERIVED_RAN | {"log:full"} <= set(ran)


# ============================================================== (f) 乙型補缺有新資料（08-11 型）

def test_f_light_backfill_runs_pa_derived_splits_and_publishes_the_game(tmp_path, monkeypatch) -> None:
    """08-11 樣本：08-10 J1 失敗 → 乙型；當日補缺迴圈補回 2026/A/253（R5 §1 實例）。

    判日型用真分類器＋假歷史；main() 用真 ``_pa_build_step``／``_build_pa_daily``，下層換成假的
    「已 published」集合——A-253 原本是缺口，跑完必須在 published 裡。
    """
    day = date(2026, 8, 11)
    history = _ok_history(tmp_path, day, previous_state="failed")
    ok, detail = dg.last_j1_status(history, before=datetime(2026, 8, 11, 10, 10, tzinfo=TPE))
    decision = dg.classify(dg.DayInputs(day, REAL_2026_SCHEDULE, ok, detail, False, ""),
                           lambda: pytest.fail("乙型不打 stats"))
    assert decision.day_type == dg.LIGHT

    published = {(2026, "A", 251), (2026, "A", 252)}
    completed = published | {(2026, "A", 253)}
    ran = _run_main(monkeypatch, decision.day_type, backfill_snos=(253,),
                    pa_build=(published, completed))
    assert "backfill:A:253" in ran
    assert {"pa_build", "derived", "splits", "career", "name_sync"} <= set(ran), ran
    assert (2026, "A", 253) in published


# ============================================================== (g) 甲型承接週回補

def _detail(*, failed: str | None = None, skipped: bool = False) -> dict:
    """refresh_log.detail（形狀照 run_refresh_recent.main）：四個衍生步驟。"""
    if skipped:
        note = {"skipped": "§3.2.3：無來源變動訊號"}
        return {"pa_build": {**note, "errors": []}, "pitch_type": {**note, "errors": []},
                "derived": {**note, "errors": []}, "splits_built": dict(note)}
    detail = {"pa_build": {"games": 2, "errors": []}, "pitch_type": {"A_v1": 1, "errors": []},
              "derived": {"team_der": 6, "errors": []}, "splits_built": {"A": 10, "career": {}}}
    if failed == "derived":
        detail["derived"] = {"errors": [{"builder": "team_der", "error": "boom"}]}
    return detail


class WeeklyDB:
    """§3.2.3 訊號 3／4＋前次衍生重試的假 DB：refresh_log 列＋box_pitching_revisions 的 fetched_at。"""

    def __init__(self, refresh_rows, revision_times):
        self.refresh_rows = sorted(refresh_rows, key=lambda r: r[0], reverse=True)
        self.revision_times = revision_times
        self.params = []

    def execute(self, sql, params=None):
        if "FROM cpbl.refresh_log" in sql:
            return FakeResult(self.refresh_rows)
        if "box_pitching_revisions" in sql:
            self.params.append(params)
            return FakeResult([(sum(1 for t in self.revision_times if t > params[0]),)])
        raise AssertionError(sql)


def _weekly_fixture(tmp_path: Path, *, j3_finished: str, j3_pitches: list[int], j4_finished: str,
                    new_revisions: int):
    """真 ``weekly_signals``＋假 DB＋假 J3／J4 狀態檔（格式照 2026-10-19 真實檔）。"""
    base = tmp_path / "repo"
    (base / "logs").mkdir(parents=True, exist_ok=True)
    log = "logs/weekly-game-pitches-20261019-131005.log"
    (base / log).write_text("".join(
        f"2026-10-19 13:22:37,412 INFO cpbl.pitch | done: {{'games': 238, 'pitches': {n}, "
        f"'skipped_frozen': 1}}\n" for n in j3_pitches), encoding="utf-8")
    (base / "logs/last-weekly-pitches.json").write_text(json.dumps(
        {"result": "ok", "exit_code": 0, "year": 2026, "started_at": "2026-10-19T13:10:05+0800",
         "finished_at": j3_finished, "log": log}), encoding="utf-8")
    (base / "logs/last-weekly-box-revisions.json").write_text(json.dumps(
        {"result": "ok", "exit_code": 0, "year": 2026, "days_back": 30,
         "started_at": "2026-10-19T14:10:04+0800", "finished_at": j4_finished}), encoding="utf-8")
    last_ok = datetime(2026, 10, 18, 10, 30, tzinfo=TPE)
    db = WeeklyDB([(last_ok, _detail())],
                  [last_ok + timedelta(hours=i + 1) for i in range(new_revisions)])
    return lambda *a, **k: _REAL_WEEKLY_SIGNALS(db, base=base)


@pytest.mark.parametrize(("case", "fixture", "must_run"), [
    ("J3 新逐球", dict(j3_finished="2026-10-19T13:22:37+0800", j3_pitches=[74033, 42369],
                    j4_finished="2026-10-12T14:11:41+0800", new_revisions=0), {"pitch_type"}),
    ("J4 新修訂列", dict(j3_finished="2026-10-12T13:22:37+0800", j3_pitches=[1],
                     j4_finished="2026-10-12T14:11:41+0800", new_revisions=3),
     {"pa_build", "derived", "splits", "career"}),
])
def test_g_jia_sync_only_takes_over_weekly_backfill(tmp_path, monkeypatch, case, fixture, must_run) -> None:
    weekly = _weekly_fixture(tmp_path, **fixture)
    gated = set(_run_main(monkeypatch, "sync_only", weekly=weekly)) & _DERIVED_RAN
    # 對照：同一來源狀態下完整鏈（未設 DAILY_DAY_TYPE）執行的衍生步驟集合
    full = set(_run_main(monkeypatch, None, weekly=weekly)) & _DERIVED_RAN
    assert must_run <= gated, (case, gated)
    assert gated == full, (case, gated, full)


def test_g_all_signals_zero_runs_no_derived_step(tmp_path, monkeypatch) -> None:
    weekly = _weekly_fixture(tmp_path, j3_finished="2026-10-12T13:22:37+0800", j3_pitches=[5],
                             j4_finished="2026-10-12T14:11:41+0800", new_revisions=0)
    signals = weekly()
    assert [s.fired for s in signals] == [False, False, False], signals
    ran = set(_run_main(monkeypatch, "sync_only", weekly=weekly))
    assert not {"pa_build", "pitch_type", "derived", "splits", "career"} & ran, ran


def test_g_j3_with_zero_pitches_is_not_a_signal(tmp_path) -> None:
    weekly = _weekly_fixture(tmp_path, j3_finished="2026-10-19T13:22:37+0800", j3_pitches=[0, 0],
                             j4_finished="2026-10-12T14:11:41+0800", new_revisions=0)
    assert [s.fired for s in weekly()] == [False, False, False]


def test_g_j4_status_newer_than_last_derived_fires_even_without_new_revision_rows(tmp_path) -> None:
    """§3.2.3 訊號 4 是「新修訂列 **或** J4 完成時刻晚於上次衍生」。"""
    weekly = _weekly_fixture(tmp_path, j3_finished="2026-10-12T13:22:37+0800", j3_pitches=[5],
                             j4_finished="2026-10-19T14:11:41+0800", new_revisions=0)
    assert [s.fired for s in weekly()] == [False, True, False]


def test_g_signal_reads_fail_open(tmp_path) -> None:
    class Broken:
        def execute(self, *a, **k):
            raise RuntimeError("db down")
    assert [s.fired for s in dg.weekly_signals(Broken(), base=tmp_path)] == [None, None, None]


def test_g_sync_only_daily_chain_syncs_after_derived(tmp_path) -> None:
    """「並同步」：sync_only 日 scrape-daily 先跑 cpbl-refresh-recent（衍生）再同步。"""
    result, _status, calls, _repo = _run_daily(tmp_path, gate_type="sync_only")
    assert result.returncode == 0
    assert calls.index("refresh-recent DAILY_DAY_TYPE=sync_only") < next(
        i for i, c in enumerate(calls) if c.startswith("sync DAILY_DAY_TYPE=sync_only"))


# ============================================================== (d) 訓練閘門（假 DB）

# 2026-10-23 本機唯讀實測（exec-3 readonly-checks.txt）：local_outcome_signature＝
# {"test_seasons": [2022..2026], "n_train": 9185, "n_test": 1652}；本機 7/26 那列 model_versions 的
# cv_metrics 為 n_train 9185／n_test 1508。下方以此為真實樣本。
REAL_SIGNATURE = {"test_seasons": [2022, 2023, 2024, 2025, 2026], "n_train": 9185, "n_test": 1652}
REAL_JULY_MODEL = {"test_seasons": [2022, 2023, 2024, 2025, 2026], "n_train": 9185, "n_test": 1508,
                   "best": "LightGBM（全特徵）"}
# 2026-10-24 本機唯讀實測（exec-4 readonly-checks.txt）：2022–2026 各季完成場（含和局）＝非和局
# 290／289／358／358／357 加完成和局 10／11／2／2／3。只取這五季做 game_features 完成數的樣本。
REAL_COMPLETED = {"2022": 300, "2023": 300, "2024": 360, "2025": 360, "2026": 360}


def _prod(model=REAL_SIGNATURE, completed=REAL_COMPLETED) -> dict:
    """正式站兩個量（refresh-cpbl-prod.sh remote_outcome_model_metrics 的一行 JSON）。"""
    return {"model": model, "features_completed": completed}


def _local(signature=REAL_SIGNATURE, completed=REAL_COMPLETED) -> dict:
    return {"signature": signature, "completed_by_season": completed}


def test_d_f1_walk_seasons_constant_matches_trainer() -> None:
    from cpbl.models import outcome_gbm

    assert dg.OUTCOME_WALK_SEASONS == outcome_gbm._WALK_SEASONS


def test_d_f1_signature_equals_what_the_real_backtest_writes(monkeypatch) -> None:
    """等價性：同一批完成場，``outcome_dataset_signature`` 與真 ``backtest()`` 寫進 cv_metrics 的
    test_seasons／n_train／n_test 逐值相同（只把模型擬合換成替身，切分邏輯用真的）。"""
    import numpy as np

    from cpbl.models import outcome_gbm

    per_season = {2019: 7, 2020: 5, 2021: 6, 2022: 4, 2023: 8, 2024: 3, 2025: 9}
    rows = [(season, None, "h", "a", i % 2) + (0.0,) * 40
            for season, n in per_season.items() for i in range(n)]
    monkeypatch.setattr(outcome_gbm, "_load", lambda completed_only: rows)
    monkeypatch.setattr(outcome_gbm, "_fit_predict", lambda train, test: (
        np.full(len(test), 0.5), np.full(len(test), 0.5), 0.5,
        type("G", (), {"feature_importances_": [0] * len(outcome_gbm.REAL_FEATURES)})()))
    result = outcome_gbm.backtest()
    assert dg.outcome_dataset_signature(per_season) == {
        k: result[k] for k in ("test_seasons", "n_train", "n_test")}


def test_d_f1_local_state_counts_completed_ties_and_non_tie_signature() -> None:
    """第 2 輪 F1：完成場集合含和局。非和局數給 trainer 規模比對，含和局總數給 game_features 比對。"""
    db = FakeDB(season_rows=[(2025, 360, 358), (2026, 360, 357)])
    state = dg.local_outcome_state(db)
    sql = db.statements[-1]
    assert "g.kind_code = 'A'" in sql
    assert "FILTER (WHERE g.home_score IS NOT NULL" in sql      # 非和局只用於 trainer 規模
    assert state["signature"] == {"test_seasons": [2026], "n_train": 358, "n_test": 357}
    assert state["completed_by_season"] == {"2025": 360, "2026": 360}       # 和局有算進來


def test_d_f1_tie_only_addition_triggers_training() -> None:
    """Codex 第 2 輪 F1 重現：正式站與本機非和局場數同為 {2025:358, 2026:357}，本機只多一場完成和局
    → 必須跑（舊判準回 (False, '…無新增…')）。"""
    before = dg.local_outcome_state(FakeDB(season_rows=[(2025, 360, 358), (2026, 360, 357)]))
    after = dg.local_outcome_state(FakeDB(season_rows=[(2025, 360, 358), (2026, 361, 357)]))
    assert before["signature"] == after["signature"]                        # trainer 規模看不到和局
    prod = _prod(model=before["signature"], completed=before["completed_by_season"])
    assert dg.outcome_train_decision(before, prod)[0] is False
    run, reason = dg.outcome_train_decision(after, prod)
    assert run is True and "含和局" in reason, reason


@pytest.mark.parametrize(("prod", "run"), [
    (_prod(), False),                          # 正式站上次回測＋鏡像＝本機現況（含 VPS 手動重訓後）→ 不跑
    (_prod(model=REAL_JULY_MODEL), True),      # 正式站還原到 7 月模型 → 跑
    (_prod(model={**REAL_SIGNATURE, "n_test": 1651}), True),   # 本機多一場非和局完成場 → 跑
    (_prod(model={**REAL_SIGNATURE, "test_seasons": [2021, 2022, 2023, 2024, 2025]}), True),   # 新球季
    (_prod(completed={**REAL_COMPLETED, "2026": 359}), True),  # 只多一場完成和局 → 跑
    (_prod(completed={}), True),               # 讀不到正式站 game_features 完成數
    (_prod(completed=None), True),
    (None, True),                              # 讀不到正式站
    ({"model": None, "features_completed": REAL_COMPLETED}, True),   # 正式站無 outcome 模型
    ({"model": {"error": "no completed games"}, "features_completed": REAL_COMPLETED}, True),
])
def test_d_f1_decision_is_against_production_state(prod, run) -> None:
    assert dg.outcome_train_decision(_local(), prod)[0] is run


def test_d_f1_parse_prod_metrics() -> None:
    assert dg.parse_prod_metrics("") is None
    assert dg.parse_prod_metrics("not json") is None
    assert dg.parse_prod_metrics(json.dumps(_prod()) + "\n")["model"]["n_test"] == 1652


_TRAIN_SSH_PREFIX = '''\
import json, os, sys
_cmd = sys.argv[-1] if len(sys.argv) > 1 else ""
_mv = os.environ.get("STUB_MODEL_VERSIONS")
if _mv and "cpbl-train-outcome" in _cmd:
    task = "outcome_simple" if "cpbl-train-outcome-simple" in _cmd else "outcome"
    rows = json.loads(open(_mv, encoding="utf-8").read())
    metrics = json.loads(os.environ["STUB_LOCAL_SIGNATURE"]) if task == "outcome" else {}
    next_id = 1 + max(int(r["id"].rsplit("-", 1)[1]) for r in rows)   # 只增不重用（還原後也不撞號）
    rows.append({"id": "%s-%d" % (task, next_id), "task": task, "cv_metrics": metrics})
    open(_mv, "w", encoding="utf-8").write(json.dumps(rows))
    print("已寫入 model_versions：%s" % rows[-1]["id"])
    raise SystemExit(0)
_feat = os.environ.get("STUB_PROD_FEATURES")
if _feat and "TRUNCATE cpbl.game_features" in _cmd:
    # 3/4 全鏡像：正式站 game_features 的完成數變成本機的；之後交給原樁記錄這次 ssh（不 exit）。
    open(_feat, "w", encoding="utf-8").write(os.environ["STUB_LOCAL_COMPLETED"])
if _mv and "FROM cpbl.model_versions WHERE task = 'outcome'" in _cmd:
    if os.environ.get("STUB_PROD_DOWN") == "1":
        raise SystemExit(255)
    outcome = [r for r in json.loads(open(_mv, encoding="utf-8").read()) if r["task"] == "outcome"]
    model = outcome[-1].get("cv_metrics") if outcome else None
    print(json.dumps({"model": model,
                      "features_completed": json.loads(open(_feat, encoding="utf-8").read())}))
    raise SystemExit(0)
if "trained_through" in _cmd:
    print(os.environ.get("STUB_TRAINED_THROUGH", ""))
    raise SystemExit(0)
'''


_GATE_HELPER = """
import contextlib, json, os, sys
from cpbl.ingest import daily_gate as dg
dg._readonly_conn = lambda: contextlib.nullcontext(None)
dg.local_outcome_state = lambda c: {"signature": json.loads(os.environ["STUB_LOCAL_SIGNATURE"]),
                                    "completed_by_season": json.loads(os.environ["STUB_LOCAL_COMPLETED"])}
sys.exit(dg.main(["train-gate", "--prod-metrics", "-"]))
"""


def _run_prod_sync(tmp_path: Path, *, prod_model: dict | None, trained_through: str,
                   local=REAL_SIGNATURE, model_versions: Path | None = None,
                   prod_completed: dict | None = None, local_completed: dict | None = None,
                   **env_extra: str):
    """跑真 refresh-cpbl-prod.sh（沿用 test_prod_sync_revision_seq 的假樁 harness）。

    假正式站 DB：``model_versions.json``——假 ssh 回答 ``model_versions(task='outcome')`` 查詢，
    收到 ``cpbl-train-outcome*`` 就新增一列。``train-gate`` 跑真 ``daily_gate.main``（本機簽章用替身），
    所以「正式站模型 → shell → 判定 → shell」整條接線都是真的（#364 審核 F1）。
    """
    import test_prod_sync_revision_seq as base

    harness = base._build_harness(tmp_path)
    base._write_exec(harness["bin"] / "ssh",
                     f"#!{sys.executable}\n{_TRAIN_SSH_PREFIX}{base._SSH_STUB}")
    uv_calls = tmp_path / "uv-calls.log"
    base._write_exec(harness["bin"] / "uv", f"""#!/bin/sh
echo "$*" >> "{uv_calls}"
case "$*" in
  *cpbl.completion*) echo 'home_score + away_score > 0' ;;
  *"daily_gate train-gate"*) exec "{sys.executable}" "{tmp_path / 'gate_helper.py'}" ;;
  *) echo "stub uv $*" ;;
esac
""")
    (tmp_path / "gate_helper.py").write_text(_GATE_HELPER, encoding="utf-8")
    model_versions = model_versions or tmp_path / "model_versions.json"
    if not model_versions.exists():   # 傳入既有檔＝延續同一個假正式站（多次執行的序列）
        model_versions.write_text(json.dumps([
            {"id": "outcome-1", "task": "outcome", "cv_metrics": prod_model},
            {"id": "outcome_simple-2", "task": "outcome_simple"}]))
    prod_features = model_versions.with_name(model_versions.stem + "-features.json")
    if not prod_features.exists():    # 假正式站 game_features 各季完成數（與 model_versions 同壽命）
        prod_features.write_text(json.dumps(prod_completed or REAL_COMPLETED), encoding="utf-8")
    (tmp_path / "tmp").mkdir(exist_ok=True)
    env = {
        "PATH": f"{harness['bin']}:/usr/bin:/bin", "HOME": str(tmp_path / "home"),
        "TMPDIR": str(tmp_path / "tmp"), "STUB_LOG_DIR": str(harness["log"]),
        "STUB_HELPER_DIR": str(harness["helpers"]),
        "STUB_LOCAL_SEQ": json.dumps(base.FAKE_LOCAL_SEQ), "STUB_PROD_MAX": json.dumps(base.FAKE_PROD_MAX),
        "VPS": "stub@harness.invalid", "LOCAL_DB": "stub-nonexistent-container",
        "DEPLOY_PATH": "/nonexistent/stub-deploy", "API_INFO_URL": "http://127.0.0.1:1/api/info",
        "SKIP_SCRAPE": "1", "WITH_DETAIL": "1", "DAILY_DAY_TYPE": "full",
        "STUB_MODEL_VERSIONS": str(model_versions), "STUB_TRAINED_THROUGH": trained_through,
        "STUB_LOCAL_SIGNATURE": json.dumps(local),
        "STUB_PROD_FEATURES": str(prod_features),
        "STUB_LOCAL_COMPLETED": json.dumps(local_completed or REAL_COMPLETED),
        **env_extra,
    }
    result = subprocess.run(["/bin/bash", str(harness["repo"] / "scripts" / "refresh-cpbl-prod.sh")],
                            env=env, text=True, capture_output=True, stdin=subprocess.DEVNULL, check=False)
    ids = [r["id"] for r in json.loads(model_versions.read_text())]
    ssh_cmds = [json.loads(p.read_text())["argv"][-1] for p in sorted((harness["log"] / "ssh").glob("*.json"))]
    return result, ids, (uv_calls.read_text().splitlines() if uv_calls.exists() else []), ssh_cmds


def _prev_year() -> str:
    return str(date.today().year - 1)


def test_d_no_new_completed_games_skips_training_and_adds_no_model_version(tmp_path: Path) -> None:
    result, ids, uv_calls, ssh_cmds = _run_prod_sync(tmp_path, prod_model=REAL_SIGNATURE,
                                                     trained_through=_prev_year())

    assert result.returncode == 0, result.stderr[-2000:]
    assert "略過 cpbl-train-outcome（" in result.stdout and "無新增" in result.stdout
    assert "略過 cpbl-train-outcome-simple" in result.stdout
    assert "略過 cpbl-build-features" in result.stdout
    assert ids == ["outcome-1", "outcome_simple-2"]                    # model_versions 無新 id
    assert not [c for c in uv_calls if "cpbl-build-features" in c]
    assert not [c for c in ssh_cmds if "TRUNCATE cpbl.game_features" in c]


def test_d_new_completed_games_train(tmp_path: Path) -> None:
    """控制組：本機比正式站上次回測多 144 場（7 月模型 → 現況）→ 照跑（證明「略過」不是 harness 跑不到）。"""
    result, ids, uv_calls, ssh_cmds = _run_prod_sync(tmp_path, prod_model=REAL_JULY_MODEL,
                                                     trained_through="2020")

    assert result.returncode == 0, result.stderr[-2000:]
    assert ids[2:] == ["outcome-3", "outcome_simple-4"]
    assert any("cpbl-build-features" in c for c in uv_calls)
    assert any("TRUNCATE cpbl.game_features" in c for c in ssh_cmds)


def test_d_f1_production_restored_to_older_model_retrains_without_any_local_state(tmp_path: Path) -> None:
    """審核 F1 路徑 1（同一個假正式站連跑三次）：

    1. 正式站是 7 月模型 → 訓練（新列＝本機現況）；
    2. 再跑一次 → 無新增，略過；
    3. 正式站還原（刪掉剛訓練的那列，回到 7 月模型）、本機不變 → 必須重訓。
    舊實作（本機狀態檔）在第 3 步會因本機指紋未變而略過。
    """
    mv = tmp_path / "prod-model-versions.json"
    run1, ids1, _u, _s = _run_prod_sync(tmp_path / "1", prod_model=REAL_JULY_MODEL,
                                        trained_through=_prev_year(), model_versions=mv)
    assert run1.returncode == 0 and ids1[2:] == ["outcome-3"], run1.stdout
    run2, ids2, _u, _s = _run_prod_sync(tmp_path / "2", prod_model=None,
                                        trained_through=_prev_year(), model_versions=mv)
    assert run2.returncode == 0 and ids2 == ids1 and "無新增" in run2.stdout
    restored = [r for r in json.loads(mv.read_text()) if r["id"] != "outcome-3"]
    mv.write_text(json.dumps(restored))                                         # 正式站還原
    run3, ids3, _u, _s = _run_prod_sync(tmp_path / "3", prod_model=None,
                                        trained_through=_prev_year(), model_versions=mv)
    assert run3.returncode == 0, run3.stderr[-2000:]
    assert "略過 cpbl-train-outcome（" not in run3.stdout, run3.stdout
    assert len(ids3) == len(restored) + 1 and ids3[-1].startswith("outcome-"), ids3


def test_d_f1_manual_retrain_on_vps_is_not_repeated(tmp_path: Path) -> None:
    """審核 F1 路徑 2：VPS 已手動重訓（正式站最新列＝本機現況），本機沒有任何紀錄 → 不重跑。"""
    result, ids, _uv, _ssh = _run_prod_sync(tmp_path, prod_model=REAL_SIGNATURE,
                                            trained_through=_prev_year())
    assert result.returncode == 0 and ids == ["outcome-1", "outcome_simple-2"]


def test_d_f1_production_unreachable_fails_open(tmp_path: Path) -> None:
    result, ids, _uv, _ssh = _run_prod_sync(tmp_path, prod_model=REAL_SIGNATURE,
                                            trained_through=_prev_year(), STUB_PROD_DOWN="1")
    assert result.returncode == 0, result.stderr[-2000:]
    assert ids[2:] == ["outcome-3"] and "讀不到正式站" in result.stdout


def test_d_simple_trainer_gate_reads_artifact_year(tmp_path: Path) -> None:
    """outcome 有新場但 artifact 已訓練到今年−1 → 只跑 outcome，不跑 simple。"""
    result, ids, _uv, _ssh = _run_prod_sync(tmp_path, prod_model=REAL_JULY_MODEL, trained_through=_prev_year())
    assert result.returncode == 0, result.stderr[-2000:]
    assert ids[2:] == ["outcome-3"]
    assert f"trained_through={_prev_year()}" in result.stdout


@pytest.mark.parametrize("day_type", ["light", "sync_only"])
def test_d_light_and_sync_only_never_train(tmp_path: Path, day_type: str) -> None:
    result, ids, uv_calls, _ssh = _run_prod_sync(tmp_path, prod_model=REAL_JULY_MODEL, trained_through="2020",
                                                 DAILY_DAY_TYPE=day_type)
    assert result.returncode == 0, result.stderr[-2000:]
    assert ids == ["outcome-1", "outcome_simple-2"]
    assert not [c for c in uv_calls if "train-gate" in c]


def test_e_force_full_trains_even_without_new_games(tmp_path: Path) -> None:
    result, ids, uv_calls, _ssh = _run_prod_sync(tmp_path, prod_model=REAL_SIGNATURE, trained_through=_prev_year(),
                                                 DAILY_FORCE_FULL="1")
    assert result.returncode == 0, result.stderr[-2000:]
    assert ids[2:] == ["outcome-3", "outcome_simple-4"]
    assert not [c for c in uv_calls if "train-gate" in c]


def test_manual_call_without_day_type_is_unchanged(tmp_path: Path) -> None:
    """手動直呼（未帶 DAILY_DAY_TYPE）＝現況：不呼叫閘門、照訓練。"""
    result, ids, uv_calls, _ssh = _run_prod_sync(tmp_path, prod_model=REAL_SIGNATURE, trained_through=_prev_year(),
                                                 DAILY_DAY_TYPE="")
    assert result.returncode == 0, result.stderr[-2000:]
    assert ids[2:] == ["outcome-3", "outcome_simple-4"]
    assert not [c for c in uv_calls if "train-gate" in c]


def test_unknown_day_type_is_rejected(tmp_path: Path) -> None:
    result, ids, _uv, _ssh = _run_prod_sync(tmp_path, prod_model=REAL_SIGNATURE, trained_through="2020",
                                            DAILY_DAY_TYPE="skip")
    assert result.returncode == 64
    assert ids == ["outcome-1", "outcome_simple-2"]


# ============================================================== 今日賽程檔（#365 介面）

def test_today_schedule_file_shape(fake_db, tmp_path: Path) -> None:
    fake_db.today_rows = [(2026, "C", 4, date(2026, 10, 21), "洲際", "ACN011", "AAA011", "1")]
    out = tmp_path / "today.json"
    payload = dg.write_today_schedule(out, date(2026, 10, 21), day_type="full", stage="after_scrape")
    on_disk = json.loads(out.read_text(encoding="utf-8"))
    assert on_disk == payload
    assert payload["schema_version"] == 1 and payload["date"] == "2026-10-21"
    # #391：F（二軍總冠軍賽）納入今日賽程檔；closed_leagues 為純新增鍵（此處未收官＝空）。
    assert payload["timezone"] == "Asia/Taipei" and payload["kinds"] == ["A", "D", "E", "C", "F"]
    assert payload["counts"] == {"A": 0, "D": 0, "E": 0, "C": 1, "F": 0}
    assert payload["closed_leagues"] == []
    assert payload["games"][0]["key"] == "2026-C-4" and payload["stage"] == "after_scrape"


def test_decide_writes_today_file_even_on_jia_day(fake_db, tmp_path: Path, monkeypatch, capsys) -> None:
    history = _ok_history(tmp_path, date(2026, 10, 15))
    marker = tmp_path / "m.json"
    marker.write_text(json.dumps({"write_counter": 0, "synced_at": "x"}), encoding="utf-8")
    today = tmp_path / "today.json"
    monkeypatch.setattr(dg, "taipei_today", lambda: date(2026, 10, 15))
    monkeypatch.delenv(dg.FORCE_ENV, raising=False)
    rc = dg.main(["decide", "--history", str(history), "--sync-marker", str(marker),
                  "--today-file", str(today), "--assume-probe", "clean"])
    out = capsys.readouterr().out
    assert rc == 0 and out.strip().splitlines()[-1] == "DAY_TYPE=skip"
    payload = json.loads(today.read_text(encoding="utf-8"))
    assert payload["date"] == "2026-10-15" and payload["games"] == [] and payload["day_type"] == "skip"
    assert payload["stage"] == "decide"


def test_decide_prints_closed_leagues_and_skips_retry_when_both_closed(fake_db, tmp_path: Path, monkeypatch,
                                                                        capsys) -> None:
    """#391：兩軍皆收官＋上次 J1 為 69（#383 常態）⇒ 不升級乙型重試、不探測；印 CLOSED_LEAGUES 給 shell。"""
    from test_season_close_schedule import BOTH

    history = _ok_history(tmp_path, date(2026, 10, 29), previous_state="failed")
    marker = tmp_path / "m.json"
    marker.write_text(json.dumps({"write_counter": 0, "synced_at": "x"}), encoding="utf-8")
    today = tmp_path / "today.json"
    monkeypatch.setattr(dg, "taipei_today", lambda: date(2026, 10, 29))
    monkeypatch.setattr(dg, "read_closure", lambda at=None: BOTH)
    monkeypatch.delenv(dg.FORCE_ENV, raising=False)
    rc = dg.main(["decide", "--history", str(history), "--sync-marker", str(marker),
                  "--today-file", str(today), "--assume-probe", "new"])
    lines = capsys.readouterr().out.strip().splitlines()
    assert rc == 0 and lines[-1] == "DAY_TYPE=skip"
    assert "CLOSED_LEAGUES=major,farm" in lines
    assert json.loads(today.read_text(encoding="utf-8"))["closed_leagues"] == ["major", "farm"]


def test_cli_help_is_side_effect_free() -> None:
    result = subprocess.run([sys.executable, "-m", "cpbl.ingest.daily_gate", "--help"],
                            text=True, capture_output=True, check=False,
                            env={**os.environ, "DATABASE_URL": "postgresql://x@127.0.0.1:1/none"})
    assert result.returncode == 0 and "decide" in result.stdout


# ============================================================== 審核 F2：探測回應不明 ≠ 確定無新場

@pytest.mark.parametrize("body", [
    {}, {"Data": None}, {"Data": {}}, {"Data": {"Games": {}}}, {"Data": {"Games": None}},
    {"Data": {"Games": [{"unexpected": "schema"}]}},
    {"Data": {"Games": [{"GameId": "2026-A-1", "KindCode": "C", "GameSno": 1,
                         "PreExeDate": "2026-10-10T18:35:00"}]}},       # 賽別與查詢不符
    {"Data": {"Games": [{"GameId": "2026-E-1", "KindCode": "E", "GameSno": 1}]}},   # 缺開賽時刻
    [], "oops",
])
def test_f2_unreadable_probe_response_is_unavailable_not_clean(body) -> None:
    def fetch(path, params):
        return body if params["kindCode"] == "E" else {"Data": {"Games": []}}
    result = dg.stats_probe(date(2026, 10, 8), fetch=fetch, local_lookup=lambda _g: {})
    assert result.status == "unavailable", result
    decision = dg.classify(_inputs(date(2026, 10, 8)), lambda: result)
    assert decision.day_type == dg.LIGHT


def test_f2_legitimately_empty_schedule_is_still_clean() -> None:
    result = dg.stats_probe(date(2026, 10, 8), fetch=lambda p, q: {"Data": {"Games": []}},
                            local_lookup=lambda _g: {})
    assert result.status == "clean"


# ============================================================== 審核 F3：衍生失敗不推進成功基準

def _f3_db(*, later_detail: dict, revision_hours_after_ok: float | None = 1):
    ok_at = datetime(2026, 10, 20, 10, 30, tzinfo=TPE)          # 上次整組成功（週二）
    later = datetime(2026, 10, 21, 10, 30, tzinfo=TPE)           # J4 觸發的那次衍生
    revisions = [] if revision_hours_after_ok is None else [ok_at + timedelta(hours=revision_hours_after_ok)]
    return ok_at, later, WeeklyDB([(ok_at, _detail()), (later, later_detail)], revisions)


def test_f3_partial_derived_failure_does_not_advance_baseline(tmp_path) -> None:
    """審核 F3 路徑：J4 修訂 → 衍生時當季衍生失敗、分項成功 → 下一次仍須重跑整組。"""
    ok_at, later, db = _f3_db(later_detail=_detail(failed="derived"))
    assert dg.last_refresh_marks(db)[1] == ok_at                    # 基準停在上次整組成功
    signals = dg.weekly_signals(db, base=tmp_path)                  # 無 J3／J4 狀態檔
    by_key = {s.key: s.fired for s in signals}
    assert by_key["j4_box"] is True                                  # 修訂列仍在基準之後
    assert by_key["derived_retry"] is True                           # 前次衍生沒跑完
    steps, _ = dg.derived_decision([dg.DerivedSignal("j1_games", False), *signals],
                                   dg.full_chain_derived())
    assert steps == dg.full_chain_derived()


def test_f3_retry_alone_fires_without_any_new_write(tmp_path) -> None:
    """J1 寫入觸發的衍生失敗（訊號只活在那一次）→ 隔天沒有任何新寫入也要重試。"""
    ok_at, later, db = _f3_db(later_detail=_detail(failed="derived"), revision_hours_after_ok=None)
    by_key = {s.key: s.fired for s in dg.weekly_signals(db, base=tmp_path)}
    assert by_key == {"j3_pitches": False, "j4_box": False, "derived_retry": True}


def test_f3_crashed_run_counts_as_failed_attempt(tmp_path) -> None:
    ok_at, later, db = _f3_db(later_detail={"error": "boom", "pa_build": {"errors": []}},
                              revision_hours_after_ok=None)
    assert {s.key: s.fired for s in dg.weekly_signals(db, base=tmp_path)}["derived_retry"] is True


def test_f3_skipped_runs_after_success_are_not_retries(tmp_path) -> None:
    """負控：之後只有「無訊號略過」的列 → 不重試、全部訊號為 0。"""
    ok_at, later, db = _f3_db(later_detail=_detail(skipped=True), revision_hours_after_ok=None)
    assert [s.fired for s in dg.weekly_signals(db, base=tmp_path)] == [False, False, False]


def test_f3_full_success_advances_baseline(tmp_path) -> None:
    ok_at, later, db = _f3_db(later_detail=_detail(), revision_hours_after_ok=1)
    assert dg.last_refresh_marks(db)[1] == later
    assert {s.key: s.fired for s in dg.weekly_signals(db, base=tmp_path)}["j4_box"] is False


# ============================================================== 審核 F4：覆寫失敗不得留下同日舊檔

def test_f4_write_failure_removes_same_day_file(fake_db, tmp_path, monkeypatch) -> None:
    out = tmp_path / "today.json"
    dg.write_today_schedule(out, date(2026, 10, 23), day_type="light", stage="decide")
    assert json.loads(out.read_text(encoding="utf-8"))["date"] == "2026-10-23"

    def boom(*a, **k):
        raise OSError("disk full")
    monkeypatch.setattr(dg, "today_games", boom)
    with pytest.raises(OSError):
        dg.write_today_schedule(out, date(2026, 10, 23), day_type="light", stage="after_scrape")
    assert not out.exists()


def test_f4_scrape_daily_removes_file_when_overwrite_fails(tmp_path) -> None:
    """審核 F4 路徑：decide 已寫「今日、零場」→ 乙型爬取 → 覆寫失敗（uv／python 起不來）→ 不得留檔。"""
    repo = tmp_path / "repo"
    (repo / "logs").mkdir(parents=True)
    stale = repo / "logs" / "daily-schedule-today.json"
    stale.write_text(json.dumps({"schema_version": 1, "date": date.today().isoformat(),
                                 "stage": "decide", "games": []}), encoding="utf-8")
    result, status, calls, _repo = _run_daily(tmp_path, gate_type="light",
                                              extra_env={"STUB_TODAY_FAIL": "1"})
    assert result.returncode == 0
    assert any(c.startswith("today-schedule") for c in calls)
    assert not stale.exists()


def test_f4_gate_failure_also_removes_file(tmp_path) -> None:
    repo = tmp_path / "repo"
    (repo / "logs").mkdir(parents=True)
    stale = repo / "logs" / "daily-schedule-today.json"
    stale.write_text("{}", encoding="utf-8")
    result, status, _calls, _repo = _run_daily(tmp_path, gate_type="garbage",
                                                extra_env={"STUB_TODAY_FAIL": "1"})
    assert status["day_type"] == "full" and not stale.exists()


# ============================================================== 第 2 輪 F1：只新增完成和局（端到端）

def test_d_f1_tie_only_addition_rebuilds_mirrors_and_retrains_end_to_end(tmp_path: Path) -> None:
    """正式站模型與本機非和局規模相同，本機只多一場 2026 完成和局 → 1/4 重建、3/4 全鏡像、4/4 回測都要跑。"""
    result, ids, uv_calls, ssh_cmds = _run_prod_sync(
        tmp_path, prod_model=REAL_SIGNATURE, trained_through=_prev_year(),
        local_completed={**REAL_COMPLETED, "2026": 361})
    assert result.returncode == 0, result.stderr[-2000:]
    assert "含和局" in result.stdout
    assert ids[2:] == ["outcome-3"]
    assert any("cpbl-build-features" in c for c in uv_calls)
    assert any("TRUNCATE cpbl.game_features" in c for c in ssh_cmds)


# ============================================================== 第 2 輪 F2：讀不懂的日期 ≠ 確定無新場

@pytest.mark.parametrize(("pre_exe", "status"), [
    ("not-a-date", "unavailable"),
    ("2026/10/08T18:35:00", "unavailable"),
    ("2026-13-45T18:35:00", "unavailable"),
    ("2026-10-08 nonsense", "unavailable"),
    ("2026-10-08T18:35:00", "new"),            # 合法日期維持原行為
    ("2026-10-08", "new"),
])
def test_f2_round2_unreadable_pre_exe_date_is_unavailable(pre_exe, status) -> None:
    """Codex 第 2 輪 F2 重現：查詢日 2026-10-08，本機沒有 2026-A-1，身分欄位合法，只換 PreExeDate。"""
    def fetch(path, params):
        rows = []
        if params["kindCode"] == "A" and params["month"] == "10":
            rows = [{"GameId": "2026-A-1", "KindCode": "A", "GameSno": 1, "GameStatus": "SCHEDULED",
                     "PreExeDate": pre_exe}]
        return {"Data": {"Games": rows}}
    result = dg.stats_probe(date(2026, 10, 8), fetch=fetch, local_lookup=lambda _g: {})
    assert result.status == status, result
    if status == "unavailable":
        assert dg.classify(_inputs(date(2026, 10, 8)), lambda: result).day_type == dg.LIGHT


# ============================================================== 第 3 輪 F2：窗口用解析後的日期比較

def _probe_one(pre_exe: str, *, day: date = date(2026, 10, 8), local: dict | None = None) -> dg.ProbeResult:
    """查詢日 2026-10-08；stats 只回 2026-A-1（身分合法），只換 PreExeDate。"""
    def fetch(path, params):
        rows = []
        if params["kindCode"] == "A" and params["month"] == "10":
            rows = [{"GameId": "2026-A-1", "KindCode": "A", "GameSno": 1, "GameStatus": "SCHEDULED",
                     "PreExeDate": pre_exe}]
        return {"Data": {"Games": rows}}
    return dg.stats_probe(day, fetch=fetch, local_lookup=lambda _g: local or {})


@pytest.mark.parametrize(("pre_exe", "status"), [
    # Fable 第 3 輪：合法 ISO 8601、但不是 YYYY-MM-DD 開頭；解析後落在窗口內 → 新場次，⛔ 不得 clean
    ("20261008T183500", "new"),
    ("2026-W41-4T18:35", "new"),
    # Codex 第 2 輪四案例：讀不懂 → unavailable
    ("not-a-date", "unavailable"),
    ("2026/10/08T18:35:00", "unavailable"),
    ("2026-13-45T18:35:00", "unavailable"),
    ("2026-10-08 nonsense", "unavailable"),
    # 合法擴充格式：原行為
    ("2026-10-08T18:35:00", "new"),
    ("2026-10-08", "new"),
])
def test_f2_round3_window_uses_parsed_date(pre_exe, status) -> None:
    result = _probe_one(pre_exe)
    assert result.status == status, (pre_exe, result)
    if status == "new":
        assert result.detail == ("新場次 2026-A-1@2026-10-08",), result
    else:
        assert dg.classify(_inputs(date(2026, 10, 8)), lambda: result).day_type == dg.LIGHT


@pytest.mark.parametrize("pre_exe", ["20261020T183500", "2026-W43-2T18:35"])
def test_f2_round3_parsed_date_outside_window_is_clean(pre_exe) -> None:
    """負控：解析後是 2026-10-20（窗口 10-08～10-15 之外）→ clean；證明不是一律判 new。"""
    assert _probe_one(pre_exe).status == "clean"


def test_f2_round3_date_change_detected_with_basic_format() -> None:
    """日期異動也以解析後日期比：本機 10-10，stats 以基本格式給 10-12 → 異動；給 10-10 → 無異動。"""
    moved = _probe_one("20261012T183500", local={"2026-A-1": "2026-10-10"})
    assert moved.status == "new" and moved.detail == ("日期異動 2026-A-1 本機 2026-10-10 → stats 2026-10-12",)
    same = _probe_one("20261010T183500", local={"2026-A-1": "2026-10-10"})
    assert same.status == "clean", same


def test_f2_round3_unreadable_local_date_is_unavailable() -> None:
    assert _probe_one("2026-10-12T18:35:00", local={"2026-A-1": "garbage"}).status == "unavailable"
