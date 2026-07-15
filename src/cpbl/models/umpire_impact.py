"""好球帶判決差異研究的純狀態邏輯。

本模組不把固定代理帶視為規則真值。`ProxyZone` 只重現既有 UI 的
`fixed_zone_proxy_v1` 契約；資料載入、估計與報告留在後續切片。
"""

from __future__ import annotations

import math
import random
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Protocol


class Call(StrEnum):
    BALL = "ball"
    STRIKE = "strike"


@dataclass(frozen=True, slots=True)
class ProxyZone:
    """固定代理帶 v1，單位為公尺。"""

    half_width: float = 0.253
    bottom: float = 0.423
    top: float = 1.077

    def __post_init__(self) -> None:
        if self.half_width <= 0 or self.bottom >= self.top:
            raise ValueError("invalid proxy zone")

    def shifted(self, centimeters: float) -> ProxyZone:
        """正值對所有邊界向外擴張，負值對稱收縮。"""
        margin = centimeters / 100.0
        return ProxyZone(
            half_width=self.half_width + margin,
            bottom=self.bottom - margin,
            top=self.top + margin,
        )


DEFAULT_PROXY_ZONE = ProxyZone()


@dataclass(frozen=True, slots=True)
class PitchState:
    """判決前狀態；score_diff_home 一律為主隊分數減客隊分數。"""

    batting_side: str
    inning: int
    score_diff_home: int
    bases: str
    outs: int
    balls: int
    strikes: int

    def __post_init__(self) -> None:
        if self.batting_side not in {"1", "2"}:
            raise ValueError("batting_side must be '1' (away) or '2' (home)")
        if self.inning < 1:
            raise ValueError("inning must be positive")
        if len(self.bases) != 3 or any(c not in {"_", "1", "2", "3"} for c in self.bases):
            raise ValueError("bases must use ___/1__/_2_/... encoding")
        if self.bases[0] not in {"_", "1"} or self.bases[1] not in {"_", "2"} or self.bases[2] not in {"_", "3"}:
            raise ValueError("base marker must match its base")
        if not 0 <= self.outs <= 2:
            raise ValueError("outs must be 0..2")
        if not 0 <= self.balls <= 3:
            raise ValueError("balls must be 0..3 before a pitch")
        if not 0 <= self.strikes <= 2:
            raise ValueError("strikes must be 0..2 before a pitch")


@dataclass(frozen=True, slots=True)
class CalledPitch:
    year: int
    kind_code: str
    game_sno: int
    pitcher_acnt: str
    pitch_cnt: int
    umpire: str
    batting_team: str
    fielding_team: str
    catcher_acnt: str
    venue: str
    state: PitchState
    plate_loc_side: float
    plate_loc_height: float
    observed_call: Call

    @property
    def game_id(self) -> str:
        return f"{self.year}-{self.kind_code}-{self.game_sno}"


@dataclass(frozen=True, slots=True)
class PitchScore:
    pitch: CalledPitch
    proxy_call: Call
    proxy_disagreement: bool
    edge_distance_cm: float
    run_value_ball: float
    run_value_strike: float
    delta_runs_offense: float
    backed_off: bool
    zone_definition: str = "fixed_zone_proxy_v1"
    delta_wp_home: float | None = None


@dataclass(frozen=True, slots=True)
class UmpireAggregate:
    umpire: str
    games: int
    called_pitches: int
    proxy_disagreements: int
    sum_delta_runs_offense: float
    per_100_called: float


@dataclass(frozen=True, slots=True)
class TeamAggregate:
    team: str
    calls_for: int
    calls_against: int
    state_value_for: float
    state_value_against: float


@dataclass(frozen=True, slots=True)
class UmpireBootstrap:
    umpire: str
    iterations: int
    total: QuantileInterval
    per_100_called: QuantileInterval


@dataclass(frozen=True, slots=True)
class TeamBootstrap:
    team: str
    iterations: int
    state_value_for: QuantileInterval
    state_value_against: QuantileInterval
    per_100_for: QuantileInterval
    per_100_against: QuantileInterval


@dataclass(frozen=True, slots=True)
class ImpactBootstrap:
    umpires: tuple[UmpireBootstrap, ...]
    teams: tuple[TeamBootstrap, ...]


@dataclass(frozen=True, slots=True)
class Transition:
    next_state: PitchState | None
    immediate_runs: int
    half_over: bool


