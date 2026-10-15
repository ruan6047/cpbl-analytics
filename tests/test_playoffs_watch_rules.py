"""#289 S08 WP1：4A 牛棚近期使用負荷純規則邊界（PRD v2 必要驗收案例「負荷」）。"""

from __future__ import annotations

import inspect
from datetime import date, timedelta

import pytest

from cpbl.playoffs import watch_rules as wr
from cpbl.playoffs.watch_rules import Appearance, DayCoverage

D = date(2026, 10, 17)


def day(k: int) -> date:
    return D - timedelta(days=k)


def full_cov() -> dict:
    return {day(k): DayCoverage(day(k), True) for k in (0, 1, 2, 3)}


_sno = iter(range(1, 10_000))


def app(k: int | None, pitches: int | None, *, kind="C", trusted=True, possible=(), outs=3, er: int | None = 0,
        sno=None, live=False, on: date | None = None) -> Appearance:
    d = on if on is not None else (day(k) if k is not None else None)
    return Appearance(game_key=(2026, kind, sno or next(_sno)), date=d, date_trusted=trusted,
                      pitch_cnt=pitches, outs=outs, er=er, possible_dates=tuple(possible), live=live)


def load(apps, cov=None, role=None):
    return wr.bullpen_load(D, apps, cov if cov is not None else full_cov(), tactical_role=role)


# —— 單日球數 P1／P0：14/15/29/30 ——————————————————————————————


@pytest.mark.parametrize(("pitches", "level"), [(14, "low"), (15, "medium"), (29, "medium"), (30, "high")])
def test_p1_boundaries(pitches, level):
    r = load([app(1, pitches)])
    assert r["level"] == level
    assert r["metrics"]["P1"] == pitches


@pytest.mark.parametrize("pitches", [14, 15, 29, 30])
def test_p0_boundaries(pitches):
    # P0 單看球數；Q=1 本身就會觸發中負荷，故 14 球以「同日球數不觸發 P0」檢查觸發清單。
    r = load([app(0, pitches)])
    metrics = {t["metric"] for t in r["triggers"]}
    assert ("P0" in metrics) == (pitches >= 15)
    if pitches >= 30:
        assert r["level"] == "high"


# —— S2：24/25/44/45；S3：39/40/59/60（不靠 P1、C 觸發） ——————————————


@pytest.mark.parametrize(("s2", "level"), [(24, "low"), (25, "medium"), (44, "medium"), (45, "high")])
def test_s2_boundaries(s2, level):
    # P1 固定 14（不觸發），其餘放 D−2；C=2 會觸發中，故比較只有 S2 的觸發集合。
    r = load([app(1, 14), app(2, s2 - 14)])
    assert r["metrics"]["S2"] == s2
    metrics = {t["metric"] for t in r["triggers"]}
    assert ("S2" in metrics) == (s2 >= 25)
    high = {t["metric"] for t in r["triggers"]} if r["level"] == "high" else set()
    assert ("S2" in high) == (level == "high")


@pytest.mark.parametrize(("s3", "level"), [(39, "low"), (40, "medium"), (59, "medium"), (60, "high")])
def test_s3_boundaries(s3, level):
    # D−1 無登板（C=0）、D−2 14 球、其餘放 D−3：S2=14 不觸發，只看 S3。
    r = load([app(2, 14), app(3, s3 - 14)])
    assert r["metrics"]["S2"] == 14
    assert r["metrics"]["S3"] == s3
    assert r["level"] == level
    if level != "low":
        assert [t["metric"] for t in r["triggers"]] == ["S3"]


# —— 連續日 C：1/2/3；當日 Q：0/1/2 ———————————————————————————


def test_consecutive_days():
    assert load([app(1, 5)])["metrics"]["C"] == 1
    assert load([app(1, 5)])["level"] == "low"
    r2 = load([app(1, 5), app(2, 5)])
    assert r2["metrics"]["C"] == 2 and r2["level"] == "medium"
    assert [t["metric"] for t in r2["triggers"]] == ["C"]
    r3 = load([app(1, 5), app(2, 5), app(3, 5)])
    assert r3["metrics"]["C"] == 3 and r3["level"] == "high" and r3["c_at_least"] is True
    # D−1 沒投 ⇒ C=0，即使 D−2、D−3 有投
    assert load([app(2, 5), app(3, 5)])["metrics"]["C"] == 0


def test_same_day_appearances_q():
    assert load([])["metrics"]["Q"] == 0
    assert load([])["level"] == "low"
    r1 = load([app(0, 5)])
    assert r1["metrics"]["Q"] == 1 and r1["level"] == "medium"
    r2 = load([app(0, 5), app(0, 5)])
    assert r2["metrics"]["Q"] == 2 and r2["level"] == "high"


def test_doubleheader_same_day_sums_pitches_one_day():
    r = load([app(1, 10), app(1, 12)])  # D−1 雙重賽兩場
    assert r["metrics"]["P1"] == 22
    assert r["metrics"]["C"] == 1  # 日期只算一天
    assert r["days"][2]["appearances"] == 2


