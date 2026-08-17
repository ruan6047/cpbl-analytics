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


ANCHOR_PATH = Path("logs") / "schedule-watchdog" / "deployed-at.json"


def deployment_anchor(repo: Path, now: datetime) -> date | None:
    """本機**實際**部署日：第一次執行時自己寫下，之後永不覆寫。

    ⚠️ 這一支存在的理由是登記表的 `history_from` 只能是**授權時的猜測**。R1 把它填成
    交付日 2026-08-15，但部署是 merge 之後才發生的另一件事——中間差幾天，那幾天的週期
    就會被判成一片 MISSING（方向是誤報，而誤報的下場是偵測器被關掉，#115 正是死於此）。
    登記表註解原本要求「部署者記得改成實際安裝日」，那是**靠人記得**——本卡的整個立論
    就是靠人記得不算數，對自己的部署程序當然也一樣。

    改法：把宣告換成量測。第一次跑就把當下寫進 `logs/schedule-watchdog/deployed-at.json`
    （`logs/` 不進版控，故它天然是「這台機器的」事實），判定下界取
    `max(effective_from, history_from, anchor)`。

    Fail-safe：
    · 檔案不存在（首次執行，或有人清了 logs/）⇒ **當場建立**，於是最多只跳過當前這一個
      週期，不會有誤報洪水；代價是那一個週期不判，方向是漏報，比誤報安全。
    · 建立後永不覆寫 ⇒ 錨點不會隨時間往前漂，昨天判得到的今天一樣判得到。
    · 寫不進去（唯讀 logs/）⇒ 回 None，呼叫端據此不判——fail closed，不硬猜。
    """
    path = repo / ANCHOR_PATH
    try:
        if path.exists():
            payload = json.loads(path.read_text(encoding="utf-8"))
            return date.fromisoformat(payload["anchor_date"])
    except (OSError, ValueError, KeyError, TypeError):
        # 錨點檔壞掉：不當作「沒有錨點」（那會讓判定面突然放寬），改為重建成**現在**。
        # 方向同樣是漏報優先。
        pass
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "anchor_date": now.date().isoformat(),
            "anchor_at": now.isoformat(),
            "why": "本機第一次執行 schedule_watch.py 的時刻＝這套機制實際生效日。"
                   "判定下界取 max(effective_from, history_from, 本錨點)，"
                   "使部署前的空窗不會被報成 MISSING。本檔寫一次後永不覆寫。",
        }, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as error:
        print(f"WARN 無法建立部署錨點（{error}）：本輪不判定任何週期", file=sys.stderr)
        return None
    return now.date()


def _floor(job: dict, anchor: date | None = None) -> date | None:
    """只判 `f >= max(effective_from, history_from, anchor)` 的週期。任一為 null ⇒ 不判。"""
    effective = job.get("effective_from")
    history = job.get("history_from")
    if not effective or not history or anchor is None:
        return None
    return max(date.fromisoformat(effective), date.fromisoformat(history), anchor)


