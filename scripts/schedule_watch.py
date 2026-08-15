#!/usr/bin/env python3
# LIFECYCLE: standing · 常設工具——這就是給你跑的；不要刪
"""排程缺席／失敗偵測器（OPS-SCHEDULE-FAILURE-BLIND1／#132）。

問題陳述（需求方 2026-08-15 裁定）：**失敗有痕跡但無讀者，且無登記表可判缺席。**

`refresh_log`、`logs/last-*.json`、`logs/*.log`、`launchctl list` 四個面都在寫，但
沒有任何程式讀它們；而「完全沒跑」的日子四個面都是空的——缺席不會產生紀錄，只能
從**預期的節奏**反推，那需要一份宣告節奏的登記表（`scripts/schedule-registry.json`）。

## 判定的形狀：回頭看上一個週期，不是看現在

固定時點的檢查會與被檢查的對象賽跑：實測 27 次每日排程有 8 次（30%）在 11:00 仍在
執行，而 2026-08-10 那次 10:10 開跑、11:50:37 才寫入終態——任何在 11:00 問「現在怎麼
樣」的偵測器都只會得到 `RUNNING`，隔日的成功再把狀態檔覆寫，那次失敗就永遠不會被報。

因此判定對象是**週期**，時點不重要：

    F0 = max{ f ∈ fires(J) : f <= T }   當前週期
    F1 = max{ f ∈ fires(J) : f < F0 }   上一個「已封閉」週期

- **F1 一律判定**：`F0` 已觸發 ⇒ `F1` 的執行窗口在語意上必然結束 ⇒ 零競態
- **F0 只在其歷史紀錄已是終態時才判定**（終態 succeeded／failed／skipped 寫下去就不可
  變 ⇒ 同樣零競態）。`running` 或無紀錄一律不指控——那可能只是還在跑
- 主判定**不含任何耗時常數**。舊的 180 分鐘停滯門檻已被實測證偽：2026-08-04 那次真的
  跑了 287 分鐘且正常結束

## 三種缺席必須分得開，否則部署當天整片誤報然後被關掉

1. **機制還沒上線** → 登記表的 `effective_from`（job 生效日）與 `history_from`（歷史
   寫入器生效日）；只判 `f >= max(兩者)` 的週期
2. **機器沒開** → 這一層由偵測器 B（生產側 `/api/info`）承接，本機 watchdog 與被監控
   對象共用故障域，看不到自己沒開機
3. **跑了沒寫紀錄** → 歷史在動工**前**就寫 `running`，故「開跑後死掉」（INCOMPLETE）
   與「從未開跑」（MISSING）可分辨

## 只採計 launchd 觸發的執行

手動補跑不算「排程有跑」。否則手動救火會把壞掉的排程蓋成健康，正是本卡要消滅的形狀。

## 隔離要求（刻意）

stdlib only、跑 `/usr/bin/python3`。**不得經 uv／venv**——偵測器不可與被監控對象共用
「uv 或 venv 壞掉」這個故障域。不碰 refresh lock、不碰 docker、不連本機 DB；只讀
JSON／plist、跑 `launchctl print`（唯讀）、一次 HTTPS GET。

時區固定 +08:00：台灣 1979 年後無日光節約，固定偏移對本專案涵蓋的所有日期都精確，
且不依賴 tzdata 是否存在（偵測器要在最少的前提下還能跑）。
"""

from __future__ import annotations

import argparse
import json
import os
import plistlib
import re
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

TAIPEI = timezone(timedelta(hours=8))

EXIT_OK = 0
EXIT_MISSING = 2
EXIT_FAILED = 3
EXIT_INCOMPLETE = 4
EXIT_SKIPPED_CONSECUTIVE = 5
EXIT_REGISTRY = 6
EXIT_B_UNREACHABLE = 7
EXIT_B_STALLED = 8
# Plan §5 的表沒有替「RunAtLoad 未兌現」配碼（Plan §7 只要求它「直接進告警」）。
# 本實作補配 9，並在此明載是實作追加而非裁定原文。
EXIT_RUNATLOAD = 9

# 嚴重度排序（大者優先）。刻意**不**用退出碼數值排序：B 側取不到訊號（7）不該蓋過
# 本機真實失敗（3）。通知一律帶上全部 finding，故退出碼只是給 launchctl 看的純量。
SEVERITY = {
    "REGISTRY_INVALID": 100,
    "REGISTRY_INCOMPLETE": 100,
    "REGISTRY_CONFLICT": 100,
    "HISTORY_CORRUPT": 95,
    "JOB_NOT_INSTALLED": 90,
    "FAILED": 80,
    "INCOMPLETE": 75,
    "MISSING": 70,
    "RUNATLOAD_NOT_HONORED": 60,
    "SKIPPED_CONSECUTIVE": 50,
    "B_STALLED": 40,
    "B_UNREACHABLE": 20,
    "B_UNAVAILABLE": 20,
}
EXIT_BY_VERDICT = {
    "REGISTRY_INVALID": EXIT_REGISTRY,
    "REGISTRY_INCOMPLETE": EXIT_REGISTRY,
    "REGISTRY_CONFLICT": EXIT_REGISTRY,
    "HISTORY_CORRUPT": EXIT_REGISTRY,
    "JOB_NOT_INSTALLED": EXIT_MISSING,
    "FAILED": EXIT_FAILED,
    "INCOMPLETE": EXIT_INCOMPLETE,
    "MISSING": EXIT_MISSING,
    "RUNATLOAD_NOT_HONORED": EXIT_RUNATLOAD,
    "SKIPPED_CONSECUTIVE": EXIT_SKIPPED_CONSECUTIVE,
    "B_STALLED": EXIT_B_STALLED,
    "B_UNREACHABLE": EXIT_B_UNREACHABLE,
    "B_UNAVAILABLE": EXIT_B_UNREACHABLE,
}

