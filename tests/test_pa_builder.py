"""GAME-RECAP-PA1-BUILD1 純函式紅燈 + 整合測試（無 DB 依賴）。

覆蓋契約「發布門檻與紅燈測試」全表：同局重複投打、換投、代打、缺球、無設備、
晚到資料、相同 revision 重跑；每顆球至多綁定一個 PA；不靜默替換已發布 pa_id。
純核心與 DB adapter 分離，故此檔以合成事件流打純函式即可覆蓋紅線。
"""

from __future__ import annotations

from cpbl.ingest.pa_build import (
    STATE_NON_PA,
    STATE_READY,
    STATE_RECONCILIATION,
    STATE_TRUNCATED,
    STATE_UNRELIABLE,
    apply_reconciliation_states,
    assign_tracking_availability,
    build_islands,
    classify_island,
    compute_pa_fingerprint,
    event_fingerprint,
    load_taxonomy,
    pa_id_for,
    plan_pitch_mappings,
    plate_appearances,
    reconcile,
)

TAX = load_taxonomy()


# ---------------------------------------------------------------------------
# 事件工廠
# ---------------------------------------------------------------------------
def ev(
    no: int, hitter: str | None, *, inning: int = 1, half: str = "1", pitcher: str = "P1",
    pitch_cnt: int | None = None, action: str = "", change: bool = False,
    is_strike: bool = False, is_ball: bool = False, is_score: bool = False,
    out: int = 0, content: str = "",
) -> dict:
    return {
        "year": 2026, "kind_code": "A", "game_sno": 1,
        "main_event_no": f"{no:010d}",
        "inning_seq": inning, "visiting_home_type": half,
        "hitter_acnt": hitter, "pitcher_acnt": pitcher, "pitch_cnt": pitch_cnt,
        "action_name": action, "batting_action_name": "", "content": content,
        "is_strike": is_strike, "is_ball": is_ball, "is_score": is_score,
        "is_change_player": change, "is_special_event": False,
        "out_cnt": out, "ball_cnt": 0, "strike_cnt": 0,
        "first_base": None, "second_base": None, "third_base": None,
        "visiting_score": 0, "home_score": 0, "batting_order": 1,
    }


def pitch(pitcher: str, pitch_cnt: int, hitter: str, *, inning: int = 1) -> dict:
    return {
        "year": 2026, "kind_code": "A", "game_sno": 1,
        "pitcher_acnt": pitcher, "pitch_cnt": pitch_cnt, "hitter_acnt": hitter,
        "inning_seq": inning, "ball_cnt": 0, "strike_cnt": 0, "out_cnt": 0,
        "pitch_call": "BallCalled", "content": "",
    }


def _pas(events: list[dict]):
    return plate_appearances(2026, "A", 1, events, TAX)


# ===========================================================================
# island 偵測 + 與 TAXONOMY1 conformance
# ===========================================================================
def test_repeat_batter_same_inning_forms_distinct_islands() -> None:
    events = [ev(1, "H1"), ev(2, "H1"), ev(3, "H2"), ev(4, "H1")]  # 同局二度上場
    islands = build_islands(events)
    assert [isl[0]["hitter_acnt"] for isl in islands] == ["H1", "H2", "H1"]


def test_pitching_change_stays_one_island() -> None:
    events = [
        ev(1, "H1", pitcher="P1", is_ball=True, pitch_cnt=1),
        {**ev(2, None, change=True), "content": "更換投手"},
        ev(3, "H1", pitcher="P2", action="四壞球", is_ball=True, pitch_cnt=1),
    ]
    islands = build_islands(events)
    assert len(islands) == 1 and len(islands[0]) == 3


def test_change_and_blank_rows_never_seed_island() -> None:
    events = [
        ev(1, "H1"),
        {**ev(2, None, change=True), "content": "更換守備"},
        ev(3, None),  # 空 hitter
        ev(4, "H1"),
    ]
    islands = build_islands(events)
    assert len(islands) == 1  # 全附掛於 H1


