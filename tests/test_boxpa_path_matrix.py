"""#293 fix-3：晚間鏈 box／PA 路徑組合矩陣（plan →（detail）→ PA build → 再 plan → sync）。

連續三輪「修正帶出新回歸」都出在這條路徑的組合上，本檔把組合逐一鎖住。驅動器照
``scripts/postseason-evening.sh`` 的實際次序呼叫真狀態機（``boxpa_refresh``／``boxpa_plan``／
``boxpa_pa_build_candidates``／``boxpa_record_sync``）；只有 www 明細、PA builder 與 scoped 同步是替身：

* builder 替身只在被呼叫時依情境改本機事實（publish、republish 新 build、或保留 published＋記
  reconciliation_required）——「有沒有被呼叫」本身就是被測的接線（再審 G1）；
* scoped 同步替身依 parts 產生 manifest（本機＝production，code 0）。

底層事實是真實 2026 E4 快照（``tests/fixtures/postseason_sources_2026_real.json``），時刻放在賽事日晚上。
這些是狀態機情境，⛔ 不是真實當晚事件的證據。
"""

from __future__ import annotations

import dataclasses
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from cpbl import postseason_sources as ps
from cpbl.ingest import postseason_evening as pe

TPE = ZoneInfo("Asia/Taipei")
KEY = "2026-E-4"
FIXTURE = Path(__file__).parent / "fixtures" / "postseason_sources_2026_real.json"
LOCAL = {KEY: pe.LocalGame(2026, "E", 4, "2026-10-12", "ADD011", "ACN011", "洲際", True)}


def real() -> ps.LocalFacts:
    return ps.facts_from_json(json.loads(FIXTURE.read_text(encoding="utf-8"))["games"][KEY])


FULL = real()
NO_PA = dataclasses.replace(FULL, published_build=None, published_at=None,
                            pa_counts={t: 0 for t in FULL.pa_counts})
BOX_MISSING = dataclasses.replace(NO_PA, box_counts={**FULL.box_counts, "game_livelog": 0})


def at(hh, mm, day=12):
    return datetime(2026, 10, day, hh, mm, tzinfo=TPE)


class World:
    """一場比賽的本機事實＋各替身；``run_wake`` 照 shell 次序跑一次喚醒。"""

    def __init__(self, facts, *, builder=None, detail=None):
        self.facts = facts
        self.state = pe.empty_state()
        self.builder = builder or (lambda f: f)          # PA builder 替身：回傳 build 後的事實
        self.detail = detail or (lambda f: f)            # www 明細替身
        self.builder_calls: list[list[str]] = []
        self.syncs: list[list[str]] = []
        self.prechecks: list[str] = []

    def _plan(self, now):
        recs = pe.boxpa_refresh(self.state, now, LOCAL, {KEY: self.facts})
        return recs, pe.boxpa_plan(self.state, now, recs)

    def run_wake(self, now):
        # shell 1b 預檢：`boxpa-plan --dry` 不取鎖、不寫狀態檔；結果鏈 idle 時只有 detail／sync／build 會進鎖。
        import copy
        dry = copy.deepcopy(self.state)
        dry_recs = pe.boxpa_refresh(dry, now, LOCAL, {KEY: self.facts})
        dry_action = pe.boxpa_plan(dry, now, dry_recs)[0]
        self.prechecks.append(dry_action)
        if dry_action not in ("detail", "sync", "build"):
            return "precheck_exit"
        recs, (action, keys, parts) = self._plan(now)
        if action == "detail":
            pe.boxpa_record_detail(self.state, now, keys, [])
            self.facts = self.detail(self.facts)
        if action in ("detail", "build", "sync"):
            recs = pe.boxpa_refresh(self.state, now, LOCAL, {KEY: self.facts})
            cands = pe.boxpa_pa_build_candidates(recs)      # = boxpa-prepare（無 --games）
            self.builder_calls.append(cands)
            if KEY in cands:
                self.facts = self.builder(self.facts)
            recs, (action, keys, parts) = self._plan(now)
        if action == "sync" and parts:
            self.syncs.append(list(parts))
            m = manifest(self.facts, now, parts)
            pe.boxpa_refresh(self.state, now, LOCAL, {KEY: self.facts})
            pe.boxpa_record_sync(self.state, now, keys, 0, m, 30.0, parts)
            pe.boxpa_refresh(self.state, now, LOCAL, {KEY: self.facts})
        return action

    @property
    def rec(self):
        return self.state["boxpa"][KEY]

    @property
    def pa(self):
        return self.rec["sources"]["pa"]

    @property
    def box(self):
        return self.rec["sources"]["box"]