@dataclass(frozen=True, slots=True)
class RunStateKey:
    """半局內的得分價值狀態；刻意排除局數與比數。"""

    batting_side: str
    bases: str
    outs: int
    balls: int
    strikes: int

    def __post_init__(self) -> None:
        PitchState(
            batting_side=self.batting_side,
            inning=1,
            score_diff_home=0,
            bases=self.bases,
            outs=self.outs,
            balls=self.balls,
            strikes=self.strikes,
        )

    @classmethod
    def from_pitch_state(cls, state: PitchState) -> RunStateKey:
        return cls(
            state.batting_side,
            state.bases,
            state.outs,
            state.balls,
            state.strikes,
        )

    @property
    def parent(self) -> tuple[str, str, int]:
        return self.batting_side, self.bases, self.outs


@dataclass(frozen=True, slots=True)
class RunObservation:
    key: RunStateKey
    remaining_runs: int
    game_id: str

    def __post_init__(self) -> None:
        if self.remaining_runs < 0:
            raise ValueError("remaining_runs must be non-negative")
        if not self.game_id:
            raise ValueError("game_id must not be empty")


@dataclass(frozen=True, slots=True)
class ValueMetrics:
    nll: float
    mae: float
    n: int


@dataclass(frozen=True, slots=True)
class CallValues:
    ball: float
    strike: float
    backed_off: bool


@dataclass(frozen=True, slots=True)
class AlphaTuning:
    alpha: float
    metrics_by_alpha: dict[float, ValueMetrics]


@dataclass(frozen=True, slots=True)
class ConfidenceInterval:
    low: float
    high: float


@dataclass(frozen=True, slots=True)
class BootstrapComparison:
    games: int
    iterations: int
    nll_delta: ConfidenceInterval
    mae_delta: ConfidenceInterval


@dataclass(frozen=True, slots=True)
class WinObservation:
    state: PitchState
    outcome_home: float
    game_id: str

    def __post_init__(self) -> None:
        if not 0 <= self.outcome_home <= 1:
            raise ValueError("outcome_home must be between zero and one")
        if not self.game_id:
            raise ValueError("game_id must not be empty")


@dataclass(frozen=True, slots=True)
class ProbabilityMetrics:
    brier: float
    log_loss: float
    calibration_intercept: float
    calibration_slope: float
    ece: float
    reliability: tuple[ReliabilityBin, ...]
    n: int


@dataclass(frozen=True, slots=True)
class ReliabilityBin:
    lower: float
    upper: float
    mean_prediction: float
    mean_outcome: float
    n: int


@dataclass(frozen=True, slots=True)
class QuantileInterval:
    low: float
    median: float
    high: float


@dataclass(frozen=True, slots=True)
class ProbabilityBootstrapComparison:
    games: int
    iterations: int
    brier_delta: ConfidenceInterval
    log_loss_delta: ConfidenceInterval


class ProbabilityPredictor(Protocol):
    def predict(self, state: PitchState) -> float: ...


ParentKey = tuple[str, str, int]


