"""完賽語意的回歸測試：比分是已開賽證據，不是完賽證據。"""

import sqlite3
from datetime import date, datetime

import pytest

from cpbl.api.helpers import official_status
from cpbl.completion import (
    _evidence_exists_sql,
    completed_games_sql,
    completed_games_sql_with_evidence,
    is_completed,
    is_completed_game,
    official_completion_scope_sql,
    official_final_sql,
    requires_official_completion,
)


@pytest.mark.parametrize(
    ("home_score", "away_score", "game_date", "as_of", "expected"),
    [
        (5, 4, date(2026, 7, 16), date(2026, 7, 19), True),   # 一般完賽
        (None, None, date(2026, 7, 19), date(2026, 7, 19), False),  # 當日未開打
        (0, 0, date(2026, 7, 18), date(2026, 7, 19), False),  # 延賽
        # 2026 二軍真實保留賽匿名化 snapshot：帶中止比分、續賽日仍在未來。
        (5, 4, date(2026, 8, 8), date(2026, 7, 19), False),
        # 同一保留賽於續完日寫回最終比分後，應重新納入 completed。
        (7, 4, date(2026, 8, 8), date(2026, 8, 8), True),
        (3, 2, date(2026, 7, 19), date(2026, 7, 19), True),  # 日期邊界
    ],
)
def test_completion_requires_score_and_date_not_after_as_of(
    home_score: int | None,
    away_score: int | None,
    game_date: date,
    as_of: date,
    expected: bool,
) -> None:
    assert is_completed(home_score, away_score, game_date, as_of) is expected


def test_completion_sql_uses_the_same_score_and_as_of_contract() -> None:
    assert completed_games_sql("CURRENT_DATE") == (
        "home_score + away_score > 0 AND game_date <= CURRENT_DATE"
    )


# --- #237：2026 起的季後 E／C 只認官方 final／完賽證據 -------------------------------
#
# 狀態矩陣的 E1 列抄自官方 2026-10-09 17:52 台北的實際擷取（official-fetch-current，
# raw-response-0.json sha256 32a4e25a…）：GameSno=1、PresentStatus=1、GameResult=''、
# IsPlayBall='Y'、VisitingScore=0、HomeScore=3、GameDate=2026-10-09。其餘列是**合成**的
# 狀態組合（final／missing／delayed／reserved／conditional），不是官方觀測。

AS_OF = date(2026, 10, 9)
_T1 = datetime(2026, 10, 9, 9, 52, 54)
_T2 = datetime(2026, 10, 9, 13, 0, 0)

# (名稱, year, kind, sno, game_date, home, away, 官方排程列[(present, result, seen)], 證據, 預期)
_MATRIX = [
    # —— 受官方判準管轄：2026 E／C ——
    ("E1-live-real-17:52", 2026, "E", 1, AS_OF, 3, 0, [(1, "", _T1)], False, False),
    ("E2-scheduled", 2026, "E", 2, date(2026, 10, 10), 0, 0, [(1, "", _T1)], False, False),
    ("E-final-after-live", 2026, "E", 11, AS_OF, 5, 2, [(1, "", _T1), (1, "0", _T2)], False, True),
    ("E-final-scoreless", 2026, "E", 12, AS_OF, 0, 0, [(1, "0", _T2)], False, True),
    ("E-missing-official", 2026, "E", 13, AS_OF, 3, 0, [], False, False),
    ("E-unknown-raw", 2026, "E", 14, AS_OF, 3, 0, [(0, "", _T1)], False, False),
    ("E-delayed", 2026, "E", 15, AS_OF, 0, 0, [(1, "1", _T1)], False, False),
    ("E-reserved-with-score", 2026, "E", 16, AS_OF, 2, 1, [(1, "2", _T1)], False, False),
    ("E-conditional-not-needed", 2026, "E", 4, date(2026, 10, 8), 0, 0, [(1, "", _T1)], False, False),
    ("E-evidence-without-final", 2026, "E", 17, AS_OF, 3, 0, [], True, True),
    ("E-final-but-future-date", 2026, "E", 18, date(2026, 10, 12), 4, 1, [(1, "0", _T2)], False, False),
    ("C-live", 2026, "C", 1, AS_OF, 2, 1, [(1, "", _T1)], False, False),
    ("C-final", 2026, "C", 2, AS_OF, 2, 1, [(1, "0", _T2)], False, True),
    # —— 不受管轄：舊判準一字不動 ——
    ("A-same-as-E1", 2026, "A", 1, AS_OF, 3, 0, [(1, "", _T1)], False, True),
    ("A-missing-official", 2026, "A", 2, AS_OF, 3, 0, [], False, True),
    ("A-reserved-future", 2026, "A", 3, date(2026, 10, 20), 5, 4, [(1, "2", _T1)], False, False),
    ("A-final-scoreless", 2026, "A", 4, AS_OF, 0, 0, [(1, "0", _T2)], False, True),
    ("A-scoreless-nothing", 2026, "A", 5, AS_OF, 0, 0, [(1, "", _T1)], False, False),
    ("D-same-as-E1", 2026, "D", 1, AS_OF, 3, 0, [(1, "", _T1)], False, True),
    ("E2025-historical", 2025, "E", 1, date(2025, 10, 11), 3, 0, [], False, True),
    ("C2025-historical", 2025, "C", 2, date(2025, 10, 20), 4, 2, [(1, "", _T1)], False, True),
]
_IDS = [m[0] for m in _MATRIX]


def _schedule_rows(m) -> list[dict]:
    _, year, kind, sno, game_date, *_rest = m
    return [{"year": year, "kind_code": kind, "game_sno": sno,
             "raw_present_status": p, "raw_game_result": r, "raw_game_date": game_date,
             "last_seen_at": seen, "fetched_at": seen,
             "payload_hash": f"{kind}{sno}-{p}-{r}-{seen.isoformat()}"} for p, r, seen in m[7]]


