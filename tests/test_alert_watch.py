"""#358 WP6＋WP3'：本機告警 watcher（`com.cpbl.alert-watch`）的行為守衛。

樣本來源（`tests/fixtures/alert_watch/`）：
- `pmset -g systemstate`、`sysctl -n kern.sleeptime`、`docker inspect` 的輸出取自本機
  2026-10-27 06:5x 的**真實執行**（唯讀），原樣入檔。
- DarkWake 時的 systemstate：這裡的 `CPU Network` 寫這組測試時是依 `pmset -g log` DarkWake 旗標
  `[CDNP]` 推論的合成值；之後 #358 exec-2c（FI-S4 一夜取樣）實測 DarkWake 中的 18 筆都正是
  `CPU Network`，與此值一致。
- 晚間鏈狀態檔／今日賽程檔取自主 checkout `logs/` 的真實檔（10-26 C-6 那晚；唯讀擷取，
  去掉與判定無關、含本機路徑的欄位）。標「衍生」的 case 是在真實樣本上改一兩個欄位。

決定性：探針、ping、武裝全部注入；⛔ 不觸網、不呼叫任何告警服務、不碰真實容器。
唯一的子行程 case 只對 127.0.0.1 上一個沒人聽的埠送 ping。
"""

from __future__ import annotations

import copy
import importlib.util
import json
import plistlib
import shutil
import socket
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
WATCH = ROOT / "scripts" / "alert_watch.py"
PING = ROOT / "scripts" / "alert_ping.py"
PLIST = ROOT / "ops" / "launchd" / "com.cpbl.alert-watch.plist"
REGISTRY = ROOT / "scripts" / "schedule-registry.json"
FIX = ROOT / "tests" / "fixtures" / "alert_watch"
SYSTEM_PYTHON = "/usr/bin/python3" if Path("/usr/bin/python3").exists() else sys.executable
TAIPEI = timezone(timedelta(hours=8))
DB, REDIS = "cpbl-analytics-db-1", "cpbl-analytics-redis-1"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


aw = _load("_alert_watch", WATCH)
ap = aw.alert_ping

FULL_WAKE = (FIX / "pmset_systemstate_fullwake.txt").read_text(encoding="utf-8")
SLEEPTIME = (FIX / "sysctl_kern_sleeptime.txt").read_text(encoding="utf-8")
DARKWAKE_SYNTHETIC = "Current System Capabilities are: CPU Network \nCurrent Power State: 4\n"
DOCKER_RUNNING = "running\n"
DOCKER_MISSING_ERR = (FIX / "docker_inspect_missing.txt").read_text(encoding="utf-8")
DOCKER_UNREACHABLE_ERR = (FIX / "docker_inspect_daemon_unreachable.txt").read_text(encoding="utf-8")


def _at(text: str) -> datetime:
    return datetime.fromisoformat(text).astimezone(TAIPEI)


class FakeRunner:
    """依指令回傳預先排好的輸出。`containers` 值：狀態字串、"missing"、"unreachable"、"timeout"。"""

    def __init__(self, *, systemstate: str = FULL_WAKE, sleeptime: str = SLEEPTIME,
                 containers: dict | None = None) -> None:
        self.systemstate, self.sleeptime = systemstate, sleeptime
        self.containers = containers or {DB: "running", REDIS: "running"}
        self.calls: list = []

    def __call__(self, argv: list, timeout: int) -> tuple:
        self.calls.append((list(argv), timeout))
        if argv[0] == aw.PMSET:
            return 0, self.systemstate, ""
        if argv[0] == aw.SYSCTL:
            return 0, self.sleeptime, ""
        if argv[0] == "docker":
            value = self.containers.get(argv[-1], "missing")
            if value == "missing":
                return 1, "", DOCKER_MISSING_ERR
            if value == "unreachable":
                return 1, "", DOCKER_UNREACHABLE_ERR
            if value == "timeout":
                return None, "", "timeout"
            return 0, f"{value}\n", ""
        raise AssertionError(f"unexpected command {argv}")


