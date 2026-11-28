"""年度總冠軍：補上新球季冠軍列（#469）＋離線重建 cpbl.championship_members。

冠軍隊由 cpbl.championships canonical dataset 決定；該表逐年保留 CPBL 官方來源，
包含未進行總冠軍賽的 1992／1994／1995。對每個冠軍 (year, team_code)：
  - 球員：該年一軍有成績者。pre-2018 用 season 表(team_id=隊碼前三碼)；
    2018+（含 season 表缺漏的 2025）改用 gamelog，以 visiting_home_type 判隊
    （'2'=主、'1'=客）。投打 season/gamelog 全 UNION 去重。
  - 總教練：managers 表（姓名→players.id，任期涵蓋冠軍年）。

冪等：每次 TRUNCATE 後重建。總冠軍總教練僅限 managers 姓名能對到 players.id 者。

**新球季自動補列（#469）**：``ensure_season_champion`` 只讀 #391 收官判定（``season_close``，⛔ 不改判定），
一軍 ``status == "decided"`` 且 ``championships`` 缺該年 ⇒ 由官方賽果補一列（冠軍＝收官判定、亞軍＝決勝場另一隊、
來源＝官方封王戰 box，與 1990–2025 同型態），直接 ``verified``（需求方裁定 R1）。奪冠總教練取官網球隊頁現任
一軍總教練（``cpbl.coaches``），該隊該年恰 1 位才寫、否則標缺（裁定 R2）。寫入一律
``ON CONFLICT (year) DO NOTHING``：⛔ 不覆蓋、不刪任何既有列。看 ``status`` 不看 ``closed``：#392 切回與
``CPBL_SEASON_CLOSE=open`` 只恢復爬蟲，冠軍事實不變。殺開關 ``CPBL_CHAMPION_AUTOFILL=off``＝不讀不寫。
寫入者：VPS 每日入口（``scripts/jobs.py`` 的 skip 日）、``build_championships``（每日鏈與 CLI）。
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable, Iterable, Mapping
from datetime import UTC, datetime

from cpbl.db import conn
from cpbl.franchises import franchise_of

log = logging.getLogger("cpbl.champ")

CANONICAL_FROM_YEAR = 1990
#: migration 052 播種的最後一年；動態上界（``coverage_through_year``）的下限。
CANONICAL_THROUGH_YEAR = 2025

AUTOFILL_ENV = "CPBL_CHAMPION_AUTOFILL"
AUTOFILL_OFF = "off"
HEAD_COACH_POS = "一軍總教練"
BOX_URL = "https://www.cpbl.com.tw/box?year={year}&KindCode={kind}&gameSno={sno}"
TEAM_PAGE_URL = "https://www.cpbl.com.tw/team/index?teamNo={code}"
MANAGER_NOTE = "自動補上（#469）：官網球隊頁現任一軍總教練（cpbl.coaches 快照）"


def coverage_through_year(closure) -> int:
    """coverage 上界＝最新 decided 的一軍球季；該季未 decided ⇒ 前一年。⛔ 不低於 052 的 2025。

    ``closure``＝``season_close.LeagueClosure``（一軍）；``None``／判不出球季 ⇒ 既有上界。"""
    season = getattr(closure, "season", None)
    if season is None:
        return CANONICAL_THROUGH_YEAR
    through = season if getattr(closure, "status", None) == "decided" else season - 1
    return max(CANONICAL_THROUGH_YEAR, through)


def championship_coverage(
    years: Iterable[int], *, as_of: datetime | None,
    through_year: int = CANONICAL_THROUGH_YEAR,
    manager_years: Iterable[int] | None = None,
) -> dict[str, object]:
    """回傳 canonical 歷史範圍的完整性；範圍外年份不影響判定。

    ``manager_years``（選填）＝有已驗證奪冠總教練的年份；給了就多回 ``managers_missing_years``
    （範圍內有冠軍列卻缺總教練的年份；只揭露、不影響 ``complete``）。"""
    expected = set(range(CANONICAL_FROM_YEAR, through_year + 1))
    years = set(years)
    present = expected.intersection(years)
    missing = sorted(expected - present)
    out: dict[str, object] = {
        "from_year": CANONICAL_FROM_YEAR,
        "through_year": through_year,
        "complete": not missing,
        "missing_years": missing,
        "as_of": as_of,
    }
    if manager_years is not None:
        out["managers_missing_years"] = sorted(present - set(manager_years))
    return out


def autofill_disabled(env: Mapping[str, str] | None = None) -> bool:
    return (os.environ if env is None else env).get(AUTOFILL_ENV, "").strip().lower() == AUTOFILL_OFF


def read_major_closure():
    """一軍收官判定（#391 唯一判定來源；唯讀交易）。"""
    from cpbl import season_close

    return season_close.league_closure(leagues=(season_close.MAJOR,))[season_close.MAJOR]


