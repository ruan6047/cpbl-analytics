"""#365 晚間鏈常設化：賽別參數、「一晚」界線、動作條件（S1／S2；驗收 a、b、c）。

時刻與場次取 2026 真實日期（本機 ``cpbl.games``／``game_schedule_status_revisions`` 唯讀抽出，見
``tests/fixtures/evening_schedule_2026_real.json`` 的 ``_provenance``）。⛔ 不連網、不碰 DB：
DB 與 stats 的入口一律換成「一被呼叫就 raise」的樁。
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from cpbl.ingest import postseason_evening as pe

TPE = ZoneInfo("Asia/Taipei")


def tpe(y, m, d, hh, mm) -> datetime:
    return datetime(y, m, d, hh, mm, tzinfo=TPE)


# =========================================================== S1：晚間賽別（P-EVENING-KINDS）

def test_evening_kinds_default_is_a_e_c_and_d_is_refused():
    assert pe.parse_evening_kinds(None) == ("A", "E", "C")
    assert pe.parse_evening_kinds("") == ("A", "E", "C")
    assert pe.parse_evening_kinds("C,A") == ("A", "C"), "依 A、E、C 排序"
    for bad in ("A,D", "D", "A,A", "a", "A,E,C,F", "A,"):
        with pytest.raises(ValueError):
            pe.parse_evening_kinds(bad)


def test_cli_refuses_d_with_exit_64_before_touching_anything(monkeypatch, tmp_path):
    monkeypatch.setenv("POSTSEASON_EVENING_KINDS", "A,E,C,D")
    monkeypatch.setenv("POSTSEASON_STATE", str(tmp_path / "state.json"))
    assert pe.main(["plan"]) == 64
    assert not (tmp_path / "state.json").exists()


def test_local_sql_takes_kinds_as_a_parameter_not_a_literal(monkeypatch):
    """五段本機 SQL 改成 ``kind_code = ANY(%s)``；設定的賽別以參數送出（AGENTS.md：不拼字串）。"""
    seen: list[tuple[str, object]] = []

    class Cur:
        def fetchall(self):
            return []

    class Conn:
        def execute(self, sql, params=None):
            seen.append((sql, params))
            return Cur()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    import cpbl.db

    monkeypatch.setattr(cpbl.db, "conn", lambda: Conn())
    monkeypatch.setenv("POSTSEASON_EVENING_KINDS", "A,C")
    pe.load_local_games(2026, tpe(2026, 9, 27, 21, 0))
    pe.local_first_seen(2026)
    pe.local_signature(2026)
    pe.local_www_starts(2026)
    assert len(seen) == 5
    for sql, params in seen:
        # 只看外層賽別篩選（最後一個 FROM cpbl.… 之後）；完賽判準 helper 內部自帶的季後範圍不在本卡範圍。
        outer = sql[sql.rindex("FROM cpbl."):]
        assert "IN ('E', 'C')" not in outer and "kind_code = ANY(" in outer, outer
        flat = list(params.values()) if isinstance(params, dict) else list(params or ())
        assert ["A", "C"] in flat, (sql, params)


# =========================================================== S1：一晚界線（P-NIGHT-WINDOW）

@pytest.mark.parametrize(("at", "night"), [
    (tpe(2026, 10, 21, 18, 35), date(2026, 10, 21)),   # C4 開賽
    (tpe(2026, 10, 22, 0, 30), date(2026, 10, 21)),    # 跨過 24:00 仍屬 10-21 的夜
    (tpe(2026, 10, 22, 9, 44), date(2026, 10, 21)),
    (tpe(2026, 10, 22, 9, 45), None),                  # DAILY_GUARD 起點：不屬任何一晚
    (tpe(2026, 10, 22, 11, 59), None),
    (tpe(2026, 10, 22, 12, 0), date(2026, 10, 22)),    # BLOCK_RELEASE_AT：新的一晚
])
def test_night_of_boundaries(at, night):
    assert pe.night_of(at) == night


# =========================================================== S2：今日賽程檔＋動作條件（驗收 a、b、c）

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "evening_schedule_2026_real.json")
                     .read_text(encoding="utf-8"))


def schedule_file(tmp_path: Path, night: str) -> Path:
    path = tmp_path / f"today-{night}.json"
    path.write_text(json.dumps(FIXTURE["schedule_files"][night], ensure_ascii=False), encoding="utf-8")
    return path


class Bombs:
    """DB 與 stats 入口：一被呼叫就記一筆並 raise。測試斷言「沒有呼叫」時，負控組必須「有呼叫」，
    證明樁真的接在路徑上（不是空測）。"""

    def __init__(self, monkeypatch):
        self.db: list[str] = []
        self.stats: list[dict] = []
        import cpbl.db

        def conn(*a, **k):
            self.db.append("conn")
            raise AssertionError("不得連 DB")

        def fetcher(timeout):
            def fetch(path, params):
                self.stats.append(dict(params))
                raise AssertionError("不得連 stats")
            return fetch

        monkeypatch.setattr(cpbl.db, "conn", conn)
        monkeypatch.setattr(pe, "_httpx_fetch", fetcher)


def _env(monkeypatch, tmp_path: Path, schedule: Path | None, now: datetime) -> Path:
    state = tmp_path / "state.json"
    monkeypatch.setenv("POSTSEASON_STATE", str(state))
    monkeypatch.setenv("POSTSEASON_STATUS", str(tmp_path / "last.json"))
    monkeypatch.setenv("POSTSEASON_STARTER_FLAG", str(tmp_path / "starter.enabled"))
    monkeypatch.setenv("POSTSEASON_TODAY_SCHEDULE", str(schedule or tmp_path / "absent.json"))
    monkeypatch.delenv("POSTSEASON_EVENING_KINDS", raising=False)
    monkeypatch.delenv("POSTSEASON_YEAR", raising=False)
    monkeypatch.setattr(pe, "_now", lambda: now)
    return state


def test_plan_dry_prints_a_targets_for_a_real_a_night(monkeypatch, tmp_path, capsys):
    """(a) 2026-09-27：A355／A356／A357 三場＋D229（⛔ 涵蓋 D 的負控）。dry 不連網、不碰 DB、不寫狀態。"""
    bombs = Bombs(monkeypatch)
    state = _env(monkeypatch, tmp_path, schedule_file(tmp_path, "2026-09-27"), tpe(2026, 10, 23, 17, 0))
    assert pe.main(["plan", "--dry", "--now", "2026-09-27T21:00:00"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["targets"] == ["2026-A-355", "2026-A-356", "2026-A-357"]
    assert "2026-D-229" not in out["targets"]
    assert out["gate"]["decision"] == "run" and out["kinds"] == ["A"]
    assert {"now", "starter_enabled", "points"} <= set(out), "#292 先發時點預覽的既有三鍵仍在（Runbook §10）"
    assert out["now"] == "2026-09-27T21:00:00+08:00"
    assert bombs.db == [] and bombs.stats == [] and not state.exists()


def test_plan_dry_second_real_a_night_with_makeup_game(monkeypatch, tmp_path, capsys):
    """(a) 第二樣本 2026-10-04：A270 是 08-16 改期的補賽場，仍以該晚目標場列出。"""
    Bombs(monkeypatch)
    _env(monkeypatch, tmp_path, schedule_file(tmp_path, "2026-10-04"), tpe(2026, 10, 23, 17, 0))
    assert pe.main(["plan", "--dry", "--now", "2026-10-04T20:00:00"]) == 0
    assert json.loads(capsys.readouterr().out)["targets"] == ["2026-A-251", "2026-A-252", "2026-A-270"]


@pytest.mark.parametrize(("night", "at"), [
    ("2026-10-15", tpe(2026, 10, 15, 21, 0)),   # 無任何 A／D／E／C（WP1 甲型樣本）
    ("2026-09-23", tpe(2026, 9, 23, 21, 0)),    # 只有 D215：⛔ 涵蓋 D，必須 quiet
])
def test_no_game_night_plan_exits_quiet_without_db_or_stats(monkeypatch, tmp_path, capsys, night, at):
    """(b) 無賽日：plan 印 quiet、不連 DB、不連 stats、狀態檔位元組不變。"""
    bombs = Bombs(monkeypatch)
    state = _env(monkeypatch, tmp_path, schedule_file(tmp_path, night), at)
    before = json.dumps({**pe.empty_state(), "last_probe_at": "2026-10-12T13:00:00+00:00"})
    state.write_text(before, encoding="utf-8")
    assert pe.main(["plan"]) == 0
    assert capsys.readouterr().out.strip() == "quiet"
    assert bombs.db == [] and bombs.stats == []
    assert state.read_text(encoding="utf-8") == before


def test_quiet_negative_control_same_stubs_are_hit_on_a_game_night(monkeypatch, tmp_path, capsys):
    """(b) 負控：同一組樁換成 09-27（A 夜）必須「有呼叫」——證明上一條的「沒呼叫」不是空測。"""
    bombs = Bombs(monkeypatch)
    _env(monkeypatch, tmp_path, schedule_file(tmp_path, "2026-09-27"), tpe(2026, 9, 27, 21, 0))
    assert pe.main(["plan"]) == 0
    assert capsys.readouterr().out.strip() != "quiet"
    assert bombs.stats, "A 夜必須讀 stats"
    assert {p["kindCode"] for p in bombs.stats} == {"A"}


def test_pending_work_keeps_the_chain_running_on_a_no_game_night(monkeypatch, tmp_path):
    """(b) 無賽日但狀態檔有待辦（未結事件／目標窗內未終態的 box／PA／pending_sync）→ 不得 quiet。"""
    today, problem = pe.read_today_schedule(schedule_file(tmp_path, "2026-10-22"))
    at = tpe(2026, 10, 22, 21, 0)
    assert pe.evening_gate(pe.empty_state(), at, today, problem=problem)[0] == "quiet"
    for state in (
        {**pe.empty_state(), "events": {"final_not_ingested:2026-C-4": {"key": "2026-C-4", "state": "open"}}},
        {**pe.empty_state(), "boxpa": {"2026-C-4": {"key": "2026-C-4", "game_date": "2026-10-22", "state": "open"}}},
        {**pe.empty_state(), "pending_sync": True},
        {**pe.empty_state(), "halted": {"reason": "sync_exit_67"}},
    ):
        decision, _, kinds = pe.evening_gate(state, at, today, problem=problem)
        assert decision == "run", state
        assert kinds, "有待辦時一定有要查的賽別"
    # 過窗的 box／PA 紀錄（例：10-21 的場、10-22 21:00 已過隔日 09:45）不是待辦，否則休賽季永遠連 DB。
    stale = {**pe.empty_state(), "boxpa": {"2026-C-4": {"key": "2026-C-4", "game_date": "2026-10-21", "state": "open"}}}
    assert pe.evening_gate(stale, at, today, problem=problem)[0] == "quiet"


@pytest.mark.parametrize("variant", ["missing", "stale", "broken"])
def test_missing_or_stale_schedule_file_falls_back_to_db(tmp_path, variant):
    """(b) 退路：賽程檔缺、日期是前天、JSON 壞 → fallback_db（連本機 DB 判定），⛔ 不得判 quiet——
    否則 J1 沒跑（Mac 睡過 10:10）就連坐晚間鏈。樣本：2026-10-12 E4 夜。"""
    path = tmp_path / "today.json"
    if variant == "stale":
        path.write_text(json.dumps(FIXTURE["schedule_files"]["2026-10-04"]), encoding="utf-8")
    elif variant == "broken":
        path.write_text('{"date": "2026-10-12", "games": [', encoding="utf-8")
    today, problem = pe.read_today_schedule(path)
    calls: list[date] = []

    def lookup(night):
        calls.append(night)
        return {"E"}

    decision, reason, kinds = pe.evening_gate(pe.empty_state(), tpe(2026, 10, 12, 21, 0), today,
                                              problem=problem, db_lookup=lookup)
    assert (decision, kinds) == ("fallback_db", ("E",)), reason
    assert calls == [date(2026, 10, 12)]
    # 本機 DB 也沒有該晚的場、又無待辦 → 這時才 quiet。
    assert pe.evening_gate(pe.empty_state(), tpe(2026, 10, 15, 21, 0), today, problem=problem,
                           db_lookup=lambda night: set())[0] == "quiet"


def _write(tmp_path: Path, body) -> Path:
    path = tmp_path / "today.json"
    path.write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
    return path


def test_reader_follows_the_364_interface(tmp_path):
    """規劃 4 §5.1：只認 schema_version == 1、stage ∈ decide／after_scrape；不看 present_status、忽略其他欄位。"""
    good = json.loads(json.dumps(FIXTURE["schedule_files"]["2026-09-27"]))
    for stage in ("decide", "after_scrape"):
        today, problem = pe.read_today_schedule(_write(tmp_path, {**good, "stage": stage}))
        assert problem == "" and [g.key for g in today.games][:3] == ["2026-A-355", "2026-A-356", "2026-A-357"]
    postponed = {**good, "games": [{**g, "present_status": 0} for g in good["games"]]}
    assert pe.gate_targets(pe.read_today_schedule(_write(tmp_path, postponed))[0], tpe(2026, 9, 27, 21, 0)) == [
        "2026-A-355", "2026-A-356", "2026-A-357"], "present_status 不影響排定場"
    for bad in ({**good, "schema_version": 2}, {**good, "schema_version": True}, {**good, "schema_version": "1"},
                {k: v for k, v in good.items() if k != "schema_version"}, {**good, "stage": "draft"},
                {k: v for k, v in good.items() if k != "stage"}):
        assert pe.read_today_schedule(_write(tmp_path, bad)) == (None, "schedule_invalid"), bad


def test_invalid_rows_void_the_whole_file(tmp_path):
    """形狀不符整檔作廢（不挑能用的列）：半套清單會讓「這場不在檔裡」被讀成今晚沒有比賽。"""
    head = {"schema_version": 1, "stage": "decide", "date": "2026-09-27"}
    for body in ({**head, "games": [{"kind_code": "A", "game_sno": "355", "game_date": "2026-09-27"}]},
                 {**head, "games": [{"kind_code": "A", "game_date": "2026-09-27"}]},
                 {**head, "games": [{"kind_code": "A", "game_sno": 355}]},
                 {**head, "games": {"A": 355}},
                 {k: v for k, v in head.items() if k != "date"} | {"games": []}):
        assert pe.read_today_schedule(_write(tmp_path, body)) == (None, "schedule_invalid"), body
    assert pe.read_today_schedule(_write(tmp_path, ["not", "an", "object"])) == (None, "schedule_invalid")


def test_night_window_keeps_last_nights_games_alive_after_midnight(tmp_path):
    """(b) 跨午夜：10-21 C4 延長到 10-22 00:30、10-22 無賽。照日曆日判會在 00:30 quiet、漏掉該場終局。"""
    today, problem = pe.read_today_schedule(schedule_file(tmp_path, "2026-10-21"))
    at = tpe(2026, 10, 22, 0, 30)
    assert pe.night_of(at) == date(2026, 10, 21)
    assert pe.evening_gate(pe.empty_state(), at, today, problem=problem)[:3:2] == ("run", ("C",))
    # 09:45 之後屬於新的一天（且讓位 10:10）；12:00 起是 10-22 的夜，10-22 無賽 → quiet（檔案仍是 10-21 → 走退路）。
    assert pe.evening_gate(pe.empty_state(), tpe(2026, 10, 22, 9, 45), today, problem=problem)[0] == "quiet"
    assert pe.evening_gate(pe.empty_state(), tpe(2026, 10, 22, 12, 0), today, problem=problem,
                           db_lookup=lambda night: set())[0] == "quiet"


@pytest.mark.parametrize(("night", "at", "kinds"), [
    ("2026-09-27", tpe(2026, 9, 27, 21, 0), {"A"}),
    ("2026-10-12", tpe(2026, 10, 12, 21, 0), {"E"}),
    ("2026-10-21", tpe(2026, 10, 21, 21, 0), {"C"}),
])
def test_stats_probe_queries_only_kinds_scheduled_tonight(monkeypatch, tmp_path, capsys, night, at, kinds):
    """(c) stats 只查當晚有排定的賽別（09-27 只查 A；10-12 只查 E；10-21 只查 C），不含 D。"""
    _env(monkeypatch, tmp_path, schedule_file(tmp_path, night), at)
    requested: list[dict] = []

    def fetcher(timeout):
        def fetch(path, params):
            requested.append(dict(params))
            # 規劃 4 §12 第 4 項負控：stats 實測對 D 也回列（#364：kindCode=D、2026-08 回 51 列）。
            # 混一列 KindCode=D（2026-09-27 真實 D229）：不得產生 D 的 StatsGame／事件。
            return {"Data": {"Games": [{"GameId": "2026-D-229", "KindCode": "D", "GameSno": 229,
                                        "GameStatus": "FINISHED", "PreExeDate": "2026-09-27T14:05:00"}]}}
        return fetch

    monkeypatch.setattr(pe, "_httpx_fetch", fetcher)
    monkeypatch.setattr(pe, "load_local_games", lambda year, now: {})
    monkeypatch.setattr(pe, "local_first_seen", lambda year: {})
    monkeypatch.setattr(pe, "publish_signals", lambda state, year, now: None)
    assert pe.main(["plan"]) == 0
    assert capsys.readouterr().out.strip() == "idle"
    assert {p["kindCode"] for p in requested} == kinds
    months = sorted({int(p["month"]) for p in requested})
    assert len(requested) == len(kinds) * len(months), "每個賽別 × 月份恰好一次"
    saved = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    assert saved["gate"]["kinds"] == sorted(kinds) and saved["gate"]["decision"] == "run"
    assert all(g["kind_code"] != "D" for g in saved["schedule"]) and not any("-D-" in k for k in saved["events"])