def evaluate_job(job: dict, now: datetime, repo: Path, lookback: int,
                 anchor: date | None = None) -> dict:
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

    floor_day = _floor(job, anchor)
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
                       boot_probe=None, anchor: date | None = None) -> list[dict]:
    """**會自己舉手的可證偽預測**：`RunAtLoad` 若沒兌現，開機後就不會有本偵測器的紀錄。

    bootout/bootstrap 只證明「load 時會啟動」；一次真正的冷開機本卡沒有觀測到（實測
    本機已連續開機近 30 天，無自然實驗）。這個不變量把那個變成下次開機自動驗證。

    ⚠️ 下界必須與 `_floor()` 用同一組界線，含**部署錨點**：偵測器裝上之前的每一次開機
    當然都沒有它的紀錄，拿宣告日當下界會把那些開機全部報成「RunAtLoad 未兌現」。
    這與 `history_from` 那個病灶是同一個，只是換一個出口——修一個不修另一個等於沒修。
    """
    if not watchdog_job or not watchdog_job.get("history_from") or anchor is None:
        return []
    floor_day = max(date.fromisoformat(watchdog_job["history_from"]), anchor)
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
# **沒有辦法標記 urgency**。所以那不是本 repo 改得動的東西：修法在系統設定裡。
#
# ⚠️ **以上是 2026-08-15 的狀態，已經不是現況。** 2026-08-16 需求方裁定「調整專注模式」
# 並當場關閉——那個模式是**非刻意**開啟的（需求方原話：「這個是我沒設定到」）。同日
# 11:58:18 實測本函式回傳 `presented`，證據是**關聯到本次通知**的裁決行：
#   osascript pid=70631 → usernoted `daemon_client.peer[70631]` → uuid `D1DCEC63`
#   → `NotificationCenter … Resolved interruption suppression for DA39-A3EE as none`
# （跨距 11:58:18.485–.505，20 毫秒）。
#
# ⚠️ **本卡先前所有的彙總數字全部撤回，勿再引用任何一個：**
#   · R2 的「suppressed 103／allowed 11」——數的是 `donotdisturbd` 的**預載解析**
#     （client 全是 `com.apple.nc.donotdisturb.user-toggles.preload`），不是通知投遞。
#   · R3 的「44/12、1960/56」——對象修對了，但視窗寫成**「最近 48 小時」這種相對量**，
#     換個時刻重跑就是別的數字（跨家族查核固定視窗重算得 37/12、1982/49）。
#     一句在不同時刻有不同真值的宣稱，沒有辦法被任何人對帳。
#
# 取而代之：彙總數字一律由
# `docs/research/OPS-SCHEDULE-FAILURE-BLIND1/measure_notification_delivery.py` 產生，
# 它**只吃絕對時間戳**、把 `log show` 指令原樣印出來、且對同一視窗重跑逐位相同。
# 引用時必須連同視窗一起寫（「於 X–Y 量得」），不得寫成無時間限定的宣稱——`log show`
# 讀的是會回收的環形緩衝，那種宣稱本質上不可能永遠為真。
#
# 教訓（本卡第四次踩到同一個形狀）：**先確認你數的是不是你以為的那個東西，
# 而且確認別人重跑會得到同一個數字。**
#   R1：數到「查不到」其實是 zsh 內建 `log` 吃掉了查詢
#   R2：數到「103/11」其實數的是預載解析；predicate 又濾掉自己要找的那一行
#   R3：對象修對了但邊界沒釘住，於是同一句宣稱有兩個值
#   R3：把「同 bundle ＋ 時間相近」當成關聯，於是無關事件會被歸給本次通知
# 前三次是「量測面與待答問題不對齊」，第四次是「量測沒有可重建的邊界與歸屬」。
#
# 現在的設計不再賭任何一種環境狀態，也不再依賴任何彙總統計：**每次執行都用本次通知
# 自己的 uuid 重新量一次投遞結果**（見 `_correlate`），並依量測回報該次達到的目標層級
# （見 READER_CONTRACT）。推播若再被擋下，下一次執行就會自己說出來。

NOTIFY_BUNDLE_ID = "com.apple.ScriptEditor2"   # osascript 的歸屬 app（實測，見上）

# ============================== 量的是「管道能力」，不是「這一則送達了」
#
# ⚠️ **這個區分是本檔的紅線，因為本卡已經在同一個地方栽過一次**：R1 把 `osascript rc=0`
# 講成「送達了」。以下欄位**永遠不宣稱某一則通知被看到**——它回答的是一個全域問題：
#
#     「以現在的系統狀態，這個 app 的通知**有沒有能力**出現在畫面上？」
#
# 為什麼改問這一題（需求方 2026-08-17 裁定）：2026-08-15 真正發生的事是**一個非刻意
# 開啟的專注模式擋掉了全部通知、而且無人察覺**。那是管道層級的故障，全域狀態直接回答
# 它，且**不需要把日誌行歸屬到某一則通知**——而那個歸屬已被證明在此平台上做不到
# （見下方「已知限制」）。
#
# 為什麼這樣問是嚴謹的：對**固定 app、固定 urgency**（osascript 無法設定 urgency）而言，
# 系統的裁決是全域模式狀態的函數。實測 2026-08-16 09:00–10:00（模式啟用中）該小時的
# 222 筆裁決，**逐 app 的 outcome 完全一致**：
#     com.apple.ScriptEditor2        → suppressed（無例外）
#     com.anthropic.claudefordesktop → suppressed（無例外）
#     com.apple.MobileSMS / Passbook / openai.codex / MacVirt → 同上
# 所以「本 app 的裁決」是良定義的，不必知道是哪一則通知觸發的。
PUSH_CHANNEL_OPEN = "open"        # 全域狀態下，本 app 的通知不會被抑制
PUSH_CHANNEL_BLOCKED = "blocked"  # 全域狀態下，本 app 的通知**會**被抑制
PUSH_CHANNEL_UNKNOWN = "unknown"  # 讀不到，或視窗內裁決不一致（模式中途改變）

