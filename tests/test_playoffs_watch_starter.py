"""#289 S08 WP4：A06 先發推測純規則邊界（PRD v2〈先發推測最低休息門檻〉）。"""

from __future__ import annotations

import inspect
from datetime import date, timedelta

import pytest

from cpbl.playoffs import watch_rules as wr
from cpbl.playoffs.watch_rules import Appearance, StarterPitcher

D = date(2026, 10, 14)

_sno = iter(range(1, 10_000))


def ap(on: date | None, *, start=False, outs: int | None = 18, trusted=True, possible=(), sno=None) -> Appearance:
    return Appearance(game_key=(2026, "C", sno or next(_sno)), date=on, date_trusted=trusted, pitch_cnt=90,
                      outs=outs, er=0, role_type="先發" if start else "中繼", possible_dates=tuple(possible))


def gs(rest: int, outs: int | None = 18) -> Appearance:
    """完整休 ``rest`` 日的先發登板（D 前 rest+1 日）。"""
    return ap(D - timedelta(days=rest + 1), start=True, outs=outs)


def p(pid: str, *apps: Appearance, role="輪值", roster=True, na=False) -> StarterPitcher:
    return StarterPitcher(player_id=pid, on_roster=roster, tactical_role=role, appearances=tuple(apps),
                          official_not_applicable=na)


def proj(*pitchers, clinch=False, elim=False):
    return wr.starter_projection(D, list(pitchers), clinch=clinch, facing_elimination=elim)


def ids(rows):
    return [r["player_id"] for r in rows]


# —— 休息日：10/9 登板、10/14 比賽＝4 日；3 日邊界；中間後援重算 ——————————————


def test_prd_example_oct9_to_oct14_is_main_candidate():
    r = proj(p("0000000001", ap(date(2026, 10, 9), start=True)))
    c = r["candidates"][0]
    assert c["full_rest_days"] == 4 and c["last_pitch_date"] == "2026-10-09"
    assert r["status"] == "single" and r["pick"] == "0000000001"


def test_three_days_rest_not_main_and_not_listed_without_clinch():
    r = proj(p("0000000001", gs(3)))
    assert r["candidates"] == [] and r["status"] == "undetermined" and r["pick"] is None
    assert r["short_rest"] == [] and r["relief"] == []
    assert r["excluded"] == [{"player_id": "0000000001", "reasons": ["insufficient_rest"],
                              "text": [wr.STARTER_EXCLUDE_TEXT["insufficient_rest"]], "full_rest_days": 3}]


def test_relief_in_between_recomputes_rest():
    # 10/9 先發（休 4 日）但 10/11 中繼後援 ⇒ 最後投球 10/11、休 2 日，不進主候選。
    r = proj(p("0000000001", ap(date(2026, 10, 9), start=True), ap(date(2026, 10, 11))))
    assert r["candidates"] == [] and r["excluded"][0]["full_rest_days"] == 2
    r2 = proj(p("0000000001", ap(date(2026, 10, 9), start=True), ap(date(2026, 10, 11))), elim=True)
    assert ids(r2["relief"]) == ["0000000001"] and r2["relief"][0]["last_pitch_date"] == "2026-10-11"
    assert r2["short_rest"] == []


def test_target_day_appearance_not_counted_as_last_pitch():
    # D 當日的登板（例如進行中）不算「最後實際投球」。
    r = proj(p("0000000001", gs(4), ap(D)))
    assert r["candidates"][0]["full_rest_days"] == 4


# —— 聽牌／淘汰才展開 3／2 日 ——————————————————————————————————————


@pytest.mark.parametrize(("clinch", "elim"), [(True, False), (False, True), (True, True)])
def test_clinch_or_elimination_expands_short_and_relief(clinch, elim):
    r = proj(p("0000000001", gs(4)), p("0000000002", gs(3)), p("0000000003", gs(2)), p("0000000004", gs(1)),
             clinch=clinch, elim=elim)
    assert r["expanded"] is True
    assert r["expand_basis"] == {"clinch": clinch, "facing_elimination": elim}
    assert ids(r["candidates"]) == ["0000000001"] and r["pick"] == "0000000001"
    assert ids(r["short_rest"]) == ["0000000002"]   # 恰 3 日；不升為主推測
    assert ids(r["relief"]) == ["0000000001", "0000000002", "0000000003"]   # ≥2 日
    assert [e["player_id"] for e in r["excluded"]] == ["0000000004"]