def manifest(f: ps.LocalFacts, now: datetime, parts) -> dict:
    pa_sent = "pa" in parts and f.published_build is not None
    return {"at": now.isoformat(), "games": {KEY: {
        "box_ok": True if "box" in parts else None, "pa_ok": True if pa_sent else None, "pa_sent": pa_sent,
        "box": {t: {"local": n, "prod": n} for t, n in f.box_counts.items()},
        "pa": {t: {"local": n, "prod": n} for t, n in f.pa_counts.items()},
        "published_build_local": f.published_build if pa_sent else None,
        "published_build_prod": f.published_build if pa_sent else None}}}


def publish(f):
    return dataclasses.replace(f, published_build=FULL.published_build, published_at=FULL.published_at,
                               pa_counts=dict(FULL.pa_counts))


def republish(build_id):
    def go(f):
        return dataclasses.replace(f, published_build=build_id, published_at=f.published_at)
    return go


def correction(f):
    """既有 builder 對 livelog 變動的處置：保留舊 published、記 reconciliation_required。"""
    return dataclasses.replace(f, reconciliation_outstanding=1)


# ------------------------------------------------------------------ 組合

def test_m1_normal_box_ready_pa_built_same_wake_one_sync():
    w = World(NO_PA, builder=publish)
    w.run_wake(at(22, 0))
    assert w.syncs == [["box", "pa"]] and w.builder_calls == [[KEY]]
    assert w.run_wake(at(22, 5)) == "precheck_exit"
    assert w.rec["state"] == "delivered" and w.pa["same_night"] is True


def test_m2_box_missing_detail_then_build_then_one_sync():
    w = World(BOX_MISSING, detail=lambda f: dataclasses.replace(f, box_counts=dict(FULL.box_counts)),
              builder=publish)
    w.run_wake(at(22, 0))
    assert w.syncs == [["box", "pa"]], "明細到齊、build、同步都在同一次喚醒"
    assert len(w.rec["detail_attempts"]) == 1


def test_m3_box_missing_and_detail_still_missing_never_builds_or_syncs():
    w = World(BOX_MISSING, builder=lambda f: pytest.fail("box 未到齊不得 build"))
    w.run_wake(at(22, 0))
    assert w.syncs == [] and w.builder_calls == [[]]


def test_m4_pa_not_published_first_then_later_two_syncs():
    calls = {"n": 0}

    def late(f):
        calls["n"] += 1
        return publish(f) if calls["n"] >= 2 else f
    w = World(NO_PA, builder=late)
    w.run_wake(at(22, 0))
    assert w.syncs == [["box"]] and w.pa["reason"] == "no_local_published_build"
    assert w.run_wake(at(22, 5)) == "sync"
    assert w.syncs == [["box"], ["pa"]]
    assert w.run_wake(at(22, 10)) == "precheck_exit" and w.rec["state"] == "delivered"


