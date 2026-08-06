"""GAME-RECAP-WP-VAL1 驗證 harness 離線測試（無 DB）。

核心合約：
1. legacy 規則（12 局和局、無突破僵局）下，規則參數化解算器與生產
   winprob._we_solver / wp_state 逐值相等——確保 walk-forward 結果差異
   只能來自時間切分，不是實作漂移。
2. 規則變體（突破僵局、無和局）行為方向正確。
3. 記憶體快照機器對合成事件的抽取語意正確（末半局排除、rest<0 略過、
   打席去重、outs 夾 0..2）。
4. 指標與 Go/No-Go verdict 邏輯。
5. （ML-WP-VAL-RESAMPLE1）評估樣本的局面分差取**打席前**比分：由事件流解出，
   不讀受污染的 `pre_state` 比分欄；解不出來 fail closed。
"""

from __future__ import annotations

import pytest

from cpbl.models.winprob import _we_solver, wp_state
from cpbl.models.winprob_val import (
    PRE_SCORE_SOURCES,
    THRESHOLDS,
    RuleSet,
    brier_constant,
    dist_from_counts,
    iter_half_pa_records,
    load_eval_season,
    metrics,
    ruleset_for,
    verdict_for,
    we_solver_rules,
    wp_state_rules,
)

LEGACY = RuleSet(max_inning=12, tiebreak_from=None, tie_allowed=True)


def _dist() -> dict:
    return {
        ("1", "___", 0): [0.55, 0.20, 0.12, 0.07, 0.03, 0.02, 0.01],
        ("2", "___", 0): [0.50, 0.22, 0.13, 0.08, 0.04, 0.02, 0.01],
        ("1", "_2_", 0): [0.30, 0.30, 0.20, 0.10, 0.05, 0.03, 0.02],
        ("2", "_2_", 0): [0.28, 0.31, 0.21, 0.10, 0.05, 0.03, 0.02],
        ("1", "1__", 1): [0.60, 0.18, 0.11, 0.06, 0.03, 0.01, 0.01],
        ("2", "12_", 2): [0.70, 0.14, 0.09, 0.04, 0.02, 0.01, 0.00],
    }


def test_legacy_solver_matches_production_everywhere():
    d = _dist()
    we_top_v, we_bot_v = we_solver_rules(d, LEGACY)
    we_top_p, we_bot_p = _we_solver(d[("1", "___", 0)], d[("2", "___", 0)])
    for i in range(1, 13):
        for diff in range(-15, 16):
            assert we_top_v(i, diff) == we_top_p(i, diff), (i, diff, "top")
            assert we_bot_v(i, diff) == we_bot_p(i, diff), (i, diff, "bot")


def test_legacy_wp_state_matches_production():
    d = _dist()
    we_top_v, we_bot_v = we_solver_rules(d, LEGACY)
    we_top_p, we_bot_p = _we_solver(d[("1", "___", 0)], d[("2", "___", 0)])
    cases = [
        (1, "1", 0, "___", 0), (5, "2", -2, "1__", 1), (9, "2", 0, "12_", 2),
        (9, "1", 1, "___", 0), (11, "2", -1, "_2_", 0), (12, "2", 0, "___", 2),
        (14, "1", 3, "___", 0),   # inning 超界夾到 cap
        (7, "2", 2, "1_3", 1),    # dist 無此狀態 → 退回空壘分布（兩實作同語意）
    ]
    for inning, vht, diff, bases, outs in cases:
        got = wp_state_rules(d, we_top_v, we_bot_v, LEGACY, inning, vht, diff, bases, outs)
        want = wp_state(d, we_top_p, we_bot_p, inning, vht, diff, bases, outs)
        assert got == want, (inning, vht, diff, bases, outs)
        assert 0.0 <= got <= 1.0


def test_tiebreak_reduces_tie_mass_in_extras():
    d = _dist()
    tb = RuleSet(max_inning=12, tiebreak_from=10, tie_allowed=True)
    we_top_l, _ = we_solver_rules(d, LEGACY)
    we_top_t, _ = we_solver_rules(d, tb)
    w_l, t_l = we_top_l(10, 0)
    w_t, t_t = we_top_t(10, 0)
    assert t_t < t_l          # 突破僵局 → 得分變多 → 和局質量下降
    assert w_l + t_l <= 1.0 + 1e-9 and w_t + t_t <= 1.0 + 1e-9
    # 第 9 局形式上仍用空壘開局分布（但延長連鎖不同 → 不要求相等）
    assert we_top_t(1, 0)[0] > 0


