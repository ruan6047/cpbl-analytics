"""#383 段 1 WP1：官方改值接受閘門（PLAN §2.1 C 條件 1–6）＋選場第四條＋69 訊號＋寫入端 manifest。

全部無 DB：純函式用合成事件；`build_game` 接線用依 SQL 片段路由的假 cursor；每日鏈用替身。
變異自證（PLAN §5 WP1-e）：逐條把 `OFFICIAL_CONDITION_CHECKS` 的一項換成恆過，對應負例必須轉為
accepted——證明每一條都承重，不是被別條順手擋下。
"""

from __future__ import annotations

import copy
import json
import uuid
from contextlib import contextmanager
from datetime import UTC, date, datetime
from typing import Any

import pytest

from cpbl.ingest import pa_build as pb
from cpbl.ingest import run_refresh_recent as rr

TAX = pb.load_taxonomy()
KEY = (2026, "A", 1)
T_BUILT = datetime(2026, 7, 1, 12, 0, tzinfo=UTC)
T_OFFICIAL = datetime(2026, 8, 1, 12, 0, tzinfo=UTC)


def ev(no: int, hitter: str, action: str, *, inning: int = 1, half: str = "1",
       pitcher: str = "P1", content: str | None = None, special: bool = False,
       v: int = 0, h: int = 0) -> dict:
    return {
        "year": 2026, "kind_code": "A", "game_sno": 1, "main_event_no": f"{no:010d}",
        "inning_seq": inning, "visiting_home_type": half, "hitter_acnt": hitter,
        "pitcher_acnt": pitcher, "pitch_cnt": no, "action_name": action,
        "batting_action_name": "", "content": content if content is not None else action,
        "is_strike": True, "is_ball": False, "is_score": False, "is_change_player": False,
        "is_special_event": special, "out_cnt": 0, "ball_cnt": 0, "strike_cnt": 0,
        "first_base": None, "second_base": None, "third_base": None,
        "visiting_score": v, "home_score": h, "batting_order": 1,
    }


def old_events() -> list[dict]:
    """published 當時的原文：H2 飛球接殺；末事件內容被結束標記覆蓋（#357 的 1.3.0 形狀）。"""
    return [
        ev(1, "H1", "一壘安打"),
        ev(2, "H2", "飛球接殺"),
        ev(3, "H3", "三振"),
        ev(4, "H4", "飛球接殺"),
        ev(5, "H9", "飛球接殺", inning=1, half="2", pitcher="P2", content="比賽結束", special=True),
    ]


def new_events() -> list[dict]:
    """官方事後改判：H2 改為一壘安打（非末事件）；末事件恢復真實內容（1.6.0 型態）。"""
    out = old_events()
    out[1] = ev(2, "H2", "一壘安打")
    out[4] = ev(5, "H9", "飛球接殺", inning=1, half="2", pitcher="P2", content="中外野飛球接殺")
    return out


BOX_BAT = {
    "H1": {"plate_appearances": 1, "hits": 1, "home_runs": 0, "bb": 0, "ibb": 0, "hbp": 0, "so": 0},
    "H2": {"plate_appearances": 1, "hits": 1, "home_runs": 0, "bb": 0, "ibb": 0, "hbp": 0, "so": 0},
    "H3": {"plate_appearances": 1, "hits": 0, "home_runs": 0, "bb": 0, "ibb": 0, "hbp": 0, "so": 1},
    "H4": {"plate_appearances": 1, "hits": 0, "home_runs": 0, "bb": 0, "ibb": 0, "hbp": 0, "so": 0},
    "H9": {"plate_appearances": 1, "hits": 0, "home_runs": 0, "bb": 0, "ibb": 0, "hbp": 0, "so": 0},
}
BOX_PIT = {
    "P1": {"hits": 2, "home_runs": 0, "ibb": 0, "hbp": 0, "so": 1},
    "P2": {"hits": 0, "home_runs": 0, "ibb": 0, "hbp": 0, "so": 0},
}


def _pas(events):
    return pb.plate_appearances(*KEY, events, TAX)


