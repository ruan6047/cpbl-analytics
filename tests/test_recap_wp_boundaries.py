"""GAME-RECAP-WP-API1 邊界單元測試（純核心，無 DB）。

卡面驗收：換局、終場（收斂 0/1）、再見、和局（0.5）、延長（含 2024+ 突破僵局
規則差異）與不可靠狀態必須有唯一 canonical 行為；不可靠列保留事件但 WP/WPA
不可用（fail closed）。另釘住 wp_reliability metadata 與 research 報告事實一致。
"""

from __future__ import annotations

import pytest

from cpbl.api.routers import recap
from cpbl.api.routers.recap import enrich_items


@pytest.fixture(autouse=True)
def _clear_caches():
    recap._dist_cache.clear()
    recap._solver_cache.clear()
    yield
    recap._dist_cache.clear()
    recap._solver_cache.clear()


# ---------------------------------------------------------------------------
# 決定性 fake scorer：值由狀態唯一決定，方便逐位驗證鏈結語意
# ---------------------------------------------------------------------------
def fake_scorer(inning: int, vht: str, diff: int, bases: str, outs: int) -> float:
    v = (0.5 + 0.08 * diff + 0.01 * (inning - 1) + (0.02 if vht == "2" else 0.0)
         + 0.005 * outs + 0.03 * sum(1 for b in bases if b != "_"))
    return min(0.99, max(0.01, v))


def row(idx: int, state: str = "ready", *, inning: int = 1, half: str = "1",
        outs: int | None = 0, bases: tuple[str, ...] = (), away: int = 0,
        home: int = 0, hitter: str = "H") -> dict:
    return {
        "pa_id": f"pa-{idx}", "pa_index": idx, "state": state,
        "hitter_acnt": hitter, "start_pitcher_acnt": "P", "end_pitcher_acnt": "P",
        "result_action": "刺殺" if state == "ready" else None, "outcome_family": None,
        "pre_state": {"inning": inning, "half": half, "outs": outs,
                      "bases": list(bases), "away_score": away, "home_score": home},
    }


def wp_of(r: dict) -> float:
    pre = r["pre_state"]
    bases = (("1" if "1" in pre["bases"] else "_") + ("2" if "2" in pre["bases"] else "_")
             + ("3" if "3" in pre["bases"] else "_"))
    return round(fake_scorer(pre["inning"], pre["half"],
                             pre["home_score"] - pre["away_score"], bases, pre["outs"]), 4)


def enrich(rows: list[dict], *, completed: bool = True,
           final_outcome: float | None = 1.0) -> list[dict]:
    return enrich_items(rows, completed=completed, final_outcome=final_outcome,
                        scorer=fake_scorer)


# ---------------------------------------------------------------------------
# 換局：after 錨點 = 下一半局首打席的打席前狀態（自然銜接、無特例）
# ---------------------------------------------------------------------------
def test_half_inning_change_chains_to_next_pre_state() -> None:
    rows = [row(0, inning=1, half="1", outs=2), row(1, inning=1, half="2", outs=0)]
    items = enrich(rows, final_outcome=1.0)
    assert items[0]["home_wp_after"] == wp_of(rows[1])
    assert items[0]["wpa"] == round(items[0]["home_wp_after"] - items[0]["home_wp_before"], 4)


# ---------------------------------------------------------------------------
# 終場收斂：最後一個真實打席 after = 1（主勝）/ 0（客勝）/ 0.5（和局）
# ---------------------------------------------------------------------------
def test_final_convergence_home_win() -> None:
    items = enrich([row(0, inning=9, half="2", home=1)], final_outcome=1.0)
    assert items[-1]["home_wp_after"] == 1.0
    assert items[-1]["beneficiary_team"] == "home"


def test_final_convergence_away_win() -> None:
    items = enrich([row(0, inning=9, half="1", away=1)], final_outcome=0.0)
    assert items[-1]["home_wp_after"] == 0.0
    assert items[-1]["beneficiary_team"] == "away"


def test_final_convergence_tie() -> None:
    items = enrich([row(0, inning=12, half="2")], final_outcome=0.5)
    assert items[-1]["home_wp_after"] == 0.5