class RunValueModel:
    """計數感知的剩餘得分分布，使用父狀態與全域分布階層式收縮。"""

    def __init__(
        self,
        *,
        alpha: float,
        max_runs: int,
        global_distribution: tuple[float, ...],
        parent_distributions: dict[ParentKey, tuple[float, ...]],
        state_distributions: dict[RunStateKey, tuple[float, ...]],
    ) -> None:
        self.alpha = alpha
        self.max_runs = max_runs
        self._global_distribution = global_distribution
        self._parent_distributions = parent_distributions
        self._state_distributions = state_distributions

    @classmethod
    def fit(
        cls, observations: Iterable[RunObservation], *, alpha: float
    ) -> RunValueModel:
        rows = list(observations)
        if not rows:
            raise ValueError("observations must not be empty")
        counts = Counter((row.key, row.remaining_runs) for row in rows)
        return cls.fit_counts(counts, alpha=alpha)

    @classmethod
    def fit_counts(
        cls,
        counts: Mapping[tuple[RunStateKey, int], int],
        *,
        alpha: float,
    ) -> RunValueModel:
        if alpha <= 0:
            raise ValueError("alpha must be positive")
        weighted = {
            (key, runs): count
            for (key, runs), count in counts.items()
            if count > 0
        }
        if not weighted:
            raise ValueError("counts must contain positive observations")

        max_runs = max(runs for _, runs in weighted)
        support = range(max_runs + 1)
        global_counts: Counter[int] = Counter()
        for (_, runs), count in weighted.items():
            global_counts[runs] += count
        # 極小均勻先驗只為保證有限 NLL，不替代由 validation 選出的 alpha。
        epsilon = 1e-9
        global_total = sum(weighted.values()) + epsilon * (max_runs + 1)
        global_distribution = tuple(
            (global_counts[runs] + epsilon) / global_total for runs in support
        )

        parent_counts: dict[ParentKey, Counter[int]] = defaultdict(Counter)
        state_counts: dict[RunStateKey, Counter[int]] = defaultdict(Counter)
        for (key, runs), count in weighted.items():
            parent_counts[key.parent][runs] += count
            state_counts[key][runs] += count

        parent_distributions: dict[ParentKey, tuple[float, ...]] = {}
        for parent, counts in parent_counts.items():
            total = sum(counts.values()) + alpha
            parent_distributions[parent] = tuple(
                (counts[runs] + alpha * global_distribution[runs]) / total
                for runs in support
            )

        state_distributions: dict[RunStateKey, tuple[float, ...]] = {}
        for key, counts in state_counts.items():
            parent_distribution = parent_distributions[key.parent]
            total = sum(counts.values()) + alpha
            state_distributions[key] = tuple(
                (counts[runs] + alpha * parent_distribution[runs]) / total
                for runs in support
            )

        return cls(
            alpha=alpha,
            max_runs=max_runs,
            global_distribution=global_distribution,
            parent_distributions=parent_distributions,
            state_distributions=state_distributions,
        )

    def parent_distribution(self, key: RunStateKey) -> tuple[float, ...]:
        return self._parent_distributions.get(key.parent, self._global_distribution)

    def distribution(self, key: RunStateKey) -> tuple[float, ...]:
        return self._state_distributions.get(key, self.parent_distribution(key))

    @staticmethod
    def _expectation(distribution: tuple[float, ...]) -> float:
        return sum(runs * probability for runs, probability in enumerate(distribution))

    def expected_runs(self, key: RunStateKey, *, parent_only: bool = False) -> float:
        distribution = (
            self.parent_distribution(key) if parent_only else self.distribution(key)
        )
        return self._expectation(distribution)

    def metrics(
        self, observations: Iterable[RunObservation], *, parent_only: bool = False
    ) -> ValueMetrics:
        rows = list(observations)
        if not rows:
            raise ValueError("observations must not be empty")
        nll = 0.0
        absolute_error = 0.0
        for row in rows:
            row_nll, row_mae = self._losses(row, parent_only=parent_only)
            nll += row_nll
            absolute_error += row_mae
        return ValueMetrics(nll=nll / len(rows), mae=absolute_error / len(rows), n=len(rows))

    def _losses(
        self, observation: RunObservation, *, parent_only: bool
    ) -> tuple[float, float]:
        distribution = (
            self.parent_distribution(observation.key)
            if parent_only
            else self.distribution(observation.key)
        )
        probability = (
            distribution[observation.remaining_runs]
            if observation.remaining_runs < len(distribution)
            else 1e-15
        )
        nll = -math.log(max(probability, 1e-15))
        mae = abs(self._expectation(distribution) - observation.remaining_runs)
        return nll, mae

    def _transition_value(
        self, transition: Transition, *, parent_only: bool = False
    ) -> float:
        if transition.half_over:
            return float(transition.immediate_runs)
        if transition.next_state is None:
            raise ValueError("nonterminal transition must have next_state")
        key = RunStateKey.from_pitch_state(transition.next_state)
        return transition.immediate_runs + self.expected_runs(key, parent_only=parent_only)

    def call_values(self, state: PitchState) -> CallValues:
        ball_transition = transition_called_pitch(state, Call.BALL)
        strike_transition = transition_called_pitch(state, Call.STRIKE)
        ball = self._transition_value(ball_transition)
        strike = self._transition_value(strike_transition)
        if ball >= strike:
            return CallValues(ball=ball, strike=strike, backed_off=False)

        # 稀疏計數格若估出反向價值，回退到較穩健的父狀態估計。
        parent_ball = self._transition_value(ball_transition, parent_only=True)
        parent_strike = self._transition_value(strike_transition, parent_only=True)
        if parent_ball < parent_strike:
            conservative = (parent_ball + parent_strike) / 2
            parent_ball = parent_strike = conservative
        return CallValues(ball=parent_ball, strike=parent_strike, backed_off=True)


