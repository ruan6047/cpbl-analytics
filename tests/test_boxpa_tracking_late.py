"""#293 fix-5：逐球（TrackMan）晚到——不得判送達，同晚重開抓逐球、build、同步（需求方裁定 6293763437）。

底層是 **G3 真實樣本**（``tests/fixtures/postseason_g3_tracking_late_2026.json``）：
2026-10-20 台灣大賽 G3（大巨蛋），21:47 明細時 stats 回 0 球，21:49:53 box＋PA 以真實 manifest 送達；
22:48 stats 已有 291 筆帶 Trackman；隔日 10:10 每日鏈補抓後 pitch_tracking＝291、builder 乾淨 republish
（映射 291）。來源與「未觀測」項見 fixture 的 ``_provenance``。

驅動器照 ``scripts/postseason-evening.sh`` 的實際次序呼叫真狀態機；只有 stats 逐球重抓、PA builder 與
scoped 同步是替身。⛔ 這些是狀態機情境，不是真實當晚事件的證據。
"""

from __future__ import annotations

import copy
import dataclasses
import json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from cpbl import pitch_coverage
from cpbl import postseason_sources as ps
from cpbl.ingest import postseason_evening as pe
from cpbl.ingest import run_refresh_recent as rr
from tests.test_postseason_boxpa_stage import _evening

TPE = ZoneInfo("Asia/Taipei")
KEY = "2026-C-3"
FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "postseason_g3_tracking_late_2026.json")
                     .read_text(encoding="utf-8"))
LOCAL = {KEY: pe.LocalGame(2026, "C", 3, "2026-10-20", "AAA011", "ACN011", "大巨蛋", True)}
G3 = ps.facts_from_json(FIXTURE["facts"][KEY])          # 21:47 明細後的真實本機事實（逐球 0）
REAL_MANIFEST = FIXTURE["manifest"]                      # 21:49:53 真實對帳 manifest
AFTER = FIXTURE["after_daily_chain"]                    # 隔日每日鏈補抓後的真實結果
ARRIVED = AFTER["pitch_tracking"]                        # 291（＝22:48 stats 帶 Trackman 的筆數）
REBUILT = AFTER["published_build"]                       # builder 乾淨 republish 的真實 build


def at(hh, mm, day=20):
    return datetime(2026, 10, day, hh, mm, tzinfo=TPE)


def arrived(f: ps.LocalFacts) -> ps.LocalFacts:
    """逐球入庫：pitch_tracking 0 → 291；291 ≥ 292×0.85，既有覆蓋判準不再判落後。"""
    return dataclasses.replace(f, box_counts={**f.box_counts, "pitch_tracking": ARRIVED},
                               tracking_lagging=False)


def rebuild(f: ps.LocalFacts) -> ps.LocalFacts:
    """既有 builder 對 tracking-only 變動的處置：乾淨 republish 帶新映射（pa_build 模組契約）。"""
    if f.box_counts["pitch_tracking"] == 0 or f.published_build == REBUILT:
        return f
    return dataclasses.replace(f, published_build=REBUILT, published_at=AFTER["published_at"],
                               pa_counts={**f.pa_counts, "game_pa_pitch_mappings": AFTER["game_pa_pitch_mappings"]})


def manifest(f: ps.LocalFacts, now: datetime, parts) -> dict:
    pa_sent = "pa" in parts and f.published_build is not None
    return {"at": now.isoformat(), "games": {KEY: {
        "box_ok": True if "box" in parts else None, "pa_ok": True if pa_sent else None, "pa_sent": pa_sent,
        "box": {t: {"local": n, "prod": n} for t, n in f.box_counts.items()},
        "pa": {t: {"local": n, "prod": n} for t, n in f.pa_counts.items()},
        "published_build_local": f.published_build if pa_sent else None,
        "published_build_prod": f.published_build if pa_sent else None}}}


