"""GAME-RECAP-DATA1：賽事復盤資料覆蓋與 canonical 打席契約唯讀稽核。"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any

Event = dict[str, Any]


@dataclass(frozen=True)
class PitchLinkageRisks:
    unique_keys: int
    ambiguous_keys: int
    ambiguous_plate_appearances: int


@dataclass(frozen=True)
class GameEventAudit:
    box_pa: int
    run_dist_pa: int
    winprob_pa: int
    frontend_pa: int
    blank_action_rows: int
    change_rows: int
    pitching_change_rows: int
    repeated_matchup_keys: int
    repeated_matchup_pas: int


def _usable(event: Event) -> bool:
    return not event.get("is_change_player") and bool(event.get("hitter_acnt"))


def legacy_pa_starts(events: list[Event]) -> dict[str, list[str]]:
    """重現三套現行近似分組；回傳各自認定的打席首事件。

    run_dist 在每半局以 (batting_order, hitter) 去重；WP 再加 inning/half，
    實際效果相同但 scope 不同；前端以半局內連續同打者分組，換人事件切斷群組。
    """
    run_dist: list[str] = []
    winprob: list[str] = []
    frontend: list[str] = []
    run_seen: dict[tuple[Any, str], set[tuple[Any, Any]]] = {}
    wp_seen: set[tuple[Any, str, Any, Any]] = set()
    previous_half: tuple[Any, str] | None = None
    previous_hitter: Any = None

    for event in events:
        half = (event.get("inning_seq"), str(event.get("visiting_home_type")))
        if half != previous_half:
            previous_half = half
            previous_hitter = None
        if not _usable(event):
            previous_hitter = None
            continue

        event_no = str(event["main_event_no"])
        hitter = event.get("hitter_acnt")
        compact_key = (event.get("batting_order"), hitter)
        half_seen = run_seen.setdefault(half, set())
        if compact_key not in half_seen:
            half_seen.add(compact_key)
            run_dist.append(event_no)

        wp_key = (*half, *compact_key)
        if wp_key not in wp_seen:
            wp_seen.add(wp_key)
            winprob.append(event_no)

        if hitter != previous_hitter:
            frontend.append(event_no)
        previous_hitter = hitter

    return {"run_dist": run_dist, "winprob": winprob, "frontend": frontend}


def pitch_linkage_risks(pa_starts: list[Event]) -> PitchLinkageRisks:
    """量化現行 (inning, pitcher, hitter) 逐球鍵可指向幾個近似打席。"""
    keys = Counter(
        (
            event.get("inning_seq"),
            event.get("pitcher_acnt"),
            event.get("hitter_acnt"),
        )
        for event in pa_starts
        if event.get("pitcher_acnt") and event.get("hitter_acnt")
    )
    return PitchLinkageRisks(
        unique_keys=sum(count == 1 for count in keys.values()),
        ambiguous_keys=sum(count > 1 for count in keys.values()),
        ambiguous_plate_appearances=sum(count for count in keys.values() if count > 1),
    )


def classify_tracking_availability(
    *, game_started: bool, game_pitch_count: int, venue_tracked_games: int
) -> str:
    """只依觀測證據分類，不把「未觀測到」冒充官方設備清冊。"""
    if not game_started:
        return "not_expected_yet"
    if game_pitch_count > 0:
        return "available"
    if venue_tracked_games > 0:
        return "expected_missing"
    return "equipment_unobserved"


def audit_game_events(events: list[Event], *, box_pa: int) -> GameEventAudit:
    """彙整單場三套近似 PA 分母與資料風險，不宣稱任何一套是 canonical。"""
    starts = legacy_pa_starts(events)
    by_event_no = {str(event["main_event_no"]): event for event in events}
    frontend_starts = [by_event_no[event_no] for event_no in starts["frontend"]]
    linkage = pitch_linkage_risks(frontend_starts)
    usable = [event for event in events if _usable(event)]
    change_rows = [event for event in events if event.get("is_change_player")]
    return GameEventAudit(
        box_pa=box_pa,
        run_dist_pa=len(starts["run_dist"]),
        winprob_pa=len(starts["winprob"]),
        frontend_pa=len(starts["frontend"]),
        blank_action_rows=sum(not str(event.get("action_name") or "").strip() for event in usable),
        change_rows=len(change_rows),
        pitching_change_rows=sum("投手" in str(event.get("content") or "") for event in change_rows),
        repeated_matchup_keys=linkage.ambiguous_keys,
        repeated_matchup_pas=linkage.ambiguous_plate_appearances,
    )