TERMINAL_STATES = ("succeeded", "failed", "skipped")
DEFAULT_API_URL = "https://cpbl.ruan-ruan.com/api/info"
USER_AGENT = "cpbl-schedule-watchdog/1.0 (+OPS-SCHEDULE-FAILURE-BLIND1)"
# 執行身分由 wrapper 在 bash 層算好後傳進來。
#
# ⚠️ **不可在 Python 這一層讀 `XPC_SERVICE_NAME`**：macOS 只讓 launchd **直接** spawn
# 的那一個行程看到 job label，它的子行程一律被重設為字串 `"0"`。實測 2026-08-15：
# 同一次 launchd 執行裡，bash 自己讀到 `dev.cpbl132.id2a`，而它 fork 出來的
# `/usr/bin/env` 與 `python3` 都讀到 `"0"`。`"0"` 在 Python 是 truthy，於是
# `if os.environ.get("XPC_SERVICE_NAME")` 會**恆為真**——手動跑也會被記成排程跑。
TRIGGER_ENV = "SCHEDULE_WATCH_TRIGGER"
DEFAULT_LOOKBACK_CYCLES = 60
# 開機後多久內沒有本偵測器的執行紀錄，就算 RunAtLoad 沒兌現。launchd 在登入態載入
# LaunchAgent 有排隊延遲，30 分鐘是寬鬆側的取捨，不是量測結果。
RUNATLOAD_GRACE_MINUTES = 30
REQUIRED_JOB_FIELDS = (
    "label", "plist", "cadence", "effective_from", "expected_installed",
    "expected_installed_reason", "status_path", "history_path", "history_from",
)


class _Parser(argparse.ArgumentParser):
    """未知參數以 64（EX_USAGE）退出，而非 argparse 預設的 2——2 在本檔是 MISSING。"""

    def error(self, message: str) -> None:  # type: ignore[override]
        self.print_usage(sys.stderr)
        sys.stderr.write(f"{self.prog}: error: {message}\n")
        raise SystemExit(64)


# --------------------------------------------------------------------- 週期數學

def _fire_time(cadence: dict, day: date) -> datetime:
    return datetime(
        day.year, day.month, day.day,
        int(cadence["hour"]), int(cadence["minute"]), tzinfo=TAIPEI,
    )


def _launchd_weekday_to_iso(weekday: int) -> int:
    """launchd 的 Weekday：0 與 7 都是週日，1–6 是週一到週六。Python isoweekday 週日是 7。"""
    return 7 if int(weekday) == 0 else int(weekday)


def previous_fire(cadence: dict, moment: datetime) -> datetime | None:
    """最近一個 <= moment 的排程觸發時刻。"""
    kind = cadence.get("kind")
    moment = moment.astimezone(TAIPEI)
    if kind == "daily":
        candidate = _fire_time(cadence, moment.date())
        if candidate > moment:
            candidate = _fire_time(cadence, moment.date() - timedelta(days=1))
        return candidate
    if kind == "weekly":
        target = _launchd_weekday_to_iso(cadence["weekday"])
        for back in range(0, 8):
            day = moment.date() - timedelta(days=back)
            if day.isoweekday() != target:
                continue
            candidate = _fire_time(cadence, day)
            if candidate <= moment:
                return candidate
        return None
    raise ValueError(f"未知的 cadence kind：{kind!r}")


def step_back(cadence: dict, fire: datetime) -> datetime:
    delta = timedelta(days=1) if cadence.get("kind") == "daily" else timedelta(days=7)
    return fire - delta


def cycle_of(cadence: dict, moment: datetime) -> datetime | None:
    """一次執行歸屬到哪個週期＝起跑時刻之前（含）最近的那個觸發點。"""
    return previous_fire(cadence, moment)


# --------------------------------------------------------------------- 歷史讀取

def parse_timestamp(value: str) -> datetime:
    """吃 ISO 時戳，含 `+0800` 這種無冒號偏移（Python 3.9 的 fromisoformat 不收）。"""
    text = value.strip()
    if len(text) >= 5 and text[-5] in "+-" and text[-3] != ":":
        text = f"{text[:-2]}:{text[-2:]}"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=TAIPEI)
    return parsed


def load_history(path: Path) -> tuple[list[dict], int]:
    """回傳 (可解析的紀錄, 壞掉的列數)。壞列跳過但計數——不靜默。"""
    records: list[dict] = []
    corrupt = 0
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return records, 0
    except OSError:
        return records, 1
    for line in raw.splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
            parse_timestamp(record["started_at"])
            if record.get("state") not in ("running",) + TERMINAL_STATES:
                raise ValueError("unknown state")
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            corrupt += 1
            continue
        records.append(record)
    return records, corrupt


def written_at(record: dict) -> datetime:
    """一列**何時被寫下**（`observed_at`），不是它描述的執行何時起跑。

    兩者對終態列差很多：2026-08-10 那次 10:10 起跑、11:50:37 才寫入 `failed`。判定
    「當時看得到什麼」必須用後者，否則 `--now` 回放會拿到未來才存在的證據，把偵測器
    的能力誇大成它沒有的。順帶也擋掉時鐘偏移寫進來的未來紀錄。
    """
    stamp = record.get("observed_at") or record.get("finished_at") or record["started_at"]
    return parse_timestamp(stamp)