# 只查 donotdisturbd：裁決與全域模式狀態都在它這裡。
# ⚠️ R4／R5 曾把 donotdisturbd 整個排除，理由寫成「它構造上沒有識別碼、無法關聯」。
# **那個理由太強、已更正**：它的 eventDetails 帶 `bundleIdentifier`，而本檔要的正是
# 「這個 app 會怎樣」而不是「這一則會怎樣」——後者才需要識別碼。排除它是當時設計的
# 副作用，不是它真的沒東西可用。
_DND_PREDICATE = 'process == "donotdisturbd"'
_RESOLVED_MARK = "Event was resolved"
_BUNDLE_RE = re.compile(r"bundleIdentifier: ([A-Za-z0-9._-]+)")
_OUTCOME_RE = re.compile(r"outcome: (\w+)")
_DND_REASON_RE = re.compile(r"reason: ([a-z ]+);")
_ACTIVE_MODE_RE = re.compile(r"activeModeUUID: \(?([0-9A-Fa-f-]+|null)\)?")
_SUPPRESSION_TYPE_RE = re.compile(r"interruptionSuppression: ([a-z ]+?);")
_LINE_TS_RE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+)")

# ============================== 已知限制：某一則通知**無法**被歸屬到它自己的裁決
#
# 這是窮盡查證後的結論（2026-08-16 全部實測），保留在此以免日後有人再試一次：
#   `uuid`／`activityIdentifier`／`parentActivityIdentifier`／`creatorActivityID` 在
#   NotificationCenter 的裁決行上全部缺席或為 0；`traceID` 兩則不同通知量到同值（是
#   callsite id）；`ident` 對 osascript 恆為 `DA39-A3EE`。`log show` 與 `log stream`、
#   `--info --debug`、`--style ndjson` 都試過。
#
# ⚠️ 但「完全沒有識別碼」是**錯的**，已更正：`donotdisturbd` 的 eventDetails 帶
# `title:`／`body:` 的**內容衍生雜湊**（實測：同內容同雜湊、異內容異雜湊各一次），
# 故若日後真的需要 per-notification 歸屬，可用唯一內容取得。需求方 2026-08-17 裁定
# **先不做**：全域狀態已足以回答「管道死了沒」，且不必假設雜湊穩定。


def _ts(line: str):
    m = _LINE_TS_RE.match(line)
    return datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S.%f") if m else None