def scenario(**overrides) -> dict:
    """一場官方改值的正例（全部六條成立）；overrides 改 facts 欄位或 events 造負例。"""
    events = overrides.pop("events", None) or new_events()
    old = overrides.pop("old", None) or old_events()
    old_pas, new_pas = _pas(old), _pas(events)
    published = {str(p.pa_id): p.pa_fingerprint() for p in old_pas}
    rec = pb.reconcile(new_pas, published)
    manifest = pb._livelog_manifest(events)[0]
    facts = pb.OfficialRevisionFacts(
        published_built_at=T_BUILT,
        revision={"id": 777, "fetched_at": T_OFFICIAL, "last_seen_at": T_OFFICIAL,
                  "detail": {"livelog_manifest_sha256": manifest, "livelog_residual_rows": 0,
                             "livelog_writer": pb.LIVELOG_WRITER_VERSION}},
        current_manifest_sha256=manifest,
        box_batting=copy.deepcopy(BOX_BAT), box_pitching=copy.deepcopy(BOX_PIT),
        scoreboard_runs={"1": 0, "2": 0}, games_scores=[(0, 0)],
        published_pas={str(p.pa_id): {"hitter_acnt": p.hitter_acnt, "end_hitter_acnt": p.end_hitter_acnt,
                                      "start_pitcher_acnt": p.start_pitcher_acnt,
                                      "end_pitcher_acnt": p.end_pitcher_acnt} for p in old_pas},
        published_event_fps={m.event_no: m.fingerprint for p in old_pas for m in p.members},
    )
    for name, value in overrides.items():
        setattr(facts, name, value(facts) if callable(value) else value)
    return {"pas": new_pas, "events": events, "rec": rec, "facts": facts}


def run_gate(s: dict, violations=None) -> dict:
    return pb.official_revision_gate(s["pas"], s["events"], s["rec"], s["facts"], TAX,
                                     invariant_violations=violations)


# ============================================================ 正例
def test_positive_official_revision_is_accepted() -> None:
    s = scenario()
    assert s["rec"].action == "reconcile" and len(s["rec"].changed_pa_ids) == 2
    # 1.6.0 謂詞原樣：兩個 changed PA → 型態受控接受不接（前提，⛔ 不改它）
    assert pb.controlled_restoration(s["pas"], {str(p.pa_id): p.pa_fingerprint()
                                                for p in _pas(old_events())},
                                     s["events"], s["rec"]) is None
    out = run_gate(s)
    assert out["accepted"] is True and out["failed"] == []
    assert out["official_revision_id"] == 777
    assert out["conditions"]["6_final_event"]["final_in_diff"] is True
    assert out["conditions"]["6_final_event"]["old_content"] == "比賽結束"
    json.dumps(out)  # 寫得進 validation_summary


def test_final_event_unchanged_is_fine() -> None:
    """差異不含末事件時條件 6 直接成立。"""
    old = old_events()
    old[4] = new_events()[4]
    out = run_gate(scenario(old=old))
    assert out["accepted"] is True
    assert out["conditions"]["6_final_event"]["final_in_diff"] is False


# ============================================================ 負例（逐條）
def _resolve_rev(**detail):
    def f(facts):
        rev = copy.deepcopy(facts.revision)
        rev["detail"].update(detail)
        return rev
    return f


NEGATIVES: dict[str, dict[str, Any]] = {
    "1_invariants": {"violations": [{"inning": 1, "half": "1", "out_pa": 4}]},
    "2_attribution": {"facts": {"revision": lambda f: {**f.revision, "fetched_at": datetime(
        2026, 6, 1, tzinfo=UTC)}}},
    "3_source_binding": {"facts": {"revision": _resolve_rev(livelog_manifest_sha256="0" * 64)}},
    "4_box": {"facts": {"box_batting": lambda f: {**f.box_batting, "H2": {
        **f.box_batting["H2"], "hits": 0}}}},
    "5_score": {"facts": {"games_scores": [(0, 1)]}},
    "6_final_event": {"old_events_final_content": "某個非標記的舊內容"},
}


def _negative(cid: str) -> tuple[dict, Any]:
    spec = NEGATIVES[cid]
    if "old_events_final_content" in spec:
        old = old_events()
        old[4] = {**old[4], "content": spec["old_events_final_content"]}
        return scenario(old=old), None
    return scenario(**spec.get("facts", {})), spec.get("violations")