def test_no_tie_ruleset_leaves_negligible_tie_mass():
    d = _dist()
    c_rules = ruleset_for("C", 2025)
    assert not c_rules.tie_allowed
    we_top_c, _ = we_solver_rules(d, c_rules)
    w, t = we_top_c(1, 0)
    assert t < 0.01           # cap 內未分勝負殘餘質量須可忽略
    assert 0.4 < w + 0.5 * t < 0.6


def test_ruleset_eras():
    assert ruleset_for("A", 2023) == RuleSet(12, None, True)
    assert ruleset_for("A", 2024) == RuleSet(12, 10, True)
    assert ruleset_for("C", 2023) == RuleSet(20, None, False)
    assert ruleset_for("D", 2018) == RuleSet(9, None, True)
    assert ruleset_for("D", 2019) == RuleSet(10, None, True)
    assert ruleset_for("D", 2024) == RuleSet(9, None, True)
    assert ruleset_for("D", 2025) == RuleSet(10, 10, True)
    assert not ruleset_for("E", 2024).tie_allowed
    # FIX1：E=一軍季後挑戰賽——無突破僵局（2025 唯一 10 局場空壘開局實證），
    # 任何年份不得借二軍 2025 突破僵局規則
    assert ruleset_for("E", 2025) == RuleSet(20, None, False)
    assert ruleset_for("E", 2024) == RuleSet(20, None, False)


def test_train_proxy_pairs_postseason_with_same_level_regular():
    """FIX1：季後 scope 的訓練 proxy 必須借同軍例行賽（E 誤配 D 是已修缺陷）。"""
    from cpbl.models.winprob_val import TRAIN_PROXY

    assert TRAIN_PROXY == {"A": "A", "C": "A", "D": "D", "E": "A"}


def _ev(no, inning, vht, order, out_cnt, hitter, vs, hs, *, first=None, change=False):
    return {
        "main_event_no": str(no), "inning_seq": inning, "visiting_home_type": vht,
        "batting_order": order, "out_cnt": out_cnt, "is_change_player": change,
        "hitter_acnt": hitter, "first_base": first, "second_base": None,
        "third_base": None, "visiting_score": vs, "home_score": hs,
    }


def test_iter_half_pa_records_semantics():
    events = [
        # 1 上：兩打席，半局得 1 分（得分發生於 V1 打席內：該列事件後比分 1-0）
        _ev(1, 1, "1", 1, 0, "V1", 1, 0),
        _ev(2, 1, "1", 2, 1, "V2", 1, 0, first="V1"),
        _ev(3, 1, "1", 2, 1, None, 1, 0),            # 無打者列 → 不成打席
        # 1 下：一打席 + 更換列（排除）+ 同打者重複列（去重）
        _ev(4, 1, "2", 1, 0, "H1", 1, 0),
        _ev(5, 1, "2", 1, 0, "H1", 1, 0),
        _ev(6, 1, "2", 2, 1, "H2", 1, 0, change=True),
        # 2 上（末半局 → 整半局排除）
        _ev(7, 2, "1", 3, 0, "V3", 1, 2),
    ]
    recs = iter_half_pa_records(events)
    assert recs == [
        ("1", "___", 0, 1),      # V1：打席前 0-0，半局終 1 分 → rest 1
        ("1", "1__", 1, 0),      # V2：打席前已 1 分入帳 → rest 0
        ("2", "___", 0, 0),      # H1：一下未得分（H1 重複列已去重）
    ]


def test_dist_from_counts_threshold_and_rounding():
    from collections import Counter
    per_year = {2020: Counter({("1", "___", 0, 0): 20, ("1", "___", 0, 1): 10,
                               ("2", "___", 0, 0): 10})}
    dist = dist_from_counts(per_year, 2020, 2020)
    assert ("1", "___", 0) in dist          # n=30 達門檻
    assert ("2", "___", 0) not in dist      # n=10 未達
    assert dist[("1", "___", 0)][0] == round(20 / 30, 5)