def probe_push_channel(since: datetime, timeout: float = 20.0,
                       bundle_id: str = None) -> dict:
    """讀全域專注模式狀態，判定本 app 的推播管道**有沒有能力**送達。

    ⚠️ 回傳的 `state` **不是**投遞結果。`open` 只代表「此刻沒有東西擋著這個 app」，
    不代表剛才那一則有人看到——後者在此平台上量不到（見上方「已知限制」）。

    ⚠️ `log` 在 zsh 是**內建指令**（`type log` → `log is a shell builtin`），裸寫
    `log show` 會被 shell 吃掉並回「too many arguments」而看起來像沒有紀錄。R1 的假陰性
    就是這樣來的，故硬寫絕對路徑。
    """
    app = bundle_id or NOTIFY_BUNDLE_ID
    verdict = {"state": PUSH_CHANNEL_UNKNOWN, "reason": "", "evidence": "",
               "active_mode": None, "measures": "管道能力，不是本則通知的投遞結果"}
    try:
        proc = subprocess.run(
            ["/usr/bin/log", "show", "--start", since.strftime("%Y-%m-%d %H:%M:%S"),
             "--style", "compact", "--predicate", _DND_PREDICATE],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            timeout=timeout, check=False)
    except (OSError, subprocess.SubprocessError):
        verdict["reason"] = "無法執行 /usr/bin/log，全域專注模式狀態不可知"
        return verdict
    if proc.returncode != 0:
        verdict["reason"] = (f"/usr/bin/log 非零退出（{proc.returncode}），"
                             "全域專注模式狀態不可知")
        return verdict

    ours = [ln for ln in proc.stdout.decode("utf-8", errors="replace").splitlines()
            if _RESOLVED_MARK in ln and app in (_BUNDLE_RE.findall(ln) or [])]
    if not ours:
        verdict["reason"] = (f"視窗內沒有 {app} 的裁決紀錄——**不推論**管道是通的，"
                             "只代表這次沒量到")
        return verdict

    outcomes = {m.group(1) for ln in ours if (m := _OUTCOME_RE.search(ln))}
    if len(outcomes) != 1:
        # 模式在視窗中途被改動 ⇒ 沒有單一的「當時狀態」可講 ⇒ 不猜
        verdict["reason"] = (f"視窗內同一個 app 出現不一致的裁決（{sorted(outcomes)}），"
                             "表示專注模式中途改變——不取其一，判為不可知")
        return verdict

    line = ours[0]
    modes = {m.group(1) for ln in ours if (m := _ACTIVE_MODE_RE.search(ln))}
    verdict["active_mode"] = sorted(modes)[0] if len(modes) == 1 else sorted(modes) or None
    reason = (m.group(1).strip() if (m := _DND_REASON_RE.search(line)) else "")
    verdict["evidence"] = line.strip()[:400]
    if outcomes == {"allowed"}:
        verdict["state"] = PUSH_CHANNEL_OPEN
        verdict["reason"] = (f"系統對 {app} 的裁決是 allowed（reason: {reason}）："
                             "此刻沒有專注模式擋著這個 app 的通知")
    else:
        kind = (m.group(1).strip() if (m := _SUPPRESSION_TYPE_RE.search(line)) else "")
        verdict["suppression_type"] = kind
        verdict["state"] = PUSH_CHANNEL_BLOCKED
        # ⚠️ 措辭不得寫成「確定沒出現」。實測 macOS 的抑制型態是 `delay delivery`——
        # 它**延後**而不是丟棄：2026-08-16 10:12:40 使用者關閉專注模式的同一秒，
        # 14 則 ScriptEditor2 通知被 `Re-add … visibility: [history, alert, lockscreen,
        # allowsScreenWake]`，也就是**最終出現了**（延後約 20 小時）。
        verdict["reason"] = (
            f"系統對 {app} 的裁決是 {sorted(outcomes)[0]}"
            f"（reason: {reason}，型態 {kind or '不明'}，模式 {verdict['active_mode']}）："
            "推播**現在送不到**。⚠️ `delay delivery` 是延後不是丟棄——它會在使用者關閉"
            "專注模式時補送，延後多久取決於對方何時關，**不可預測也不保證在有用的時間內**")
    return verdict