def test_resumed_game_same_key_counted_once():
    a = app(1, 20, sno=777)
    r = load([a, a])
    assert r["metrics"]["P1"] == 20
    assert r["days"][2]["appearances"] == 1


def test_conflicting_duplicate_key_is_unknown():
    r = load([app(1, 20, sno=778), app(1, 25, sno=778)])
    assert r["level"] == "unknown"
    assert "duplicate_conflict" in r["incomplete"][0]["reasons"]


# —— 完整性：缺日期灰、無來源不綠、保留賽日期不可信、box 未送達 ————————————


def test_missing_date_coverage_is_unknown_not_green():
    cov = full_cov()
    del cov[day(2)]
    r = load([], cov)
    assert r["level"] == "unknown" and r["label"] == "未知"
    assert r["triggers"] == []
    assert r["incomplete"][0]["reasons"] == ["no_source"]


def test_no_source_at_all_is_not_green():
    r = load([], {})
    assert r["level"] == "unknown"
    assert len(r["incomplete"]) == 4


def test_incomplete_without_reason_defaults_to_no_source():
    r = load([], full_cov() | {day(1): DayCoverage(day(1), False)})
    assert r["incomplete"][0]["reasons"] == ["no_source"]


def test_box_missing_is_unknown_and_keeps_known_pitches():
    cov = full_cov() | {day(2): DayCoverage(day(2), False, ("box_missing",))}
    r = load([app(1, 40)], cov)  # 已知 P1=40（本來是紅），但完整性先判 ⇒ 灰
    assert r["level"] == "unknown"
    assert r["triggers"] == []
    assert r["metrics"]["P1"] == 40
    assert r["metrics"]["S2"] is None and r["metrics"]["C"] is None
    assert r["incomplete"][0]["text"] == [wr.REASON_TEXT["box_missing"]]


def test_reserve_game_date_untrusted_unknown_but_pitches_listed():
    a = app(None, 18, trusted=False, possible=(day(2), day(1)))
    r = load([a])
    assert r["level"] == "unknown"
    assert {i["offset"] for i in r["incomplete"]} == {1, 2}
    assert all(i["reasons"] == ["date_untrusted"] for i in r["incomplete"])
    assert r["unattributed"][0]["pitches"] == 18


def test_reserve_game_outside_window_does_not_grey():
    a = app(None, 18, trusted=False, possible=(day(20), day(19)))
    r = load([a])
    assert r["level"] == "low"
    assert r["unattributed"] == []


def test_reserve_game_unknown_dates_greys_whole_window():
    r = load([app(None, 18, trusted=False)])
    assert r["level"] == "unknown"
    assert len(r["incomplete"]) == 4


def test_pitch_count_missing_is_unknown():
    r = load([app(1, None)])
    assert r["level"] == "unknown"
    assert r["incomplete"][0]["reasons"] == ["pitch_count_missing"]


def test_live_unobserved_target_day_is_unknown():
    cov = full_cov() | {day(0): DayCoverage(day(0), False, ("live_unobserved",), live=True)}
    r = load([], cov)
    assert r["level"] == "unknown"
    assert r["incomplete"][0]["offset"] == 0


def test_live_pitches_marked_live():
    cov = full_cov() | {day(0): DayCoverage(day(0), True, live=True)}
    r = load([app(0, 16, live=True)], cov)
    assert r["live"] is True
    assert r["days"][3]["live"] is True
    assert r["level"] == "medium"


def test_no_official_game_is_evidenced_zero():
    # 該隊當日無正式場 ⇒ reader 給 complete=True ⇒ 0 球是有證據的 0 ⇒ 可綠
    r = load([])
    assert r["level"] == "low" and r["complete"] is True
    assert r["metrics"] == {"P0": 0, "P1": 0, "S2": 0, "S3": 0, "C": 0, "Q": 0}


# —— 跨 A/E/C：窗口內不分賽別 ————————————————————————————————


def test_cross_kind_window():
    r = load([app(3, 20, kind="A"), app(2, 20, kind="E"), app(1, 14, kind="C")])
    assert r["metrics"]["S3"] == 54 and r["metrics"]["S2"] == 34
    assert r["level"] == "high"  # C=3


# —— D4：輪值者本應綠改寫；紅／橘照常；灰仍灰 ——————————————————————


def test_rotation_green_becomes_starter_exempt():
    r = load([], role="輪值")
    assert r["level"] == "starter_exempt"
    assert r["label"] == "先發投手，不套用牛棚負荷燈號"


def test_rotation_red_orange_unchanged():
    assert load([app(1, 30)], role="輪值")["level"] == "high"
    assert load([app(1, 15)], role="輪值")["level"] == "medium"


def test_rotation_unknown_stays_unknown():
    assert load([], {}, role="輪值")["level"] == "unknown"


def test_non_rotation_roles_get_green():
    for role in ("終結", "勝利組", "長中繼", "unclassified", None):
        assert load([], role=role)["level"] == "low"


# —— 休息日（WP4 重用） ——————————————————————————————————————————