@dataclass
class _Res:
    ok: bool = True
    attempted: bool = True
    text: str = "ok"

    def summary(self) -> str:
        return f"fake {self.text}"


class Calls:
    def __init__(self, ok: bool = True) -> None:
        self.pings: list = []
        self.arms: list = []
        self.ok = ok

    def pinger(self, config, check, signal, **kw):  # noqa: ANN001
        self.pings.append((check, signal, kw.get("body", "")))
        return _Res(self.ok, True, f"ping {check} {signal}")

    def armer(self, config, check, **kw):  # noqa: ANN001
        self.arms.append((check, kw))
        return _Res(self.ok, True, f"arm {check}")


CONFIG = ap.Config(ping_key="pk-synthetic", api_key="ak-synthetic", ping_base="http://127.0.0.1:9",
                   api_base="http://127.0.0.1:9", timeout=0.1, slug_override="", source="test")


def _run(repo: Path, now: str, runner: FakeRunner, calls: Calls, **kw) -> list:
    return aw.run_once(repo, _at(now), run=runner, config=CONFIG, pinger=calls.pinger,
                       armer=calls.armer, **kw)


def _state(repo: Path) -> dict:
    return json.loads((repo / aw.STATE_PATH).read_text(encoding="utf-8"))


# =========================================================== 探針的真實樣本

def test_real_full_wake_sample_counts_as_awake() -> None:
    assert aw.parse_capabilities(FULL_WAKE) == ["CPU", "Graphics", "Audio", "Network"]
    assert aw.parse_sleeptime(SLEEPTIME) == [1792970939, 136195]


def test_real_pmset_log_shows_darkwake_without_video_flag() -> None:
    """旁證（不是 systemstate 本身）：真實 `pmset -g log` 的 DarkWake 旗標沒有 V（video），完全喚醒有。"""
    import re

    lines = (FIX / "pmset_log_wake_excerpt.txt").read_text(encoding="utf-8").splitlines()
    flags = [(("DarkWake from" in ln), re.search(r"\[([A-Z]+)\]", ln).group(1)) for ln in lines]
    assert any(dark for dark, _ in flags) and any(not dark for dark, _ in flags)
    assert all(("V" not in f) if dark else ("V" in f) for dark, f in flags)


def test_darkwake_without_graphics_is_not_awake() -> None:
    obs = aw.observe(_at("2026-10-27T03:00:00+08:00"), (DB,), FakeRunner(systemstate=DARKWAKE_SYNTHETIC))
    assert obs["awake"] is False


@pytest.mark.parametrize(("value", "expected"), [
    ("running", "running"), ("exited", "exited"), ("created", "created"),
    ("restarting", "restarting"), ("missing", aw.MISSING),
    ("unreachable", aw.DAEMON_UNREACHABLE), ("timeout", aw.DAEMON_UNREACHABLE),
])
def test_container_status_classification_from_real_outputs(value: str, expected: str) -> None:
    obs = aw.observe(_at("2026-10-27T12:00:00+08:00"), (DB,), FakeRunner(containers={DB: value}))
    assert obs["containers"][DB] == expected
    assert obs["down"] is (expected != "running")


def test_daemon_unreachable_is_down_and_labelled() -> None:
    """D1：OrbStack 沒開或卡住也算停擺，訊息標明 Docker 無回應。"""
    obs = aw.observe(_at("2026-10-27T12:00:00+08:00"), (DB, REDIS),
                     FakeRunner(containers={DB: "unreachable", REDIS: "unreachable"}))
    assert obs["down"] and obs["reason"] == "Docker 無回應"


# ======================================================== 驗收 5：判定表

def _obs(at: str, *, awake=True, down=True, sleeptime=(1792970939, 136195), reason="x=exited") -> dict:
    return {"at": _at(at).isoformat(), "awake": awake, "down": down,
            "sleeptime": list(sleeptime) if sleeptime else None, "reason": reason}


T0, T5 = "2026-10-27T18:21:46+08:00", "2026-10-27T18:26:46+08:00"


