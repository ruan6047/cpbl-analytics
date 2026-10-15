"""#289 審核 R1（第 2 輪）：登板「實際投球日期」所有輸入形狀 → 4A 負荷判定。

形狀清單與推導：~/.wf-evidence/cpbl-analytics/289/exec-1/r4/DATE-SHAPES.md（S01–S23）。
投球日只能由 games 的 game_date／delay_kind／orig_date 推出（pitching_gamelog 無日期欄），
這裡對 :func:`watch_reader.pitch_dates`＋:func:`watch_rules.bullpen_load` 逐形狀斷言。
判準：實際日期不可信 ⇒ 候選集合必須完整；不完整就無界 ⇒ 整窗灰，⛔ 被當成窗口外排除。
"""

from __future__ import annotations

import itertools
from datetime import date, timedelta

import pytest

from cpbl.playoffs import watch_reader as wrd
from cpbl.playoffs import watch_rules as wr
from cpbl.playoffs.watch_rules import DayCoverage

D = date(2026, 10, 17)                       # 目標場；窗口 10/14–10/17
IN, IN2 = date(2026, 10, 15), date(2026, 10, 16)
OUT, OUT2 = date(2026, 9, 1), date(2026, 9, 5)
WINDOW = [D - timedelta(days=k) for k in (3, 2, 1, 0)]


def row(gd, od=None, dk=None, sno=400, pitches: int | None = 30, exists=True):
    """pitching_gamelog⟕games 一列；exists=False ＝ 沒有 games 列（LEFT JOIN 全 NULL）。"""
    if not exists:
        gd = od = dk = None
    return {"year": 2026, "kind_code": "A", "game_sno": sno, "game_date": gd, "orig_date": od, "delay_kind": dk,
            "pitch_cnt": pitches, "inning_pitched_cnt": 1, "inning_pitched_div3": 0, "earned_runs": 0,
            "role_type": "中繼"}


def load(*rows):
    cov = {d: DayCoverage(d, True) for d in WINDOW}
    return wr.bullpen_load(D, [wrd.appearance_of(r) for r in rows], cov, tactical_role="終結")


def grey_days(r) -> dict[int, list[str]]:
    return {i["offset"]: i["reasons"] for i in r["incomplete"]}


ALL4 = {3: ["date_missing"], 2: ["date_missing"], 1: ["date_missing"], 0: ["date_missing"]}

# (形狀, 列, 期望等級, 期望灰日→理由)
SHAPES = [
    ("S01 缺 games 列", row(None, exists=False), "unknown", ALL4),
    ("S03 缺 game_date、orig_date 在窗口內", row(None, IN), "unknown", ALL4),
    ("S04 缺 game_date、orig_date 在窗口外（審核探針）", row(None, OUT), "unknown", ALL4),
    ("S07 可信、game_date 在窗口內", row(IN2), "high", {}),
    ("S08 可信、game_date 在窗口外", row(OUT), "low", {}),
    ("S09 延賽、orig_date 在窗口內、game_date 在窗口內", row(IN2, IN, "延賽"), "high", {}),
    ("S10 延賽、orig_date 與 game_date 都在窗口外", row(OUT2, OUT, "延賽"), "low", {}),
    ("S11 保留、[開賽,續賽] 全在窗口內", row(IN2, IN, "保留"), "unknown",
     {2: ["date_untrusted"], 1: ["date_untrusted"]}),
    ("S12 保留、區間跨入窗口（中間日也算候選）", row(IN, OUT, "保留"), "unknown",
     {3: ["date_untrusted"], 2: ["date_untrusted"]}),
    ("S13 保留、區間全在窗口外", row(OUT2, OUT, "保留"), "low", {}),
    ("S14 保留、單一候選日在窗口內", row(IN2, IN2, "保留"), "unknown", {1: ["date_untrusted"]}),
    ("S15 保留、單一候選日在窗口外", row(OUT2, OUT2, "保留"), "low", {}),
    ("S16 保留、缺 orig_date", row(IN, None, "保留"), "unknown", ALL4),
    ("S17 保留、orig_date 晚於 game_date", row(IN, IN2, "保留"), "unknown", ALL4),
    ("S18 值域外 delay_kind", row(OUT, None, "其他"), "unknown", ALL4),
]


@pytest.mark.parametrize(("name", "r", "level", "grey"), SHAPES, ids=[s[0][:3] for s in SHAPES])
def test_date_shape(name, r, level, grey):
    out = load(r)
    assert out["level"] == level, name
    assert grey_days(out) == grey, name
    if grey:
        assert out["complete"] is False and out["unattributed"][0]["pitches"] == 30


# S02／S05／S06 與其餘「缺 game_date」組合：delay_kind × orig_date 的完整笛卡兒積，全部無界整窗灰。
@pytest.mark.parametrize(("dk", "od"), list(itertools.product((None, "延賽", "保留", "其他"), (None, IN, OUT))))
def test_missing_game_date_is_unbounded_for_every_delay_kind_and_orig_date(dk, od):
    trusted, possible = wrd.pitch_dates(row(None, od, dk))
    assert trusted is False and possible == ()
    out = load(row(None, od, dk))
    assert out["level"] == "unknown" and grey_days(out) == ALL4


# 可信日期：orig_date 對 NULL／延賽 一律不影響（延賽的 orig_date 是原定日，不是投球日）。
@pytest.mark.parametrize(("dk", "od"), list(itertools.product((None, "延賽"), (None, IN, OUT))))
def test_actual_date_ignores_orig_date(dk, od):
    trusted, possible = wrd.pitch_dates(row(OUT2, od, dk))
    assert trusted is True and possible == ()
    assert load(row(OUT2, od, dk))["level"] == "low"


def test_reserve_candidates_are_the_full_interval():
    trusted, possible = wrd.pitch_dates(row(date(2026, 9, 5), date(2026, 9, 1), "保留"))
    assert trusted is False
    assert possible == tuple(date(2026, 9, d) for d in range(1, 6))


def test_s19_doubleheader_sums_one_day():
    out = load(row(IN2, sno=401, pitches=16), row(IN2, sno=402, pitches=16))
    assert out["metrics"]["P1"] == 32 and out["metrics"]["C"] == 1 and out["level"] == "high"


def test_s20_resumed_same_key_once_conflict_grey():
    assert load(row(IN2, sno=403), row(IN2, sno=403))["metrics"]["P1"] == 30
    conflict = load(row(IN2, sno=404, pitches=30), row(IN2, sno=404, pitches=10))
    assert conflict["level"] == "unknown" and grey_days(conflict) == {1: ["duplicate_conflict"]}


def test_s23_pitch_count_missing_grey():
    out = load(row(IN2, pitches=None))
    assert out["level"] == "unknown" and grey_days(out) == {1: ["pitch_count_missing"]}


def test_rest_days_unknown_when_any_appearance_unbounded():
    out = load(row(OUT2, sno=410), row(None, OUT, sno=411))
    assert out["full_rest_days"] is None and out["rest_unknown_reason"] == "date_missing"
