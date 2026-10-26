"""#365 驗收 (i)：合併前碼寫出的晚間狀態檔，新碼載入後原樣保留、補上新鍵，未結項照常繼續處理。

fixture＝本機 ``logs/postseason-evening-state.json`` 的副本（2026-10-23 21:09 台北唯讀複製，sha256
4e5143b04f513cf114ca611ef1f97878a9ddd0fcdf96e72cd99dfa84f0d1cec5；25 鍵、version 1）。⛔ 測試只讀副本、
不讀寫現行狀態檔。副本當下沒有未結項（事件全為 synced、box／PA 全為 delivered），下列**構造**只在記憶體做：
* 事件 ``schedule_changed:2026-C-5`` 的 state 改回 ``open``；
* 加一筆 box／PA 紀錄 ``2026-C-5``（game_date 2026-10-25，box 仍缺）；
* 先發時點不構造：用副本真實的 ``schedule``（C5 SCHEDULED 2026-10-25T17:05）與 ``starter_enabled_since``。
"""

from __future__ import annotations

import copy
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from cpbl.ingest import postseason_evening as pe

TPE = ZoneInfo("Asia/Taipei")
FIXTURE = Path(__file__).parent / "fixtures" / "postseason_evening_state_premerge_2026-10-23.json"
RAW = json.loads(FIXTURE.read_text(encoding="utf-8"))
NO_GAME_NIGHT = datetime(2026, 10, 24, 21, 0, tzinfo=TPE)    # C4（10-21）與 C5（10-25）之間的休息日


def loaded(tmp_path: Path) -> dict:
    path = tmp_path / "state.json"
    path.write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
    return pe.load_state(path)


def test_pre_merge_state_file_is_carried_forward(tmp_path):
    state = loaded(tmp_path)
    assert len(RAW) == 25 and RAW["version"] == 1
    for key, value in RAW.items():
        assert state[key] == value, key
    new = set(pe.empty_state()) - set(RAW)
    # #342 另加 starter_watch（先發觀察窗；空 dict＝尚無紀錄）。
    assert new == {"gate", "a_fetch_gate", "night_backup", "backup_uses", "a_stats_rows", "starter_watch"}
    assert {k: state[k] for k in new} == {"gate": None, "a_fetch_gate": None, "night_backup": None,
                                         "backup_uses": [], "a_stats_rows": None, "starter_watch": {}}
    assert pe.backup_plan(state, NO_GAME_NIGHT) == ("backup", "", ""), "沒有 night_backup ⇒ 第一次同步照常備份"


def _with_open_items(state: dict) -> dict:
    state = copy.deepcopy(state)
    state["events"]["schedule_changed:2026-C-5"]["state"] = "open"          # 構造
    state["boxpa"]["2026-C-5"] = {"key": "2026-C-5", "game_date": "2026-10-25", "state": "open", "reason": None,
                                  "detail_attempts": [], "tracking_attempts": [], "sends": [], "manifest": None,
                                  "final_prod_at": None,
                                  "sources": {"box": {"reason": "local_box_incomplete:game_livelog"}}}  # 構造
    return state


def test_open_items_keep_the_chain_running_and_are_processed(tmp_path):
    base = loaded(tmp_path)
    no_games = lambda night: set()  # noqa: E731
    assert pe.evening_gate(base, NO_GAME_NIGHT, None, db_lookup=no_games)[0] == "quiet", "前提：副本本身無待辦"
    state = _with_open_items(base)
    decision, reason, kinds = pe.evening_gate(state, NO_GAME_NIGHT, None, db_lookup=no_games)
    assert decision == "fallback_db" and kinds == ("C",) and "open_events" in reason, reason
    probed = []
    schedule = [pe.StatsGame(**g) for g in state["schedule"]]
    pe.plan(state, NO_GAME_NIGHT, probe=lambda: probed.append(1) or schedule, load_local=lambda: {})
    assert probed == [1], "未結事件照常讀 stats"
    at_c5 = datetime(2026, 10, 25, 21, 0, tzinfo=TPE)
    recs = pe.boxpa_refresh(state, at_c5, {}, {})
    assert "2026-C-5" in recs and state["boxpa"]["2026-C-5"]["state"] == "open", "未結 box／PA 繼續處理"
    assert state["boxpa"]["2026-C-4"]["state"] == "delivered", "舊的已送達紀錄不被改動"
    # 先發時點：副本的旗標開啟起點（starter_enabled_since）沿用；上面的 plan 以旗標關呼叫會清掉起點，故另取一份。
    fresh = _with_open_items(base)
    due = pe.refresh_starter_checkpoints(fresh, datetime(2026, 10, 25, 16, 6, tzinfo=TPE), True)
    assert "2026-C-5|S-60|2026-10-25T09:05:00+00:00" in due, "先發時點到點後照常 due"