def test_full_rest_days_prd_example():
    assert wr.full_rest_days(date(2026, 10, 14), date(2026, 10, 9)) == 4
    assert wr.full_rest_days(date(2026, 10, 14), date(2026, 10, 13)) == 0
    assert wr.full_rest_days(date(2026, 10, 14), date(2026, 10, 14)) == 0


def test_last_pitch_date_counts_relief_in_between():
    apps = [app(None, 90, on=date(2026, 10, 9)), app(None, 12, on=date(2026, 10, 12))]
    last, reason = wr.last_pitch_date(apps, before=date(2026, 10, 14))
    assert last == date(2026, 10, 12) and reason is None


def test_last_pitch_date_reserve_ambiguity():
    apps = [app(None, 90, on=date(2026, 10, 9)),
            app(None, 12, trusted=False, possible=(date(2026, 10, 10), date(2026, 10, 11)))]
    assert wr.last_pitch_date(apps, before=date(2026, 10, 14)) == (None, "date_untrusted")
    old = [app(None, 90, on=date(2026, 10, 9)),
           app(None, 12, trusted=False, possible=(date(2026, 9, 1), date(2026, 9, 2)))]
    assert wr.last_pitch_date(old, before=date(2026, 10, 14)) == (date(2026, 10, 9), None)


def test_load_reports_rest_days():
    r = load([app(None, 20, on=date(2026, 10, 12))])
    assert r["last_pitch_date"] == "2026-10-12" and r["full_rest_days"] == 4


def test_recent_appearances_order():
    a1 = app(None, 1, on=date(2026, 10, 1))
    a2 = app(None, 2, on=date(2026, 10, 5))
    a3 = app(None, 3, on=date(2026, 10, 9))
    a4 = app(None, 4, on=date(2026, 10, 12))
    assert [a.pitch_cnt for a in wr.recent_appearances([a1, a3, a2, a4])] == [4, 3, 2]


# —— 連投 ERA ——————————————————————————————————————————————————


def test_consecutive_day_era_pools_raw_counts():
    apps = [
        app(None, 10, kind="A", on=date(2026, 9, 1), outs=3, er=0),
        app(None, 10, kind="A", on=date(2026, 9, 2), outs=3, er=1),   # 前一日有投 ⇒ 納入
        app(None, 10, kind="A", on=date(2026, 9, 3), outs=2, er=2),   # 納入
        app(None, 10, kind="A", on=date(2026, 9, 10), outs=6, er=0),  # 間隔 >1 ⇒ 不納入
    ]
    r = wr.consecutive_day_era(apps)
    assert r["appearances"] == 2 and r["outs"] == 5 and r["er"] == 3
    assert r["era"] == round(27 * 3 / 5, 2)
    assert r["ip"] == "1.2"


def test_consecutive_day_era_outs_zero_undefined():
    apps = [app(None, 10, kind="A", on=date(2026, 9, 1)),
            app(None, 10, kind="A", on=date(2026, 9, 2), outs=0, er=2)]
    r = wr.consecutive_day_era(apps)
    assert r["era"] is None and r["outs"] == 0 and r["complete"] is True


def test_consecutive_day_era_excludes_untrusted_dates():
    apps = [app(None, 10, kind="A", on=date(2026, 9, 1)),
            app(None, 10, kind="A", trusted=False, possible=(date(2026, 9, 2),))]
    r = wr.consecutive_day_era(apps)
    assert r["appearances"] == 0 and r["excluded_untrusted"] == 1 and r["era"] is None


def test_consecutive_day_era_missing_er_incomplete():
    apps = [app(None, 10, kind="A", on=date(2026, 9, 1)),
            app(None, 10, kind="A", on=date(2026, 9, 2), er=None)]
    r = wr.consecutive_day_era(apps)
    assert r["complete"] is False and r["era"] is None


# —— G12：門檻唯一、無參數、不可覆寫 ——————————————————————————————


def test_policy_version_and_thresholds_frozen():
    assert wr.POLICY_VERSION == "playoffs-policy/v2.0-proposed"
    assert dict(wr.THRESHOLDS["high"]) == {"P0": 30, "P1": 30, "S2": 45, "S3": 60, "C": 3, "Q": 2}
    assert dict(wr.THRESHOLDS["medium"]) == {"P0": 15, "P1": 15, "S2": 25, "S3": 40, "C": 2, "Q": 1}
    with pytest.raises(TypeError):
        wr.THRESHOLDS["high"]["P1"] = 99  # type: ignore[index]
    with pytest.raises(TypeError):
        wr.THRESHOLDS["low"] = {}  # type: ignore[index]


def test_no_threshold_parameters():
    params = set(inspect.signature(wr.bullpen_load).parameters)
    assert params == {"target_date", "appearances", "coverage", "tactical_role"}
    assert load([])["policy_version"] == wr.POLICY_VERSION


def test_module_is_pure():
    src = inspect.getsource(wr)
    for banned in ("import psycopg", "cpbl.db", "datetime.now", "date.today", "os.environ", "time.time"):
        assert banned not in src