def test_m5_pa_never_published_keeps_building_without_syncing_then_handed_to_daily():
    w = World(NO_PA)
    w.run_wake(at(22, 0))
    for t in (at(22, 5), at(23, 0)):
        assert w.run_wake(t) == "build", "每次喚醒都再交給 builder，但不同步"
    assert w.syncs == [["box"]] and all(c == [KEY] for c in w.builder_calls)
    pe.boxpa_refresh(w.state, at(10, 20, day=13), LOCAL, {KEY: w.facts})
    assert (w.rec["state"], w.rec["reason"]) == ("unreached", "handed_to_daily_chain")
    assert w.pa["same_night"] is False


def test_m6_g1_delivered_then_box_update_with_correction_rebuilds_and_keeps_pa_pending():
    """再審 G1：已 published 的場 box 更新 → 重開 → builder **必須被呼叫** → 官方更正照實待收尾。"""
    w = World(NO_PA, builder=publish)
    w.run_wake(at(21, 30))
    assert w.rec["state"] == "delivered" or w.run_wake(at(21, 35)) == "precheck_exit"
    w.builder = correction
    w.facts = dataclasses.replace(w.facts, box_counts={**w.facts.box_counts, "game_livelog": 356})
    w.run_wake(at(22, 0))
    assert w.builder_calls[-1] == [KEY], "已有 published 的場也要交給 builder"
    assert w.syncs == [["box", "pa"], ["box"]]
    assert (w.pa["status"], w.pa["reason"]) == ("pending_update", "official_correction_pending")
    assert w.run_wake(at(22, 10)) == "precheck_exit" and len(pe.boxpa_syncs(w.rec)) == 2


def test_m7_delivered_then_tracking_late_republish_goes_with_box_in_one_sync():
    w = World(NO_PA, builder=publish)
    w.run_wake(at(21, 30))
    w.builder = republish("33333333-3333-3333-3333-333333333333")
    w.facts = dataclasses.replace(w.facts, box_counts={**w.facts.box_counts, "pitch_tracking": 340})
    w.run_wake(at(22, 0))
    assert w.syncs == [["box", "pa"], ["box", "pa"]], "republish 的 PA 與更新的 box 同一次送"
    assert w.run_wake(at(22, 5)) == "precheck_exit"
    assert w.pa["status"] == "delivered" and w.rec["state"] == "delivered"


def test_m8_new_published_alone_after_delivery_sends_only_pa():
    w = World(NO_PA, builder=publish)
    w.run_wake(at(21, 30))
    w.builder = lambda f: f
    w.facts = dataclasses.replace(w.facts, published_build="44444444-4444-4444-4444-444444444444")
    w.run_wake(at(22, 0))
    assert w.syncs == [["box", "pa"], ["pa"]]


def test_m9_quota_exhausted_then_box_update_still_builds_but_no_third_sync():
    w = World(NO_PA, builder=publish)
    w.run_wake(at(21, 30))
    w.facts = dataclasses.replace(w.facts, box_counts={**w.facts.box_counts, "game_livelog": 356})
    w.run_wake(at(21, 40))
    assert len(w.syncs) == 2
    w.builder = correction
    w.facts = dataclasses.replace(w.facts, box_counts={**w.facts.box_counts, "game_livelog": 357})
    assert w.run_wake(at(22, 0)) == "build"
    assert len(w.syncs) == 2, "以場計：不得有第 3 次"
    assert w.builder_calls[-1] == [KEY], "額度用完也照常 build，分類照實"
    assert w.pa["reason"] == "official_correction_pending"
    assert w.box["reason"] == "local_changed_since_sync" and w.rec["state"] == "open", "box 新版未送：照實待更新"
    pe.boxpa_refresh(w.state, at(10, 20, day=13), LOCAL, {KEY: w.facts})
    assert (w.rec["state"], w.rec["reason"]) == ("unreached", "handed_to_daily_chain")


def test_m10_correction_before_first_sync_sends_old_published_and_marks_pending():
    w = World(dataclasses.replace(FULL, reconciliation_outstanding=0), builder=correction)
    w.run_wake(at(22, 0))
    assert w.syncs == [["box", "pa"]]
    assert w.pa["reason"] == "official_correction_pending"
    assert w.run_wake(at(22, 5)) == "precheck_exit"