def notify(title: str, message: str, *, verify: bool = True) -> dict:
    """彈通知，並量一次**推播管道有沒有能力送達**。

    ⚠️ `osascript` 回 0 **不是**通知彈出的證據——被專注模式靜音時它一樣回 0。
    ⚠️ 而 `push_channel.state == "open"` 也**不是**送達的證據，它只是管道沒被擋。
    真正不依賴任何使用者設定的讀者是 `logs/schedule-alert.json` ＋ pytest header。
    """
    # ⚠️ `command_failed` 是**獨立於管道狀態**的一面：通知指令自己就沒跑成功。
    # R6 移除關聯機制時把這個守衛一起刪掉了，於是 osascript 非零退出只剩 JSON 裡一個
    # 數字、讀者摘要完全不提——那正是本卡最原始痛點的反面（rc≠0 卻沒有人看到）。
    verdict: dict = {"attempted": True, "osascript_rc": None, "push_channel": None,
                     "command_failed": False, "command_error": ""}
    script = (f'display notification {json.dumps(message, ensure_ascii=False)} '
              f'with title {json.dumps(title, ensure_ascii=False)}')
    # 取送出前一秒當查詢起點：`log show --start` 的解析度是秒，取「現在」會漏掉同秒事件。
    since = datetime.now() - timedelta(seconds=1)
    try:
        proc = subprocess.run(["osascript", "-e", script], stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL, timeout=20, check=False)
    except (OSError, subprocess.SubprocessError) as error:
        verdict["command_failed"] = True
        verdict["command_error"] = f"osascript 無法執行：{error}"
        verdict["push_channel"] = {"state": PUSH_CHANNEL_UNKNOWN,
                                   "reason": f"osascript 無法執行：{error}",
                                   "evidence": "", "active_mode": None,
                                   "measures": "管道能力，不是本則通知的投遞結果"}
        return verdict
    verdict["osascript_rc"] = proc.returncode
    if proc.returncode != 0:
        # 指令本身失敗 ⇒ 根本沒有送出，管道狀態再好也沒有意義。
        verdict["command_failed"] = True
        verdict["command_error"] = f"osascript 非零退出（{proc.returncode}）：通知沒有送出"
        verdict["push_channel"] = {"state": PUSH_CHANNEL_UNKNOWN,
                                   "reason": verdict["command_error"],
                                   "evidence": "", "active_mode": None,
                                   "measures": "管道能力，不是本則通知的投遞結果"}
        return verdict
    if verify:
        verdict["push_channel"] = probe_push_channel(since)
    else:
        verdict["push_channel"] = {"state": PUSH_CHANNEL_UNKNOWN, "reason": "未查證",
                                   "evidence": "", "active_mode": None,
                                   "measures": "管道能力，不是本則通知的投遞結果"}
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

    # 部署錨點只算一次，且要在任何判定之前——它是所有 job 的共同下界。
    anchor = deployment_anchor(repo, now)
    report["deployment_anchor"] = anchor.isoformat() if anchor else None

    watchdog_job = None
    for job in registry["jobs"]:
        if job["label"] == "com.cpbl.schedule-watchdog":
            watchdog_job = job
        if not job["expected_installed"]:
            continue  # 刻意不安裝的 job 不判缺席（#115 死於把刻意邊界報成故障）
        report["jobs"].append(evaluate_job(job, now, repo, lookback, anchor))

    report["global_findings"].extend(
        runatload_findings(repo, watchdog_job, now, boot_probe=boot_probe, anchor=anchor))

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
# ⚠️ 目標層級**不是常數，是每次執行量出來的**——這是本輪最重要的設計決定。
#
# 2026-08-16 需求方裁定「調整專注模式」並當場關閉（原話：「這個是我沒設定到」——它是
# **非刻意**設定）。於是推播復活：同日 10:14 實測 `usernoted: Presenting` ＋
# `donotdisturbd: outcome: allowed; reason: disabled`，需求方並口述「有看到」。
#
# 那要不要因此宣告達成目標 2？**floor 維持 3，observed 才是 2**，理由三條：
#
# 1. **一次成功不是常態證據。** 那則探針是在需求方**正在螢幕前、而且正在等它**的
#    情況下被看到的；真正的告警在 21:10 無預警發出，橫幅數秒後自動消失。用一次
#    attended 的成功去推論 unattended 的夜晚，正是本卡在別處禁止的推論形狀。
# 2. **這條通道靠一個使用者設定，而它已經無聲退化過一次。** 那個專注模式不是刻意
#    開的，卻擋掉了所有通知且無人察覺——那正是本卡要消滅的失效形狀。可以被無聲撤銷
#    的保證不是保證。
# 3. **「人看到了」永遠是人證，碼判不到。** 與 R1 不肯把 `rc=0` 當送達是同一把尺。
#
# 所以：`goal_floor` 是不依賴任何使用者設定就成立的保證（稽核痕跡 ＋ pytest header），
# 而 `push_channel` 只回報**管道能力**、不往目標層級推（見 no_per_notification_claim）。
# 推播若被擋，下一次執行就會自己說出來——把「無聲退化」換成「有聲退化」，那是本卡
# 真正買到的東西；至於「那一則到底有沒有被看到」，本卡誠實地不回答。