class WinProbabilityModel:
    """以 count-aware 或父狀態得分分布驅動相同的 CPBL 半局邊界 DP。"""

    def __init__(self, run_model: RunValueModel, *, count_aware: bool) -> None:
        from cpbl.models.winprob import _we_solver

        self.run_model = run_model
        self.count_aware = count_aware
        top = self._distribution(RunStateKey("1", "___", 0, 0, 0))
        bottom = self._distribution(RunStateKey("2", "___", 0, 0, 0))
        self._we_top, self._we_bottom = _we_solver(list(top), list(bottom))

    def _distribution(self, key: RunStateKey) -> tuple[float, ...]:
        if self.count_aware:
            return self.run_model.distribution(key)
        return self.run_model.parent_distribution(key)

    @staticmethod
    def _clip_diff(diff: int) -> int:
        from cpbl.models.winprob import DIFF_CLIP

        return max(-DIFF_CLIP, min(DIFF_CLIP, diff))

    @staticmethod
    def _score(win_tie: tuple[float, float]) -> float:
        win, tie = win_tie
        return win + 0.5 * tie

    def _after_half(self, state: PitchState) -> float:
        from cpbl.models.winprob import MAX_INNING

        inning = min(state.inning, MAX_INNING)
        diff = self._clip_diff(state.score_diff_home)
        if state.batting_side == "1":
            if inning >= 9 and diff > 0:
                return 1.0
            return self._score(self._we_bottom(inning, diff))
        if inning >= 9:
            if diff > 0:
                return 1.0
            if diff < 0:
                return 0.0
            if inning >= MAX_INNING:
                return 0.5
        return self._score(self._we_top(inning + 1, diff))

    def predict(self, state: PitchState) -> float:
        from cpbl.models.winprob import MAX_INNING

        inning = min(state.inning, MAX_INNING)
        distribution = self._distribution(RunStateKey.from_pitch_state(state))
        probability = 0.0
        for runs, weight in enumerate(distribution):
            if not weight:
                continue
            run_diff = -runs if state.batting_side == "1" else runs
            boundary_state = replace(
                state,
                inning=inning,
                score_diff_home=self._clip_diff(state.score_diff_home + run_diff),
            )
            probability += weight * self._after_half(boundary_state)
        return min(1.0, max(0.0, probability))

    def _transition_probability(self, state: PitchState, call: Call) -> float:
        transition = transition_called_pitch(state, call)
        if transition.half_over:
            boundary = replace(
                state,
                score_diff_home=state.score_diff_home
                + (
                    transition.immediate_runs
                    if state.batting_side == "2"
                    else -transition.immediate_runs
                ),
            )
            return self._after_half(boundary)
        if transition.next_state is None:
            raise ValueError("nonterminal transition must have next_state")
        return self.predict(transition.next_state)

    def call_values(self, state: PitchState) -> CallValues:
        ball = self._transition_probability(state, Call.BALL)
        strike = self._transition_probability(state, Call.STRIKE)
        monotone = ball >= strike if state.batting_side == "2" else ball <= strike
        if monotone:
            return CallValues(ball, strike, False)

        baseline = WinProbabilityModel(self.run_model, count_aware=False)
        parent_ball = baseline._transition_probability(state, Call.BALL)
        parent_strike = baseline._transition_probability(state, Call.STRIKE)
        parent_monotone = (
            parent_ball >= parent_strike
            if state.batting_side == "2"
            else parent_ball <= parent_strike
        )
        if not parent_monotone:
            conservative = (parent_ball + parent_strike) / 2
            parent_ball = parent_strike = conservative
        return CallValues(parent_ball, parent_strike, True)

    def metrics(self, observations: Iterable[WinObservation]) -> ProbabilityMetrics:
        rows = list(observations)
        if not rows:
            raise ValueError("observations must not be empty")
        predictions = [self.predict(row.state) for row in rows]
        outcomes = [row.outcome_home for row in rows]
        epsilon = 1e-15
        brier = sum((prediction - outcome) ** 2 for prediction, outcome in zip(predictions, outcomes, strict=True)) / len(rows)
        log_loss = -sum(
            outcome * math.log(max(prediction, epsilon))
            + (1 - outcome) * math.log(max(1 - prediction, epsilon))
            for prediction, outcome in zip(predictions, outcomes, strict=True)
        ) / len(rows)
        intercept, slope = _calibration_fit(predictions, outcomes)
        buckets: list[list[float]] = [[0.0, 0.0, 0.0] for _ in range(10)]
        for prediction, outcome in zip(predictions, outcomes, strict=True):
            bucket = buckets[min(int(prediction * 10), 9)]
            bucket[0] += prediction
            bucket[1] += outcome
            bucket[2] += 1
        ece = sum(
            abs(bucket[0] / bucket[2] - bucket[1] / bucket[2]) * bucket[2]
            for bucket in buckets
            if bucket[2]
        ) / len(rows)
        reliability = tuple(
            ReliabilityBin(
                lower=index / 10,
                upper=(index + 1) / 10,
                mean_prediction=bucket[0] / bucket[2],
                mean_outcome=bucket[1] / bucket[2],
                n=int(bucket[2]),
            )
            for index, bucket in enumerate(buckets)
            if bucket[2]
        )
        return ProbabilityMetrics(
            brier, log_loss, intercept, slope, ece, reliability, len(rows)
        )