def test_metrics_and_baseline():
    scored = [(0.9, 1.0, False, 1), (0.8, 1.0, False, 1), (0.2, 0.0, False, 2),
              (0.1, 0.0, False, 2), (0.55, 0.5, True, 3)]
    m = metrics(scored)
    assert m["n_pa"] == 5
    assert m["n_games"] == 3
    assert 0 <= m["brier"] < 0.05
    assert m["ece_weighted"] >= 0
    m_reg = metrics(scored, exclude_irregular=True)
    assert m_reg["n_pa"] == 4
    assert brier_constant(scored, 0.5) > m["brier"]


def test_cluster_bootstrap_wider_than_iid_for_correlated_games():
    """同場打席共享賽果 → 叢集 SE 遠大於逐 PA binomial SE。"""
    import random
    rng = random.Random(7)
    scored = []
    for g in range(60):                       # 60 場、每場 30 打席、bin 固定
        y = 1.0 if rng.random() < 0.5 else 0.0
        scored += [(0.55, y, False, g)] * 30
    m = metrics(scored, bootstrap=True)
    b5 = next(d for d in m["deciles"] if d["bin"] == 5)
    iid_se = (0.25 / b5["n"]) ** 0.5          # 天真逐 PA SE ≈ 0.012
    assert b5["dev_se"] > 3 * iid_se          # 叢集 SE ≈ sqrt(.25/60) ≈ 0.065


def _season(year, *, ece=0.01, brier=0.20, maxdev=0.03, n=8000, cov=1.0, base=0.24,
            sig=()):
    return {
        "year": year, "coverage": cov,
        "walk_forward": {"n_pa": n, "brier": brier, "ece_weighted": ece,
                         "decile_max_dev": maxdev, "significant_bins": list(sig)},
        "baseline_home_const": {"brier": base},
    }


def _pooled(*, n=40000, ece=0.01, deciles=()):
    return {"n_pa": n, "n_games": n // 75, "brier": 0.15, "ece_weighted": ece,
            "decile_max_dev": 0.02, "deciles": list(deciles),
            "baseline_home_const_brier": 0.24}


def test_verdict_v2_supported_and_hard_failures():
    ok = verdict_for("A", [_season(2024), _season(2025)], _pooled())
    assert ok["status"] == "supported"
    # v1 點估計超標只進 reference，不再構成硬性失敗
    v1_only = verdict_for("A", [_season(2024, ece=0.04, maxdev=0.09)], _pooled())
    assert v1_only["status"] == "supported"
    assert v1_only["v1_flags"]
    worse_than_base = verdict_for("A", [_season(2024, brier=0.25, base=0.24)], _pooled())
    assert worse_than_base["status"] == "unsupported"
    low_cov = verdict_for("A", [_season(2024, cov=0.9)], _pooled())
    assert low_cov["status"] == "unsupported"


def test_verdict_v2_pooled_significant_bias():
    big = {"bin": 5, "pred": 0.55, "actual": 0.50, "n": 5000,
           "dev_ci": [0.031, 0.07], "dev_se": 0.01}
    hard = verdict_for("A", [_season(2024)], _pooled(deciles=[big]))
    assert hard["status"] == "unsupported"
    bounded = {"bin": 5, "pred": 0.52, "actual": 0.50, "n": 5000,
               "dev_ci": [0.005, 0.036], "dev_se": 0.008}
    ok = verdict_for("A", [_season(2024)], _pooled(deciles=[bounded]))
    assert ok["status"] == "supported"
    assert any("受控" in d for d in ok["disclosure"])


def test_verdict_proxy_scopes_capped_at_warning():
    ok = verdict_for("C", [_season(2024, n=400)], _pooled(n=1600))
    assert ok["status"] == "proxy_with_warning"
    small = verdict_for("D", [_season(2024, n=3000)], _pooled(n=3000))
    assert small["status"] == "proxy_with_warning"     # 樣本不足亦不得標 supported
    assert THRESHOLDS["min_season_pa"] == 5000


def test_verdict_proxy_requires_minimum_pooled_evidence():
    bad = verdict_for("C", [_season(2024, n=400)],
                      _pooled(n=1600, ece=THRESHOLDS["proxy_pooled_ece_max"] + 0.01))
    assert bad["status"] == "unsupported"              # 池化嚴重失準 → 不得掛警示上線


