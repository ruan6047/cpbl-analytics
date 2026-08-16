"""排程偵測器的行為守衛（OPS-SCHEDULE-FAILURE-BLIND1／#132）。

**這一檔的主體是變異檢驗，不是正常路徑。** 卡面驗收條件第 3 條逐字要求「必須驗證告警
機制自己會響：刻意讓一個排程失敗，確認訊號真的出現。沒做過這件事的偵測器不算數」。
因此每一種判定都有一個 case **人為讓該情境成立**，斷言偵測器真的報出來；正常路徑另有
負控制（`test_healthy_schedule_reports_nothing`），確保這些斷言不是恆真。

決定性：全部走假 repo ＋ `now` 覆寫 ＋ 注入式 launchctl／開機探針。**不觸網、不碰真實
launchd、不觸發任何爬蟲。**
"""

from __future__ import annotations

import importlib.util
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
WATCH = ROOT / "scripts" / "schedule_watch.py"
REAL_REGISTRY = ROOT / "scripts" / "schedule-registry.json"
TAIPEI = timezone(timedelta(hours=8))


def _load_module():
    spec = importlib.util.spec_from_file_location("_schedule_watch", WATCH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


sw = _load_module()

DAILY = {"kind": "daily", "hour": 10, "minute": 10}
WEEKLY_MON = {"kind": "weekly", "weekday": 1, "hour": 14, "minute": 10}

PLIST_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<plist version="1.0">
<dict>
  <key>Label</key><string>{label}</string>
  <key>StartCalendarInterval</key>
  <dict>
{interval}  </dict>
</dict>
</plist>
"""


def _write_plist(path: Path, label: str, cadence: dict) -> None:
    lines = ""
    if cadence["kind"] == "weekly":
        lines += f"    <key>Weekday</key><integer>{cadence['weekday']}</integer>\n"
    lines += f"    <key>Hour</key><integer>{cadence['hour']}</integer>\n"
    lines += f"    <key>Minute</key><integer>{cadence['minute']}</integer>\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(PLIST_TEMPLATE.format(label=label, interval=lines), encoding="utf-8")


def _job(label: str, cadence: dict, *, effective_from="2026-08-01", history_from="2026-08-01",
         expected_installed=True) -> dict:
    return {
        "label": label,
        "plist": f"scripts/{label}.plist",
        "cadence": cadence,
        "effective_from": effective_from,
        "expected_installed": expected_installed,
        "expected_installed_reason": "測試用",
        "status_path": f"logs/last-{label}.json",
        "history_path": f"logs/schedule-history/{label}.jsonl",
        "history_from": history_from,
    }


def _build_repo(tmp_path: Path, jobs: list, *, anchor: str = "2026-01-01") -> tuple[Path, dict]:
    """假 repo。`anchor` 預設落在很早的過去＝「這套機制早就部署好了」。

    ⚠️ 必須明寫，不能讓它由第一次執行自己產生：那樣錨點會等於 `now`，判定下界把所有
    被測週期都擋掉，於是每一條缺席／失敗測試都變成恆真的空斷言。錨點自己的行為另有
    專門的一組測試（見檔尾「部署錨點」節）。
    """
    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True, exist_ok=True)
    for job in jobs:
        _write_plist(repo / job["plist"], job["label"], job["cadence"])
    if anchor is not None:
        path = repo / sw.ANCHOR_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"anchor_date": anchor, "anchor_at": f"{anchor}T00:00:00+08:00"}),
                        encoding="utf-8")
    return repo, {"schema_version": 1, "jobs": jobs}


def _write_history(repo: Path, label: str, records: list) -> None:
    path = repo / "logs" / "schedule-history" / f"{label}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def _record(started: str, state: str, *, trigger="launchd", exit_code=None,
            failed_phase=None, log=None, finished: str | None = None) -> dict:
    """`finished` 與 `started` 分開很重要：終態列的 `observed_at` 才是它**何時存在**。

    2026-08-10 那次 10:10 起跑、11:50:37 才寫入 failed——若把兩者混為一談，`--now`
    回放會在 11:00 就「看到」還不存在的終態，把偵測器的能力誇大成它沒有的。
    """
    ended = None if state == "running" else (finished or started)
    return {"schema_version": 1, "label": "x", "state": state, "trigger": trigger,
            "started_at": started, "finished_at": ended,
            "exit_code": exit_code, "failed_phase": failed_phase, "log": log,
            "note": None, "observed_at": ended or started}


def _evaluate(repo: Path, registry: dict, now: str, *, installed=True, listing=(),
              api_url="none", boots=()) -> dict:
    return sw.evaluate(
        registry, repo, sw.parse_timestamp(now), api_url, 1.0, 60,
        installed_probe=(installed if callable(installed) else (lambda _label: installed)),
        listing_probe=lambda: list(listing),
        boot_probe=lambda: list(boots),
    )


def _verdicts(report: dict) -> set:
    found = {f["verdict"] for f in report["registry_findings"]}
    found |= {f["verdict"] for f in report["global_findings"]}
    for job in report["jobs"]:
        found |= {f["verdict"] for f in job["findings"]}
    return found


# ----------------------------------------------------------------- 週期數學

@pytest.mark.parametrize(("now", "expected"), [
    ("2026-08-15T09:00:00+0800", "2026-08-14T10:10:00+08:00"),   # 還沒到今天的觸發點
    ("2026-08-15T10:10:00+0800", "2026-08-15T10:10:00+08:00"),   # 剛好命中
    ("2026-08-15T21:10:00+0800", "2026-08-15T10:10:00+08:00"),   # 偵測器實際執行的時刻
])
def test_daily_current_cycle(now: str, expected: str) -> None:
    assert sw.previous_fire(DAILY, sw.parse_timestamp(now)).isoformat() == expected


@pytest.mark.parametrize(("now", "expected"), [
    ("2026-08-15T21:10:00+0800", "2026-08-10T14:10:00+08:00"),   # 週六 → 回到週一
    ("2026-08-10T14:09:59+0800", "2026-08-03T14:10:00+08:00"),   # 差一秒還沒觸發
])
def test_weekly_current_cycle(now: str, expected: str) -> None:
    assert sw.previous_fire(WEEKLY_MON, sw.parse_timestamp(now)).isoformat() == expected


def test_launchd_weekday_zero_is_sunday() -> None:
    """launchd 的 Weekday 0 與 7 都是週日；Python isoweekday 只認 7。搞錯會整整差一天。"""
    cadence = {"kind": "weekly", "weekday": 0, "hour": 9, "minute": 0}
    fire = sw.previous_fire(cadence, sw.parse_timestamp("2026-08-15T21:00:00+0800"))
    assert fire.isoweekday() == 7 and fire.isoformat() == "2026-08-09T09:00:00+08:00"


# ------------------------------------------------- 負控制：正常時必須完全安靜

def test_healthy_schedule_reports_nothing(tmp_path: Path) -> None:
    """負控制。少了這個，下面每一條「會響」的斷言都可能只是因為它恆響。"""
    job = _job("com.cpbl.daily", DAILY)
    repo, registry = _build_repo(tmp_path, [job])
    _write_history(repo, "com.cpbl.daily", [
        _record("2026-08-13T10:10:00+0800", "running"),
        _record("2026-08-13T10:40:00+0800", "succeeded", exit_code=0),
        _record("2026-08-14T10:10:00+0800", "running"),
        _record("2026-08-14T10:40:00+0800", "succeeded", exit_code=0),
        _record("2026-08-15T10:10:00+0800", "running"),
        _record("2026-08-15T10:40:00+0800", "succeeded", exit_code=0),
    ])
    report = _evaluate(repo, registry, "2026-08-15T21:10:00+0800")

    assert report["verdict"] == "OK"
    assert report["exit_code"] == 0
    assert report["message"] == "排程一切正常"


# ------------------------------------------------------- 變異檢驗：逐一讓它成立

def test_mutation_missing_cycle_is_reported(tmp_path: Path) -> None:
    """**缺席**：昨天完全沒有紀錄。這是最難的一種——沒跑不會產生任何痕跡，
    只能靠「預期每天有一列而某天沒有」反推。"""
    job = _job("com.cpbl.daily", DAILY)
    repo, registry = _build_repo(tmp_path, [job])
    _write_history(repo, "com.cpbl.daily", [
        _record("2026-08-13T10:10:00+0800", "succeeded", exit_code=0),
        # 08-14 整天沒有任何列 ← 人為造成的缺席
        _record("2026-08-15T10:10:00+0800", "succeeded", exit_code=0),
    ])
    report = _evaluate(repo, registry, "2026-08-15T21:10:00+0800")

    assert "MISSING" in _verdicts(report)
    assert report["exit_code"] == sw.EXIT_MISSING
    assert "沒跑" in report["message"]


def test_mutation_failed_cycle_is_reported_with_streak(tmp_path: Path) -> None:
    """**失敗**，且訊息必須帶連續次數（需求方裁定四：第 1 天與第 5 天讀起來要不一樣）。"""
    job = _job("com.cpbl.daily", DAILY)
    repo, registry = _build_repo(tmp_path, [job])
    _write_history(repo, "com.cpbl.daily", [
        _record("2026-08-12T10:10:00+0800", "succeeded", exit_code=0),
        _record("2026-08-13T10:10:00+0800", "failed", exit_code=1, failed_phase="scrape"),
        _record("2026-08-14T10:10:00+0800", "failed", exit_code=1, failed_phase="scrape"),
        _record("2026-08-15T10:10:00+0800", "failed", exit_code=1, failed_phase="sync"),
    ])
    report = _evaluate(repo, registry, "2026-08-15T21:10:00+0800")

    assert report["exit_code"] == sw.EXIT_FAILED
    assert report["jobs"][0]["streak"] == 3
    assert "連續第 3 天" in report["message"]


def test_mutation_incomplete_run_is_distinguishable_from_absence(tmp_path: Path) -> None:
    """**開跑後死掉**：停在 `running` 而後繼週期已觸發。

    這是「歷史在動工前就寫 running」買到的唯一東西——沒有它，崩潰與從未開跑在觀測上
    完全相同。
    """
    job = _job("com.cpbl.daily", DAILY)
    repo, registry = _build_repo(tmp_path, [job])
    _write_history(repo, "com.cpbl.daily", [
        _record("2026-08-14T10:10:00+0800", "running"),   # 沒有終態列 ← 被 kill 掉
        _record("2026-08-15T10:10:00+0800", "succeeded", exit_code=0),
    ])
    report = _evaluate(repo, registry, "2026-08-15T21:10:00+0800")

    assert "INCOMPLETE" in _verdicts(report)
    assert "MISSING" not in _verdicts(report)     # 與缺席分得開
    assert report["exit_code"] == sw.EXIT_INCOMPLETE


def test_single_skip_is_silent_but_consecutive_skips_alarm(tmp_path: Path) -> None:
    """單次 lock 撞期是設計內的正常行為（週跑刻意讓路給每日鏈），不該告警。

    真正的病是**永久跳過**——stale lock 留下即永遠 skip、永遠 exit 75、永遠沒訊號。
    以「連續」為判準才打中病灶而不製造噪音。
    """
    job = _job("com.cpbl.weekly", WEEKLY_MON)
    repo, registry = _build_repo(tmp_path, [job])
    _write_history(repo, "com.cpbl.weekly", [
        _record("2026-08-03T14:10:00+0800", "succeeded", exit_code=0),
        _record("2026-08-10T14:10:00+0800", "skipped", exit_code=75),
    ])
    quiet = _evaluate(repo, registry, "2026-08-11T21:10:00+0800")
    assert quiet["exit_code"] == 0

    _write_history(repo, "com.cpbl.weekly", [
        _record("2026-08-17T14:10:00+0800", "skipped", exit_code=75),
    ])
    loud = _evaluate(repo, registry, "2026-08-18T21:10:00+0800")
    assert "SKIPPED_CONSECUTIVE" in _verdicts(loud)
    assert loud["exit_code"] == sw.EXIT_SKIPPED_CONSECUTIVE
    assert "連續第 2 週" in loud["message"]


def test_mutation_job_declared_but_not_installed(tmp_path: Path) -> None:
    job = _job("com.cpbl.daily", DAILY)
    repo, registry = _build_repo(tmp_path, [job])
    report = _evaluate(repo, registry, "2026-08-15T21:10:00+0800", installed=False)

    assert "JOB_NOT_INSTALLED" in _verdicts(report)


def test_mutation_history_corruption_is_counted_not_swallowed(tmp_path: Path) -> None:
    job = _job("com.cpbl.daily", DAILY)
    repo, registry = _build_repo(tmp_path, [job])
    _write_history(repo, "com.cpbl.daily", [
        _record("2026-08-14T10:10:00+0800", "succeeded", exit_code=0),
        _record("2026-08-15T10:10:00+0800", "succeeded", exit_code=0),
    ])
    path = repo / "logs" / "schedule-history" / "com.cpbl.daily.jsonl"
    with path.open("a", encoding="utf-8") as handle:
        handle.write('{"state": "succ\n')            # 截斷的一列（崩潰時可能出現）
    report = _evaluate(repo, registry, "2026-08-15T21:10:00+0800")

    assert "HISTORY_CORRUPT" in _verdicts(report)
    assert report["jobs"][0]["corrupt_lines"] == 1


# --------------------------------------- 變異檢驗：fail closed 對登記表告警

def test_mutation_plist_on_disk_missing_from_registry(tmp_path: Path) -> None:
    """磁碟有 plist 而登記表沒有 → **對登記表告警，不對 job 告警**（需求方裁定一）。"""
    job = _job("com.cpbl.daily", DAILY)
    repo, registry = _build_repo(tmp_path, [job])
    _write_plist(repo / "scripts" / "com.cpbl.stranger.plist", "com.cpbl.stranger", DAILY)
    report = _evaluate(repo, registry, "2026-08-15T21:10:00+0800")

    assert "REGISTRY_INCOMPLETE" in _verdicts(report)
    assert report["exit_code"] == sw.EXIT_REGISTRY


def test_mutation_launchctl_has_a_job_the_registry_does_not(tmp_path: Path) -> None:
    job = _job("com.cpbl.daily", DAILY)
    repo, registry = _build_repo(tmp_path, [job])
    report = _evaluate(repo, registry, "2026-08-15T21:10:00+0800",
                       listing=["com.cpbl.daily", "com.cpbl.surprise"])

    assert "REGISTRY_INCOMPLETE" in _verdicts(report)


def test_deliberately_uninstalled_job_is_not_reported_as_broken(tmp_path: Path) -> None:
    """#115 死於把刻意邊界當缺陷。`expected_installed=false` 且真的沒裝 ⇒ 完全安靜。"""
    job = _job("com.cpbl.dormant", WEEKLY_MON, effective_from=None, history_from=None,
               expected_installed=False)
    repo, registry = _build_repo(tmp_path, [job])
    report = _evaluate(repo, registry, "2026-08-15T21:10:00+0800", installed=False)

    assert report["exit_code"] == 0
    assert report["jobs"] == []          # 不判缺席，連評估都不做


def test_mutation_dormant_job_that_got_installed_is_a_registry_conflict(tmp_path: Path) -> None:
    """反向：宣告不該裝卻裝了。方向仍是「先確認是刻意 cutover 還是誤裝」而非指控 job。"""
    job = _job("com.cpbl.dormant", WEEKLY_MON, effective_from=None, history_from=None,
               expected_installed=False)
    repo, registry = _build_repo(tmp_path, [job])
    report = _evaluate(repo, registry, "2026-08-15T21:10:00+0800", installed=True)

    assert "REGISTRY_CONFLICT" in _verdicts(report)


def test_mutation_cadence_drift_between_registry_and_plist(tmp_path: Path) -> None:
    """cadence 在兩處重複必然漂移，故機械對帳。plist 才是 launchd 真正吃的那份。"""
    job = _job("com.cpbl.daily", DAILY)
    repo, registry = _build_repo(tmp_path, [job])
    _write_plist(repo / job["plist"], job["label"], {"kind": "daily", "hour": 3, "minute": 10})
    report = _evaluate(repo, registry, "2026-08-15T21:10:00+0800")

    assert "REGISTRY_INVALID" in _verdicts(report)


def test_mutation_missing_plist_and_missing_field(tmp_path: Path) -> None:
    job = _job("com.cpbl.daily", DAILY)
    repo, registry = _build_repo(tmp_path, [job])
    (repo / job["plist"]).unlink()
    assert "REGISTRY_INVALID" in _verdicts(_evaluate(repo, registry, "2026-08-15T21:10:00+0800"))

    broken = _job("com.cpbl.daily", DAILY)
    del broken["history_from"]
    repo2, registry2 = _build_repo(tmp_path / "b", [broken])
    assert "REGISTRY_INVALID" in _verdicts(
        _evaluate(repo2, registry2, "2026-08-15T21:10:00+0800"))


def test_mutation_history_from_in_the_future_is_rejected(tmp_path: Path) -> None:
    """`history_from` 落在未來會讓偵測器永久靜默——那是 fail **open**，必須擋掉。"""
    job = _job("com.cpbl.daily", DAILY, history_from="2099-01-01")
    repo, registry = _build_repo(tmp_path, [job])
    report = _evaluate(repo, registry, "2026-08-15T21:10:00+0800")

    assert "REGISTRY_INVALID" in _verdicts(report)


def test_registry_problems_suppress_job_claims(tmp_path: Path) -> None:
    """登記表不可信時其餘判定一律不宣稱（優先序最高）。"""
    job = _job("com.cpbl.daily", DAILY)
    repo, registry = _build_repo(tmp_path, [job])
    _write_plist(repo / "scripts" / "com.cpbl.stranger.plist", "com.cpbl.stranger", DAILY)
    report = _evaluate(repo, registry, "2026-08-15T21:10:00+0800")

    assert report["registry_blocked"] is True
    assert report["jobs"] == []


# -------------------------------------------- 部署當天不得整片誤報（#115 的死法）

def test_cycles_before_history_from_are_not_reported_missing(tmp_path: Path) -> None:
    """`effective_from`（job 生效日）與 `history_from`（歷史寫入器生效日）必須分開。

    不分開的話，部署當天整段既有歷史會被報成一片 MISSING，然後告警被關掉——與登記表
    本身要擋的是同一個死法，只是換一個維度。
    """
    job = _job("com.cpbl.daily", DAILY, effective_from="2026-07-19", history_from="2026-08-15")
    repo, registry = _build_repo(tmp_path, [job])
    report = _evaluate(repo, registry, "2026-08-15T21:10:00+0800")

    assert report["exit_code"] == 0
    assert report["jobs"][0]["cycles"] == []    # 08-14 在 history_from 之前，不判


def test_manual_run_does_not_satisfy_a_scheduled_cycle(tmp_path: Path) -> None:
    """手動補跑不算「排程有跑」——否則手動救火會把壞掉的排程蓋成健康。"""
    job = _job("com.cpbl.daily", DAILY)
    repo, registry = _build_repo(tmp_path, [job])
    _write_history(repo, "com.cpbl.daily", [
        _record("2026-08-14T19:00:00+0800", "succeeded", trigger="manual", exit_code=0),
        _record("2026-08-15T10:10:00+0800", "succeeded", exit_code=0),
    ])
    report = _evaluate(repo, registry, "2026-08-15T21:10:00+0800")

    assert "MISSING" in _verdicts(report)


def test_machine_off_for_days_aggregates_into_one_message(tmp_path: Path) -> None:
    """launchd 把錯過的多個 interval 合併成一次補跑，故 3 天關機只有 1 次補跑、
    2 個週期是真的缺席。偵測器如實報出，但訊息**聚合**成一則（不逐週期轟炸）。"""
    job = _job("com.cpbl.daily", DAILY)
    repo, registry = _build_repo(tmp_path, [job])
    _write_history(repo, "com.cpbl.daily", [
        _record("2026-08-11T10:10:00+0800", "succeeded", exit_code=0),
        # 08-12、08-13、08-14 關機 ← 三個週期缺席（08-15 是 F0，無紀錄故不判）
    ])
    report = _evaluate(repo, registry, "2026-08-15T21:10:00+0800")

    assert report["jobs"][0]["streak"] == 3
    assert report["message"].count("；") == 0        # 一則，不是三則
    assert "連續第 3 天" in report["message"]


def test_current_cycle_still_running_is_never_accused(tmp_path: Path) -> None:
    """`running` 不指控——那可能只是還在跑。實測 27 次排程有 8 次在 11:00 仍在執行，
    而 2026-08-04 那次真的跑了 287 分鐘且正常結束。"""
    job = _job("com.cpbl.daily", DAILY)
    repo, registry = _build_repo(tmp_path, [job])
    _write_history(repo, "com.cpbl.daily", [
        _record("2026-08-14T10:10:00+0800", "succeeded", exit_code=0),
        _record("2026-08-15T10:10:00+0800", "running"),
    ])
    report = _evaluate(repo, registry, "2026-08-15T11:00:00+0800")

    assert report["exit_code"] == 0
    assert [c["role"] for c in report["jobs"][0]["cycles"]] == ["F1"]


# --------------------------------------------------------- 偵測器 B（生產側）

def _api_fixture(tmp_path: Path, metrics: dict) -> str:
    path = tmp_path / "info.json"
    path.write_text(json.dumps({"status": "running", "version": "x", "metrics": metrics}),
                    encoding="utf-8")
    return path.as_uri()


def test_mutation_production_stall_is_reported(tmp_path: Path) -> None:
    job = _job("com.cpbl.daily", DAILY, history_from="2026-08-15")
    repo, registry = _build_repo(tmp_path, [job])
    api = _api_fixture(tmp_path, {"prod_sync_stalled": True, "prod_sync_age_hours": 51.2,
                                  "prod_sync_last_at": "2026-08-13T10:40:00+08:00",
                                  "prod_sync_stall_after_h": 36})
    report = _evaluate(repo, registry, "2026-08-15T21:10:00+0800", api_url=api)

    assert "B_STALLED" in _verdicts(report)
    assert report["exit_code"] == sw.EXIT_B_STALLED
    assert "51.2" in report["message"]


def test_production_healthy_is_silent(tmp_path: Path) -> None:
    job = _job("com.cpbl.daily", DAILY, history_from="2026-08-15")
    repo, registry = _build_repo(tmp_path, [job])
    api = _api_fixture(tmp_path, {"prod_sync_stalled": False, "prod_sync_age_hours": 11.0,
                                  "prod_sync_last_at": "2026-08-15T10:40:00+08:00",
                                  "prod_sync_stall_after_h": 36})
    assert _evaluate(repo, registry, "2026-08-15T21:10:00+0800", api_url=api)["exit_code"] == 0


def test_mutation_production_unreachable_and_fields_absent_are_different(tmp_path: Path) -> None:
    """「取不到訊號」與「B 說一切正常」必須是兩件事。把不確定讀成健康正是本卡的病。"""
    job = _job("com.cpbl.daily", DAILY, history_from="2026-08-15")
    repo, registry = _build_repo(tmp_path, [job])

    gone = _evaluate(repo, registry, "2026-08-15T21:10:00+0800",
                     api_url=(tmp_path / "nope.json").as_uri())
    assert "B_UNREACHABLE" in _verdicts(gone)

    stale_api = _api_fixture(tmp_path, {"games_indexed": 1})     # 舊版 /api/info
    absent = _evaluate(repo, registry, "2026-08-15T21:10:00+0800", api_url=stale_api)
    assert "B_UNAVAILABLE" in _verdicts(absent)


def test_local_failure_outranks_production_signal_loss(tmp_path: Path) -> None:
    """退出碼取**嚴重度**最高者，不是數值最大者：B 取不到訊號（7）不該蓋掉本機失敗（3）。"""
    job = _job("com.cpbl.daily", DAILY)
    repo, registry = _build_repo(tmp_path, [job])
    _write_history(repo, "com.cpbl.daily", [
        _record("2026-08-14T10:10:00+0800", "failed", exit_code=1, failed_phase="scrape"),
    ])
    report = _evaluate(repo, registry, "2026-08-15T21:10:00+0800",
                       api_url=(tmp_path / "nope.json").as_uri())

    assert {"FAILED", "B_UNREACHABLE"} <= _verdicts(report)
    assert report["exit_code"] == sw.EXIT_FAILED


# -------------------------------------------- RunAtLoad 的自證不變量（開機對帳）

def test_mutation_boot_without_a_watchdog_run_proves_runatload_failed(tmp_path: Path) -> None:
    """bootout/bootstrap 只證明「load 時會啟動」；一次真正的冷開機本卡沒有觀測到。

    這個不變量把那個推導換成**會自己舉手的可證偽預測**：開機後寬限期內沒有偵測器的
    執行紀錄，就是 RunAtLoad 沒兌現的反證。下一次自然關機就是實驗。
    """
    job = _job("com.cpbl.schedule-watchdog", {"kind": "daily", "hour": 21, "minute": 10})
    repo, registry = _build_repo(tmp_path, [job])
    _write_history(repo, "com.cpbl.schedule-watchdog", [
        _record("2026-08-15T21:10:00+0800", "succeeded", exit_code=0),
    ])
    boot = datetime(2026, 8, 15, 8, 0, tzinfo=TAIPEI)          # 早上開機，沒有對應紀錄

    report = _evaluate(repo, registry, "2026-08-15T21:10:00+0800", boots=[boot])
    assert "RUNATLOAD_NOT_HONORED" in _verdicts(report)

    _write_history(repo, "com.cpbl.schedule-watchdog", [
        _record("2026-08-15T08:02:00+0800", "succeeded", exit_code=0),
    ])
    healed = _evaluate(repo, registry, "2026-08-15T21:10:00+0800", boots=[boot])
    assert "RUNATLOAD_NOT_HONORED" not in _verdicts(healed)


def test_boot_inside_grace_window_is_not_yet_an_accusation(tmp_path: Path) -> None:
    job = _job("com.cpbl.schedule-watchdog", {"kind": "daily", "hour": 21, "minute": 10})
    repo, registry = _build_repo(tmp_path, [job])
    boot = datetime(2026, 8, 15, 21, 5, tzinfo=TAIPEI)
    report = _evaluate(repo, registry, "2026-08-15T21:10:00+0800", boots=[boot])

    assert "RUNATLOAD_NOT_HONORED" not in _verdicts(report)


# ------------------------------------------------------- 真實登記表本身的健檢

def test_shipped_registry_is_internally_consistent() -> None:
    """交付的登記表對真實 plist 逐欄對帳。cadence 打錯會讓每個週期都算在錯的時點上。"""
    registry = json.loads(REAL_REGISTRY.read_text(encoding="utf-8"))
    labels = [job["label"] for job in registry["jobs"]]
    on_disk = sorted(p.name[: -len(".plist")] for p in (ROOT / "scripts").glob("com.cpbl.*.plist"))

    assert sorted(labels) == on_disk, "登記表與 scripts/ 下的 plist 必須一一對應"
    for job in registry["jobs"]:
        for field in sw.REQUIRED_JOB_FIELDS:
            assert field in job, f"{job.get('label')} 缺 {field}"
        expected = dict(job["cadence"])
        if expected.get("kind") == "weekly":
            expected["weekday"] = sw._launchd_weekday_to_iso(expected["weekday"])
        assert sw.plist_cadence(ROOT / job["plist"]) == expected, job["label"]
        if job["expected_installed"]:
            assert job["effective_from"] and job["history_from"], job["label"]


# ------------------------------------------------- 2026-08-10 回放（卡面驗證 1）

# 取自**真實存檔** logs/refresh-20260810-101000.log 的三行（該檔在 logs/ 內、不入版控，
# 故此處固定為 fixture 以保 CI 可重現；本機的完整回放輸出見交付報告）：
#   [2026-08-10 10:10:00] start: cpbl-refresh-recent
#   [2026-08-10 11:50:37] scrape exit=1
#   [2026-08-10 11:50:37] overall exit=1
# ⚠️ 失敗相是 **scrape** 不是 sync（該檔內 "sync prod" 出現 0 次——爬取先失敗，
# 同步根本沒被嘗試）。Plan 的預先登記預測寫成 `FAILED(sync, exit=1)`，相標錯了；
# 時點預測（當晚報出）成立。見交付報告。
REPLAY_2026_08_10 = [
    _record("2026-08-10T10:10:00+0800", "running", log="logs/refresh-20260810-101000.log"),
    _record("2026-08-10T10:10:00+0800", "failed", finished="2026-08-10T11:50:37+0800",
            exit_code=1, failed_phase="scrape", log="logs/refresh-20260810-101000.log"),
    # 隔日的成功——正是它把 last-launchd-status.json 覆寫成 succeeded，讓那次失敗
    # 在「只讀最近一次」的世界裡徹底消失（實測 logs/refresh-20260811-101138.log
    # start 10:11:38、overall exit=0 @ 10:44:08）。
    _record("2026-08-11T10:11:38+0800", "running", log="logs/refresh-20260811-101138.log"),
    _record("2026-08-11T10:11:38+0800", "succeeded", finished="2026-08-11T10:44:08+0800",
            exit_code=0, log="logs/refresh-20260811-101138.log"),
]

# history_from 設在回放歷史的第一天：那是「歷史寫入器在這個回放世界裡的生效日」。
# 設更早會把 08-10 之前沒有紀錄的日子全報成 MISSING，正是 history_from 存在的理由。
REPLAY_HISTORY_FROM = "2026-08-10"


def _replay_repo(tmp_path: Path) -> tuple[Path, dict]:
    job = _job("com.cpbl.scrape-daily", DAILY,
               effective_from="2026-07-19", history_from=REPLAY_HISTORY_FROM)
    repo, registry = _build_repo(tmp_path, [job])
    _write_history(repo, "com.cpbl.scrape-daily", REPLAY_2026_08_10)
    return repo, registry


def test_replay_alerts_the_same_evening_via_the_terminal_current_cycle(tmp_path: Path) -> None:
    """**預先登記的預測 1**：偵測器 21:10 執行 → 當天晚上（2026-08-10）就報出來。

    這條路徑是 Plan 質疑 2 追加的「F0 已是終態就一併判」。沒有它，08-10 要等到隔日。
    """
    repo, registry = _replay_repo(tmp_path)
    report = _evaluate(repo, registry, "2026-08-10T21:10:00+0800")

    assert report["exit_code"] == sw.EXIT_FAILED
    cycles = {c["role"]: c["verdict"] for c in report["jobs"][0]["cycles"]}
    assert cycles["F0"] == "FAILED"
    assert "連續第 1 天" in report["message"]


def test_replay_still_alerts_next_day_even_if_the_detector_ran_at_1100(tmp_path: Path) -> None:
    """**預先登記的預測 2**：若偵測器剛好在 11:00 跑（該次仍 `running`），當下不指控，
    但隔日由 F1 補上——**兩條路徑都沒有偽陰性**，這是嚴格優於「只判上一個週期」的下界。
    """
    repo, registry = _replay_repo(tmp_path)

    during = _evaluate(repo, registry, "2026-08-10T11:00:00+0800")
    assert during["exit_code"] == 0                      # running 不指控

    after = _evaluate(repo, registry, "2026-08-11T21:10:00+0800")
    assert after["exit_code"] == sw.EXIT_FAILED
    cycles = {c["role"]: c["verdict"] for c in after["jobs"][0]["cycles"]}
    assert cycles["F1"] == "FAILED" and cycles["F0"] == "OK"


def test_replay_shows_what_the_old_last_status_surface_lost(tmp_path: Path) -> None:
    """08-13（PM 碰巧翻到的那天）：只讀「最近一次」的世界裡狀態是 `succeeded`。

    這就是為什麼歷史必須持久化——`logs/refresh-*.log` 只留 30 份、輪替上限早已咬住，
    而 `last-launchd-status.json` 只留最近一次。
    """
    repo, registry = _replay_repo(tmp_path)
    report = _evaluate(repo, registry, "2026-08-13T21:10:00+0800")

    # F1（08-12）沒有紀錄 → MISSING。F0（08-13）同樣沒有紀錄，但**不判**——「還沒跑」
    # 與「不會跑了」在無紀錄時分不開，保守的一方是不指控，隔日由 F1 補上。
    assert report["exit_code"] == sw.EXIT_MISSING
    assert report["jobs"][0]["streak"] == 1
    assert [c["role"] for c in report["jobs"][0]["cycles"]] == ["F1"]



# ==================================================== 通知投遞：發了不等於送到
#
# 這一組的重點是**投遞判定不得說謊**，而「不說謊」在本卡被打穿過四次：
#   R1：把 `osascript rc=0` 當成送達
#   R2：predicate 濾掉 `Presenting`，presented 結構上不可達
#   R3：把「查不到」渲染成「確定沒送到」
#   R3：用「同 bundle ＋ 時間相近」當關聯，會把無關事件歸給本次通知
#
# 因此每一條都配負控制，且 fixture 一律沿用**實際擷取到的日誌行形狀**（欄位、大小寫、
# 括號都照抄），否則測試會對著一個現實裡不存在的格式變綠。


class _FakeProc:
    def __init__(self, returncode: int, stdout: bytes = b"") -> None:
        self.returncode = returncode
        self.stdout = stdout


class _FakePopen:
    """`notify()` 用 Popen 是為了拿 **PID**——那是關聯回「我們這一則」的唯一硬錨點。"""

    def __init__(self, pid: int, returncode: int) -> None:
        self.pid = pid
        self.returncode = returncode

    def wait(self, timeout=None):  # noqa: ANN001, ANN201 — 只需與 Popen 介面相容
        return self.returncode

    def kill(self) -> None:
        pass


# 真實日誌行形狀（2026-08-16 11:58:18 那次探針原樣擷取，只把 pid／uuid 參數化）。
_TS = "2026-08-16 11:58:18"
_APP = "com.apple.ScriptEditor2"


def _peer_line(pid: int, thread: str = "412f811") -> str:
    return (f"{_TS}.480 Df usernoted[682:{thread}] [com.apple.xpc:connection] "
            f"[0x8dcca6400] activating connection: mach=false listener=false peer=true "
            f"name=com.apple.usernoted.daemon_client.peer[{pid}].0x8dcca6400")


def _record_line(uuid: str, thread: str = "412f811") -> str:
    return (f"{_TS}.485 Df usernoted[682:{thread}] [com.apple.unc:application] "
            f'Delivering <NotificationRecord app:"{_APP}" ident:"DA39-A3EE" req:"" '
            f'uuid:"{uuid}" source:"FDEF2B8D">')


def _presenting_line(uuid: str, thread: str = "412f811") -> str:
    return (f"{_TS}.490 Df usernoted[682:{thread}] [com.apple.unc:application] "
            f'Presenting <NotificationRecord app:"{_APP}" ident:"DA39-A3EE" '
            f'uuid:"{uuid}"> as banner (["badge", "sound", "alert"])')


def _resolution_line(behavior: str) -> str:
    # ⚠️ 這一行**整行不含 bundle id**——只有恆定的 ident。本輪第一版用 bundle 過濾，
    # 於是把裁決行整批濾掉、永遠判 unverified，被端到端探針當場抓到。
    return (f"{_TS}.495 Df NotificationCenter[734:41464c9] [com.apple.unc:application] "
            f"Resolved interruption suppression for DA39-A3EE as {behavior}")


def _muted_line(cause: str) -> str:
    return (f"{_TS}.494 Df NotificationCenter[734:1aec] [com.apple.unc:application] "
            f"DA39-A3EE ({_APP}) muted by {cause}")


_MUTED_LINE = _muted_line("DND suppression: delay")


def _log(pid: int, uuid: str, *, tail_lines=()) -> bytes:
    body = [_peer_line(pid), _record_line(uuid), _presenting_line(uuid), *tail_lines]
    return "\n".join(body).encode()


def _patch_notify(monkeypatch, *, pid: int = 4242, osascript_rc: int = 0,
                  log_rc: int = 0, log_out: bytes = b""):
    """把 `osascript`（Popen）與 `/usr/bin/log`（run）都換成假樁。

    ⚠️ 本檔不得真的彈通知、也不得真的查系統日誌：前者干擾使用者，後者讓測試結果隨
    當下的專注模式漂移（今天綠明天紅，而且紅得沒有道理）。
    """
    calls = []

    def fake_popen(argv, **kwargs):
        calls.append(argv)
        assert argv[0] == "osascript", f"未預期的 Popen：{argv}"
        return _FakePopen(pid, osascript_rc)

    def fake_run(argv, **kwargs):
        calls.append(argv)
        assert argv[0] == "/usr/bin/log", f"未預期的 run：{argv}"
        return _FakeProc(log_rc, log_out)

    monkeypatch.setattr(sw.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(sw.subprocess, "run", fake_run)
    return calls


# ------------------------------------------------------------ 事件關聯 [event correlation]


def test_verdict_is_correlated_to_this_notification_by_uuid(monkeypatch) -> None:
    """關聯鏈：我們給的 PID → usernoted 的 peer 行 → 該執行緒的 uuid → 帶該 uuid 的行。"""
    _patch_notify(monkeypatch, pid=4242,
                  log_out=_log(4242, "D1DCEC63", tail_lines=[_resolution_line("none")]))

    verdict = sw.notify("t", "m")

    assert verdict["delivered"] == sw.DELIVERY_PRESENTED
    assert verdict["correlation"]["uuid"] == "D1DCEC63"
    assert verdict["correlation"]["osascript_pid"] == 4242


def test_unrelated_notification_from_the_same_bundle_is_not_attributed_to_us(
    monkeypatch,
) -> None:
    """**R3 被判錯誤歸屬的那條**：同 bundle 的無關事件不得算到本次通知頭上。

    這裡故意讓時間跨距內出現第二則通知的 uuid。R3 的「同 bundle ＋ 時間窗」會把它的
    抑制訊號吃下來並判 suppressed；現在必須因為歸屬有歧義而**拒絕作答**。
    """
    other = (f"{_TS}.492 Df NotificationCenter[734:1aec] [com.apple.unc:dnd] "
             f'record <NotificationRecord app:"{_APP}" ident:"DA39-A3EE" '
             f'uuid:"BEEFCAFE">')
    _patch_notify(monkeypatch, pid=4242,
                  log_out=_log(4242, "D1DCEC63",
                               tail_lines=[other, _muted_line("DND suppression: delay")]))

    verdict = sw.notify("t", "m")

    assert verdict["delivered"] == sw.DELIVERY_UNVERIFIED, (
        "跨距內有別則通知時仍作答＝把無關事件歸給本次通知")
    assert "無法歸屬" in verdict["reason"] or "另有通知" in verdict["reason"]


def test_missing_peer_line_means_unverified_not_a_guess(monkeypatch) -> None:
    """關聯不上就是關聯不上——不准退回「同 bundle 猜一個」。"""
    _patch_notify(monkeypatch, pid=4242,
                  log_out=_log(9999, "D1DCEC63", tail_lines=[_resolution_line("none")]))

    verdict = sw.notify("t", "m")

    assert verdict["delivered"] == sw.DELIVERY_UNVERIFIED
    assert verdict["correlation"] is None


def test_donotdisturbd_is_not_in_the_predicate_because_it_cannot_be_correlated() -> None:
    """`donotdisturbd` 的行沒有任何欄位對得回某一則通知（實測：uuid 欄位 0/2 行有、
    `identifier` 是空字串、`UUID:` 是解析自己的 id、`clientIdentifier` 是預載客戶端）。
    只剩 bundle 可比，而那正是 R3 錯誤歸屬的來源，故整個排除。"""
    assert "donotdisturbd" not in sw._LOG_PREDICATE
    assert 'process == "usernoted"' in sw._LOG_PREDICATE
    assert 'process == "NotificationCenter"' in sw._LOG_PREDICATE


# ------------------------------------------------------------------ 三態判定


def test_focus_suppression_is_reported_as_definitely_not_shown(monkeypatch) -> None:
    _patch_notify(monkeypatch, pid=4242,
                  log_out=_log(4242, "F983C9FB",
                               tail_lines=[_muted_line("DND suppression: delay"),
                                           _resolution_line("delay")]))

    verdict = sw.notify("t", "m")

    assert verdict["delivered"] == sw.DELIVERY_SUPPRESSED
    assert verdict["goal_observed"] == 3


def test_display_state_mute_is_also_suppression_not_presented(monkeypatch) -> None:
    """實測 2026-08-15 13:23:29：抑制原因是 `muted by display state (displayShared)`，
    **不是** DND。R3 只認 `muted by DND suppression` ＋ donotdisturbd 的 `outcome:`，
    會把這一則judge 錯邊。原因字串必須照實帶出來，不得一律寫成「專注模式」。"""
    _patch_notify(monkeypatch, pid=4242,
                  log_out=_log(4242, "B2B7584D",
                               tail_lines=[_muted_line("display state (displayShared)"),
                                           _resolution_line("delay")]))

    verdict = sw.notify("t", "m")

    assert verdict["delivered"] == sw.DELIVERY_SUPPRESSED
    assert "display state" in verdict["reason"]


def test_presenting_alone_never_means_shown(monkeypatch) -> None:
    """**負控制**：`Presenting` 由 usernoted 在問 DND **之前**就印，三種結局都會出現。

    只有 `Resolved interruption suppression … as none` 才是「沒被擋」的裁決。
    """
    _patch_notify(monkeypatch, pid=4242, log_out=_log(4242, "D1DCEC63"))   # 無裁決行

    verdict = sw.notify("t", "m")

    assert verdict["delivered"] == sw.DELIVERY_UNVERIFIED, (
        "只有 Presenting 就判 presented ⇒ 被 DND 擋下的那些也會被判成送達")


@pytest.mark.parametrize(
    ("log_rc", "log_out", "why"),
    [(1, b"", "/usr/bin/log 非零退出"),
     (0, b"", "查得到但沒有本則通知的紀錄")],
)
def test_unverifiable_delivery_never_claims_success(
    monkeypatch, log_rc: int, log_out: bytes, why: str,
) -> None:
    """**fail closed**：查不到就是 unverified，不准退化成 presented。"""
    _patch_notify(monkeypatch, log_rc=log_rc, log_out=log_out)

    verdict = sw.notify("t", "m")

    assert verdict["delivered"] == sw.DELIVERY_UNVERIFIED, why
    assert verdict["goal_observed"] is None


def test_osascript_failure_is_not_silently_swallowed(monkeypatch) -> None:
    _patch_notify(monkeypatch, osascript_rc=3)

    verdict = sw.notify("t", "m")

    assert verdict["osascript_rc"] == 3
    assert verdict["delivered"] == sw.DELIVERY_UNVERIFIED


def test_delivery_probe_uses_absolute_log_path_not_the_shell_builtin(monkeypatch) -> None:
    """`log` 在 zsh 是內建指令（`type log` → `log is a shell builtin`）。

    R1 的探查寫成裸 `log show`，被 shell 吃掉並回「too many arguments」，於是得到
    **假陰性**——看起來像「系統沒有紀錄」，其實是查詢從來沒跑。釘住絕對路徑。
    """
    calls = _patch_notify(monkeypatch, pid=4242,
                          log_out=_log(4242, "D1DCEC63",
                                       tail_lines=[_resolution_line("none")]))

    sw.notify("t", "m")

    log_calls = [c for c in calls if "log" in c[0]]
    assert log_calls and log_calls[0][0] == "/usr/bin/log"


def test_goal_observed_is_derived_from_the_measurement_not_asserted(monkeypatch) -> None:
    """目標層級由量測推導。presented→2、suppressed→3、unverified→不宣稱。"""
    _patch_notify(monkeypatch, pid=1, log_out=_log(1, "AAAA1111",
                                                   tail_lines=[_resolution_line("none")]))
    assert sw.notify("t", "m")["goal_observed"] == 2

    _patch_notify(monkeypatch, pid=2, log_out=_log(2, "BBBB2222",
                                                   tail_lines=[_muted_line("DND suppression: delay")]))
    assert sw.notify("t", "m")["goal_observed"] == 3

    _patch_notify(monkeypatch, pid=3, log_out=b"")
    assert sw.notify("t", "m")["goal_observed"] is None


def test_alert_artifact_tells_the_reader_what_happened_to_the_push(
    tmp_path: Path, monkeypatch,
) -> None:
    """讀到 alert 的人必須立刻知道推播的下場，而不是預設有人被通知到了。"""
    _patch_notify(monkeypatch, pid=4242,
                  log_out=_log(4242, "F983C9FB",
                               tail_lines=[_muted_line("DND suppression: delay")]))
    repo = tmp_path / "repo"
    (repo / "logs").mkdir(parents=True)
    report = {"exit_code": sw.EXIT_FAILED, "verdict": "FAILED", "message": "假的失敗"}

    sw.write_notify_artifacts(repo, report)

    alert = json.loads((repo / "logs" / "schedule-alert.json").read_text(encoding="utf-8"))
    assert alert["notification"]["delivered"] == sw.DELIVERY_SUPPRESSED
    assert alert["notification"]["goal_observed"] == 3
    assert alert["notification"]["correlation"]["uuid"] == "F983C9FB"
    assert alert["reader"]["goal_floor"] == 3
    assert "人證" in alert["reader"]["what_code_can_never_prove"]


def test_healthy_run_sends_no_notification_and_removes_the_alert(tmp_path: Path,
                                                                 monkeypatch) -> None:
    """負控制：正常時不得彈通知，且要把上一輪的 alert 收掉（『檔案在』才是訊號）。"""
    def explode(*args, **kwargs):
        raise AssertionError("正常路徑不該呼叫任何外部指令")

    monkeypatch.setattr(sw.subprocess, "run", explode)
    monkeypatch.setattr(sw.subprocess, "Popen", explode)
    repo = tmp_path / "repo"
    (repo / "logs").mkdir(parents=True)
    stale = repo / "logs" / "schedule-alert.json"
    stale.write_text("{}", encoding="utf-8")

    sw.write_notify_artifacts(repo, {"exit_code": sw.EXIT_OK, "verdict": "OK", "message": ""})

    assert not stale.exists(), "條件解除後 alert 必須自動消失"


# ============================================ 讀者投遞：pytest header 是唯一有保證的那個
#
# 卡面驗收條件 2 要求指名「誰會看到」。推播已實測是死的（見上一組），所以讀者落在
# `tests/conftest.py` 的 `pytest_report_header`——CLAUDE.md 明訂 push 前必跑 pytest，
# 故這個表面**不需要任何人記得**就會被執行。下面這組證明它真的會出現、也真的會消失。


def _conftest():
    spec = importlib.util.spec_from_file_location(
        "_cpbl_conftest", ROOT / "tests" / "conftest.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_no_alert_file_means_a_completely_silent_header(monkeypatch) -> None:
    """負控制：沒有告警時 header 必須一個字都不多印。

    這條若不存在，下面那條就可能只是「永遠都在喊」而不是「壞了才喊」。
    """
    conf = _conftest()
    monkeypatch.setattr(conf, "_SCHEDULE_ALERT", ROOT / "logs" / "does-not-exist.json")

    assert conf._schedule_alert_header() == []


def test_alert_file_surfaces_in_the_header_with_the_delivery_truth(
    tmp_path: Path, monkeypatch,
) -> None:
    """告警在，header 就要印出訊息、檔案位置，以及**這次推播到底怎麼了**。"""
    conf = _conftest()
    alert = tmp_path / "schedule-alert.json"
    alert.write_text(json.dumps({
        "observed_at": "2026-08-15T21:10:00+0800",
        "verdict": "FAILED", "message": "每日鏈失敗",
        "notification": {"delivered": sw.DELIVERY_SUPPRESSED},
    }, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(conf, "_SCHEDULE_ALERT", alert)

    lines = conf._schedule_alert_header()

    assert any("每日鏈失敗" in ln for ln in lines), "訊息本身沒印出來"
    assert any(str(alert) in ln for ln in lines), "沒告訴讀者去哪看"
    assert any("確定沒有" in ln for ln in lines), (
        "沒有說推播被擋下——讀者會誤以為已經有人被通知到")


def _header_for(conf, tmp_path: Path, monkeypatch, delivered: str) -> str:
    alert = tmp_path / f"alert-{delivered}.json"
    alert.write_text(json.dumps({
        "observed_at": "x", "message": "m",
        "notification": {"delivered": delivered},
    }, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(conf, "_SCHEDULE_ALERT", alert)
    return "\n".join(conf._schedule_alert_header())


def test_the_three_delivery_states_each_say_something_different(
    tmp_path: Path, monkeypatch,
) -> None:
    """**三態必須講三種話。**

    R2 把 `unverified` 和 `suppressed` 都渲染成「沒有送達」——把「查不到」講成「確定
    沒送到」，是在宣稱自己沒有的確定性；那與 R1 把 `rc=0` 講成「送到了」是同一個錯，
    只是換一邊。這條同時擋住兩個方向。
    """
    conf = _conftest()
    texts = {d: _header_for(conf, tmp_path, monkeypatch, d)
             for d in (sw.DELIVERY_PRESENTED, sw.DELIVERY_SUPPRESSED, sw.DELIVERY_UNVERIFIED)}

    assert len(set(texts.values())) == 3, "有兩個狀態講了一模一樣的話"

    # suppressed：可以斷言「確定沒出現」
    assert "確定沒有" in texts[sw.DELIVERY_SUPPRESSED]
    # unverified：**不准**斷言任何一邊
    unverified = texts[sw.DELIVERY_UNVERIFIED]
    assert "既不代表送到" in unverified and "也不代表沒送到" in unverified
    assert "確定沒有" not in unverified, "把『查不到』講成『確定沒送到』"
    # presented：可以說呈現了，但**不得**宣稱有人讀了
    presented = texts[sw.DELIVERY_PRESENTED]
    assert "已呈現" in presented
    assert "不保證有人讀" in presented, "『系統呈現了』不等於『人看到了』"


def test_corrupt_alert_file_degrades_to_a_line_and_never_breaks_pytest(
    tmp_path: Path, monkeypatch,
) -> None:
    """觀測器不得把被觀測的東西弄掛：壞掉的 alert 只降級成一行提示，不是例外。"""
    conf = _conftest()
    alert = tmp_path / "schedule-alert.json"
    alert.write_text("{ this is not json", encoding="utf-8")
    monkeypatch.setattr(conf, "_SCHEDULE_ALERT", alert)

    lines = conf._schedule_alert_header()

    assert len(lines) == 1 and "讀不開" in lines[0]


def test_reader_contract_separates_the_guaranteed_floor_from_the_measured_level() -> None:
    """目標層級**不是常數**：floor 是不靠使用者設定就成立的那一半，observed 由量測來。

    2026-08-16 需求方關掉非刻意開啟的專注模式後推播復活，但那條通道靠一個**可被無聲
    撤銷**的設定（它已經無聲退化過一次），且「有人讀了」永遠是人證。故 floor 維持 3。
    """
    assert sw.READER_CONTRACT["goal_floor"] == 3
    assert "goal" not in sw.READER_CONTRACT, "不得再有一個會被誤讀成常態宣稱的 goal 欄"
    assert "pytest" in sw.READER_CONTRACT["when"]
    assert sw._GOAL_BY_DELIVERY[sw.DELIVERY_PRESENTED] == 2
    assert sw._GOAL_BY_DELIVERY[sw.DELIVERY_SUPPRESSED] == 3
    assert sw._GOAL_BY_DELIVERY[sw.DELIVERY_UNVERIFIED] is None, "查不到時不得宣稱層級"


# ================================================================== 部署錨點
#
# R1 把登記表的 `history_from` 填成**交付日**，並自承那是最弱的一環：部署是 merge
# 之後才發生的另一件事，中間差幾天，那幾天的週期就會被判成一片 MISSING。原本的補救
# 是註解裡寫「部署者記得改成實際安裝日」——但本卡的整個立論就是「靠人記得不算數」，
# 對自己的部署程序當然也一樣。
#
# 改法：把宣告換成量測。下面這組證明錨點真的擋掉了那場誤報洪水，且不會反過來把真
# 缺席也吃掉。


def _repo_without_anchor(tmp_path: Path):
    return _build_repo(tmp_path, [_job("com.cpbl.scrape-daily", DAILY,
                                       effective_from="2026-08-01",
                                       history_from="2026-08-01")], anchor=None)


def test_anchor_is_created_on_first_run_and_then_never_moves(tmp_path: Path) -> None:
    repo, _ = _repo_without_anchor(tmp_path)
    first = datetime(2026, 8, 15, 21, 10, tzinfo=TAIPEI)

    assert sw.deployment_anchor(repo, first) == first.date()
    # 隔天再跑：錨點必須還是第一天，否則判定面會隨時間往前漂、永遠判不到東西
    later = datetime(2026, 8, 20, 21, 10, tzinfo=TAIPEI)
    assert sw.deployment_anchor(repo, later) == first.date()


def test_deploying_late_does_not_produce_a_flood_of_false_missing(tmp_path: Path) -> None:
    """**R1 的病灶本體**：登記表宣告 08-01 生效，但機制其實 08-15 才裝上。

    沒有錨點時，08-01→08-15 這 14 個週期全都沒有歷史 ⇒ 一片 MISSING ⇒ 部署當天噴一
    整串誤報，然後偵測器被關掉（#115 就是死於這個形狀）。
    """
    repo, registry = _repo_without_anchor(tmp_path)
    now = "2026-08-15T21:10:00+0800"

    # 錨點尚未建立 → 第一次執行當場建立成今天 → 不指控任何過去週期
    report = _evaluate(repo, registry, now)
    assert report["exit_code"] == 0, f"部署當天不得誤報：{report['message']}"
    assert report["deployment_anchor"] == "2026-08-15"

    # 負控制：把錨點挪到宣告日，同一份資料就會噴出 MISSING——證明上面那條不是恆真
    (repo / sw.ANCHOR_PATH).write_text(
        json.dumps({"anchor_date": "2026-08-01"}), encoding="utf-8")
    flooded = _evaluate(repo, registry, now)
    assert flooded["exit_code"] == sw.EXIT_MISSING
    assert flooded["jobs"][0]["streak"] > 1, "沒有錨點時本來就該是一整串誤報"


def test_anchor_still_lets_real_absence_through_afterwards(tmp_path: Path) -> None:
    """錨點只擋部署前，不得把部署**之後**的真缺席也吃掉——否則就是換一種形式的失明。"""
    repo, registry = _build_repo(
        tmp_path, [_job("com.cpbl.scrape-daily", DAILY,
                        effective_from="2026-08-01", history_from="2026-08-01")],
        anchor="2026-08-15")

    report = _evaluate(repo, registry, "2026-08-18T21:10:00+0800")

    assert report["exit_code"] == sw.EXIT_MISSING, "錨點之後的缺席仍然要報"


def test_corrupt_anchor_is_rebuilt_as_now_not_treated_as_absent(tmp_path: Path) -> None:
    """錨點檔壞掉不得讓判定面突然放寬（那會在最不該的時候噴誤報）。"""
    repo, _ = _repo_without_anchor(tmp_path)
    (repo / sw.ANCHOR_PATH).parent.mkdir(parents=True, exist_ok=True)
    (repo / sw.ANCHOR_PATH).write_text("{ not json", encoding="utf-8")
    now = datetime(2026, 8, 15, 21, 10, tzinfo=TAIPEI)

    assert sw.deployment_anchor(repo, now) == now.date()


def test_floor_takes_the_latest_of_all_three_bounds() -> None:
    """下界＝max(effective_from, history_from, anchor)，三者任一為 None ⇒ 不判。"""
    job = {"effective_from": "2026-08-01", "history_from": "2026-08-05"}
    from datetime import date as _date

    assert sw._floor(job, _date(2026, 8, 10)) == _date(2026, 8, 10)   # anchor 最晚
    assert sw._floor(job, _date(2026, 8, 2)) == _date(2026, 8, 5)     # history 最晚
    assert sw._floor(job, None) is None                               # 錨點拿不到 ⇒ 不判
    assert sw._floor({"effective_from": None, "history_from": "2026-08-05"},
                     _date(2026, 8, 10)) is None


def test_boots_before_the_deployment_anchor_are_not_runatload_failures(tmp_path: Path) -> None:
    """RunAtLoad 檢查必須與 `_floor()` 用同一組界線，**含部署錨點**。

    偵測器裝上之前的每一次開機當然都沒有它的紀錄——拿宣告日當下界，那些開機會全部
    被報成「RunAtLoad 未兌現」。這與 history_from 那個病灶是同一個，只是換一個出口；
    修一個不修另一個等於沒修，所以這裡單獨釘一條。
    """
    job = _job("com.cpbl.schedule-watchdog", {"kind": "daily", "hour": 21, "minute": 10},
               effective_from="2026-08-01", history_from="2026-08-01")
    repo, registry = _build_repo(tmp_path, [job], anchor="2026-08-15")
    _write_history(repo, "com.cpbl.schedule-watchdog", [
        _record("2026-08-16T21:10:00+0800", "succeeded", exit_code=0),
    ])
    before = datetime(2026, 8, 10, 8, 0, tzinfo=TAIPEI)   # 部署前開機，當然沒有紀錄
    after = datetime(2026, 8, 16, 8, 0, tzinfo=TAIPEI)    # 部署後開機，也沒有紀錄

    only_before = _evaluate(repo, registry, "2026-08-16T21:10:00+0800", boots=[before])
    assert "RUNATLOAD_NOT_HONORED" not in _verdicts(only_before), (
        "部署前的開機被報成 RunAtLoad 未兌現＝誤報洪水的另一個出口")

    # 負控制：錨點**之後**的同一種開機仍然要被抓——否則上一句只是把檢查關掉了
    with_after = _evaluate(repo, registry, "2026-08-16T21:10:00+0800", boots=[after])
    assert "RUNATLOAD_NOT_HONORED" in _verdicts(with_after)



# ======================================= predicate 缺陷：presented 曾經結構上不可達
#
# 跨家族查核在 R2 抓到：`Presenting` 是 **usernoted** 發的，而 R2 的 predicate 只查
# `donotdisturbd OR NotificationCenter`——**把自己註解裡記下的那一行，用七行之後的
# predicate 濾掉了**。實測（同一則通知、同一時間窗）：舊 predicate 找到 0 筆，
# 加上 usernoted 找到 1 筆。


def test_predicate_must_include_usernoted_or_presented_is_unreachable() -> None:
    """`Presenting` 與帶 uuid 的 `Record` 都由 usernoted 發出；沒有它就無法關聯，
    presented 也永遠判不到。"""
    assert 'process == "usernoted"' in sw._LOG_PREDICATE


def test_mutation_dropping_usernoted_from_the_predicate_kills_the_verdict(
    monkeypatch,
) -> None:
    """**變異檢驗**：把 usernoted 的行從查詢結果拿掉，presented 必須消失。

    舊 predicate 的效果就是「看不到 usernoted 的行」，故直接濾掉即可模擬。
    ⚠️ 連 peer 行也會一起不見 ⇒ 連關聯都建立不起來，判定退回 unverified。
    """
    full = _log(4242, "D1DCEC63", tail_lines=[_resolution_line("none")])

    _patch_notify(monkeypatch, pid=4242, log_out=full)
    assert sw.notify("t", "m")["delivered"] == sw.DELIVERY_PRESENTED

    without_usernoted = "\n".join(
        ln for ln in full.decode().splitlines() if "usernoted[" not in ln).encode()
    _patch_notify(monkeypatch, pid=4242, log_out=without_usernoted)
    mutated = sw.notify("t", "m")

    assert mutated["delivered"] == sw.DELIVERY_UNVERIFIED
    assert mutated["delivered"] != sw.DELIVERY_PRESENTED, (
        "舊 predicate 下仍判得出 presented ⇒ 這條變異檢驗是空的")


def test_mutation_ignoring_the_muted_line_would_flip_suppressed_to_presented(
    monkeypatch,
) -> None:
    """`muted by …` 必須優先於裁決行讀。

    實測 2026-08-15 13:23:29：`muted by display state (displayShared)` 與
    `Resolved … as delay` 同時出現；若只讀裁決行也還好，但若把 muted 行忽略、
    又剛好裁決行缺席（本 case），就會退回 unverified 而不是誤判 presented——
    這條釘住「muted 行本身足以定案」。
    """
    _patch_notify(monkeypatch, pid=4242,
                  log_out=_log(4242, "B2B7584D",
                               tail_lines=[_muted_line("display state (displayShared)")]))
    assert sw.notify("t", "m")["delivered"] == sw.DELIVERY_SUPPRESSED

    # 負控制：拿掉 muted 行、也沒有裁決行 ⇒ 只剩 Presenting ⇒ 必須是 unverified
    _patch_notify(monkeypatch, pid=4242, log_out=_log(4242, "B2B7584D"))
    assert sw.notify("t", "m")["delivered"] == sw.DELIVERY_UNVERIFIED



def test_anchor_floor_behaves_across_the_day_boundary(tmp_path: Path) -> None:
    """跨日回歸：錨點是「昨天」時，判定窗必須正常前進，且不得補判部署前的週期。

    2026-08-16 這天正好是真實的跨日機會——登記表的 `history_from` 與部署錨點都變成
    「昨天」。這條把當時實測的三個時點釘住，避免日後改動在日界線上出現 off-by-one。
    """
    job = _job("com.cpbl.schedule-watchdog", {"kind": "daily", "hour": 21, "minute": 10},
               effective_from="2026-08-15", history_from="2026-08-15")
    repo, registry = _build_repo(tmp_path, [job], anchor="2026-08-15")
    # 08-15 21:10 那一輪有紀錄且成功；08-14（部署前）當然沒有
    _write_history(repo, "com.cpbl.schedule-watchdog", [
        _record("2026-08-15T21:10:00+0800", "succeeded", exit_code=0),
    ])

    # 隔天早上：F1=08-14 在錨點之前 ⇒ 不得被判 MISSING
    morning = _evaluate(repo, registry, "2026-08-16T10:30:00+0800")
    assert morning["exit_code"] == 0, f"跨日後補判了部署前的週期：{morning['message']}"

    # 隔天 21:10：F1=08-15 已在錨點之後且有成功紀錄 ⇒ 仍然安靜
    evening = _evaluate(repo, registry, "2026-08-16T21:10:00+0800")
    assert evening["exit_code"] == 0

    # 負控制：把 08-15 那筆紀錄拿掉，同一個時點就必須報 MISSING——
    # 證明上面兩條不是因為判定窗整個空掉才安靜的
    (repo / "logs" / "schedule-history" / "com.cpbl.schedule-watchdog.jsonl").unlink()
    naked = _evaluate(repo, registry, "2026-08-16T21:10:00+0800")
    assert naked["exit_code"] == sw.EXIT_MISSING
