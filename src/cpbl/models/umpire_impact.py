"""好球帶判決差異研究的純狀態邏輯。

本模組不把固定代理帶視為規則真值。`ProxyZone` 只重現既有 UI 的
`fixed_zone_proxy_v1` 契約；資料載入、估計與報告留在後續切片。
"""

from __future__ import annotations

import math
import random
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, replace
from enum import StrEnum


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
        if alpha <= 0:
            raise ValueError("alpha must be positive")

        max_runs = max(row.remaining_runs for row in rows)
        support = range(max_runs + 1)
        global_counts = Counter(row.remaining_runs for row in rows)
        # 極小均勻先驗只為保證有限 NLL，不替代由 validation 選出的 alpha。
        epsilon = 1e-9
        global_total = len(rows) + epsilon * (max_runs + 1)
        global_distribution = tuple(
            (global_counts[runs] + epsilon) / global_total for runs in support
        )

        parent_counts: dict[ParentKey, Counter[int]] = defaultdict(Counter)
        state_counts: dict[RunStateKey, Counter[int]] = defaultdict(Counter)
        for row in rows:
            parent_counts[row.key.parent][row.remaining_runs] += 1
            state_counts[row.key][row.remaining_runs] += 1

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
