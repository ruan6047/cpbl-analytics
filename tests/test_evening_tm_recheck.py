"""#365 S5（驗收 g）：P-TM-RECHECK（首見完賽後 45 分再抓一次逐球）與「晚間鏈沒有 leaderboard 重抓」。

錨點取本機晚間狀態檔（副本）的真實 F（``finished_first_seen.finished_at``）：
* 2026-C-4：2026-10-21T14:19:21.026446+00:00（台北 22:19:21；當晚結果同步 22:22，見規劃 3 §5.4 B 段樣本）。
* 2026-C-3：2026-10-20T13:24:58.177196+00:00（台北 21:24:58），配 tests/test_boxpa_tracking_late.py 的 G3 真實樣本
  （21:47:27 明細、21:49:53 box＋PA 送達）。
⚠️ 規劃 3 §4.1 (g) 寫「E4 的真實 F」，但狀態檔的 E4 是舊版字串（首見完賽 10-15，沒有曾見未完賽的證據），不是 F；
改用 C4／C3（偏離理由見 #365 執行報告）。
"""

from __future__ import annotations

import ast
import dataclasses
import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from cpbl.ingest import postseason_evening as pe
from tests.test_boxpa_tracking_late import G3, KEY, World, at
from tests.test_postseason_evening_sync import EVENING
from tests.test_schedule_watch import REAL_REGISTRY

C4_F = datetime.fromisoformat("2026-10-21T14:19:21.026446+00:00")
NOT_LAGGING = dataclasses.replace(G3, tracking_lagging=False)
C3_FINISHED = {"finished_at": "2026-10-20T13:24:58.177196+00:00",
               "last_unfinished_at": "2026-10-20T13:19:38.701788+00:00"}


def test_tm_recheck_param_default_and_due_boundaries(monkeypatch):
    monkeypatch.delenv("POSTSEASON_TM_RECHECK_MIN", raising=False)
    assert pe.tm_recheck_minutes() == 45
    assert pe.tm_recheck_due(C4_F, C4_F + timedelta(minutes=44), 45, done=False) is False
    assert pe.tm_recheck_due(C4_F, C4_F + timedelta(minutes=45), 45, done=False) is True
    assert pe.tm_recheck_due(C4_F, C4_F + timedelta(minutes=45), 45, done=True) is False
    assert pe.tm_recheck_due(None, C4_F + timedelta(days=1), 45, done=False) is False
    monkeypatch.setenv("POSTSEASON_TM_RECHECK_MIN", "30")
    assert pe.tm_recheck_minutes() == 30
    state = {"finished_first_seen": {"2026-C-4": {"finished_at": C4_F.isoformat(), "last_unfinished_at": "x"}}}
    rec = {"key": "2026-C-4", "detail_attempts": ["2026-10-21T14:21:40+00:00"], "tracking_attempts": []}
    assert pe.boxpa_tm_recheck_due(state, rec, C4_F + timedelta(minutes=29)) is False
    assert pe.boxpa_tm_recheck_due(state, rec, C4_F + timedelta(minutes=30)) is True


@pytest.mark.parametrize("bad", ["0", "-1", "abc", "4.5"])
def test_tm_recheck_param_refuses_non_positive_integers_with_exit_64(monkeypatch, tmp_path, bad):
    monkeypatch.setenv("POSTSEASON_TM_RECHECK_MIN", bad)
    monkeypatch.setenv("POSTSEASON_STATE", str(tmp_path / "state.json"))
    with pytest.raises(ValueError):
        pe.tm_recheck_minutes()
    assert pe.main(["boxpa-status"]) == 64


def test_anchor_falls_back_to_first_seen_and_legacy_strings():
    state = {"finished_first_seen": {
        "2026-C-4": {"finished_at": None, "last_unfinished_at": None,
                     "first_seen_finished_at": C4_F.isoformat()},
        "2026-E-4": "2026-10-15T10:25:28.793144+00:00",      # 狀態檔真實舊版字串
        "2026-C-5": {"finished_at": None, "last_unfinished_at": "2026-10-23T09:57:05+00:00"}}}
    assert pe.tm_anchor(state, "2026-C-4") == C4_F
    assert pe.tm_anchor(state, "2026-E-4") == datetime.fromisoformat("2026-10-15T10:25:28.793144+00:00")
    assert pe.tm_anchor(state, "2026-C-5") is None, "尚未完賽：沒有錨點"


