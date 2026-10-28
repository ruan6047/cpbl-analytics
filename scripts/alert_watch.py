#!/usr/bin/env python3
# LIFECYCLE: standing · 常設工具——這就是給你跑的；不要刪
"""本機告警 watcher（#358 WP6＋WP3'；launchd job `com.cpbl.alert-watch`，每 300 秒一次）。

兩件事，各自獨立、都不改被觀測的鏈：

1. **本機服務停擺**（驗收 5；需求方裁定 6418264766、D1／D2 6429157634）：只讀觀測
   `cpbl-analytics-db-1`、`cpbl-analytics-redis-1` 的容器狀態。**連續兩次觀測都「Mac 完全醒著」、
   中間沒睡過、而且都停擺**才送 `/fail` 到 healthchecks check `services`；Docker daemon 無回應也算停擺
   （D1）。睡眠、DarkWake、剛醒的第一次觀測都不送——`services` 只認明確的 `/fail`，不靠沉默告警，
   所以 Mac 睡著不會誤報（6418264766 第 3 題）。
2. **晚間鏈**（check `evening`；門檻＝開賽＋5h，裁定 6348735853 第 5 項；D3 fallback 23:35）：
   讀今日賽程檔與晚間鏈狀態檔，「今晚有 A／E／C 排定場」才以 Management API 武裝；全部終態且已同步
   就送成功；`halted` 立即送 `/69`。plan FATAL（70）不立即送，由期限涵蓋（裁定第 6 項）。
   ⛔ 不改 `postseason-evening.sh`／`postseason_evening.py`（規劃 2 §4.2）。

## 「Mac 醒著」的判準（規劃 2 §3.2）

`awake`＝`pmset -g systemstate` 的能力清單含 `Graphics`（完全喚醒實測 `CPU Graphics Audio Network`）；
`continuous`＝兩次觀測的 `kern.sleeptime` 相同（中間沒入睡）。DarkWake 沒有 Graphics 有旁證：
`pmset -g log` 的 DarkWake 列旗標是 `[CDNP]`／`[CDNPB]`、完全喚醒是 `[CDNVA]`（V＝video）。DarkWake 當下的
systemstate 已實測（#358 exec-2c，FI-S4 一夜取樣）：落在 DarkWake 的 18 筆都是 `CPU Network`、沒有 Graphics。
限制：取樣由使用者程序觸發、不是 launchd，單夜／單機／AC。⛔ 不改用沉默告警。

## 隔離（刻意）

stdlib only、跑系統 `/usr/bin/python3`；⛔ 不取 refresh lock、不連 DB、不寫 DB、不動容器
（只跑 `docker inspect`）。每次觀測都有上限：docker 15 秒、pmset／sysctl 5 秒、ping 見 alert_ping.py。
本機狀態只寫 `logs/alert-watch/state.json`；ping／武裝結果一行一筆印到 stdout（遮罩過）。
所有 ping 一律 fail-open（驗收 6）：失敗不影響兩鏈，也不讓本 job 以外的任何東西失敗。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from collections.abc import Callable
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
import alert_ping  # noqa: E402 — 同目錄模組；sys.path 先補上才能在 launchd 下載入

TAIPEI = timezone(timedelta(hours=8))
STATE_SCHEMA = 1
DEFAULT_CONTAINERS = ("cpbl-analytics-db-1", "cpbl-analytics-redis-1")
STATE_PATH = Path("logs") / "alert-watch" / "state.json"
TODAY_FILE = Path("logs") / "daily-schedule-today.json"
EVENING_STATE = Path("logs") / "postseason-evening-state.json"
EVENING_LAST = Path("logs") / "last-postseason-evening.json"

PMSET = "/usr/bin/pmset"
SYSCTL = "/usr/sbin/sysctl"
PROBE_TIMEOUT = 5
DOCKER_TIMEOUT = 15

# D2：每 300 秒一次、連 2 次確認。兩次觀測間隔須落在 4–15 分鐘（規劃 2 §3.4）。
CONFIRM_MIN = timedelta(minutes=4)
CONFIRM_MAX = timedelta(minutes=15)
OK_REFRESH = timedelta(minutes=60)
DAEMON_UNREACHABLE = "daemon_unreachable"
MISSING = "missing"

# 晚間鏈（規劃 2 §4.2）。賽別與「一晚」的界線沿用晚間鏈既有定義（Runbook §10 動作條件）。
EVENING_KINDS = ("A", "E", "C")
TODAY_STAGES = ("decide", "after_scrape")
TERMINAL_STATUSES = frozenset({"FINISHED", "POSTPONED"})  # 同 postseason_evening.A_FETCH_RELEASE_STATUSES
EVENING_GRACE = timedelta(hours=5)                         # 裁定 6348735853 第 5 項
FALLBACK_DEADLINE = time(23, 35)                           # D3 6429157634
NIGHT_START = time(9, 45)
# 晚間鏈事件的終態（postseason_evening：open → ingested（本機已入庫）→ synced（已同步），或 unreached
# （交隔日每日鏈）。白名單：新增其他值時這裡會判不成立（fail closed），不會被當成已結。
SETTLED_EVENT_STATES = frozenset({"synced", "unreached"})
HALTED_EXIT = 69
START_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}", re.ASCII)
_SLEEPTIME_RE = re.compile(r"sec\s*=\s*(\d+),\s*usec\s*=\s*(\d+)")
_CAPS_RE = re.compile(r"Current System Capabilities are:(.*)")

Runner = Callable[[list, int], tuple]


# ------------------------------------------------------------------ 指令與探針

def run_command(argv: list, timeout: int) -> tuple:
    """回 (returncode | None, stdout, stderr)。逾時與找不到指令都回 None，⛔ 不拋。"""
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, check=False)
        return proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired:
        return None, "", "timeout"
    except OSError as error:
        return None, "", f"{type(error).__name__}"


def parse_capabilities(text: str) -> list | None:
    match = _CAPS_RE.search(text or "")
    return match.group(1).split() if match else None


def parse_sleeptime(text: str) -> list | None:
    match = _SLEEPTIME_RE.search(text or "")
    return [int(match.group(1)), int(match.group(2))] if match else None


def classify_container(rc: int | None, out: str, err: str) -> str:
    if rc == 0 and out.strip():
        return out.strip().splitlines()[0].strip()
    if rc is not None and "no such object" in (err or "").lower():
        return MISSING
    return DAEMON_UNREACHABLE


def observe(now: datetime, containers: tuple, run: Runner = run_command) -> dict:
    rc, out, _ = run([PMSET, "-g", "systemstate"], PROBE_TIMEOUT)
    caps = parse_capabilities(out) if rc == 0 else None
    rc, out, _ = run([SYSCTL, "-n", "kern.sleeptime"], PROBE_TIMEOUT)
    sleeptime = parse_sleeptime(out) if rc == 0 else None
    statuses = {}
    for name in containers:
        statuses[name] = classify_container(
            *run(["docker", "inspect", "--format", "{{.State.Status}}", name], DOCKER_TIMEOUT))
    down = any(s != "running" for s in statuses.values())
    if any(s == DAEMON_UNREACHABLE for s in statuses.values()):
        reason = "Docker 無回應"
    else:
        reason = "、".join(f"{n}={s}" for n, s in statuses.items() if s != "running")
    return {"at": now.isoformat(), "awake": bool(caps and "Graphics" in caps), "capabilities": caps,
            "sleeptime": sleeptime, "containers": statuses, "down": down, "reason": reason}


# ------------------------------------------------------------- 驗收 5：服務

def _parse_at(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else None


def services_decision(prev: dict | None, cur: dict, last_ok_at: datetime | None,
                      now: datetime) -> tuple:
    """回 (動作, 理由)。動作 ∈ {"fail", "success", None}。"""
    if not cur.get("awake"):
        return None, "not_awake"
    if cur.get("down"):
        if not prev:
            return None, "first_observation"
        prev_at, cur_at = _parse_at(prev.get("at")), _parse_at(cur.get("at"))
        continuous = (bool(prev.get("awake")) and cur.get("sleeptime") is not None
                      and prev.get("sleeptime") == cur.get("sleeptime")
                      and prev_at is not None and cur_at is not None
                      and CONFIRM_MIN <= cur_at - prev_at <= CONFIRM_MAX)
        if continuous and prev.get("down"):
            return "fail", cur.get("reason") or "停擺"
        return None, "unconfirmed"
    if (prev and prev.get("down")) or last_ok_at is None or now - last_ok_at >= OK_REFRESH:
        return "success", "healthy"
    return None, "healthy"


# --------------------------------------------------------------- 晚間鏈

def watch_night(now: datetime) -> date:
    local = now.astimezone(TAIPEI)
    return local.date() if local.time() >= NIGHT_START else local.date() - timedelta(days=1)


def load_json(path: Path) -> object:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def tonight_keys(doc: object, night: date) -> list | None:
    """今日賽程檔的「排定場」（同晚間鏈動作條件：不看 present_status）。檔不可用回 None。"""
    if not isinstance(doc, dict) or doc.get("schema_version") != 1:
        return None
    if doc.get("date") != night.isoformat() or doc.get("stage") not in TODAY_STAGES:
        return None
    games = doc.get("games")
    if not isinstance(games, list):
        return None
    return [g["key"] for g in games if isinstance(g, dict) and g.get("kind_code") in EVENING_KINDS
            and g.get("game_date") == doc["date"] and isinstance(g.get("key"), str)]


def _row_key(row: dict) -> str:
    return f"{row.get('year')}-{row.get('kind_code')}-{row.get('game_sno')}"


def _schedule_rows(state: object) -> dict:
    rows = state.get("schedule") if isinstance(state, dict) else None
    return {_row_key(r): r for r in rows if isinstance(r, dict)} if isinstance(rows, list) else {}


def parse_start(raw: object) -> datetime | None:
    if not isinstance(raw, str) or not START_RE.fullmatch(raw):
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=TAIPEI)
    except ValueError:
        return None


def evening_deadline(state: object, keys: list, night: date) -> tuple:
    """回 (期限, "start"|"fallback")。今晚每一場都有可解析且屬於今晚的開賽時刻才用開賽＋5h。"""
    rows = _schedule_rows(state)
    starts = []
    for key in keys:
        start = parse_start((rows.get(key) or {}).get("starts_at"))
        if start is None or start.date() != night:
            return datetime.combine(night, FALLBACK_DEADLINE, TAIPEI), "fallback"
        starts.append(start)
    return max(starts) + EVENING_GRACE, "start"


def evening_settled(state: object, keys: list) -> tuple:
    """成功條件（欄位缺失一律不成立＝fail closed，結果是期限告警）。"""
    if not isinstance(state, dict):
        return False, "state_unavailable"
    # 規劃 2 §4.2 第 2 點「欄位缺失一律不送成功」（審核第 1 輪 blocking 1）：每個欄位都要「在、而且是
    # 預期的值」才算成立；缺欄、型別不對、不認得的值一律不成立，結果是期限告警。
    if "halted" not in state:
        return False, "halted_unavailable"
    if state["halted"]:
        return False, "halted"
    if state.get("pending_sync") is not False:
        return False, "pending_sync"
    events = state.get("events")
    if not isinstance(events, dict):
        return False, "events_unavailable"
    for event in events.values():
        if not isinstance(event, dict):
            return False, "event_malformed"
        if "state" not in event:
            return False, "event_state_unavailable"
        if event["state"] == "open":
            return False, "open_events"
        if event["state"] == "ingested":
            return False, "event_not_synced"
        if event["state"] not in SETTLED_EVENT_STATES:
            return False, "event_state_unknown"
    rows = _schedule_rows(state)
    for key in keys:
        status = (rows.get(key) or {}).get("status")
        if status not in TERMINAL_STATUSES:
            return False, f"not_final:{key}:{status}"
    return True, "settled"


def halted_reason(state: object, last: object) -> str | None:
    for doc in (state, last):
        halted = doc.get("halted") if isinstance(doc, dict) else None
        if halted:
            reason = halted.get("reason") if isinstance(halted, dict) else halted
            return str(reason or "halted")
    return None


def cron_for(deadline: datetime) -> str:
    """服務端的期限＝cron 時刻＋grace（5h），所以 cron 設在期限前 5 小時（只對今天生效）。"""
    at = (deadline - EVENING_GRACE).astimezone(TAIPEI)
    return f"{at.minute} {at.hour} {at.day} {at.month} *"


def evening_step(now: datetime, repo: Path, previous: dict | None, config: alert_ping.Config,
                 pinger=alert_ping.ping, armer=alert_ping.arm_schedule) -> tuple:
    """回 (新的 evening 狀態, 紀錄行)。每晚最多武裝一次、改正一次、送一次成功。"""
    night = watch_night(now)
    ev = dict(previous or {})
    if ev.get("night") != night.isoformat():
        ev = {"night": night.isoformat(), "armed": None, "corrected": False, "arm_failures": 0,
              "success_sent": False, "halted_sent": None}
    lines = []
    state, last = load_json(repo / EVENING_STATE), load_json(repo / EVENING_LAST)

    halted = halted_reason(state, last)
    if halted and ev.get("halted_sent") != halted:
        result = pinger(config, alert_ping.CHECK_EVENING, HALTED_EXIT, body=f"halted: {halted}"[:200])
        lines.append(result.summary())
        if result.ok:
            ev["halted_sent"] = halted

    keys = tonight_keys(load_json(repo / TODAY_FILE), night)
    ev["keys"] = keys
    if not keys:
        return ev, lines

    deadline, kind = evening_deadline(state, keys, night)
    armed = ev.get("armed")
    wants_arm = armed is None or (armed.get("kind") == "fallback" and kind == "start"
                                  and not ev.get("corrected")
                                  and armed.get("deadline") != deadline.isoformat())
    # 「每晚最多武裝一次、改正一次」數的是**成功**的武裝（規劃 2 §4.2 第 1 點）。失敗就在下一次喚醒
    # 再試、⛔ 沒有放棄上限（審核第 1 輪 blocking 2：舊版連敗 3 次就放棄整晚，網路恢復也不再武裝，
    # 晚間鏈整天沒跑時就沒有期限告警）。每次只是一個有逾時的 API 請求，5 分鐘一次的成本可忽略。
    if wants_arm:
        result = armer(config, alert_ping.CHECK_EVENING, cron=cron_for(deadline), tz="Asia/Taipei",
                       grace_seconds=int(EVENING_GRACE.total_seconds()))
        lines.append(f"{result.summary()} deadline={deadline.isoformat()} basis={kind}")
        if result.ok:
            if armed is not None:
                ev["corrected"] = True
            ev["armed"] = {"deadline": deadline.isoformat(), "kind": kind, "at": now.isoformat()}
        else:
            ev["arm_failures"] = int(ev.get("arm_failures") or 0) + 1  # 只供檢視，不當上限

    if not ev.get("success_sent"):
        # 兩份狀態檔任一份 halted 都不算成功（偵測器讀的是 last-…；閒置喚醒不重寫它）。
        settled, why = (False, "halted") if halted else evening_settled(state, keys)
        ev["settled_reason"] = why
        if settled:
            result = pinger(config, alert_ping.CHECK_EVENING, "success")
            lines.append(result.summary())
            if result.ok:
                ev["success_sent"] = True
    return ev, lines


# ------------------------------------------------------------------ 主流程

def _write_state(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent,
                                     prefix=f".{path.name}.", delete=False) as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
        temp = Path(handle.name)
    os.replace(temp, path)


def run_once(repo: Path, now: datetime, *, containers: tuple = DEFAULT_CONTAINERS,
             state_path: Path | None = None, only: str | None = None,
             run: Runner = run_command, config: alert_ping.Config | None = None,
             pinger=alert_ping.ping, armer=alert_ping.arm_schedule) -> list:
    """跑一次觀測與判定，寫狀態檔，回紀錄行。"""
    state_path = state_path or (repo / STATE_PATH)
    if config is None:
        env_file = None if os.environ.get(alert_ping.PROC_ENV_FILE) else repo / ".env"
        config = alert_ping.load_config(env_file)
    loaded = load_json(state_path)
    state = loaded if isinstance(loaded, dict) and loaded.get("schema_version") == STATE_SCHEMA else {}
    lines = []

    if only in (None, "services"):
        services = dict(state.get("services") or {})
        obs = observe(now, containers, run)
        action, why = services_decision(services.get("last_obs"), obs,
                                        _parse_at(services.get("last_ok_at")), now)
        if action == "fail":
            result = pinger(config, alert_ping.CHECK_SERVICES, "fail", body=why)
            lines.append(f"{result.summary()} reason={why}")
            services["last_fail_at"] = now.isoformat() if result.ok else services.get("last_fail_at")
        elif action == "success":
            result = pinger(config, alert_ping.CHECK_SERVICES, "success")
            lines.append(result.summary())
            if result.ok:
                services["last_ok_at"] = now.isoformat()
        services["last_obs"] = obs
        services["last_decision"] = {"action": action, "reason": why}
        state["services"] = services

    if only in (None, "evening"):
        ev, ev_lines = evening_step(now, repo, state.get("evening"), config, pinger, armer)
        state["evening"] = ev
        lines += ev_lines

    state["schema_version"] = STATE_SCHEMA
    state["observed_at"] = now.isoformat()
    try:
        _write_state(state_path, state)
    except OSError as error:
        lines.append(f"WARN 狀態檔寫入失敗：{type(error).__name__}")
    return [config.mask(line) for line in lines]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="alert_watch.py",
        description="本機告警 watcher（#358）：本機服務停擺偵測＋晚間鏈武裝／成功／halted。",
        epilog=("在做什麼：只讀 pmset／sysctl／docker inspect 與 logs/ 下的晚間鏈狀態檔，"
                "依判準送 healthchecks ping 或以 Management API 武裝 evening check。\n"
                "會寫什麼：logs/alert-watch/state.json（或 --state）；不取 refresh lock、不連 DB、不動容器。\n"
                "怎麼呼叫：/usr/bin/python3 scripts/alert_watch.py --repo <repo>（launchd 每 300 秒）；"
                "故障注入：CPBL_ALERT_SLUG_OVERRIDE=test 加 --only services --containers <拋棄式容器> --state <暫存檔>"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--repo", type=Path, default=HERE.parent)
    parser.add_argument("--state", type=Path, default=None)
    parser.add_argument("--containers", default=",".join(DEFAULT_CONTAINERS))
    parser.add_argument("--only", choices=("services", "evening"), default=None)
    parser.add_argument("--now", help="ISO 時戳覆寫（決定性回放；含時區）")
    return parser


def main(argv: list | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        now = datetime.fromisoformat(args.now) if args.now else datetime.now(TAIPEI)
        if now.tzinfo is None:
            raise ValueError("--now 必須含時區")
        containers = tuple(c for c in args.containers.split(",") if c)
        for line in run_once(args.repo, now, containers=containers, state_path=args.state,
                             only=args.only):
            print(f"[{now.isoformat()}] {line}")
        return 0
    except Exception as error:  # noqa: BLE001 — 本 job 失敗不得連坐任何東西
        print(f"WARN alert-watch 失敗：{type(error).__name__}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