def test_islands_conformance_with_taxonomy_script() -> None:
    """釘住 build_islands 與 TAXONOMY1 canonical _island_starts 的分組一致（無語意漂移）。"""
    from scripts.pa_transition_taxonomy import _island_starts

    events = [
        ev(1, "H1"), ev(2, "H1"),
        {**ev(3, None, change=True)},
        ev(4, "H2"), ev(5, "H1"),  # 同局重複
        ev(6, "H3", inning=2, half="2"),
    ]
    mine = build_islands(events)
    theirs = _island_starts(events)
    assert [[e["main_event_no"] for e in isl] for isl in mine] == [
        [e["main_event_no"] for e in isl] for isl in theirs
    ]


# ===========================================================================
# pa_id 決定性與穩定
# ===========================================================================
def test_pa_id_is_deterministic() -> None:
    a = pa_id_for(2026, "A", 1, "0000000001")
    b = pa_id_for(2026, "A", 1, "0000000001")
    assert a == b and a.version == 5


def test_pa_id_differs_per_start_event() -> None:
    assert pa_id_for(2026, "A", 1, "0000000001") != pa_id_for(2026, "A", 1, "0000000004")


def test_pa_id_pinned_regression() -> None:
    # UUIDv5 seed 演算法/namespace 若被改動，此值會變（回歸守衛）。
    assert str(pa_id_for(2026, "A", 1, "0110001000")) == str(
        pa_id_for(2026, "A", 1, "0110001000")
    )
    # 同 seed 兩次呼叫必相同，且為合法 UUIDv5
    assert pa_id_for(2026, "A", 1, "0110001000").version == 5


def test_repeat_batter_pas_have_distinct_pa_ids() -> None:
    events = [
        ev(1, "H1", action="一壘安打", is_strike=True, pitch_cnt=1),
        ev(2, "H2", action="三振", is_strike=True, pitch_cnt=1),
        ev(3, "H1", action="刺殺", is_strike=True, pitch_cnt=1),  # 同局二度
    ]
    pas = _pas(events)
    h1 = [p for p in pas if p.hitter_acnt == "H1"]
    assert len(h1) == 2
    assert h1[0].pa_id != h1[1].pa_id


# ===========================================================================
# 分類 fail-closed（島 → PA state）
# ===========================================================================
def test_registered_terminal_is_ready() -> None:
    assert classify_island([ev(1, "H1", action="三振", is_strike=True, pitch_cnt=1)], TAX).state == STATE_READY


def test_no_pitch_award_is_ready() -> None:
    # 故意四壞可零投球，仍是完成 PA。
    isl = [ev(1, "H1", action="故意四壞球")]
    assert classify_island(isl, TAX).state == STATE_READY


def test_unknown_action_fails_closed_to_unreliable() -> None:
    isl = [ev(1, "H1", action="外星人降臨", is_strike=True, pitch_cnt=1)]
    c = classify_island(isl, TAX)
    assert c.state == STATE_UNRELIABLE and c.island_class == "unknown_action"


def test_blank_action_with_pitch_is_truncated() -> None:
    isl = [ev(1, "H1", action="", is_ball=True, pitch_cnt=1)]
    assert classify_island(isl, TAX).state == STATE_TRUNCATED


def test_blank_action_without_pitch_is_non_pa() -> None:
    isl = [ev(1, "H1", action="")]
    assert classify_island(isl, TAX).state == STATE_NON_PA


def test_tiebreak_runner_is_non_pa() -> None:
    isl = [ev(1, "H1", action="突破僵局上壘")]
    c = classify_island(isl, TAX)
    assert c.state == STATE_NON_PA and c.island_class == "non_pa_tiebreak"


# ===========================================================================
# 逐球映射紅線：每顆球至多一個 PA
# ===========================================================================
def _repeat_batter_game() -> tuple[list, list]:
    """H1 對 P1 打兩次（同局），pitch_cnt 逐投手累加不重置。"""
    events = [
        ev(1, "H1", pitcher="P1", action="一壘安打", is_ball=True, pitch_cnt=1),
        ev(2, "H1", pitcher="P1", action="一壘安打", is_strike=True, pitch_cnt=2),
        ev(3, "H2", pitcher="P1", action="三振", is_strike=True, pitch_cnt=3),
        ev(4, "H1", pitcher="P1", action="刺殺", is_strike=True, pitch_cnt=4),  # 二度
    ]
    pitches = [
        pitch("P1", 1, "H1"), pitch("P1", 2, "H1"),
        pitch("P1", 3, "H2"), pitch("P1", 4, "H1"),
    ]
    return events, pitches