@pytest.mark.parametrize("cid", pb.OFFICIAL_CONDITIONS)
def test_each_negative_is_rejected_by_exactly_its_condition(cid: str) -> None:
    s, violations = _negative(cid)
    out = run_gate(s, violations)
    assert out["accepted"] is False
    assert out["failed"] == [cid]


@pytest.mark.parametrize("cid", pb.OFFICIAL_CONDITIONS)
def test_mutation_removing_condition_turns_its_negative_green(cid: str, monkeypatch) -> None:
    """變異自證：拿掉第 cid 條（換成恆過）→ 它的負例被接受；正例在變異下仍接受。"""
    monkeypatch.setitem(pb.OFFICIAL_CONDITION_CHECKS, cid, lambda **_k: {"ok": True, "mutant": True})
    s, violations = _negative(cid)
    assert run_gate(s, violations)["accepted"] is True
    assert run_gate(scenario())["accepted"] is True


@pytest.mark.parametrize("detail,why", [
    ({"livelog_residual_rows": 1}, "寫入當下有殘列"),
    ({"livelog_writer": "livelog-writer-old"}, "寫入規則版本不是現行"),
    ({"livelog_manifest_sha256": None}, "WP1 之前的 revision：沒有 manifest"),
])
def test_source_binding_rejects_other_shapes(detail: dict, why: str) -> None:
    out = run_gate(scenario(revision=_resolve_rev(**detail)))
    assert out["failed"] == ["3_source_binding"], why


def test_source_binding_rejects_when_current_rows_differ_from_recorded() -> None:
    """非官方 writer 事後改了本機列：現行 manifest ≠ 寫入當下記錄的。"""
    out = run_gate(scenario(current_manifest_sha256="f" * 64))
    assert out["failed"] == ["3_source_binding"]


def test_attribution_rejects_missing_revision() -> None:
    out = run_gate(scenario(revision=None))
    assert "2_attribution" in out["failed"] and "3_source_binding" in out["failed"]


@pytest.mark.parametrize("override", [
    {"scoreboard_runs": {"1": 1, "2": 0}},
    {"games_scores": []},
    {"games_scores": [(0, 0), (0, 0)]},
])
def test_score_consistency_negatives(override: dict) -> None:
    assert run_gate(scenario(**override))["failed"] == ["5_score"]


def test_score_rejects_null_final_score() -> None:
    events = new_events()
    events[4] = {**events[4], "visiting_score": None}
    assert "5_score" in run_gate(scenario(events=events))["failed"]


def test_box_rejects_when_game_has_no_box() -> None:
    assert run_gate(scenario(box_batting={}, box_pitching={}))["failed"] == ["4_box"]


def test_box_checks_old_build_players_too() -> None:
    """舊 build 涉及、新 build 不涉及的投手也要對（新舊 build 都算）。"""
    s = scenario()
    pid = next(p for p, row in s["facts"].published_pas.items() if row["hitter_acnt"] == "H2")
    s["facts"].published_pas[pid] = {**s["facts"].published_pas[pid], "end_pitcher_acnt": "PX"}
    s["facts"].box_pitching["PX"] = {"hits": 0, "home_runs": 0, "ibb": 0, "hbp": 0, "so": 1}
    out = run_gate(s)
    assert out["failed"] == ["4_box"]
    assert {"side": "pit", "player": "PX", "field": "SO", "pa_derived": 0, "box": 1} in \
        out["conditions"]["4_box"]["mismatches"]


@pytest.mark.parametrize("mutate,reason", [
    ("golden", "golden_list_game"),
    ("marker_new", "new_final_is_end_marker"),
    ("final_no", "final_event_no_changed"),
])
def test_final_event_other_negatives(mutate: str, reason: str) -> None:
    if mutate == "golden":
        s = scenario(golden_game=True)
    elif mutate == "marker_new":
        events = new_events()
        events[4] = {**events[4], "content": "主審裁定比賽結束"}
        s = scenario(events=events)
    else:
        events = [*new_events(), ev(6, "H10", "飛球接殺", inning=1, half="2", pitcher="P2")]
        s = scenario(events=events)
    out = run_gate(s)
    assert "6_final_event" in out["failed"]
    assert out["conditions"]["6_final_event"]["reason"] == reason


