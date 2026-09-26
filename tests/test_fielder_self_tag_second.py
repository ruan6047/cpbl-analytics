"""#208：「野手接球自踩壘包 二壘」在 PA builder 的處理（無 DB）。

事件來源是 2026/D/183 4 局下的真實 livelog 33 列，2026-09-26 以 READ ONLY 交易自本機
``cpbl.game_livelog`` 取出，存於 ``tests/fixtures/livelog_2026_D_183_b4.json``
（欄位＝``pa_build._EVENT_COLS``）。

taxonomy 1.3.0 只把這個**精確原詞**登錄為打者出局（``out``）：原文「打者出局-…二壘出局。
1分打點。2人出局」可證實打者出局，但「二壘」指壘包或野手未證實——本檔⛔ 不斷言任何
守備細節，也⛔ 不以前綴或近似詞放行（負控）。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cpbl.ingest.pa_build import (
    STATE_READY,
    STATE_UNRELIABLE,
    half_inning_out_violations,
    load_taxonomy,
    plate_appearances,
)

EVENTS = json.loads(
    (Path(__file__).parent / "fixtures" / "livelog_2026_D_183_b4.json").read_text(encoding="utf-8")
)
ACTION = "野手接球自踩壘包 二壘"
KAO = "0000007091"  # 高捷（打者，本打席 二滾）
KAO_START_EVENT = "0420014000"


def _with_action(events: list[dict], action: str) -> list[dict]:
    """把高捷打席的 action_name 換成指定詞（負控：同形狀、未登錄的詞）。"""
    return [{**e, "action_name": action} if e["hitter_acnt"] == KAO else e for e in events]


def _pa_of(pas, hitter: str):
    (pa,) = [p for p in pas if p.hitter_acnt == hitter]
    return pa


def test_taxonomy_registers_only_the_exact_phrase_as_batter_out() -> None:
    tax = load_taxonomy()
    assert tax.actions[ACTION] == {"role": "pa_terminal", "outcome_family": "out"}
    # 同族只有既有的「一壘」與本卡精確詞；不得出現通配或其他壘包變體
    assert sorted(a for a in tax.actions if a.startswith("野手接球自踩壘包")) == [
        "野手接球自踩壘包 一壘",
        ACTION,
    ]


def test_builder_fielder_self_tag_second_is_ready_out() -> None:
    pas = plate_appearances(2026, "D", 183, EVENTS, load_taxonomy())
    kao = _pa_of(pas, KAO)
    nxt = pas[pas.index(kao) + 1]

    assert kao.start_event_no == KAO_START_EVENT
    assert (kao.state, kao.island_class, kao.result_action, kao.outcome_family) == (
        STATE_READY, "completed_pa", ACTION, "out",
    )
    # 打席前 1 出局、二三壘有人；下一打席起點 2 出局、三壘有人，主隊 +1 分
    assert (kao.pre_state["outs"], kao.pre_state["bases"]) == (1, ["2", "3"])
    assert (nxt.pre_state["outs"], nxt.pre_state["bases"]) == (2, ["3"])
    assert nxt.pre_state["home_score"] - kao.pre_state["home_score"] == 1
    # 整個半局：8 個打席全 ready、打者出局 PA 恰 3（犧短＋本打席＋游滾），不變式不觸發
    assert len(pas) == 8
    assert all(p.state == STATE_READY for p in pas)
    assert half_inning_out_violations(pas) == []


# 內部空白差異（雙半形空白、全形空白、無空白）也算未登錄詞；前後空白則由既有
# ``pa_build._clean`` 正規化（原本就用來吃官網的「一壘安打 」），不是本卡新增的放行。
@pytest.mark.parametrize(
    "lookalike",
    [
        "野手接球自踩壘包 三壘",
        "野手接球自踩壘包",
        "野手接球自踩壘包二壘",
        "野手接球自踩壘包  二壘",
        "野手接球自踩壘包\u3000二壘",
    ],
)
def test_builder_still_fails_closed_on_unregistered_lookalike(lookalike: str) -> None:
    kao = _pa_of(plate_appearances(2026, "D", 183, _with_action(EVENTS, lookalike),
                                   load_taxonomy()), KAO)
    assert (kao.state, kao.island_class) == (STATE_UNRELIABLE, "unknown_action")


def test_outer_whitespace_is_normalized_by_existing_clean() -> None:
    kao = _pa_of(plate_appearances(2026, "D", 183, _with_action(EVENTS, f" {ACTION} "),
                                   load_taxonomy()), KAO)
    assert (kao.state, kao.result_action, kao.outcome_family) == (STATE_READY, ACTION, "out")