def index_by_cycle(cadence: dict, records: list[dict], trigger: str = "launchd",
                   now: datetime | None = None) -> dict:
    """cycle → 該週期在 `now` 當下的最後一列（append-only，故檔案順序即時間順序）。"""
    by_cycle: dict = {}
    for record in records:
        if record.get("trigger") != trigger:
            continue
        if now is not None and written_at(record) > now:
            continue
        cycle = cycle_of(cadence, parse_timestamp(record["started_at"]))
        if cycle is not None:
            by_cycle[cycle] = record
    return by_cycle


# --------------------------------------------------------------------- 逐週期判定

def verdict_for_cycle(record: dict | None) -> str:
    if record is None:
        return "MISSING"
    state = record.get("state")
    if state == "succeeded":
        return "OK"
    if state == "failed":
        return "FAILED"
    if state == "skipped":
        return "SKIPPED"
    return "INCOMPLETE"  # 停在 running 而後繼週期已觸發 ⇒ 那次執行死掉了


def _floor(job: dict) -> date | None:
    """只判 `f >= max(effective_from, history_from)` 的週期。任一為 null ⇒ 不判。"""
    effective = job.get("effective_from")
    history = job.get("history_from")
    if not effective or not history:
        return None
    return max(date.fromisoformat(effective), date.fromisoformat(history))


def evaluate_job(job: dict, now: datetime, repo: Path, lookback: int) -> dict:
    cadence = job["cadence"]
    history_file = repo / job["history_path"]
    records, corrupt = load_history(history_file)
    by_cycle = index_by_cycle(cadence, records, now=now)

    result: dict[str, Any] = {
        "label": job["label"],
        "cadence": cadence,
        "history_path": job["history_path"],
        "corrupt_lines": corrupt,
        "findings": [],
        "cycles": [],
        "streak": 0,
    }

    floor_day = _floor(job)
    f0 = previous_fire(cadence, now)
    if f0 is None or floor_day is None:
        result["note"] = "尚無可判定的週期（effective_from／history_from 未填或未到）"
        return result
    f1 = step_back(cadence, f0)

    def in_scope(fire: datetime) -> bool:
        return fire.date() >= floor_day

    judged: list[tuple[datetime, str]] = []
    if in_scope(f1):
        judged.append((f1, verdict_for_cycle(by_cycle.get(f1))))
    f0_record = by_cycle.get(f0)
    if in_scope(f0) and f0_record is not None and f0_record.get("state") in TERMINAL_STATES:
        judged.append((f0, verdict_for_cycle(f0_record)))

    result["cycles"] = [
        {"cycle": fire.isoformat(), "verdict": verdict, "role": "F0" if fire == f0 else "F1"}
        for fire, verdict in judged
    ]
    if corrupt:
        result["findings"].append({
            "verdict": "HISTORY_CORRUPT",
            "detail": f"{corrupt} 列無法解析：{job['history_path']}",
        })

    bad = [(fire, verdict) for fire, verdict in judged if verdict != "OK"]
    if not bad:
        return result

    # 連續計數：從最新的非 OK 週期往回走，直到遇到 OK 或走出 floor／lookback。
    newest_bad_fire = max(fire for fire, _ in bad)
    streak = 0
    cursor = newest_bad_fire
    for _ in range(lookback):
        if not in_scope(cursor):
            break
        if verdict_for_cycle(by_cycle.get(cursor)) == "OK":
            break
        streak += 1
        cursor = step_back(cadence, cursor)
    result["streak"] = streak

    for fire, verdict in bad:
        emitted = verdict
        if verdict == "SKIPPED":
            # 單次 lock 撞期是設計內的正常行為（週跑刻意讓路給每日鏈）。真正的病是
            # **永久跳過**——stale lock 留下即永遠 skip。以「連續」為判準才打中病灶。
            if streak < 2:
                continue
            emitted = "SKIPPED_CONSECUTIVE"
        record = by_cycle.get(fire) or {}
        result["findings"].append({
            "verdict": emitted,
            "cycle": fire.isoformat(),
            "streak": streak,
            "exit_code": record.get("exit_code"),
            "failed_phase": record.get("failed_phase"),
            "log": record.get("log"),
        })
    return result


# --------------------------------------------------------------------- 登記表校驗

