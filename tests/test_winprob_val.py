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
6. （ML-WP-VERDICT-ROBUST1）判定對 bootstrap seed 穩健、判定詞彙能表達「測不了」，
   且**門檻數值未被順手改掉**。
"""

from __future__ import annotations

import random
from collections import defaultdict

import pytest

from cpbl.models.winprob import _we_solver, wp_state
from cpbl.models.winprob_val import (
    BOOT_SEEDS,
    LEGACY_BOOT_SEED,
    MC_TOLERANCE_Z,
    PRE_SCORE_SOURCES,
    SIG_NOT_SIGNIFICANT,
    SIG_SIGNIFICANT,
    SIG_UNDETERMINED,
    THRESHOLDS,
    VERDICT_INSUFFICIENT,
    RuleSet,
    _tail_state,
    brier_constant,
    cluster_bootstrap_bins,
    cluster_bootstrap_brier_delta,
    cluster_bootstrap_devs,
    dist_from_counts,
    iter_half_pa_records,
    load_eval_season,
    metrics,
    null_ece_reference,
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
            sig=(), delta_state=None):
    """delta_state=None → 不帶 bootstrap 資訊（verdict 退回 v2 的點估計行為）。"""
    row = {
        "year": year, "coverage": cov,
        "walk_forward": {"n_pa": n, "brier": brier, "ece_weighted": ece,
                         "decile_max_dev": maxdev, "significant_bins": list(sig)},
        "baseline_home_const": {"brier": base},
    }
    if delta_state is not None:
        row["baseline_home_const"]["delta_boot"] = {
            "n_games": n // 75, "delta": round(brier - base, 5), "se": 0.01,
            "ci": [-0.02, 0.02], "sig_state": delta_state, "p_one": 0.2,
            "p_one_mc_ci": [0.18, 0.22], "n_seeds_significant": 0,
            "n_seeds": len(BOOT_SEEDS)}
    return row


def _decile(b, pred, actual, n, *, sig_state=SIG_SIGNIFICANT, se=0.008):
    return {"bin": b, "pred": pred, "actual": actual, "n": n, "dev_se": se,
            "dev_ci": [0.031, 0.07], "dev_ci_legacy_seed": [0.030, 0.071],
            "sig_state": sig_state, "p_one": 0.0, "p_one_mc_ci": [0.0, 0.002],
            "n_seeds_significant": 12, "n_seeds": len(BOOT_SEEDS)}


def _pooled(*, n=40000, ece=0.01, deciles=(), null_ece=None):
    return {"n_pa": n, "n_games": n // 75, "brier": 0.15, "ece_weighted": ece,
            "decile_max_dev": 0.02, "deciles": list(deciles),
            "null_ece": null_ece,
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
    big = _decile(5, 0.55, 0.50, 5000)
    hard = verdict_for("A", [_season(2024)], _pooled(deciles=[big]))
    assert hard["status"] == "unsupported"
    bounded = _decile(5, 0.52, 0.50, 5000)
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
    `sys.modules` 裡沒有任何 `cpbl.api.*`——證明上抽後 models 的 import 是**潔淨**的。

    ⚠️ 這**不是**紅→綠的回歸證明：上抽前那個 `api` import 本來就寫在
    `_resolve_pre_scores()` 函式內，單純載入模組同樣不會把 `cpbl.api.*` 放進
    `sys.modules`，故本測試在上抽前也會綠（RESAMPLE1-R1-001，查核指出，已實測確認）。
    它守的是**日後不回退**：若有人把 `pre_scores_from_events` 或其他 api 依賴改成
    模組層 import，這裡會紅。
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


# ===========================================================================
# ML-WP-VERDICT-ROBUST1：判定的 seed 穩健性與「測不了」詞彙
# ===========================================================================
def _legacy_cluster_bootstrap_devs(scored, reps, ci, seed=LEGACY_BOOT_SEED):
    """v2 逐場重抽的**參考實作**（基準 876ce9f 的 `cluster_bootstrap_devs` 逐行複製）。

    存在理由：v3 把重抽向量化了。若向量化順手改了抽樣序列或累加語意，判定的變化
    就無法歸因於「機制改了」——那正是 ML-WP-VAL-RESAMPLE1 用三路對照才辨認出來的
    那種混淆。這份參考實作把「抽到同一批場次」釘成可執行的斷言。
    """
    by_game = {}
    for wp, y, _, gk in scored:
        g = by_game.setdefault(gk, [[0.0, 0.0, 0] for _ in range(10)])
        b = g[min(int(wp * 10), 9)]
        b[0] += wp
        b[1] += y
        b[2] += 1
    games = list(by_game.values())
    rng = random.Random(seed)
    devs = defaultdict(list)
    for _ in range(reps):
        agg = [[0.0, 0.0, 0] for _ in range(10)]
        for g in rng.choices(games, k=len(games)):
            for i in range(10):
                agg[i][0] += g[i][0]
                agg[i][1] += g[i][1]
                agg[i][2] += g[i][2]
        for i, (sw, so, bn) in enumerate(agg):
            if bn:
                devs[i].append(sw / bn - so / bn)
    lo_q, hi_q = (1 - ci) / 2, 1 - (1 - ci) / 2
    out = {}
    for i, ds in devs.items():
        ds.sort()
        n = len(ds)
        mean = sum(ds) / n
        se = (sum((d - mean) ** 2 for d in ds) / max(n - 1, 1)) ** 0.5
        out[i] = {"se": round(se, 4),
                  "ci": [round(ds[int(lo_q * (n - 1))], 4),
                         round(ds[int(hi_q * (n - 1))], 4)]}
    return out


def _synthetic_scored(n_games=180, seed=11):
    rng = random.Random(seed)
    rows = []
    for g in range(n_games):
        y = 1.0 if rng.random() < 0.52 else 0.0
        for _ in range(rng.randint(20, 45)):
            rows.append((rng.random(), y, False, g))
    return rows


def test_vectorised_resampling_draws_the_same_games_as_the_v2_loop():
    """機制換了，抽樣沒換——否則判定變化無法歸因。"""
    scored = _synthetic_scored()
    assert cluster_bootstrap_devs(scored, 200, 0.99) == \
        _legacy_cluster_bootstrap_devs(scored, 200, 0.99)


def test_tail_state_separates_undetermined_from_the_two_decided_answers():
    """三態的核心：`undetermined` 不得被吸收進 significant 或 not_significant。"""
    import numpy as np

    n = 6000
    alpha_one = (1 - 0.99) / 2          # 0.005
    # 尾機率 0 → 再多抽也不會翻 → significant
    clear = np.full(n, 0.05)
    assert _tail_state(clear, 0.99, MC_TOLERANCE_Z)["state"] == SIG_SIGNIFICANT
    # 尾機率 0.5 → 明確不顯著
    split = np.concatenate([np.full(n // 2, 0.05), np.full(n // 2, -0.05)])
    assert _tail_state(split, 0.99, MC_TOLERANCE_Z)["state"] == SIG_NOT_SIGNIFICANT
    # 尾機率正好壓在 α_one 上 → MC 誤差跨過門檻 → 解析不出來
    k = int(alpha_one * n)
    edge = np.concatenate([np.full(k, -0.05), np.full(n - k, 0.05)])
    got = _tail_state(edge, 0.99, MC_TOLERANCE_Z)
    assert got["state"] == SIG_UNDETERMINED
    assert got["p_one_mc_ci"][0] < alpha_one < got["p_one_mc_ci"][1]


def test_bin_significance_is_deterministic_and_reports_seed_agreement():
    """v3 的判定不再吃 seed 運氣：同輸入必得同輸出，且跨 seed 的分歧看得見。"""
    scored = _synthetic_scored(seed=23)
    a = cluster_bootstrap_bins(scored, reps=120, ci=0.99, seeds=BOOT_SEEDS[:4])
    b = cluster_bootstrap_bins(scored, reps=120, ci=0.99, seeds=BOOT_SEEDS[:4])
    assert a == b
    for info in a.values():
        assert info["sig_state"] in (SIG_SIGNIFICANT, SIG_NOT_SIGNIFICANT,
                                     SIG_UNDETERMINED)
        assert 0 <= info["n_seeds_significant"] <= info["n_seeds"] == 4
        # v2 的單一 seed CI 仍留著供 A/B 對照，但不再是判定依據
        assert info["ci_legacy_seed"] == \
            _legacy_cluster_bootstrap_devs(scored, 120, 0.99)[
                next(k for k in a if a[k] is info)]["ci"]


def test_seed_ladder_extends_the_registered_set_deterministically():
    from cpbl.models.winprob_val import seed_ladder

    assert seed_ladder(len(BOOT_SEEDS)) == list(BOOT_SEEDS)
    long = seed_ladder(48)
    assert long[:len(BOOT_SEEDS)] == list(BOOT_SEEDS)   # 註冊 seed 集永遠打頭
    assert len(set(long)) == 48                         # 不重複
    assert long == seed_ladder(48)                      # 可重現


def test_budget_escalates_until_the_decision_resolves():
    """「undetermined」不得只是「我沒抽夠」的別名：解析不出來就自動加碼。

    若停在固定 seed 數，「註冊了幾個 seed」會變成新的任意數字直接左右 Go/No-Go
    ——本卡實測 D 池化十分位 2 就是在 6,000 次下 undetermined、12,000 次下 significant。
    """
    from cpbl.models.winprob_val import _escalate

    seen = []

    def compute(seeds):
        seen.append(len(seeds))
        return len(seeds), len(seeds) < 48      # 48 個 seed 才解析得出來

    result, seeds, total, unresolved = _escalate(
        compute, reps=500, base_seeds=BOOT_SEEDS, max_reps=192 * 500)
    assert seen == [12, 24, 48] and result == 48
    assert total == 48 * 500 and not unresolved

    # 上限撞到就停，並誠實回報還沒解析出來
    seen.clear()

    def never(seeds):
        seen.append(len(seeds))
        return len(seeds), True

    _r, _s, total, unresolved = _escalate(never, reps=500, base_seeds=BOOT_SEEDS,
                                          max_reps=48 * 500)
    assert seen == [12, 24, 48] and total == 48 * 500 and unresolved


def test_hitting_the_reps_cap_is_reported_not_silently_decided():
    scored = _synthetic_scored(seed=31)
    got = cluster_bootstrap_bins(scored, reps=50, ci=0.99, seeds=BOOT_SEEDS[:2],
                                 max_reps=4 * 50)
    # 200 次重抽估不出 α_one=0.005 的尾巴：k=0 時 Wilson 上界仍遠高於 α_one，
    # 故**沒有任何分箱能被判成 significant**——判不動就要說判不動。
    assert not any(v["sig_state"] == SIG_SIGNIFICANT for v in got.values())
    capped = [v for v in got.values() if v["sig_state"] == SIG_UNDETERMINED]
    assert capped and all(v["hit_reps_cap"] for v in capped)
    assert {v["reps_total"] for v in got.values()} == {4 * 50}


def test_undetermined_pooled_bin_is_neither_pass_nor_fail():
    """本卡的病灶案例（D 十分位 2 型態）：幅度超界、顯著性解析不出來。

    v2 會依 seed 隨機丟進 unsupported 或 supported；v3 必須回 `insufficient_evidence`
    ——**既不放行也不定罪**。
    """
    over_undet = _decile(2, 0.29, 0.24, 6351, sig_state=SIG_UNDETERMINED)
    v = verdict_for("D", [_season(2024, delta_state=SIG_SIGNIFICANT)],
                    _pooled(deciles=[over_undet]))
    assert v["status"] == VERDICT_INSUFFICIENT
    assert not v["reasons"]                      # 沒有解析得出來的失敗
    assert any("無法解析" in m for m in v["insufficient"])
    # 對照：同一個分箱若顯著性解析得出來，門檻不變、仍是硬性失敗
    over_sig = _decile(2, 0.29, 0.24, 6351, sig_state=SIG_SIGNIFICANT)
    hard = verdict_for("D", [_season(2024, delta_state=SIG_SIGNIFICANT)],
                       _pooled(deciles=[over_sig]))
    assert hard["status"] == "unsupported"


def test_no_evaluable_sample_is_insufficient_not_unsupported():
    """v2 在 winprob_val.py:645 把「無可評樣本」寫成 unsupported——最明顯的壓縮。"""
    v = verdict_for("E", [], {"n_pa": 0})
    assert v["status"] == VERDICT_INSUFFICIENT
    assert v["insufficient"] == ["無可評樣本"]
    assert v["reasons"] == []


def test_season_baseline_gate_needs_a_resolvable_gap():
    """4 場的季不得一票否決整個 scope（E2025 型態）。"""
    lost_but_noisy = _season(2025, brier=0.28886, base=0.25289, n=300,
                             delta_state=SIG_UNDETERMINED)
    v = verdict_for("E", [lost_but_noisy], _pooled(n=300, ece=0.01))
    assert v["status"] == VERDICT_INSUFFICIENT
    assert not v["reasons"]
    assert any("不可區分" in m for m in v["insufficient"])
    # 對照：差距解析得出來時，門檻不變、仍是硬性失敗
    lost_clearly = _season(2025, brier=0.28886, base=0.25289, n=90000,
                           delta_state=SIG_SIGNIFICANT)
    assert verdict_for("A", [lost_clearly], _pooled())["status"] == "unsupported"


def test_unreachable_ece_threshold_is_reported_as_untestable():
    """門檻在該樣本量下不可能通過時，它不是判準而是雜訊產生器。"""
    tiny = [_decile(b, 0.5, 0.5, 200, se=0.09) for b in range(10)]
    null = null_ece_reference(tiny)
    assert null["analytic_mean"] > THRESHOLDS["proxy_pooled_ece_max"]
    v = verdict_for("C", [_season(2025, n=400, delta_state=SIG_SIGNIFICANT)],
                    _pooled(n=1600, ece=0.10970, deciles=tiny, null_ece=null))
    assert v["status"] == VERDICT_INSUFFICIENT
    assert not v["reasons"]
    assert any("不可達" in m for m in v["insufficient"])
    gate = next(g for g in v["gates"] if g["gate"] == "proxy_pooled_ece")
    assert gate["decision"] == "unreachable"


def test_reachable_ece_threshold_still_fails_hard():
    """反向對照：門檻判得動時，超標仍然是 unsupported——本卡沒有放寬任何門檻。"""
    sharp = [_decile(b, 0.5, 0.5, 20000, se=0.004) for b in range(10)]
    null = null_ece_reference(sharp)
    assert null["analytic_mean"] < THRESHOLDS["proxy_pooled_ece_max"]
    v = verdict_for("C", [_season(2025, n=40000, delta_state=SIG_SIGNIFICANT)],
                    _pooled(n=200000, ece=0.20, deciles=sharp, null_ece=null))
    assert v["status"] == "unsupported"
    assert any("代理證據不足" in m for m in v["reasons"])


def test_brier_delta_bootstrap_resolves_a_large_gap_and_not_a_tiny_sample():
    """Δ 的三態必須真的隨樣本量改變，而不是常數。"""
    scored = [(0.9, y, False, g) for g in range(200)
              for y in ([1.0] * 40)]
    big = cluster_bootstrap_brier_delta(scored, 0.5, reps=1000, ci=0.99,
                                        seeds=BOOT_SEEDS[:3])
    assert big["delta"] < 0 and big["sig_state"] == SIG_SIGNIFICANT
    rng = random.Random(5)
    noisy = [(0.55, 1.0 if rng.random() < 0.5 else 0.0, False, g)
             for g in range(4) for _ in range(70)]
    small = cluster_bootstrap_brier_delta(noisy, 0.52, reps=200, ci=0.99,
                                          seeds=BOOT_SEEDS[:3])
    assert small["sig_state"] != SIG_SIGNIFICANT
    assert small["n_games"] == 4


def test_thresholds_are_untouched_by_the_verdict_rework():
    """本卡改的是判定方法與詞彙，**不是門檻**。任一數字被動到這裡就紅。

    v3 的新旋鈕（seed 集、MC 容忍度）刻意住在 THRESHOLDS 之外，讓「有沒有偷改門檻」
    是一個機械可驗的問題。
    """
    assert THRESHOLDS == {
        "ece_weighted_max": 0.025,
        "decile_max_dev": 0.06,
        "min_season_pa": 5000,
        "min_coverage": 0.98,
        "pooled_bin_dev_max": 0.03,
        "proxy_pooled_ece_max": 0.05,
        "boot_reps": 500,
        "boot_ci": 0.99,
    }
    assert BOOT_SEEDS[0] == LEGACY_BOOT_SEED == 20260725
    assert len(set(BOOT_SEEDS)) == len(BOOT_SEEDS) == 12


def test_registered_boot_budget_can_resolve_a_clean_tail():
    """seed 集大小不是隨手挑的：重抽總數必須大到「一次都沒跨過 0」能判成 significant。

    k=0 時 Wilson 上界 ≈ z²/(N+z²)，要小於 α_one=(1−ci)/2 就需要
    N > z²(1/α_one − 1) ≈ 1,791。註冊預算 12 seeds × 500 reps = 6,000 有 3.3 倍餘裕；
    少於 4 個 seed 則連完全乾淨的分箱都會被判成 undetermined（`--check` 型的死當）。
    """
    import numpy as np

    from cpbl.models.winprob_val import _wilson

    n_total = len(BOOT_SEEDS) * THRESHOLDS["boot_reps"]
    alpha_one = (1 - THRESHOLDS["boot_ci"]) / 2
    assert _wilson(0, n_total, MC_TOLERANCE_Z)[1] < alpha_one
    assert _wilson(0, 3 * THRESHOLDS["boot_reps"], MC_TOLERANCE_Z)[1] > alpha_one
    clean = np.full(n_total, 0.05)
    assert _tail_state(clean, THRESHOLDS["boot_ci"],
                       MC_TOLERANCE_Z)["state"] == SIG_SIGNIFICANT


def test_unknown_pre_score_source_is_rejected():
    games, pas, livelog = _first_pitch_hr_fixture()
    with pytest.raises(ValueError):
        load_eval_season(_EvalCursor(games, pas, livelog), "A", 2026,
                         pre_score_source="pre_State")
    assert PRE_SCORE_SOURCES == ("events", "pre_state")
