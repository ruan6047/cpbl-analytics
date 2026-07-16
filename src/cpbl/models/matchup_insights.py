"""投打對決「天敵候選／優勢對位」的統計核心（ML-MATCHUP1）。

純函式、不查 DB。設計要點（spec：matchups-redesign.md §天敵／優勢統計定義）：

- 主指標為 wOBA 型線性加權率（`woba_generic_v1`，MLB 通用權重）。權重僅作
  「相對差異」比較——主角、對手與聯盟都用同一組權重，尺度偏差在差值中對消；
  本輸出為描述性統計，不代表因果或未來預測。
- **leave-pair-out baseline**（第二輪審核必改）：官方 batter/pitcher 母體本身
  「包含」被評配對，直接當 baseline 會與配對樣本相依（covariance），噪音被
  過度扣除、tau² 系統性低估。故先從兩側官方彙總扣除該配對的原始計數，得
  leave-pair-out 剩餘 baseline，期望與殘差全以此定義；扣除後計數或分母不為
  正者視為不可評估。
- 對稱期望：expected(pair) = league_mean + batter_dev + pitcher_dev（兩側偏差
  皆以 leave-pair-out 剩餘 rate 對聯盟均值中心化）。差值 delta = observed −
  expected 只有一個號向（正=有利打者），角色翻轉時同一組對戰不可能被雙方
  同時標成優勢（spec 對稱測試由建構保證）。
- 經驗貝氏收縮 [empirical Bayes shrinkage]：delta 以 N(0, tau²) 先驗回縮，
  抽樣變異 sigma²/n 與 tau² 皆由資料估計（動差法），不靠人工拍門檻；
  tau² 無法可靠估計時整體 fail-closed（由呼叫端以 hyper=None 表達），
  嚴禁退回任意常數先驗。
- 排名以收縮後效果量排序；顯示閘門用後驗同號機率（credibility），未達閘門
  一律不進候選（樣本不足誠實退化）。閘門與先驗強度附敏感度檢查。
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

WOBA_VERSION = "woba_generic_v1"
# MLB 通用線性權重（FanGraphs 慣用近似值）；uBB = BB − IBB。
_WOBA_WEIGHTS = {
    "ubb": 0.69,
    "hbp": 0.72,
    "singles": 0.89,
    "doubles": 1.27,
    "triples": 1.62,
    "home_runs": 2.10,
}
# 顯示閘門（預先註冊）：後驗同號機率下限與敏感度掃描點。
CREDIBILITY_GATE = 0.75
GATE_SCAN = (0.70, 0.75, 0.80)
PRIOR_SCAN = (0.5, 1.0, 2.0)
_TAU2_FLOOR = 1e-8


@dataclass(frozen=True, slots=True)
class WobaLine:
    """一組（或一組彙總）對戰的 wOBA 樣本：加權和與機會數。"""

    weighted_sum: float
    opportunities: int

    @property
    def rate(self) -> float | None:
        return self.weighted_sum / self.opportunities if self.opportunities else None


def woba_line(counts: Mapping[str, Any]) -> WobaLine:
    """由原始計數建 wOBA 樣本；缺欄位視為 0（ingest 容缺原則）。

    分母 = AB + uBB + HBP + SF（標準 wOBA 分母；IBB 不記名也不記分母）。
    """
    def _int(key: str) -> int:
        value = counts.get(key)
        return int(value) if value else 0

    ubb = max(_int("bb") - _int("ibb"), 0)
    events = {
        "ubb": ubb,
        "hbp": _int("hbp"),
        "singles": _int("singles"),
        "doubles": _int("doubles"),
        "triples": _int("triples"),
        "home_runs": _int("home_runs"),
    }
    weighted = sum(_WOBA_WEIGHTS[key] * count for key, count in events.items())
    opportunities = _int("at_bats") + ubb + _int("hbp") + _int("sac_fly")
    return WobaLine(weighted, opportunities)


def merge_lines(lines: Iterable[WobaLine]) -> WobaLine:
    """跨年／跨對手彙總：先加總原始加權和與機會數，再算 rate。"""
    total_w = total_n = 0.0
    for line in lines:
        total_w += line.weighted_sum
        total_n += line.opportunities
    return WobaLine(total_w, int(total_n))


@dataclass(frozen=True, slots=True)
class PairSample:
    """單一 打者×投手 配對在指定 scope 內的彙總樣本。"""

    hitter_id: str
    pitcher_id: str
    line: WobaLine


@dataclass(frozen=True, slots=True)
class Hyperparameters:
    """由資料估出的先驗：sigma2=每機會抽樣變異、tau2=配對真實差異變異。"""

    sigma2: float
    tau2: float
    pairs_used: int

    @property
    def prior_strength(self) -> float:
        """等效先驗樣本數 K = sigma²/tau²（機會數單位）。"""
        return self.sigma2 / self.tau2


def per_opportunity_variance(league: WobaLine, event_counts: Mapping[str, int]) -> float:
    """每機會事件值變異：以聯盟事件分布算 E[(w−μ)²]；非計分事件值為 0。"""
    n = league.opportunities
    if n <= 0:
        raise ValueError("league opportunities must be positive")
    mean = league.weighted_sum / n
    scored = 0
    variance = 0.0
    for key, weight in _WOBA_WEIGHTS.items():
        count = int(event_counts.get(key) or 0)
        scored += count
        variance += count * (weight - mean) ** 2
    variance += (n - scored) * mean**2
    return variance / n


# 估 tau² 的最小配對機會數。門檻設 50 而非 10：動差估計對「大量微樣本配對」
# 敏感——它們幾乎全是抽樣噪音，噪音模型的殘餘偏差會把 tau² 系統性壓低
# （實資料診斷：全池估 0.00018，但 n≥50／n≥100 分層一致指向 ~0.0005）。
# 只用可偵測到 matchup 訊號的樣本估先驗才誠實。
_EST_MIN_N = 50
# 可靠估計 tau² 的最少配對數（預先註冊）：動差估計的相對標準誤 ~ sqrt(2/K)，
# K<20 時誤差 >30%，先驗本身不可信 → 呼叫端應 fail-closed（hyper=None），
# 不得用任意常數先驗頂替。生涯 kind A 實資料約 344 對，單季通常掛零。
MIN_PAIRS_FOR_PRIOR = 20

PairKey = tuple[str, str]


def additive_expected(
    batter_dev: float, pitcher_dev: float, league_mean: float
) -> float:
    """對戰期望 = 聯盟均值 + 打者偏差 + 投手偏差（各以自身母體均值中心化）。

    偏差相加保證對稱：角色翻轉不改變期望，故 delta 只有一個號向。
    夾在 [0, 權重上限] 內。
    """
    raw = league_mean + batter_dev + pitcher_dev
    return min(max(raw, 0.0), max(_WOBA_WEIGHTS.values()))


def leave_pair_out(baseline: WobaLine, pair: WobaLine) -> WobaLine | None:
    """自官方彙總扣除被評配對的原始計數，回傳剩餘 baseline。

    扣除後分母不為正、或加權和為負（官方彙總含近似拆分時的邊角）→ 回 None
    表示不可評估，呼叫端必須跳過該配對，不得硬夾成 0。
    """
    rem_n = baseline.opportunities - pair.opportunities
    rem_w = baseline.weighted_sum - pair.weighted_sum
    if rem_n <= 0 or rem_w < 0:
        return None
    return WobaLine(rem_w, rem_n)


@dataclass(frozen=True, slots=True)
class PairContext:
    """單一配對的 leave-pair-out 評估脈絡（期望、兩側剩餘與官方機會數）。"""

    expected: float
    hitter_rem: int
    pitcher_rem: int
    hitter_official: int
    pitcher_official: int


def pair_context(
    pair_line: WobaLine,
    hitter_baseline: WobaLine,
    pitcher_baseline: WobaLine,
    *,
    bat_league_mean: float,
    pit_league_mean: float,
) -> PairContext | None:
    """由官方兩側彙總建 leave-pair-out 期望；不可評估回 None。

    投手官方分母（BF−IBB）比 wOBA 分母多犧牲觸擊等少量事件，扣除配對的
    wOBA 機會數屬可驗證近似；殘餘自我納入僅剩該配對的犧牲觸擊，量級可忽略。
    """
    h_rem = leave_pair_out(hitter_baseline, pair_line)
    p_rem = leave_pair_out(pitcher_baseline, pair_line)
    if h_rem is None or p_rem is None:
        return None
    expected = additive_expected(
        h_rem.rate - bat_league_mean,
        p_rem.rate - pit_league_mean,
        bat_league_mean,
    )
    return PairContext(
        expected=expected,
        hitter_rem=h_rem.opportunities,
        pitcher_rem=p_rem.opportunities,
        hitter_official=hitter_baseline.opportunities,
        pitcher_official=pitcher_baseline.opportunities,
    )


def estimate_hyperparameters(
    pairs: Iterable[PairSample],
    *,
    contexts: Mapping[PairKey, PairContext],
    sigma2: float,
) -> Hyperparameters:
    """動差法估 tau²；期望與噪音校正一致採 leave-pair-out 定義。

    配對樣本與剩餘 baseline 由不相交的機會構成（獨立成立），
    Var(residual) = tau² + sigma²·(1/n + 1/h_rem + 1/p_rem)，故
    tau² = max(Σ(n·r² − sigma²·(1 + n/h_rem + n/p_rem))/Σn, floor)。
    只納入配對機會數 ≥ _EST_MIN_N 且可建 leave-pair-out 脈絡的列；
    可用配對 < MIN_PAIRS_FOR_PRIOR 時拋 ValueError（呼叫端 fail-closed）。
    """
    numerator = weight_total = 0.0
    used = 0
    for pair in pairs:
        n = pair.line.opportunities
        rate = pair.line.rate
        ctx = contexts.get((pair.hitter_id, pair.pitcher_id))
        if n < _EST_MIN_N or rate is None or ctx is None:
            continue
        residual = rate - ctx.expected
        noise = sigma2 * (1.0 + n / ctx.hitter_rem + n / ctx.pitcher_rem)
        numerator += n * residual**2 - noise
        weight_total += n
        used += 1
    if used < MIN_PAIRS_FOR_PRIOR or weight_total <= 0:
        raise ValueError(
            f"estimable pairs={used} < {MIN_PAIRS_FOR_PRIOR}，tau² 不可靠，須 fail-closed"
        )
    tau2 = max(numerator / weight_total, _TAU2_FLOOR)
    return Hyperparameters(sigma2=sigma2, tau2=tau2, pairs_used=used)


@dataclass(frozen=True, slots=True)
class ShrunkDelta:
    delta_raw: float
    delta_shrunk: float
    posterior_sd: float
    credibility: float


def shrink_delta(
    delta_raw: float, opportunities: float, hyper: Hyperparameters
) -> ShrunkDelta:
    """後驗均值與同號機率；opportunities 為有效機會數（可含 baseline 噪音折減）。"""
    if opportunities <= 0:
        return ShrunkDelta(delta_raw, 0.0, math.sqrt(hyper.tau2), 0.5)
    precision_data = opportunities / hyper.sigma2
    precision_prior = 1.0 / hyper.tau2
    weight = precision_data / (precision_data + precision_prior)
    shrunk = weight * delta_raw
    posterior_sd = math.sqrt(1.0 / (precision_data + precision_prior))
    if posterior_sd <= 0 or shrunk == 0:
        credibility = 0.5
    else:
        z = abs(shrunk) / posterior_sd
        credibility = 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))
    return ShrunkDelta(delta_raw, shrunk, posterior_sd, credibility)


@dataclass(frozen=True, slots=True)
class InsightCandidate:
    """單一對手的洞察候選；delta 號向固定為「正=有利打者」。"""

    opponent_id: str
    opportunities: int
    observed: float
    expected: float
    shrunk: ShrunkDelta
    effective_opportunities: float = 0.0
    opponent_baseline_opportunities: int = 0


# 對手官方 baseline 至少這麼多機會數，其期望值才夠穩定；用於覆蓋率敏感度。
OPPONENT_BASELINE_FLOOR = 100


def evaluate_pairs(
    pairs: Iterable[PairSample],
    *,
    role: str,
    contexts: Mapping[PairKey, PairContext],
    hyper: Hyperparameters,
) -> list[InsightCandidate]:
    """算每個對手的收縮後 delta；期望與噪音一致採 leave-pair-out 定義。

    缺脈絡（官方季表無紀錄、或扣除配對後不可評估）時跳過——期望無從定義，
    誠實不評。有效機會數 n_eff = 1/(1/n + 1/h_rem + 1/p_rem) 把剩餘 baseline
    的抽樣噪音折進可信度；剩餘機會數大，n_eff ≈ n。
    """
    if role not in {"batting", "pitching"}:
        raise ValueError(f"不支援的角色：{role}")
    out: list[InsightCandidate] = []
    for pair in pairs:
        rate = pair.line.rate
        ctx = contexts.get((pair.hitter_id, pair.pitcher_id))
        if rate is None or ctx is None:
            continue
        n = pair.line.opportunities
        n_eff = 1.0 / (1.0 / n + 1.0 / ctx.hitter_rem + 1.0 / ctx.pitcher_rem)
        shrunk = shrink_delta(rate - ctx.expected, n_eff, hyper)
        if role == "batting":
            opponent, opp_off = pair.pitcher_id, ctx.pitcher_official
        else:
            opponent, opp_off = pair.hitter_id, ctx.hitter_official
        out.append(
            InsightCandidate(
                opponent_id=opponent,
                opportunities=n,
                observed=rate,
                expected=ctx.expected,
                shrunk=shrunk,
                effective_opportunities=n_eff,
                opponent_baseline_opportunities=opp_off,
            )
        )
    return out


@dataclass(frozen=True, slots=True)
class Insights:
    advantages: tuple[InsightCandidate, ...]
    disadvantages: tuple[InsightCandidate, ...]
    eligible: int
    gated_out: int


def rank_insights(
    candidates: Iterable[InsightCandidate],
    *,
    role: str,
    limit: int = 3,
    credibility_gate: float = CREDIBILITY_GATE,
) -> Insights:
    """效果量×可信度排名：先以 credibility 閘門過濾，再依 |delta_shrunk| 排序。

    delta 正=有利打者：打者視角優勢=正、天敵=負；投手視角相反。
    同一組對戰在兩視角的 |delta| 相同、標籤鏡像——不可能同時雙方優勢。
    """
    if limit < 1:
        raise ValueError("limit must be >= 1")
    rows = list(candidates)
    passed = [c for c in rows if c.shrunk.credibility >= credibility_gate]
    batter_favored = sorted(
        (c for c in passed if c.shrunk.delta_shrunk > 0),
        key=lambda c: (-abs(c.shrunk.delta_shrunk), c.opponent_id),
    )
    pitcher_favored = sorted(
        (c for c in passed if c.shrunk.delta_shrunk < 0),
        key=lambda c: (-abs(c.shrunk.delta_shrunk), c.opponent_id),
    )
    if role == "batting":
        advantages, disadvantages = batter_favored, pitcher_favored
    else:
        advantages, disadvantages = pitcher_favored, batter_favored
    return Insights(
        advantages=tuple(advantages[:limit]),
        disadvantages=tuple(disadvantages[:limit]),
        eligible=len(passed),
        gated_out=len(rows) - len(passed),
    )


def sensitivity_report(
    candidates: list[InsightCandidate],
    *,
    role: str,
    limit: int,
    hyper: Hyperparameters,
) -> dict[str, Any]:
    """閘門、先驗強度與對手覆蓋敏感度：候選名單成員是否隨合理擾動改變。

    - gate 掃 GATE_SCAN；
    - 先驗強度乘 PRIOR_SCAN（tau² 反向縮放後重算收縮與 credibility）；
    - 覆蓋：排除官方 baseline 稀疏（期望不穩）的對手後重排。
    名單（不含順序）在所有情境相同 → stable=true；否則列出各情境成員。
    """
    def members(cands: list[InsightCandidate], gate: float) -> frozenset[str]:
        ranked = rank_insights(cands, role=role, limit=limit, credibility_gate=gate)
        return frozenset(
            c.opponent_id for c in (*ranked.advantages, *ranked.disadvantages)
        )

    reference = members(candidates, CREDIBILITY_GATE)
    gate_variants = {f"gate_{gate:.2f}": members(candidates, gate) for gate in GATE_SCAN}

    prior_variants: dict[str, frozenset[str]] = {}
    for scale in PRIOR_SCAN:
        scaled = Hyperparameters(
            sigma2=hyper.sigma2, tau2=hyper.tau2 / scale, pairs_used=hyper.pairs_used
        )
        rescored = [
            InsightCandidate(
                opponent_id=c.opponent_id,
                opportunities=c.opportunities,
                observed=c.observed,
                expected=c.expected,
                shrunk=shrink_delta(
                    c.shrunk.delta_raw,
                    c.effective_opportunities or c.opportunities,
                    scaled,
                ),
                effective_opportunities=c.effective_opportunities,
                opponent_baseline_opportunities=c.opponent_baseline_opportunities,
            )
            for c in candidates
        ]
        prior_variants[f"prior_x{scale:g}"] = members(rescored, CREDIBILITY_GATE)

    well_covered = [
        c for c in candidates
        if c.opponent_baseline_opportunities >= OPPONENT_BASELINE_FLOOR
    ]
    coverage_variants = {
        f"opp_baseline_ge_{OPPONENT_BASELINE_FLOOR}": members(
            well_covered, CREDIBILITY_GATE
        )
    }

    variants = {**gate_variants, **prior_variants, **coverage_variants}
    stable = all(v == reference for v in variants.values())
    return {
        "stable": stable,
        "reference_members": sorted(reference),
        "variants": {key: sorted(value) for key, value in variants.items()},
    }
