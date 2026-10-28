"""#358 WP4：schedule-watchdog 對外部告警登記與設定的判定。

放在獨立檔而不是 `tests/test_schedule_watch.py` 尾端：那一檔的尾端也是 #366／PR #371 revert 的
範圍，另起一檔避免讓 revert 多一個衝突（規劃 2 §6）。沿用該檔的假 repo 工具。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.test_schedule_watch import (
    DAILY,
    REAL_REGISTRY,
    _build_repo,
    _job,
    _record,
    _verdicts,
    _write_history,
    sw,
)

# ------------------------------------------- #358：外部告警的登記與設定（WP4）

def _alert_daily_job(**alert_overrides) -> dict:
    job = _job("com.cpbl.daily", DAILY)
    job["alert"] = {"channel": "healthchecks", "check": "daily", "schedule": "10 10 * * *",
                    "tz": "Asia/Taipei", "grace_minutes": 50, "deadline": "11:00", **alert_overrides}
    return job


def _healthy_history(repo: Path) -> None:
    _write_history(repo, "com.cpbl.daily", [
        _record("2026-08-14T10:10:00+0800", "running"),
        _record("2026-08-14T10:40:00+0800", "succeeded", exit_code=0),
        _record("2026-08-15T10:10:00+0800", "running"),
        _record("2026-08-15T10:40:00+0800", "succeeded", exit_code=0),
    ])


def _evaluate_alert(repo: Path, registry: dict, missing: list, probe=None) -> dict:
    return sw.evaluate(registry, repo, sw.parse_timestamp("2026-08-15T21:10:00+0800"), "none", 1.0, 60,
                       installed_probe=lambda _l: True, listing_probe=lambda: [],
                       boot_probe=lambda: [],
                       alert_probe=probe or (lambda _repo, _need_api: list(missing)))


def test_declared_alert_without_keys_is_reported_not_healthy(tmp_path: Path) -> None:
    """規劃 1 §3.3：金鑰缺席時 hook 不動作，但 watchdog 不得把「沒設定」當健康。"""
    repo, registry = _build_repo(tmp_path, [_alert_daily_job()])
    _healthy_history(repo)
    report = _evaluate_alert(repo, registry, ["CPBL_HC_PING_KEY"])
    assert "ALERT_NOT_CONFIGURED" in _verdicts(report)
    assert report["exit_code"] == sw.EXIT_ALERT_NOT_CONFIGURED
    assert "CPBL_HC_PING_KEY" in report["message"]


def test_configured_alert_is_silent(tmp_path: Path) -> None:
    """負控制：設定齊全時同一個 repo 完全安靜。"""
    repo, registry = _build_repo(tmp_path, [_alert_daily_job()])
    _healthy_history(repo)
    report = _evaluate_alert(repo, registry, [])
    assert report["exit_code"] == sw.EXIT_OK and _verdicts(report) == set()


def test_no_alert_segment_never_probes(tmp_path: Path) -> None:
    """登記表沒宣告告警就不檢查金鑰（既有假 repo 的測試不受影響）。"""
    repo, registry = _build_repo(tmp_path, [_job("com.cpbl.daily", DAILY)])
    _healthy_history(repo)

    def boom(_repo, _need):  # noqa: ANN001
        raise AssertionError("不該被呼叫")

    assert _evaluate_alert(repo, registry, [], probe=boom)["exit_code"] == sw.EXIT_OK


def test_alert_never_outranks_a_real_failure(tmp_path: Path) -> None:
    repo, registry = _build_repo(tmp_path, [_alert_daily_job()])
    _write_history(repo, "com.cpbl.daily", [
        _record("2026-08-15T10:10:00+0800", "failed", exit_code=1, failed_phase="scrape",
                finished="2026-08-15T10:30:00+0800")])
    report = _evaluate_alert(repo, registry, ["CPBL_HC_PING_KEY"])
    assert report["verdict"] == "FAILED"


@pytest.mark.parametrize("overrides", [
    {"schedule": "10 11 * * *"},          # 與 cadence 不符
    {"deadline": "11:40"},                # 門檻與 grace 不符
    {"check": ""},                        # 沒有 check 名
])
def test_alert_segment_drift_is_registry_invalid(tmp_path: Path, overrides: dict) -> None:
    repo, registry = _build_repo(tmp_path, [_alert_daily_job(**overrides)])
    _healthy_history(repo)
    assert "REGISTRY_INVALID" in _verdicts(_evaluate_alert(repo, registry, []))


def test_evening_alert_must_point_at_a_declared_job_and_needs_api_key(tmp_path: Path) -> None:
    job = _alert_daily_job()
    job["evening_alert"] = {"check": "evening", "for": "com.cpbl.nope"}
    repo, registry = _build_repo(tmp_path, [job])
    _healthy_history(repo)
    assert "REGISTRY_INVALID" in _verdicts(_evaluate_alert(repo, registry, []))

    seen = []
    job["evening_alert"]["for"] = "com.cpbl.daily"
    _evaluate_alert(repo, registry, [], probe=lambda _r, need_api: seen.append(need_api) or [])
    assert seen == [True]


def test_default_alert_probe_reads_repo_env_without_values(tmp_path: Path) -> None:
    """預設探針只讀 repo/.env 判有無，不連網；缺 .env 時兩鍵都報缺。"""
    assert sw.alert_settings_missing(tmp_path, True) == ["CPBL_HC_PING_KEY", "CPBL_HC_API_KEY"]
    (tmp_path / ".env").write_text("CPBL_HC_PING_KEY=pk-synthetic\nCPBL_HC_API_KEY=ak-synthetic\n",
                                   encoding="utf-8")
    assert sw.alert_settings_missing(tmp_path, True) == []


def test_shipped_registry_alert_segments_are_consistent() -> None:
    registry = json.loads(REAL_REGISTRY.read_text(encoding="utf-8"))
    assert sw.check_alert_segments(registry) == []
    assert any("alert" in job for job in registry["jobs"])
