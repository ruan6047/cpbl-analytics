"""好球帶判決差異研究的純狀態邏輯。

本模組不把固定代理帶視為規則真值。`ProxyZone` 只重現既有 UI 的
`fixed_zone_proxy_v1` 契約；資料載入、估計與報告留在後續切片。
"""

from __future__ import annotations

import math
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