_EXISTING_SQL = "SELECT champion_team_code, franchise_code FROM cpbl.championships WHERE year = %s"
_DECISIVE_SQL = ("SELECT home_team_code, away_team_code FROM cpbl.games "
                 "WHERE year = %s AND kind_code = %s AND game_sno = %s")
_INSERT_CHAMP_SQL = """
INSERT INTO cpbl.championships (
    year, champion_team_code, runner_up_team_code, franchise_code,
    source_url, verification_status, verified_at
) VALUES (%(year)s, %(champion)s, %(runner_up)s, %(franchise)s, %(source_url)s, 'verified', %(verified_at)s)
ON CONFLICT (year) DO NOTHING
"""
_MANAGER_PRESENT_SQL = "SELECT 1 FROM cpbl.championship_managers WHERE year = %s"
_HEAD_COACH_SQL = ("SELECT DISTINCT name FROM cpbl.coaches "
                   "WHERE year = %s AND team_code = %s AND pos = %s ORDER BY name")
_INSERT_MANAGER_SQL = """
INSERT INTO cpbl.championship_managers (
    year, manager_name, franchise_code, source_url, verification_status, verified_at, note
) VALUES (%(year)s, %(manager_name)s, %(franchise)s, %(source_url)s, 'verified', %(verified_at)s, %(note)s)
ON CONFLICT (year) DO NOTHING
"""


def _ensure_manager(cur, year: int, team_code: str, franchise: str, now: datetime) -> str:
    cur.execute(_MANAGER_PRESENT_SQL, (year,))
    if cur.fetchone():
        return "present"
    cur.execute(_HEAD_COACH_SQL, (year, team_code, HEAD_COACH_POS))
    names = [row[0] for row in cur.fetchall()]
    if len(names) != 1:
        return "missing" if not names else "ambiguous"
    cur.execute(_INSERT_MANAGER_SQL, {
        "year": year, "manager_name": names[0], "franchise": franchise,
        "source_url": TEAM_PAGE_URL.format(code=team_code), "verified_at": now, "note": MANAGER_NOTE,
    })
    return "inserted" if cur.rowcount else "present"


def ensure_season_champion(cur, closure, *, now: datetime | None = None,
                           env: Mapping[str, str] | None = None) -> dict:
    """收官判定 decided 且冠軍表缺該年 ⇒ 補一列（只新增）。回傳動作摘要；⛔ 不 commit（交呼叫端交易）。

    ``action``：``disabled``／``not_decided``／``no_decisive_game``／``present``／``present_conflict``／``inserted``；
    ``manager``：``inserted``／``present``／``missing``／``ambiguous``／``None``（未處理）。"""
    if autofill_disabled(env):
        return {"action": "disabled", "year": None, "manager": None}
    from cpbl.season_close import MAJOR

    season = getattr(closure, "season", None)
    decided_by = getattr(closure, "decided_by", None)
    champion = getattr(closure, "champion_team_code", None)
    if (getattr(closure, "league", None) != MAJOR or getattr(closure, "status", None) != "decided"
            or season is None or not champion or not decided_by
            or decided_by[0] != season or decided_by[1] != "C"):
        return {"action": "not_decided", "year": season, "manager": None,
                "status": getattr(closure, "status", None)}
    now = now or datetime.now(UTC)
    year = int(season)
    cur.execute(_EXISTING_SQL, (year,))
    existing = cur.fetchone()
    if existing:
        if existing[0] != champion:
            log.warning("championships %s 既有冠軍 %s ≠ 收官判定 %s：不覆蓋", year, existing[0], champion)
            return {"action": "present_conflict", "year": year, "manager": None}
        manager = _ensure_manager(cur, year, champion, existing[1], now)
        return {"action": "present", "year": year, "manager": manager}
    cur.execute(_DECISIVE_SQL, decided_by)
    row = cur.fetchone()
    if not row or champion not in row or row[0] == row[1]:
        log.warning("決勝場 %s 找不到或與冠軍 %s 不符（%s）：不補列", decided_by, champion, row)
        return {"action": "no_decisive_game", "year": year, "manager": None}
    runner_up = row[1] if row[0] == champion else row[0]
    franchise = franchise_of(champion)
    cur.execute(_INSERT_CHAMP_SQL, {
        "year": year, "champion": champion, "runner_up": runner_up, "franchise": franchise,
        "source_url": BOX_URL.format(year=year, kind=decided_by[1], sno=decided_by[2]), "verified_at": now,
    })
    if not cur.rowcount:  # 並行寫入者先補了：視同已存在，⛔ 不覆蓋
        return {"action": "present", "year": year, "manager": None}
    manager = _ensure_manager(cur, year, champion, franchise, now)
    log.info("championships 補上 %s：冠軍 %s、亞軍 %s、總教練 %s", year, champion, runner_up, manager)
    return {"action": "inserted", "year": year, "manager": manager,
            "champion_team_code": champion, "runner_up_team_code": runner_up}


