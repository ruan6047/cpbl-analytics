"""#207：「犧飛趁」（犧牲飛球上壘-趁傳）在 splits_calc／pa_sim／PA builder 的處理（無 DB）。

事件來源是 2026/A/347 8 局下（余謙整段登板）的真實 livelog 23 列，2026-09-25 以
READ ONLY 交易自本機 ``cpbl.game_livelog`` 取出，存於
``tests/fixtures/livelog_2026_A_347_b8.json``（欄位＝``pa_build._EVENT_COLS``）。
下方 box 數值抄自同場官方 ``batting_gamelog``／``pitching_gamelog``。
"""

from __future__ import annotations

import json
from collections import Counter
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

from cpbl.ingest import splits_calc
from cpbl.ingest.pa_build import STATE_READY, STATE_UNRELIABLE, load_taxonomy, plate_appearances
from cpbl.models.pa_sim import build_pa_snapshots, classify_action, events_from_rows

EVENTS = json.loads(
    (Path(__file__).parent / "fixtures" / "livelog_2026_A_347_b8.json").read_text(encoding="utf-8")
)
LIN = "0000003467"   # 林泓育（打者，犧飛趁）
YU = "0000006176"    # 余謙（投手，本場只投 8 局下）
SF_CHOICE_EVENT = "0820018000"  # 林泓育打席首事件

# 林泓育本場四個打席的真實終結列（batting_action_name, content）
LIN_TERMINALS = [
    ("游滾", "擊出內野滾地球， 打者-游擊手  傳一壘手刺殺出局。 1人出局。"),
    ("游滾", "擊出內野滾地球， 打者-游擊手  傳一壘手刺殺出局。 1人出局。"),
    ("全打", "擊出左外野高飛球，全壘打。3分打點。 二壘跑者林政華回本壘得分。 一壘跑者梁家榮回本壘得分。"),
    ("犧飛趁", "擊出右外野高飛球， 三壘跑者林政華回本壘得分。 一壘跑者梁家榮-右外野手  "
               "傳游擊手封殺出局 2人出局。犧牲飛球-右外野手 趁傳上一壘。1分打點。"),
]
LIN_BOX = {"plate_appearances": 4, "at_bats": 3, "hits": 1, "home_runs": 1, "sac_fly": 1, "rbi": 4}
YU_BOX = {"plate_appearances": 7, "hits": 3, "home_runs": 0, "sac_hit": 0, "sac_fly": 2,
          "bb": 0, "hbp": 0, "so": 0, "pitch_cnt": 19, "strikes": 14, "balls": 5}


def _with_action(events: list[dict], batting_action: str, action: str) -> list[dict]:
    """把林泓育打席的結果詞換成指定詞（負控：同形狀、未登錄的詞）。"""
    return [
        {**e, "batting_action_name": batting_action, "action_name": action}
        if e["hitter_acnt"] == LIN else e
        for e in events
    ]


# ---------------------------------------------------------------------------
# splits_calc
# ---------------------------------------------------------------------------
def test_batter_full_game_box_reconciles_with_sf_choice() -> None:
    total: Counter = Counter()
    for action, content in LIN_TERMINALS:
        for k, v in splits_calc.PA_OUTCOME[action].items():
            total[splits_calc._BAT_COLS[k]] += v
        total["rbi"] += sum(int(m.group(1)) for m in splits_calc._RBI.finditer(content))
    assert {k: total[k] for k in LIN_BOX} == LIN_BOX


def _run_calc_t2(monkeypatch: pytest.MonkeyPatch, events: list[dict]):
    rows = [
        (e["game_sno"], e["inning_seq"], e["visiting_home_type"], e["main_event_no"],
         e["hitter_acnt"], e["pitcher_acnt"], e["batting_order"], e["out_cnt"],
         e["first_base"], e["second_base"], e["third_base"],
         e["batting_action_name"], e["is_strike"], e["is_ball"],
         e["visiting_score"], e["home_score"], e["is_change_player"], e["content"])
        for e in events
    ]

    def execute(sql: str, _params=None):
        if "pitching_gamelog" in sql:
            data = [(347, "0000005604", "先發"), (347, YU, "最後一任")]
        elif "cpbl.games" in sql:
            data = [(347, date(2026, 9, 24), "樂天桃園")]
        else:
            data = rows
        return SimpleNamespace(fetchall=lambda: data)

    @contextmanager
    def fake_conn():
        yield SimpleNamespace(execute=execute)

    monkeypatch.setattr(splits_calc, "conn", fake_conn)
    monkeypatch.setattr(splits_calc, "_load_bio", dict)
    monkeypatch.setattr(splits_calc, "merge_plan", lambda *_a: (frozenset(), {}))
    return splits_calc.calc_t2(2026, "A", None, None)


