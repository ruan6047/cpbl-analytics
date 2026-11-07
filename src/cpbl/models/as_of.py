"""截至某場的本季戰績與打擊率（#394；#396 共用同一組函式）。

從逐場資料按 ``(game_date, game_sno)`` 截止即時聚合，用目前修訂資料重算，**不等於**重現
當時已知的版本。⛔ 不可只比 ``game_sno``：補賽的低場號日期在後（2026/A/180 只比場號會算成
34-26／24-34，正確是 30-24／20-31）。

``matchup.team_stats`` 是另一件事：全季累計，它的 ``last10`` 只計有勝負的場次，戰績榜在用，
故刻意不共用。這裡的近 10 場是官方定義（需求方 6700041668）：最近 10 場完成場、含和局，
與 ``team_standings.last10`` 收斂。
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import date
from typing import Any

from cpbl.completion import completed_games_sql_with_evidence

_DONE = completed_games_sql_with_evidence("g")
_FORM_WINDOW = 10


def _cutoff_sql(include_game: bool) -> str:
    return f"(g.game_date, g.game_sno) {'<=' if include_game else '<'} (%s, %s)"


def _rate3(hits: int, at_bats: int) -> float:
    """四捨五入到三位，與官方一致。⛔ 不用 ``round()``：它對半進位取偶，5/16 會成 .312 而官方是 .313。"""
    return (2000 * hits + at_bats) // (2 * at_bats) / 1000


def form_label(results: Sequence[str]) -> str:
    """``W``／``T``／``L`` 序列（舊到新）的最近 10 場：無和局 ``W-L``，有和局 ``W-T-L``。"""
    window = list(results[-_FORM_WINDOW:])
    w, t, loss = window.count("W"), window.count("T"), window.count("L")
    return f"{w}-{t}-{loss}" if t else f"{w}-{loss}"


def accumulate_records(rows: Iterable[Sequence[Any]],
                       team_codes: Iterable[str]) -> dict[str, dict]:
    """``rows`` 依時間序的 (主隊, 客隊, 主分, 客分) → ``{team_code: {w, l, form}}``。"""
    results: dict[str, list[str]] = {}
    wanted = set(team_codes)
    for home, away, home_score, away_score in rows:
        for code, mine, other in ((home, home_score, away_score), (away, away_score, home_score)):
            if code in wanted:
                outcome = "W" if mine > other else "L" if mine < other else "T"
                results.setdefault(code, []).append(outcome)
    return {code: {"w": seq.count("W"), "l": seq.count("L"), "form": form_label(seq)}
            for code, seq in results.items()}


def team_records_as_of(cur, season: int, kind_code: str, game_date: date, game_sno: int,
                       team_codes: Iterable[str], *, include_game: bool = True,
                       extra_result: Mapping[str, Any] | None = None) -> dict[str, dict]:
    """回 ``{team_code: {"w": int, "l": int, "form": str}}``；該隊沒有完成場時不放。

    ``extra_result``（``home_team_code``／``away_team_code``／``home_score``／``away_score``）
    是尚未入庫的本場，排在最後一場；只能搭配 ``include_game=False``，否則本場會算兩次。
    """
    cur.execute(
        f"""
        SELECT g.home_team_code, g.away_team_code, g.home_score, g.away_score
        FROM cpbl.games g
        WHERE g.year = %s AND g.kind_code = %s AND {_cutoff_sql(include_game)} AND {_DONE}
        ORDER BY g.game_date, g.game_sno
        """,
        (season, kind_code, game_date, game_sno),
    )
    rows = list(cur.fetchall())
    if extra_result:
        rows.append((extra_result["home_team_code"], extra_result["away_team_code"],
                     extra_result["home_score"], extra_result["away_score"]))
    return accumulate_records(rows, team_codes)


def batter_avg_as_of(cur, season: int, kind_code: str, game_date: date, game_sno: int,
                     hitter_ids: Iterable[str], *, include_game: bool = True,
                     extra_lines: Iterable[Mapping[str, Any]] | None = None) -> dict[str, float]:
    """回 ``{hitter_acnt: avg}``（三位小數）；累計 AB=0 不放，前端顯示「—」。

    ``extra_lines``（``hitter_acnt``／``at_bats``／``hits``）是尚未入庫的本場，只能搭配
    ``include_game=False``，否則本場會算兩次。
    """
    ids = list(hitter_ids)
    if not ids:
        return {}
    cur.execute(
        f"""
        SELECT b.hitter_acnt, sum(b.at_bats), sum(b.hits)
        FROM cpbl.batting_gamelog b
        JOIN cpbl.games g
          ON g.year = b.year AND g.kind_code = b.kind_code AND g.game_sno = b.game_sno
        WHERE b.year = %s AND b.kind_code = %s AND b.hitter_acnt = ANY(%s)
          AND {_cutoff_sql(include_game)} AND {_DONE}
        GROUP BY b.hitter_acnt
        """,
        (season, kind_code, ids, game_date, game_sno),
    )
    totals = {hitter: [int(ab or 0), int(hits or 0)] for hitter, ab, hits in cur.fetchall()}
    for line in extra_lines or ():
        if line["hitter_acnt"] in ids:
            total = totals.setdefault(line["hitter_acnt"], [0, 0])
            total[0] += line["at_bats"]
            total[1] += line["hits"]
    return {hitter: _rate3(hits, ab) for hitter, (ab, hits) in totals.items() if ab > 0}