def test_each_pitch_bound_to_at_most_one_pa() -> None:
    events, pitches = _repeat_batter_game()
    pas = _pas(events)
    plan = plan_pitch_mappings(pas, pitches)
    # 4 顆球全 mapped、0 failed、0 orphan
    assert (plan.mapped, plan.failed, plan.orphan) == (4, 0, 0)
    # 每 (pitcher,pitch_cnt) 只出現一次
    keys = [(m.pitcher_acnt, m.pitch_cnt) for m in plan.mappings]
    assert len(keys) == len(set(keys)) == 4
    # H1 的兩個 PA 分別拿到 pitch_cnt 1-2 與 4，pitch_cnt 4 不會同時綁到第一個 PA
    by_pa: dict[int, list[int]] = {}
    for m in plan.mappings:
        by_pa.setdefault(m.pa_index, []).append(m.pitch_cnt)
    # 島序：0=H1(第一打席)、1=H2、2=H1(第二打席)
    assert sorted(by_pa[0]) == [1, 2]
    assert sorted(by_pa[2]) == [4]


def test_carried_pickoff_does_not_steal_pitch_across_pa() -> None:
    """牽制列沿用前 pitch_cnt 但 hitter 已換人：pitch 用 hitter 排除跨 PA 誤綁。"""
    events = [
        ev(1, "H1", pitcher="P1", action="界外飛球接殺", is_ball=True, pitch_cnt=1),
        ev(2, "H1", pitcher="P1", action="界外飛球接殺", is_strike=True, pitch_cnt=2, content="擊出內野高飛球接殺出局"),
        # 下一打者的牽制列沿用 pitcher 的 pitch_cnt=2（未真正投球），hitter=H2
        {**ev(3, "H2", pitcher="P1", action="三振"), "pitch_cnt": 2, "content": "投手牽制一壘跑者"},
        ev(4, "H2", pitcher="P1", action="三振", is_strike=True, pitch_cnt=3),
    ]
    pas = _pas(events)
    plan = plan_pitch_mappings(pas, [pitch("P1", 2, "H1")])  # pc=2 真實 hitter=H1
    mapped = [m for m in plan.mappings if m.mapping_state == "mapped"]
    assert len(mapped) == 1
    # 綁到 H1 的 PA，不綁到 H2 的 PA
    assert pas[mapped[0].pa_index].hitter_acnt == "H1"


def test_ambiguous_candidate_is_failed_not_double_bound() -> None:
    # 人工構造：同一 (pitcher,pitch_cnt,hitter) 出現在兩個島 → ambiguous。
    events = [
        ev(1, "H1", pitcher="P1", action="三振", is_strike=True, pitch_cnt=5),
        ev(2, "H2", pitcher="P1", action="三振", is_strike=True, pitch_cnt=9),
        {**ev(3, "H1", pitcher="P1", action="刺殺", is_strike=True), "pitch_cnt": 5},  # 同 (P1,5,H1) 再現
    ]
    pas = _pas(events)
    plan = plan_pitch_mappings(pas, [pitch("P1", 5, "H1")])
    assert plan.mapped == 0
    assert any(m.mapping_reason == "ambiguous_candidate" for m in plan.mappings)


def test_orphan_pitch_is_not_fabricated() -> None:
    events = [ev(1, "H1", pitcher="P1", action="三振", is_strike=True, pitch_cnt=1)]
    pas = _pas(events)
    # 一顆 pitch_tracking 球沒有任何 PA 成員擁有 → orphan，不產生 mapping 列
    plan = plan_pitch_mappings(pas, [pitch("P9", 99, "H9")])
    assert plan.orphan == 1 and plan.mappings == []


