"""年度總冠軍成員：離線重建 cpbl.championship_members。

冠軍隊由官網已入庫的 games(kind_code='C', 總冠軍賽) 推導（系列賽勝場最多者），
不需另爬。對每個冠軍 (year, team_code)：
  - 球員：該年一軍有成績者。pre-2018 用 season 表(team_id=隊碼前三碼)；
    2018+（含 season 表缺漏的 2025）改用 gamelog，以 visiting_home_type 判隊
    （'2'=主、'1'=客）。投打 season/gamelog 全 UNION 去重。
  - 總教練：managers 表（姓名→players.id，任期涵蓋冠軍年）。

冪等：每次 TRUNCATE 後重建。資料界線：games kind C 缺的年份（如 1992/1994/1995）
無法標注；總冠軍總教練僅限 managers 姓名能對到 players.id 者。
"""

from __future__ import annotations

import logging

from cpbl.db import conn

log = logging.getLogger("cpbl.champ")

# 各年冠軍隊（系列賽勝場最多者）。team_code 形如 AAA011，前三碼對 season 表 team_id。
_CHAMP_SQL = """
WITH cg AS (
  SELECT year,
    CASE WHEN home_score > away_score THEN home_team_code ELSE away_team_code END AS wcode
  FROM cpbl.games WHERE kind_code = 'C' AND home_score <> away_score
), champ AS (
  SELECT year, wcode, row_number() OVER (PARTITION BY year ORDER BY count(*) DESC) rn
  FROM cg GROUP BY year, wcode
)
SELECT year, wcode FROM champ WHERE rn = 1 ORDER BY year
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
WHERE m.team_code = %(code)s AND %(year)s BETWEEN m.from_year AND m.to_year
ON CONFLICT (player_id, year) DO NOTHING
"""


def build_championships() -> dict:
    with conn() as c:
        cur = c.cursor()
        cur.execute(_CHAMP_SQL)
        champs = cur.fetchall()
        cur.execute("TRUNCATE cpbl.championship_members")
        n_player = n_mgr = 0
        for year, code in champs:
            args = {"year": year, "code": code, "tid": code[:3]}
            cur.execute(_PLAYERS_SQL, args)
            n_player += cur.rowcount
            cur.execute(_MANAGER_SQL, args)
            n_mgr += cur.rowcount
        out = {"champions": len(champs),
               "years": [y for y, _ in champs],
               "player_rows": n_player, "manager_rows": n_mgr}
    log.info("championship_members rebuilt: %s", out)
    return out