# ===========================================================================
# ML-WP-VAL-RESAMPLE1：評估樣本的打席前比分
# ===========================================================================
_FULL = {"inning": 5, "half": "1", "outs": 0, "bases": []}


class _EvalCursor:
    """`load_eval_season()` 的三段查詢：完成場、published PA、逐球事件流。"""

    def __init__(self, games, pas, livelog):
        # games:   [(sno, home_score, away_score, delay_kind, max_inn), ...]
        # pas:     [(sno, state, pre_state, pa_index, start_event_no), ...]
        # livelog: [(sno, main_event_no, visiting_score, home_score), ...]
        self._games, self._pas, self._livelog = games, pas, livelog
        self._rows: list = []

    def execute(self, sql, params=None):
        if "FROM cpbl.games g " in sql:
            self._rows = list(self._games)
        elif "FROM cpbl.game_livelog WHERE" in sql:
            self._rows = list(self._livelog)
        elif "FROM cpbl.game_plate_appearances" in sql:
            self._rows = list(self._pas)
        else:
            raise AssertionError(f"未預期的查詢：{sql[:70]}")

    def fetchall(self):
        return self._rows


def _first_pitch_hr_fixture():
    """本卡病灶的最小重現。

    一場 1:0 主隊勝。第 2 個打席是**主隊**首球陽春全壘打，起始列＝終結列，故
    canonical `pre_state` 記到的已是得分**後**的 1:0；正確的打席前比分是 0:0。
    事件 "e1"（前一個打席）與 "e2"（全壘打）都在事件流裡。
    """
    games = [(1, 1, 0, None, 9)]
    pre_before = {**_FULL, "away_score": 0, "home_score": 0}
    pre_polluted = {**_FULL, "away_score": 0, "home_score": 1}   # ← 事件後快照
    pas = [(1, "ready", pre_before, 1, "e1"),
           (1, "ready", pre_polluted, 2, "e2")]
    # livelog 比分欄是事件**後**快照：e1 之後仍 0:0，e2 之後 0:1（主隊得 1 分）
    livelog = [(1, "e1", 0, 0), (1, "e2", 0, 1)]
    return games, pas, livelog


def test_eval_sample_uses_pre_pa_scores_not_the_polluted_snapshot():
    """全壘打打席自己的局面分差必須是 0，不是 +1（那一分是它造成的，不是它面對的）。"""
    games, pas, livelog = _first_pitch_hr_fixture()
    season = load_eval_season(_EvalCursor(games, pas, livelog), "A", 2026)
    assert [p["diff"] for p in season["pas"]] == [0, 0]
    assert season["pre_score_source"] == "events"


def test_legacy_pre_state_source_reproduces_the_contaminated_diff():
    """舊讀法必須**仍可重現**受污染的值——A/B 對照要能量出差異，不能兩邊都已修好。"""
    games, pas, livelog = _first_pitch_hr_fixture()
    season = load_eval_season(_EvalCursor(games, pas, livelog), "A", 2026,
                              pre_score_source="pre_state")
    assert [p["diff"] for p in season["pas"]] == [0, 1]   # ← 病灶：+1 是自己打出來的
    assert season["pre_score_source"] == "pre_state"


def test_scores_between_plate_appearances_are_still_carried():
    """打席**之間**造成得分的事件（盜壘／暴投）不得被吃掉——舊讀法在這種形狀碰巧正確，
    修法不能為了修 A 形狀而弄壞 B 形狀。"""
    games = [(1, 1, 0, None, 9)]
    pas = [(1, "ready", {**_FULL, "away_score": 0, "home_score": 0}, 1, "e1"),
           (1, "ready", {**_FULL, "away_score": 0, "home_score": 1}, 2, "e3")]
    # e2 是打席之間的暴投得分（不是任何打席的起始列）
    livelog = [(1, "e1", 0, 0), (1, "e2", 0, 1), (1, "e3", 0, 1)]
    season = load_eval_season(_EvalCursor(games, pas, livelog), "A", 2026)
    assert [p["diff"] for p in season["pas"]] == [0, 1]