def test_walkoff_last_pa_converges_to_win() -> None:
    """再見：9 局下平手的最後打席 → after=1.0、wpa=1−before、受益主隊。"""
    r = row(0, inning=9, half="2", outs=1, bases=("2",))
    items = enrich([r], final_outcome=1.0)
    it = items[0]
    assert it["home_wp_after"] == 1.0
    assert it["wpa"] == round(1.0 - it["home_wp_before"], 4)
    assert it["beneficiary_team"] == "home"


def test_incomplete_game_last_pa_partial_final_unknown() -> None:
    items = enrich([row(0)], completed=False, final_outcome=None)
    it = items[0]
    assert it["wp_status"] == "partial"
    assert it["home_wp_before"] is not None
    assert it["home_wp_after"] is None and it["wpa"] is None
    assert it["wp_unavailable_reason"] == "final_unknown"


# ---------------------------------------------------------------------------
# 不可靠狀態：fail closed（保留事件列、WP 欄不可用並附原因）
# ---------------------------------------------------------------------------
def test_not_ready_states_fail_closed_but_rows_kept() -> None:
    rows = [row(0), row(1, state="truncated"), row(2, state="unreliable"),
            row(3, state="reconciliation_required"), row(4)]
    items = enrich(rows)
    assert len(items) == 5  # 事件列保留
    reasons = {i["pa_index"]: i["wp_unavailable_reason"] for i in items}
    assert reasons[1] == "pa_state_truncated"
    assert reasons[2] == "pa_state_unreliable"
    assert reasons[3] == "pa_state_reconciliation_required"
    for i in (1, 2, 3):
        assert items[i]["wp_status"] == "unavailable"
        assert items[i]["home_wp_before"] is None


def test_ready_with_incomplete_pre_state_fails_closed() -> None:
    items = enrich([row(0, outs=None)])
    assert items[0]["wp_status"] == "unavailable"
    assert items[0]["wp_unavailable_reason"] == "pre_state_incomplete"


def test_unreliable_next_pa_pre_state_still_anchors_previous() -> None:
    """不可靠打席的 pre_state 是有效狀態快照（可作前一打席的 after 錨點）；
    其自身 WPA 缺席 → WPA 總和不強行守恆（誠實揭露，不重分配）。"""
    rows = [row(0, outs=0), row(1, state="truncated", outs=1), row(2, outs=2)]
    items = enrich(rows)
    assert items[0]["home_wp_after"] == wp_of(rows[1])
    assert items[1]["wp_status"] == "unavailable"
    assert items[2]["wp_status"] == "available"


def test_next_pa_incomplete_pre_state_gives_partial() -> None:
    rows = [row(0), row(1, state="truncated", outs=None), row(2)]
    items = enrich(rows)
    assert items[0]["wp_status"] == "partial"
    assert items[0]["wp_unavailable_reason"] == "next_pa_state_incomplete"


# ---------------------------------------------------------------------------
# 延長 / 突破僵局：non_pa 佈局列不作錨點；(kind, season) 規則差異
# ---------------------------------------------------------------------------
def test_non_pa_tiebreak_row_skipped_as_anchor() -> None:
    """non_pa 佈局列快照在跑者佈局前（bases 空）→ 前一打席的 after 必須錨到
    下一個真實打席（含突破僵局跑者），否則延長局開局狀態被低估。"""
    rows = [
        row(0, inning=9, half="2", outs=2),                       # 9 局下最後打席
        row(1, state="non_pa", inning=10, half="1", outs=0),      # 佈局列：bases 空
        row(2, inning=10, half="1", outs=0, bases=("2",)),        # 10 局上首打席（二壘有人）
    ]
    items = enrich(rows)
    assert items[0]["home_wp_after"] == wp_of(rows[2])
    assert items[0]["home_wp_after"] != wp_of(rows[1])
    assert items[1]["wp_status"] == "unavailable"
    assert items[1]["wp_unavailable_reason"] == "non_pa_context"