def _calibration_fit(
    predictions: list[float], outcomes: list[float]
) -> tuple[float, float]:
    """以 fractional-binomial Newton steps 估 calibration intercept／slope。"""
    epsilon = 1e-9
    logits = [
        math.log(min(1 - epsilon, max(epsilon, probability)) / (1 - min(1 - epsilon, max(epsilon, probability))))
        for probability in predictions
    ]
    intercept, slope = 0.0, 1.0
    for _ in range(50):
        gradient_0 = gradient_1 = 0.0
        info_00 = info_01 = info_11 = 1e-8
        for logit, outcome in zip(logits, outcomes, strict=True):
            linear = max(-30.0, min(30.0, intercept + slope * logit))
            fitted = 1 / (1 + math.exp(-linear))
            residual = outcome - fitted
            weight = fitted * (1 - fitted)
            gradient_0 += residual
            gradient_1 += residual * logit
            info_00 += weight
            info_01 += weight * logit
            info_11 += weight * logit * logit
        determinant = info_00 * info_11 - info_01 * info_01
        if determinant <= 0:
            break
        delta_intercept = (info_11 * gradient_0 - info_01 * gradient_1) / determinant
        delta_slope = (-info_01 * gradient_0 + info_00 * gradient_1) / determinant
        intercept += delta_intercept
        slope += delta_slope
        if max(abs(delta_intercept), abs(delta_slope)) < 1e-8:
            break
    return intercept, slope


def bootstrap_probability_deltas(
    candidate: ProbabilityPredictor,
    baseline: ProbabilityPredictor,
    observations: Iterable[WinObservation],
    *,
    iterations: int = 2_000,
    seed: int = 0,
) -> ProbabilityBootstrapComparison:
    """以整場 paired cluster 重抽 candidate − baseline 的 Brier／LogLoss。"""
    if iterations <= 0:
        raise ValueError("iterations must be positive")
    epsilon = 1e-15
    by_game: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0, 0.0])
    for row in observations:
        candidate_probability = min(1 - epsilon, max(epsilon, candidate.predict(row.state)))
        baseline_probability = min(1 - epsilon, max(epsilon, baseline.predict(row.state)))
        outcome = row.outcome_home
        candidate_brier = (candidate_probability - outcome) ** 2
        baseline_brier = (baseline_probability - outcome) ** 2
        candidate_log_loss = -(
            outcome * math.log(candidate_probability)
            + (1 - outcome) * math.log(1 - candidate_probability)
        )
        baseline_log_loss = -(
            outcome * math.log(baseline_probability)
            + (1 - outcome) * math.log(1 - baseline_probability)
        )
        aggregate = by_game[row.game_id]
        aggregate[0] += candidate_brier - baseline_brier
        aggregate[1] += candidate_log_loss - baseline_log_loss
        aggregate[2] += 1
    if not by_game:
        raise ValueError("observations must not be empty")

    clusters = list(by_game.values())
    rng = random.Random(seed)
    brier_deltas: list[float] = []
    log_loss_deltas: list[float] = []
    for _ in range(iterations):
        sampled = rng.choices(clusters, k=len(clusters))
        count = sum(cluster[2] for cluster in sampled)
        brier_deltas.append(sum(cluster[0] for cluster in sampled) / count)
        log_loss_deltas.append(sum(cluster[1] for cluster in sampled) / count)
    return ProbabilityBootstrapComparison(
        games=len(clusters),
        iterations=iterations,
        brier_delta=ConfidenceInterval(
            _percentile(brier_deltas, 0.025), _percentile(brier_deltas, 0.975)
        ),
        log_loss_delta=ConfidenceInterval(
            _percentile(log_loss_deltas, 0.025),
            _percentile(log_loss_deltas, 0.975),
        ),
    )