def test_not_expanded_hides_short_and_relief():
    r = proj(p("0000000001", gs(4)), p("0000000002", gs(3)), p("0000000003", gs(2)))
    assert r["expanded"] is False and r["short_rest"] == [] and r["relief"] == []
    assert [(e["player_id"], e["reasons"]) for e in r["excluded"]] == [
        ("0000000002", ["insufficient_rest"]), ("0000000003", ["insufficient_rest"])]


def test_short_rest_never_becomes_pick():
    r = proj(p("0000000002", gs(3)), clinch=True)
    assert ids(r["short_rest"]) == ["0000000002"]
    assert r["candidates"] == [] and r["pick"] is None and r["status_label"] == "候選未定"


def test_five_days_rest_is_not_short():
    r = proj(p("0000000001", gs(5)), clinch=True)
    assert r["short_rest"] == [] and ids(r["candidates"]) == ["0000000001"]


# —— 資格：30 日先發證據、輪值（opener）、名單、日期可核實 ————————————————


def test_no_recent_start_within_30_days_excluded():
    # 先發在 D−31，之後只有後援（休 4 日）：不進主候選，保留於 excluded 並說明。
    old = ap(D - timedelta(days=31), start=True)
    r = proj(p("0000000001", old, ap(D - timedelta(days=5))))
    assert r["candidates"] == []
    assert r["excluded"][0]["reasons"] == ["no_recent_start"]
    assert r["excluded"][0]["text"] == [wr.STARTER_EXCLUDE_TEXT["no_recent_start"]]


def test_start_exactly_30_days_ago_counts():
    edge = ap(D - timedelta(days=30), start=True)
    r = proj(p("0000000001", edge))
    assert ids(r["candidates"]) == ["0000000001"]


def test_untrusted_start_is_not_evidence():
    r = proj(p("0000000001", ap(D - timedelta(days=10), start=True, trusted=False, possible=(D - timedelta(days=40),)),
               ap(D - timedelta(days=6))))
    assert "no_recent_start" in r["excluded"][0]["reasons"]


def test_opener_gs_without_rotation_role_not_main():
    for role in ("長中繼", "勝利組", "終結", None):
        r = proj(p("0000000001", gs(5), role=role))
        assert r["candidates"] == [] and r["pick"] is None
        assert r["excluded"][0]["reasons"] == ["not_rotation"]
    r = proj(p("0000000001", gs(5), role="長中繼"), clinch=True)
    assert r["short_rest"] == [] and r["relief"] == []


def test_rotation_without_start_evidence_not_main():
    r = proj(p("0000000001", ap(D - timedelta(days=6))))
    assert r["candidates"] == [] and r["excluded"][0]["reasons"] == ["no_recent_start"]


def test_not_on_roster_and_official_not_applicable_excluded():
    r = proj(p("0000000001", gs(5), roster=False), p("0000000002", gs(5), na=True))
    assert r["candidates"] == []
    assert [e["reasons"] for e in r["excluded"]] == [["not_on_roster"], ["official_not_applicable"]]


def test_unverifiable_last_pitch_date_excluded():
    # 保留賽可能日期晚於最後可信先發 ⇒ 最後投球日不可核實。
    reserve = ap(None, trusted=False, possible=(D - timedelta(days=4), D - timedelta(days=2)))
    r = proj(p("0000000001", gs(6), reserve), clinch=True)
    assert r["candidates"] == [] and r["relief"] == []
    assert r["excluded"][0]["reasons"] == ["date_untrusted"] and r["excluded"][0]["full_rest_days"] is None


def test_duplicate_conflict_excluded():
    a = ap(D - timedelta(days=6), start=True, sno=9001)
    b = Appearance(game_key=a.game_key, date=a.date, date_trusted=True, pitch_cnt=50, outs=9, er=0, role_type="先發")
    r = proj(p("0000000001", a, b))
    assert "duplicate_conflict" in r["excluded"][0]["reasons"]


# —— 排序、並列、至多 3 人 ——————————————————————————————————————————