def test_unresolved_pre_score_fails_closed_and_is_counted():
    """起始事件對不回事件流 → 排除且獨立計數，**不得**退回 `pre_state` 的污染值。"""
    games = [(1, 1, 0, None, 9)]
    pas = [(1, "ready", {**_FULL, "away_score": 0, "home_score": 0}, 1, "e1"),
           (1, "ready", {**_FULL, "away_score": 0, "home_score": 1}, 2, "MISSING")]
    livelog = [(1, "e1", 0, 0)]
    season = load_eval_season(_EvalCursor(games, pas, livelog), "A", 2026)
    assert [p["diff"] for p in season["pas"]] == [0]
    assert season["pa_state_counts"]["ready_pre_score_unresolved"] == 1
    # 舊讀法沒有這個分支（它永遠讀得到 pre_state）——對照組樣本數因此不同，
    # A/B 報表必須把這件事顯式列出來
    legacy = load_eval_season(_EvalCursor(games, pas, livelog), "A", 2026,
                              pre_score_source="pre_state")
    assert "ready_pre_score_unresolved" not in legacy["pa_state_counts"]
    assert len(legacy["pas"]) == 2


def test_recap_reexports_the_same_pre_score_function_object():
    """同一條紅線只能有一份實作（其一）：`/recap-wp` 用的必須是**同一個函式物件**。

    ML-WP-VAL-RESAMPLE1 把該純函式從 `api/routers/recap` 上抽到本模組（models 不得
    import api，且留在 api 側會構成 winprob_val → recap → winprob_scorer → winprob_val
    迴圈），recap 改以別名 re-export。這裡釘住 re-export 是**別名而非副本**：
    若日後有人在 recap 側貼回一份實作，識別測試會紅而數值測試不會。
    """
    from cpbl.api.routers import recap
    from cpbl.models import winprob_val

    assert recap.pre_scores_from_events is winprob_val.pre_scores_from_events
    # 既有 import 路徑必須仍可用（#96 落地的測試正是走這條）
    from cpbl.api.routers.recap import pre_scores_from_events as reexported

    assert reexported is winprob_val.pre_scores_from_events
    assert winprob_val.pre_scores_from_events.__module__ == "cpbl.models.winprob_val"


def test_models_layer_does_not_import_the_api_layer():
    """分層方向：`models` 不得 import `api`。

    以子行程從乾淨的 import 狀態載入 `cpbl.models.winprob_val`，斷言載入後
    `sys.modules` 裡沒有任何 `cpbl.api.*`。上抽之前這條會紅（取樣路徑得延後 import
    `api/routers/recap` 才拿得到解算），是本次上抽要證明的東西。
    """
    import subprocess
    import sys

    code = (
        "import sys; import cpbl.models.winprob_val; "
        "leaked = sorted(m for m in sys.modules if m.startswith('cpbl.api')); "
        "print(leaked)"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                         check=True)
    assert out.stdout.strip() == "[]", f"models 層洩漏了 api 依賴：{out.stdout.strip()}"


def test_pre_score_resolution_delegates_to_the_single_implementation(monkeypatch):
    """同一條紅線只能有一份實作（其二）：評估樣本必須真的呼叫那支共用純函式。

    這支測試釘住的是**依賴**而非數值——若日後有人在取樣路徑上另刻一份解算，
    數值測試仍可能全綠，這裡會紅。
    """
    from cpbl.models import winprob_val

    calls: list[int] = []
    original = winprob_val.pre_scores_from_events

    def spy(pa_rows, events):
        calls.append(len(pa_rows))
        return original(pa_rows, events)

    monkeypatch.setattr(winprob_val, "pre_scores_from_events", spy)
    games, pas, livelog = _first_pitch_hr_fixture()
    winprob_val.load_eval_season(_EvalCursor(games, pas, livelog), "A", 2026)
    assert calls == [2], "評估樣本沒走那支共用純函式（疑似另刻了第二份實作）"


def test_unknown_pre_score_source_is_rejected():
    games, pas, livelog = _first_pitch_hr_fixture()
    with pytest.raises(ValueError):
        load_eval_season(_EvalCursor(games, pas, livelog), "A", 2026,
                         pre_score_source="pre_State")
    assert PRE_SCORE_SOURCES == ("events", "pre_state")