@pytest.mark.parametrize(("prev", "cur", "expected"), [
    (_obs(T0), _obs(T5), "fail"),                                          # 醒著、沒睡、連兩次停擺
    (None, _obs(T5), None),                                                # 只有一次觀測
    (_obs(T0), _obs(T5, awake=False), None),                               # 本次不是完全喚醒
    (_obs(T0, awake=False), _obs(T5), None),                               # 上次不是完全喚醒（剛醒）
    (_obs(T0), _obs(T5, sleeptime=(1792999999, 0)), None),                 # 中間睡過
    (_obs(T0, sleeptime=None), _obs(T5, sleeptime=None), None),            # 量不到 sleeptime
    (_obs(T0, down=False), _obs(T5), None),                                # 第一次看到停擺
    (_obs("2026-10-27T18:24:46+08:00"), _obs(T5), None),                   # 間隔 2 分（<4）
    (_obs("2026-10-27T18:01:46+08:00"), _obs(T5), None),                   # 間隔 25 分（>15）
])
def test_services_decision_table(prev, cur, expected) -> None:
    action, _ = aw.services_decision(prev, cur, None, _at(T5))
    assert action == expected


@pytest.mark.parametrize(("prev_down", "last_ok", "expected"), [
    (True, "2026-10-27T18:20:00+08:00", "success"),     # 恢復：上次停擺
    (False, None, "success"),                           # 從沒送過成功
    (False, "2026-10-27T17:50:00+08:00", None),         # 36 分前送過
    (False, "2026-10-27T17:20:00+08:00", "success"),    # 滿 60 分
])
def test_services_healthy_success_ping_cadence(prev_down, last_ok, expected) -> None:
    prev = _obs(T0, down=prev_down)
    cur = _obs(T5, down=False)
    action, _ = aw.services_decision(prev, cur, _at(last_ok) if last_ok else None, _at(T5))
    assert action == expected


def test_services_end_to_end_two_runs_then_recovery(tmp_path: Path) -> None:
    """10-23 形狀：Docker 重啟後 redis 沒起來（Mac 醒著）→ 第二次觀測送 /fail；修好後送成功。"""
    calls = Calls()
    stopped = FakeRunner(containers={DB: "running", REDIS: "exited"})
    _run(tmp_path, T0, stopped, calls, only="services")
    assert calls.pings == []
    _run(tmp_path, T5, stopped, calls, only="services")
    assert calls.pings == [(ap.CHECK_SERVICES, "fail", f"{REDIS}=exited")]
    _run(tmp_path, "2026-10-27T18:31:46+08:00", stopped, calls, only="services")
    assert len(calls.pings) == 2  # 仍停擺：每次都再送 /fail（服務端只在轉換時寄信）
    _run(tmp_path, "2026-10-27T18:36:46+08:00", FakeRunner(), calls, only="services")
    assert calls.pings[-1][:2] == (ap.CHECK_SERVICES, "success")
    assert _state(tmp_path)["services"]["last_obs"]["down"] is False


def test_sleep_between_observations_never_fires(tmp_path: Path) -> None:
    """裁定 6418264766 第 3 題：Mac 睡眠期間容器也會停，那不算；醒來第一次觀測也不算。"""
    calls = Calls()
    _run(tmp_path, T0, FakeRunner(containers={DB: "exited", REDIS: "exited"}), calls, only="services")
    woke = FakeRunner(sleeptime="{ sec = 1793050000, usec = 1 } Tue Oct 27 18:30:00 2026\n",
                      containers={DB: "exited", REDIS: "exited"})
    _run(tmp_path, T5, woke, calls, only="services")
    assert calls.pings == []
    _run(tmp_path, "2026-10-27T18:31:46+08:00", woke, calls, only="services")
    assert [p[1] for p in calls.pings] == ["fail"]


def test_darkwake_runs_never_ping(tmp_path: Path) -> None:
    calls = Calls()
    dark = FakeRunner(systemstate=DARKWAKE_SYNTHETIC, containers={DB: "exited", REDIS: "exited"})
    for minute in (0, 5, 10, 15):
        _run(tmp_path, f"2026-10-27T03:{minute:02d}:00+08:00", dark, calls, only="services")
    assert calls.pings == []