def test_ranking_rest_then_median_outs_then_id():
    r = proj(p("0000000003", gs(5, outs=15)), p("0000000001", gs(4, outs=21)), p("0000000002", gs(5, outs=18)))
    assert ids(r["candidates"]) == ["0000000002", "0000000003", "0000000001"]
    assert r["pick"] == "0000000002" and r["status"] == "single" and r["tied_top"] == []


def test_median_of_last_three_starts():
    d = lambda k: D - timedelta(days=k)  # noqa: E731
    apps = [ap(d(25), start=True, outs=27), ap(d(20), start=True, outs=12),
            ap(d(15), start=True, outs=15), ap(d(10), start=True, outs=21)]
    r = proj(p("0000000001", *apps))
    c = r["candidates"][0]
    assert c["recent_start_outs_median"] == 15   # 最近 3 次 21/15/12；第 4 次 27 不計
    assert [s["outs"] for s in c["recent_starts"]] == [21, 15, 12]


def test_median_ignores_relief_outs():
    r = proj(p("0000000001", ap(D - timedelta(days=12), start=True, outs=18), ap(D - timedelta(days=8), outs=3)))
    assert r["candidates"][0]["recent_start_outs_median"] == 18


def test_tie_on_first_two_keys_is_undetermined():
    r = proj(p("0000000002", gs(5, outs=18)), p("0000000001", gs(5, outs=18)), p("0000000003", gs(4, outs=24)))
    assert r["status"] == "undetermined" and r["status_label"] == "候選未定" and r["pick"] is None
    assert r["tied_top"] == ["0000000001", "0000000002"]
    assert ids(r["candidates"]) == ["0000000001", "0000000002", "0000000003"]   # ID 只作顯示順序


def test_tie_broken_by_median_is_single():
    r = proj(p("0000000002", gs(5, outs=19)), p("0000000001", gs(5, outs=18)))
    assert r["pick"] == "0000000002" and r["status"] == "single"


def test_unknown_median_cannot_win_or_be_beaten_at_same_rest():
    r = proj(p("0000000001", gs(5, outs=None)), p("0000000002", gs(5, outs=18)))
    assert r["pick"] is None and r["status"] == "undetermined"
    assert set(r["tied_top"]) == {"0000000001", "0000000002"}
    solo = proj(p("0000000001", gs(5, outs=None)))
    assert solo["pick"] is None and solo["tied_top"] == ["0000000001"]
    ahead = proj(p("0000000001", gs(6, outs=18)), p("0000000002", gs(5, outs=None)))
    assert ahead["pick"] == "0000000001"


def test_at_most_three_candidates_per_team():
    r = proj(*(p(f"000000000{i}", gs(4 + i, outs=18)) for i in range(1, 6)), clinch=True)
    assert len(r["candidates"]) == 3 and r["main_total"] == 5
    assert ids(r["candidates"]) == ["0000000005", "0000000004", "0000000003"]
    short = proj(*(p(f"000000000{i}", gs(3, outs=10 + i)) for i in range(1, 6)), clinch=True)
    assert len(short["short_rest"]) == 3 and ids(short["short_rest"])[0] == "0000000005"


def test_no_candidates_is_undetermined():
    r = proj()
    assert r["status"] == "undetermined" and r["candidates"] == [] and r["tied_top"] == []


# —— G12：門檻固定、版本化、無參數；模組純度 ——————————————————————————————


def test_starter_thresholds_frozen_and_versioned():
    assert dict(wr.STARTER_REST) == {"main": 4, "short": 3, "relief": 2}
    assert wr.STARTER_EVIDENCE_DAYS == 30 and wr.STARTER_MAX_CANDIDATES == 3
    with pytest.raises(TypeError):
        wr.STARTER_REST["main"] = 5  # type: ignore[index]
    assert proj()["policy_version"] == wr.POLICY_VERSION == "playoffs-policy/v2.0-proposed"


def test_no_threshold_parameters():
    params = set(inspect.signature(wr.starter_projection).parameters)
    assert params == {"target_date", "pitchers", "clinch", "facing_elimination"}
    assert set(inspect.signature(wr.starter_facts).parameters) == {"target_date", "pitcher"}
