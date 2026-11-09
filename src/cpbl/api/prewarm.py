"""回應快取的啟動預熱清單（#442 PLAN v4 G2）。

預熱的鍵會被**釘選**：背景刷新者在到期前主動重算，所以穩態下爆量（6 隊球隊頁同時 SSR）遇到的是暖快取。
選鍵原則：本季的 season 級鍵，以及現役各隊的逐隊鍵；每支端點同時預熱「參數全用預設值」與
「前端實際帶的參數」兩種（web/src/app/teams/[code]/page.tsx、web/src/lib/api.ts），兩者的快取鍵不同。

⛔ 只放 :func:`cpbl.api.response_cache.cached` 已裝的端點；即時端點不在這裡（排除理由見該模組）。
清單在背景執行緒依序執行，任何一項失敗只記 log（fail-open）。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from cpbl.api.helpers import DEFAULT_SEASON
from cpbl.db import conn


def _active_teams() -> list[str]:
    with conn() as c:
        return [r[0] for r in c.execute(
            "SELECT team_code FROM cpbl.team_dim WHERE active = true ORDER BY team_code").fetchall()]


def jobs() -> list[tuple[str, Callable[[], Any]]]:
    from cpbl.api.routers import leaders, standings, teams

    y = DEFAULT_SEASON
    out: list[tuple[str, Callable[[], Any]]] = []

    def add(name: str, fn, **kw) -> None:
        out.append((name, lambda fn=fn, kw=kw: fn.warm(**kw)))

    # season 級（預設參數＝不帶 query；前端參數＝球隊頁／首頁實際帶的）
    add("special-records", teams.special_records_endpoint)
    add("special-records?season", teams.special_records_endpoint, season=y, kind_code="A")
    add("team-split", standings.season_team_split, season=y)
    add("season/standings", standings.season_standings, season=y)
    add("seasons", standings.seasons, kind_code="A")
    add("standings", standings.official_standings)
    add("standings?season_code=0", standings.official_standings, season=y, season_code=0, kind_code="A")
    add("standings-trend", standings.standings_trend)
    add("batting-leaders", leaders.batting_leaders)
    add("batting-leaders?ops500", leaders.batting_leaders, season=y, sort="ops", min_pa=0, limit=500,
        kind_code="A")
    add("pitching-leaders", leaders.pitching_leaders)
    add("pitching-leaders?ip500", leaders.pitching_leaders, season=y, sort="ip", min_ip=0, limit=500,
        kind_code="A")
    add("fielding", leaders.fielding)
    add("fielding?g1000", leaders.fielding, season=y, pos=None, sort="g", limit=1000, kind_code="A")
    add("records", leaders.records)
    add("records/team", leaders.team_records)
    add("records/championships", leaders.championships)
    add("records/postseason", leaders.postseason_records)
    add("franchises", teams.franchises)
    try:
        codes = _active_teams()
    except Exception:  # noqa: BLE001 — 拿不到現役隊伍就只預熱 season 級
        codes = []
    for code in codes:
        add(f"style {code}", teams.team_style, code=code)
        add(f"upcoming-records {code}", teams.team_upcoming_records, code=code, season=y)
        add(f"hot-zone {code}", teams.team_hot_zone, code=code, season=y)
        add(f"players {code}", teams.team_players, code=code)
        add(f"eras {code}", teams.team_eras, code=code, kind_code="A")
        add(f"der {code}", teams.team_der_endpoint, code=code)
    return out