def _python_verdict(m) -> bool:
    _, year, kind, _sno, game_date, home, away, _rows, evidence, _ = m
    official_final = official_status(_schedule_rows(m))[0] == "final"
    return is_completed_game(home, away, game_date, AS_OF, evidence, official_final,
                             official_required=requires_official_completion(kind, year))


def _sqlite_verdicts(cond_alias: str = "g") -> dict[str, bool]:
    """把 SQL 片段放進記憶體 sqlite 求值（純本機、不連任何 PostgreSQL）。

    ⚠️ 這是 PostgreSQL 語意的**近似**：驗的是 CASE／EXISTS／選列 ORDER BY 的邏輯形狀，
    真實 PG 的全庫對帳仍是 `test_daily_summary.py::test_completed_matches_the_canonical_predicate_for_every_game`。
    """
    db = sqlite3.connect(":memory:")
    db.execute("ATTACH ':memory:' AS cpbl")
    db.executescript(
        "CREATE TABLE cpbl.games(year INT, kind_code TEXT, game_sno INT, game_date TEXT,"
        " home_score INT, away_score INT);"
        "CREATE TABLE cpbl.game_completion_evidence(year INT, kind_code TEXT, game_sno INT);"
        "CREATE TABLE cpbl.game_schedule_status_revisions(year INT, kind_code TEXT, game_sno INT,"
        " raw_present_status INT, raw_game_result TEXT, raw_game_date TEXT, last_seen_at TEXT,"
        " fetched_at TEXT, payload_hash TEXT);")
    names = {}
    for m in _MATRIX:
        name, year, kind, sno, game_date, home, away, _rows, evidence, _ = m
        names[(year, kind, sno)] = name
        db.execute("INSERT INTO cpbl.games VALUES (?,?,?,?,?,?)",
                   (year, kind, sno, game_date.isoformat(), home, away))
        if evidence:
            db.execute("INSERT INTO cpbl.game_completion_evidence VALUES (?,?,?)", (year, kind, sno))
        for r in _schedule_rows(m):
            db.execute("INSERT INTO cpbl.game_schedule_status_revisions VALUES (?,?,?,?,?,?,?,?,?)",
                       (year, kind, sno, r["raw_present_status"], r["raw_game_result"],
                        r["raw_game_date"].isoformat(), r["last_seen_at"].isoformat(),
                        r["fetched_at"].isoformat(), r["payload_hash"]))
    cond = completed_games_sql_with_evidence(cond_alias, f"'{AS_OF.isoformat()}'")
    rows = db.execute(f"SELECT {cond_alias}.year, {cond_alias}.kind_code, {cond_alias}.game_sno, "
                      f"COALESCE({cond}, 0) FROM cpbl.games {cond_alias}").fetchall()
    return {names[(y, k, s)]: bool(v) for y, k, s, v in rows}


@pytest.mark.parametrize("m", _MATRIX, ids=_IDS)
def test_official_completion_matrix_python(m) -> None:
    assert _python_verdict(m) is m[-1]


def test_official_completion_matrix_sql_matches_python() -> None:
    sql = _sqlite_verdicts()
    assert {m[0]: _python_verdict(m) for m in _MATRIX} == sql
    assert sql == {m[0]: m[-1] for m in _MATRIX}


def test_real_e1_partial_score_is_not_completed_but_was_under_the_old_rule() -> None:
    """反例本身：舊判準把 17:52 的 E1 判成完賽，新判準不判。"""
    e1 = next(m for m in _MATRIX if m[0] == "E1-live-real-17:52")
    assert is_completed_game(3, 0, AS_OF, AS_OF) is True            # 舊（未傳 official_required）
    assert _python_verdict(e1) is False
    assert _sqlite_verdicts()["E1-live-real-17:52"] is False


@pytest.mark.parametrize("m", [m for m in _MATRIX if not requires_official_completion(m[2], m[1])],
                         ids=[m[0] for m in _MATRIX if not requires_official_completion(m[2], m[1])])
def test_unguarded_kinds_keep_the_prior_predicate_exactly(m) -> None:
    _, year, kind, _sno, game_date, home, away, _rows, evidence, _ = m
    official_final = official_status(_schedule_rows(m))[0] == "final"
    assert _python_verdict(m) is is_completed_game(home, away, game_date, AS_OF, evidence,
                                                   official_final)


@pytest.mark.parametrize(
    ("kind", "year", "expected"),
    [("E", 2026, True), ("C", 2026, True), ("E", 2027, True), ("E", 2025, False),
     ("C", 2025, False), ("A", 2026, False), ("D", 2026, False), ("F", 2026, False),
     ("E", None, False), (None, 2026, False)],
)
def test_requires_official_completion_scope(kind, year, expected) -> None:
    assert requires_official_completion(kind, year) is expected


def test_sql_else_branch_is_the_prior_expression_verbatim() -> None:
    """ELSE 支必須逐字等於改動前的式子——A／D／歷史年份的 SQL 判準一字不動。"""
    prior = (
        "(g.game_date <= X AND ("
        f"g.home_score + g.away_score > 0 OR {_evidence_exists_sql('g')} OR ("
        f"g.home_score + g.away_score = 0 AND {official_final_sql('g')})))"
    )
    cond = completed_games_sql_with_evidence("g", "X")
    assert cond.startswith(f"(CASE WHEN {official_completion_scope_sql('g')} THEN ")
    assert cond.endswith(f" ELSE {prior} END)")
    assert official_completion_scope_sql("g") == "(g.kind_code IN ('E', 'C') AND g.year >= 2026)"