def test_only_evening_runs_no_probes(tmp_path: Path) -> None:
    runner = FakeRunner()
    _run(tmp_path, T0, runner, Calls(), only="evening")
    assert runner.calls == []


# ========================================================= 晚間鏈（WP3'）

def _evening_repo(tmp_path: Path, *, today: dict | None, state: dict | None,
                  last: dict | None = None) -> Path:
    logs = tmp_path / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    for name, doc in ((aw.TODAY_FILE, today), (aw.EVENING_STATE, state), (aw.EVENING_LAST, last)):
        if doc is not None:
            (tmp_path / name).write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    return tmp_path


def _fixture(name: str) -> dict:
    return json.loads((FIX / name).read_text(encoding="utf-8"))


REAL_TODAY = _fixture("daily_schedule_today_2026-10-26.json")       # C-6 一場
REAL_STATE = _fixture("postseason_evening_state_2026-10-27.json")    # C-6 FINISHED、全部 synced
REAL_LAST = _fixture("last_postseason_evening_2026-10-27.json")


def _with_status(state: dict, key: str, status: str) -> dict:
    out = copy.deepcopy(state)
    for row in out["schedule"]:
        if aw._row_key(row) == key:
            row["status"] = status
    return out


@pytest.mark.parametrize(("now", "night"), [
    ("2026-10-26T09:44:59+08:00", "2026-10-25"), ("2026-10-26T09:45:00+08:00", "2026-10-26"),
    ("2026-10-27T00:30:00+08:00", "2026-10-26"), ("2026-10-26T23:59:00+08:00", "2026-10-26"),
])
def test_watch_night_boundaries(now: str, night: str) -> None:
    assert aw.watch_night(_at(now)).isoformat() == night


def test_real_sample_arms_at_start_plus_five_hours(tmp_path: Path) -> None:
    """衍生：真實 10-26 樣本，把 C-6 改回開賽前的 SCHEDULED。C-6 15:05 開賽 ⇒ 期限 20:05。"""
    repo = _evening_repo(tmp_path, today=REAL_TODAY,
                         state=_with_status(REAL_STATE, "2026-C-6", "SCHEDULED"), last=REAL_LAST)
    calls = Calls()
    _run(repo, "2026-10-26T10:30:00+08:00", FakeRunner(), calls, only="evening")
    assert calls.arms == [(ap.CHECK_EVENING, {"cron": "5 15 26 10 *", "tz": "Asia/Taipei",
                                              "grace_seconds": 18000})]
    assert calls.pings == []
    ev = _state(repo)["evening"]
    assert ev["armed"]["kind"] == "start" and ev["armed"]["deadline"].startswith("2026-10-26T20:05")
    _run(repo, "2026-10-26T10:35:00+08:00", FakeRunner(), calls, only="evening")
    assert len(calls.arms) == 1  # 每晚只武裝一次


def test_real_sample_settled_night_sends_one_success(tmp_path: Path) -> None:
    """真實 10-26 終局後的狀態：C-6 FINISHED、pending_sync=false、事件全 synced、halted=null。"""
    repo = _evening_repo(tmp_path, today=REAL_TODAY, state=REAL_STATE, last=REAL_LAST)
    calls = Calls()
    _run(repo, "2026-10-26T17:45:00+08:00", FakeRunner(), calls, only="evening")
    _run(repo, "2026-10-26T17:50:00+08:00", FakeRunner(), calls, only="evening")
    assert calls.pings == [(ap.CHECK_EVENING, "success", "")]