def tune_alpha(
    train: Iterable[RunObservation],
    validation: Iterable[RunObservation],
    *,
    candidates: Iterable[float],
) -> AlphaTuning:
    train_rows = list(train)
    validation_rows = list(validation)
    candidate_values = tuple(candidates)
    if not candidate_values:
        raise ValueError("candidates must not be empty")
    metrics_by_alpha = {
        alpha: RunValueModel.fit(train_rows, alpha=alpha).metrics(validation_rows)
        for alpha in candidate_values
    }
    best_alpha = min(candidate_values, key=lambda alpha: metrics_by_alpha[alpha].nll)
    return AlphaTuning(alpha=best_alpha, metrics_by_alpha=metrics_by_alpha)


def _percentile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    index = (len(ordered) - 1) * probability
    lower = math.floor(index)
    upper = math.ceil(index)
    if lower == upper:
        return ordered[lower]
    fraction = index - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def bootstrap_metric_deltas(
    model: RunValueModel,
    observations: Iterable[RunObservation],
    *,
    iterations: int = 2_000,
    seed: int = 0,
) -> BootstrapComparison:
    """以整場為 cluster 重抽，回傳 candidate − parent baseline 的 95% CI。"""
    if iterations <= 0:
        raise ValueError("iterations must be positive")
    by_game: dict[str, list[float]] = defaultdict(lambda: [0.0] * 5)
    for row in observations:
        candidate_nll, candidate_mae = model._losses(row, parent_only=False)
        baseline_nll, baseline_mae = model._losses(row, parent_only=True)
        aggregate = by_game[row.game_id]
        aggregate[0] += candidate_nll - baseline_nll
        aggregate[1] += candidate_mae - baseline_mae
        aggregate[2] += 1
    if not by_game:
        raise ValueError("observations must not be empty")

    clusters = list(by_game.values())
    rng = random.Random(seed)
    nll_deltas: list[float] = []
    mae_deltas: list[float] = []
    for _ in range(iterations):
        sampled = rng.choices(clusters, k=len(clusters))
        count = sum(cluster[2] for cluster in sampled)
        nll_deltas.append(sum(cluster[0] for cluster in sampled) / count)
        mae_deltas.append(sum(cluster[1] for cluster in sampled) / count)
    return BootstrapComparison(
        games=len(clusters),
        iterations=iterations,
        nll_delta=ConfidenceInterval(
            _percentile(nll_deltas, 0.025), _percentile(nll_deltas, 0.975)
        ),
        mae_delta=ConfidenceInterval(
            _percentile(mae_deltas, 0.025), _percentile(mae_deltas, 0.975)
        ),
    )


def post_to_pre_count(call: Call, post_balls: int, post_strikes: int) -> tuple[int, int]:
    """把官方 TrackMan 的 post-call count 還原為判決前球數。"""
    if call is Call.BALL:
        if not 1 <= post_balls <= 4 or not 0 <= post_strikes <= 2:
            raise ValueError("invalid post-call count for BallCalled")
        return post_balls - 1, post_strikes
    if not 0 <= post_balls <= 3 or not 1 <= post_strikes <= 3:
        raise ValueError("invalid post-call count for StrikeCalled")
    return post_balls, post_strikes - 1


def proxy_call(side: float, height: float, zone: ProxyZone = DEFAULT_PROXY_ZONE) -> Call:
    in_zone = abs(side) <= zone.half_width and zone.bottom <= height <= zone.top
    return Call.STRIKE if in_zone else Call.BALL


def score_called_pitch(
    pitch: CalledPitch,
    run_model: RunValueModel,
    zone: ProxyZone = DEFAULT_PROXY_ZONE,
) -> PitchScore:
    proxy = proxy_call(pitch.plate_loc_side, pitch.plate_loc_height, zone)
    values = run_model.call_values(pitch.state)
    observed_value = values.ball if pitch.observed_call is Call.BALL else values.strike
    proxy_value = values.ball if proxy is Call.BALL else values.strike
    return PitchScore(
        pitch=pitch,
        proxy_call=proxy,
        proxy_disagreement=pitch.observed_call is not proxy,
        edge_distance_cm=signed_edge_distance_cm(
            pitch.plate_loc_side, pitch.plate_loc_height, zone
        ),
        run_value_ball=values.ball,
        run_value_strike=values.strike,
        delta_runs_offense=observed_value - proxy_value,
        backed_off=values.backed_off,
    )