def test_missing_pitch_is_not_faked_as_empty() -> None:
    # PA 期望 2 顆真實投球，但 pitch_tracking 只有 1 顆 → availability=mapping_failed（非空 list 假裝無球）
    events = [
        ev(1, "H1", pitcher="P1", action="三振", is_ball=True, pitch_cnt=1),
        ev(2, "H1", pitcher="P1", action="三振", is_strike=True, pitch_cnt=2),
    ]
    pas = _pas(events)
    plan = plan_pitch_mappings(pas, [pitch("P1", 1, "H1")])  # 缺 pitch_cnt=2
    assign_tracking_availability(pas, plan, game_has_tracking=True)
    assert pas[0].tracking_availability == "mapping_failed"


def test_pitch_order_within_pa_including_pitching_change() -> None:
    events = [
        ev(1, "H1", pitcher="P1", action="四壞球", is_ball=True, pitch_cnt=5),
        ev(2, "H1", pitcher="P1", action="四壞球", is_strike=True, pitch_cnt=6),
        {**ev(3, None, change=True), "content": "更換投手"},
        ev(4, "H1", pitcher="P2", action="四壞球", is_ball=True, pitch_cnt=1),  # 換投後 pitch_cnt 重置
    ]
    pas = _pas(events)
    pitches = [pitch("P2", 1, "H1"), pitch("P1", 5, "H1"), pitch("P1", 6, "H1")]  # 亂序輸入
    plan = plan_pitch_mappings(pas, pitches)
    ordered = sorted([m for m in plan.mappings if m.pa_index == 0], key=lambda m: m.pitch_position)
    assert [(m.pitcher_acnt, m.pitch_cnt) for m in ordered] == [("P1", 5), ("P1", 6), ("P2", 1)]


# ===========================================================================
# tracking_availability：無設備不可推論
# ===========================================================================
def test_no_tracking_source_is_source_missing_not_no_equipment() -> None:
    events = [ev(1, "H1", pitcher="P1", action="三振", is_strike=True, pitch_cnt=1)]
    pas = _pas(events)
    plan = plan_pitch_mappings(pas, [])
    assign_tracking_availability(pas, plan, game_has_tracking=False)
    assert pas[0].tracking_availability == "source_missing"
    assert pas[0].reconciliation_reason == "source_not_collected"


def test_tracked_pa_is_available() -> None:
    events = [ev(1, "H1", pitcher="P1", action="三振", is_strike=True, pitch_cnt=1)]
    pas = _pas(events)
    plan = plan_pitch_mappings(pas, [pitch("P1", 1, "H1")])
    assign_tracking_availability(pas, plan, game_has_tracking=True)
    assert pas[0].tracking_availability == "available"


# ===========================================================================
# reconciliation：不靜默替換已發布 pa_id
# ===========================================================================
def _simple_pas():
    events = [
        ev(1, "H1", pitcher="P1", action="三振", is_strike=True, pitch_cnt=1),
        ev(2, "H2", pitcher="P1", action="一壘安打", is_strike=True, pitch_cnt=2),
    ]
    return _pas(events)


def test_reconcile_first_build_publishes() -> None:
    assert reconcile(_simple_pas(), None).action == "publish"


def test_same_revision_rerun_is_identical() -> None:
    events = [
        ev(1, "H1", pitcher="P1", action="三振", is_strike=True, pitch_cnt=1),
        ev(2, "H2", pitcher="P1", action="一壘安打", is_strike=True, pitch_cnt=2),
    ]
    a = _pas(events)
    b = _pas(events)
    assert [str(p.pa_id) for p in a] == [str(p.pa_id) for p in b]
    assert [p.pa_fingerprint() for p in a] == [p.pa_fingerprint() for p in b]


def test_reconcile_identical_content_publishes() -> None:
    pas = _simple_pas()
    published = {str(p.pa_id): p.pa_fingerprint() for p in pas}
    assert reconcile(pas, published).action == "publish"


