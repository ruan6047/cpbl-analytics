"""#238 唯讀重建。截止完成集合、公告首見與年度來源各自帶證據，不補未知。"""

from __future__ import annotations

from datetime import UTC, datetime

from cpbl.api import between_games as bg
from cpbl.reports import announcements, background, population, readers
from cpbl.reports.context import bounded_context, key, validate_target
from cpbl.reports.stats import field_candidates, player_period, three_periods, watch_points


def _report_background(cur, season: int, kind: str, anchor: dict, upto: list[dict],
                       regular: list[dict], regular_closed: bool, rosters: list[dict],
                       target: dict | None, schedule_rows: list[dict], lineup: dict,
                       recent_games: list[dict], cache: dict, read_at: str) -> dict:
    """歷史與比較共用既有背景組裝；系列範圍及近期使用範圍各自明示。"""
    team_codes = ([target["away_team_code"], target["home_team_code"]] if target else
                  [anchor["away_team_code"], anchor["home_team_code"]])
    if len(set(team_codes)) != 2 or not all(isinstance(t, str) and t for t in team_codes):
        raise ValueError("比較來源必須有兩個不同隊伍")
    through_keys = [key(g) for g in upto]
    snos = [g["game_sno"] for g in upto]
    regular_snos = [g["game_sno"] for g in regular]
    announced_members = [m for m in lineup["items"] if m["team_code"] in team_codes]
    sources = []
    boxes = {role: readers.box(cur, season, kind, snos, role) for role in ("pitching", "batting")}
    regular_boxes = cache.setdefault("regular_boxes", {})
    for role in boxes:
        if role not in regular_boxes:
            regular_boxes[role] = readers.box(cur, season, "A", regular_snos, role)
    recent_boxes = boxes if recent_games == upto else {
        role: readers.box(cur, season, anchor["kind_code"], [g["game_sno"] for g in recent_games], role)
        for role in boxes
    }
    observed = [r for rows in boxes.values() for r in rows]
    rosters = [population.reconcile(r, observed) for r in rosters]
    candidate_teams = {r["team_code"] for r in rosters if not r["registration_complete"]}
    ids = sorted({r["player_id"] for rows in boxes.values() for r in rows}
                 | {m["player_id"] for roster in rosters for m in roster["members"] if m.get("player_id")})
    next_block = None
    starters = {}
    target_date = None
    if target:
        target_date = datetime.fromisoformat(target["game_date"]).date()
        rows = [r for r in schedule_rows if r["kind_code"] == target["kind_code"] and r["game_sno"] == target["game_sno"]]
        sched = bg.pregame_schedule(rows, target_date)
        next_block = {**target, "game_date": target["game_date"], **sched}
        for side in ("away", "home"):
            starter = next_block[f"{side}_starter"]
            starter["team_code"] = target[f"{side}_team_code"]
            if starter["status"] == "announced":
                starters[starter["team_code"]] = starter["acnt"]
                ids.append(starter["acnt"])
    ids.extend(m["player_id"] for m in announced_members)
    if kind != anchor["kind_code"]:
        ids.extend(r["player_id"] for role in boxes
                   for r in [*regular_boxes[role], *recent_boxes[role]] if r["team_code"] in candidate_teams)
    people = readers.people(cur, sorted(set(ids)))
    if "fields" not in cache:
        cache["fields"] = readers.fielding(cur, season) if regular_closed else []
    fields = cache["fields"]
    hitter_ids = sorted({r["player_id"] for r in boxes["batting"]}
                        | {m["player_id"] for roster in rosters for m in roster["members"]
                           if m.get("player_id") and m.get("role") == "batting"}
                        | {m["player_id"] for m in announced_members})
    if kind != anchor["kind_code"]:
        hitter_ids = sorted(set(hitter_ids) | {r["player_id"] for r in
                            [*regular_boxes["batting"], *recent_boxes["batting"]]
                            if r["team_code"] in candidate_teams})
    pairs = readers.matchups(cur, season, hitter_ids, list(starters.values())) if hitter_ids and starters and regular_closed else {}
    if "verified" not in cache:
        cache["verified"] = background.current_matches(cur, season, regular_boxes) if regular_closed else {}
    verified = cache["verified"]
    teams = background.team_background(season, regular, regular_boxes, team_codes) if regular_closed else []
    cards = background.cards(cur, ids, season, verified)
    players = []
    trait_league_cache = cache.setdefault("trait_league", {})
    for role, rows in boxes.items():
        for team in team_codes:
            roster = next(r for r in rosters if r["team_code"] == team)
            members = {m["player_id"] for m in roster["members"] if m.get("player_id") and m.get("role") == role}
            members |= {r["player_id"] for r in rows if r["team_code"] == team}
            if kind != anchor["kind_code"] and team in candidate_teams:
                # 本季／近期觀測只作候選，不混入 C 正式母體或 C 使用統計。
                members |= {r["player_id"] for r in [*regular_boxes[role], *recent_boxes[role]]
                            if r["team_code"] == team}
            if role == "batting":
                members |= {m["player_id"] for m in announced_members if m["team_code"] == team}
            if role == "pitching" and team in starters:
                members.add(starters[team])
            opponent = next(t for t in team_codes if t != team)
            reg_keys = [key(g) for g in regular if team in (g["away_team_code"], g["home_team_code"])]
            cutoff = f"截至 {season}/{anchor['kind_code']}/{anchor['game_sno']} 完賽"
            for pid in sorted(members):
                player_cache = cache.setdefault("player_background", {})
                if (pid, role) not in player_cache:
                    player_cache[(pid, role)] = background.player_background(
                        cur, pid, role, season, verified.get(role, False), cards[role].get(pid),
                        trait_league_cache=trait_league_cache)
                person = people.get(pid, {})
                periods = three_periods(series=rows, regular=regular_boxes[role], role=role,
                                        player_id=pid, team=team, opponent=opponent,
                                        series_keys=through_keys, regular_keys=reg_keys,
                                        # 註冊完整不等於全 box 完整：既有 reader 只有
                                        # game-range row coverage，不能推出會員未登場。
                                        cutoff=cutoff, complete_population=False,
                                        opponent_keys=[key(g) for g in regular if {team, opponent}
                                                       == {g["away_team_code"], g["home_team_code"]}])
                apps = [{"game_key": r["game_key"], "game_sno": r["game_sno"],
                         "date": g["game_date"], "date_trusted": bg.date_trusted(g),
                         "role_type": r["role_type"], "outs": r["outs"], "pitch_cnt": r["pitch_cnt"]}
                        for g in recent_games for r in recent_boxes[role] if role == "pitching" and r["game_sno"] == g["game_sno"]
                        and r["player_id"] == pid and r["team_code"] == team]
                usage = bg.pitcher_usage(apps, target_date) if role == "pitching" and apps else None
                if usage is not None:
                    usage_period = player_period(recent_boxes[role], role=role, player_id=pid, team=team,
                                                 expected_keys=[key(g) for g in recent_games],
                                                 source="recent_completed_through_X", cutoff=cutoff)
                    usage["coverage_status"] = usage_period["coverage_status"]
                    usage["through_game_keys"] = [key(g) for g in recent_games]
                    usage["cutoff_label"] = cutoff
                    if usage["coverage_status"] != "complete":
                        usage["consecutive_days"] = usage["days_to_next"] = None
                pair = pairs.get((pid, starters.get(opponent))) if role == "batting" else None
                vs = {"status": "missing" if role == "batting" else "not_applicable",
                      "pitcher_id": starters.get(opponent) if role == "batting" else None}
                if pair:
                    vs = {"status": "available", "pitcher_id": pair["pitcher_acnt"],
                          "counts": {**bg.sum_batting([pair]), "g": None}, "sample": {"pa": pair["pa"], "ab": pair["ab"]},
                          "source": "batter_pitcher_matchups_A", "updated_at": pair["updated_at"],
                          "covered_game_keys": [], "coverage_status": "unverified"}
                players.append({"player_id": pid, "team_code": team, "role": role,
                                "name": next((m.get("name") for m in roster["members"]
                                              if m["player_id"] == pid), None)
                                        or next((m.get("name") for m in announced_members
                                                 if m["player_id"] == pid and m["team_code"] == team), None)
                                        or person.get("name")
                                        or next((r["name"] for r in [*rows, *recent_boxes[role], *regular_boxes[role]]
                                                 if r["player_id"] == pid and r["team_code"] == team), None),
                                "bats": person.get("bats"), "throws": person.get("throws"),
                                "periods": periods, "pitching_usage": usage, "vs_starter": vs,
                                "fielding": [r for r in fields if r["player_id"] == pid and r["team_code"] == team],
                                "last_game": player_period(recent_boxes[role], role=role, player_id=pid, team=team,
                                                           expected_keys=[key(anchor)],
                                                           source="box_X", cutoff=cutoff),
                                **player_cache[(pid, role)]})
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
            starter["name"] = next((p["name"] for p in players if p["role"] == "pitching"
                                    and p["player_id"] == starter["acnt"]
                                    and p["team_code"] == starter["team_code"]),
                                   people.get(starter["acnt"], {}).get("name"))
    return {"next_game": next_block, "population": rosters,
            "players": players, "sources": sources,
            "regular_coverage": {"year": season, "kind": "A", "closed_before_X": regular_closed,
                                 "covered_game_keys": [key(g) for g in regular], "current_matches_A": verified},
            "field_candidates": {t: field_candidates(fields, team=t,
                                                       player_ids={p["player_id"] for p in players if p["team_code"] == t})
                                 for t in team_codes},
            "teams": teams, "watch_points": watch_points(players, team_codes=team_codes,
                                                        anchor_key=key(anchor)),
            "announcements": {"lineup": lineup},
            "coverage": {"games": len(upto), "with_pitching": len({r["game_sno"] for r in boxes["pitching"]}),
                         "with_batting": len({r["game_sno"] for r in boxes["batting"]})}}


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
    team_codes = [anchor["away_team_code"], anchor["home_team_code"]]
    if not all(isinstance(t, str) and t for t in team_codes) or len(set(team_codes)) != 2:
        raise ValueError("完賽來源必須有兩個不同隊伍")
    rosters = [population.adapt(population_records or [], season, kind, t) for t in team_codes]
    schedule_rows = readers.schedules(cur, season)
    preliminary = bounded_context(anchor, all_games, schedule_rows)
    identities = {(kind, t) for t in team_codes}
    identities.update((row["kind_code"], row[f"{side}_team_code"])
                      for row in preliminary["rows"] if row["game_date"] >= preliminary["cutoff_date"]
                      for side in ("away", "home"))
    population_sources = population.provenance([
        population.adapt(population_records or [], season, k, t) for k, t in sorted(identities)])
    context = bounded_context(anchor, all_games, schedule_rows, population_sources)
    candidates = [r for r in context["rows"] if key(r) not in context["through_game_keys"]
                  and r["game_date"] >= context["cutoff_date"]]
    lineup_rows = readers.lineup_revisions(cur, season, candidates)
    materials = announcements.context_materials(lineup_rows, schedule_rows, candidates) if lineup_rows else []
    if materials:
        context = bounded_context(anchor, all_games, schedule_rows, population_sources, materials)
    target = validate_target(context, next_kind, next_sno, supplied_hash) if next_kind else None
    lineup = next((m["lineup"] for m in materials if target and m["game_key"] == key(target)),
                  {"status": "unverified", "items": []})
    through_keys = context["through_game_keys"]
    upto = [g for g in all_games if key(g) in through_keys]
    snos = [g["game_sno"] for g in upto]
    regular_games = [g for g in all_games if g["kind_code"] == "A"]
    regular_closed = bool(regular_games) and all(g["completed"] and g["game_date"] < anchor["game_date"]
                                                  for g in regular_games)
    regular = [g for g in regular_games if g["completed"] and g["game_date"] < anchor["game_date"]]
    read_at = datetime.now(UTC).isoformat()
    sources = [{"source": "game_completion", "scope": {"year": season, "kind": kind},
                "reference": f"/api/v1/games/{sno}/status?season={season}&kind_code={kind}",
                "source_version": None, "fetched_at": None, "updated_at": None,
                "covered_game_keys": through_keys, "coverage_status": "available",
                "cutoff_basis": "completed_collection_through_X", "read_at": read_at},
               *[{**s, "scope": {"year": season, "kind": s["game_key"].split('/')[1]},
                  "covered_game_keys": [s["game_key"]], "coverage_status": "available",
                  "updated_at": None, "read_at": read_at} for s in context["sources"]]]
    sources.extend({**s, "read_at": read_at} for s in population_sources)
    if target and lineup.get("source_version"):
        sources.append({"source": "lineup_announcement", "scope": {"year": season, "kind": next_kind,
                        "game_sno": next_sno}, "reference": lineup["source_url"],
                        "source_version": lineup["source_version"], "fetched_at": lineup.get("observed_at"),
                        "updated_at": None, "read_at": read_at, "covered_game_keys": [key(target)],
                        "coverage_status": lineup["status"], "cutoff_basis": "positive_scheduled_before_started_observation"})
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
    cache = {}
    cross_series = bool(target and (target["kind_code"] != kind or
                                   {target["away_team_code"], target["home_team_code"]} != set(team_codes)))
    historical = _report_background(cur, season, kind, anchor, upto, regular, regular_closed,
                                    rosters, None if cross_series else target, schedule_rows,
                                    {"status": "unverified", "items": []} if cross_series else lineup,
                                    upto, cache, read_at)
    comparison = None
    if cross_series:
        comparison_games = [g for g in all_games if g["completed"] and g["kind_code"] == next_kind
                            and g["game_date"] <= anchor["game_date"]]
        comparison_rosters = [population.adapt(population_records or [], season, next_kind, t)
                              for t in (target["away_team_code"], target["home_team_code"])]
        comparison = _report_background(cur, season, next_kind, anchor, comparison_games, regular,
                                        regular_closed, comparison_rosters, target, schedule_rows,
                                        lineup, upto, cache, read_at)
        comparison["game"] = comparison.pop("next_game")
        comparison["kind_code"] = next_kind
        comparison["series_game_keys"] = [key(g) for g in comparison_games]
        comparison["usage_cutoff_label"] = f"近期使用，截至 {season}/{kind}/{sno} 完賽"
        sources.extend(comparison["sources"])
    sources.extend(historical.pop("sources"))
    return {**base, "status": "ok", "game": anchor,
            "anchor": {**base, "completed": True, "through_game_keys": through_keys,
                       "cutoff_label": f"截至 {season}/{kind}/{sno} 完賽", "completed_observed_at": None},
            "journey_context": context, **historical,
            "next_game": comparison["game"] if comparison else historical["next_game"],
            "comparison": comparison, "sources": sources, "read_at": read_at}


def report_anchor(cur, season: int, kind: str, sno: int) -> dict:
    """Y 須有既存正式列；只定位最新完賽 E/C 為截至場 X，下一場判定仍交 journey。"""
    games = readers.games(cur, season)
    own = next((g for g in games if g["kind_code"] == kind and g["game_sno"] == sno), None)
    base = {"season": season, "kind_code": kind, "game_sno": sno}
    if own is not None and own["completed"]:
        return {**base, "status": "final"}
    if own is None and not any(r["kind_code"] == kind and r["game_sno"] == sno
                               for r in readers.schedules(cur, season)):
        return {**base, "status": "not_found"}
    done = [g for g in games if g["kind_code"] in ("E", "C") and g["completed"]]
    if not done:
        return {**base, "status": "no_anchor"}
    anchor = max(done, key=lambda g: (g["game_date"], g["kind_code"] == "C", g["game_sno"]))
    return {**base, "status": "ok",
            "anchor": {"kind_code": anchor["kind_code"], "game_sno": anchor["game_sno"]}}