def autofill_champion(*, now: datetime | None = None, env: Mapping[str, str] | None = None,
                      read_closure: Callable | None = None) -> dict:
    """獨立入口（VPS 休季 skip 日用）：讀收官判定 → 單一交易補列。錯誤上浮（呼叫端記失敗，⛔ 不吞）。"""
    if autofill_disabled(env):
        return {"action": "disabled", "year": None, "manager": None}
    closure = (read_closure or read_major_closure)()
    with conn() as c:
        return ensure_season_champion(c.cursor(), closure, now=now, env=env)


# 各年已驗證冠軍。team_code 形如 AAA011，前三碼對 season 表 team_id；
# franchise_code 對 managers 與未來球團累積排行。
_CHAMP_SQL = """
SELECT year, champion_team_code, franchise_code, verified_at
FROM cpbl.championships
WHERE verification_status = 'verified'
ORDER BY year
"""

# 冠軍隊該年一軍球員：season 表(team_id) + gamelog(vht 判隊)，投打全 UNION。
_PLAYERS_SQL = """
INSERT INTO cpbl.championship_members (player_id, year, team_code, role)
SELECT DISTINCT pid, %(year)s, %(code)s, 'player' FROM (
    SELECT player_id AS pid FROM cpbl.batting_seasons  WHERE year = %(year)s AND team_id = %(tid)s
    UNION SELECT player_id FROM cpbl.pitching_seasons   WHERE year = %(year)s AND team_id = %(tid)s
    UNION
    SELECT bg.hitter_acnt FROM cpbl.batting_gamelog bg
      JOIN cpbl.games g ON g.year = bg.year AND g.kind_code = bg.kind_code AND g.game_sno = bg.game_sno
     WHERE bg.year = %(year)s AND bg.kind_code = 'A'
       AND ((bg.visiting_home_type = '2' AND g.home_team_code = %(code)s)
         OR (bg.visiting_home_type = '1' AND g.away_team_code = %(code)s))
    UNION
    SELECT pg.pitcher_acnt FROM cpbl.pitching_gamelog pg
      JOIN cpbl.games g ON g.year = pg.year AND g.kind_code = pg.kind_code AND g.game_sno = pg.game_sno
     WHERE pg.year = %(year)s AND pg.kind_code = 'A'
       AND ((pg.visiting_home_type = '2' AND g.home_team_code = %(code)s)
         OR (pg.visiting_home_type = '1' AND g.away_team_code = %(code)s))
) s
WHERE pid IS NOT NULL
ON CONFLICT (player_id, year) DO NOTHING
"""

# 總教練：managers 姓名對 players.id，任期涵蓋冠軍年（球員已先插入，衝突則保留 player）。
_MANAGER_SQL = """
INSERT INTO cpbl.championship_members (player_id, year, team_code, role)
SELECT DISTINCT p.id, %(year)s, %(code)s, 'manager'
FROM cpbl.managers m JOIN cpbl.players p ON p.name = m.name
WHERE m.team_code = %(fcode)s AND %(year)s BETWEEN m.from_year AND m.to_year
ON CONFLICT (player_id, year) DO NOTHING
"""


def build_championships(*, now: datetime | None = None, env: Mapping[str, str] | None = None,
                        read_closure: Callable | None = None) -> dict:
    """先補新球季冠軍列（#469），再 TRUNCATE 重建成員。

    補列失敗（收官判定讀不到等）⛔ 不連坐成員重建與每日鏈其餘步驟：記進回傳的 ``autofill``
    （``action="error"``），CLI 據此非零退出。"""
    if autofill_disabled(env):
        closure, autofill = None, {"action": "disabled", "year": None, "manager": None}
    else:
        try:
            closure, autofill = (read_closure or read_major_closure)(), None
        except Exception as exc:  # noqa: BLE001 — 判不出就不補，失敗如實回報
            log.exception("讀取收官判定失敗：本次不補冠軍列")
            closure, autofill = None, {"action": "error", "error": type(exc).__name__, "manager": None}
    with conn() as c:
        cur = c.cursor()
        if autofill is None:
            autofill = ensure_season_champion(cur, closure, now=now, env=env)
        cur.execute(_CHAMP_SQL)
        champs = cur.fetchall()
        cur.execute("TRUNCATE cpbl.championship_members")
        n_player = n_mgr = 0
        for year, code, franchise_code, _verified_at in champs:
            args = {"year": year, "code": code, "fcode": franchise_code, "tid": code[:3]}
            cur.execute(_PLAYERS_SQL, args)
            n_player += cur.rowcount
            cur.execute(_MANAGER_SQL, args)
            n_mgr += cur.rowcount
        verified_at = max((row[3] for row in champs), default=None)
        coverage = championship_coverage([row[0] for row in champs], as_of=verified_at,
                                         through_year=coverage_through_year(closure))
        out = {"champions": len(champs),
               "years": [row[0] for row in champs],
               "coverage": coverage,
               "autofill": autofill,
               "player_rows": n_player, "manager_rows": n_mgr}
    log.info("championship_members rebuilt: %s", out)
    return out