def aggregate_umpires(scores: Iterable[PitchScore]) -> list[UmpireAggregate]:
    grouped: dict[str, list[PitchScore]] = defaultdict(list)
    for score in scores:
        grouped[score.pitch.umpire].append(score)
    output: list[UmpireAggregate] = []
    for umpire, rows in grouped.items():
        total = sum(row.delta_runs_offense for row in rows)
        output.append(
            UmpireAggregate(
                umpire=umpire,
                games=len({row.pitch.game_id for row in rows}),
                called_pitches=len(rows),
                proxy_disagreements=sum(row.proxy_disagreement for row in rows),
                sum_delta_runs_offense=total,
                per_100_called=total / len(rows) * 100,
            )
        )
    return sorted(output, key=lambda row: row.umpire)


def aggregate_teams(scores: Iterable[PitchScore]) -> list[TeamAggregate]:
    calls_for: Counter[str] = Counter()
    calls_against: Counter[str] = Counter()
    value_for: Counter[str] = Counter()
    value_against: Counter[str] = Counter()
    for score in scores:
        calls_for[score.pitch.batting_team] += 1
        calls_against[score.pitch.fielding_team] += 1
        value_for[score.pitch.batting_team] += score.delta_runs_offense
        value_against[score.pitch.fielding_team] += score.delta_runs_offense
    teams = sorted(set(calls_for) | set(calls_against))
    return [
        TeamAggregate(
            team,
            calls_for[team],
            calls_against[team],
            value_for[team],
            value_against[team],
        )
        for team in teams
    ]


def bootstrap_umpire_aggregates(
    historical: Iterable[RunObservation],
    pitches: Iterable[CalledPitch],
    *,
    alpha: float,
    iterations: int = 2_000,
    seed: int = 0,
) -> list[UmpireBootstrap]:
    """相容舊介面；主審與球隊仍由同一組 replicate 共同估計。"""
    return list(
        bootstrap_impact_aggregates(
            historical,
            pitches,
            alpha=alpha,
            iterations=iterations,
            seed=seed,
        ).umpires
    )


def bootstrap_impact_aggregates(
    historical: Iterable[RunObservation],
    pitches: Iterable[CalledPitch],
    *,
    alpha: float,
    iterations: int = 2_000,
    seed: int = 0,
) -> ImpactBootstrap:
    """同時重抽歷史與 scoring 場次，重算主審及球隊聚合的 95% 區間。"""
    if iterations <= 0:
        raise ValueError("iterations must be positive")
    history_profiles: dict[str, Counter[tuple[RunStateKey, int]]] = defaultdict(Counter)
    for row in historical:
        history_profiles[row.game_id][(row.key, row.remaining_runs)] += 1
    scoring_games: dict[str, list[CalledPitch]] = defaultdict(list)
    for pitch in pitches:
        scoring_games[pitch.game_id].append(pitch)
    if not history_profiles or not scoring_games:
        raise ValueError("historical and pitches must not be empty")

    history_ids = list(history_profiles)
    scoring_ids = list(scoring_games)
    umpires = sorted({pitch.umpire for rows in scoring_games.values() for pitch in rows})
    teams = sorted(
        {
            team
            for rows in scoring_games.values()
            for pitch in rows
            for team in (pitch.batting_team, pitch.fielding_team)
        }
    )
    total_samples: dict[str, list[float]] = defaultdict(list)
    rate_samples: dict[str, list[float]] = defaultdict(list)
    team_for_samples: dict[str, list[float]] = defaultdict(list)
    team_against_samples: dict[str, list[float]] = defaultdict(list)
    team_for_rate_samples: dict[str, list[float]] = defaultdict(list)
    team_against_rate_samples: dict[str, list[float]] = defaultdict(list)
    rng = random.Random(seed)
    for _ in range(iterations):
        history_weights = Counter(rng.choices(history_ids, k=len(history_ids)))
        combined: Counter[tuple[RunStateKey, int]] = Counter()
        for game_id, weight in history_weights.items():
            for cell, count in history_profiles[game_id].items():
                combined[cell] += count * weight
        model = RunValueModel.fit_counts(combined, alpha=alpha)

        scoring_weights = Counter(rng.choices(scoring_ids, k=len(scoring_ids)))
        totals: Counter[str] = Counter()
        calls: Counter[str] = Counter()
        team_for_totals: Counter[str] = Counter()
        team_against_totals: Counter[str] = Counter()
        team_for_calls: Counter[str] = Counter()
        team_against_calls: Counter[str] = Counter()
        value_cache: dict[tuple[RunStateKey, Call, Call], float] = {}
        for game_id, weight in scoring_weights.items():
            for pitch in scoring_games[game_id]:
                calls[pitch.umpire] += weight
                team_for_calls[pitch.batting_team] += weight
                team_against_calls[pitch.fielding_team] += weight
                proxy = proxy_call(pitch.plate_loc_side, pitch.plate_loc_height)
                cache_key = (
                    RunStateKey.from_pitch_state(pitch.state),
                    pitch.observed_call,
                    proxy,
                )
                if cache_key not in value_cache:
                    values = model.call_values(pitch.state)
                    observed_value = (
                        values.ball if pitch.observed_call is Call.BALL else values.strike
                    )
                    proxy_value = values.ball if proxy is Call.BALL else values.strike
                    value_cache[cache_key] = observed_value - proxy_value
                totals[pitch.umpire] += value_cache[cache_key] * weight
                team_for_totals[pitch.batting_team] += value_cache[cache_key] * weight
                team_against_totals[pitch.fielding_team] += value_cache[cache_key] * weight
        for umpire in umpires:
            total_samples[umpire].append(totals[umpire])
            rate_samples[umpire].append(
                totals[umpire] / calls[umpire] * 100 if calls[umpire] else 0.0
            )
        for team in teams:
            team_for_samples[team].append(team_for_totals[team])
            team_against_samples[team].append(team_against_totals[team])
            team_for_rate_samples[team].append(
                team_for_totals[team] / team_for_calls[team] * 100
                if team_for_calls[team]
                else 0.0
            )
            team_against_rate_samples[team].append(
                team_against_totals[team] / team_against_calls[team] * 100
                if team_against_calls[team]
                else 0.0
            )

    umpire_intervals = tuple(
        UmpireBootstrap(
            umpire=umpire,
            iterations=iterations,
            total=QuantileInterval(
                _percentile(total_samples[umpire], 0.025),
                _percentile(total_samples[umpire], 0.5),
                _percentile(total_samples[umpire], 0.975),
            ),
            per_100_called=QuantileInterval(
                _percentile(rate_samples[umpire], 0.025),
                _percentile(rate_samples[umpire], 0.5),
                _percentile(rate_samples[umpire], 0.975),
            ),
        )
        for umpire in umpires
    )

    def interval(samples: list[float]) -> QuantileInterval:
        return QuantileInterval(
            _percentile(samples, 0.025),
            _percentile(samples, 0.5),
            _percentile(samples, 0.975),
        )

    team_intervals = tuple(
        TeamBootstrap(
            team=team,
            iterations=iterations,
            state_value_for=interval(team_for_samples[team]),
            state_value_against=interval(team_against_samples[team]),
            per_100_for=interval(team_for_rate_samples[team]),
            per_100_against=interval(team_against_rate_samples[team]),
        )
        for team in teams
    )
    return ImpactBootstrap(umpires=umpire_intervals, teams=team_intervals)


