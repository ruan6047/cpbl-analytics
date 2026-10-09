"""既有正式來源的 cursor reader。只 SELECT；不打服務或逐人 HTTP。"""

from __future__ import annotations

from cpbl.api.helpers import _dicts
from cpbl.completion import completed_games_sql_with_evidence

_DONE = completed_games_sql_with_evidence("g")


def games(cur, season: int) -> list[dict]:
    cur.execute(f"SELECT g.*, {_DONE} AS completed FROM cpbl.games g "
                "WHERE g.year=%s AND g.kind_code IN ('A','E','C') "
                "ORDER BY g.game_date, g.game_sno", (season,))
    return _dicts(cur)


def schedules(cur, season: int) -> list[dict]:
    cur.execute(
        """SELECT year,kind_code,game_sno,raw_present_status,raw_game_result,raw_game_date,
                  payload_hash,raw_payload,fetched_at,last_seen_at,
                  raw_payload->>'IsPlayBall' AS is_play_ball,
                  NULLIF(raw_payload->>'VisitingPitcherAcnt','') AS away_p,
                  NULLIF(raw_payload->>'HomePitcherAcnt','') AS home_p,
                  NULLIF(raw_payload->>'GameDateTimeS','') AS scheduled_start
           FROM cpbl.game_schedule_status_revisions WHERE year=%s AND kind_code IN ('E','C')""",
        (season,),
    )
    return _dicts(cur)


def box(cur, season: int, kind: str, snos: list[int], role: str) -> list[dict]:
    if not snos:
        return []
    if role == "batting":
        query = """SELECT b.hitter_acnt AS player_id,b.hitter_name AS name,b.game_sno,
            b.role_type,b.plate_appearances AS pa,b.at_bats AS ab,b.hits AS h,b.doubles AS b2,
            b.triples AS b3,b.home_runs AS hr,b.bb,b.ibb,b.hbp,b.sac_fly AS sf,b.so,
            b.runs AS r,b.rbi,b.sb,b.cs,b.singles,b.total_bases AS tb,b.sac_hit AS sh,
            CASE b.visiting_home_type WHEN '1' THEN g.away_team_code WHEN '2' THEN g.home_team_code END AS team_code,
            CASE b.visiting_home_type WHEN '1' THEN g.home_team_code WHEN '2' THEN g.away_team_code END AS opponent_code
            FROM cpbl.batting_gamelog b JOIN cpbl.games g
              ON (g.year,g.kind_code,g.game_sno)=(b.year,b.kind_code,b.game_sno)
            WHERE b.year=%s AND b.kind_code=%s AND b.game_sno=ANY(%s)"""
    elif role == "pitching":
        query = """SELECT b.pitcher_acnt AS player_id,b.pitcher_name AS name,b.game_sno,
            b.role_type,b.inning_pitched_cnt*3+b.inning_pitched_div3 AS outs,
            b.earned_runs AS er,b.hits AS h,b.home_runs AS hr,b.bb,b.so,b.hbp,
            b.plate_appearances AS pa,b.pitch_cnt,
            CASE b.visiting_home_type WHEN '1' THEN g.away_team_code WHEN '2' THEN g.home_team_code END AS team_code,
            CASE b.visiting_home_type WHEN '1' THEN g.home_team_code WHEN '2' THEN g.away_team_code END AS opponent_code
            FROM cpbl.pitching_gamelog b JOIN cpbl.games g
              ON (g.year,g.kind_code,g.game_sno)=(b.year,b.kind_code,b.game_sno)
            WHERE b.year=%s AND b.kind_code=%s AND b.game_sno=ANY(%s)"""
    else:
        raise ValueError("未知投打角色")
    cur.execute(query, (season, kind, snos))
    return [{**r, "game_key": f"{season}/{kind}/{r['game_sno']}"} for r in _dicts(cur)]


def people(cur, ids: list[str]) -> dict[str, dict]:
    cur.execute("SELECT id,name,bats,throws FROM cpbl.players WHERE id=ANY(%s)", (ids,))
    return {r["id"]: r for r in _dicts(cur)}


def fielding(cur, season: int) -> list[dict]:
    cur.execute("SELECT * FROM cpbl.fielding_current WHERE year=%s AND kind_code='A'", (season,))
    return _dicts(cur)


def source_revisions(cur, season: int, kind: str, snos: list[int]) -> list[dict]:
    cur.execute(
        """SELECT DISTINCT ON (game_sno,source) game_sno,source,source_version,outcome,row_count,
                  fetched_at,last_seen_at
           FROM cpbl.game_source_revisions WHERE year=%s AND kind_code=%s AND game_sno=ANY(%s)
           ORDER BY game_sno,source,last_seen_at DESC,fetched_at DESC,source_version DESC""",
        (season, kind, snos),
    )
    return _dicts(cur)


def pitching_sources(cur, season: int, kind: str, snos: list[int]) -> list[dict]:
    """既存逐投手 box 版本，首次取得時間不冒稱官方更正時間。"""
    if not snos:
        return []
    cur.execute(
        """SELECT DISTINCT ON (game_sno,pitcher_acnt) game_sno,pitcher_acnt AS player_id,
                  content_hash AS source_version,fetched_at,last_seen_at
           FROM cpbl.box_pitching_revisions WHERE year=%s AND kind_code=%s AND game_sno=ANY(%s)
           ORDER BY game_sno,pitcher_acnt,fetched_at DESC,id DESC""", (season, kind, snos),
    )
    return _dicts(cur)


def matchups(cur, season: int, hitters: list[str], pitchers: list[str]) -> dict[tuple, dict]:
    cur.execute(
        """SELECT hitter_acnt,pitcher_acnt,plate_appearances AS pa,at_bats AS ab,hits AS h,
                  doubles AS b2,triples AS b3,home_runs AS hr,bb,ibb,hbp,sac_fly AS sf,so,updated_at
           FROM cpbl.batter_pitcher_matchups WHERE year=%s AND kind_code='A'
             AND hitter_acnt=ANY(%s) AND pitcher_acnt=ANY(%s)""", (season, hitters, pitchers),
    )
    return {(r["hitter_acnt"], r["pitcher_acnt"]): r for r in _dicts(cur)}