def test_candidates_are_all_open_box_ready_games_regardless_of_published():
    state = pe.empty_state()
    recs = pe.boxpa_refresh(state, at(22, 0), LOCAL, {KEY: FULL})
    assert pe.boxpa_pa_build_candidates(recs) == [KEY]
    recs = pe.boxpa_refresh(pe.empty_state(), at(22, 0), LOCAL, {KEY: BOX_MISSING})
    assert pe.boxpa_pa_build_candidates(recs) == []


# ------------------------------------------------------------------ fix-4：已送達／額度用完後才更新（B1）
#
# 需求方裁定 6204889879（「本機記『更正待同步』」）：仍呼叫本機 PA builder、狀態記更正待同步／待更新，
# ⛔ 不再同步 production、⛔ 不超過 A3 以場計上限，隔日 10:10 每日鏈補上；不得停在「已送達」。

def _two_syncs_box_box(w):
    """21:30 box＋pa → 21:35 無更新（轉 delivered）→ 21:40 livelog 更新只送 box（第 2 次）。"""
    w.run_wake(at(21, 30))
    w.run_wake(at(21, 35))
    assert w.rec["state"] == "delivered"
    w.facts = dataclasses.replace(w.facts, box_counts={**w.facts.box_counts, "game_livelog": 356})
    w.run_wake(at(21, 40))
    assert w.syncs == [["box", "pa"], ["box"]]


def _assert_pending_until_daily(w):
    assert len(w.syncs) == 2, "A3 以場計：沒有第 3 次 production 同步"
    assert w.builder_calls[-1] == [KEY], "本機 PA builder 仍被呼叫"
    assert w.rec["state"] == "open" and w.rec["reason"] == "source_changed_after_quota"
    assert w.box["reason"] == "local_changed_since_sync"
    assert w.pa["reason"] == "official_correction_pending"
    pe.boxpa_refresh(w.state, at(10, 20, day=13), LOCAL, {KEY: w.facts})
    assert (w.rec["state"], w.rec["reason"]) == ("unreached", "handed_to_daily_chain"), "交隔日 10:10 補"


def test_b1_seat1_m9_open_quota_used_then_update_passes_precheck_and_builds():
    """席 1 現象 A：第 2 次同步後直接再更新（場次仍 open）→ 預檢 build 必須進鎖、builder 被呼叫。"""
    w = World(NO_PA, builder=publish)
    w.run_wake(at(21, 30))
    w.facts = dataclasses.replace(w.facts, box_counts={**w.facts.box_counts, "game_livelog": 356})
    w.run_wake(at(21, 40))
    w.builder = correction
    w.facts = dataclasses.replace(w.facts, box_counts={**w.facts.box_counts, "game_livelog": 357})
    assert w.run_wake(at(22, 0)) == "build"
    assert w.prechecks[-1] == "build"
    _assert_pending_until_daily(w)


def test_b1_seat1_s4_delivered_after_idle_wake_then_update_reopens_and_builds():
    """席 1 現象 B／席 2 S4：第 2 次同步後有一次無更新喚醒（轉 delivered），之後才更新＋更正。"""
    w = World(NO_PA, builder=publish)
    _two_syncs_box_box(w)
    assert w.run_wake(at(21, 45)) == "precheck_exit" and w.rec["state"] == "delivered"
    w.builder = correction
    w.facts = dataclasses.replace(w.facts, box_counts={**w.facts.box_counts, "game_livelog": 357})
    assert w.run_wake(at(22, 0)) == "build"
    _assert_pending_until_daily(w)


