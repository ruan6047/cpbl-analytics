"""#283 S02 測試共用：由本機 DB 唯讀抽取的真實年份 fixture 組 ``SeriesInputs``。

fixture：``tests/fixtures/postseason_real_years.json``（抽取 SQL、DB 時點與列形狀見其 ``_provenance``）。
年度規則實證只用這份真實資料；注入案例（和局、G8、雙隊達標…）只改事件、隊碼一律用真實隊碼。
"""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import date, datetime
from pathlib import Path

from cpbl import postseason_contract as pc

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "postseason_real_years.json"
REAL = json.loads(FIXTURE.read_text(encoding="utf-8"))
YEARS = REAL["years"]

LION, BRO, DRAGON, RAKUTEN, GUARDIAN, HAWK = "ADD011", "ACN011", "AAA011", "AJL011", "AKP011", "AEO011"
LAMIGO = "AJK011"


def standings(year: int) -> pc.StandingsFacts:
    y = YEARS[str(year)]
    if y["official"]:
        seg = {"0": [], "1": [], "2": []}
        for s, tc, w, l, t in y["official"]:  # noqa: E741
            seg[str(s)].append(pc.TeamRecord(tc, w, l, t))
        return pc.StandingsFacts("official", tuple(seg["0"]), tuple(seg["1"]), tuple(seg["2"]))
    seg = {"1": [], "2": []}
    for s, tc, w, l, t in y["computed"]:  # noqa: E741
        seg.setdefault(str(s), []).append(pc.TeamRecord(tc, w, l, t))
    full = pc._sum_records(seg)
    return pc.StandingsFacts("computed", tuple(full), tuple(seg["1"]), tuple(seg["2"]))


def games(year: int) -> list[pc.GameFact]:
    """fixture 只有 canonical completed，沒有官方狀態列：完賽列給 final、其餘 scheduled（注入，非抽取）。"""
    out = []
    for kind, sno, _seg, day, away, home, a, h, done in YEARS[str(year)]["games"]:
        out.append(pc.GameFact(
            year=year, kind_code=kind, game_sno=sno, game_date=date.fromisoformat(day),
            away_team_code=away, home_team_code=home, away_score=a, home_score=h, completed=done,
            official_status="final" if done else "scheduled",
        ))
    return out


def inputs(year: int, *, games_override=None, rule=None, rule_given=False, **kw) -> pc.SeriesInputs:
    return pc.SeriesInputs(
        year=year, games=games(year) if games_override is None else games_override,
        standings=standings(year), rule=rule, rule_given=rule_given,
        manifest=[{"source": "games", "scope": f"{year}/E,C", "version_or_hash": "fixture",
                   "observed_at": None, "status": "ok"}],
        **kw,
    )


def with_result(g: pc.GameFact, away: int, home: int, *, completed: bool = True) -> pc.GameFact:
    return replace(g, away_score=away, home_score=home, completed=completed,
                   official_status="final" if completed else g.official_status)


def case_b_rule(year: int) -> pc.SeasonRule:
    """T3：2017／2018 只作 C 讓勝實證的**測試內**規則（§60-2 條文；API 常數只服務 2022–2026）。

    依據：兩年 Lamigo 皆上下半季第 1，且終止點決定性（C4／C5 於 Lamigo 實勝 3＋規則勝 1 時結束；
    無讓勝則系列不會在該場結束）。§60-2 條文在 repo 內沒有施行起點，2006 反例證明舊制不同。"""
    base = pc.SEASON_RULES[2022]
    return replace(base, year=year, rule_version="test-only/§60-2 as of 聯盟規章.txt", announcement=None,
                   arrangement=())


NOW_2026 = datetime.fromisoformat("2026-10-15T01:00:00+08:00")