def launchctl_installed(label: str) -> bool:
    """只看**存在性**，不讀 LastExitStatus／runs——那些計數器會被 reload／reboot 歸零。"""
    try:
        proc = subprocess.run(
            ["launchctl", "print", f"gui/{os.getuid()}/{label}"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return proc.returncode == 0


def launchctl_cpbl_labels() -> list[str]:
    try:
        proc = subprocess.run(
            ["launchctl", "list"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    labels = []
    for line in proc.stdout.splitlines()[1:]:
        parts = line.split("\t")
        if parts and parts[-1].startswith("com.cpbl."):
            labels.append(parts[-1].strip())
    return labels


def plist_cadence(plist_path: Path) -> dict | None:
    """回 None ⇒ 呼叫端判 REGISTRY_INVALID（fail closed）。

    ⚠️ 例外刻意抓得寬：plistlib 對格式不良的 plist 會拋 `xml.parsers.expat.ExpatError`，
    那不是 `plistlib.InvalidFileException` 的子類。實測 `plutil -lint` 對「XML 註解裡
    有連續兩個減號」是放行的，plistlib 才會拒收——本卡開發時自己的 watchdog plist 就
    踩到，lint 全綠而解析炸掉。校驗器不可以因為冒出沒列舉到的例外型別就整個掛掉。
    """
    try:
        with plist_path.open("rb") as handle:
            data = plistlib.load(handle)
    except Exception:  # noqa: BLE001 — 解析不了就是不可信，型別不重要
        return None
    interval = data.get("StartCalendarInterval")
    if not isinstance(interval, dict):
        return None
    if "Weekday" in interval:
        return {"kind": "weekly", "weekday": _launchd_weekday_to_iso(interval["Weekday"]),
                "hour": interval.get("Hour"), "minute": interval.get("Minute")}
    return {"kind": "daily", "hour": interval.get("Hour"), "minute": interval.get("Minute")}


def check_registry(registry: dict, repo: Path, today: date, installed_probe=None,
                   listing_probe=None) -> list[dict]:
    """Fail closed 一律歸「對登記表告警」，與 job 告警分開，且優先序最高。"""
    installed_probe = installed_probe or launchctl_installed
    listing_probe = listing_probe or launchctl_cpbl_labels
    findings: list[dict] = []
    jobs = registry.get("jobs")
    if not isinstance(jobs, list) or not jobs:
        return [{"verdict": "REGISTRY_INVALID", "detail": "登記表沒有 jobs 陣列"}]

    declared = set()
    for job in jobs:
        label = job.get("label", "<no label>")
        declared.add(label)
        missing = [field for field in REQUIRED_JOB_FIELDS if field not in job]
        if missing:
            findings.append({"verdict": "REGISTRY_INVALID",
                             "detail": f"{label} 缺必填欄位：{', '.join(missing)}"})
            continue
        plist_path = repo / job["plist"]
        if not plist_path.exists():
            findings.append({"verdict": "REGISTRY_INVALID",
                             "detail": f"{label} 指向的 plist 不存在：{job['plist']}"})
        else:
            actual = plist_cadence(plist_path)
            expected = dict(job["cadence"])
            if expected.get("kind") == "weekly":
                expected["weekday"] = _launchd_weekday_to_iso(expected["weekday"])
            if actual != expected:
                findings.append({
                    "verdict": "REGISTRY_INVALID",
                    "detail": f"{label} cadence 與 plist 不符：登記表 {expected}／plist {actual}",
                })
        history_from = job.get("history_from")
        if history_from and date.fromisoformat(history_from) > today:
            findings.append({"verdict": "REGISTRY_INVALID",
                             "detail": f"{label} 的 history_from={history_from} 在未來——"
                                       "歷史寫入器不可能從未來開始，八成是打錯或忘了更新"})
        is_installed = installed_probe(label)
        if job["expected_installed"] and not is_installed:
            findings.append({"verdict": "JOB_NOT_INSTALLED", "label": label,
                             "detail": f"{label} 宣告應安裝但 launchctl 找不到"})
        if not job["expected_installed"] and is_installed:
            findings.append({"verdict": "REGISTRY_CONFLICT", "label": label,
                             "detail": f"{label} 宣告不應安裝卻已安裝——"
                                       "先確認是刻意 cutover 還是誤裝，再更新登記表"})

    for plist_path in sorted((repo / "scripts").glob("com.cpbl.*.plist")):
        label = plist_path.name[: -len(".plist")]
        if label not in declared:
            findings.append({"verdict": "REGISTRY_INCOMPLETE",
                             "detail": f"磁碟上有 {plist_path.name} 而登記表沒有 {label}"})
    for label in listing_probe():
        if label not in declared:
            findings.append({"verdict": "REGISTRY_INCOMPLETE",
                             "detail": f"launchctl 有 {label} 而登記表沒有"})
    return findings


# ------------------------------------------------------------- 偵測器 B（生產側）

def probe_production(api_url: str, timeout: float) -> dict:
    """讀生產 `/api/info` 的停擺訊號。**這不是即時告警**——讀者是本偵測器，訊號會遲到
    到下次開機／下次排程執行（需求方 2026-08-15 裁定二，明確接受此代價）。"""
    if api_url in ("", "none"):
        return {"state": "disabled"}
    # ⚠️ **必須帶自訂 User-Agent。** 實測 2026-08-15：urllib 預設的 `Python-urllib/3.9`
    # 打 https://cpbl.ruan-ruan.com/api/info 被邊緣擋成 **403**，同一時刻 curl 回 200。
    # 沒有這一行，偵測器每天都會報 B_UNREACHABLE——一個永遠在叫的告警會被關掉，
    # 而那正是本卡在修的病。這個缺陷只有真的打一次生產才看得到，讀碼看不出來。
    request = urllib.request.Request(api_url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            body = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError, json.JSONDecodeError) as error:
        return {"state": "unreachable", "error": f"{type(error).__name__}: {error}"}
    metrics = body.get("metrics") or {}
    if "prod_sync_stalled" not in metrics:
        return {"state": "unavailable",
                "error": "/api/info 沒有 prod_sync_stalled 欄位（偵測器 B 尚未部署？）"}
    return {
        "state": "stalled" if metrics.get("prod_sync_stalled") else "ok",
        "last_at": metrics.get("prod_sync_last_at"),
        "age_hours": metrics.get("prod_sync_age_hours"),
        "stall_after_hours": metrics.get("prod_sync_stall_after_h"),
    }


# ------------------------------------------------- RunAtLoad 自證不變量（開機對帳）

def last_boot_times(limit: int = 20) -> list[datetime]:
    """`last reboot` 讀 wtmp（實測可回溯 5 個月；`pmset -g log` 只有 7 天，不可用）。"""
    try:
        proc = subprocess.run(["last", "reboot"], stdout=subprocess.PIPE,
                              stderr=subprocess.DEVNULL, text=True, check=False)
    except (OSError, subprocess.SubprocessError):
        return []
    boots: list[datetime] = []
    pattern = re.compile(r"^reboot\s+\S+\s+(\w{3})\s+(\w{3})\s+(\d+)\s+(\d{2}):(\d{2})")
    months = {m: i + 1 for i, m in enumerate(
        ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])}
    today = datetime.now(TAIPEI).date()
    for line in proc.stdout.splitlines():
        match = pattern.match(line)
        if not match:
            continue
        _, mon, day, hour, minute = match.groups()
        if mon not in months:
            continue
        year = today.year
        try:
            moment = datetime(year, months[mon], int(day), int(hour), int(minute), tzinfo=TAIPEI)
        except ValueError:
            continue
        if moment.date() > today:      # wtmp 不記年份；未來的日期一定是去年的
            moment = moment.replace(year=year - 1)
        boots.append(moment)
        if len(boots) >= limit:
            break
    return boots


def runatload_findings(repo: Path, watchdog_job: dict | None, now: datetime,
                       boot_probe=None) -> list[dict]:
    """**會自己舉手的可證偽預測**：`RunAtLoad` 若沒兌現，開機後就不會有本偵測器的紀錄。

    bootout/bootstrap 只證明「load 時會啟動」；一次真正的冷開機本卡沒有觀測到（實測
    本機已連續開機近 30 天，無自然實驗）。這個不變量把那個推導換成下次開機自動驗證。
    """
    if not watchdog_job or not watchdog_job.get("history_from"):
        return []
    floor_day = date.fromisoformat(watchdog_job["history_from"])
    records, _ = load_history(repo / watchdog_job["history_path"])
    runs = sorted(parse_timestamp(r["started_at"]) for r in records)
    findings = []
    for boot in (boot_probe or last_boot_times)():
        if boot.date() < floor_day or boot > now:
            continue
        deadline = boot + timedelta(minutes=RUNATLOAD_GRACE_MINUTES)
        if now < deadline:
            continue  # 開機不久，還在寬限期內
        if not any(boot <= run <= deadline for run in runs):
            findings.append({
                "verdict": "RUNATLOAD_NOT_HONORED",
                "detail": f"{boot.isoformat()} 開機後 {RUNATLOAD_GRACE_MINUTES} 分鐘內"
                          "沒有 watchdog 執行紀錄——RunAtLoad 未兌現",
            })
    return findings


# --------------------------------------------------------------------- 訊息組裝

_VERDICT_TEXT = {
    "FAILED": "失敗",
    "MISSING": "沒跑",
    "INCOMPLETE": "跑到一半死掉",
    "SKIPPED_CONSECUTIVE": "連續被跳過",
    "JOB_NOT_INSTALLED": "排程未安裝",
    "HISTORY_CORRUPT": "歷史檔毀損",
    "REGISTRY_INVALID": "登記表無效",
    "REGISTRY_INCOMPLETE": "登記表不完整",
    "REGISTRY_CONFLICT": "登記表與實況衝突",
    "RUNATLOAD_NOT_HONORED": "RunAtLoad 未兌現",
    "B_STALLED": "生產同步停擺",
    "B_UNREACHABLE": "取不到生產訊號",
    "B_UNAVAILABLE": "生產訊號欄位缺失",
}
_JOB_TEXT = {
    "com.cpbl.scrape-daily": "每日鏈",
    "com.cpbl.weekly-box-revisions": "週跑 box",
    "com.cpbl.weekly-game-pitches": "週跑逐球",
    "com.cpbl.schedule-watchdog": "排程偵測器",
}


def _streak_text(cadence: dict, streak: int) -> str:
    """裁定四：訊息**必須**含連續次數。第 1 天與第 5 天讀起來就該不一樣，否則重複
    通知會退化成噪音——而告警疲勞的解法是修掉失敗，不是消音。"""
    unit = "天" if cadence.get("kind") == "daily" else "週"
    return f"連續第 {streak} {unit}"


def build_message(report: dict) -> str:
    parts = []
    for job in report["jobs"]:
        cadence = job.get("cadence") or {}
        for finding in job["findings"]:
            name = _JOB_TEXT.get(job["label"], job["label"])
            text = _VERDICT_TEXT.get(finding["verdict"], finding["verdict"])
            if finding.get("streak"):
                parts.append(f"{name}{text}（{_streak_text(cadence, finding['streak'])}）")
            else:
                parts.append(f"{name}{text}")
    for finding in report["registry_findings"] + report["global_findings"]:
        parts.append(_VERDICT_TEXT.get(finding["verdict"], finding["verdict"])
                     + "：" + finding.get("detail", ""))
    return "；".join(parts) if parts else "排程一切正常"


# =============================================== 通知投遞：發了不等於送到
#
# R1 只做到「`osascript` 回 0」，並自承那不是證據。跨家族查核補上了缺的另一半——
# **確認沒有出現**：注入異常後立即檢查通知中心與桌面，都沒有可見通知。
#
# 以下是量出來的原因（每一條都有實測輸出，不是讀文件推斷）：
#
# 1. `osascript` 送出的通知歸屬 app 是 **Script Editor**，不是本專案的任何東西：
#      usernoted: Connection com.apple.ScriptEditor2 with path: /usr/bin/osascript
# 2. `usernoted` **接受了**它，還說要當 banner 顯示——這就是 rc=0 且日誌看起來成功的原因：
#      usernoted: … successfully processed by pipeline, scheduled for delivery.
#      usernoted: Presenting … as banner (["badge", "sound", "alert"])
# 3. 然後 `NotificationCenter` 去問 `donotdisturbd`，被**專注模式擋掉**：
#      donotdisturbd: Event was resolved: … outcome: suppressed; reason: mode configuration type
#      NotificationCenter: DA39-A3EE (com.apple.ScriptEditor2) muted by DND suppression: delay
#
# 那個模式的設定是 `applicationConfigurationType: Exclusive` 且
# `allowedApplicationIdentifiers: {}`（**空的**）——沒有任何 app 能突破——加上
# `minimumBreakthroughUrgency: essential`，而 AppleScript 的 `display notification`
# **沒有辦法標記 urgency**（那需要 Time Sensitive／Critical Alerts 授權的真 app bundle）。
# 所以這不是本 repo 改得動的東西：修法是使用者在系統設定裡改專注模式白名單。
#
# 24 小時實測分佈（`log show --last 24h --predicate 'process == "donotdisturbd"'`）：
#   suppressed 103 次、allowed 11 次；11 次 allowed **全部**落在 23:45–05:19（睡覺時段），
#   白天清醒時段（含 21:21、21:37，正是本 watchdog 21:10 的槽）**無一例外全部 suppressed**。
#
# 結論：在這台機器的現行設定下，推播通知**結構上沒有讀者**。既然如此，偵測器至少
# 必須**知道自己被靜音了**並說出來——否則它只是換一種形式的「沒有讀者的告警」，
# 也就是本卡一開始要消滅的東西。

NOTIFY_BUNDLE_ID = "com.apple.ScriptEditor2"   # osascript 的歸屬 app（實測，見上）

# 投遞判定。`delivered` 只有三種值，且**永遠不會因為測不到就寫 True**（fail closed）。
DELIVERY_PRESENTED = "presented"          # 系統紀錄顯示真的呈現了
DELIVERY_SUPPRESSED = "suppressed"        # 專注模式／勿擾擋掉——有寫入，但沒有人看到
DELIVERY_UNVERIFIED = "unverified"        # 查不到系統紀錄：**不代表送到了**


def _delivery_probe(since: datetime, timeout: float = 20.0) -> dict:
    """問 macOS 統一日誌：剛剛那則通知到底有沒有被呈現。

    ⚠️ 這裡刻意**不**用 `osascript` 的退出碼當任何依據——它在被靜音時一樣回 0。
    唯一採信的是 `donotdisturbd`／`NotificationCenter` 的解析結果。

    ⚠️ `log` 在 zsh 是**內建指令**（實測：`type log` → `log is a shell builtin`），
    直接寫 `log show` 會被 shell 吃掉並回「too many arguments」而看起來像沒有紀錄。
    本卡 R1 的探查就是這樣得到假陰性的，故此處硬寫絕對路徑 `/usr/bin/log`。
    """
    verdict = {"delivered": DELIVERY_UNVERIFIED, "reason": "", "evidence": ""}
    started = since.strftime("%Y-%m-%d %H:%M:%S")
    try:
        proc = subprocess.run(
            ["/usr/bin/log", "show", "--start", started, "--style", "compact",
             "--predicate",
             'process == "donotdisturbd" OR process == "NotificationCenter"'],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            timeout=timeout, check=False)
    except (OSError, subprocess.SubprocessError):
        verdict["reason"] = "無法執行 /usr/bin/log，投遞與否不可知"
        return verdict
    if proc.returncode != 0:
        verdict["reason"] = f"/usr/bin/log 非零退出（{proc.returncode}），投遞與否不可知"
        return verdict

    text = proc.stdout.decode("utf-8", errors="replace")
    ours = [ln for ln in text.splitlines() if NOTIFY_BUNDLE_ID in ln]
    muted = [ln for ln in ours if "muted by DND suppression" in ln]
    if muted:
        verdict["delivered"] = DELIVERY_SUPPRESSED
        verdict["reason"] = "專注模式／勿擾擋下：系統有收到，但畫面上沒有出現"
        verdict["evidence"] = muted[0].strip()[:400]
        return verdict
    presented = [ln for ln in ours if "Presenting" in ln]
    if presented:
        # ⚠️ `usernoted` 的 "Presenting" 發生在**問 DND 之前**，所以它單獨不算數；
        # 只有在同時找不到 muted 行時才採信。上面的順序就是這個意思。
        verdict["delivered"] = DELIVERY_PRESENTED
        verdict["reason"] = "系統紀錄顯示已呈現，且未見專注模式攔截"
        verdict["evidence"] = presented[0].strip()[:400]
        return verdict
    verdict["reason"] = "統一日誌裡找不到這則通知的處理紀錄，投遞與否不可知"
    return verdict


def notify(title: str, message: str, *, verify: bool = True) -> dict:
    """彈通知**並回報它到底有沒有被看到**。回傳投遞判定 dict。

    ⚠️ `osascript` 回 0 **不是**通知彈出的證據——被專注模式靜音時它一樣回 0。
    因此呼叫端另有兩個不依賴權限的備援：持久產物 `logs/schedule-alert.json`
    ＋ 非零退出碼（讓 `launchctl print` 那一面也留下痕跡）。
    """
    verdict: dict = {"attempted": True, "osascript_rc": None,
                     "delivered": DELIVERY_UNVERIFIED, "reason": "", "evidence": ""}
    script = (f'display notification {json.dumps(message, ensure_ascii=False)} '
              f'with title {json.dumps(title, ensure_ascii=False)}')
    # 取送出前一秒當查詢起點：`log show --start` 的解析度是秒，取「現在」會漏掉同秒事件。
    since = datetime.now() - timedelta(seconds=1)
    try:
        proc = subprocess.run(["osascript", "-e", script], stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL, timeout=20, check=False)
    except (OSError, subprocess.SubprocessError) as error:
        verdict["reason"] = f"osascript 無法執行：{error}"
        return verdict
    verdict["osascript_rc"] = proc.returncode
    if proc.returncode != 0:
        verdict["reason"] = f"osascript 非零退出（{proc.returncode}）"
        return verdict
    if verify:
        verdict.update(_delivery_probe(since))
    return verdict


# --------------------------------------------------------------------- 主流程

def evaluate(registry: dict, repo: Path, now: datetime, api_url: str, api_timeout: float,
             lookback: int, installed_probe=None, listing_probe=None,
             boot_probe=None) -> dict:
    registry_findings = check_registry(registry, repo, now.date(),
                                       installed_probe=installed_probe,
                                       listing_probe=listing_probe)
    blocking = [f for f in registry_findings if f["verdict"].startswith("REGISTRY_")]
    report: dict[str, Any] = {
        "now": now.isoformat(),
        "registry_findings": registry_findings,
        "global_findings": [],
        "jobs": [],
        "production": {},
        "registry_blocked": bool(blocking),
    }
    if blocking:
        # 登記表不可信時其餘判定一律不宣稱（fail closed，方向是對登記表告警）。
        report["verdict"] = max((f["verdict"] for f in blocking), key=lambda v: SEVERITY[v])
        report["exit_code"] = EXIT_REGISTRY
        report["message"] = build_message(report)
        return report

    watchdog_job = None
    for job in registry["jobs"]:
        if job["label"] == "com.cpbl.schedule-watchdog":
            watchdog_job = job
        if not job["expected_installed"]:
            continue  # 刻意不安裝的 job 不判缺席（#115 死於把刻意邊界報成故障）
        report["jobs"].append(evaluate_job(job, now, repo, lookback))

    report["global_findings"].extend(
        runatload_findings(repo, watchdog_job, now, boot_probe=boot_probe))

    production = probe_production(api_url, api_timeout)
    report["production"] = production
    if production["state"] == "unreachable":
        report["global_findings"].append({"verdict": "B_UNREACHABLE",
                                          "detail": production.get("error", "")})
    elif production["state"] == "unavailable":
        report["global_findings"].append({"verdict": "B_UNAVAILABLE",
                                          "detail": production.get("error", "")})
    elif production["state"] == "stalled":
        report["global_findings"].append({
            "verdict": "B_STALLED",
            "detail": f"生產最後一次 prod-sync 是 {production.get('last_at')}"
                      f"（{production.get('age_hours')}h 前，門檻 "
                      f"{production.get('stall_after_hours')}h）",
        })

    all_verdicts = [f["verdict"] for f in registry_findings]
    all_verdicts += [f["verdict"] for f in report["global_findings"]]
    for job in report["jobs"]:
        all_verdicts += [f["verdict"] for f in job["findings"]]
    if all_verdicts:
        worst = max(all_verdicts, key=lambda v: SEVERITY.get(v, 0))
        report["verdict"] = worst
        report["exit_code"] = EXIT_BY_VERDICT.get(worst, EXIT_REGISTRY)
    else:
        report["verdict"] = "OK"
        report["exit_code"] = EXIT_OK
    report["message"] = build_message(report)
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = _Parser(
        prog="schedule_watch.py",
        description="排程缺席／失敗偵測器：回頭看上一個應該完成的週期，而不是看現在。",
        epilog=(
            "在做什麼：依 scripts/schedule-registry.json 宣告的節奏，判定每個 launchd job 的"
            "『上一個已封閉週期』（以及已是終態的當前週期）跑了沒、跑成怎樣；"
            "另讀生產 /api/info 的停擺訊號。\n"
            "會寫什麼：--notify 時才寫 logs/schedule-alert.json、logs/schedule-watchdog/"
            "last-run.json 與 logs/schedule-history/com.cpbl.schedule-watchdog.jsonl；"
            "否則只印 JSON 到 stdout。不碰 refresh lock、不連 DB、不觸發任何爬蟲。\n"
            "怎麼呼叫：scripts/schedule_watch.py（唯讀查詢）／"
            "scripts/schedule-watchdog.sh（launchd 用，會通知）／"
            "--now 2026-08-10T21:10:00+08:00 --api-url none（決定性回放）"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    here = Path(__file__).resolve().parent
    parser.add_argument("--registry", type=Path, default=here / "schedule-registry.json")
    parser.add_argument("--repo", type=Path, default=here.parent,
                        help="logs/ 的所在（預設＝本腳本的上層目錄）")
    parser.add_argument("--now", help="ISO 時戳覆寫，讓週期數學可決定性測試")
    parser.add_argument("--api-url", default=DEFAULT_API_URL,
                        help="偵測器 B 的來源；`none` 停用")
    parser.add_argument("--api-timeout", type=float, default=8.0)
    parser.add_argument("--lookback-cycles", type=int, default=DEFAULT_LOOKBACK_CYCLES)
    parser.add_argument("--notify", action="store_true",
                        help="有 finding 時彈 osascript 通知並留下持久產物")
    parser.add_argument("--quiet", action="store_true", help="不印 JSON 報告")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    now = parse_timestamp(args.now) if args.now else datetime.now(TAIPEI)
    try:
        registry = json.loads(args.registry.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        report = {"now": now.isoformat(), "verdict": "REGISTRY_INVALID",
                  "exit_code": EXIT_REGISTRY, "registry_findings": [
                      {"verdict": "REGISTRY_INVALID", "detail": f"讀不到登記表：{error}"}],
                  "global_findings": [], "jobs": [], "production": {}}
        report["message"] = build_message(report)
    else:
        report = evaluate(registry, args.repo, now, args.api_url, args.api_timeout,
                          args.lookback_cycles)

    if not args.quiet:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    if args.notify:
        write_notify_artifacts(args.repo, report)
    return int(report["exit_code"])


def current_trigger() -> str:
    """執行身分：由 wrapper 在 bash 層以 `$PPID == 1` 判定後經環境變數傳進來。

    不確定時一律回 `manual`（fail closed）。方向是刻意的：把手動跑誤記成排程跑會讓
    手動救火把壞掉的排程蓋成健康（fail open，靜默）；反過來只會多報一次缺席（吵，
    但看得見）。
    """
    return "launchd" if os.environ.get(TRIGGER_ENV) == "launchd" else "manual"


# 誰會看到、什麼時候看到——卡面驗收條件 2 要求指名，而**這一段就是那個指名**。
#
# ⚠️ 誠實標定：這是**目標 3（留下可稽核的痕跡）**，不是目標 2（主動送到人面前）。
# 推播那條路在這台機器上量到是死的（見 notify() 上方的專注模式實測），而修法在系統
# 設定裡、不在本 repo，故本卡不宣稱達成目標 2。
READER_CONTRACT = {
    "goal": 3,
    "goal_note": "目標 3（可稽核痕跡）。**不是**目標 2：它仍然要等人來跑 pytest，"
                 "不會主動送到人面前。推播那條路在本機實測是死的——專注模式把 "
                 "osascript 通知全部 suppressed，詳見本檔 notify() 區段的量測。",
    "who": "任何要動這個 repo 的人或 AI——不需要指派，也不需要誰記得",
    "when": "每次跑 `uv run pytest`。CLAUDE.md 明訂 push 前必跑，而 "
            "tests/conftest.py 的 pytest_report_header 會把本告警印在最前面（`-q` 也印）",
    "how": "logs/schedule-alert.json 存在＝有未處理的排程異常；條件解除時本檔自動刪除，"
           "故『檔案在』本身就是訊號。pytest header 會把訊息與『推播有沒有送達』一起印出來",
    "push_channel": "無。本專案的告警模型是機器可讀狀態檔供人／AI 每日查，"
                    "不另設推播管道（見 scripts/backup-prod-db.sh 檔頭）。"
                    "要改成真的會叫人的推播，屬需求方裁量，不由執行者自行引入。",
}


def write_notify_artifacts(repo: Path, report: dict) -> None:
    """三層備援：通知（在本機被專注模式靜音）→ 持久產物 → 非零退出碼。

    ⚠️ 通知**先送再寫檔**，因為投遞判定要一起寫進產物；osascript 與日誌查詢都有
    timeout，故不會因為通知那一層卡住而讓產物寫不出來。
    """
    stamp = datetime.now(TAIPEI).strftime("%Y-%m-%dT%H:%M:%S%z")
    trigger = current_trigger()
    delivery: dict = {"attempted": False,
                      "delivered": DELIVERY_UNVERIFIED,
                      "reason": "本次無異常，未送出通知"}
    if report["exit_code"] != EXIT_OK:
        delivery = notify("CPBL 排程異常", report["message"])
    run_dir = repo / "logs" / "schedule-watchdog"
    try:
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "last-run.json").write_text(
            json.dumps({"observed_at": stamp, "verdict": report["verdict"],
                        "exit_code": report["exit_code"], "message": report["message"],
                        "trigger": trigger, "ppid": os.getppid(),
                        # 留存但**不當判準**（見 TRIGGER_ENV 的註解：子行程一律看到 "0"）
                        "xpc_service_name": os.environ.get("XPC_SERVICE_NAME"),
                        "notification": delivery, "reader": READER_CONTRACT,
                        "report": report}, ensure_ascii=False, indent=2),
            encoding="utf-8")
        history = repo / "logs" / "schedule-history" / "com.cpbl.schedule-watchdog.jsonl"
        history.parent.mkdir(parents=True, exist_ok=True)
        with history.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({
                "schema_version": 1, "label": "com.cpbl.schedule-watchdog",
                "state": "succeeded", "exit_code": report["exit_code"], "trigger": trigger,
                "started_at": stamp, "finished_at": stamp, "observed_at": stamp,
                "failed_phase": None, "log": None, "note": report["verdict"],
            }, ensure_ascii=False, sort_keys=True) + "\n")
        alert = repo / "logs" / "schedule-alert.json"
        if report["exit_code"] == EXIT_OK:
            if alert.exists():
                alert.unlink()
        else:
            alert.write_text(json.dumps(
                {"observed_at": stamp, "verdict": report["verdict"],
                 "message": report["message"],
                 # ⚠️ 這兩個欄位是本檔的重點：讀到這份 alert 的人必須立刻知道
                 # 「有沒有人被通知到」，而不是預設『既然有告警就有人看到了』。
                 "notification": delivery, "reader": READER_CONTRACT,
                 "report": report},
                ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as error:
        print(f"WARN 無法寫入 watchdog 產物：{error}", file=sys.stderr)
    if delivery.get("attempted") and delivery.get("delivered") != DELIVERY_PRESENTED:
        # 靜音本身要在 stderr 留痕：launchd 會把它收進
        # logs/launchd-schedule-watchdog.err.log，那是第三個不依賴權限的面。
        print(f"WARN 通知未確認送達（{delivery.get('delivered')}）："
              f"{delivery.get('reason')}　→ 讀者請改看 logs/schedule-alert.json",
              file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