def test_tiebreak_ruleset_changes_extra_inning_wp(monkeypatch) -> None:
    """2024+ 突破僵局：同一延長局狀態在 2023/2024 規則下 WP 必須不同
    （未來半局開局分布 空壘 vs 二壘有人）。"""
    dist = {
        ("1", "___", 0): [0.75, 0.15, 0.06, 0.03, 0.01, 0.0, 0.0],
        ("2", "___", 0): [0.72, 0.16, 0.07, 0.04, 0.01, 0.0, 0.0],
        ("1", "_2_", 0): [0.35, 0.40, 0.15, 0.07, 0.03, 0.0, 0.0],
        ("2", "_2_", 0): [0.30, 0.42, 0.17, 0.08, 0.03, 0.0, 0.0],
    }
    monkeypatch.setattr(recap, "_load_dist", lambda span, kind: dict(dist))
    s23, m23 = recap._get_scorer("A", 2023)
    s24, m24 = recap._get_scorer("A", 2024)
    assert m23["ruleset"] == "cap12,tie"
    assert m24["ruleset"] == "cap12,tb10,tie"
    wp23 = s23(10, "1", 0, "_2_", 0)
    wp24 = s24(10, "1", 0, "_2_", 0)
    assert wp23 != wp24


# ---------------------------------------------------------------------------
# WPA 算術一致性與 model_not_built
# ---------------------------------------------------------------------------
def test_wpa_equals_rounded_after_minus_before() -> None:
    rows = [row(i, inning=1 + i // 2, half="12"[i % 2], home=i % 3) for i in range(6)]
    for it in enrich(rows):
        if it["wp_status"] == "available":
            assert it["wpa"] == round(it["home_wp_after"] - it["home_wp_before"], 4)


def test_no_model_fails_closed_for_all_rows() -> None:
    items = enrich_items([row(0), row(1)], completed=True, final_outcome=1.0, scorer=None)
    assert all(i["wp_status"] == "unavailable" for i in items)
    assert all(i["wp_unavailable_reason"] == "model_not_built" for i in items)


# ---------------------------------------------------------------------------
# wp_reliability metadata：與 research 報告事實一致（本卡唯一 owner）
# ---------------------------------------------------------------------------
def test_wp_reliability_structure_and_semantics() -> None:
    for kind in ("A", "C", "D", "E"):
        rel = recap.wp_reliability(kind)
        assert rel["schema_version"] == "1.0.0"
        assert rel["semantics"] == "reference"
        assert rel["scope"] == kind
        assert rel["status"] == "unsupported"  # VAL1：全 scope unsupported
        assert rel["methodology"] == "/methodology#winprob"
        # 只引已 merge 報告；STRENGTH1 未 merge，不得引用
        assert rel["evidence"], "evidence 不可為空"
        assert not any("STRENGTH" in e for e in rel["evidence"])


def test_wp_reliability_distribution_sources_match_val1() -> None:
    scopes = recap.WP_RELIABILITY_SCOPES
    assert scopes["A"]["distribution_source"] == "own"
    assert scopes["D"]["distribution_source"] == "own"
    assert scopes["C"]["distribution_source"] == "borrowed"
    assert scopes["C"]["borrowed_from"] == "A"
    assert scopes["E"]["distribution_source"] == "borrowed"
    assert scopes["E"]["borrowed_from"] == "A"  # FIX1：E=一軍季後挑戰賽，借 A 非 D


def test_wp_reliability_facts_not_embellished() -> None:
    """關鍵數字釘住報告值（VAL1 §0/§3、FIX1 §2、CAL1 §0/§5）。"""
    scopes = recap.WP_RELIABILITY_SCOPES
    assert "±4–6pt" in scopes["A"]["known_bias"]
    assert "0.153" in scopes["A"]["known_bias"] and "0.245" in scopes["A"]["known_bias"]
    assert "時間平穩" in scopes["A"]["remediation"]  # CAL1 No-Go 機制
    assert "0.110" in scopes["C"]["validation"] and "25 場" in scopes["C"]["validation"]
    assert "+4.7pt" in scopes["D"]["validation"]
    assert "0.289" in scopes["E"]["validation"] and "13 場" in scopes["E"]["validation"]
    assert scopes["E"]["scope_label"] == "一軍季後挑戰賽"  # FIX1 修正後語意
