"""局面勝率 [WP] 解算器的**唯一取得點**（跨消費者共用同一台機器）。

原本住在 ``api/routers/recap.py``（GAME-RECAP-WP-API1）。UX-GAME-RECAP1 第五輪人工審
把「關鍵打席以 |ΔWP| 選取＋直接顯示擺動值」納入 recap 之後，``models/pa_facts`` 也需要
同一個解算器——models 不得 import api（分層），而「分布來源對照表 + span + ruleset」
只能有一個 owner（前科：leaders 自建勝敗序列與 special_records 分歧），故上抽到 models。

``api/routers/recap.py`` 仍以別名 re-export（``_get_scorer``／``_dist_cache``／
``_solver_cache``），舊 import 路徑與快取清除語意不變。

紅線不變：全 scope 時間外驗證 unsupported（WP-VAL1）、事後校準 No-Go（WP-CAL1）。
本模組只負責**取得解算器**，誠實揭露的文案與 metadata 仍歸 ``api/routers/recap.py``
（``wp_reliability``）與 ``/methodology``。
"""

from __future__ import annotations

from collections.abc import Callable

from cpbl.models.winprob import _load_dist
from cpbl.models.winprob_val import RuleSet, ruleset_for, we_solver_rules, wp_state_rules

MODEL_SPAN = "2018-2025"  # 生產 run_dist artifact 唯一 span（重建後重啟 API 生效）

# 分布來源（對齊 winprob_val.TRAIN_PROXY 語意）：C/E（一軍季後）借一軍例行分布；
# D（二軍例行）只可用自身分布——生產目前無 D artifact → fail closed（model_not_built），
# 不得靜默借 A（spec §8.2「未驗證賽制不得借用一軍口徑而不揭露」）。
DIST_SOURCE: dict[str, tuple[str, str]] = {
    "A": ("A", "own"),
    "C": ("A", "borrowed"),
    "D": ("D", "own"),
    "E": ("A", "borrowed"),
}

# 模型載入（表小、跨 request 重用；artifact 重建後重啟 API 生效，同 /winprob 慣例）
_dist_cache: dict[tuple[str, str], dict | None] = {}
_solver_cache: dict[tuple[str, str, RuleSet], tuple] = {}

Scorer = Callable[[int, str, int, str, int], float]  # (inning, vht, diff, bases, outs)


def get_dist(dist_kind: str) -> dict | None:
    key = (MODEL_SPAN, dist_kind)
    if key not in _dist_cache:
        try:
            _dist_cache[key] = _load_dist(MODEL_SPAN, dist_kind)
        except RuntimeError:
            _dist_cache[key] = None  # artifact 未建置 → fail closed
    return _dist_cache[key]


def get_scorer(kind_code: str, season: int) -> tuple[Scorer | None, dict | None]:
    """回傳 (scorer, model metadata)；無分布 artifact 時 (None, None)。"""
    dist_kind, source = DIST_SOURCE[kind_code]
    dist = get_dist(dist_kind)
    if dist is None:
        return None, None
    rules = ruleset_for(kind_code, season)
    skey = (MODEL_SPAN, dist_kind, rules)
    if skey not in _solver_cache:
        _solver_cache[skey] = we_solver_rules(dist, rules)
    we_top, we_bot = _solver_cache[skey]

    def scorer(inning: int, vht: str, diff: int, bases: str, outs: int) -> float:
        return wp_state_rules(dist, we_top, we_bot, rules, inning, vht, diff, bases, outs)

    model = {
        "model_span": MODEL_SPAN,
        "model_kind": dist_kind,
        # run_dist artifact（migration 049）無時戳欄位 → 誠實回 null，不假造建置時間
        "model_built_at": None,
        "ruleset": rules.tag,
        "distribution_source": source,
    }
    return scorer, model