def test_fallback_then_single_correction(tmp_path: Path) -> None:
    """D3：還拿不到開賽時刻 ⇒ 23:35（cron 18:35＋5h）；取得後改一次，之後不再改。"""
    no_rows = copy.deepcopy(REAL_STATE)
    no_rows["schedule"] = [r for r in no_rows["schedule"] if aw._row_key(r) != "2026-C-6"]
    repo = _evening_repo(tmp_path, today=REAL_TODAY, state=no_rows)
    calls = Calls()
    _run(repo, "2026-10-26T10:30:00+08:00", FakeRunner(), calls, only="evening")
    assert calls.arms[0][1]["cron"] == "35 18 26 10 *"

    _evening_repo(tmp_path, today=REAL_TODAY, state=_with_status(REAL_STATE, "2026-C-6", "SCHEDULED"))
    _run(repo, "2026-10-26T12:00:00+08:00", FakeRunner(), calls, only="evening")
    assert calls.arms[1][1]["cron"] == "5 15 26 10 *"

    moved = _with_status(REAL_STATE, "2026-C-6", "SCHEDULED")
    for row in moved["schedule"]:
        if aw._row_key(row) == "2026-C-6":
            row["starts_at"] = "2026-10-26T18:35:00"
    _evening_repo(tmp_path, today=REAL_TODAY, state=moved)
    _run(repo, "2026-10-26T13:00:00+08:00", FakeRunner(), calls, only="evening")
    assert len(calls.arms) == 2 and _state(repo)["evening"]["corrected"] is True


@pytest.mark.parametrize("mutate", [
    lambda t: None,                                                  # 沒有今日賽程檔
    lambda t: {**t, "date": "2026-10-25"},                           # 日期不是今晚
    lambda t: {**t, "schema_version": 2},                            # 不認得的版本
    lambda t: {**t, "games": [{**t["games"][0], "kind_code": "D"}]},  # 只有二軍（不屬晚間鏈）
    lambda t: {**t, "games": []},                                    # 無賽日
])
def test_no_scheduled_game_tonight_never_arms(tmp_path: Path, mutate) -> None:
    repo = _evening_repo(tmp_path, today=mutate(copy.deepcopy(REAL_TODAY)), state=REAL_STATE)
    calls = Calls()
    _run(repo, "2026-10-26T10:30:00+08:00", FakeRunner(), calls, only="evening")
    assert calls.arms == [] and calls.pings == []


@pytest.mark.parametrize(("mutate", "reason"), [
    (lambda s: {**s, "pending_sync": True}, "pending_sync"),
    (lambda s: {k: v for k, v in s.items() if k != "pending_sync"}, "pending_sync"),
    (lambda s: {**s, "events": {"x": {"state": "open"}}}, "open_events"),
    (lambda s: {k: v for k, v in s.items() if k != "events"}, "events_unavailable"),
    (lambda s: _with_status(s, "2026-C-6", "START"), "not_final:2026-C-6:START"),
    (lambda s: _with_status(s, "2026-C-6", "RESERVED"), "not_final:2026-C-6:RESERVED"),
    # 審核第 1 輪 blocking 1（規劃 2 §4.2 第 2 點「欄位缺失一律不送成功」）：審核者重現的三種＋未知值
    (lambda s: {k: v for k, v in s.items() if k != "halted"}, "halted_unavailable"),
    (lambda s: {**s, "events": {"x": {"type": "final_not_ingested"}}}, "event_state_unavailable"),
    (lambda s: {**s, "events": {"x": "synced"}}, "event_malformed"),
    (lambda s: {**s, "events": {"x": {"state": "pending_review"}}}, "event_state_unknown"),
    # 晚間鏈的 ingested＝本機已入庫、尚未同步到正式站（postseason_evening 同步成功才改 synced）
    (lambda s: {**s, "events": {"x": {"state": "ingested"}}}, "event_not_synced"),
])
def test_not_settled_fails_closed(tmp_path: Path, mutate, reason: str) -> None:
    repo = _evening_repo(tmp_path, today=REAL_TODAY, state=mutate(copy.deepcopy(REAL_STATE)))
    calls = Calls()
    _run(repo, "2026-10-26T22:00:00+08:00", FakeRunner(), calls, only="evening")
    assert all(p[1] != "success" for p in calls.pings)
    assert _state(repo)["evening"]["settled_reason"] == reason


def test_postponed_counts_as_terminal(tmp_path: Path) -> None:
    repo = _evening_repo(tmp_path, today=REAL_TODAY,
                         state=_with_status(REAL_STATE, "2026-C-6", "POSTPONED"))
    calls = Calls()
    _run(repo, "2026-10-26T19:00:00+08:00", FakeRunner(), calls, only="evening")
    assert (ap.CHECK_EVENING, "success", "") in calls.pings


