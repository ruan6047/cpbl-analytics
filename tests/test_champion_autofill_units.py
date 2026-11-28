"""#469 規劃修訂 r2：``ops/vps/`` 冠軍補列 systemd unit 的靜態契約（不安裝、不連 VPS）。

鎖住：ExecStart 是不 migrate 的新入口、在 ``prod_cpbl_api`` 內執行；每日一次、時刻避開 #393 VPS
每日 11:10 與週一 13:10（WP0 實測 ``cpbl393-vps-season-daily.timer``／``cpbl393-vps-weekly-pitches.timer``）；
``Persistent=true``；timer 指向同名 service。
"""

from __future__ import annotations

import configparser
import re
import tomllib
from datetime import datetime, timedelta
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
UNIT_DIR = REPO_ROOT / "ops" / "vps"
SERVICE = UNIT_DIR / "cpbl469-champion-autofill.service"
TIMER = UNIT_DIR / "cpbl469-champion-autofill.timer"

EXPECTED_EXEC = "/usr/bin/docker exec prod_cpbl_api cpbl-champion-autofill"
# #393 VPS lane 的既有觸發時刻（Asia/Taipei）：每日 11:10、週一 13:10。
BUSY = (("*", "11:10"), ("Mon", "13:10"))
MIN_GAP = timedelta(minutes=30)


class _UnitParser(configparser.ConfigParser):
    def optionxform(self, optionstr: str) -> str:  # systemd 鍵大小寫有意義
        return optionstr


def _unit(path: Path) -> configparser.ConfigParser:
    parser = _UnitParser(interpolation=None, strict=True)
    parser.read_string(path.read_text(encoding="utf-8"))
    return parser


def test_service_execs_the_no_migrate_entry_inside_the_api_container():
    svc = _unit(SERVICE)
    assert svc["Service"]["Type"] == "oneshot"
    assert svc["Service"]["ExecStart"] == EXPECTED_EXEC
    text = SERVICE.read_text(encoding="utf-8")
    assert "migrate" not in text.split("[Service]", 1)[1]
    assert "cpbl-build-championships" not in text


def test_exec_command_is_a_declared_console_script_of_the_entry_module():
    command = EXPECTED_EXEC.split()[-1]
    scripts = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["scripts"]
    assert scripts[command] == "cpbl.ingest.run_champion_autofill:main"


def test_timer_targets_the_service_and_is_persistent():
    tmr = _unit(TIMER)["Timer"]
    assert tmr["Unit"] == SERVICE.name
    assert tmr["Persistent"] == "true"
    assert _unit(TIMER)["Install"]["WantedBy"] == "timers.target"


def _on_calendar() -> tuple[str, str]:
    value = _unit(TIMER)["Timer"]["OnCalendar"]
    m = re.fullmatch(r"(?:(Mon|Tue|Wed|Thu|Fri|Sat|Sun) )?\*-\*-\* (\d{2}):(\d{2}):00 Asia/Taipei", value)
    assert m, f"OnCalendar 必須是每日固定時刻且明寫 Asia/Taipei：{value!r}"
    return (m.group(1) or "*"), f"{m.group(2)}:{m.group(3)}"


def test_timer_runs_daily_in_taipei_time():
    weekday, _ = _on_calendar()
    assert weekday == "*", "必須每天跑（一週內補上靠每日重試）"


@pytest.mark.parametrize(("busy_day", "busy_at"), BUSY)
def test_timer_keeps_clear_of_393_vps_lane(busy_day, busy_at):
    _, at = _on_calendar()
    ours = datetime.strptime(at, "%H:%M")
    theirs = datetime.strptime(busy_at, "%H:%M")
    assert abs(ours - theirs) >= MIN_GAP, f"{at} 與 #393 {busy_day} {busy_at} 相距不足 {MIN_GAP}"