def test_tm_recheck_reopens_a_delivered_game_and_only_touches_stats():
    """G3 真實樣本（既有覆蓋判準判不落後時，21:49 即送達，見 test_venue_without_recent_equipment…）：
    首見完賽 21:24:58＋45 分＝22:09:58 才再抓一次逐球（boxpa-tracking：只打 stats、不寫 www 帳本、
    不佔明細額度）；抓過後回送達，不重複抓。"""
    fetched = []
    w = World(NOT_LAGGING, tracking=lambda f: fetched.append("tracking") or f)
    pe._boxpa_rec(w.state, KEY, "2026-10-20")["detail_attempts"].append("2026-10-20T13:47:27.606400+00:00")
    w.state["finished_first_seen"] = {KEY: C3_FINISHED}
    assert w.run_wake(at(21, 49)) == "sync"
    assert w.rec["state"] == "delivered"
    before_www, before_detail = dict(w.state["www_requests"]), list(w.rec["detail_attempts"])
    assert w.run_wake(at(22, 9)) == "precheck_exit", "F+44 分不到期"
    assert w.run_wake(at(22, 10)) == "tracking", "F+45 分到期"
    assert fetched == ["tracking"]
    assert w.state["www_requests"] == before_www and w.rec["detail_attempts"] == before_detail
    assert w.rec["state"] == "delivered", "逐球沒變：照原分類回送達（不新增同步）"
    assert w.syncs == [["box", "pa"]]
    assert w.run_wake(at(22, 30)) == "precheck_exit", "做過一次就不再到期"


def test_tm_recheck_outside_the_target_window_does_nothing():
    """過了隔日 09:45 的場不重開（交每日鏈）；舊的已送達紀錄不因 TM 參數回頭重開。"""
    w = World(NOT_LAGGING)
    pe._boxpa_rec(w.state, KEY, "2026-10-20")["detail_attempts"].append("2026-10-20T13:47:27.606400+00:00")
    w.state["finished_first_seen"] = {KEY: C3_FINISHED}
    w.run_wake(at(21, 49))
    pe.boxpa_refresh(w.state, at(10, 0, day=21), {}, {KEY: w.facts})
    assert w.rec["state"] == "delivered"


# =========================================================== 晚間鏈沒有 leaderboard／進階重抓（grep 0 命中）

FORBIDDEN = ("LB_RECHECK", "P-LB-RECHECK", "cpbl_advanced", "scrape_advanced", "sync_advanced_snapshot",
             "leaderboard")


def forbidden_hits(text: str) -> list[str]:
    low = text.lower()
    return [w for w in FORBIDDEN if w.lower() in low]


def _evening_sources() -> dict[str, str]:
    registry = json.loads(REAL_REGISTRY.read_text(encoding="utf-8"))
    (entry,) = [j for j in registry["jobs"] if j["label"] == "com.cpbl.postseason-evening"]
    plist = REAL_REGISTRY.parents[1] / entry["plist"]
    return {Path(pe.__file__).name: Path(pe.__file__).read_text(encoding="utf-8"),
            EVENING.name: EVENING.read_text(encoding="utf-8"),
            plist.name: plist.read_text(encoding="utf-8"),
            "registry:com.cpbl.postseason-evening": json.dumps(entry, ensure_ascii=False)}


def test_no_leaderboard_recheck_anywhere_in_the_evening_chain():
    """Q2＝甲（需求方裁定 #343 6361673244 第 2 項）：P-LB-RECHECK 刪除，晚間鏈不得出現進階／leaderboard 抓取。"""
    sources = _evening_sources()
    assert len(sources) == 4
    for name, text in sources.items():
        assert forbidden_hits(text) == [], name
    tree = ast.parse(sources[Path(pe.__file__).name])
    imported = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
    imported |= {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    imported |= {f"{n.module}.{a.name}" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module
                 for a in n.names}
    assert not any("cpbl_advanced" in m for m in imported), sorted(imported)


def test_forbidden_word_check_is_not_vacuous():
    """負控：同一支檢查對含 POSTSEASON_LB_RECHECK_MIN 的字串必須命中（證明檢查不是空的）。"""
    assert forbidden_hits('os.environ.get("POSTSEASON_LB_RECHECK_MIN")') == ["LB_RECHECK"]
    assert forbidden_hits("from cpbl.ingest.cpbl_advanced import scrape_advanced_result") == [
        "cpbl_advanced", "scrape_advanced"]
    assert forbidden_hits("E／C Leaderboard 重抓") == ["leaderboard"]