def signed_edge_distance_cm(
    side: float, height: float, zone: ProxyZone = DEFAULT_PROXY_ZONE
) -> float:
    """到代理帶邊界的最短距離；帶內為正、帶外為負。"""
    horizontal_margin = zone.half_width - abs(side)
    lower_margin = height - zone.bottom
    upper_margin = zone.top - height
    if horizontal_margin >= 0 and lower_margin >= 0 and upper_margin >= 0:
        return min(horizontal_margin, lower_margin, upper_margin) * 100.0
    dx = max(abs(side) - zone.half_width, 0.0)
    dy = max(zone.bottom - height, height - zone.top, 0.0)
    return -math.hypot(dx, dy) * 100.0


def _walk_bases(bases: str) -> tuple[str, int]:
    first, second, third = (c != "_" for c in bases)
    run = int(first and second and third)
    next_third = third or (first and second)
    next_second = second or first
    return "1" + ("2" if next_second else "_") + ("3" if next_third else "_"), run


def transition_called_pitch(state: PitchState, call: Call) -> Transition:
    """套用標準 called ball／strike；未捕第三好球等例外由資料層隔離。"""
    if call is Call.BALL and state.balls < 3:
        return Transition(replace(state, balls=state.balls + 1), 0, False)
    if call is Call.STRIKE and state.strikes < 2:
        return Transition(replace(state, strikes=state.strikes + 1), 0, False)
    if call is Call.BALL:
        bases, runs = _walk_bases(state.bases)
        diff = state.score_diff_home + (runs if state.batting_side == "2" else -runs)
        return Transition(
            replace(state, score_diff_home=diff, bases=bases, balls=0, strikes=0),
            runs,
            False,
        )
    if state.outs == 2:
        return Transition(None, 0, True)
    return Transition(replace(state, outs=state.outs + 1, balls=0, strikes=0), 0, False)
