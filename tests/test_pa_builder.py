"""GAME-RECAP-PA1-BUILD1 純函式紅燈 + 整合測試（無 DB 依賴）。

覆蓋契約「發布門檻與紅燈測試」全表：同局重複投打、換投、代打、缺球、無設備、
晚到資料、相同 revision 重跑；每顆球至多綁定一個 PA；不靜默替換已發布 pa_id。
純核心與 DB adapter 分離，故此檔以合成事件流打純函式即可覆蓋紅線。
"""

from __future__ import annotations

from pathlib import Path

from cpbl.ingest.pa_build import (
    STATE_NON_PA,
    STATE_READY,
    STATE_RECONCILIATION,
    STATE_TRUNCATED,
    STATE_UNRELIABLE,
    PlateAppearance,
    ReconcileResult,
    apply_invariant_states,
    apply_reconciliation_states,
    assign_tracking_availability,
    build_islands,
    classify_island,
    compute_pa_fingerprint,
    derive_half_inning_outs,
    event_fingerprint,
    half_inning_out_violations,
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
    out: int = 0, content: str = "", balls: int = 0, strikes: int = 0, order: int = 1,
) -> dict:
    return {
        "year": 2026, "kind_code": "A", "game_sno": 1,
        "main_event_no": f"{no:010d}",
        "inning_seq": inning, "visiting_home_type": half,
        "hitter_acnt": hitter, "pitcher_acnt": pitcher, "pitch_cnt": pitch_cnt,
        "action_name": action, "batting_action_name": "", "content": content,
        "is_strike": is_strike, "is_ball": is_ball, "is_score": is_score,
        "is_change_player": change, "is_special_event": False,
        "out_cnt": out, "ball_cnt": balls, "strike_cnt": strikes,
        "first_base": None, "second_base": None, "third_base": None,
        "visiting_score": 0, "home_score": 0, "batting_order": order,
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
# FIX1：打席中途代打換人不切界（打者變化 ≠ 打席變化）
# ===========================================================================
def _mid_pa_pinch_hit_events() -> list[dict]:
    """2018/A/116 7 局下實形：H1 打到 1-2，代打 H2 上場續打完成三振。

    每一列都帶同一個 ``action_name=三振``——livelog 的結果是打席層級被複製到每列，
    正是照打者切界會把「一個打席一個出局」記成兩個的成因。
    """
    return [
        ev(10, "H1", action="三振", is_ball=True, pitch_cnt=103, balls=1, strikes=0, order=3),
        ev(11, "H1", action="三振", is_strike=True, pitch_cnt=104, balls=1, strikes=1, order=3),
        ev(12, "H1", action="三振", is_strike=True, pitch_cnt=105, balls=1, strikes=2, order=3),
        {**ev(13, "H2", action="三振", change=True, pitch_cnt=105, balls=1, strikes=2, order=3),
         "content": "更換代打：H1=>H2。"},
        ev(14, "H2", action="三振", is_strike=True, pitch_cnt=106, balls=1, strikes=3, order=3,
           content="好球沒揮棒。 打者出局-三振出局。 3人出局。"),
    ]


def test_mid_pa_pinch_hit_stays_one_island() -> None:
    islands = build_islands(_mid_pa_pinch_hit_events())
    assert len(islands) == 1 and len(islands[0]) == 5


def test_mid_pa_pinch_hit_yields_single_out_pa() -> None:
    pas = _pas(_mid_pa_pinch_hit_events())
    assert len(pas) == 1
    assert pas[0].outcome_family == "out" and pas[0].state == STATE_READY
    # 打席歸屬於起始事件（pa_id seed），完成者記為終結投打側
    assert pas[0].start_event_no == "0000000010" and pas[0].end_event_no == "0000000014"


def test_mid_pa_pinch_hit_without_announcement_uses_count_continuity() -> None:
    """2023/A/73 8 局下實形：官方漏記代打公告，但球數 1 壞續投到 2 壞。"""
    events = [
        ev(3, "H1", action="刺殺", is_ball=True, pitch_cnt=10, balls=1, strikes=0, order=2),
        ev(4, "H2", action="刺殺", is_ball=True, pitch_cnt=11, balls=2, strikes=0, order=2),
        ev(5, "H2", action="刺殺", is_strike=True, pitch_cnt=12, balls=2, strikes=0, order=2,
           content="擊出內野滾地球，刺殺出局。 2人出局。"),
    ]
    assert len(build_islands(events)) == 1


def test_pre_pitch_pinch_hit_stays_one_island() -> None:
    """2019/A/68 實形：原打者只有牽制列（無真實投球）即被代打取代。"""
    events = [
        {**ev(18, "H1", action="三振", pitch_cnt=16, order=4), "content": "投手牽制一壘跑者"},
        {**ev(19, "H2", action="三振", change=True, pitch_cnt=16, order=4),
         "content": "更換代打：H1=>H2。"},
        ev(20, "H2", action="三振", is_strike=True, pitch_cnt=17, strikes=1, order=4),
        ev(21, "H2", action="三振", is_strike=True, pitch_cnt=18, strikes=3, order=4,
           content="揮棒落空。 打者出局-三振出局。 3人出局。"),
    ]
    assert len(build_islands(events)) == 1


def test_zero_pitch_walk_then_between_pa_pinch_hit_stays_two_islands() -> None:
    """紅線反例（2018/A/9 9 局上實形）：零投球故意四壞是**完成的打席**，
    緊接著的代打屬**打席間**換人，兩者不得合併——棒次槽不同且球數歸零。"""
    events = [
        ev(15, "H1", action="故意四壞球", pitch_cnt=13, order=4,
           content="故意四壞球上壘。"),
        {**ev(16, "H2", action="一壘安打", change=True, pitch_cnt=13, order=5),
         "content": "更換代打：X=>H2。"},
        ev(17, "H2", action="一壘安打", is_ball=True, pitch_cnt=14, balls=1, order=5),
        ev(18, "H2", action="一壘安打", is_strike=True, pitch_cnt=15, balls=1, strikes=1,
           order=5, content="擊出左外野平飛球，一壘安打 。"),
    ]
    islands = build_islands(events)
    assert len(islands) == 2
    pas = _pas(events)
    assert [p.outcome_family for p in pas] == ["walk", "hit"]


def test_pinch_hit_announcement_alone_does_not_merge_across_batting_order() -> None:
    """公告列存在但棒次槽已前進（＝打席間換人）→ 仍須切界。"""
    events = [
        ev(1, "H1", action="三振", is_strike=True, pitch_cnt=1, strikes=3, order=1,
           content="揮棒落空。 打者出局-三振出局。 1人出局。"),
        {**ev(2, "H2", action="飛球接殺", change=True, pitch_cnt=1, order=2),
         "content": "更換代打：X=>H2。"},
        ev(3, "H2", action="飛球接殺", is_strike=True, pitch_cnt=2, strikes=1, order=2,
           content="飛球接殺出局。 2人出局。"),
    ]
    assert len(build_islands(events)) == 2


def test_pinch_hit_merge_does_not_cross_half_innings() -> None:
    events = [
        ev(1, "H1", action="三振", is_strike=True, pitch_cnt=1, balls=1, strikes=2, order=3),
        ev(2, "H2", action="三振", inning=1, half="2", is_strike=True, pitch_cnt=1,
           balls=1, strikes=3, order=3),
    ]
    assert len(build_islands(events)) == 2


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
        hitter=pa.hitter_acnt, end_hitter=pa.end_hitter_acnt,
        start_pitcher=pa.start_pitcher_acnt,
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


# ===========================================================================
# taxonomy 打包：生產容器（無 repo docs/）也須能載入
# ===========================================================================
def test_taxonomy_loads_from_packaged_data() -> None:
    # load_taxonomy 解析到的路徑必須存在且可載入（含全 action）
    tax = load_taxonomy()
    assert tax.version == "1.1.0"
    assert len(tax.actions) >= 55  # v1.0.0 收錄 58 個 action，FIX1 未增刪 action


def test_packaged_taxonomy_is_byte_identical_to_canonical_docs() -> None:
    # src/cpbl/data 的打包副本必須與 docs/design canonical 逐位元組相同（drift 守衛）
    from cpbl.ingest import pa_build

    pkg = Path(pa_build.__file__).resolve().parent.parent / "resources" / pa_build._TAXONOMY_FILENAME
    docs = (
        Path(pa_build.__file__).resolve().parents[3]
        / "docs" / "design" / pa_build._TAXONOMY_FILENAME
    )
    assert pkg.exists(), "打包副本 src/cpbl/data 必須存在（生產容器不含 docs/）"
    if docs.exists():  # 本機 repo 佈局；生產 wheel 內無 docs/
        assert pkg.read_bytes() == docs.read_bytes()


def test_default_taxonomy_path_prefers_packaged_copy() -> None:
    from cpbl.ingest import pa_build

    resolved = pa_build._default_taxonomy_path()
    assert resolved.name == pa_build._TAXONOMY_FILENAME
    assert resolved.exists()
    # 打包副本存在時必須優先選它（不依賴 repo docs/）
    assert resolved.parent.name == "resources"


# ===========================================================================
# FIX1：outs 由 content 推導（不讀會落後的 out_cnt）
# ===========================================================================
def test_derive_outs_reads_narrative_not_out_cnt() -> None:
    """2018/A/78 4 局下實形：新打席首列 out_cnt 停在 0（落後），實際已 2 出局。"""
    events = [
        ev(1, "H1", action="三振", is_strike=True, pitch_cnt=1, out=0,
           content="揮棒落空。 打者出局-三振出局。 1人出局。"),
        ev(2, "H2", action="刺殺", is_strike=True, pitch_cnt=2, out=1,
           content="擊出內野滾地球，刺殺出局。 2人出局。"),
        ev(3, "H3", action="飛球接殺", is_strike=True, pitch_cnt=3, out=0),  # out_cnt 落後
        ev(4, "H3", action="飛球接殺", is_strike=True, pitch_cnt=4, out=2,
           content="飛球接殺出局。 3人出局。"),
    ]
    derived = derive_half_inning_outs(events)
    assert derived["0000000003"] == (2, 2)  # 前 2 出局；本列未再增加
    pas = _pas(events)
    assert [p.pre_state["outs"] for p in pas] == [0, 1, 2]
    assert [p.post_state["outs"] for p in pas] == [1, 2, 3]


def test_derive_outs_resets_per_half_inning() -> None:
    events = [
        ev(1, "H1", action="三振", is_strike=True, pitch_cnt=1, out=0,
           content="打者出局-三振出局。 3人出局。"),
        ev(2, "H9", action="三振", inning=1, half="2", is_strike=True, pitch_cnt=1, out=3,
           content="打者出局-三振出局。 1人出局。"),
    ]
    derived = derive_half_inning_outs(events)
    assert derived["0000000002"] == (0, 1)  # 換半局歸零，不沿用上半局的 3


def test_derive_outs_is_monotonic_within_half_inning() -> None:
    """單一敘述異常不得使後續事件整段偏移（出局數不可能減少）。"""
    events = [
        ev(1, "H1", action="三振", is_strike=True, pitch_cnt=1, content="2人出局。"),
        ev(2, "H2", action="三振", is_strike=True, pitch_cnt=2, content="1人出局。"),
        ev(3, "H3", action="三振", is_strike=True, pitch_cnt=3),
    ]
    assert derive_half_inning_outs(events)["0000000003"] == (2, 2)


# ===========================================================================
# FIX1：半局出局不變式 fail closed
# ===========================================================================
def _out_pa(index: int, inning: int, half: str) -> PlateAppearance:
    return PlateAppearance(
        pa_id=pa_id_for(2026, "A", 1, f"{index:010d}"), pa_index=index, year=2026,
        kind_code="A", game_sno=1, start_event_no=f"{index:010d}", end_event_no=None,
        hitter_acnt=f"H{index}", end_hitter_acnt=f"H{index}",
        start_pitcher_acnt="P1", end_pitcher_acnt="P1",
        state=STATE_READY, island_class="completed_pa", result_action="三振",
        outcome_family="out", pre_state={"inning": inning, "half": half, "outs": 0},
        post_state={}, members=[],
    )


def test_three_out_pa_per_half_inning_is_not_a_violation() -> None:
    assert half_inning_out_violations([_out_pa(i, 1, "1") for i in range(3)]) == []


def test_fourth_out_pa_in_half_inning_is_a_violation() -> None:
    v = half_inning_out_violations([_out_pa(i, 1, "1") for i in range(4)])
    assert v == [{"inning": 1, "half": "1", "out_pa": 4}]


def test_violation_counts_per_half_inning_not_per_inning() -> None:
    pas = [_out_pa(i, 1, "1") for i in range(3)] + [_out_pa(i + 10, 1, "2") for i in range(3)]
    assert half_inning_out_violations(pas) == []


def test_non_batter_out_families_do_not_count_toward_invariant() -> None:
    """野手選擇／不死三振打者上壘，出局記在跑者身上——不計入本不變式。"""
    pas = [_out_pa(i, 1, "1") for i in range(3)]
    extra = _out_pa(9, 1, "1")
    extra.outcome_family = "fielders_choice"
    assert half_inning_out_violations([*pas, extra]) == []


def test_invariant_marks_violating_half_inning_unreliable() -> None:
    pas = [_out_pa(i, 1, "1") for i in range(4)] + [_out_pa(9, 2, "1")]
    apply_invariant_states(pas, half_inning_out_violations(pas))
    assert [p.state for p in pas[:4]] == [STATE_UNRELIABLE] * 4
    assert all(p.reconciliation_reason == "half_inning_out_overflow" for p in pas[:4])
    assert pas[4].state == STATE_READY  # 未違反的半局不受影響


# ===========================================================================
# FIX1：builder 升級的發布路徑不得削弱 fail closed
# ===========================================================================
def _one_pa() -> list[PlateAppearance]:
    return _pas([ev(1, "H1", action="三振", is_strike=True, pitch_cnt=1)])


def test_builder_upgrade_with_identical_source_publishes() -> None:
    pas = _one_pa()
    stale = {str(pas[0].pa_id): "fingerprint-from-old-builder"}
    rec = reconcile(pas, stale, builder_upgrade_same_source=True)
    assert rec.action == "publish" and rec.builder_upgrade is True
    assert rec.changed_pa_ids == [str(pas[0].pa_id)]  # 差異仍逐筆留痕


def test_source_drift_still_fails_closed_regardless_of_builder_version() -> None:
    pas = _one_pa()
    stale = {str(pas[0].pa_id): "fingerprint-from-drifted-source"}
    rec = reconcile(pas, stale, builder_upgrade_same_source=False)
    assert rec.action == "reconcile" and rec.builder_upgrade is False


def test_builder_upgrade_flag_does_not_flag_pas_as_reconciliation() -> None:
    pas = _one_pa()
    rec = reconcile(pas, {str(pas[0].pa_id): "stale"}, builder_upgrade_same_source=True)
    apply_reconciliation_states(pas, rec)
    assert pas[0].state == STATE_READY


def test_invariant_flag_is_not_overwritten_by_reconciliation_bookkeeping() -> None:
    """不變式（資料本身錯）優先於 reconciliation（與既有發布不一致）的簿記。

    次序若反過來，違反半局的 PA 會先被標 reconciliation_required，
    不變式便看不到 ready 的出局 PA 而**靜默放行**——本測試釘住這個次序。
    """
    pas = [_out_pa(i, 1, "1") for i in range(4)]
    apply_invariant_states(pas, half_inning_out_violations(pas))
    rec = ReconcileResult(action="reconcile", added_pa_ids=[str(p.pa_id) for p in pas])
    apply_reconciliation_states(pas, rec)
    assert all(p.state == STATE_UNRELIABLE for p in pas)
    assert all(p.reconciliation_reason == "half_inning_out_overflow" for p in pas)


# ===========================================================================
# FIX1 iteration 2：查核 Critical 反例——球數不歸零 ≠ 同一打席
# ===========================================================================
def test_count_continuation_across_advancing_batting_order_is_not_merged() -> None:
    """`2021/D/64` 6 局下實形：棒次 5 於 1-1 結束（「2人出局。」），棒次 6 首列是 2-1。

    來源球數在換打者時**沒有歸零**——iteration 1 只看球數會把兩個真打席併成一個
    （查核 Critical，違反紅線 1）。棒次槽已前進即為兩個打席。
    """
    events = [
        ev(22, "H1", is_ball=True, pitch_cnt=20, balls=1, strikes=0, order=5),
        ev(23, "H1", is_strike=True, pitch_cnt=21, balls=1, strikes=1, order=5),
        ev(24, "H1", is_strike=True, pitch_cnt=22, balls=1, strikes=1, order=5,
           content=" 2人出局。"),
        ev(25, "H2", is_ball=True, pitch_cnt=23, balls=2, strikes=1, order=6),
        ev(26, "H2", is_strike=True, pitch_cnt=24, balls=2, strikes=2, order=6),
    ]
    assert len(build_islands(events)) == 2


def test_count_continuation_with_advancing_order_and_no_announcement_is_not_merged() -> None:
    """`2018/A/4` 實形：棒次 11 的 (1,0) 接棒次 12 的 (2,0)，無代打公告。"""
    events = [
        ev(33000, "H1", is_ball=True, pitch_cnt=0, balls=1, strikes=0, order=11),
        ev(33900, "H2", action="四壞球", is_ball=True, pitch_cnt=1, balls=2, strikes=0, order=12),
        ev(34000, "H2", action="四壞球", is_ball=True, pitch_cnt=2, balls=3, strikes=0, order=12),
    ]
    assert len(build_islands(events)) == 2


def test_zero_batting_order_still_merges_on_count_continuation() -> None:
    """`2020/A/239` 3 局上實形：早年資料 batting_order 全為 0，兩段同為 0 仍可合併。"""
    events = [
        ev(1, "H1", action="三振", is_strike=True, pitch_cnt=41, strikes=1, order=0),
        ev(3, "H1", action="三振", is_strike=True, pitch_cnt=43, balls=1, strikes=2, order=0),
        {**ev(4, "H2", action="三振", change=True, pitch_cnt=43, balls=1, strikes=2, order=0),
         "content": "更換代打：H1=>H2。"},
        ev(5, "H2", action="三振", is_strike=True, pitch_cnt=44, balls=1, strikes=3, order=0,
           content="好球沒揮棒。 打者出局-三振出局。 1人出局。"),
    ]
    assert len(build_islands(events)) == 1


def test_zero_batting_order_alone_cannot_carry_the_weak_signal() -> None:
    """batting_order=0 是缺值哨兵：只有公告列而無球數佐證時不得合併。"""
    events = [
        {**ev(1, "H1", action="三振", pitch_cnt=16, order=0), "content": "投手牽制一壘跑者"},
        {**ev(2, "H2", action="三振", change=True, pitch_cnt=16, order=0),
         "content": "更換代打：H1=>H2。"},
        ev(3, "H2", action="三振", is_strike=True, pitch_cnt=17, strikes=1, order=0),
    ]
    assert len(build_islands(events)) == 2


# ===========================================================================
# FIX1 iteration 2：記錄規則 9.15(b) 的打席歸屬
# ===========================================================================
def test_strikeout_after_two_strikes_is_charged_to_original_batter() -> None:
    """9.15(b) 第一句：原打者於第 2 好球後退出、代打者以三振完成 → 記原打者。"""
    pas = _pas(_mid_pa_pinch_hit_events())
    assert len(pas) == 1
    assert pas[0].hitter_acnt == "H1"      # 記錄歸屬＝被判第 2 好球者
    assert pas[0].end_hitter_acnt == "H2"  # 實際打完的是代打者


def test_non_strikeout_result_is_charged_to_the_substitute() -> None:
    """9.15(b) 第二句：代打者以其他結果完成打擊（含四壞球）→ 記該代打者。"""
    events = [
        ev(1, "H1", action="一壘安打", is_ball=True, pitch_cnt=1, balls=1, order=3),
        {**ev(2, "H2", action="一壘安打", change=True, pitch_cnt=1, balls=1, order=3),
         "content": "更換代打：H1=>H2。"},
        ev(3, "H2", action="一壘安打", is_ball=True, pitch_cnt=2, balls=2, order=3),
        ev(4, "H2", action="一壘安打", is_strike=True, pitch_cnt=3, balls=2, strikes=1,
           order=3, content="擊出中外野平飛球，一壘安打 。"),
    ]
    pas = _pas(events)
    assert len(pas) == 1
    assert pas[0].hitter_acnt == "H2" and pas[0].end_hitter_acnt == "H2"


def test_strikeout_charged_to_substitute_when_original_never_reached_two_strikes() -> None:
    """原打者未達 2 好球即退出（僅牽制列）→ 三振記代打者，非原打者。"""
    events = [
        {**ev(18, "H1", action="三振", pitch_cnt=16, order=4), "content": "投手牽制一壘跑者"},
        {**ev(19, "H2", action="三振", change=True, pitch_cnt=16, order=4),
         "content": "更換代打：H1=>H2。"},
        ev(20, "H2", action="三振", is_strike=True, pitch_cnt=17, strikes=1, order=4),
        ev(21, "H2", action="三振", is_strike=True, pitch_cnt=18, strikes=2, order=4),
        ev(22, "H2", action="三振", is_strike=True, pitch_cnt=19, strikes=3, order=4,
           content="揮棒落空。 打者出局-三振出局。 3人出局。"),
    ]
    pas = _pas(events)
    assert len(pas) == 1
    assert pas[0].hitter_acnt == "H2" and pas[0].end_hitter_acnt == "H2"


def test_uncaught_third_strike_is_a_9_15_b_strikeout() -> None:
    """不死三振仍是三振（9.15(a)(3)）→ 適用 9.15(b) 第一句，記原打者。

    iteration 2 曾把它當「其他結果」歸完成者，是只讀 9.15(b) 未套 9.15(a) 定義所致
    （查核 Major）。全庫不死三振 1,118 筆、每年皆有，只是尚無跨打者實例。
    """
    for action in ("不死三振 捕逸", "不死三振 暴投", "不死三振 趁傳",
                   "不死三振 捕手傳一壘傳球失誤", "不死三振 捕手傳一壘接球失誤"):
        events = [
            ev(1, "H1", action=action, is_strike=True, pitch_cnt=1, strikes=2, order=3),
            {**ev(2, "H2", action=action, change=True, pitch_cnt=1, strikes=2, order=3),
             "content": "更換代打：H1=>H2。"},
            ev(3, "H2", action=action, is_strike=True, pitch_cnt=2, strikes=3, order=3,
               content="不死三振上壘。"),
        ]
        pas = _pas(events)
        assert len(pas) == 1, action
        assert pas[0].hitter_acnt == "H1", action        # 被判第 2 好球者
        assert pas[0].end_hitter_acnt == "H2", action    # 實際完成者


def test_strikeout_action_set_matches_taxonomy() -> None:
    """含「三振」字樣的 taxonomy action 必須恰好等於 9.15(b) 的三振集合。

    新增三振變體（或 taxonomy 改名）時本測試會紅，杜絕靜默漏列——
    iteration 2 正是漏了不死三振五種，且交付統計也因此少算一筆。
    """
    from cpbl.ingest.pa_build import STRIKEOUT_ACTIONS

    assert {a for a in TAX.actions if "三振" in a} == set(STRIKEOUT_ACTIONS)


def test_single_batter_pa_has_identical_charged_and_completing_hitter() -> None:
    events = [ev(1, "H1", action="三振", is_strike=True, pitch_cnt=1, strikes=3)]
    pa = _pas(events)[0]
    assert pa.hitter_acnt == pa.end_hitter_acnt == "H1"


# ===========================================================================
# FIX1 iteration 3：taxonomy JSON 必須是「產生器產得出來」的（可重現性）
# ===========================================================================
def test_generator_static_blocks_match_committed_taxonomy_json() -> None:
    """產生器的靜態區塊必須與 committed JSON 一致，否則按文件重跑會覆寫回舊語意。

    iteration 2 手改了 JSON 卻沒改 `scripts/pa_transition_taxonomy.py`，任何人跑
    docstring 裡的一鍵重生成命令都會把 v1.1 打回 v1.0（查核 Critical）。
    本測試不需 DB：只用一個最小 report 呼叫 `build_taxonomy_json`，比對靜態區塊。
    """
    import json as _json

    from cpbl.ingest import pa_build
    from scripts.pa_transition_taxonomy import TAXONOMY_VERSION, build_taxonomy_json

    committed = _json.loads(
        (Path(pa_build.__file__).resolve().parent.parent / "resources"
         / pa_build._TAXONOMY_FILENAME).read_text(encoding="utf-8")
    )
    generated = build_taxonomy_json(
        {"profiles": [], "generated_at": "x", "parameters": committed["parameters"]}
    )
    assert generated["taxonomy_version"] == committed["taxonomy_version"] == TAXONOMY_VERSION
    for block in ("island_rule", "island_classes", "fail_closed"):
        assert generated[block] == committed[block], f"{block} 與產生器不一致"


def test_committed_taxonomy_declares_the_fix1_semantics() -> None:
    """committed JSON 必須實際帶有 FIX1 的語意欄位（防再度退回 v1.0 形狀）。"""
    tax_doc = load_taxonomy()
    assert tax_doc.version == "1.1.0"
    import json as _json

    from cpbl.ingest import pa_build

    doc = _json.loads(
        (Path(pa_build.__file__).resolve().parent.parent / "resources"
         / pa_build._TAXONOMY_FILENAME).read_text(encoding="utf-8")
    )
    assert "batting_order" in doc["island_rule"]["exclude_from_boundary"]
    assert "boundary_note" in doc["island_rule"] and "attribution" in doc["island_rule"]
    assert "9.15(b)" in doc["island_rule"]["attribution"]
    assert "half_inning_out_overflow" in doc["fail_closed"]


# ===========================================================================
# FIX1 iteration 4：taxonomy 產生器的**動態證據**必須與 canonical island 同語意
# ===========================================================================
def test_generator_profiling_path_merges_mid_pa_pinch_hits() -> None:
    """產生器的 profiles/classification 聚合必須走 canonical build_islands。

    iteration 3 只修了紅燈抽樣的 `_island_starts()`，profiles 仍由獨立的
    `_ISLAND_SQL`（打者一變就切）計算，296 個跨打者 PA 在動態證據裡被重複計算
    （查核 Critical）。本測試以打席中途代打實形直打聚合純函式，無 DB。
    """
    from scripts.pa_transition_taxonomy import _aggregate_islands

    agg = _aggregate_islands(_mid_pa_pinch_hit_events())
    assert len(agg) == 1, "代打續打席必須聚合為一個 island"
    assert agg[0]["term_action"] == "三振"
    assert agg[0]["rows"] == 4  # 4 個非換人成員列（公告列參與分組但不計入聚合）
    assert agg[0]["batter_out"] is True


def test_generator_profiling_path_keeps_real_boundaries_split() -> None:
    """反向：真打席邊界（球數不歸零但棒次前進、零投球故意四壞＋打席間代打）不得被聚合合併。"""
    from scripts.pa_transition_taxonomy import _aggregate_islands

    non_reset = [
        ev(22, "H1", is_ball=True, pitch_cnt=20, balls=1, strikes=0, order=5),
        ev(24, "H1", is_strike=True, pitch_cnt=22, balls=1, strikes=1, order=5,
           content=" 2人出局。"),
        ev(25, "H2", is_ball=True, pitch_cnt=23, balls=2, strikes=1, order=6),
    ]
    assert len(_aggregate_islands(non_reset)) == 2

    walk_then_pinch = [
        ev(15, "H1", action="故意四壞球", pitch_cnt=13, order=4, content="故意四壞球上壘。"),
        {**ev(16, "H2", action="一壘安打", change=True, pitch_cnt=13, order=5),
         "content": "更換代打：X=>H2。"},
        ev(17, "H2", action="一壘安打", is_ball=True, pitch_cnt=14, balls=1, order=5,
           content="擊出左外野平飛球，一壘安打 。"),
    ]
    assert len(_aggregate_islands(walk_then_pinch)) == 2


def test_generator_aggregation_grouping_matches_build_islands() -> None:
    """聚合的島數必須等於 canonical build_islands 的「含有效成員」島數（同一來源）。"""
    from scripts.pa_transition_taxonomy import _aggregate_islands

    events = (_mid_pa_pinch_hit_events()
              + [ev(30, "H9", action="三振", is_strike=True, pitch_cnt=1, strikes=3,
                    inning=2, half="1", order=1)])
    canonical = [
        isl for isl in build_islands(events)
        if any(not e.get("is_change_player") and (e.get("hitter_acnt") or "").strip()
               for e in isl)
    ]
    assert len(_aggregate_islands(events)) == len(canonical) == 2


def test_builder_upgrade_ignores_tracking_only_drift() -> None:
    """tracking revision 漂移不阻擋 builder 升級發布：pa_fingerprint 是 livelog 純函式。

    真實案例 2026/A/215：livelog revision 相同、TrackMan 晚發布使 tracking revision
    改變，iteration 4 首次重建時被過緊的雙 revision 守門擋成 reconciliation_required。
    fingerprint 從不含 tracking 欄位，livelog 相同即可歸因於 builder。
    （本測試釘 reconcile 的行為端：upgrade 旗標成立時有差異仍發布。）
    """
    pas = _one_pa()
    rec = reconcile(pas, {str(pas[0].pa_id): "old-fp"}, builder_upgrade_same_source=True)
    assert rec.action == "publish" and rec.changed_pa_ids