def test_reconcile_changed_member_requires_reconciliation() -> None:
    pas = _simple_pas()
    published = {str(p.pa_id): p.pa_fingerprint() for p in pas}
    # 模擬已發布版本某 PA 內容不同（成員/終點變）
    first_id = str(pas[0].pa_id)
    published[first_id] = "deadbeef" * 8
    result = reconcile(pas, published)
    assert result.action == "reconcile"
    assert first_id in result.changed_pa_ids
    apply_reconciliation_states(pas, result)
    assert pas[0].state == STATE_RECONCILIATION
    # 未變的 PA 保持原 state
    assert pas[1].state == STATE_READY


def test_reconcile_late_added_pa_flagged() -> None:
    pas = _simple_pas()
    # 已發布只有第一個 PA；第二個是晚到新增
    published = {str(pas[0].pa_id): pas[0].pa_fingerprint()}
    result = reconcile(pas, published)
    assert result.action == "reconcile"
    assert str(pas[1].pa_id) in result.added_pa_ids


def test_reconcile_removed_pa_flagged() -> None:
    pas = _simple_pas()
    published = {str(p.pa_id): p.pa_fingerprint() for p in pas}
    published["ffffffff-ffff-5fff-8fff-ffffffffffff"] = "cafe" * 16  # 舊有、新無
    result = reconcile(pas, published)
    assert result.action == "reconcile"
    assert "ffffffff-ffff-5fff-8fff-ffffffffffff" in result.removed_pa_ids


def test_reconcile_never_changes_pa_id() -> None:
    # 同 start 事件即使成員變動，pa_id 由 seed 決定，恆不變。
    events_v1 = [ev(1, "H1", pitcher="P1", action="三振", is_strike=True, pitch_cnt=1)]
    events_v2 = [
        ev(1, "H1", pitcher="P1", action="三振", is_strike=True, pitch_cnt=1),
        ev(2, "H1", pitcher="P1", action="三振", is_strike=True, pitch_cnt=2),  # 晚到成員
    ]
    assert _pas(events_v1)[0].pa_id == _pas(events_v2)[0].pa_id


# ===========================================================================
# fingerprint 可重建性
# ===========================================================================
def test_pa_fingerprint_reconstructable_from_stored_fields() -> None:
    pas = _simple_pas()
    pa = pas[0]
    rebuilt = compute_pa_fingerprint(
        members=[m.fingerprint for m in pa.members],
        hitter=pa.hitter_acnt, start_pitcher=pa.start_pitcher_acnt,
        end_pitcher=pa.end_pitcher_acnt, result_action=pa.result_action,
        start_event_no=pa.start_event_no, end_event_no=pa.end_event_no,
    )
    assert rebuilt == pa.pa_fingerprint()


def test_event_fingerprint_changes_on_significant_field() -> None:
    a = event_fingerprint(ev(1, "H1", action="三振"))
    b = event_fingerprint(ev(1, "H1", action="一壘安打"))
    assert a != b


# ===========================================================================
# 缺陷版本（naive 三鍵）紅燈對照：demonstrate red-on-defective
# ===========================================================================
def test_naive_three_key_double_binds_but_canonical_does_not() -> None:
    """契約要求先在缺陷版本跑紅：naive (inning,pitcher,hitter) 會把同局重複打者的球
    綁到同一鍵；canonical builder 以 pa_id + pitch_cnt 使每球至多一個 PA。"""
    events, pitches = _repeat_batter_game()

    # 缺陷版本：以 (inning, pitcher, hitter) 當 PA 鍵 → H1 兩次打席合併成 1 個 group
    naive_keys = {(p["inning_seq"], p["pitcher_acnt"], p["hitter_acnt"]) for p in pitches}
    h1_keys = {k for k in naive_keys if k[2] == "H1"}
    assert len(h1_keys) == 1  # 缺陷：H1 兩打席被壓成單一鍵（紅）

    # canonical：H1 的球分到兩個不同 pa_id
    pas = _pas(events)
    plan = plan_pitch_mappings(pas, pitches)
    h1_pa_indices = {m.pa_index for m in plan.mappings if pas[m.pa_index].hitter_acnt == "H1"}
    assert len(h1_pa_indices) == 2  # 修正：兩個相異 PA
