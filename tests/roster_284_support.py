"""#284 名單測試共用：身份佐證 fixture 載入、隔離 DB 種子與 DSN 身分斷言。

fixture `tests/fixtures/roster_284_identity.json` 是本機共享 cpbl 的唯讀匯出（只含鍵欄；
查詢與匯出時間在檔內 meta）。樣本＝official_population 2026 E 兩隊 64 人＋同名他人＋
兩隊 2026 team_roster；⛔ 不自造 32 人——變異一律是對真實樣本的單點改動。
"""

from __future__ import annotations

import json
import os
from functools import cache
from pathlib import Path

import pytest
from psycopg.conninfo import conninfo_to_dict

from cpbl.rosters.identity import EVIDENCE_KINDS, PlayerRecord, TeamYearContext

FIXTURE = Path(__file__).parent / "fixtures" / "roster_284_identity.json"

# 卡號隔離資源（本卡 Resource 欄）：容器 cpbl284-pg 127.0.0.1:55284。
LOCAL_DB = ("127.0.0.1", "55284", "cpbl_test_284")
PROD_DB = ("127.0.0.1", "55284", "cpbl_test_284_prod")


@cache
def fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def isolated_dsn(env: str, expected: tuple[str, str, str]) -> str:
    """opt-in DSN；未設＝skip（⛔ skip 不算通過），設了但不是本卡資源＝fail。"""
    dsn = os.environ.get(env)
    if not dsn:
        pytest.skip(f"{env} 未設（#284 隔離 DB 演練為 opt-in）")
    d = conninfo_to_dict(dsn)
    if (d.get("host"), str(d.get("port")), d.get("dbname")) != expected:
        pytest.fail(f"{env} 不在 #284 隔離資源 {expected}", pytrace=False)
    return dsn


def context_from_fixture(year: int, team: str, extra_names: list[str] = ()) -> TeamYearContext:
    """以 fixture 重建 load_context 的同一份佐證（純函式測試用）。"""
    doc = fixture()
    players = {r[0]: PlayerRecord(r[0], r[1], r[2]) for r in doc["players"]}
    evidence: dict[str, set[str]] = {}
    roster_names: dict[str, str] = {}
    for y, t, pid, name in doc["team_roster"]:
        if y == year and t == team:
            evidence.setdefault(pid, set()).add("team_roster")
            roster_names[pid] = name
    games = {(g[0], g[1], g[3]): (g[4], g[5]) for g in doc["games"]}
    for table in ("batting_gamelog", "pitching_gamelog"):
        for y, kind, sno, pid, vht in doc[table]:
            if y != year or kind not in EVIDENCE_KINDS or (y, kind, sno) not in games:
                continue
            home, away = games[(y, kind, sno)]
            if (vht == "2" and home == team) or (vht == "1" and away == team):
                evidence.setdefault(pid, set()).add(f"gamelog_{kind}")
    return TeamYearContext(year=year, team_code=team, team_known=True, players=players,
                           evidence=evidence, roster_names=roster_names)


def seed(c) -> None:
    """把 fixture 鍵欄灌進隔離 DB（冪等）。只寫本卡隔離庫。"""
    doc = fixture()
    with c.cursor() as cur:
        cur.executemany(
            "INSERT INTO cpbl.players (id, name, country) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
            doc["players"])
        cur.executemany(
            "INSERT INTO cpbl.team_roster (year, team_code, player_id, name) VALUES (%s, %s, %s, %s) "
            "ON CONFLICT DO NOTHING", doc["team_roster"])
        cur.executemany(
            "INSERT INTO cpbl.games (year, kind_code, game_season_code, game_sno, home_team_code, "
            "away_team_code) VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING", doc["games"])
        cur.executemany(
            "INSERT INTO cpbl.batting_gamelog (year, kind_code, game_sno, hitter_acnt, "
            "visiting_home_type) VALUES (%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
            doc["batting_gamelog"])
        cur.executemany(
            "INSERT INTO cpbl.pitching_gamelog (year, kind_code, game_sno, pitcher_acnt, "
            "visiting_home_type) VALUES (%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
            doc["pitching_gamelog"])


ROSTER_TABLES = ("roster_annotation_revision", "series_roster_member", "series_roster")
SEED_TABLES = ("batting_gamelog", "pitching_gamelog", "games", "team_roster", "players")


def reset(c) -> None:
    """測試隔離用：清空名單三表與種子表。

    名單三表有不可變觸發器（含 TRUNCATE），測試重置只能在本卡隔離庫以
    session_replication_role=replica 暫停使用者觸發器——⛔ 這不是任何正式路徑。
    """
    db = c.execute("SELECT current_database()").fetchone()[0]
    assert db in (LOCAL_DB[2], PROD_DB[2]), db
    c.execute("SET session_replication_role = replica")
    for t in ROSTER_TABLES:
        c.execute(f"TRUNCATE cpbl.{t} CASCADE")  # 表名來自上方常數
    for t in SEED_TABLES:
        if t == "players":
            c.execute("DELETE FROM cpbl.players")
        else:
            c.execute(f"TRUNCATE cpbl.{t}")
    c.execute("SET session_replication_role = origin")