def test_gate_not_applicable_to_builder_upgrade_or_publish() -> None:
    s = scenario()
    s["rec"] = pb.ReconcileResult(action="publish", changed_pa_ids=s["rec"].changed_pa_ids,
                                  builder_upgrade=True)
    out = run_gate(s)
    assert out["accepted"] is False and out["failed"][0] == "0_not_applicable"


def test_box_counts_follow_b4_rules() -> None:
    rows = [("A", "P", "故意四壞球"), ("A", "P", "四壞球"), ("B", "P", "全壘打"),
            ("B", "P", "觸身死球"), ("C", "P", "不死三振 暴投"), ("C", "P", "三振"),
            ("C", "P", None), ("C", "P", "犧牲飛球")]
    bat, pit = pb.box_counts_from_pas(rows, TAX)
    assert (bat["A"]["BB"], bat["A"]["IBB"], bat["A"]["PA"]) == (2, 1, 2)
    assert (bat["B"]["H"], bat["B"]["HR"], bat["B"]["HBP"]) == (1, 1, 1)
    assert (bat["C"]["SO"], bat["C"]["PA"]) == (2, 3)
    assert pit["P"]["IBB"] == 1 and pit["P"]["SO"] == 2 and "PA" not in pit["P"]


def test_fixed_box_fields_are_the_b4_set() -> None:
    """B4 已固定（⛔ 不增減）：打者 AB、投手 BF 與 BB 排除。"""
    assert list(pb.BOX_BATTING_FIELDS) == ["PA", "H", "HR", "BB", "IBB", "HBP", "SO"]
    assert list(pb.BOX_PITCHING_FIELDS) == ["H", "HR", "IBB", "HBP", "SO"]


# ============================================================ build_game 接線（假 cursor）
class _Res:
    def __init__(self, rows):
        self.rows = rows