READER_CONTRACT = {
    "goal_floor": 3,
    "goal_floor_note": "不依賴任何使用者設定就成立的部分：logs/schedule-alert.json ＋ "
                       "tests/conftest.py 印在每次 pytest header 的那幾行。這一層永遠為真。",
    "push_channel_note": "notification.push_channel 量的是**管道能力**（這個 app 的通知"
                         "此刻有沒有能力出現在畫面上），不是本則通知的投遞結果。"
                         "open／blocked／unknown 三態；判準是全域專注模式對本 app 的裁決，"
                         "不需要把日誌歸屬到某一則通知。⚠️ blocked 的實際型態是 "
                         "`delay delivery`＝延後補送，不是丟棄。",
    "no_per_notification_claim": "本卡**不宣稱**任何一則通知是否被看到，也不再有 "
                                 "goal_observed 欄位。兩個理由：(1) 通知 id 沒有被寫進"
                                 "裁決行，某一則的結果在此平台上量不到；(2) 就算量到被"
                                 "抑制也推不出『沒出現』——`delay delivery` 是延後，實測"
                                 "使用者關閉專注模式時 14 則會被 Re-add 補送。"
                                 "而『延後多久算失效』本專案沒有任何文件訂過界線，"
                                 "自己訂一條就是把猜測寫成判準。",
    "who": "需求方（螢幕上的通知）＋ 任何要動這個 repo 的人或 AI（pytest header）",
    "when": "通知：異常發生當晚 21:10 即時；header：每次跑 `uv run pytest`（CLAUDE.md "
            "明訂 push 前必跑，`-q` 也印）。兩者都不需要有人記得去翻檔案。",
    "how": "logs/schedule-alert.json 存在＝有未處理的排程異常；條件解除時自動刪除，"
           "故『檔案在』本身就是訊號。header 會把訊息與『這次推播到底有沒有出現』一起印。",
    "push_channel": "macOS 通知（osascript → Script Editor）。2026-08-16 需求方關閉非刻意"
                    "開啟的專注模式後復活。⚠️ 它靠使用者設定，可被無聲撤銷，故每次執行"
                    "都會重新量一次而不是假設它還活著。要引入 email／Slack／webhook 等"
                    "其他推播管道會改變本專案的告警模型，屬需求方裁量。",
    "what_code_can_never_prove": "『這一則有人看到了』。系統紀錄可以證明管道被擋（壞了），但無法證明某一則通知被呈現給人看——通知 id 沒有被寫進裁決行。"
                                 "2026-08-16 那次是需求方口述的**人證**，不可重跑、"
                                 "不在任何日誌裡、也不可能被測試涵蓋。",
}


def write_notify_artifacts(repo: Path, report: dict) -> None:
    """三層備援：通知（在本機被專注模式靜音）→ 持久產物 → 非零退出碼。

    ⚠️ 通知**先送再寫檔**，因為投遞判定要一起寫進產物；osascript 與日誌查詢都有
    timeout，故不會因為通知那一層卡住而讓產物寫不出來。
    """
    stamp = datetime.now(TAIPEI).strftime("%Y-%m-%dT%H:%M:%S%z")
    trigger = current_trigger()
    delivery: dict = {"attempted": False,
                      "push_channel": {"state": PUSH_CHANNEL_UNKNOWN,
                                       "reason": "本次無異常，未送出通知",
                                       "evidence": "", "active_mode": None,
                                       "measures": "管道能力，不是本則通知的投遞結果"}}
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
    channel = (delivery.get("push_channel") or {}).get("state")
    if delivery.get("attempted") and delivery.get("command_failed"):
        # 最優先：連送都沒送出去，與「送了但被擋」是兩件事，讀者摘要必須分得開。
        print(f"WARN 通知指令失敗：{delivery.get('command_error')}　"
              "→ 這則告警**完全沒有**送出，讀者請看 logs/schedule-alert.json",
              file=sys.stderr)
    elif delivery.get("attempted") and channel == PUSH_CHANNEL_BLOCKED:
        # 管道被擋是**可以斷言**的：抑制是全域的，與是哪一則無關。
        # 落 logs/launchd-schedule-watchdog.err.log，那是不依賴通知權限的那一面。
        print("WARN 推播管道被專注模式擋住，這則告警**確定沒有**出現在螢幕上　"
              "→ 讀者請看 logs/schedule-alert.json（pytest header 也會印）",
              file=sys.stderr)
    elif delivery.get("attempted") and channel == PUSH_CHANNEL_UNKNOWN:
        # ⚠️ 措辭必須與上面不同：量不到就是量不到，**不得**講成「沒送到」。
        print("WARN 通知已送出，但量不到專注模式狀態——**既不代表送到，也不代表沒送到**。"
              "　保險起見請看 logs/schedule-alert.json", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
