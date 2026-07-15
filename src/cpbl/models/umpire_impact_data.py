"""ML-UMP1 的資料契約、唯讀 audit 與資料載入。

所有研究 SQL 都限制在 `cpbl` schema，且不寫入資料庫。TrackMan 與 livelog
只能在完整狀態鍵恰好命中一列時使用；零筆或多筆一律隔離。
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass
from itertools import groupby
from typing import Any

from cpbl.models.umpire_impact import (
    Call,
    CalledPitch,
    PitchState,
    RunObservation,
    RunStateKey,
    WinObservation,
    post_to_pre_count,
)

LINKED_CALLED_CTE = """
WITH tracking AS (
  SELECT t.*
  FROM cpbl.pitch_tracking t
  WHERE t.year = %(season)s AND t.kind_code = %(kind)s
    AND t.pitch_call IN ('StrikeCalled', 'BallCalled')
), live_context AS (
  SELECT l.*,
         COALESCE(max(l.visiting_score) OVER (
           PARTITION BY l.year, l.kind_code, l.game_sno
           ORDER BY l.main_event_no::bigint
           ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING), 0) AS pre_away_score,
         COALESCE(max(l.home_score) OVER (
           PARTITION BY l.year, l.kind_code, l.game_sno
           ORDER BY l.main_event_no::bigint
           ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING), 0) AS pre_home_score
  FROM cpbl.game_livelog l
  WHERE l.year = %(season)s AND l.kind_code = %(kind)s
), candidate_rows AS (
  SELECT t.year, t.kind_code, t.game_sno, t.pitcher_acnt, t.pitch_cnt,
         t.hitter_acnt, t.inning_seq, t.batting_order,
         t.ball_cnt, t.strike_cnt, t.out_cnt, t.pitch_call,
         t.plate_loc_side, t.plate_loc_height,
         l.main_event_no, l.catcher_acnt, l.visiting_home_type,
         l.first_base, l.second_base, l.third_base,
         l.pre_away_score, l.pre_home_score, l.content
  FROM tracking t
  LEFT JOIN live_context l
    ON l.year = t.year AND l.kind_code = t.kind_code AND l.game_sno = t.game_sno
   AND l.pitcher_acnt = t.pitcher_acnt
   AND l.hitter_acnt = t.hitter_acnt
   AND l.inning_seq = t.inning_seq
   AND l.batting_order = t.batting_order
   AND l.pitch_cnt = t.pitch_cnt
   AND l.ball_cnt = t.ball_cnt
   AND l.strike_cnt = t.strike_cnt
   AND l.out_cnt = t.out_cnt
   AND ((t.pitch_call = 'BallCalled' AND l.is_ball)
        OR (t.pitch_call = 'StrikeCalled' AND l.is_strike))
), match_counts AS (
  SELECT year, kind_code, game_sno, pitcher_acnt, pitch_cnt,
         count(main_event_no) AS match_count
  FROM candidate_rows
  GROUP BY year, kind_code, game_sno, pitcher_acnt, pitch_cnt
), linked_called AS (
  SELECT c.*
  FROM candidate_rows c
  JOIN match_counts m USING (year, kind_code, game_sno, pitcher_acnt, pitch_cnt)
  WHERE m.match_count = 1 AND c.main_event_no IS NOT NULL
)
"""


SCORED_CALLED_SQL = LINKED_CALLED_CTE + """
, game_meta AS (
  SELECT year, kind_code, game_sno,
         min(venue) AS venue,
         min(home_team_code) AS home_team_code,
         min(away_team_code) AS away_team_code
  FROM cpbl.games
  WHERE year = %(season)s AND kind_code = %(kind)s
  GROUP BY year, kind_code, game_sno
  HAVING count(DISTINCT ROW(venue, home_team_code, away_team_code)) = 1
)
SELECT l.year, l.kind_code, l.game_sno, l.pitcher_acnt, l.pitch_cnt,
       l.pitch_call, l.ball_cnt, l.strike_cnt, l.out_cnt, l.inning_seq,
       l.visiting_home_type, l.first_base, l.second_base, l.third_base,
       l.pre_away_score, l.pre_home_score,
       l.plate_loc_side, l.plate_loc_height, l.catcher_acnt,
       d.head_umpire, g.venue, g.home_team_code, g.away_team_code
