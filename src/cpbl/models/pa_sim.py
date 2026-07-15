"""單一打席情境模擬的資料快照與結果分類。"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from cpbl.ingest.splits_calc import PA_OUTCOME

OUTCOMES = ("K", "BB_HBP", "1B", "XBH", "HR", "BIP_OUT", "OTHER_REACH")
_REACH_ACTIONS = {
    "一失", "二失", "三失", "游失", "投失", "捕失", "中失", "左失", "右失",
    "失", "雙誤", "野選", "礙打", "犧短誤", "犧飛誤",
}


@dataclass(frozen=True)
class PAEvent:
    event_no: int
    inning: int
    half: str
    hitter: str
    pitcher: str
    bases: str
    outs: int
    away_score: int
    home_score: int
    action: str | None


@dataclass(frozen=True)
class GameState:
    inning: int
    half: str
    bases: str
    outs: int
    away_score: int
    home_score: int


@dataclass(frozen=True)
class PASnapshot:
    event_no: int
    hitter: str
    pitcher: str
    result: str
    before: GameState
    after: GameState
    runs_delta: int
    inning_ended: bool
    game_ended: bool


@dataclass(frozen=True)
class PAAudit:
    total_pa: int
    classified_pa: int
    rebuilt_pa: int
    unknown_actions: dict[str, int]

    @property
    def classification_rate(self) -> float:
        return self.classified_pa / self.total_pa if self.total_pa else 0.0

    @property
    def rebuild_rate(self) -> float:
        return self.rebuilt_pa / self.total_pa if self.total_pa else 0.0


def classify_action(action: str | None) -> str | None:
    """將官方打席結果詞彙映射成互斥結果；未知詞彙一律不猜。"""
    if not action or action not in PA_OUTCOME:
        return None
    delta = PA_OUTCOME[action]
    if delta.get("so"):
        return "K"
    if delta.get("bb") or delta.get("hbp"):
        return "BB_HBP"
    if delta.get("home_runs"):
        return "HR"
    if delta.get("singles"):
        return "1B"
    if delta.get("doubles") or delta.get("triples"):
        return "XBH"
    if action in _REACH_ACTIONS:
        return "OTHER_REACH"
    return "BIP_OUT"


def events_from_rows(rows: Iterable[Mapping]) -> list[PAEvent]:
    """將 livelog 的事件後比分轉成打席模型需要的事件前比分。"""
    away_score = home_score = 0
    events: list[PAEvent] = []
    for row in rows:
        if all(row.get(key) is not None for key in ("inning", "half", "hitter", "pitcher")):
            bases = (
                ("1" if row.get("first_base") else "_")
                + ("2" if row.get("second_base") else "_")
                + ("3" if row.get("third_base") else "_")
            )
            events.append(
                PAEvent(
                    event_no=int(row["event_no"]),
                    inning=int(row["inning"]),
                    half=str(row["half"]),
                    hitter=str(row["hitter"]),
                    pitcher=str(row["pitcher"]),
                    bases=bases,
                    outs=int(row.get("outs") or 0),
                    away_score=away_score,
                    home_score=home_score,
                    action=row.get("action"),
                )
            )
        if row.get("post_away") is not None:
            away_score = int(row["post_away"])
        if row.get("post_home") is not None:
            home_score = int(row["post_home"])
    return events


def _state(event: PAEvent) -> GameState:
    return GameState(
        inning=event.inning,
        half=event.half,
        bases=event.bases,
        outs=min(max(event.outs, 0), 2),
        away_score=event.away_score,
        home_score=event.home_score,
    )


def _group_events(events: list[PAEvent]) -> list[list[PAEvent]]:
    groups: list[list[PAEvent]] = []
    for event in sorted(events, key=lambda row: row.event_no):
        key = (event.inning, event.half, event.hitter)
        current_key = None
        if groups:
            current = groups[-1][0]
            current_key = (current.inning, current.half, current.hitter)
        if key != current_key:
            groups.append([])
        groups[-1].append(event)
    return groups


def build_pa_snapshots(
    events: list[PAEvent], final_score: tuple[int, int] | None = None,
) -> list[PASnapshot]:
    """由依事件序排列的資料，以「下一打席首事件」取得實際 post-state。

    最後一個打席沒有下一狀態時不猜測，由資料稽核列入未重建樣本。
    """
    if not events:
        return []
    groups = _group_events(events)

    snapshots: list[PASnapshot] = []
    for index, group in enumerate(groups):
        action = next((row.action for row in reversed(group) if row.action), None)
        result = classify_action(action)
        if result is None:
            continue
        first = group[0]
        before = _state(first)
        game_ended = index == len(groups) - 1
        if game_ended:
            if final_score is None:
                continue
            away_score, home_score = final_score
            after = GameState(
                inning=before.inning,
                half=before.half,
                bases="___",
                outs=0,
                away_score=away_score,
                home_score=home_score,
            )
        else:
            after = _state(groups[index + 1][0])
        batting_before = before.away_score if before.half == "1" else before.home_score
        batting_after = after.away_score if before.half == "1" else after.home_score
        snapshots.append(
            PASnapshot(
                event_no=first.event_no,
                hitter=first.hitter,
                pitcher=first.pitcher,
                result=result,
                before=before,
                after=after,
                runs_delta=max(0, batting_after - batting_before),
                inning_ended=game_ended or (
                    (before.inning, before.half) != (after.inning, after.half)
                ),
                game_ended=game_ended,
            )
        )
    return snapshots


def audit_pa_events(
    events: list[PAEvent], final_score: tuple[int, int] | None = None,
) -> PAAudit:
    """統計可分類與可重建率；未知官方詞彙完整回報，不以其他類別吸收。"""
    groups = _group_events(events)
    actions = [
        next((row.action for row in reversed(group) if row.action), None)
        for group in groups
    ]
    terminal_actions = [action for action in actions if action]
    unknown = Counter(action for action in terminal_actions if classify_action(action) is None)
    classified = sum(classify_action(action) is not None for action in terminal_actions)
    rebuilt = len(build_pa_snapshots(events, final_score))
    return PAAudit(
        total_pa=len(terminal_actions),
        classified_pa=classified,
        rebuilt_pa=rebuilt,
        unknown_actions=dict(sorted(unknown.items())),
    )