def test_b1_seat2_s5_m4_path_delivered_then_correction():
    """席 2 S5：[box]、[pa] 兩次後 delivered，再有 box 更新＋官方更正。"""
    calls = {"n": 0}

    def late(f):
        calls["n"] += 1
        return publish(f) if calls["n"] >= 2 else f
    w = World(NO_PA, builder=late)
    w.run_wake(at(21, 30))
    w.run_wake(at(21, 35))
    assert w.syncs == [["box"], ["pa"]]
    assert w.run_wake(at(21, 45)) == "precheck_exit" and w.rec["state"] == "delivered"
    w.builder = correction
    w.facts = dataclasses.replace(w.facts, box_counts={**w.facts.box_counts, "game_livelog": 357})
    assert w.run_wake(at(22, 0)) == "build"
    _assert_pending_until_daily(w)


def test_b1_delivered_with_quota_left_reopens_and_syncs_once_more():
    """額度還有時，已送達後的更新照常送（第 2 次），不受 fix-4 影響。"""
    w = World(NO_PA, builder=publish)
    w.run_wake(at(21, 30))
    assert w.run_wake(at(21, 35)) == "precheck_exit" and w.rec["state"] == "delivered"
    w.facts = dataclasses.replace(w.facts, box_counts={**w.facts.box_counts, "game_livelog": 356})
    assert w.run_wake(at(22, 0)) == "sync" and w.syncs == [["box", "pa"], ["box"]]


def test_terminal_state_is_set_when_the_sync_is_recorded_not_by_a_later_plan():
    """終態時序：最後一次同步入帳當下就轉終態——之後的喚醒只跑 `--dry` 預檢、不寫狀態檔。"""
    w = World(NO_PA, builder=publish)
    w.run_wake(at(22, 0))
    assert w.rec["state"] == "delivered", "boxpa-record 存檔時已是 delivered"
    w2 = World(dataclasses.replace(FULL), builder=correction)
    w2.run_wake(at(22, 0))
    assert w2.rec["state"] == "correction_pending", "更正待同步，不記已送達"


def test_box_ready_rejects_not_final_and_missing_box():
    assert not pe.boxpa_box_ready({"sources": {"box": {"reason": "not_final"}}})
    assert not pe.boxpa_box_ready({"sources": {"box": {"reason": "local_box_incomplete:game_livelog"}}})
    assert not pe.boxpa_box_ready({"sources": None})
    assert pe.boxpa_box_ready({"sources": {"box": {"reason": "no_prod_evidence"}}})
    assert pe.boxpa_pa_build_candidates({"k1": {"sources": {"box": {"reason": "not_final"}}},
                                          "k2": {"sources": {"box": {"reason": None, "status": "delivered"}}}}) == ["k2"]


def test_cli_boxpa_prepare_without_games_hands_published_games_to_the_builder(monkeypatch, tmp_path, capsys):
    """G1 的 CLI 接線（席 2 G1c）：`boxpa-prepare` 無 --games 時，已有 published、box 已到齊的場也要交給 builder。"""
    state = pe.empty_state()
    pe.boxpa_refresh(state, at(21, 30), LOCAL, {KEY: FULL})
    rec = state["boxpa"][KEY]
    assert rec["sources"]["pa"]["reason"] == "no_prod_evidence", "已有 published"
    monkeypatch.setenv("POSTSEASON_STATE", str(tmp_path / "state.json"))
    monkeypatch.setenv("POSTSEASON_YEAR", "2026")
    (tmp_path / "state.json").write_text(json.dumps(state), encoding="utf-8")
    monkeypatch.setattr(pe, "_now", lambda: at(21, 31))
    monkeypatch.setattr(pe, "load_local_games", lambda year, now: LOCAL)
    monkeypatch.setattr(pe, "boxpa_load_facts", lambda keys: {KEY: FULL})
    seen = []
    monkeypatch.setattr(pe, "boxpa_pa_build", lambda year, keys: seen.append(list(keys)) or {"games": len(keys)})
    assert pe.main(["boxpa-prepare"]) == 0
    assert seen == [[KEY]]