def test_halted_sends_69_once(tmp_path: Path) -> None:
    last = {**REAL_LAST, "halted": {"reason": "sync_exit_66", "at": "2026-10-26T13:00:00+00:00"}}
    repo = _evening_repo(tmp_path, today=REAL_TODAY, state=REAL_STATE, last=last)
    calls = Calls()
    _run(repo, "2026-10-26T21:00:00+08:00", FakeRunner(), calls, only="evening")
    _run(repo, "2026-10-26T21:05:00+08:00", FakeRunner(), calls, only="evening")
    halted = [p for p in calls.pings if p[1] == 69]
    assert len(halted) == 1 and "sync_exit_66" in halted[0][2]


class FlakyArmCalls(Calls):
    """審核第 1 輪 blocking 2 的重現：前 `failures` 次武裝失敗、之後恢復。"""

    def __init__(self, failures: int) -> None:
        super().__init__()
        self.failures = failures

    def armer(self, config, check, **kw):  # noqa: ANN001
        self.arms.append((check, kw))
        ok = len(self.arms) > self.failures
        return _Res(ok, True, f"arm {check}")


def test_arm_failure_recovers_the_same_night(tmp_path: Path) -> None:
    """規劃 2 §4.2 第 1 點、驗收 1：API 短暫故障不得讓當晚放棄武裝。前三次失敗，第四次就要武裝上。"""
    repo = _evening_repo(tmp_path, today=REAL_TODAY,
                         state=_with_status(REAL_STATE, "2026-C-6", "SCHEDULED"))
    calls = FlakyArmCalls(failures=3)
    for at in ("10:30", "10:35", "10:40", "11:00", "18:00"):
        _run(repo, f"2026-10-26T{at}:00+08:00", FakeRunner(), calls, only="evening")
    assert len(calls.arms) == 4  # 第四次成功之後就不再呼叫
    ev = _state(repo)["evening"]
    assert ev["armed"]["deadline"].startswith("2026-10-26T20:05") and ev["armed"]["kind"] == "start"
    assert ev["arm_failures"] == 3


def test_arm_keeps_retrying_while_api_is_down(tmp_path: Path) -> None:
    """一直失敗就每次喚醒都再試（沒有放棄上限）；每次都只是一個有逾時的 API 請求。"""
    repo = _evening_repo(tmp_path, today=REAL_TODAY,
                         state=_with_status(REAL_STATE, "2026-C-6", "SCHEDULED"))
    calls = Calls(ok=False)
    for minute in range(0, 30, 5):
        _run(repo, f"2026-10-26T10:{30 + minute:02d}:00+08:00", FakeRunner(), calls, only="evening")
    assert len(calls.arms) == 6
    assert _state(repo)["evening"]["armed"] is None


def test_clinched_series_unplayed_game_is_not_distinguishable(tmp_path: Path) -> None:
    """規劃 2 §4.2 第 4 點：系列已封王，官方仍列 C-7 10-27 18:35 SCHEDULED。

    真實狀態檔（10-27 06:51）裡 C-7 就是 SCHEDULED；本機 `present_status` 全史只觀測到 1
    （docs/research/GAME-RECAP-STATUS1_REVIEW.md §2.1），兩個來源都分不出「不會進行」。
    今日賽程檔是衍生的（10-27 J1 尚未執行）。本 case 釘住**現行行為**：會武裝、永遠不終局
    ⇒ 到 23:35 期限告警。需求方已裁定接受誤報（#358 issuecomment-6430106528），⛔ 不改這個行為。
    """
    today = copy.deepcopy(REAL_TODAY)
    today["date"] = "2026-10-27"
    today["games"] = [{**today["games"][0], "key": "2026-C-7", "game_sno": 7, "game_date": "2026-10-27"}]
    repo = _evening_repo(tmp_path, today=today, state=REAL_STATE, last=REAL_LAST)
    calls = Calls()
    _run(repo, "2026-10-27T10:30:00+08:00", FakeRunner(), calls, only="evening")
    _run(repo, "2026-10-27T23:00:00+08:00", FakeRunner(), calls, only="evening")
    assert calls.arms[0][1]["cron"] == "35 18 27 10 *"
    assert calls.pings == []
    assert _state(repo)["evening"]["settled_reason"] == "not_final:2026-C-7:SCHEDULED"


