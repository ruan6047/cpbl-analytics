"""#283 S02 測試共用：由本機 DB 唯讀抽取的真實年份 fixture 組 ``SeriesInputs``。

fixture：``tests/fixtures/postseason_real_years.json``（抽取 SQL、DB 時點與列形狀見其 ``_provenance``）。
年度規則實證只用這份真實資料；注入案例（和局、G8、雙隊達標…）只改事件、隊碼一律用真實隊碼。
"""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, date, datetime
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


# —— 讀取層腳本化 cursor（reader 測試與跨語言 golden 共用；不連 DB） ——

READER_NOW = datetime(2026, 10, 14, 17, 0, tzinfo=UTC)   # 台北 10/15 01:00


class ScriptedCursor:
    """依 SQL 常數回列；``fail`` 內的 SQL 一律丟例外（模擬缺表／權限）。"""

    def __init__(self, table: dict, fail=()):
        self.table, self.fail, self.calls = table, set(fail), []
        self._rows, self.description = [], None

    def execute(self, sql, params=None):
        self.calls.append(sql)
        if sql in self.fail:
            raise RuntimeError("relation does not exist")
        cols, rows = self.table.get(sql, ([], []))
        self.description = [(c,) for c in cols]
        self._rows = list(rows)

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._rows[0] if self._rows else None


READER_GAME_COLS = ["year", "kind_code", "game_sno", "game_date", "venue", "mvp_id", "away_team_code",
              "home_team_code", "away_score", "home_score", "completed"]
# 2026 真實 E1–E4、C1（本機 DB 唯讀，見 tests/fixtures/postseason_real_years.json）
READER_GAMES = [
    (2026, "E", 1, date(2026, 10, 9), "洲際", None, "ADD011", "ACN011", 1, 4, True),
    (2026, "E", 2, date(2026, 10, 10), "亞太主", None, "ACN011", "ADD011", 0, 1, True),
    (2026, "E", 3, date(2026, 10, 11), "洲際", None, "ADD011", "ACN011", 4, 2, True),
    (2026, "E", 4, date(2026, 10, 12), "洲際", None, "ADD011", "ACN011", 2, 8, True),
    (2026, "C", 1, date(2026, 10, 17), "大巨蛋", None, "ACN011", "AAA011", 0, 0, False),
]
_OFFICIAL = [(0, "AAA011", 67, 53, 0), (0, "ADD011", 64, 55, 1), (0, "AEO011", 59, 61, 0),
             (0, "ACN011", 56, 62, 2), (1, "AAA011", 39, 21, 0), (1, "ACN011", 20, 38, 2),
             (1, "ADD011", 30, 29, 1), (2, "ACN011", 36, 24, 0), (2, "ADD011", 34, 26, 0),
             (2, "AAA011", 28, 32, 0)]


def reader_table():
    return {
        pc.GAMES_V2_SQL: (READER_GAME_COLS, READER_GAMES),
        pc.OFFICIAL_STANDINGS_SQL: (["season_code", "team_code", "w", "l", "t"], _OFFICIAL),
        pc.REFRESH_SQL: (["refreshed_at", "ok", "scope"], [(READER_NOW, True, "daily")]),
        pc.RECAP_BUILDS_SQL: (["year", "kind_code", "game_sno", "state", "built_at"],
                              [(2026, "E", n, "published", READER_NOW) for n in (1, 2, 3, 4)]),
    }