class FakeCursor:
    """依 SQL 片段路由的假 cursor；記下所有寫入。只支援 build_game 預設路徑會發的查詢。"""

    def __init__(self, *, events, old_pas, builds, revision, rev_ids, box_bat=None, box_pit=None):
        self.events, self.old_pas, self.builds = events, old_pas, builds
        self.revision, self.rev_ids = revision, rev_ids
        self.box_bat = BOX_BAT if box_bat is None else box_bat
        self.box_pit = BOX_PIT if box_pit is None else box_pit
        self.writes: list[tuple[str, Any]] = []
        self._rows: list[dict] = []
        self.rowcount = 0
        self._pa_row = 0

    def _published(self):
        return [b for b in self.builds if b["state"] == "published"]

    def execute(self, sql: str, params: Any = None) -> None:  # noqa: C901 — 路由表
        s = " ".join(sql.split())
        rows: list[dict] = []
        if "pg_advisory_xact_lock" in s or "FROM cpbl.pitch_tracking" in s:
            rows = []
        elif "FROM cpbl.game_livelog" in s:
            rows = [dict(e) for e in self.events]
        elif s.startswith("INSERT INTO cpbl.game_recap_source_revisions"):
            rows = [{"id": self.rev_ids.get(params[4], 999)}]
        elif s.startswith("SELECT build_id, state, validation_summary FROM cpbl.game_recap_builds"):
            _y, _k, _g, ll, _tk, bv, tv = params
            rows = sorted(({"build_id": b["build_id"], "state": b["state"],
                            "validation_summary": b["validation_summary"], "built_at": b["built_at"]}
                           for b in self.builds if b["livelog_revision_id"] == ll
                           and b["builder_version"] == bv and b["taxonomy_version"] == tv),
                          key=lambda r: r["built_at"], reverse=True)[:1]
        elif s.startswith("SELECT build_id, builder_version, taxonomy_version"):
            rows = [{k: b[k] for k in ("build_id", "builder_version", "taxonomy_version",
                                       "livelog_revision_id", "tracking_revision_id")}
                    for b in self._published()]
        elif "array_agg(e.event_fingerprint" in s:
            rows = [{"pa_id": p.pa_id, "hitter_acnt": p.hitter_acnt,
                     "end_hitter_acnt": p.end_hitter_acnt, "start_pitcher_acnt": p.start_pitcher_acnt,
                     "end_pitcher_acnt": p.end_pitcher_acnt, "result_action": p.result_action,
                     "start_event_no": p.start_event_no, "end_event_no": p.end_event_no,
                     "member_fps": [m.fingerprint for m in p.members]} for p in self.old_pas]
        elif s.startswith("SELECT built_at FROM cpbl.game_recap_builds"):
            rows = [{"built_at": b["built_at"]} for b in self.builds if b["build_id"] == params[0]]
        elif "FROM cpbl.game_source_revisions" in s:
            rows = [self.revision] if self.revision else []
        elif "FROM cpbl.batting_gamelog" in s:
            rows = [{"hitter_acnt": k, **v} for k, v in self.box_bat.items()]
        elif "FROM cpbl.pitching_gamelog" in s:
            rows = [{"pitcher_acnt": k, **v} for k, v in self.box_pit.items()]
        elif "FROM cpbl.game_scoreboard" in s:
            rows = [{"visiting_home_type": "1", "runs": 0}, {"visiting_home_type": "2", "runs": 0}]
        elif "FROM cpbl.games WHERE" in s:
            rows = [{"away_score": 0, "home_score": 0}]
        elif s.startswith("SELECT pa.pa_id, pa.hitter_acnt, pa.end_hitter_acnt"):
            rows = [{"pa_id": p.pa_id, "hitter_acnt": p.hitter_acnt, "end_hitter_acnt": p.end_hitter_acnt,
                     "start_pitcher_acnt": p.start_pitcher_acnt, "end_pitcher_acnt": p.end_pitcher_acnt}
                    for p in self.old_pas]
        elif s.startswith("SELECT e.event_no, e.event_fingerprint"):
            rows = [{"event_no": m.event_no, "event_fingerprint": m.fingerprint}
                    for p in self.old_pas for m in p.members]
        elif s.startswith("SELECT build_id, livelog_revision_id, built_at"):
            rows = [{"build_id": b["build_id"], "livelog_revision_id": b["livelog_revision_id"],
                     "built_at": b["built_at"], "invariant_violations": []}
                    for b in self.builds if b["state"] == "reconciliation_required"]
        elif s.startswith("INSERT INTO cpbl.game_recap_builds"):
            bid, *_rest = params
            self.builds.append({"build_id": bid, "state": "building", "livelog_revision_id": params[4],
                                "builder_version": params[6], "taxonomy_version": params[7],
                                "tracking_revision_id": params[5], "built_at": datetime.now(UTC),
                                "validation_summary": json.loads(params[8])})
            self.writes.append(("insert_build", bid))
        elif s.startswith("INSERT INTO cpbl.game_plate_appearances"):
            self._pa_row += 1
            rows = [{"pa_row_id": self._pa_row}]
            self.writes.append(("insert_pa", None))
        elif s.startswith("UPDATE cpbl.game_recap_builds"):
            self.writes.append(("update", (s, params)))
            self._apply_update(s, params)
        else:
            raise AssertionError(f"未路由的 SQL：{s[:120]}")
        self._rows = rows

    def _apply_update(self, s: str, params: Any) -> None:
        self.rowcount = 0
        if "WHERE build_id=%s" in s:
            target = "published" if "state='published'" in s.split("WHERE")[0] else "reconciliation_required"
            for b in self.builds:
                if b["build_id"] == params[0]:
                    b["state"] = target
                    self.rowcount += 1
        elif "build_id = ANY" in s:
            for b in self.builds:
                if b["build_id"] in params[0] and b["state"] == "reconciliation_required":
                    b["state"] = "superseded"
                    self.rowcount += 1
        elif "state='published'" in s.split("SET")[1]:
            for b in self.builds:
                if b["state"] == "published":
                    b["state"] = "superseded"
                    self.rowcount += 1

    def executemany(self, sql: str, rows: Any) -> None:
        self.writes.append(("executemany", sql.split("(")[0].strip()))

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)


