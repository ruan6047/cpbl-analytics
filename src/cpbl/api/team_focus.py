"""球隊頁「近日焦點」共用小工具：現行連續安打（唯讀）。

原本本檔也是「近期球員熱區」（打者 OPS 版）的來源（UX-TEAM-FOCUS2），
該熱區已被 UX-TEAM-HOTZONE1 的過程型口徑取代並移到 `cpbl.api.team_hotzone`
（理由見該模組 docstring：12 個打席的 OPS 幾乎是純噪音）。本檔只留下
`_current_hit_streak`——這支函式與熱區指標選擇無關（現行連續安打是結果型
但本身就是「目前進行中」的狀態展示，不是排序榜），且已被 UX-TEAM-RECORDS1
的「即將挑戰的紀錄」重用（`cpbl.api.team_records`），故保留獨立模組避免
循環 import（team_records 不應反過來 import team_hotzone）。
"""

from __future__ import annotations

from cpbl.completion import completed_games_sql_with_evidence

# 完成場判準（證據感知）：0:0 真和局需外部完賽證據（DATA-TIE-REMEDY1）。別名 `g`＝
# 下方 JOIN 給 cpbl.games 的別名；限定詞是正確性要求（未限定會使 EXISTS 恆真）。
# 日界吃 helper 的台北預設。原本明示傳 UTC 只是「沿用當時的預設、等需求方裁決」，
# 裁決已於 2026-08-21 下達（業務日期一律台北，DATA-TZ-BOUNDARY-SUCCESSION1）。
_DONE_G = completed_games_sql_with_evidence("g")

_TEAM_CODE_EXPR = "CASE bg.visiting_home_type WHEN '2' THEN g.home_team_code ELSE g.away_team_code END"


def _current_hit_streak(cur, code: str, season: int, hitter_acnt: str) -> int:
    """由最近一場完賽（本季、該隊）往前數的現行連續安打場次。"""
    cur.execute(
        "SELECT bg.at_bats, bg.hits FROM cpbl.batting_gamelog bg "
        "JOIN cpbl.games g ON g.year=bg.year AND g.kind_code=bg.kind_code AND g.game_sno=bg.game_sno "
        "WHERE bg.year=%s AND bg.kind_code='A' AND bg.hitter_acnt=%s "
        f"AND {_DONE_G} AND {_TEAM_CODE_EXPR}=%s "
        "ORDER BY g.game_date DESC, g.game_sno DESC",
        (season, hitter_acnt, code),
    )
    streak = 0
    for ab, h in cur.fetchall():
        ab = int(ab or 0)
        h = int(h or 0)
        if h > 0:
            streak += 1
        elif ab > 0:
            break
        # ab==0 且 h==0（如保送/觸身球無打數）：不計入也不中止，跳過該場
    return streak