class World:
    def __init__(self, facts, *, tracking=None, builder=rebuild, codes=None):
        self.facts = facts
        self.state = pe.empty_state()
        self.state["events"] = {f"final_not_ingested:{KEY}": {
            "key": KEY, "t3_synced": FIXTURE["final_prod_at"]}}
        self.tracking = tracking or (lambda f: f)        # stats 逐球重抓替身
        self.builder = builder
        self.codes = list(codes or [])                   # scoped 同步結束碼（預設 0）
        self.syncs: list[list[str]] = []
        self.actions: list[str] = []
        self.first_manifest = True

    def _plan(self, now):
        recs = pe.boxpa_refresh(self.state, now, LOCAL, {KEY: self.facts})
        return recs, pe.boxpa_plan(self.state, now, recs)

    def run_wake(self, now):
        dry = copy.deepcopy(self.state)
        dry_action = pe.boxpa_plan(dry, now, pe.boxpa_refresh(dry, now, LOCAL, {KEY: self.facts}))[0]
        if dry_action not in ("detail", "sync", "tracking", "build"):   # shell 1b 預檢
            self.actions.append("precheck_exit")
            return "precheck_exit"
        _, (action, keys, parts) = self._plan(now)
        first = action
        self.actions.append(action)
        if action == "tracking":
            pe.boxpa_record_tracking(self.state, now, keys, [])
            self.facts = self.tracking(self.facts)
        if action in ("detail", "tracking", "build", "sync"):
            if KEY in pe.boxpa_pa_build_candidates(pe.boxpa_refresh(self.state, now, LOCAL, {KEY: self.facts})):
                self.facts = self.builder(self.facts)
            _, (action, keys, parts) = self._plan(now)
        if action == "sync" and parts:
            self.syncs.append(list(parts))
            code = self.codes.pop(0) if self.codes else 0
            if code == 72:                   # ssh 暫時失敗：沒有 manifest
                m = None
            elif self.first_manifest:        # 第一次成功送出用 21:49:53 的真實 manifest
                m, self.first_manifest = {"at": REAL_MANIFEST["at"], "games": REAL_MANIFEST["games"]}, False
            else:
                m = manifest(self.facts, now, parts)
            pe.boxpa_refresh(self.state, now, LOCAL, {KEY: self.facts})
            pe.boxpa_record_sync(self.state, now, keys, code, m, 133.0, parts)
            pe.boxpa_refresh(self.state, now, LOCAL, {KEY: self.facts})
        return first

    @property
    def rec(self):
        return self.state["boxpa"][KEY]

    @property
    def box(self):
        return self.rec["sources"]["box"]


def g3_after_first_send(**kw) -> World:
    """G3 實際路徑：21:47:27 明細（本機 box 到齊、PA published、逐球 0）→ 21:49 box＋PA 一次送出。"""
    w = World(G3, **kw)
    pe._boxpa_rec(w.state, KEY, "2026-10-20")["detail_attempts"].append(FIXTURE["detail_attempt"])
    assert w.run_wake(at(21, 49)) == "sync"
    assert w.syncs == [["box", "pa"]]
    return w


# ------------------------------------------------------------------ 分類器（真實樣本）

def test_g3_real_manifest_with_tracking_lagging_is_not_delivered():
    m = {**REAL_MANIFEST["games"][KEY], "at": REAL_MANIFEST["at"]}
    out = ps.classify(G3, m, at(21, 50), final_prod_at=FIXTURE["final_prod_at"])
    assert G3.tracking_lagging and G3.box_counts["pitch_tracking"] == 0
    assert (out["box"].status, out["box"].reason) == ("pending_update", "tracking_pending"), "假齊備"
    assert out["box"].prod_at is None and out["box"].same_night is None
    assert out["pa"].status == "delivered" and out["final"].status == "delivered"


def test_box_is_still_sent_first_when_tracking_lagging():
    """逐球不擋 box 核心先送：還沒有 manifest 時照常 no_prod_evidence（要送）。"""
    out = ps.classify(G3, None, at(21, 48), final_prod_at=FIXTURE["final_prod_at"])
    assert out["box"].reason == "no_prod_evidence"


def test_venue_without_recent_equipment_is_delivered_without_waiting():
    """既有判準判不落後（球場近期無設備）→ 0 球照常判送達，不等。"""
    no_equipment = dataclasses.replace(G3, tracking_lagging=False)
    m = {**REAL_MANIFEST["games"][KEY], "at": REAL_MANIFEST["at"]}
    assert ps.classify(no_equipment, m, at(21, 50))["box"].status == "delivered"
    w = g3_after_first_send()
    w.facts = no_equipment
    w.state["boxpa"][KEY]["state"] = "open"
    pe.boxpa_refresh(w.state, at(21, 50), LOCAL, {KEY: w.facts})
    assert w.rec["state"] == "delivered"
    assert w.run_wake(at(22, 30)) == "precheck_exit"


