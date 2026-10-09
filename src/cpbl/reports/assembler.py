"""#238 唯讀重建。截止完成集合、公告首見與年度來源各自帶證據，不補未知。"""

from __future__ import annotations

from datetime import UTC, datetime

from cpbl.api import between_games as bg
from cpbl.reports import background, population, readers
from cpbl.reports.context import bounded_context, key, validate_target
from cpbl.reports.stats import field_candidates, player_period, three_periods, watch_points


def build_report(cur, season: int, kind: str, sno: int, next_kind: str | None = None,
                 next_sno: int | None = None, supplied_hash: str | None = None,
                 population_records: list[dict] | None = None) -> dict:
    all_games = readers.games(cur, season)
    anchor = next((g for g in all_games if g["kind_code"] == kind and g["game_sno"] == sno), None)
    base = {"season": season, "kind_code": kind, "game_sno": sno}
    if anchor is None:
        return {**base, "status": "not_found"}
    if not anchor["completed"]:
        return {**base, "status": "not_final", "game": anchor}
    schedule_rows = readers.schedules(cur, season)
    context = bounded_context(anchor, all_games, schedule_rows)
    target = validate_target(context, next_kind, next_sno, supplied_hash) if next_kind else None
    through_keys = context["through_game_keys"]
    upto = [g for g in all_games if key(g) in through_keys]
    snos = [g["game_sno"] for g in upto]
    team_codes = [anchor["away_team_code"], anchor["home_team_code"]]
    rosters = [population.adapt(population_records or [], season, kind, t) for t in team_codes]
    regular_games = [g for g in all_games if g["kind_code"] == "A"]
    regular_closed = bool(regular_games) and all(g["completed"] and g["game_date"] < anchor["game_date"]
                                                  for g in regular_games)
    regular = [g for g in regular_games if g["completed"] and g["game_date"] < anchor["game_date"]]
    regular_snos = [g["game_sno"] for g in regular]
    read_at = datetime.now(UTC).isoformat()
    sources = [{"source": "game_completion", "scope": {"year": season, "kind": kind},
                "reference": f"/api/v1/games/{sno}/status?season={season}&kind_code={kind}",
                "source_version": None, "fetched_at": None, "updated_at": None,
                "covered_game_keys": through_keys, "coverage_status": "available",
                "cutoff_basis": "completed_collection_through_X", "read_at": read_at},
               *[{**s, "scope": {"year": season, "kind": s["game_key"].split('/')[1]},
                  "covered_game_keys": [s["game_key"]], "coverage_status": "available",
                  "updated_at": None, "read_at": read_at} for s in context["sources"]]]
    for r in readers.source_revisions(cur, season, kind, snos):
        sources.append({**r, "scope": {"year": season, "kind": kind},
                        "reference": f"/api/v1/games/{r['game_sno']}/live?season={season}&kind_code={kind}",
                        "covered_game_keys": [f"{season}/{kind}/{r['game_sno']}"],
                        "coverage_status": r["outcome"], "cutoff_basis": "through_X", "read_at": read_at})
    for r in readers.pitching_sources(cur, season, kind, snos):
        sources.append({**r, "source": "box_pitching", "scope": {"year": season, "kind": kind,
                        "role": "pitching", "player_id": r["player_id"]},
                        "reference": f"/api/v1/games/{r['game_sno']}/live?season={season}&kind_code={kind}",
                        "covered_game_keys": [f"{season}/{kind}/{r['game_sno']}"], "updated_at": None,
                        "coverage_status": "available", "cutoff_basis": "through_X", "read_at": read_at})
    boxes = {role: readers.box(cur, season, kind, snos, role) for role in ("pitching", "batting")}
    regular_boxes = {role: readers.box(cur, season, "A", regular_snos, role) for role in boxes}
    ids = sorted({r["player_id"] for rows in boxes.values() for r in rows}
                 | {m["player_id"] for roster in rosters for m in roster["members"] if m.get("player_id")})
    next_block = None
    starters = {}
    if target:
        date = datetime.fromisoformat(target["game_date"]).date()
        rows = [r for r in schedule_rows if r["kind_code"] == next_kind and r["game_sno"] == next_sno]
        sched = bg.pregame_schedule(rows, date)
        next_block = {**target, "game_date": target["game_date"], **sched}
        for side in ("away", "home"):
            starter = next_block[f"{side}_starter"]
            starter["team_code"] = target[f"{side}_team_code"]
            if starter["status"] == "announced":
                starters[starter["team_code"]] = starter["acnt"]
                ids.append(starter["acnt"])
    people = readers.people(cur, sorted(set(ids)))
    fields = readers.fielding(cur, season) if regular_closed else []
    pairs = readers.matchups(cur, season, ids, list(starters.values())) if starters and regular_closed else {}
    verified = background.current_matches(cur, season, regular_boxes) if regular_closed else {}
    teams = background.team_background(season, regular, regular_boxes, team_codes) if regular_closed else []
    cards = background.cards(cur, ids, season, verified)
    players = []
    for role, rows in boxes.items():
        for team in team_codes:
            roster = next(r for r in rosters if r["team_code"] == team)
            members = {m["player_id"] for m in roster["members"] if m.get("player_id") and m.get("role") == role}
            members |= {r["player_id"] for r in rows if r["team_code"] == team}
            if role == "pitching" and team in starters:
                members.add(starters[team])
            opponent = next(t for t in team_codes if t != team)
            reg_keys = [key(g) for g in regular if team in (g["away_team_code"], g["home_team_code"])]
            cutoff = f"截至 {season}/{kind}/{sno} 完賽"
            for pid in sorted(members):
                person = people.get(pid, {})
                periods = three_periods(series=rows, regular=regular_boxes[role], role=role,
                                        player_id=pid, team=team, opponent=opponent,
                                        series_keys=through_keys, regular_keys=reg_keys,
                                        cutoff=cutoff, complete_population=roster["complete"],
                                        opponent_keys=[key(g) for g in regular if {team, opponent}
                                                       == {g["away_team_code"], g["home_team_code"]}])
                apps = [{"game_key": r["game_key"], "game_sno": r["game_sno"],
                         "date": g["game_date"], "date_trusted": bg.date_trusted(g),
                         "role_type": r["role_type"], "outs": r["outs"], "pitch_cnt": r["pitch_cnt"]}
                        for g in upto for r in rows if role == "pitching" and r["game_sno"] == g["game_sno"]
                        and r["player_id"] == pid and r["team_code"] == team]
                usage = bg.pitcher_usage(apps, date if target else None) if role == "pitching" else None
                if usage and periods["series"]["coverage_status"] != "complete":
                    usage["coverage_status"] = "partial"
                    usage["consecutive_days"] = usage["days_to_next"] = None
                pair = pairs.get((pid, starters.get(opponent)))
                vs = {"status": "missing", "pitcher_id": starters.get(opponent)}
                if pair:
                    vs = {"status": "available", "pitcher_id": pair["pitcher_acnt"],
                          "counts": {**bg.sum_batting([pair]), "g": None}, "sample": {"pa": pair["pa"], "ab": pair["ab"]},
                          "source": "batter_pitcher_matchups_A", "updated_at": pair["updated_at"],
                          "covered_game_keys": [], "coverage_status": "unverified"}
                players.append({"player_id": pid, "team_code": team, "role": role,
                                "name": person.get("name") or next((r["name"] for r in rows if r["player_id"] == pid), None),
                                "bats": person.get("bats"), "throws": person.get("throws"),
                                "periods": periods, "pitching_usage": usage, "vs_starter": vs,
                                "fielding": [r for r in fields if r["player_id"] == pid and r["team_code"] == team],
                                "last_game": player_period(rows, role=role, player_id=pid, team=team,
                                                           expected_keys=[f"{season}/{kind}/{sno}"],
                                                           source="box_X", cutoff=cutoff),
                                **background.player_background(cur, pid, role, season, verified.get(role, False), cards[role].get(pid))})
    for p in players:
        advanced = p.get("official_pr")
        if advanced:
            sources.append({"source": "advanced_stats_A", "player_id": p["player_id"],
                            "scope": {"year": season, "kind": "A", "role": p["role"]},
                            "reference": f"/api/v1/players/{p['player_id']}/advanced?season={season}&kind_code=A",
                            "source_version": str(advanced["source_run_id"]) if advanced.get("source_run_id") else None,
                            "fetched_at": advanced.get("source_fetched_at"), "updated_at": advanced.get("updated_at"),
                            "read_at": read_at, "coverage_status": "available", "cutoff_basis": "closed_A_before_X"})
    if next_block:
        for side in ("away", "home"):
            starter = next_block[f"{side}_starter"]
            starter["name"] = people.get(starter["acnt"], {}).get("name")
    return {**base, "status": "ok", "game": anchor,
            "anchor": {**base, "completed": True, "through_game_keys": through_keys,
                       "cutoff_label": f"截至 {season}/{kind}/{sno} 完賽", "completed_observed_at": None},
            "journey_context": context, "next_game": next_block, "population": rosters,
            "players": players, "sources": sources, "read_at": read_at,
            "regular_coverage": {"year": season, "kind": "A", "closed_before_X": regular_closed,
                                 "covered_game_keys": [key(g) for g in regular], "current_matches_A": verified},
            "field_candidates": {t: field_candidates(fields, team=t,
                                                       player_ids={p["player_id"] for p in players if p["team_code"] == t})
                                 for t in team_codes},
            "teams": teams, "watch_points": watch_points(players, team_codes=team_codes,
                                                        anchor_key=f"{season}/{kind}/{sno}"),
            "announcements": {"lineup": {"status": "unverified", "items": []}},
            "coverage": {"games": len(upto), "with_pitching": len({r["game_sno"] for r in boxes["pitching"]}),
                         "with_batting": len({r["game_sno"] for r in boxes["batting"]})}}