FROM linked_called l
LEFT JOIN game_meta g USING (year, kind_code, game_sno)
LEFT JOIN cpbl.game_detail d USING (year, kind_code, game_sno)
ORDER BY l.game_sno, l.pitcher_acnt, l.pitch_cnt
"""


@dataclass(frozen=True, slots=True)
class LinkedCalledRow:
    year: int
    kind_code: str
    game_sno: int
    pitcher_acnt: str
    pitch_cnt: int
    pitch_call: str
    ball_cnt: int | None
    strike_cnt: int | None
    out_cnt: int | None
    inning_seq: int | None
    visiting_home_type: str | None
    first_base: str | None
    second_base: str | None
    third_base: str | None
    pre_away_score: int | None
    pre_home_score: int | None
    plate_loc_side: float | None
    plate_loc_height: float | None
    catcher_acnt: str | None
    head_umpire: str | None
    venue: str | None
    home_team_code: str | None
    away_team_code: str | None


@dataclass(frozen=True, slots=True)
class ScoringPitchData:
    pitches: tuple[CalledPitch, ...]
    exclusions: dict[str, int]


def build_called_pitches(rows: list[LinkedCalledRow]) -> ScoringPitchData:
    pitches: list[CalledPitch] = []
    exclusions: dict[str, int] = defaultdict(int)
    for row in rows:
        if row.plate_loc_side is None or row.plate_loc_height is None:
            exclusions["missing_location"] += 1
            continue
        if (
            row.out_cnt is None
            or row.inning_seq is None
            or row.visiting_home_type not in {"1", "2"}
            or row.pre_away_score is None
            or row.pre_home_score is None
            or row.catcher_acnt is None
        ):
            exclusions["missing_state_context"] += 1
            continue
        if (
            row.head_umpire is None
            or row.venue is None
            or row.home_team_code is None
            or row.away_team_code is None
        ):
            exclusions["missing_game_metadata"] += 1
            continue
        observed = Call.BALL if row.pitch_call == "BallCalled" else Call.STRIKE
        try:
            balls, strikes = post_to_pre_count(observed, row.ball_cnt, row.strike_cnt)
            bases = (
                ("1" if row.first_base else "_")
                + ("2" if row.second_base else "_")
                + ("3" if row.third_base else "_")
            )
            state = PitchState(
                batting_side=row.visiting_home_type,
                inning=row.inning_seq,
                score_diff_home=row.pre_home_score - row.pre_away_score,
                bases=bases,
                outs=row.out_cnt,
                balls=balls,
                strikes=strikes,
            )
        except (TypeError, ValueError):
            exclusions["invalid_post_count"] += 1
            continue
        batting_team = (
            row.away_team_code
            if row.visiting_home_type == "1"
            else row.home_team_code
        )
        fielding_team = (
            row.home_team_code
            if row.visiting_home_type == "1"
            else row.away_team_code
        )
        pitches.append(
            CalledPitch(
                year=row.year,
                kind_code=row.kind_code,
                game_sno=row.game_sno,
                pitcher_acnt=row.pitcher_acnt,
                pitch_cnt=row.pitch_cnt,
                umpire=row.head_umpire,
                batting_team=batting_team,
                fielding_team=fielding_team,
                catcher_acnt=row.catcher_acnt,
                venue=row.venue,
                state=state,
                plate_loc_side=row.plate_loc_side,
                plate_loc_height=row.plate_loc_height,
                observed_call=observed,
            )
        )
    return ScoringPitchData(tuple(pitches), dict(exclusions))


def load_called_pitches(
    connection: Any, season: int, kind: str = "A"
) -> ScoringPitchData:
    cursor = connection.execute(SCORED_CALLED_SQL, {"season": season, "kind": kind})
    return build_called_pitches([LinkedCalledRow(*row) for row in cursor])


HISTORICAL_LIVELOG_SQL = """
SELECT year, kind_code, game_sno, main_event_no::bigint,
       inning_seq, visiting_home_type, batting_order,
       hitter_acnt, pitcher_acnt, pitch_cnt, out_cnt, ball_cnt, strike_cnt,
       first_base, second_base, third_base,
       is_ball, is_strike, batting_action_name, is_change_player,
       visiting_score, home_score
FROM cpbl.game_livelog
WHERE year BETWEEN %(from_year)s AND %(to_year)s
  AND kind_code = %(kind)s