def test_g3_lagging_judgement_comes_from_existing_coverage_rule():
    """G3 的 tracking_lagging 由既有覆蓋判準在本機真實 DB 算出（fixture 原樣）：292 球、0 追蹤、
    同球場 C-1／C-2 達 0.80 → 落後；C-1／C-2 本身不落後。逐球 291 筆入庫後 ≥ 292×0.85 不再落後。"""
    assert FIXTURE["facts"][KEY]["tracking_lagging"] is True
    assert FIXTURE["facts"]["2026-C-1"]["tracking_lagging"] is False
    assert FIXTURE["facts"]["2026-C-2"]["tracking_lagging"] is False
    assert ARRIVED >= FIXTURE["livelog_pitches"] * 0.85 and FIXTURE["livelog_pitches"] >= 50
    assert ARRIVED == FIXTURE["stats_trackman_after"], "入庫列數＝stats 帶 Trackman 的筆數"


# ------------------------------------------------------------------ 狀態機路徑

def test_g3_late_tracking_reopens_same_night_fetches_builds_and_syncs_box_and_pa():
    calls = []

    def fetch(f):
        calls.append("tracking")
        return arrived(f)

    w = g3_after_first_send(tracking=fetch)
    assert w.rec["state"] == "open" and w.box["reason"] == "tracking_pending", "21:49 不得判 delivered"
    assert w.run_wake(at(21, 54)) == "precheck_exit", "距 21:47:27 明細未滿 20 分鐘"
    assert w.run_wake(at(22, 8)) == "tracking"
    assert calls == ["tracking"]
    assert w.syncs == [["box", "pa"], ["box", "pa"]], "逐球與重建的 PA 映射同一次送出"
    assert w.rec["state"] == "delivered" and w.box["status"] == "delivered"
    assert w.box["same_night"] is True and len(pe.boxpa_syncs(w.rec)) == 2
    assert w.run_wake(at(22, 30)) == "precheck_exit"


def test_tracking_poll_is_every_20_minutes_and_never_touches_www_ledgers():
    w = g3_after_first_send()                  # stats 一直沒有逐球
    before_www = dict(w.state["www_requests"])
    for hh, mm, expect in ((22, 6, "precheck_exit"), (22, 8, "tracking"), (22, 20, "precheck_exit"),
                           (22, 28, "tracking"), (23, 58, "tracking")):
        assert w.run_wake(at(hh, mm)) == expect, (hh, mm)
    assert w.rec["detail_attempts"] == [FIXTURE["detail_attempt"]], "不佔明細 www 的 3 次額度"
    assert len(w.rec["tracking_attempts"]) == 3
    assert w.state["www_requests"] == before_www, "C2：逐球重抓不寫 www 賽別冷卻帳本"
    assert w.state["challenge_failures"] == []
    assert w.rec["state"] == "open" and w.box["reason"] == "tracking_pending"
    assert w.box["same_night"] is None
    pe.boxpa_refresh(w.state, at(0, 10, day=21), LOCAL, {KEY: w.facts})
    assert w.box["same_night"] is False, "跨 24:00 仍未到：照實記同晚未達"
    pe.boxpa_refresh(w.state, at(10, 20, day=21), LOCAL, {KEY: w.facts})
    assert (w.rec["state"], w.rec["reason"]) == ("unreached", "handed_to_daily_chain")