def _fake_world(*, recon_builder: str | None, revision: dict | None = None, box_bat=None):
    """published 1.3.0（舊原文）＋（可選）一筆 recon build；現行 livelog＝新原文。"""
    old_pas = _pas(old_events())
    sha_old = pb._livelog_manifest(old_events())[0]
    sha_new = pb._livelog_manifest(new_events())[0]
    builds = [{"build_id": str(uuid.uuid4()), "state": "published", "builder_version": "pa-build-1.3.0",
               "taxonomy_version": TAX.version, "livelog_revision_id": 100, "tracking_revision_id": None,
               "built_at": T_BUILT, "validation_summary": {}}]
    if recon_builder:
        builds.append({"build_id": str(uuid.uuid4()), "state": "reconciliation_required",
                       "builder_version": recon_builder, "taxonomy_version": TAX.version,
                       "livelog_revision_id": 101, "tracking_revision_id": None,
                       "built_at": datetime(2026, 10, 28, 6, 19, tzinfo=UTC),
                       "validation_summary": {"reconcile": {"action": "reconcile"},
                                              "invariant_violations": []}})
    if revision is None:
        revision = {"id": 777, "fetched_at": T_OFFICIAL, "last_seen_at": T_OFFICIAL,
                    "detail": {"livelog_manifest_sha256": sha_new, "livelog_residual_rows": 0,
                               "livelog_writer": pb.LIVELOG_WRITER_VERSION}}
    return FakeCursor(events=new_events(), old_pas=old_pas, builds=builds, revision=revision,
                      rev_ids={sha_old: 100, sha_new: 101}, box_bat=box_bat)


def test_builder_bump_makes_160_recon_build_non_equivalent_and_gate_runs() -> None:
    """PM 指定：1.6.0 的 reconcile build 在 1.7.0 下不是等價 build → 不 noop、進入新閘門。"""
    assert pb.BUILDER_VERSION != "pa-build-1.6.0"
    cur = _fake_world(recon_builder="pa-build-1.6.0")
    assert pb._existing_equivalent_build(cur, year=2026, kind="A", game=1,
                                         livelog_rev=101, tracking_rev=None) is None
    res = pb.build_game(cur, *KEY)
    assert res.action == "official_publish" and res.build_state == "published"
    summary = res.summary["reconcile"]
    assert summary["official_revision"]["accepted"] is True
    assert summary["accepted_shape"] == {"shape": "official_revision", "official_revision_id": 777}
    states = [b["state"] for b in cur.builds]
    # 舊 published 與 1.6.0 recon build 都轉 superseded；新 build published；無殘留待收尾
    assert states.count("published") == 1 and "reconciliation_required" not in states
    assert summary["official_revision"]["resolved_builds"] == [cur.builds[1]["build_id"]]


def test_equivalent_160_build_under_160_would_have_been_noop(monkeypatch) -> None:
    """對照組：版本不進位時同一場是 noop，閘門永遠不會被評估（這就是進版的理由）。"""
    monkeypatch.setattr(pb, "BUILDER_VERSION", "pa-build-1.6.0")
    cur = _fake_world(recon_builder="pa-build-1.6.0")
    res = pb.build_game(cur, *KEY)
    assert res.action == "noop" and not [w for w in cur.writes if w[0] == "insert_build"]


def test_rejected_writes_recon_build_with_failed_conditions_then_reevaluates_without_writing() -> None:
    bad_box = {**BOX_BAT, "H2": {**BOX_BAT["H2"], "hits": 0}}   # 官方 box 尚未改（改到一半）
    cur = _fake_world(recon_builder=None, box_bat=bad_box)
    first = pb.build_game(cur, *KEY)
    assert first.action == "reconcile" and first.build_state == "reconciliation_required"
    assert first.summary["reconcile"]["official_revision"]["failed"] == ["4_box"]
    n_builds = len(cur.builds)

    second = pb.build_game(cur, *KEY)   # 同一來源、box 仍錯：重評、不寫
    assert second.action == "noop" and second.summary["official_reevaluated"] is True
    assert len(cur.builds) == n_builds

    cur.box_bat = BOX_BAT               # 官方 box 改對了（livelog 不變）
    third = pb.build_game(cur, *KEY)
    assert third.action == "official_publish"
    assert [b["state"] for b in cur.builds].count("reconciliation_required") == 0


