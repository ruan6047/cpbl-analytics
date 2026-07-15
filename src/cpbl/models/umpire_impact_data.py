"""ML-UMP1 的資料契約、唯讀 audit 與資料載入。

所有研究 SQL 都限制在 `cpbl` schema，且不寫入資料庫。TrackMan 與 livelog
只能在完整狀態鍵恰好命中一列時使用；零筆或多筆一律隔離。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

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