def test_tracking_after_quota_is_exhausted_builds_locally_and_waits_for_daily_chain():
    """6204889879（範圍 6205405581：已送達且額度用完）：本機記待同步、⛔ 不第 3 次同步、隔日補。"""
    w = World(G3, tracking=arrived, codes=[72, 0])
    pe._boxpa_rec(w.state, KEY, "2026-10-20")["detail_attempts"].append(FIXTURE["detail_attempt"])
    w.run_wake(at(21, 49))                     # 72：ssh 暫時失敗（算一次同步）
    w.run_wake(at(21, 52))                     # 重送 0：box 核心送達，額度用完
    assert len(pe.boxpa_syncs(w.rec)) == 2 and w.box["reason"] == "tracking_pending"
    assert w.run_wake(at(22, 12)) == "tracking"
    assert len(w.syncs) == 2, "以場計：不得有第 3 次"
    assert w.facts.published_build == REBUILT, "額度用完也照常本機 build"
    assert w.box["reason"] == "local_changed_since_sync" and w.rec["state"] == "open"
    assert w.rec["reason"] == "source_changed_after_quota", "本機記待同步（待隔日 10:10 每日鏈）"
    assert w.run_wake(at(22, 20)) == "build" and len(w.syncs) == 2
    pe.boxpa_refresh(w.state, at(10, 20, day=21), LOCAL, {KEY: w.facts})
    assert (w.rec["state"], w.rec["reason"]) == ("unreached", "handed_to_daily_chain")


def test_delivered_state_left_by_old_code_reopens_on_tracking_pending():
    """部署前舊碼已把 G3 記成 delivered（真實狀態檔快照的形狀）→ 新分類器判 tracking_pending 即重開。"""
    w = g3_after_first_send()
    w.rec["state"], w.rec["reason"] = "delivered", None
    assert w.run_wake(at(22, 50)) == "tracking"
    assert w.rec["state"] == "open" and w.rec["reason"] == "reopened_tracking_pending"


def test_detail_and_sync_still_outrank_tracking():
    """次序 detail > sync > tracking > build（R1／G1 既有行為不變）。"""
    w = g3_after_first_send()
    rec = w.rec
    now = at(22, 30)
    recs = pe.boxpa_refresh(w.state, now, LOCAL, {KEY: w.facts})
    assert pe.boxpa_plan(w.state, now, recs)[0] == "tracking"
    other = dataclasses.replace(G3, key="2026-C-4", published_build=None, published_at=None)
    local = {**LOCAL, "2026-C-4": pe.LocalGame(2026, "C", 4, "2026-10-20", "ACN011", "AAA011", "大巨蛋", True)}
    recs = pe.boxpa_refresh(w.state, now, local, {KEY: w.facts, "2026-C-4": other})
    assert pe.boxpa_plan(w.state, now, recs)[:2] == ("sync", ["2026-C-4"])
    assert rec["state"] == "open"


# ------------------------------------------------------------------ 接線

def test_boxpa_tracking_only_calls_stats_pitches_for_target_games(monkeypatch):
    import cpbl.ingest._browser as browser
    import cpbl.ingest.cpbl_pitch_tracking as pt

    calls = []
    monkeypatch.setattr(pt, "scrape_game_pitches", lambda games, delay=1.0: calls.append(list(games)) or
                        {"games": len(games), "pitches": 291})
    monkeypatch.setattr(pt, "is_frozen", lambda *a: False)

    def boom(*a, **k):
        raise AssertionError("逐球重抓不得連 www")

    monkeypatch.setattr(browser, "www_marker", boom)
    monkeypatch.setattr(rr, "scrape_gamelogs", boom)
    monkeypatch.setattr(rr, "scrape_game_details", boom)
    out = pe.boxpa_tracking(2026, [KEY], delay=0)
    assert calls == [[(2026, "C", 3)]] and out["errors"] == []
    with pytest.raises(ValueError):   # #365：A 已是晚間賽別；D 仍不收（負控）
        pe.boxpa_tracking(2026, ["2026-D-3"], delay=0)


def test_lagging_sql_is_the_single_shared_source(monkeypatch):
    seen = {}

    class C:
        def execute(self, sql, params=None):
            seen["sql"], seen["params"] = sql, params
            return self

        def fetchall(self):
            return []

    from contextlib import contextmanager

    @contextmanager
    def fake_conn():
        yield C()

    monkeypatch.setattr(rr, "conn", fake_conn)
    rr._lagging_pitch_games(2026, "C")
    assert seen["sql"] == pitch_coverage.lagging_pitch_games_sql() and seen["params"] == (2026, "C", 3)