def _group_total(table: dict, acnt: str, grp: str) -> Counter:
    total: Counter = Counter()
    for (who, g, _item), cnt in table.items():
        if who == acnt and g == grp:
            total.update(cnt)
    return total


def test_calc_t2_counts_sf_choice_and_reconciles_pitcher_box(monkeypatch) -> None:
    bat, pit, _gofo, diag = _run_calc_t2(monkeypatch, EVENTS)

    assert not diag["unknown_action"]
    lin = _group_total(bat, LIN, "4")  # 壘上情境家族：每 PA 恰一桶
    assert (lin["plate_appearances"], lin["at_bats"], lin["sac_fly"], lin["rbi"]) == (1, 0, 1, 1)
    assert lin["fly_outs"] == 1  # 沿用犧飛慣例，非官方逐場 FO 證明
    yu = _group_total(pit, YU, "5")
    assert {k: yu[k] for k in YU_BOX} == YU_BOX


def test_calc_t2_still_fails_closed_on_unregistered_lookalike(monkeypatch) -> None:
    events = _with_action(EVENTS, "犧飛野", "犧牲飛球上壘-野選")
    _bat, _pit, _gofo, diag = _run_calc_t2(monkeypatch, events)
    assert diag["unknown_action"] == Counter({"犧飛野": 1})  # build_splits 據此中止寫入


# ---------------------------------------------------------------------------
# pa_sim
# ---------------------------------------------------------------------------
def _sim_rows(events: list[dict]) -> list[dict]:
    return [
        {"event_no": int(e["main_event_no"]), "inning": e["inning_seq"],
         "half": e["visiting_home_type"], "hitter": e["hitter_acnt"],
         "pitcher": e["pitcher_acnt"], "first_base": e["first_base"],
         "second_base": e["second_base"], "third_base": e["third_base"],
         "outs": e["out_cnt"], "post_away": e["visiting_score"],
         "post_home": e["home_score"], "action": e["batting_action_name"],
         "is_change_player": e["is_change_player"]}
        for e in events
    ]


def test_pa_sim_sf_choice_is_other_reach_with_real_post_state() -> None:
    assert classify_action("犧飛趁") == "OTHER_REACH"
    snaps = [s for s in build_pa_snapshots(events_from_rows(_sim_rows(EVENTS))) if s.hitter == LIN]

    assert len(snaps) == 1
    s = snaps[0]
    assert s.result == "OTHER_REACH"
    assert (s.before.bases, s.before.outs, s.before.home_score) == ("1_3", 1, 5)
    # 下一打席（馬傑森）首事件：打者上一壘、一壘跑者被封殺、三壘跑者得分
    assert (s.after.bases, s.after.outs, s.after.home_score) == ("1__", 2, 6)
    assert s.runs_delta == 1


def test_pa_sim_fails_closed_on_unregistered_lookalike() -> None:
    assert classify_action("犧飛野") is None


# ---------------------------------------------------------------------------
# PA builder
# ---------------------------------------------------------------------------
def _pa_of(pas, hitter: str):
    (pa,) = [p for p in pas if p.hitter_acnt == hitter]
    return pa


def test_builder_sf_choice_is_ready_fielders_choice() -> None:
    pas = plate_appearances(2026, "A", 347, EVENTS, load_taxonomy())
    lin = _pa_of(pas, LIN)
    nxt = pas[pas.index(lin) + 1]

    assert lin.start_event_no == SF_CHOICE_EVENT
    assert (lin.state, lin.outcome_family) == (STATE_READY, "fielders_choice")
    assert (lin.pre_state["outs"], lin.pre_state["bases"]) == (1, ["1", "3"])
    assert lin.post_state["outs"] == 2
    # 下一打席起點＝打者站上一壘、2 出局
    assert (nxt.pre_state["outs"], nxt.pre_state["bases"]) == (2, ["1"])
    assert all(p.state == STATE_READY for p in pas)


def test_builder_still_fails_closed_on_unregistered_lookalike() -> None:
    events = _with_action(EVENTS, "犧飛野", "犧牲飛球上壘-野選")
    lin = _pa_of(plate_appearances(2026, "A", 347, events, load_taxonomy()), LIN)
    assert (lin.state, lin.island_class) == (STATE_UNRELIABLE, "unknown_action")