def test_no_manifest_revision_rejects_via_condition_3() -> None:
    legacy = {"id": 5, "fetched_at": T_OFFICIAL, "last_seen_at": T_OFFICIAL,
              "detail": {"phase": "getlive", "event_rows": 5}}
    cur = _fake_world(recon_builder=None, revision=legacy)
    res = pb.build_game(cur, *KEY)
    assert res.build_state == "reconciliation_required"
    assert res.summary["reconcile"]["official_revision"]["failed"] == ["3_source_binding"]
    assert sum(1 for b in cur.builds if b["state"] == "published") == 1   # 舊 published 保留


def test_reevaluable_only_for_gate_rejected_builds_without_invariants() -> None:
    gated = {"state": "reconciliation_required",
             "validation_summary": {"reconcile": {"official_revision": {"accepted": False}},
                                    "invariant_violations": []}}
    assert pb._official_gate_reevaluable(gated) is True
    assert pb._official_gate_reevaluable({**gated, "state": "published"}) is False
    assert pb._official_gate_reevaluable(
        {"state": "reconciliation_required", "validation_summary": {"reconcile": {}}}) is False
    assert pb._official_gate_reevaluable({**gated, "validation_summary": {
        **gated["validation_summary"], "invariant_violations": [{"x": 1}]}}) is False
    assert pb._official_gate_reevaluable(None) is False


# ============================================================ 每日路徑端到端（選場第四條 → 閘門 → 69）
class _DriftRows:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class _DriftConn:
    """`rr._pa_manifest_drift_targets` 的替身連線：published sha 查詢＋livelog 串流。"""

    def __init__(self, published_rows, events):
        self.published_rows, self.events = published_rows, events

    def execute(self, sql, params=None):
        return _DriftRows(self.published_rows)

    def cursor(self, **_kw):
        conn = self

        class _C:
            itersize = None

            def execute(self, *_a, **_k):
                pass

            def __iter__(self):
                return iter([dict(e) for e in conn.events])

        return _C()


def _daily_selects(monkeypatch, current_events) -> list:
    published_sha = pb._livelog_manifest(old_events())[0]
    holder = _DriftConn([(2026, "A", 1, published_sha)], current_events)

    @contextmanager
    def fake_conn():
        yield holder

    monkeypatch.setattr(rr, "conn", fake_conn)
    return rr._pa_manifest_drift_targets(2026, ["A"])


def test_e2e_b_unofficial_in_place_edit_is_selected_rejected_and_alerts_69(monkeypatch) -> None:
    """(b) 非官方 writer 原地改一列非末事件（detail 沒有新 manifest）→ 第四條選中 → 條件 2／3 拒收 → 69。"""
    tampered = old_events()
    tampered[1] = {**tampered[1], "content": "手動 SQL 改的內容"}
    assert _daily_selects(monkeypatch, tampered) == [KEY]          # WP2-A F1：舊實作此處為空

    publish_time_revision = {"id": 5, "fetched_at": datetime(2026, 6, 30, tzinfo=UTC),
                             "last_seen_at": datetime(2026, 6, 30, tzinfo=UTC),
                             "detail": {"phase": "getlive", "event_rows": 5}}
    old_pas = _pas(old_events())
    cur = FakeCursor(events=tampered, old_pas=old_pas, builds=[
        {"build_id": str(uuid.uuid4()), "state": "published", "builder_version": "pa-build-1.6.0",
         "taxonomy_version": TAX.version, "livelog_revision_id": 100, "tracking_revision_id": None,
         "built_at": T_BUILT, "validation_summary": {}}],
        revision=publish_time_revision, rev_ids={pb._livelog_manifest(old_events())[0]: 100})
    res = pb.build_game(cur, *KEY)
    assert res.build_state == "reconciliation_required"
    failed = res.summary["reconcile"]["official_revision"]["failed"]
    assert "2_attribution" in failed and "3_source_binding" in failed
    assert sum(1 for b in cur.builds if b["state"] == "published") == 1   # 舊 published 保留

    monkeypatch.setattr(rr, "_build_pa_daily", lambda *_a, **_k: {
        "games": 1, "actions": {"reconcile": 1}, "build_states": {}, "errors": [],
        "coverage": {"A": {"gap": 0, "reconciliation_outstanding": 1, "oldest_days": 0}},
        "reconciliation_alerts": [{"game": "2026/A/1", "days": 0, "failed": failed}]})
    step = rr._pa_build_step(2026, [date(2026, 10, 28)], include_farm=True)
    note = rr._pa_alert_note(step["reconciliation_alerts"])
    assert note.startswith("PA 對帳待收尾：2026/A/1(") and "3_source_binding" in note