def test_load_local_facts_marks_lagging_from_the_shared_sql():
    class Cur:
        def __init__(self):
            self.lagging_params = []
            self._last = ""

        def execute(self, sql, params=None):
            self._last = sql
            if sql == pitch_coverage.lagging_pitch_games_sql(equipment_kinds=True):
                self.lagging_params.append(params)
            return self

        def fetchall(self):
            return [(3,)] if self._last == pitch_coverage.lagging_pitch_games_sql(equipment_kinds=True) else []

        def fetchone(self):
            s = self._last
            if "COALESCE(" in s and "FROM cpbl.games g" in s:
                return (datetime(2026, 10, 20).date(), True)
            if "SELECT build_id::text, built_at" in s:
                return None
            if "max(fetched_at) FROM cpbl.game_source_revisions" in s:
                return (None, None, None)
            if "min(fetched_at)" in s:
                return (None,)
            return (0,)

    cur = Cur()
    out = ps.load_local_facts(cur, [(2026, "C", 3), (2026, "C", 2)])
    assert out["2026-C-3"].tracking_lagging is True and out["2026-C-2"].tracking_lagging is False
    assert cur.lagging_params == [(2026, "C", 2026, ["A", "E", "C"], 1)], \
        "每個 (year, kind) 只跑一次；設備證據取同年一軍 A／E／C；days_back=1 涵蓋昨日場"


# ------------------------------------------------------------------ 設備證據跨一軍賽別（需求方 2026-10-21 裁定）

DAILY_CHAIN_SQL_SHA256 = "4f7d6147bef6157690c6902d01ca70c5e55dc1f75e06debbd517f9fb4d259c67"   # 抽出前 inline 原文


def test_daily_chain_lagging_sql_is_byte_identical_to_the_pre_extraction_text():
    """每日鏈的判準與設備母體（同賽別）不得被晚間鏈的改動帶動：預設 SQL 逐字等於抽出前的原文。"""
    import hashlib

    sql = pitch_coverage.lagging_pitch_games_sql()
    assert hashlib.sha256(sql.encode()).hexdigest() == DAILY_CHAIN_SQL_SHA256
    assert "ANY(%s)" not in sql and " ev AS (" not in sql


def test_evening_equipment_evidence_spans_first_team_kinds_with_same_constants():
    sql = pitch_coverage.lagging_pitch_games_sql(equipment_kinds=True)
    flat = " ".join(sql.split())
    assert "WHERE gm.year=%s AND gm.kind_code=%s AND" in flat, "受測場仍只取該賽別"
    assert "ev AS ( SELECT gm.venue, gm.game_sno, gm.game_date," in flat
    assert "WHERE gm.year=%s AND gm.kind_code = ANY(%s) AND" in flat, "設備證據取多個賽別"
    assert "rn FROM ev)" in flat and "rn FROM cov)" not in flat
    assert "FROM r WHERE rn<=10 GROUP BY venue" in flat
    assert "bool_or(pitches>=50 AND tracked>=pitches*0.80)" in flat
    assert "cov.pitches >= 50 AND cov.tracked < cov.pitches * 0.85" in flat
    assert sql.count("%s") == pitch_coverage.lagging_pitch_games_sql().count("%s") + 2
    assert ps.EQUIPMENT_EVIDENCE_KINDS == ("A", "E", "C"), "一軍例行賽＋季後；⛔ 不含二軍 D"


def test_shell_precheck_admits_tracking_and_runs_it_without_www_then_replans(tmp_path):
    result, read, lock = _evening(tmp_path, boxpa="tracking 2026-C-3", stage="boxpa")
    assert result.returncode == 0, result.stderr
    lines = read("uv.txt").splitlines()
    i_trk = next(i for i, x in enumerate(lines) if "boxpa-tracking --games 2026-C-3" in x)
    assert "--group scrape" not in lines[i_trk], "逐球重抓只打 stats，不載入爬蟲群組"
    i_prep = next(i for i, x in enumerate(lines) if x.endswith("boxpa-prepare"))
    i_plan = max(i for i, x in enumerate(lines) if x.endswith("boxpa-plan"))
    assert i_trk < i_prep < i_plan, "重抓 → PA build → 重新決定 parts"
    assert read("uv.txt").rstrip().endswith("finish") and not lock.exists()


def test_tracking_poll_interval_reuses_the_detail_cadence():
    assert pe.BOXPA_TRACKING_POLL == pe.BOXPA_WWW_COOLDOWN == timedelta(minutes=20)