ORDER BY year, game_sno, main_event_no::bigint
"""


@dataclass(frozen=True, slots=True)
class LivelogRow:
    year: int
    kind_code: str
    game_sno: int
    main_event_no: int
    inning: int | None
    side: str | None
    batting_order: int | None
    hitter_acnt: str | None
    pitcher_acnt: str | None
    pitch_cnt: int | None
    outs: int | None
    balls: int | None
    strikes: int | None
    first_base: str | None
    second_base: str | None
    third_base: str | None
    is_ball: bool | None
    is_strike: bool | None
    batting_action_name: str | None
    is_change_player: bool | None
    away_score: int | None
    home_score: int | None


@dataclass(frozen=True, slots=True)
class HistoricalRunData:
    observations: tuple[RunObservation, ...]
    win_observations: tuple[WinObservation, ...]
    games: int
    excluded_final_halves: int
    duplicate_pitch_rows: int
    invalid_states: int


def _pitch_candidate(row: LivelogRow) -> bool:
    return bool(
        not row.is_change_player
        and row.hitter_acnt
        and row.pitcher_acnt
        and row.pitch_cnt is not None
        and (row.is_ball or row.is_strike or row.batting_action_name)
    )


def _build_game_observations(
    rows: list[LivelogRow],
) -> tuple[list[RunObservation], list[WinObservation], int, int, int]:
    """單場重建；回 observations、末半局數、重複投球列數、無效狀態數。"""
    if not rows:
        return [], [], 0, 0, 0

    pre_scores: dict[int, tuple[int, int]] = {}
    half_order: list[tuple[int, str]] = []
    half_scores: dict[tuple[int, str], int] = {}
    away_score = home_score = 0
    for row in rows:
        pre_scores[row.main_event_no] = away_score, home_score
        if row.away_score is not None:
            away_score = row.away_score
        if row.home_score is not None:
            home_score = row.home_score
        if row.inning is None or row.side not in {"1", "2"}:
            continue
        half = row.inning, row.side
        if half not in half_scores:
            half_order.append(half)
        batting_score = away_score if row.side == "1" else home_score
        half_scores[half] = max(half_scores.get(half, 0), batting_score)

    if not half_order:
        return [], [], 0, 0, 0
    excluded_halves = {half_order[-1]}

    pitch_groups: dict[tuple[int, str, str, int], list[LivelogRow]] = defaultdict(list)
    for row in rows:
        if not _pitch_candidate(row) or row.inning is None or row.side not in {"1", "2"}:
            continue
        identity = row.inning, row.side, str(row.pitcher_acnt), int(row.pitch_cnt)
        pitch_groups[identity].append(row)

    selected: list[LivelogRow] = []
    duplicate_pitch_rows = 0
    for candidates in pitch_groups.values():
        duplicate_pitch_rows += len(candidates) - 1
        called = [row for row in candidates if row.is_ball or row.is_strike]
        selected.append(min(called or candidates, key=lambda row: row.main_event_no))
    selected.sort(key=lambda row: row.main_event_no)

    observations: list[RunObservation] = []
    win_observations: list[WinObservation] = []
    invalid_states = 0
    previous_pa: tuple[int, str, int | None, str] | None = None
    previous_post_count: tuple[int | None, int | None] = (None, None)
    game_id = f"{rows[0].year}-{rows[0].kind_code}-{rows[0].game_sno}"
    outcome_home = 1.0 if home_score > away_score else (0.0 if home_score < away_score else 0.5)
    for row in selected:
        half = int(row.inning), str(row.side)
        if half in excluded_halves:
            continue
        pa = half[0], half[1], row.batting_order, str(row.hitter_acnt)
        balls, strikes = (0, 0) if pa != previous_pa else previous_post_count
        previous_pa = pa
        previous_post_count = row.balls, row.strikes
        if (
            row.outs is None
            or balls is None
            or strikes is None
            or not 0 <= row.outs <= 2
            or not 0 <= balls <= 3
            or not 0 <= strikes <= 2
        ):
            invalid_states += 1
            continue

        bases = (
            ("1" if row.first_base else "_")
            + ("2" if row.second_base else "_")
            + ("3" if row.third_base else "_")
        )
        pre_away, pre_home = pre_scores[row.main_event_no]
        pre_batting_score = pre_away if half[1] == "1" else pre_home
        remaining_runs = half_scores[half] - pre_batting_score
        if remaining_runs < 0:
            invalid_states += 1
            continue
        state = PitchState(
            batting_side=half[1],
            inning=half[0],
            score_diff_home=pre_home - pre_away,
            bases=bases,
            outs=row.outs,
            balls=balls,
            strikes=strikes,
        )
        observations.append(
            RunObservation(RunStateKey.from_pitch_state(state), remaining_runs, game_id)
        )
        win_observations.append(WinObservation(state, outcome_home, game_id))
    return (
        observations,
        win_observations,
        len(excluded_halves),
        duplicate_pitch_rows,
        invalid_states,
    )


def build_run_observations(rows: list[LivelogRow]) -> HistoricalRunData:
    observations: list[RunObservation] = []
    win_observations: list[WinObservation] = []
    games = excluded = duplicates = invalid = 0
    ordered = sorted(rows, key=lambda row: (row.year, row.game_sno, row.main_event_no))
    for _, game_rows_iter in groupby(ordered, key=lambda row: (row.year, row.kind_code, row.game_sno)):
        game_rows = list(game_rows_iter)
        (
            game_observations,
            game_win_observations,
            game_excluded,
            game_duplicates,
            game_invalid,
        ) = _build_game_observations(game_rows)
        observations.extend(game_observations)
        win_observations.extend(game_win_observations)
        games += 1
        excluded += game_excluded
        duplicates += game_duplicates
        invalid += game_invalid
    return HistoricalRunData(
        tuple(observations),
        tuple(win_observations),
        games,
        excluded,
        duplicates,
        invalid,
    )


def load_run_observations(
    connection: Any, from_year: int, to_year: int, kind: str = "A"
) -> HistoricalRunData:
    """從唯讀 livelog 查詢載入歷史計數狀態。"""
    cursor = connection.execute(
        HISTORICAL_LIVELOG_SQL,
        {"from_year": from_year, "to_year": to_year, "kind": kind},
    )
    rows = [LivelogRow(*row) for row in cursor]
    return build_run_observations(rows)


@dataclass(frozen=True, slots=True)
class TrackingAudit:
    total_called: int
    located_called: int
    unique_linked: int
    valid_post_count: int
    linked_missing_context: int

    @property
    def link_rate(self) -> float:
        return self.unique_linked / self.total_called if self.total_called else 0.0

    @property
    def valid_count_rate(self) -> float:
        return self.valid_post_count / self.total_called if self.total_called else 0.0

    @property
    def passes(self) -> bool:
        return (
            self.total_called > 0
            and self.link_rate >= 0.995
            and self.valid_count_rate >= 0.995
            and self.linked_missing_context == 0
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "link_rate": self.link_rate,
            "valid_count_rate": self.valid_count_rate,
            "passes": self.passes,
        }


_AUDIT_SQL = LINKED_CALLED_CTE + """
SELECT
  (SELECT count(*) FROM tracking) AS total_called,
  (SELECT count(*) FROM tracking
    WHERE plate_loc_side IS NOT NULL AND plate_loc_height IS NOT NULL) AS located_called,
  (SELECT count(*) FROM linked_called) AS unique_linked,
  (SELECT count(*) FROM tracking
    WHERE (pitch_call = 'BallCalled' AND ball_cnt BETWEEN 1 AND 4
           AND strike_cnt BETWEEN 0 AND 2)
       OR (pitch_call = 'StrikeCalled' AND ball_cnt BETWEEN 0 AND 3
           AND strike_cnt BETWEEN 1 AND 3)) AS valid_post_count,
  (SELECT count(*) FROM linked_called
    WHERE catcher_acnt IS NULL OR visiting_home_type IS NULL
       OR pre_away_score IS NULL OR pre_home_score IS NULL) AS linked_missing_context
"""


def audit_tracking(connection: Any, season: int, kind: str = "A") -> TrackingAudit:
    """執行 spec 的 99.5% fail-closed 資料 gate。"""
    row = connection.execute(_AUDIT_SQL, {"season": season, "kind": kind}).fetchone()
    if row is None:
        return TrackingAudit(0, 0, 0, 0, 0)
    return TrackingAudit(*(int(value) for value in row))