def test_e2e_c_official_revision_with_matching_box_is_selected_and_published(monkeypatch) -> None:
    """(c) 官方新 revision（detail 有 manifest、box 一致）→ 第四條選中 → 閘門通過 → publish。"""
    assert _daily_selects(monkeypatch, new_events()) == [KEY]
    cur = _fake_world(recon_builder=None)
    res = pb.build_game(cur, *KEY)
    assert res.action == "official_publish" and res.build_state == "published"
    assert res.summary["reconcile"]["official_revision"]["failed"] == []


# ============================================================ 審核 r1 F1：涉及球員缺官方 box 列＝拒收
def _with_event4(**fields) -> list[dict]:
    events = new_events()
    events[3] = {**events[3], **fields}
    return events


def test_r1_f1_pitcher_missing_from_box_is_rejected() -> None:
    """審核者重現：H4 的投手改成 P3，官方投手 box 只有 P1、P2 → 條件 4 拒收（不得把缺列當 0）。"""
    out = run_gate(scenario(events=_with_event4(pitcher_acnt="P3")))
    assert out["accepted"] is False and out["failed"] == ["4_box"]
    assert {"side": "pit", "player": "P3"} in out["conditions"]["4_box"]["missing_box_rows"]


def test_r1_f1_batter_missing_from_box_is_rejected() -> None:
    """對稱負例：H4 那一打席改由 H5 打，官方打者 box 沒有 H5 → 拒收。"""
    out = run_gate(scenario(events=_with_event4(hitter_acnt="H5")))
    assert out["accepted"] is False and "4_box" in out["failed"]
    assert {"side": "bat", "player": "H5"} in out["conditions"]["4_box"]["missing_box_rows"]


def test_r1_f1_pitcher_missing_keeps_old_published_and_alerts_69(monkeypatch) -> None:
    events = _with_event4(pitcher_acnt="P3")
    sha_old, sha_new = pb._livelog_manifest(old_events())[0], pb._livelog_manifest(events)[0]
    old_pas = _pas(old_events())
    cur = FakeCursor(events=events, old_pas=old_pas, builds=[
        {"build_id": str(uuid.uuid4()), "state": "published", "builder_version": "pa-build-1.6.0",
         "taxonomy_version": TAX.version, "livelog_revision_id": 100, "tracking_revision_id": None,
         "built_at": T_BUILT, "validation_summary": {}}],
        revision={"id": 778, "fetched_at": T_OFFICIAL, "last_seen_at": T_OFFICIAL,
                  "detail": {"livelog_manifest_sha256": sha_new, "livelog_residual_rows": 0,
                             "livelog_writer": pb.LIVELOG_WRITER_VERSION}},
        rev_ids={sha_old: 100, sha_new: 101})
    res = pb.build_game(cur, *KEY)
    assert res.action == "reconcile" and res.build_state == "reconciliation_required"
    failed = res.summary["reconcile"]["official_revision"]["failed"]
    assert failed == ["4_box"]
    published = [b for b in cur.builds if b["state"] == "published"]
    assert len(published) == 1 and published[0]["livelog_revision_id"] == 100   # 舊 published 保留

    monkeypatch.setattr(rr, "_build_pa_daily", lambda *_a, **_k: {
        "games": 1, "actions": {"reconcile": 1}, "build_states": {}, "errors": [],
        "coverage": {"A": {"gap": 0, "reconciliation_outstanding": 1, "oldest_days": 0}},
        "reconciliation_alerts": [{"game": "2026/A/1", "days": 0, "failed": failed}]})
    step = rr._pa_build_step(2026, [date(2026, 10, 28)], include_farm=True)
    assert rr._pa_alert_note(step["reconciliation_alerts"]) == "PA 對帳待收尾：2026/A/1(4_box;0天)"