# ============================================ fail-open（驗收 6）與 CLI

def _closed_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def test_subprocess_fail_open_on_unreachable_service(tmp_path: Path) -> None:
    """系統 Python 實跑：ping 打到沒人聽的埠 ⇒ rc 0、狀態檔照寫、金鑰不外露。"""
    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    shutil.copy2(WATCH, repo / "scripts" / "alert_watch.py")
    shutil.copy2(PING, repo / "scripts" / "alert_ping.py")
    port = _closed_port()
    (repo / ".env").write_text(f"CPBL_HC_PING_KEY=pk-synthetic-sub\nCPBL_HC_PING_BASE=http://127.0.0.1:{port}\n"
                               "CPBL_HC_TIMEOUT_SECONDS=0.3\n", encoding="utf-8")
    last = {**REAL_LAST, "halted": {"reason": "sync_exit_66"}}
    _evening_repo(repo, today=REAL_TODAY, state=REAL_STATE, last=last)
    result = subprocess.run([SYSTEM_PYTHON, str(repo / "scripts" / "alert_watch.py"), "--repo", str(repo),
                             "--only", "evening", "--now", "2026-10-26T21:00:00+08:00"],
                            cwd=repo, env={"PATH": "/usr/bin:/bin", "HOME": str(repo)},
                            text=True, capture_output=True, timeout=60, check=False)
    assert result.returncode == 0, result.stderr
    assert "failed" in result.stdout and "pk-synthetic-sub" not in result.stdout + result.stderr
    state = json.loads((repo / aw.STATE_PATH).read_text(encoding="utf-8"))
    assert state["evening"]["halted_sent"] is None  # 沒送成功 ⇒ 下次再試


def test_cli_help_is_side_effect_free(tmp_path: Path) -> None:
    result = subprocess.run([SYSTEM_PYTHON, str(WATCH), "--help"], cwd=tmp_path, text=True,
                            capture_output=True, timeout=30, check=False)
    assert result.returncode == 0 and "會寫什麼" in result.stdout
    assert list(tmp_path.iterdir()) == []


# =============================================== plist 與登記表

def test_plist_is_interval_300_on_system_python() -> None:
    plist = plistlib.loads(PLIST.read_bytes())
    assert plist["Label"] == "com.cpbl.alert-watch"
    assert plist["StartInterval"] == 300
    args = plist["ProgramArguments"]
    assert args[0] == "/usr/bin/python3" and args[1].endswith("/scripts/alert_watch.py")
    assert "--repo" in args
    assert "/usr/local/bin" in plist["EnvironmentVariables"]["PATH"]  # docker CLI（OrbStack）


def test_registry_alert_segments_match_watcher_constants() -> None:
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    jobs = {j["label"]: j for j in registry["jobs"]}
    watch = jobs["com.cpbl.alert-watch"]
    assert watch["plist"] == "ops/launchd/com.cpbl.alert-watch.plist"
    assert watch["cadence"] == {"kind": "interval", "seconds": 300}
    assert watch["status_path"] == "logs/alert-watch/state.json" == str(aw.STATE_PATH)
    assert watch["alert"]["check"] == ap.CHECK_SERVICES
    assert watch["alert"]["interval_seconds"] == watch["cadence"]["seconds"]
    evening = watch["evening_alert"]
    assert evening["check"] == ap.CHECK_EVENING and evening["for"] == "com.cpbl.postseason-evening"
    assert "alert" not in jobs["com.cpbl.postseason-evening"]  # 晚間鏈條目刻意不動（#371 revert 範圍）
    assert evening["deadline_after_start_minutes"] * 60 == aw.EVENING_GRACE.total_seconds()
    assert evening["fallback_deadline"] == aw.FALLBACK_DEADLINE.strftime("%H:%M")
